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

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED_QUANTS = ["Q4_K_M", "Q5_K_M", "Q8_0"]

_project_root = Path(__file__).resolve().parent.parent


def find_llama_cpp() -> Path | None:
    """Auto-detect llama.cpp installation."""
    candidates = [
        Path.home() / "llama.cpp",
        _project_root / "llama.cpp",
        Path("/opt/llama.cpp"),
    ]
    for p in candidates:
        convert_script = p / "convert_hf_to_gguf.py"
        if convert_script.exists():
            return p
    return None


def convert_hf_to_gguf(
    model_path: str,
    output_path: str,
    quant_level: str = "Q4_K_M",
    llama_cpp_path: str | None = None,
):
    """Convert a HuggingFace model to quantized GGUF format.

    Two-step process:
      1. Convert HF safetensors/bin → FP16 GGUF (via convert_hf_to_gguf.py)
      2. Quantize FP16 GGUF → target quantization (via llama-quantize)
    """
    if quant_level not in SUPPORTED_QUANTS:
        print(f"[GGUF] ERROR: Unsupported quantization '{quant_level}'.")
        print(f"[GGUF] Supported: {', '.join(SUPPORTED_QUANTS)}")
        sys.exit(1)

    # Resolve llama.cpp location
    if llama_cpp_path:
        llama_dir = Path(llama_cpp_path)
    else:
        llama_dir = find_llama_cpp()

    if llama_dir is None or not llama_dir.exists():
        print("[GGUF] ERROR: llama.cpp not found.")
        print("[GGUF] Clone it: git clone https://github.com/ggerganov/llama.cpp")
        print("[GGUF] Then: python model/convert_gguf.py --llama-cpp /path/to/llama.cpp ...")
        sys.exit(1)

    convert_script = llama_dir / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        print(f"[GGUF] ERROR: convert_hf_to_gguf.py not found in {llama_dir}")
        sys.exit(1)

    quantize_bin = llama_dir / "build" / "bin" / "llama-quantize"
    if sys.platform == "win32":
        quantize_bin = quantize_bin.with_suffix(".exe")
    if not quantize_bin.exists():
        alt = llama_dir / "llama-quantize"
        if sys.platform == "win32":
            alt = alt.with_suffix(".exe")
        if alt.exists():
            quantize_bin = alt
        else:
            print("[GGUF] ERROR: llama-quantize binary not found.")
            print("[GGUF] Build llama.cpp first:")
            print(f"[GGUF]   cd {llama_dir} && cmake -B build && cmake --build build --config Release")
            sys.exit(1)

    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"\n{'='*60}")
    print("  Kwyre AI — GGUF Conversion")
    print(f"  Source:       {model_path}")
    print(f"  Output:       {output_path}")
    print(f"  Quantization: {quant_level}")
    print(f"  llama.cpp:    {llama_dir}")
    print(f"{'='*60}\n")

    # Step 1: Convert HF → FP16 GGUF
    with tempfile.TemporaryDirectory(prefix="kwyre_gguf_") as tmpdir:
        fp16_path = os.path.join(tmpdir, "model-fp16.gguf")

        print("[GGUF] Step 1/2: Converting HuggingFace model to FP16 GGUF...")
        cmd_convert = [
            sys.executable, str(convert_script),
            model_path,
            "--outfile", fp16_path,
            "--outtype", "f16",
        ]
        print(f"[GGUF] Running: {' '.join(cmd_convert)}")
        result = subprocess.run(cmd_convert, capture_output=False)
        if result.returncode != 0:
            print(f"[GGUF] ERROR: FP16 conversion failed (exit code {result.returncode})")
            sys.exit(1)

        if not os.path.exists(fp16_path):
            print("[GGUF] ERROR: FP16 GGUF file was not created.")
            sys.exit(1)

        fp16_size = os.path.getsize(fp16_path) / (1024 ** 3)
        print(f"[GGUF] FP16 GGUF created: {fp16_size:.2f} GB")

        # Step 2: Quantize FP16 → target
        print(f"[GGUF] Step 2/2: Quantizing to {quant_level}...")
        cmd_quantize = [
            str(quantize_bin),
            fp16_path,
            output_path,
            quant_level,
        ]
        print(f"[GGUF] Running: {' '.join(cmd_quantize)}")
        result = subprocess.run(cmd_quantize, capture_output=False)
        if result.returncode != 0:
            print(f"[GGUF] ERROR: Quantization failed (exit code {result.returncode})")
            sys.exit(1)

    if not os.path.exists(output_path):
        print("[GGUF] ERROR: Output GGUF file was not created.")
        sys.exit(1)

    final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    final_size_gb = final_size_mb / 1024

    print(f"\n{'='*60}")
    print("  Conversion complete!")
    print(f"  Output: {output_path}")
    print(f"  Size:   {final_size_mb:.0f} MB ({final_size_gb:.2f} GB)")
    print(f"  Quant:  {quant_level}")
    print(f"{'='*60}")
    print("\n  Run with Kwyre Air:")
    print(f"    KWYRE_GGUF_PATH={output_path} python server/serve_cpu.py\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert HuggingFace models to GGUF for Kwyre Air (CPU inference)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python model/convert_gguf.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./models/kwyre-4b.gguf
  python model/convert_gguf.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./models/kwyre-4b-q5.gguf --quant Q5_K_M
  python model/convert_gguf.py --model ./local-model --output ./models/model.gguf --llama-cpp ~/llama.cpp
""",
    )
    parser.add_argument(
        "--model", required=True,
        help="HuggingFace model ID or local directory path",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output .gguf file path",
    )
    parser.add_argument(
        "--quant", default="Q4_K_M", choices=SUPPORTED_QUANTS,
        help="Quantization level (default: Q4_K_M)",
    )
    parser.add_argument(
        "--llama-cpp", default=None,
        help="Path to llama.cpp repo (auto-detected if not specified)",
    )

    args = parser.parse_args()
    convert_hf_to_gguf(args.model, args.output, args.quant, args.llama_cpp)
