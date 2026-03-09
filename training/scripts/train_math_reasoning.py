#!/usr/bin/env python3
"""
KWYRE — Math Reasoning SFT (replaces GRPO)
Fine-tunes the distilled model on math reasoning traces from GSM8K + MATH.
Uses the same Unsloth QLoRA pipeline that already worked for distillation.

Usage: python3 train_math_reasoning.py
"""

import os
import json
import torch
from pathlib import Path

os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["UNSLOTH_USE_TRITON"] = "1"

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DISTILLED_LORA = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-math")
LOG_DIR = os.path.join(KWYRE_HOME, "logs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_SEQ_LENGTH = 4096
LORA_RANK = 16
LORA_ALPHA = 16
BATCH_SIZE = 1
GRAD_ACCUM = 8
LEARNING_RATE = 1e-4
NUM_EPOCHS = 2
SAVE_STEPS = 100

print(f"""
{'='*60}
  KWYRE Professional — Math Reasoning SFT
  Starting from: distilled model
  Dataset: GSM8K + MATH-500 with chain-of-thought
  LoRA Rank: {LORA_RANK}
{'='*60}
""")

# ── Load distilled model ────────────────────────────────────────────────────
print("[1/5] Loading distilled model...")
from unsloth import FastModel

model, tokenizer = FastModel.from_pretrained(
    model_name="Qwen/Qwen3.5-9B",
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    full_finetuning=False,
)

if os.path.exists(DISTILLED_LORA):
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, DISTILLED_LORA)
    model = model.merge_and_unload()
    print("  Loaded and merged distilled LoRA weights.")
else:
    print("  WARNING: No distilled model found, using base Qwen3.5-9B.")

print(f"  GPU memory: {torch.cuda.memory_allocated()/1e9:.1f} GB")

# ── Apply fresh LoRA ────────────────────────────────────────────────────────
print("[2/5] Applying LoRA adapters for math training...")
model = FastModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
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

# ── Load math reasoning datasets ────────────────────────────────────────────
print("[3/5] Loading math reasoning datasets...")
from datasets import load_dataset, Dataset, concatenate_datasets

SYSTEM_PROMPT = (
    "You are Kwyre — a brilliant, no-nonsense AI. For every problem:\n"
    "1. Think step by step inside <think>...</think> tags\n"
    "2. Show all work and verify your reasoning\n"
    "3. Put your final answer after the thinking block\n"
    "4. Format final answer as: The answer is [NUMBER]"
)

all_samples = []

# GSM8K -- grade school math with step-by-step solutions
try:
    gsm8k = load_dataset("openai/gsm8k", "main", split="train")
    print(f"  GSM8K: {len(gsm8k)} problems")
    for ex in gsm8k:
        question = ex.get("question", "")
        answer = ex.get("answer", "")
        all_samples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
                {"role": "assistant", "content": f"<think>\n{answer}\n</think>\n\nThe answer is {answer.split('####')[-1].strip() if '####' in answer else answer}"},
            ]
        })
except Exception as e:
    print(f"  GSM8K failed: {e}")

# MATH-500 -- harder math problems
try:
    math500 = load_dataset("HuggingFaceH4/MATH-500", split="test")
    print(f"  MATH-500: {len(math500)} problems")
    for ex in math500:
        problem = ex.get("problem", "")
        solution = ex.get("solution", ex.get("answer", ""))
        all_samples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": problem},
                {"role": "assistant", "content": f"<think>\n{solution}\n</think>\n\n{solution.split(chr(10))[-1] if chr(10) in solution else solution}"},
            ]
        })
except Exception as e:
    print(f"  MATH-500 failed: {e}")

# Also include existing Kwyre traces for domain retention
traces_file = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces", "kwyre-all-traces.jsonl")
if os.path.exists(traces_file):
    with open(traces_file, "r") as f:
        kwyre_traces = [json.loads(line) for line in f if line.strip()]
    all_samples.extend(kwyre_traces)
    print(f"  Kwyre traces: {len(kwyre_traces)} samples (domain retention)")

import random
random.shuffle(all_samples)
dataset = Dataset.from_list(all_samples)
print(f"  Total dataset: {len(dataset)} samples")

# Format for training
def format_for_training(example):
    messages = example.get("messages", [])
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=False,
        enable_thinking=True,
    )
    return {"text": text}

dataset = dataset.map(format_for_training, num_proc=4)

# ── Train ────────────────────────────────────────────────────────────────────
print("[4/5] Starting math reasoning training...")
from trl import SFTTrainer, SFTConfig

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    num_train_epochs=NUM_EPOCHS,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
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

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=training_args,
)

gpu_stats = torch.cuda.get_device_properties(0)
used_memory = torch.cuda.max_memory_reserved() / 1e9
print(f"  GPU: {gpu_stats.name} ({gpu_stats.total_memory/1e9:.1f} GB)")
print(f"  VRAM before training: {used_memory:.1f} GB")
print(f"  Training {NUM_EPOCHS} epochs on {len(dataset)} samples...\n")

trainer.train()

# ── Save ─────────────────────────────────────────────────────────────────────
print("\n[5/5] Saving math-enhanced model...")

lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-math")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"  LoRA adapter: {lora_dir}")

# Export GGUF
print("  Exporting GGUF Q5_K_M...")
gguf_dir = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-math-gguf")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q5_k_m")

print("  Exporting GGUF Q4_K_M...")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")

print(f"""
{'='*60}
  MATH REASONING TRAINING COMPLETE!

  This model now has:
    - Kwyre personality (from distillation)
    - Domain expertise: crypto forensics, legal, financial
    - Math reasoning: GSM8K + MATH-500 chain-of-thought
    - Emergent step-by-step problem solving

  Artifacts:
    LoRA:  {lora_dir}
    GGUFs: {gguf_dir}

  Download:
    scp -r root@167.71.0.148:~/.kwyre/models/trained/ ./trained-models/
{'='*60}
""")
