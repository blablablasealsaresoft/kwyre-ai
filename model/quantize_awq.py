"""
Offline AWQ quantization for Kwyre AI.

Quantizes the base Qwen3.5-9B model (with merged LoRA adapters if present)
to 4-bit AWQ format and saves to models/kwyre-9b-awq/.

Run ONCE before starting the server with KWYRE_QUANT=awq:
    python model/quantize_awq.py
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

DEFAULT_MODEL_PATH = os.path.join(
    os.path.expanduser("~"),
    ".cache", "huggingface", "hub",
    "models--Qwen--Qwen3.5-9B", "snapshots",
    "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
)
DEFAULT_OUTPUT_PATH = os.path.join(_project_root, "models", "kwyre-9b-awq")
DEFAULT_ADAPTER_PATH = os.path.join(_project_root, "qat_output_v1", "final")

AWQ_QUANT_CONFIG = {
    "zero_point": True,
    "q_group_size": 128,
    "w_bit": 4,
    "version": "GEMM",
}


def main():
    parser = argparse.ArgumentParser(description="Quantize Qwen3.5-9B to AWQ format")
    parser.add_argument(
        "--model-path", default=DEFAULT_MODEL_PATH,
        help="Path to base model weights (default: HF cache)",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT_PATH,
        help="Output directory for AWQ model (default: models/kwyre-9b-awq/)",
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

    if not os.path.isdir(args.model_path):
        print(f"ERROR: Model not found at {args.model_path}")
        sys.exit(1)

    print(f"Loading tokenizer from {args.model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path, trust_remote_code=True,
    )

    has_adapter = (
        not args.no_merge_adapter
        and os.path.isdir(args.adapter_path)
        and os.path.exists(os.path.join(args.adapter_path, "adapter_config.json"))
    )

    if has_adapter:
        print(f"Loading base model + LoRA adapter from {args.adapter_path}...")
        base_model = AutoAWQForCausalLM.from_pretrained(
            args.model_path, trust_remote_code=True,
        )
        peft_model = PeftModel.from_pretrained(base_model.model, args.adapter_path)
        base_model.model = peft_model.merge_and_unload()
        print("LoRA adapters merged into base model")
        model = base_model
    else:
        if not args.no_merge_adapter:
            print(f"No LoRA adapter found at {args.adapter_path} — quantizing base model")
        print(f"Loading model from {args.model_path}...")
        model = AutoAWQForCausalLM.from_pretrained(
            args.model_path, trust_remote_code=True,
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
