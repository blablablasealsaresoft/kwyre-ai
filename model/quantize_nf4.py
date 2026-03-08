"""
Kwyre AI — Pre-quantize models to 4-bit NF4 for distribution.

Loads the FP16 model from HuggingFace cache, quantizes to NF4,
and saves the compact version. Clients download ~2 GB instead of ~8 GB.

Usage:
    python model/quantize_nf4.py --model Qwen/Qwen3-4B --output ./dist/kwyre-4b-nf4
    python model/quantize_nf4.py --model Qwen/Qwen3-0.6B --output ./dist/kwyre-draft-nf4
"""

import argparse
import os
import shutil
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def quantize_and_save(model_id: str, output_dir: str):
    print(f"\n{'='*60}")
    print(f"  Kwyre AI — NF4 Quantization")
    print(f"  Source:  {model_id}")
    print(f"  Output:  {output_dir}")
    print(f"{'='*60}\n")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    print(f"Loading {model_id} with NF4 quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=True,
        quantization_config=quant_config,
        device_map="auto",
        dtype=torch.bfloat16,
    )

    vram_gb = torch.cuda.memory_allocated() / 1e9
    print(f"Model loaded — VRAM: {vram_gb:.1f} GB")

    os.makedirs(output_dir, exist_ok=True)

    print(f"Saving quantized model to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    total_bytes = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    )
    total_mb = total_bytes / (1024 * 1024)
    total_gb = total_bytes / (1024 ** 3)

    print(f"\nDone. Quantized model saved:")
    print(f"  Size: {total_mb:.0f} MB ({total_gb:.2f} GB)")
    print(f"  Path: {os.path.abspath(output_dir)}")

    del model
    torch.cuda.empty_cache()
    return total_bytes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quantize model to NF4 for distribution")
    parser.add_argument("--model", required=True, help="HuggingFace model ID")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()
    quantize_and_save(args.model, args.output)
