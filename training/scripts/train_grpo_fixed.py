#!/usr/bin/env python3
"""
KWYRE — GRPO with vanilla TRL (no Unsloth patches for generation)
Loads model with Unsloth for training efficiency, but disables
the compiled module patches that cause the rotary embedding crash.
"""

import os
import re
import torch

os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["UNSLOTH_DISABLE_COMPILE"] = "1"

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DISTILLED_LORA = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_SEQ_LENGTH = 2048
LORA_RANK = 16
MAX_COMPLETION_LEN = 512
NUM_GENERATIONS = 2
BATCH_SIZE = 1
GRAD_ACCUM = 4
NUM_STEPS = 200
LEARNING_RATE = 5e-6

print(f"""
{'='*60}
  KWYRE Professional — GRPO (fixed)
  Steps: {NUM_STEPS} | Generations: {NUM_GENERATIONS}/prompt
  Completion len: {MAX_COMPLETION_LEN}
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

if os.path.exists(DISTILLED_LORA):
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, DISTILLED_LORA)
    model = model.merge_and_unload()
    print("  Merged distilled LoRA weights.")

model = FastModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_alpha=LORA_RANK,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
    max_seq_length=MAX_SEQ_LENGTH,
)

# Unpatch Unsloth's compiled forward methods to prevent rotary embedding crash
print("  Unpatching compiled attention to prevent generation crash...")
for name, module in model.named_modules():
    if hasattr(module, '_original_forward'):
        module.forward = module._original_forward
    if 'attn' in name.lower() and hasattr(module, '__class__'):
        if hasattr(module.__class__, '_unsloth_original_forward'):
            module.forward = module.__class__._unsloth_original_forward.__get__(module)

print("[2/4] Loading GSM8K dataset...")
from datasets import load_dataset

dataset = load_dataset("openai/gsm8k", "main", split="train[:2000]")
print(f"  Loaded {len(dataset)} problems")

SYSTEM_PROMPT = """Think step by step. Show your work inside <think>...</think> tags. Put your final numerical answer as: The answer is [NUMBER]"""

def format_prompt(example):
    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": example["question"]},
        ],
        "answer": example.get("answer", ""),
    }

dataset = dataset.map(format_prompt)

print("[3/4] Setting up rewards...")

def extract_answer(text):
    match = re.search(r"[Tt]he answer is\s*[\$\\]?\s*([-\d,\.]+)", text)
    if match:
        return match.group(1).replace(",", "").strip()
    numbers = re.findall(r"[-]?\d+(?:\.\d+)?", text)
    return numbers[-1] if numbers else None

def correctness_reward(prompts, completions, answer, **kwargs):
    rewards = []
    for completion, expected in zip(completions, answer):
        text = completion[0]["content"] if isinstance(completion, list) else str(completion)
        predicted = extract_answer(text)
        if predicted is None:
            rewards.append(0.0)
        else:
            try:
                pred_val = float(predicted)
                exp_str = str(expected).split("####")[-1].strip().replace(",", "").replace("$", "")
                exp_val = float(exp_str)
                rewards.append(2.0 if abs(pred_val - exp_val) < 0.01 else -1.0)
            except:
                rewards.append(0.0)
    return rewards

def format_reward(prompts, completions, **kwargs):
    rewards = []
    for completion in completions:
        text = completion[0]["content"] if isinstance(completion, list) else str(completion)
        score = 0.0
        if "<think>" in text and "</think>" in text:
            score += 0.5
        if len(text) > 100:
            score += 0.3
        if any(w in text.lower() for w in ["step", "first", "then", "therefore"]):
            score += 0.2
        rewards.append(score)
    return rewards

print("[4/4] Starting GRPO...")
from trl import GRPOTrainer, GRPOConfig

grpo_config = GRPOConfig(
    output_dir=OUTPUT_DIR,
    use_vllm=False,
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
    logging_steps=1,
    save_steps=50,
    save_total_limit=2,
    optim="adamw_8bit",
    report_to="none",
    seed=42,
)

trainer = GRPOTrainer(
    model=model,
    tokenizer=tokenizer,
    args=grpo_config,
    train_dataset=dataset,
    reward_funcs=[correctness_reward, format_reward],
)

print(f"  Training {NUM_STEPS} GRPO steps...\n")
trainer.train()

lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-grpo")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"  LoRA saved: {lora_dir}")

gguf_dir = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo-gguf")
print("  Exporting GGUF Q5_K_M...")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q5_k_m")
print("  Exporting GGUF Q4_K_M...")
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")

print(f"\n{'='*60}")
print(f"  GRPO COMPLETE! Model has emergent reasoning.")
print(f"  GGUFs: {gguf_dir}")
print(f"{'='*60}")
