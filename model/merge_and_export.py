"""
Merge QAT-trained LoRA adapters into the base model and prepare for deployment.

Supports both tiers:
  Personal:     python model/merge_and_export.py --model_id Qwen/Qwen3-4B --adapter_path ./qat_output_4b/final --output_dir ./merged-4b
  Professional: python model/merge_and_export.py --model_id Qwen/Qwen3.5-9B --adapter_path ./qat_output_9b/final --output_dir ./merged-9b
"""

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

from spike_serve import apply_spike_hooks, get_sparsity_stats, reset_sparsity_stats, set_tracking

SPIKE_SKIP = [
    "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    "q_proj", "k_proj", "v_proj", "o_proj",
]

TEST_PROMPTS = [
    "What is 15 * 23?",
    "Explain how photosynthesis works in two sentences.",
    "Write a short Python function to reverse a string.",
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Merge QAT-trained LoRA adapters and export for deployment"
    )
    p.add_argument("--model_id", default="Qwen/Qwen3-4B",
                    help="Model ID. Options: Qwen/Qwen3-4B (personal), Qwen/Qwen3.5-9B (professional)")
    p.add_argument("--adapter_path", required=True,
                    help="Path to LoRA adapter checkpoint from QAT training")
    p.add_argument("--output_dir", required=True,
                    help="Directory to save the merged model or adapter")
    p.add_argument("--merge_method", default="full", choices=["full", "adapter_only"],
                    help="'full' merges LoRA into base weights; "
                         "'adapter_only' copies adapter for PeftModel loading at serve time")
    p.add_argument("--push_to_hub", default=None,
                    help="HuggingFace repo id to push to (e.g. kwyre/Qwen3.5-9B-SpikeQAT)")
    p.add_argument("--test_generation", action="store_true",
                    help="Run a quick generation test after merge to verify quality")
    p.add_argument("--test_spike_k", type=float, default=8.0,
                    help="k value for spike encoding during test generation")
    p.add_argument("--max_spike", type=int, default=31)
    return p.parse_args()


def check_vram(required_gb: float = 10.0):
    if not torch.cuda.is_available():
        print("WARNING: No CUDA GPU detected. Full-precision merge requires GPU.")
        print("         Proceeding on CPU -- this will be slow and memory-hungry.")
        return
    total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    free_gb = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)) / 1e9
    print(f"GPU: {torch.cuda.get_device_name(0)}  |  {free_gb:.1f} GB free / {total_gb:.1f} GB total")
    if free_gb < required_gb:
        print(f"WARNING: Full-precision merge needs ~{required_gb:.0f} GB VRAM.")
        print(f"         Only {free_gb:.1f} GB available. You may hit OOM.")
        print("         Consider closing other GPU processes or using --merge_method adapter_only.")


def validate_adapter(adapter_path: str) -> dict:
    config_path = os.path.join(adapter_path, "adapter_config.json")
    if not os.path.isfile(config_path):
        print(f"ERROR: No adapter_config.json found at {adapter_path}")
        sys.exit(1)

    weights_bin = os.path.join(adapter_path, "adapter_model.bin")
    weights_safetensors = os.path.join(adapter_path, "adapter_model.safetensors")
    if not os.path.isfile(weights_bin) and not os.path.isfile(weights_safetensors):
        print(f"ERROR: No adapter weights found at {adapter_path}")
        print("       Expected adapter_model.bin or adapter_model.safetensors")
        sys.exit(1)

    with open(config_path) as f:
        adapter_config = json.load(f)

    print(f"Adapter validated: rank={adapter_config.get('r', '?')}, "
          f"alpha={adapter_config.get('lora_alpha', '?')}, "
          f"targets={adapter_config.get('target_modules', '?')}")
    return adapter_config


def load_adapter_config_defaults(adapter_config: dict) -> dict:
    return {
        "lora_rank": adapter_config.get("r", 64),
        "lora_alpha": adapter_config.get("lora_alpha", 128),
        "target_modules": adapter_config.get("target_modules", ["gate_proj", "up_proj", "down_proj"]),
    }


