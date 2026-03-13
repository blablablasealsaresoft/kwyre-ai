"""
Kwyre AI — Pre-quantize models to 4-bit NF4 for distribution.

Loads the FP16 model from HuggingFace cache, quantizes to NF4,
and saves the compact version. Clients download ~2.5 GB instead of ~8 GB.

Usage:
    # Personal tier (Qwen3.5-4B Uncensored)
    python model/quantize_nf4.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./dist/kwyre-4b-nf4

    # Draft model (Qwen3.5-0.8B)
    python model/quantize_nf4.py --model Qwen/Qwen3.5-0.8B --output ./dist/kwyre-draft-nf4

    # Professional tier (Qwen3.5-9B)
    python model/quantize_nf4.py --model Qwen/Qwen3.5-9B --output ./dist/kwyre-9b-nf4
"""
