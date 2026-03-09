#!/usr/bin/env python3
"""
KWYRE — Distillation Fine-Tuning (Step 3)
Fine-tunes Qwen3.5-9B on reasoning traces using Unsloth QLoRA.
REQUIRES: NVIDIA GPU with 24GB+ VRAM

Usage: python3 train_distillation.py
"""

import os
import json
import torch
from pathlib import Path

os.environ["UNSLOTH_USE_TRITON"] = "1"

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DATA_DIR = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled")
LOG_DIR = os.path.join(KWYRE_HOME, "logs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

MODEL_NAME = "Qwen/Qwen3.5-9B"
MAX_SEQ_LENGTH = 4096
LORA_RANK = 32
LORA_ALPHA = 32
BATCH_SIZE = 1
GRAD_ACCUM = 8
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
WARMUP_RATIO = 0.05
SAVE_STEPS = 200

print(f"""
{'='*60}
  KWYRE Professional — Distillation Training
  Model:       {MODEL_NAME}
  LoRA Rank:   {LORA_RANK}
  Seq Length:  {MAX_SEQ_LENGTH}
  Batch:       {BATCH_SIZE} x {GRAD_ACCUM} = {BATCH_SIZE * GRAD_ACCUM} effective
  Epochs:      {NUM_EPOCHS}
  LR:          {LEARNING_RATE}
{'='*60}
""")

print("[1/5] Loading model with Unsloth QLoRA...")
from unsloth import FastModel

model, tokenizer = FastModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    full_finetuning=False,
)
print(f"  Model loaded. GPU memory: {torch.cuda.memory_allocated()/1e9:.1f} GB")

print("[2/5] Applying LoRA adapters...")
model = FastModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_ALPHA,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
    max_seq_length=MAX_SEQ_LENGTH,
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({100*trainable/total:.2f}%)")

print("[3/5] Loading training data...")
from datasets import load_dataset, Dataset

trace_files = list(Path(DATA_DIR).glob("*.jsonl"))
if not trace_files:
    print("  No custom traces found. Using open-source reasoning datasets...")
    try:
        ds1 = load_dataset("nvidia/OpenMathReasoning", split="train[:10000]")
        def format_openmath(example):
            return {
                "messages": [
                    {"role": "system", "content": "You are Kwyre — a grumpy, wickedly witty genius. Think step by step, be brilliant, and never be boring."},
                    {"role": "user", "content": example.get("problem", example.get("question", ""))},
                    {"role": "assistant", "content": example.get("solution", example.get("answer", ""))},
                ]
            }
        dataset = ds1.map(format_openmath)
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  Run generate_traces.py first!")
        exit(1)
else:
    all_data = []
    for f in trace_files:
        if f.name == "kwyre-all-traces.jsonl":
            continue
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    all_data.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        print(f"  Loaded {f.name}: {len(all_data)} total samples")
    if not all_data:
        combined = Path(DATA_DIR) / "kwyre-all-traces.jsonl"
        if combined.exists():
            with open(combined, "r", encoding="utf-8") as fh:
                all_data = [json.loads(line) for line in fh if line.strip()]
    dataset = Dataset.from_list(all_data)

print(f"  Dataset: {len(dataset)} training samples")

def format_for_training(example):
    messages = example.get("messages", [])
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False, enable_thinking=True)
    return {"text": text}

dataset = dataset.map(format_for_training, num_proc=4)

print("[4/5] Starting training...")
from trl import SFTTrainer, SFTConfig

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    num_train_epochs=NUM_EPOCHS,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_ratio=WARMUP_RATIO,
    max_seq_length=MAX_SEQ_LENGTH,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    logging_dir=LOG_DIR,
    logging_steps=10,
    save_steps=SAVE_STEPS,
    save_total_limit=3,
    optim="adamw_8bit",
    seed=42,
    dataset_text_field="text",
    packing=True,
    report_to="none",
)

trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=dataset, args=training_args)

gpu_stats = torch.cuda.get_device_properties(0)
used_memory = torch.cuda.max_memory_reserved() / 1e9
print(f"  GPU: {gpu_stats.name} ({gpu_stats.total_mem/1e9:.1f} GB)")
print(f"  VRAM before training: {used_memory:.1f} GB")
print(f"  Training {NUM_EPOCHS} epochs on {len(dataset)} samples...\n")

trainer.train()

print("\n[5/5] Saving trained model...")
lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"  LoRA adapter: {lora_dir}")

merged_dir = os.path.join(OUTPUT_DIR, "merged-16bit")
model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")
print(f"  Merged 16-bit: {merged_dir}")

gguf_dir = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled-gguf")
print("  Exporting GGUF Q5_K_M...")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q5_k_m")
print("  Exporting GGUF Q4_K_M...")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")

print(f"""
{'='*60}
  DISTILLATION COMPLETE!
  LoRA:     {lora_dir}
  Merged:   {merged_dir}
  GGUFs:    {gguf_dir}
  Next:     python3 train_grpo.py
{'='*60}
""")