def merge_full(model_id: str, adapter_path: str, output_dir: str):
    print("\n" + "=" * 60)
    print("FULL MERGE: LoRA -> base model weights")
    print("=" * 60)

    check_vram()

    print(f"\n[1/4] Loading base model {model_id} in full precision...")
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    print(f"      Base model loaded in {time.time() - t0:.1f}s")

    print(f"[2/4] Loading LoRA adapter from {adapter_path}...")
    t0 = time.time()
    model = PeftModel.from_pretrained(model, adapter_path)
    print(f"      Adapter loaded in {time.time() - t0:.1f}s")

    print("[3/4] Merging LoRA weights into base model...")
    t0 = time.time()
    model = model.merge_and_unload()
    print(f"      Merge complete in {time.time() - t0:.1f}s")

    print(f"[4/4] Saving merged model to {output_dir}...")
    os.makedirs(output_dir, exist_ok=True)
    t0 = time.time()
    model.save_pretrained(output_dir, safe_serialization=True)
    print(f"      Model saved in {time.time() - t0:.1f}s")

    print("      Saving tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.save_pretrained(output_dir)

    del model
    torch.cuda.empty_cache()

    return output_dir


def merge_adapter_only(model_id: str, adapter_path: str, output_dir: str, adapter_config: dict):
    print("\n" + "=" * 60)
    print("ADAPTER-ONLY EXPORT: copying adapter for PeftModel loading")
    print("=" * 60)

    os.makedirs(output_dir, exist_ok=True)

    adapter_files = [
        f for f in os.listdir(adapter_path)
        if f.startswith("adapter_") or f == "README.md"
    ]

    print(f"Copying {len(adapter_files)} adapter file(s) to {output_dir}...")
    for fname in adapter_files:
        src = os.path.join(adapter_path, fname)
        dst = os.path.join(output_dir, fname)
        shutil.copy2(src, dst)
        print(f"  -> {fname}")

    meta = {
        "base_model": model_id,
        "adapter_source": os.path.abspath(adapter_path),
        "adapter_config": adapter_config,
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "usage": "Load with PeftModel.from_pretrained(base_model, adapter_path)",
    }
    meta_path = os.path.join(output_dir, "adapter_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  -> adapter_meta.json")

    return output_dir


def run_test_generation(model_path: str, model_id: str, merge_method: str,
                        adapter_path: str, spike_k: float, max_spike: int):
    print("\n" + "=" * 60)
    print("VERIFICATION: test generation with spike encoding")
    print("=" * 60)

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    load_path = model_path if merge_method == "full" else model_id

    print(f"\nLoading model from {load_path} (4-bit quantized)...")
    model = AutoModelForCausalLM.from_pretrained(
        load_path,
        trust_remote_code=True,
        quantization_config=quant_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    if merge_method == "adapter_only":
        print(f"Loading adapter from {adapter_path}...")
        model = PeftModel.from_pretrained(model, adapter_path)

    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(
        load_path if merge_method == "full" else model_id,
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"Applying spike hooks (k={spike_k}, max_spike={max_spike}, measure_only=False)...")
    spike_hooks, n_converted = apply_spike_hooks(
        model, k=spike_k, max_spike=max_spike,
        skip_patterns=SPIKE_SKIP, measure_only=False,
    )
    print(f"  {n_converted} layers with spike encoding active\n")

    reset_sparsity_stats()
    set_tracking(True)

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        inputs = tokenizer([text], return_tensors="pt").to(model.device)

        t0 = time.time()
        with torch.no_grad():
            gen_ids = model.generate(
                inputs.input_ids,
                attention_mask=inputs.attention_mask,
                max_new_tokens=256,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.time() - t0
        new_ids = gen_ids[0][inputs.input_ids.shape[1]:]
        reply = tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        print(f"--- Test {i}/{len(TEST_PROMPTS)} ({elapsed:.1f}s, {len(new_ids)/(elapsed or 1):.1f} tok/s) ---")
        print(f"Prompt:   {prompt}")
        print(f"Response: {reply}\n")

    stats = get_sparsity_stats()
    set_tracking(False)

    print("=" * 40)
    print(f"Sparsity: {stats['avg_sparsity']}% across {stats['layers']} layers "
          f"({stats['total_calls']} hook calls)")
    print("=" * 40)

    for h in spike_hooks:
        h.remove()
    del model
    torch.cuda.empty_cache()


def save_metadata(output_dir: str, args, adapter_config: dict):
    lora_info = load_adapter_config_defaults(adapter_config)
    metadata = {
        "base_model": args.model_id,
        "adapter_path": os.path.abspath(args.adapter_path),
        "merge_method": args.merge_method,
        "qat_config": {
            "spike_k_final": args.test_spike_k,
            "max_spike": args.max_spike,
            "lora_rank": lora_info["lora_rank"],
            "lora_alpha": lora_info["lora_alpha"],
            "target_modules": lora_info["target_modules"],
            "skip_patterns": SPIKE_SKIP,
        },
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "recommended_spike_k": args.test_spike_k,
    }

    path = os.path.join(output_dir, "spike_qat_metadata.json")
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"\nMetadata saved to {path}")
    return metadata


def print_deployment_instructions(args):
    print("\n" + "=" * 60)
    print("DEPLOYMENT INSTRUCTIONS")
    print("=" * 60)

    if args.merge_method == "full":
        merged_path = os.path.abspath(args.output_dir)
        print(f"""
In serve_local_4bit.py, make these changes:

1. Change MODEL_ID to the merged model:

   MODEL_ID = "{merged_path}"

2. Enable spike encoding (change measure_only to False):

   spike_hooks, n_converted = apply_spike_hooks(
       model, k=SPIKE_K, max_spike=SPIKE_MAX,
       skip_patterns=SPIKE_SKIP, measure_only=False,  # <-- changed
   )

3. Keep spike hooks active during inference (remove the hook removal block):

   # DELETE these lines:
   # for h in spike_hooks:
   #     h.remove()
   # spike_hooks = []
""")
    else:
        adapter_dir = os.path.abspath(args.output_dir)
        print(f"""
In serve_local_4bit.py, make these changes:

1. Add PeftModel import:

   from peft import PeftModel

2. After model loading, add adapter loading:

   model = PeftModel.from_pretrained(model, "{adapter_dir}")
   model.eval()

3. Enable spike encoding (change measure_only to False):

   spike_hooks, n_converted = apply_spike_hooks(
       model, k=SPIKE_K, max_spike=SPIKE_MAX,
       skip_patterns=SPIKE_SKIP, measure_only=False,  # <-- changed
   )

4. Keep spike hooks active during inference (remove the hook removal block):

   # DELETE these lines:
   # for h in spike_hooks:
   #     h.remove()
   # spike_hooks = []
""")

    if args.push_to_hub:
        print(f"Model was pushed to: https://huggingface.co/{args.push_to_hub}")
        print(f"You can also use MODEL_ID = \"{args.push_to_hub}\" in serve_local_4bit.py")


def push_to_hub(output_dir: str, repo_id: str, model_id: str, merge_method: str):
    print(f"\nPushing to HuggingFace Hub: {repo_id}...")

    if merge_method == "full":
        print("  Loading merged model for upload...")
        model = AutoModelForCausalLM.from_pretrained(
            output_dir, trust_remote_code=True, torch_dtype=torch.bfloat16,
            device_map="cpu",
        )
        model.push_to_hub(repo_id, safe_serialization=True)
        del model

        tokenizer = AutoTokenizer.from_pretrained(output_dir, trust_remote_code=True)
        tokenizer.push_to_hub(repo_id)
    else:
        from huggingface_hub import HfApi
        api = HfApi()
        api.upload_folder(
            folder_path=output_dir,
            repo_id=repo_id,
            repo_type="model",
            commit_message="Upload QAT LoRA adapter (spike-encoded)",
        )

    print(f"  Pushed to https://huggingface.co/{repo_id}")


def main():
    args = parse_args()

    print("=" * 60)
    print("SpikeQAT Merge & Export")
    print("=" * 60)
    print(f"  Base model:    {args.model_id}")
    print(f"  Adapter:       {args.adapter_path}")
    print(f"  Output:        {args.output_dir}")
    print(f"  Merge method:  {args.merge_method}")
    print(f"  Push to Hub:   {args.push_to_hub or 'no'}")
    print(f"  Test gen:      {args.test_generation}")
    print()

    adapter_config = validate_adapter(args.adapter_path)

    if args.merge_method == "full":
        merge_full(args.model_id, args.adapter_path, args.output_dir)
    else:
        merge_adapter_only(args.model_id, args.adapter_path, args.output_dir, adapter_config)

    save_metadata(args.output_dir, args, adapter_config)

    if args.test_generation:
        try:
            run_test_generation(
                args.output_dir, args.model_id, args.merge_method,
                args.adapter_path, args.test_spike_k, args.max_spike,
            )
        except torch.cuda.OutOfMemoryError:
            print("\nERROR: GPU OOM during test generation.")
            print("The merge itself succeeded -- the model is saved at:", args.output_dir)
            print("Try running test generation separately with more VRAM available.")
        except Exception as e:
            print(f"\nERROR during test generation: {e}")
            print("The merge itself succeeded -- the model is saved at:", args.output_dir)

    if args.push_to_hub:
        try:
            push_to_hub(args.output_dir, args.push_to_hub, args.model_id, args.merge_method)
        except Exception as e:
            print(f"\nERROR pushing to Hub: {e}")
            print("The local export succeeded. Push manually with:")
            print(f"  huggingface-cli upload {args.push_to_hub} {args.output_dir}")

    print_deployment_instructions(args)

    print("\nDone.")


if __name__ == "__main__":
    main()
