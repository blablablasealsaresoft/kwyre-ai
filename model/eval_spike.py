"""
Evaluate QAT-trained spike models across k values.

Measures perplexity, activation sparsity, and generation quality at each
spike threshold to find the best sparsity-quality tradeoff after training.

Usage:
    python eval_spike.py --adapter_path ./qat_output --k_values 50,25,12,8,5,3
    python eval_spike.py --no_baseline --k_values 8,5,3 --eval_samples 50
"""

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from datasets import load_dataset

from spike_serve import (
    apply_spike_hooks,
    get_sparsity_stats,
    reset_sparsity_stats,
    set_tracking,
)

SPIKE_SKIP = [
    "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    "q_proj", "k_proj", "v_proj", "o_proj",
]

TEST_PROMPTS = [
    "Explain quantum entanglement in simple terms.",
    "Write a Python function to find the longest palindromic substring.",
    "What are the key differences between TCP and UDP?",
    "Translate 'The weather is beautiful today' into Japanese, French, and Spanish.",
    "Solve step by step: If a train travels 120km in 1.5 hours, what is its average speed?",
    "Write a haiku about artificial intelligence.",
    "What causes the northern lights (aurora borealis)?",
    "Create a simple REST API endpoint in FastAPI that returns user data.",
    "Explain the difference between stack and heap memory.",
    "What is the capital of Kazakhstan and what is it known for?",
]


def parse_args():
    p = argparse.ArgumentParser(description="Evaluate spike-encoded model quality across k values")
    p.add_argument("--model_id", default="Qwen/Qwen3.5-9B")
    p.add_argument("--adapter_path", default=None, help="Path to LoRA adapter directory from QAT training")
    p.add_argument("--k_values", default="50,25,12,8,5,3", help="Comma-separated k values to test")
    p.add_argument("--max_spike", type=int, default=31)
    p.add_argument("--max_seq_len", type=int, default=2048)
    p.add_argument("--eval_samples", type=int, default=200)
    p.add_argument("--dataset", default="teknium/OpenHermes-2.5")
    p.add_argument("--output_file", default="eval_results.json")
    p.add_argument("--no_baseline", action="store_true", help="Skip baseline evaluation without spikes")
    return p.parse_args()


def load_model(model_id, adapter_path=None):
    print(f"Loading tokenizer for {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, padding_side="left", truncation_side="left", trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading {model_id} with 4-bit quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=True,
        quantization_config=quant_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    if adapter_path:
        print(f"Loading LoRA adapter from {adapter_path}...")
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter_path)
        model = model.merge_and_unload()
        print("Adapter merged.")

    model.eval()
    gpu_mem = torch.cuda.memory_allocated() / 1e9
    print(f"Model loaded. GPU VRAM: {gpu_mem:.1f} GB")
    return model, tokenizer


def load_eval_data(dataset_name, n_samples, tokenizer, max_seq_len):
    """Load the last n_samples from the dataset (held-out from training)."""
    print(f"Loading eval data from {dataset_name} (last {n_samples} samples)...")
    ds = load_dataset(dataset_name, split="train")
    start_idx = max(len(ds) - n_samples, 0)
    eval_slice = ds.select(range(start_idx, len(ds)))

    role_map = {"human": "user", "gpt": "assistant", "system": "system"}

    encoded = []
    for row in eval_slice:
        conversations = row.get("conversations", [])
        if not conversations:
            continue
        messages = [
            {"role": role_map.get(turn.get("from", ""), turn.get("role", "user")),
             "content": turn.get("value", turn.get("content", ""))}
            for turn in conversations
        ]
        try:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False,
                enable_thinking=False,
            )
        except Exception:
            text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        ids = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_seq_len).input_ids
        if ids.shape[1] > 1:
            encoded.append(ids)

    print(f"Encoded {len(encoded)} eval samples (max_seq_len={max_seq_len})")
    return encoded


