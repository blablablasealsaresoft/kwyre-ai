"""
Offline AWQ quantization for Kwyre AI — Professional tier.

Quantizes the QAT-trained Qwen3.5-9B model to 4-bit AWQ format for
1.4x faster inference. Run ONCE after merge_and_export.py.

The Personal tier (Qwen3.5-4B) uses NF4 quantization via bitsandbytes
at load time and does not need offline AWQ pre-quantization.

Usage:
    python model/quantize_awq.py --model Qwen/Qwen3.5-9B --output models/kwyre-9b-awq
"""

import os  # filesystem and path operations
import argparse  # command-line argument parsing
from awq import AutoAWQForCausalLM  # AWQ quantization model loader
from transformers import AutoTokenizer  # HuggingFace tokenizer loader
from peft import PeftModel  # LoRA adapter loading utilities

_script_dir = os.path.dirname(os.path.abspath(__file__))  # absolute path to this script's directory
_project_root = os.path.dirname(_script_dir)  # parent directory as project root

DEFAULT_MODEL_ID = os.environ.get("KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
_TIER_NAMES = {
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": "kwyre-4b",
    "Qwen/Qwen3.5-9B": "kwyre-9b",
}
_TIER_NAME = _TIER_NAMES.get(DEFAULT_MODEL_ID, "kwyre-custom")  # resolve tier name for current model
DEFAULT_OUTPUT_PATH = os.path.join(_project_root, "models", f"{_TIER_NAME}-awq")  # default quantized output path
DEFAULT_ADAPTER_PATH = os.path.join(_project_root, "qat_output_v1", "final")  # default LoRA adapter location

AWQ_QUANT_CONFIG = {  # AWQ quantization hyperparameters
    "zero_point": True,  # enable zero-point calibration for accuracy
    "q_group_size": 128,  # group size for weight quantization blocks
    "w_bit": 4,  # quantize weights to 4-bit precision
    "version": "GEMM",  # use GEMM kernel for inference speed
}


def main():  # entry point for AWQ quantization pipeline
    parser = argparse.ArgumentParser(description="Quantize model to AWQ format")  # create CLI argument parser
    parser.add_argument(  # model source argument
        "--model", default=None,
        help="Model path or HF ID. Default: resolves from KWYRE_MODEL env or HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive",
    )
    parser.add_argument(  # output directory argument
        "--output", default=DEFAULT_OUTPUT_PATH,
        help=f"Output directory (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(  # LoRA adapter path argument
        "--adapter-path", default=DEFAULT_ADAPTER_PATH,
        help="Path to LoRA adapter to merge before quantizing (skipped if not found)",
    )
    parser.add_argument(  # flag to skip LoRA merge step
        "--no-merge-adapter", action="store_true",
        help="Skip LoRA adapter merging even if adapters exist",
    )
    args = parser.parse_args()  # parse command-line arguments

    model_path = args.model  # use explicitly provided model path
    if model_path is None:  # no model path given, resolve from HF cache
        cache_path = os.path.join(  # construct HuggingFace cache directory path
            os.path.expanduser("~"), ".cache", "huggingface", "hub",
            f"models--{DEFAULT_MODEL_ID.replace('/', '--')}", "snapshots",
        )
        if os.path.isdir(cache_path):  # check if cached model exists
            snap_dirs = [d for d in os.listdir(cache_path) if os.path.isdir(os.path.join(cache_path, d))]  # list snapshot directories
            model_path = os.path.join(cache_path, snap_dirs[0]) if snap_dirs else DEFAULT_MODEL_ID  # use first snapshot or fallback to HF ID
        else:
            model_path = DEFAULT_MODEL_ID  # fallback to HuggingFace model ID for download

    print(f"[AWQ] Resolved model path: {model_path}")  # display resolved model source

    if not os.path.isdir(model_path):  # warn if local path doesn't exist
        print(f"WARNING: Local model not found at {model_path}, will attempt HF download")

    print(f"Loading tokenizer from {model_path}...")  # status message for tokenizer load
    tokenizer = AutoTokenizer.from_pretrained(  # load tokenizer from model path
        model_path, trust_remote_code=True,
    )

    has_adapter = (  # check if LoRA adapter should be merged
        not args.no_merge_adapter
        and os.path.isdir(args.adapter_path)  # adapter directory exists
        and os.path.exists(os.path.join(args.adapter_path, "adapter_config.json"))  # adapter config present
    )

    if has_adapter:  # merge LoRA adapter into base model before quantizing
        print(f"Loading base model + LoRA adapter from {args.adapter_path}...")  # status for adapter merge
        base_model = AutoAWQForCausalLM.from_pretrained(  # load base model for AWQ
            model_path, trust_remote_code=True,
        )
        peft_model = PeftModel.from_pretrained(base_model.model, args.adapter_path)  # attach LoRA adapter weights
        base_model.model = peft_model.merge_and_unload()  # merge adapter into base and discard wrapper
        print("LoRA adapters merged into base model")  # confirm merge complete
        model = base_model  # use merged model for quantization
    else:  # no adapter to merge, load base model directly
        if not args.no_merge_adapter:  # only log when merge wasn't explicitly skipped
            print(f"No LoRA adapter found at {args.adapter_path} — quantizing base model")
        print(f"Loading model from {model_path}...")  # status for base model load
        model = AutoAWQForCausalLM.from_pretrained(  # load model directly for AWQ
            model_path, trust_remote_code=True,
        )

    print("Quantizing to AWQ (w_bit=4, group_size=128, GEMM kernel)...")  # status for quantization start
    print("This may take 10-30 minutes depending on GPU...")  # time estimate warning
    model.quantize(tokenizer, quant_config=AWQ_QUANT_CONFIG)  # run AWQ calibration and quantization

    os.makedirs(args.output, exist_ok=True)  # create output directory if missing
    print(f"Saving quantized model to {args.output}...")  # status for save operation
    model.save_quantized(args.output)  # save AWQ-quantized model weights
    tokenizer.save_pretrained(args.output)  # save tokenizer alongside quantized model

    print("Done. Start the server with: KWYRE_QUANT=awq python server/serve_local_4bit.py")  # display next-step instructions


if __name__ == "__main__":  # only run when executed directly
    main()  # invoke main quantization function
