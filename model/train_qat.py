#!/usr/bin/env python3
"""QAT fine-tuning: teach Qwen3.5-4B/9B to tolerate spike-encoded activations.

Supports both Personal (4B) and Professional (9B) tiers. The 4B model
benefits from QAT when running with SpikeServe on the main model
(not just the draft model), enabling higher sparsity inference.

Usage:
    python model/train_qat.py --model_id Qwen/Qwen3.5-9B --output_dir ./qat_output_9b

Training config (9B):
    LoRA rank: 128 (alpha 256), targets: gate_proj, up_proj, down_proj
    Spike hooks: 408 MLP layers, k-curriculum: 50.0 -> 3.0
    Dataset: teknium/OpenHermes-2.5

Loads model from local HF cache, trains with STE spike encoding hooks
and a k-curriculum that gradually increases quantization aggressiveness.
"""

import argparse
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainerCallback,
)
from trl import SFTConfig, SFTTrainer

from spike_qat import (
    KCurriculumScheduler,
    apply_spike_hooks_trainable,
    get_qat_sparsity_stats,
    reset_qat_stats,
    set_k,
    set_max_spike,
    set_qat_tracking,
)

SPIKE_SKIP = [
    "embed", "lm_head", "layernorm", "norm", "visual", "merger",
    "q_proj", "k_proj", "v_proj", "o_proj",
]