def evaluate_perplexity(model, encoded_samples, max_seq_len, label=""):
    """Compute perplexity over encoded samples with sliding window for long sequences."""
    total_loss = 0.0
    total_tokens = 0
    skipped = 0

    for i, input_ids in enumerate(encoded_samples):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"  {label} sample {i + 1}/{len(encoded_samples)}...")

        input_ids = input_ids.to(model.device)
        seq_len = input_ids.shape[1]

        try:
            if seq_len <= max_seq_len:
                with torch.no_grad():
                    outputs = model(input_ids, labels=input_ids)
                total_loss += outputs.loss.item() * (seq_len - 1)
                total_tokens += seq_len - 1
            else:
                for start in range(0, seq_len - 1, max_seq_len // 2):
                    end = min(start + max_seq_len, seq_len)
                    chunk = input_ids[:, start:end]
                    with torch.no_grad():
                        outputs = model(chunk, labels=chunk)
                    chunk_tokens = chunk.shape[1] - 1
                    total_loss += outputs.loss.item() * chunk_tokens
                    total_tokens += chunk_tokens
                    if end == seq_len:
                        break
        except torch.cuda.OutOfMemoryError:
            skipped += 1
            torch.cuda.empty_cache()
            continue

    if skipped:
        print(f"  Skipped {skipped} samples due to OOM")

    avg_loss = total_loss / total_tokens if total_tokens > 0 else float("inf")
    return math.exp(avg_loss)


def evaluate_generation(model, tokenizer, k_value, max_spike):
    """Generate responses for test prompts and return them."""
    responses = []
    for prompt in TEST_PROMPTS:
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = tokenizer([text], return_tensors="pt").to(model.device)

        try:
            with torch.no_grad():
                gen_ids = model.generate(
                    inputs.input_ids,
                    attention_mask=inputs.attention_mask,
                    max_new_tokens=512,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=True,
                    use_cache=True,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
            new_ids = gen_ids[0][inputs.input_ids.shape[1]:]
            reply = tokenizer.decode(new_ids, skip_special_tokens=True)
            reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
            reply = re.sub(r"<think>.*", "", reply, flags=re.DOTALL)
            reply = reply.strip()
        except torch.cuda.OutOfMemoryError:
            reply = "[OOM - skipped]"
            torch.cuda.empty_cache()

        responses.append({"prompt": prompt, "response": reply})
    return responses


def run_eval_for_k(model, tokenizer, encoded_samples, k_value, max_spike, max_seq_len):
    """Run full evaluation (perplexity + generation + sparsity) for a single k value."""
    k_label = f"k={k_value}"
    print(f"\n{'='*60}")
    print(f"Evaluating {k_label} (max_spike={max_spike})")
    print(f"{'='*60}")

    hooks, n_layers = apply_spike_hooks(
        model, k=k_value, max_spike=max_spike,
        skip_patterns=SPIKE_SKIP, measure_only=False,
    )
    print(f"Applied spike hooks to {n_layers} layers")

    reset_sparsity_stats()
    set_tracking(True)

    print("Computing perplexity...")
    t0 = time.time()
    ppl = evaluate_perplexity(model, encoded_samples, max_seq_len, label=k_label)
    ppl_time = time.time() - t0

    sparsity = get_sparsity_stats()

    print("Generating test responses...")
    generations = evaluate_generation(model, tokenizer, k_value, max_spike)

    set_tracking(False)
    for h in hooks:
        h.remove()

    print(f"  PPL: {ppl:.2f} | Sparsity: {sparsity['avg_sparsity']:.1f}% | Time: {ppl_time:.1f}s")

    return {
        "k": k_value,
        "perplexity": round(ppl, 4),
        "sparsity_pct": sparsity["avg_sparsity"],
        "sparsity_layers": sparsity["layers"],
        "ppl_eval_time_s": round(ppl_time, 1),
        "generations": generations,
    }


def run_baseline(model, tokenizer, encoded_samples, max_seq_len):
    """Run evaluation with no spike hooks (baseline)."""
    print(f"\n{'='*60}")
    print("Evaluating baseline (no spikes)")
    print(f"{'='*60}")

    print("Computing perplexity...")
    t0 = time.time()
    ppl = evaluate_perplexity(model, encoded_samples, max_seq_len, label="baseline")
    ppl_time = time.time() - t0

    print("Generating test responses...")
    generations = evaluate_generation(model, tokenizer, None, None)

    print(f"  PPL: {ppl:.2f} | Time: {ppl_time:.1f}s")

    return {
        "k": None,
        "perplexity": round(ppl, 4),
        "sparsity_pct": 0.0,
        "sparsity_layers": 0,
        "ppl_eval_time_s": round(ppl_time, 1),
        "generations": generations,
    }


def print_results(results, baseline):
    baseline_ppl = baseline["perplexity"] if baseline else None

    print(f"\n\n{'='*60}")
    print("=== QAT Spike Evaluation Results ===")
    print(f"{'='*60}\n")

    print("Perplexity:")
    if baseline:
        print(f"  k=None (baseline)  | PPL: {baseline_ppl:<7.2f} | Sparsity: 0.0%")

    for r in results:
        delta_str = ""
        if baseline_ppl is not None:
            delta = r["perplexity"] - baseline_ppl
            delta_str = f" | Delta: {delta:+.2f}"
        print(f"  k={r['k']:<17} | PPL: {r['perplexity']:<7.2f} | Sparsity: {r['sparsity_pct']:.1f}%{delta_str}")

    mid_idx = len(results) // 2
    show_k = results[mid_idx] if results else baseline
    if show_k and show_k.get("generations"):
        k_label = f"k={show_k['k']}" if show_k["k"] is not None else "baseline"
        print(f"\nSample Generations ({k_label}):")
        for gen in show_k["generations"][:3]:
            print(f"\n  [Prompt] {gen['prompt']}")
            preview = gen["response"][:300]
            if len(gen["response"]) > 300:
                preview += "..."
            print(f"  [Response] {preview}")

    print()


def main():
    args = parse_args()
    k_values = [float(k.strip()) for k in args.k_values.split(",")]

    print(f"Spike Evaluation Config:")
    print(f"  Model:       {args.model_id}")
    print(f"  Adapter:     {args.adapter_path or '(none)'}")
    print(f"  K values:    {k_values}")
    print(f"  Max spike:   {args.max_spike}")
    print(f"  Eval samples:{args.eval_samples}")
    print(f"  Dataset:     {args.dataset}")
    print(f"  Output:      {args.output_file}")
    print()

    model, tokenizer = load_model(args.model_id, args.adapter_path)
    encoded_samples = load_eval_data(args.dataset, args.eval_samples, tokenizer, args.max_seq_len)

    baseline = None
    if not args.no_baseline:
        baseline = run_baseline(model, tokenizer, encoded_samples, args.max_seq_len)

    results = []
    for k in sorted(k_values, reverse=True):
        result = run_eval_for_k(
            model, tokenizer, encoded_samples, k, args.max_spike, args.max_seq_len,
        )
        results.append(result)

    print_results(results, baseline)

    output = {
        "config": {
            "model_id": args.model_id,
            "adapter_path": args.adapter_path,
            "k_values": k_values,
            "max_spike": args.max_spike,
            "max_seq_len": args.max_seq_len,
            "eval_samples": args.eval_samples,
            "dataset": args.dataset,
        },
        "baseline": baseline,
        "results": results,
    }

    output_path = Path(args.output_file)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"Full results saved to {output_path}")


if __name__ == "__main__":
    main()
