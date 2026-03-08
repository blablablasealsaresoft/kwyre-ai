"""
Kwyre AI — Convert HuggingFace models to MLX format.

Converts Qwen/Llama-family models from HuggingFace safetensors format
to MLX-optimized format with optional quantization (4-bit, 8-bit).

Supports both safetensors and GGUF source models.

Usage:
    # Convert from HuggingFace cache (default 4-bit quantization)
    python model/convert_mlx.py --model Qwen/Qwen3.5-9B --output ./models/kwyre-9b-mlx

    # Convert with 8-bit quantization
    python model/convert_mlx.py --model Qwen/Qwen3.5-9B --output ./models/kwyre-9b-mlx-8bit --quantize 8

    # Convert without quantization (full precision)
    python model/convert_mlx.py --model Qwen/Qwen3.5-9B --output ./models/kwyre-9b-mlx-fp16 --quantize 0

    # Convert from a local directory
    python model/convert_mlx.py --model-path /path/to/model --output ./models/kwyre-9b-mlx

    # Convert from a GGUF file
    python model/convert_mlx.py --gguf /path/to/model.gguf --output ./models/kwyre-9b-mlx
"""

import argparse
import os
import sys
import shutil
import json
from pathlib import Path

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)


def _resolve_hf_cache_path(model_id: str) -> str:
    """Resolve a HuggingFace model ID to a local cache path."""
    cache_base = os.path.join(
        os.path.expanduser("~"),
        ".cache", "huggingface", "hub",
        f"models--{model_id.replace('/', '--')}",
        "snapshots",
    )
    if not os.path.isdir(cache_base):
        return ""
    snap_dirs = [d for d in os.listdir(cache_base)
                 if os.path.isdir(os.path.join(cache_base, d))]
    if not snap_dirs:
        return ""
    return os.path.join(cache_base, snap_dirs[0])


def convert_from_safetensors(model_path: str, output_dir: str, quantize_bits: int = 4):
    """Convert a HuggingFace safetensors model to MLX format."""
    try:
        from mlx_lm import convert
    except ImportError:
        print("[MLX] ERROR: mlx-lm package not installed.")
        print("[MLX] Install with: pip install mlx-lm")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Kwyre AI — MLX Model Conversion")
    print(f"  Source:     {model_path}")
    print(f"  Output:     {output_dir}")
    print(f"  Quantize:   {'none (full precision)' if quantize_bits == 0 else f'{quantize_bits}-bit'}")
    print(f"{'='*60}\n")

    q_arg = None
    if quantize_bits == 4:
        q_arg = True
    elif quantize_bits == 8:
        q_arg = True

    os.makedirs(output_dir, exist_ok=True)

    convert_kwargs = {
        "hf_path": model_path,
        "mlx_path": output_dir,
    }
    if quantize_bits > 0:
        convert_kwargs["quantize"] = True
        convert_kwargs["q_bits"] = quantize_bits

    convert(**convert_kwargs)

    total_bytes = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    )
    total_mb = total_bytes / (1024 * 1024)
    total_gb = total_bytes / (1024 ** 3)

    print(f"\nDone. MLX model saved:")
    print(f"  Size: {total_mb:.0f} MB ({total_gb:.2f} GB)")
    print(f"  Path: {os.path.abspath(output_dir)}")
    print(f"\nStart the server with:")
    print(f"  KWYRE_MODEL_PATH={os.path.abspath(output_dir)} python server/serve_mlx.py")

    return total_bytes


def convert_from_gguf(gguf_path: str, output_dir: str):
    """Convert a GGUF model to MLX format.

    Uses mlx_lm's built-in GGUF conversion if available,
    otherwise falls back to manual weight extraction.
    """
    if not os.path.isfile(gguf_path):
        print(f"ERROR: GGUF file not found at {gguf_path}")
        sys.exit(1)

    try:
        from mlx_lm.gguf_utils import convert_gguf
    except ImportError:
        print("[MLX] ERROR: mlx-lm GGUF utilities not available.")
        print("[MLX] Ensure mlx-lm >= 0.12.0 is installed: pip install mlx-lm>=0.12.0")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Kwyre AI — GGUF to MLX Conversion")
    print(f"  Source: {gguf_path}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    os.makedirs(output_dir, exist_ok=True)
    convert_gguf(gguf_path, mlx_path=output_dir)

    total_bytes = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    )
    total_mb = total_bytes / (1024 * 1024)

    print(f"\nDone. MLX model saved:")
    print(f"  Size: {total_mb:.0f} MB")
    print(f"  Path: {os.path.abspath(output_dir)}")
    print(f"\nStart the server with:")
    print(f"  KWYRE_MODEL_PATH={os.path.abspath(output_dir)} python server/serve_mlx.py")

    return total_bytes


def main():
    parser = argparse.ArgumentParser(
        description="Convert HuggingFace/GGUF models to MLX format for Apple Silicon",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--model", default=None,
        help="HuggingFace model ID (e.g. Qwen/Qwen3.5-9B). Resolves from HF cache.",
    )
    source_group.add_argument(
        "--model-path", default=None,
        help="Path to local model directory (safetensors format)",
    )
    source_group.add_argument(
        "--gguf", default=None,
        help="Path to GGUF model file",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory for MLX model",
    )
    parser.add_argument(
        "--quantize", type=int, default=4, choices=[0, 4, 8],
        help="Quantization bits: 0=none, 4=4-bit (default), 8=8-bit",
    )
    args = parser.parse_args()

    if args.gguf:
        convert_from_gguf(args.gguf, args.output)
    else:
        if args.model:
            model_path = _resolve_hf_cache_path(args.model)
            if not model_path:
                print(f"ERROR: Model {args.model} not found in HuggingFace cache.")
                print(f"Download it first: huggingface-cli download {args.model}")
                sys.exit(1)
        else:
            model_path = args.model_path
            if not os.path.isdir(model_path):
                print(f"ERROR: Model directory not found at {model_path}")
                sys.exit(1)

        convert_from_safetensors(model_path, args.output, quantize_bits=args.quantize)


if __name__ == "__main__":
    main()
