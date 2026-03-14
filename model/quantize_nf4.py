"""
Kwyre AI — Pre-quantize models to 4-bit NF4 for distribution.

Loads the FP16 model from HuggingFace cache, quantizes to NF4,
and saves the compact version. Clients download ~2 GB instead of ~8 GB.

Usage:
    python model/quantize_nf4.py --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive --output ./dist/kwyre-4b-nf4
    python model/quantize_nf4.py --model Qwen/Qwen3.5-0.8B --output ./dist/kwyre-draft-nf4
"""

import argparse  # command-line argument parsing
import os  # filesystem and path operations
import torch  # core tensor computation library
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # HuggingFace model loading utilities


def quantize_and_save(model_id: str, output_dir: str):  # main quantization pipeline function
    print(f"\n{'='*60}")  # print header separator line
    print("  Kwyre AI — NF4 Quantization")  # display script title
    print(f"  Source:  {model_id}")  # show source model identifier
    print(f"  Output:  {output_dir}")  # show output directory path
    print(f"{'='*60}\n")  # print footer separator line

    quant_config = BitsAndBytesConfig(  # configure 4-bit quantization parameters
        load_in_4bit=True,  # enable 4-bit weight quantization
        bnb_4bit_compute_dtype=torch.bfloat16,  # use bfloat16 for compute operations
        bnb_4bit_quant_type="nf4",  # use NormalFloat4 quantization scheme
        bnb_4bit_use_double_quant=True,  # enable nested quantization for extra savings
    )

    print("Loading tokenizer...")  # status message for tokenizer load
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)  # load tokenizer from HuggingFace

    print(f"Loading {model_id} with NF4 quantization...")  # status message for model load
    model = AutoModelForCausalLM.from_pretrained(  # load and quantize model in one step
        model_id,
        trust_remote_code=True,  # allow custom model code from repo
        quantization_config=quant_config,  # apply NF4 quantization during loading
        device_map="auto",  # auto-distribute layers across available GPUs
        dtype=torch.bfloat16,  # set default tensor dtype to bfloat16
    )

    vram_gb = torch.cuda.memory_allocated() / 1e9  # compute current GPU memory usage in GB
    print(f"Model loaded — VRAM: {vram_gb:.1f} GB")  # display VRAM usage after loading

    os.makedirs(output_dir, exist_ok=True)  # create output directory if missing

    print(f"Saving quantized model to {output_dir}...")  # status message for save operation
    model.save_pretrained(output_dir)  # save quantized model weights and config
    tokenizer.save_pretrained(output_dir)  # save tokenizer files alongside model

    total_bytes = sum(  # calculate total size of saved files
        os.path.getsize(os.path.join(output_dir, f))  # get byte size of each file
        for f in os.listdir(output_dir)  # iterate files in output directory
        if os.path.isfile(os.path.join(output_dir, f))  # only count regular files
    )
    total_mb = total_bytes / (1024 * 1024)  # convert bytes to megabytes
    total_gb = total_bytes / (1024 ** 3)  # convert bytes to gigabytes

    print("\nDone. Quantized model saved:")  # completion status header
    print(f"  Size: {total_mb:.0f} MB ({total_gb:.2f} GB)")  # display model size in MB and GB
    print(f"  Path: {os.path.abspath(output_dir)}")  # display absolute output path

    del model  # free model from memory
    torch.cuda.empty_cache()  # release unused GPU memory back to CUDA
    return total_bytes  # return total saved size in bytes


if __name__ == "__main__":  # only run when executed directly
    parser = argparse.ArgumentParser(description="Quantize model to NF4 for distribution")  # create CLI parser
    parser.add_argument("--model", required=True, help="HuggingFace model ID")  # required model identifier argument
    parser.add_argument("--output", required=True, help="Output directory")  # required output path argument
    args = parser.parse_args()  # parse command-line arguments
    quantize_and_save(args.model, args.output)  # run quantization with parsed arguments
