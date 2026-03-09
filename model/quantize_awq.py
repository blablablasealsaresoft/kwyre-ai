"""
Offline AWQ quantization for Kwyre AI.

Quantizes the model to 4-bit AWQ format for faster inference.

Usage:
    Personal:     python model/quantize_awq.py --model Qwen/Qwen3-4B --output models/kwyre-4b-awq
    Professional: python model/quantize_awq.py --model Qwen/Qwen3.5-9B --output models/kwyre-9b-awq
"""

import os
import sys
import argparse
import torch
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer
from peft import PeftModel, AutoPeftModelForCausalLM

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)

DEFAULT_MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3-4B")
_TIER_NAMES = {"Qwen/Qwen3-4B": "kwyre-4b", "Qwen/Qwen3.5-9B": "kwyre-9b"}
_TIER_NAME = _TIER_NAMES.get(DEFAULT_MODEL_ID, "kwyre-custom")
DEFAULT_OUTPUT_PATH = os.path.join(_project_root, "models", f"{_TIER_NAME}-awq")
DEFAULT_ADAPTER_PATH = os.path.join(_project_root, "qat_output_v1", "final")

AWQ_QUANT_CONFIG = {
    "zero_point": True,
    "q_group_size": 128,
    "w_bit": 4,
    "version": "GEMM",
}


def main():
    parser = argparse.ArgumentParser(description="Quantize model to AWQ format")
    parser.add_argument(
        "--model", default=None,
        help="Model path or HF ID. Default: resolves from KWYRE_MODEL env or Qwen/Qwen3-4B",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT_PATH,
        help=f"Output directory (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--adapter-path", default=DEFAULT_ADAPTER_PATH,
        help="Path to LoRA adapter to merge before quantizing (skipped if not found)",
    )
    parser.add_argument(
        "--no-merge-adapter", action="store_true",
        help="Skip LoRA adapter merging even if adapters exist",
    )
    args = parser.parse_args()

    model_path = args.model
    if model_path is None:
        cache_path = os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface", "hub",
            f"models--{DEFAULT_MODEL_ID.replace('/', '--')}", "snapshots",
        )
        if os.path.isdir(cache_path):
            snap_dirs = [d for d in os.listdir(cache_path) if os.path.isdir(os.path.join(cache_path, d))]
            model_path = os.path.join(cache_path, snap_dirs[0]) if snap_dirs else DEFAULT_MODEL_ID
        else:
            model_path = DEFAULT_MODEL_ID

    print(f"[AWQ] Resolved model path: {model_path}")

    if not os.path.isdir(model_path):
        print(f"WARNING: Local model not found at {model_path}, will attempt HF download")

    print(f"Loading tokenizer from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, trust_remote_code=True,
    )

    has_adapter = (
        not args.no_merge_adapter
        and os.path.isdir(args.adapter_path)
        and os.path.exists(os.path.join(args.adapter_path, "adapter_config.json"))
    )

    if has_adapter:
        print(f"Loading base model + LoRA adapter from {args.adapter_path}...")
        base_model = AutoAWQForCausalLM.from_pretrained(
            model_path, trust_remote_code=True,
        )
        peft_model = PeftModel.from_pretrained(base_model.model, args.adapter_path)
        base_model.model = peft_model.merge_and_unload()
        print("LoRA adapters merged into base model")
        model = base_model
    else:
        if not args.no_merge_adapter:
            print(f"No LoRA adapter found at {args.adapter_path} — quantizing base model")
        print(f"Loading model from {model_path}...")
        model = AutoAWQForCausalLM.from_pretrained(
            model_path, trust_remote_code=True,
        )

    print(f"Quantizing to AWQ (w_bit=4, group_size=128, GEMM kernel)...")
    print("This may take 10-30 minutes depending on GPU...")
    model.quantize(tokenizer, quant_config=AWQ_QUANT_CONFIG)

    os.makedirs(args.output, exist_ok=True)
    print(f"Saving quantized model to {args.output}...")
    model.save_quantized(args.output)
    tokenizer.save_pretrained(args.output)

    print(f"Done. Start the server with: KWYRE_QUANT=awq python server/serve_local_4bit.py")


if __name__ == "__main__":
    main()
