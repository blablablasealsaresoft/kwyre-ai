# ═══════════════════════════════════════════════════════════════════════════════
# model/convert_gguf.py — DOCSTRING REPLACEMENT (top of file)
# ═══════════════════════════════════════════════════════════════════════════════
"""
Kwyre AI — Convert HuggingFace models to GGUF format for llama.cpp
==================================================================
Converts transformer models to GGUF with quantization for use with
Kwyre Air (CPU-only inference via llama-cpp-python).

NOTE: For the draft model, pre-built GGUFs are available at:
      https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF

Supported quantization levels:
  Q4_K_M  — 4-bit, medium quality — recommended
  Q5_K_M  — 5-bit, higher quality
  Q8_0    — 8-bit, near-lossless

Usage:
    # Personal tier
    python model/convert_gguf.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./models/kwyre-4b.gguf

    # Higher quality quantization
    python model/convert_gguf.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./models/kwyre-4b-q5.gguf --quant Q5_K_M

    # From a local model directory
    python model/convert_gguf.py --model ./dist/kwyre-4b-nf4 --output ./models/kwyre-4b.gguf
"""


# ═══════════════════════════════════════════════════════════════════════════════
# model/quantize_awq.py — CONFIG PATCHES
# Replace DEFAULT_MODEL_ID and _TIER_NAMES lines.
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODEL_ID = os.environ.get("KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
_TIER_NAMES = {
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": "kwyre-4b",
    "Qwen/Qwen3.5-9B": "kwyre-9b",
}
