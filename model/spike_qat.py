"""
SpikeQAT: Straight-Through Estimator spike encoding for Quantization-Aware Training.

Companion to spike_serve.py.  spike_serve uses dynamic_spikes() for
inference measurement; this module wraps the same quantization in a
custom autograd Function so gradients flow through round() via STE,
enabling end-to-end training with spike-encoded activations.

Imported by: train_qat.py, eval_spike.py, serve_local_4bit.py
"""

import torch
import torch.nn as nn
from collections import defaultdict

# ---------------------------------------------------------------------------
# Module-level mutable state (hooks read these every forward pass)
# ---------------------------------------------------------------------------
_current_k: float = 8.0
_current_max_spike: int = 31

_qat_stats = defaultdict(lambda: {"total": 0, "zeros": 0, "calls": 0})
_qat_tracking = True


def set_k(k: float):
    global _current_k
    _current_k = k


def set_max_spike(ms: int):
    global _current_max_spike
    _current_max_spike = ms


def set_qat_tracking(enabled: bool):
    global _qat_tracking
    _qat_tracking = enabled


def reset_qat_stats():
    _qat_stats.clear()


def get_qat_sparsity_stats() -> dict:
    if not _qat_stats:
        return {"avg_sparsity": 0.0, "layers": 0, "total_calls": 0}

    total_elements = 0
    total_zeros = 0
    total_calls = 0
    for stats in _qat_stats.values():
        total_elements += stats["total"]
        total_zeros += stats["zeros"]
        total_calls += stats["calls"]

    pct = (total_zeros / total_elements * 100) if total_elements > 0 else 0.0
    return {
        "avg_sparsity": round(pct, 1),
        "layers": len(_qat_stats),
        "total_calls": total_calls,
    }


# ---------------------------------------------------------------------------
# STE autograd function
# ---------------------------------------------------------------------------
class SpikeSTEFunction(torch.autograd.Function):
    """Forward: quantize activations to integer spikes and reconstruct.
    Backward: straight-through (gradient passes as if quantization was identity).
    """

    @staticmethod
    def forward(ctx, x, k, max_spike):
        vth = x.abs().mean(dim=-1, keepdim=True).float() / k
        vth = vth.clamp(min=1e-5, max=1e4)
        spikes = (x.float() / vth).round().clamp(-max_spike, max_spike)
        return (spikes * vth).to(x.dtype)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output, None, None


def spike_ste(x: torch.Tensor, k: float, max_spike: int) -> torch.Tensor:
    return SpikeSTEFunction.apply(x, k, max_spike)


# ---------------------------------------------------------------------------
# Hook attachment
# ---------------------------------------------------------------------------
def apply_spike_hooks_trainable(model, k=8.0, max_spike=31, skip_patterns=None, layer_stride=1):
    """Attach STE spike-encoding hooks to eligible Linear layers.

    Unlike spike_serve.apply_spike_hooks, this always modifies activations
    (no measure_only mode) and uses SpikeSTEFunction so gradients flow
    through for QAT.

    The hooks read from module-level _current_k / _current_max_spike on
    every forward pass, so call set_k() to change k mid-training without
    re-attaching hooks.

    Args:
        layer_stride: Only hook every Nth eligible layer (1 = all, 4 = every 4th).

    Returns (hooks_list, num_converted_layers).
    """
    global _current_k, _current_max_spike
    _current_k = k
    _current_max_spike = max_spike

    skip_patterns = skip_patterns or [
        "embed", "lm_head", "layernorm", "norm", "visual", "merger",
        "q_proj", "k_proj", "v_proj", "o_proj",
    ]

    hooks = []
    converted = 0
    eligible_idx = 0

    for name, module in model.named_modules():
        if any(p in name.lower() for p in skip_patterns):
            continue

        is_linear = isinstance(module, nn.Linear)
        try:
            import bitsandbytes as bnb
            is_linear = is_linear or isinstance(
                module, (bnb.nn.Linear4bit, bnb.nn.Linear8bitLt)
            )
        except ImportError:
            pass

        if not is_linear:
            continue

        if eligible_idx % layer_stride != 0:
            eligible_idx += 1
            continue
        eligible_idx += 1

        def _make_hook(layer_name):
            def _hook(mod, args):
                x = args[0]
                if not x.is_floating_point() or x.dim() < 2:
                    return args

                x_enc = spike_ste(x, _current_k, _current_max_spike)

                if _qat_tracking:
                    with torch.no_grad():
                        # Reuse the already-computed encoded tensor to measure sparsity.
                        # Compare against a small threshold instead of recomputing spikes,
                        # and accumulate on GPU to avoid per-layer CUDA syncs.
                        vth = x.abs().mean(dim=-1, keepdim=True).float() / _current_k
                        vth = vth.clamp(min=1e-5, max=1e4)
                        near_zero = (x_enc.abs() < vth * 0.5)
                        st = _qat_stats[layer_name]
                        st["total"] += x_enc.numel()
                        st["zeros"] += int(near_zero.sum())
                        st["calls"] += 1

                return (x_enc,) + args[1:] if len(args) > 1 else (x_enc,)
            return _hook

        h = module.register_forward_pre_hook(_make_hook(name))
        hooks.append(h)
        converted += 1

    return hooks, converted


# ---------------------------------------------------------------------------
# K curriculum scheduler
# ---------------------------------------------------------------------------
class KCurriculumScheduler:
    """Anneal the spike threshold divisor *k* over training.

    High k = fine quantization grid (more spike levels, lower sparsity).
    Low  k = coarse grid (fewer levels, higher sparsity, more aggressive).

    Supports two modes:
      "step"   - discrete k values at specified step boundaries
      "linear" - linear interpolation from start_k to end_k
    """

    DEFAULT_SCHEDULE = [
        (0, 50.0),
        (6000, 25.0),
        (12000, 12.0),
        (18000, 8.0),
        (24000, 5.0),
    ]

    def __init__(
        self,
        mode: str = "step",
        k_schedule=None,
        total_steps: int = 30000,
        warmup_steps: int = 0,
        start_k: float = 50.0,
        end_k: float = 5.0,
    ):
        self.mode = mode
        self.total_steps = total_steps
        self.warmup_steps = warmup_steps
        self.start_k = start_k
        self.end_k = end_k

        if mode == "step":
            self.schedule = sorted(k_schedule or self.DEFAULT_SCHEDULE, key=lambda t: t[0])
        else:
            self.schedule = None

    def get_k(self, current_step: int) -> float:
        if current_step < self.warmup_steps:
            return self.start_k

        if self.mode == "linear":
            effective = current_step - self.warmup_steps
            span = max(self.total_steps - self.warmup_steps, 1)
            t = min(effective / span, 1.0)
            return self.start_k + (self.end_k - self.start_k) * t

        # step mode: find the last boundary <= current_step
        k_val = self.schedule[0][1]
        for step_boundary, k in self.schedule:
            if current_step >= step_boundary:
                k_val = k
            else:
                break
        return k_val
