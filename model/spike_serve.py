"""
SpikeServe: Spike-encoded activation layer for any LLM.

Extracts SpikingBrain's core innovation -- dynamic spike encoding of
activations -- and applies it as a hook-based optimization layer on any
transformer model.

Key idea: Instead of quantizing weights (like GPTQ/GGUF), this quantizes
ACTIVATIONS into integer spike counts.  ~40-60% of those counts are zero,
which on sparse-aware hardware means 40-60% fewer multiplications.

This STACKS on top of weight quantization (bitsandbytes 4-bit):
  Weights  -> 4-bit NF4 quantization  (bitsandbytes)
  Activations -> Dynamic spike encoding (SpikeServe)
"""

import torch
import torch.nn as nn
from collections import defaultdict

_spike_stats = defaultdict(lambda: {"total": 0, "zeros": 0, "calls": 0})
_track_stats = True


def dynamic_spikes(x, k=3.0, max_spike=7):
    """Convert floating-point activations to integer spike counts.

    Algorithm (from SpikingBrain W8ASpike/quant_linear.py):
      1. Adaptive threshold: vth = mean(|x|) / k
      2. Quantize: spikes = round(x / vth)
      3. Clamp to [-max_spike, max_spike]
      4. Reconstruct: x_approx = spikes * vth

    Sparsity emerges naturally: values within +/-vth/2 of zero round to 0.
    """
    vth = x.abs().mean(dim=-1, keepdim=True).float() / k
    vth = vth.clamp(min=1e-5, max=1e4)
    spikes_int = (x.float() / vth).round()
    spikes_int = spikes_int.clamp(-max_spike, max_spike)
    return spikes_int, vth


def apply_spike_hooks(model, k=3.0, max_spike=7, skip_patterns=None,
                      measure_only=True):
    """Attach spike-analysis hooks to eligible linear layers.

    When *measure_only=True* (default), the hooks compute sparsity
    metrics but do NOT modify the activations -- the model runs at
    full fidelity while we report what sparsity spike encoding would
    achieve.

    When *measure_only=False*, activations are replaced with their
    spike-encoded approximations (requires a model trained for this).
    """
    skip_patterns = skip_patterns or [
        "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    ]

    hooks = []
    converted = 0

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

        def _make_hook(layer_name, k_val, max_s, passive):
            def _hook(mod, args):
                if not _track_stats:
                    return None if passive else args
                x = args[0]
                if not x.is_floating_point() or x.dim() < 2:
                    return None if passive else args

                spikes_int, vth = dynamic_spikes(x, k=k_val, max_spike=max_s)
                total = spikes_int.numel()
                zeros = (spikes_int == 0).sum().item()
                st = _spike_stats[layer_name]
                st["total"] += total
                st["zeros"] += zeros
                st["calls"] += 1

                if passive:
                    return None  # don't modify activations

                x_approx = (spikes_int * vth).to(x.dtype)
                return (x_approx,) + args[1:] if len(args) > 1 else (x_approx,)
            return _hook

        h = module.register_forward_pre_hook(
            _make_hook(name, k, max_spike, measure_only)
        )
        hooks.append(h)
        converted += 1

    return hooks, converted


def get_sparsity_stats():
    """Average activation sparsity across all spike-encoded layers."""
    if not _spike_stats:
        return {"avg_sparsity": 0.0, "layers": 0, "total_calls": 0}

    total_elements = 0
    total_zeros = 0
    total_calls = 0
    for stats in _spike_stats.values():
        total_elements += stats["total"]
        total_zeros += stats["zeros"]
        total_calls += stats["calls"]

    pct = (total_zeros / total_elements * 100) if total_elements > 0 else 0.0
    return {
        "avg_sparsity": round(pct, 1),
        "layers": len(_spike_stats),
        "total_calls": total_calls,
    }


def set_tracking(enabled: bool):
    global _track_stats
    _track_stats = enabled


def reset_sparsity_stats():
    _spike_stats.clear()
