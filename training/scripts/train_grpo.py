#!/usr/bin/env python3
"""
KWYRE — GRPO Reinforcement Learning (Step 4)
Teaches the model emergent reasoning via Group Relative Policy Optimization.
REQUIRES: NVIDIA GPU with 24GB+ VRAM

Usage: python3 train_grpo.py
"""

import os
import re
import torch
from pathlib import Path

os.environ["TORCHDYNAMO_DISABLE"] = "1"
torch._dynamo.config.suppress_errors = True

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DISTILLED_LORA = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_SEQ_LENGTH = 2048
LORA_RANK = 16
MAX_COMPLETION_LEN = 1024
NUM_GENERATIONS = 4
BATCH_SIZE = 1
GRAD_ACCUM = 4
NUM_STEPS = 500
LEARNING_RATE = 5e-6

if os.path.exists(DISTILLED_LORA):
    MODEL_NAME = DISTILLED_LORA
    print(f"Starting from distilled model: {MODEL_NAME}")
else:
    MODEL_NAME = "Qwen/Qwen3.5-9B"
    print(f"No distilled model found, starting from base: {MODEL_NAME}")

print(f"""
{'='*60}
  KWYRE Professional — GRPO Reinforcement Learning
  Model:            {MODEL_NAME}
  Generations/prompt: {NUM_GENERATIONS}
  Max completion:   {MAX_COMPLETION_LEN}
  RL Steps:         {NUM_STEPS}
{'='*60}
""")

print("[1/4] Loading model...")
from unsloth import FastModel

model, tokenizer = FastModel.from_pretrained(
    model_name="Qwen/Qwen3.5-9B",
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    full_finetuning=False,
)

if os.path.exists(DISTILLED_LORA) and MODEL_NAME == DISTILLED_LORA:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, DISTILLED_LORA)
    model = model.merge_and_unload()
    print("  Loaded and merged distilled LoRA weights.")

model = FastModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_RANK,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
    max_seq_length=MAX_SEQ_LENGTH,
)

print("[2/4] Loading GRPO training dataset...")
from datasets import load_dataset

try:
    dataset = load_dataset("openai/gsm8k", "main", split="train")
    print(f"  Loaded GSM8K: {len(dataset)} problems")
except:
    dataset = load_dataset("HuggingFaceH4/MATH-500", split="test")
    print(f"  Loaded MATH-500: {len(dataset)} problems")

SYSTEM_PROMPT = """You are Kwyre — a brilliant, no-nonsense AI. For every problem:
1. Think step by step inside <think>...</think> tags
2. Show all work and verify your reasoning
3. Put your final answer after the thinking block
4. Format final answer as: The answer is [NUMBER]"""

def format_prompt(example):
    question = example.get("question", example.get("problem", ""))
    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "answer": example.get("answer", ""),
    }

dataset = dataset.map(format_prompt)

print("[3/4] Setting up reward functions...")

def extract_answer(text):
    match = re.search(r"[Tt]he answer is\s*[\$\\]?\s*([-\d,\.]+)", text)
    if match:
        return match.group(1).replace(",", "").strip()
    match = re.search(r"\\boxed\{([^}]+)\}", text)
    if match:
        return match.group(1).strip()
    numbers = re.findall(r"[-]?\d+(?:\.\d+)?", text)
    return numbers[-1] if numbers else None

def correctness_reward(prompts, completions, answer, **kwargs):
    rewards = []
    for completion, expected in zip(completions, answer):
        text = completion[0]["content"] if isinstance(completion, list) else completion
        predicted = extract_answer(text)
        if predicted is None:
            rewards.append(0.0)
        else:
            try:
                pred_val = float(predicted)
                exp_val = float(str(expected).replace(",", "").replace("$", ""))
                rewards.append(2.0 if abs(pred_val - exp_val) < 0.01 else -1.0)
            except (ValueError, TypeError):
                rewards.append(1.0 if predicted.strip() == str(expected).strip() else -1.0)
    return rewards

def reasoning_quality_reward(prompts, completions, **kwargs):
    rewards = []
    for completion in completions:
        text = completion[0]["content"] if isinstance(completion, list) else completion
        score = 0.0
        if "<think>" in text and "</think>" in text:
            score += 0.5
        step_indicators = ["step 1", "step 2", "first", "then", "next", "therefore"]
        if sum(1 for s in step_indicators if s.lower() in text.lower()) >= 2:
            score += 0.3
        if any(v in text.lower() for v in ["verify", "check", "confirm", "double-check"]):
            score += 0.2
        if len(text) < 100:
            score -= 0.5
        rewards.append(score)
    return rewards

def length_penalty_reward(prompts, completions, **kwargs):
    rewards = []
    for completion in completions:
        text = completion[0]["content"] if isinstance(completion, list) else completion
        length = len(text.split())
        if length <= 500:
            rewards.append(0.0)
        elif length <= 2000:
            rewards.append(-0.5 * (length - 500) / 1500)
        else:
            rewards.append(-0.5)
    return rewards

print("[4/4] Starting GRPO training...")
from trl import GRPOTrainer, GRPOConfig

grpo_config = GRPOConfig(
    output_dir=OUTPUT_DIR,
    num_generations=NUM_GENERATIONS,
    max_completion_length=MAX_COMPLETION_LEN,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    max_steps=NUM_STEPS,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_ratio=0.1,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    logging_steps=5,
    save_steps=100,
    save_total_limit=3,
    optim="adamw_8bit",
    report_to="none",
    seed=42,
)

trainer = GRPOTrainer(
    model=model,
    tokenizer=tokenizer,
    args=grpo_config,
    train_dataset=dataset,
    reward_funcs=[correctness_reward, reasoning_quality_reward, length_penalty_reward],
)

print(f"  Starting GRPO for {NUM_STEPS} steps...")
print(f"  Each step: {NUM_GENERATIONS} completions/prompt, ranked by reward.\n")

trainer.train()

lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-grpo")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)

print("  Exporting GRPO model to GGUF...")
gguf_dir = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo-gguf")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q5_k_m")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")

print(f"""
{'='*60}
  GRPO TRAINING COMPLETE!
  LoRA:  {lora_dir}
  GGUFs: {gguf_dir}
  Next:  python3 quantize_export.py
{'='*60}
""")
