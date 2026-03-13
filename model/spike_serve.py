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

import threading  # provides thread-safe locking primitives

import torch  # core tensor computation library
import torch.nn as nn  # neural network module definitions
from collections import defaultdict  # dict with auto-initialized default values

_spike_stats = defaultdict(lambda: {"total": 0, "zeros": 0, "calls": 0})  # per-layer sparsity statistics accumulator
_track_stats = True  # global toggle for statistics collection
_spike_lock = threading.Lock()  # mutex protecting concurrent stats updates


class AdaptiveKController:
    """Dynamically adjusts spike threshold k per-layer based on activation statistics.

    Layers with higher activation variance benefit from a larger k (finer grid),
    while layers with concentrated activations can use a smaller k (more aggressive
    sparsity) without quality loss.

    The controller profiles each layer's activation distribution during the first
    N forward passes (calibration phase), then locks in per-layer k values.
    """

    def __init__(self, base_k: float = 3.0, min_k: float = 2.0, max_k: float = 8.0,
                 calibration_passes: int = 10, target_sparsity: float = 0.55):
        self._base_k = base_k
        self._min_k = min_k
        self._max_k = max_k
        self._calibration_passes = calibration_passes
        self._target_sparsity = target_sparsity
        self._layer_stats: dict[str, dict] = {}
        self._layer_k: dict[str, float] = {}
        self._calibrated = False
        self._pass_count = 0
        self._lock = threading.Lock()

    def record(self, layer_name: str, x: torch.Tensor):
        """Record activation statistics during calibration."""
        with self._lock:
            if self._calibrated:
                return
            if layer_name not in self._layer_stats:
                self._layer_stats[layer_name] = {
                    "mean_abs_sum": 0.0,
                    "var_sum": 0.0,
                    "kurtosis_sum": 0.0,
                    "count": 0,
                }
            stats = self._layer_stats[layer_name]
            with torch.no_grad():
                flat = x.float().flatten()
                stats["mean_abs_sum"] += flat.abs().mean().item()
                stats["var_sum"] += flat.var().item()
                mu = flat.mean()
                std = flat.std().clamp(min=1e-8)
                stats["kurtosis_sum"] += ((flat - mu) / std).pow(4).mean().item() - 3.0
                stats["count"] += 1

    def maybe_calibrate(self):
        """After enough passes, compute per-layer k values."""
        with self._lock:
            if self._calibrated:
                return
            self._pass_count += 1
            if self._pass_count < self._calibration_passes:
                return

            if not self._layer_stats:
                self._calibrated = True
                return

            var_values = {}
            for name, stats in self._layer_stats.items():
                n = max(stats["count"], 1)
                avg_var = stats["var_sum"] / n
                avg_kurtosis = stats["kurtosis_sum"] / n
                var_values[name] = avg_var

                # High variance -> larger k (finer quantization grid)
                # Low variance -> smaller k (more sparsity)
                # Leptokurtic (high kurtosis) -> heavy tails need more range
                if avg_var < 0.01:
                    layer_k = self._min_k
                elif avg_kurtosis > 5.0:
                    layer_k = min(self._base_k * 1.5, self._max_k)
                elif avg_var > 1.0:
                    layer_k = min(self._base_k * (1.0 + avg_var * 0.3), self._max_k)
                else:
                    layer_k = self._base_k

                self._layer_k[name] = round(layer_k, 2)

            self._calibrated = True
            avg_k = sum(self._layer_k.values()) / max(len(self._layer_k), 1)
            print(f"[AdaptiveK] Calibrated {len(self._layer_k)} layers | "
                  f"avg k={avg_k:.2f} | range=[{min(self._layer_k.values()):.2f}, "
                  f"{max(self._layer_k.values()):.2f}]")

    def get_k(self, layer_name: str) -> float:
        """Get the k value for a specific layer."""
        with self._lock:
            return self._layer_k.get(layer_name, self._base_k)

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return self._calibrated

    def stats(self) -> dict:
        with self._lock:
            if not self._calibrated:
                return {"calibrated": False, "passes": self._pass_count,
                        "target": self._calibration_passes}
            k_values = list(self._layer_k.values())
            return {
                "calibrated": True,
                "layers": len(k_values),
                "avg_k": round(sum(k_values) / max(len(k_values), 1), 2),
                "min_k": round(min(k_values), 2) if k_values else 0,
                "max_k": round(max(k_values), 2) if k_values else 0,
                "target_sparsity": self._target_sparsity,
            }


adaptive_k = AdaptiveKController()


