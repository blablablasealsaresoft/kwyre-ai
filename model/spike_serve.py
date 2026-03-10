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


def dynamic_spikes(x, k=3.0, max_spike=7):
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

                spikes_int, vth = dynamic_spikes(x, k=k_val, max_spike=max_s)  # encode activations to spikes

                if _track_stats:  # accumulate sparsity statistics if enabled
                    total = spikes_int.numel()  # total number of elements in spike tensor
                    zeros = (spikes_int == 0).sum().item()  # count zero-valued spikes
                    with _spike_lock:  # thread-safe stats update
                        st = _spike_stats[layer_name]  # get or create layer stats entry
                        st["total"] += total  # accumulate total element count
                        st["zeros"] += zeros  # accumulate zero spike count
                        st["calls"] += 1  # increment hook invocation counter

                if passive:  # measure-only mode
                    return None  # don't modify activations (measure-only mode)

                x_approx = (spikes_int * vth).to(x.dtype)  # reconstruct activations from spikes
                return (x_approx,) + args[1:] if len(args) > 1 else (x_approx,)  # replace input with spike-encoded version
            return _hook  # return the configured hook function

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