def _resolve_model_path(model_id: str) -> str:
    """Resolve model path from dist/, HuggingFace cache, or use the ID directly."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    name_map = {
        "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": "kwyre-4b",
        "Qwen/Qwen3.5-9B": "kwyre-9b",
    }
    short_name = name_map.get(model_id, "")
    if short_name:
        dist_path = os.path.join(project_root, "dist", f"{short_name}-nf4")
        if os.path.isdir(dist_path):
            return dist_path
    cache_path = os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub",
        f"models--{model_id.replace('/', '--')}", "snapshots",
    )
    if os.path.isdir(cache_path):
        snap_dirs = [d for d in os.listdir(cache_path) if os.path.isdir(os.path.join(cache_path, d))]
        if snap_dirs:
            return os.path.join(cache_path, snap_dirs[0])
    return model_id


def parse_args():
    p = argparse.ArgumentParser(description="QLoRA + Spike QAT Training")
    p.add_argument("--model_id", type=str, default="Qwen/Qwen3.5-9B",
                    help="Model ID or path. Supports both 4B (Personal) and 9B (Professional).")
    p.add_argument("--dataset", type=str, default="teknium/OpenHermes-2.5")
    p.add_argument("--max_samples", type=int, default=100_000)
    p.add_argument("--output_dir", type=str, default="./qat_output")
    p.add_argument("--num_epochs", type=int, default=5)
    p.add_argument("--batch_size", type=int, default=1)
    p.add_argument("--grad_accum", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max_seq_len", type=int, default=2048)
    p.add_argument("--lora_rank", type=int, default=128)
    p.add_argument("--lora_alpha", type=int, default=256)
    p.add_argument("--k_start", type=float, default=50.0)
    p.add_argument("--k_end", type=float, default=3.0)
    p.add_argument("--k_schedule", type=str, default="step", choices=["step", "linear"])
    p.add_argument("--max_spike", type=int, default=15)
    p.add_argument("--layer_stride", type=int, default=1,
                    help="Only hook every Nth eligible MLP layer (1=all, 4=every 4th)")
    p.add_argument("--warmup_steps", type=int, default=500)
    p.add_argument("--save_steps", type=int, default=1000)
    p.add_argument("--eval_steps", type=int, default=500)
    p.add_argument("--logging_steps", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gradient_checkpointing", action="store_true", default=True)
    p.add_argument("--resume_from", type=str, default=None)
    p.add_argument("--wandb_project", type=str, default=None)
    return p.parse_args()


def load_model_and_tokenizer(args):
    model_path = _resolve_model_path(args.model_id)
    print(f"[QAT] Model path: {model_path}")

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, padding_side="right", trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )

    print(f"Loading {args.model_id} with 4-bit NF4 quantization...")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        quantization_config=quant_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )

    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=args.gradient_checkpointing,
    )

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        target_modules=["gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable params: {trainable:,} / {total:,} ({100 * trainable / total:.2f}%)")

    return model, tokenizer


def load_and_prepare_dataset(args, tokenizer):
    print(f"Loading dataset {args.dataset} (max {args.max_samples:,} samples)...")
    ds = load_dataset(args.dataset, split="train")
    ds = ds.shuffle(seed=args.seed).select(range(min(args.max_samples, len(ds))))
    split = ds.train_test_split(test_size=0.05, seed=args.seed)
    train_ds, eval_ds = split["train"], split["test"]

    role_map = {"human": "user", "gpt": "assistant", "system": "system"}

    def format_example(example):
        messages = []
        for turn in example["conversations"]:
            role = role_map.get(turn["from"], turn["from"])
            messages.append({"role": role, "content": turn["value"]})
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=False,
            enable_thinking=False,
        )
        return {"text": text}

    train_ds = train_ds.map(format_example, remove_columns=train_ds.column_names)
    eval_ds = eval_ds.map(format_example, remove_columns=eval_ds.column_names)

    print(f"Train: {len(train_ds):,}  |  Eval: {len(eval_ds):,}")
    return train_ds, eval_ds


class SpikeKSchedulerCallback(TrainerCallback):
    def __init__(self, scheduler: KCurriculumScheduler):
        self.scheduler = scheduler

    def on_step_end(self, args, state, control, **kwargs):
        new_k = self.scheduler.get_k(state.global_step)
        set_k(new_k)

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        logs["spike/k"] = self.scheduler.get_k(state.global_step)

    def on_epoch_end(self, args, state, control, **kwargs):
        current_k = self.scheduler.get_k(state.global_step)
        set_qat_tracking(True)
        reset_qat_stats()
        # Stats will accumulate over the next eval pass if one runs,
        # otherwise the next epoch start disables tracking again.
        print(f"[Epoch {state.epoch:.0f}] k={current_k:.1f}")

    def on_epoch_begin(self, args, state, control, **kwargs):
        set_qat_tracking(False)


def build_k_schedule(args, total_steps):
    if args.k_schedule == "step":
        k_values = [50.0, 20.0, 10.0, 5.0, 3.0]
        n_phases = len(k_values)
        phase_len = max(total_steps // n_phases, 1)
        schedule = [(i * phase_len, kv) for i, kv in enumerate(k_values)]
        return KCurriculumScheduler(
            mode="step", k_schedule=schedule,
            total_steps=total_steps, start_k=args.k_start, end_k=args.k_end,
        )
    return KCurriculumScheduler(
        mode="linear", total_steps=total_steps,
        warmup_steps=args.warmup_steps, start_k=args.k_start, end_k=args.k_end,
    )


def main():
    args = parse_args()

    if args.wandb_project:
        os.environ["WANDB_PROJECT"] = args.wandb_project

    model, tokenizer = load_model_and_tokenizer(args)

    print(f"Attaching STE spike hooks (k={args.k_start}, max_spike={args.max_spike})...")
    hooks, n_hooked = apply_spike_hooks_trainable(
        model, k=args.k_start, max_spike=args.max_spike,
        skip_patterns=SPIKE_SKIP, layer_stride=args.layer_stride,
    )
    set_k(args.k_start)
    set_max_spike(args.max_spike)
    set_qat_tracking(False)
    print(f"Spike hooks attached to {n_hooked} layers (stats tracking OFF for speed)")

    train_ds, eval_ds = load_and_prepare_dataset(args, tokenizer)

    steps_per_epoch = math.ceil(len(train_ds) / (args.batch_size * args.grad_accum))
    total_steps = steps_per_epoch * args.num_epochs
    k_scheduler = build_k_schedule(args, total_steps)

    print("\n" + "=" * 60)
    print("QAT Training Configuration")
    print("=" * 60)
    print(f"  Model:           {args.model_id}")
    print(f"  Dataset:         {args.dataset} ({len(train_ds):,} train samples)")
    print(f"  Epochs:          {args.num_epochs}")
    print(f"  Batch (eff.):    {args.batch_size * args.grad_accum}")
    print(f"  Steps/epoch:     {steps_per_epoch:,}")
    print(f"  Total steps:     {total_steps:,}")
    print(f"  LR:              {args.lr}")
    print(f"  LoRA:            r={args.lora_rank} alpha={args.lora_alpha} (MLP only)")
    print(f"  K schedule:      {args.k_schedule} {args.k_start} -> {args.k_end}")
    print(f"  Max spike:       {args.max_spike}")
    print(f"  Spike layers:    {n_hooked}")
    print(f"  Seq length:      {args.max_seq_len}")
    gpu_mem = torch.cuda.memory_allocated() / 1e9
    gpu_total = torch.cuda.get_device_properties(0).total_memory / 1e9
    est_hours = total_steps * 1.5 / 3600
    print(f"  VRAM:            {gpu_mem:.1f} / {gpu_total:.1f} GB")
    print(f"  Est. time:       ~{est_hours:.1f} hours (rough)")
    print("=" * 60 + "\n")

    training_config = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=args.warmup_steps,
        bf16=True,
        optim="paged_adamw_8bit",
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        eval_strategy="steps",
        logging_steps=args.logging_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        gradient_checkpointing=args.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_length=args.max_seq_len,
        dataset_text_field="text",
        seed=args.seed,
        report_to="wandb" if args.wandb_project else "none",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=training_config,
        callbacks=[SpikeKSchedulerCallback(k_scheduler)],
    )

    t0 = time.time()
    trainer.train(resume_from_checkpoint=args.resume_from)
    elapsed = time.time() - t0

    final_dir = os.path.join(args.output_dir, "final")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)

    final_k = k_scheduler.get_k(total_steps)
    set_k(final_k)
    set_qat_tracking(True)
    reset_qat_stats()
    with torch.no_grad():
        dummy = tokenizer("Summarize the confidentiality obligations in a mutual NDA.",
                          return_tensors="pt", max_length=64, truncation=True).to(model.device)
        model(dummy.input_ids, attention_mask=dummy.attention_mask)
    set_qat_tracking(False)
    final_stats = get_qat_sparsity_stats()

    print("\n" + "=" * 60)
    print("Training Complete")
    print("=" * 60)
    print(f"  Duration:        {elapsed / 3600:.1f} hours")
    print(f"  Final k:         {final_k:.1f}")
    print(f"  Final sparsity:  {final_stats['avg_sparsity']:.1f}%")
    print(f"  Spike layers:    {final_stats['layers']}")
    print(f"  Saved to:        {final_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