def dynamic_spikes(x, k=3.0, max_spike=15):
    """Convert floating-point activations to integer spike counts.

    Algorithm (from SpikingBrain W8ASpike/quant_linear.py):
      1. Adaptive threshold: vth = mean(|x|) / k
      2. Quantize: spikes = round(x / vth)
      3. Clamp to [-max_spike, max_spike]
      4. Reconstruct: x_approx = spikes * vth

    Sparsity emerges naturally: values within +/-vth/2 of zero round to 0.
    """
    vth = x.abs().mean(dim=-1, keepdim=True).float() / k  # compute adaptive threshold per row
    vth = vth.clamp(min=1e-5, max=1e4)  # prevent division by zero or overflow
    spikes_int = (x.float() / vth).round()  # quantize activations to integer spike counts
    spikes_int = spikes_int.clamp(-max_spike, max_spike)  # clamp spikes within allowed range
    return spikes_int, vth  # return spike counts and threshold for reconstruction


def apply_spike_hooks(model, k=3.0, max_spike=15, skip_patterns=None,
                      measure_only=True):
    """Attach spike-analysis hooks to eligible linear layers.

    When *measure_only=True* (default), the hooks compute sparsity
    metrics but do NOT modify the activations -- the model runs at
    full fidelity while we report what sparsity spike encoding would
    achieve.

    When *measure_only=False*, activations are replaced with their
    spike-encoded approximations (requires a model trained for this).
    """
    skip_patterns = skip_patterns or [  # default layer name patterns to exclude
        "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    ]

    hooks = []  # storage for registered hook handles
    converted = 0  # counter for successfully hooked layers

    for name, module in model.named_modules():  # iterate all submodules recursively
        if any(p in name.lower() for p in skip_patterns):  # skip excluded layer patterns
            continue

        is_linear = isinstance(module, nn.Linear)  # check if standard linear layer
        try:
            import bitsandbytes as bnb  # optional quantized layer support
            is_linear = is_linear or isinstance(  # also match bitsandbytes quantized layers
                module, (bnb.nn.Linear4bit, bnb.nn.Linear8bitLt)
            )
        except ImportError:
            pass  # bitsandbytes not installed, skip quantized check

        if not is_linear:  # only hook linear layers
            continue

        def _make_hook(layer_name, k_val, max_s, passive):  # closure factory for per-layer hooks
            def _hook(mod, args):  # forward pre-hook receives module and input args
                x = args[0]  # extract the input activation tensor
                if not x.is_floating_point() or x.dim() < 2:  # skip non-float or 1D tensors
                    return None if passive else args

                if adaptive_k.is_calibrated:
                    effective_k = adaptive_k.get_k(layer_name)
                else:
                    effective_k = k_val
                    adaptive_k.record(layer_name, x)
                    adaptive_k.maybe_calibrate()

                spikes_int, vth = dynamic_spikes(x, k=effective_k, max_spike=max_s)

                if _track_stats:  # accumulate sparsity statistics if enabled
                    total = spikes_int.numel()
                    zeros = (spikes_int == 0).sum().item()
                    with _spike_lock:  # thread-safe stats update
                        st = _spike_stats[layer_name]
                        st["total"] += total
                        st["zeros"] += zeros
                        st["calls"] += 1

                if passive:  # measure-only mode
                    return None

                x_approx = (spikes_int * vth).to(x.dtype)
                return (x_approx,) + args[1:] if len(args) > 1 else (x_approx,)
            return _hook

        h = module.register_forward_pre_hook(  # attach hook to run before forward pass
            _make_hook(name, k, max_spike, measure_only)
        )
        hooks.append(h)  # store hook handle for later removal
        converted += 1  # increment converted layer counter

    return hooks, converted  # return handles and count of hooked layers


def get_sparsity_stats():
    """Average activation sparsity across all spike-encoded layers."""
    with _spike_lock:  # acquire lock for thread-safe read
        if len(_spike_stats) == 0:  # no stats collected yet
            return {"avg_sparsity": 0.0, "layers": 0, "total_calls": 0}

        total_elements = 0  # accumulator for all activation elements
        total_zeros = 0  # accumulator for zero-valued activations
        total_calls = 0  # accumulator for total hook invocations
        for stats in _spike_stats.values():  # iterate per-layer stats
            total_elements += stats["total"]  # sum element counts across layers
            total_zeros += stats["zeros"]  # sum zero counts across layers
            total_calls += stats["calls"]  # sum call counts across layers

        pct = (total_zeros / total_elements * 100) if total_elements > 0 else 0.0  # compute sparsity percentage
        return {
            "avg_sparsity": round(pct, 1),  # rounded average sparsity percentage
            "layers": len(_spike_stats),  # number of tracked layers
            "total_calls": total_calls,  # total hook invocations across layers
        }


def set_tracking(enabled: bool):  # toggle statistics collection on/off
    global _track_stats  # reference module-level tracking flag
    _track_stats = enabled  # update tracking state


def reset_sparsity_stats():  # clear all accumulated statistics
    with _spike_lock:  # acquire lock for thread-safe mutation
        _spike_stats.clear()  # remove all per-layer stats entries


def get_adaptive_k_stats() -> dict:
    return adaptive_k.stats()
