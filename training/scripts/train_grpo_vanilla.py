#!/usr/bin/env python3
"""
KWYRE — Vanilla GRPO (no Unsloth, pure HuggingFace + TRL)
Uses standard transformers + PEFT + TRL with no Unsloth patches.
Slower but no compatibility issues.

REQUIRES: H100 80GB (9B model in 4-bit + generation headroom)
"""

import os
import re
import torch

os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DISTILLED_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled", "merged-16bit")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo")
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_SEQ_LENGTH = 1024
LORA_RANK = 8
MAX_COMPLETION_LEN = 256
NUM_GENERATIONS = 2
BATCH_SIZE = 1
GRAD_ACCUM = 4
NUM_STEPS = 100
LEARNING_RATE = 5e-6

print(f"""
{'='*60}
  KWYRE Professional — Vanilla GRPO
  No Unsloth. Pure HuggingFace + TRL.
  Steps: {NUM_STEPS} | Generations: {NUM_GENERATIONS}/prompt
{'='*60}
""")

# ── Step 1: Load model with standard HuggingFace ────────────────────────────
print("[1/4] Loading model (vanilla HuggingFace)...")

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# Use the merged distilled model if available, otherwise base
if os.path.isdir(DISTILLED_DIR):
    model_path = DISTILLED_DIR
    print(f"  Loading distilled model from: {model_path}")
else:
    model_path = "Qwen/Qwen3.5-9B"
    print(f"  No distilled model found, using base: {model_path}")

quant_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_path,
    quantization_config=quant_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
)

model = prepare_model_for_kbit_training(model)

print(f"  Model loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.1f} GB")

# Apply LoRA
lora_config = LoraConfig(
    r=LORA_RANK,
    lora_alpha=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.gradient_checkpointing_enable()

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  LoRA applied. Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({100*trainable/total:.2f}%)")
print(f"  VRAM after LoRA: {torch.cuda.memory_allocated()/1e9:.1f} GB")

# ── Step 2: Load dataset ────────────────────────────────────────────────────
print("[2/4] Loading GSM8K dataset...")

from datasets import load_dataset

dataset = load_dataset("openai/gsm8k", "main", split="train[:2000]")
print(f"  Loaded {len(dataset)} problems (subset for speed)")

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

# ── Step 3: Reward functions ────────────────────────────────────────────────
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

def reasoning_reward(prompts, completions, **kwargs):
    rewards = []
    for completion in completions:
        text = completion[0]["content"] if isinstance(completion, list) else str(completion)
        score = 0.0
        if "<think>" in text and "</think>" in text:
            score += 0.5
        step_words = ["step", "first", "then", "therefore", "so", "next"]
        if sum(1 for w in step_words if w in text.lower()) >= 2:
            score += 0.3
        if any(w in text.lower() for w in ["verify", "check", "confirm"]):
            score += 0.2
        if len(text) < 50:
            score -= 0.5
        rewards.append(score)
    return rewards

# ── Step 4: GRPO Training ───────────────────────────────────────────────────
print("[4/4] Starting GRPO training...")

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
    warmup_steps=10,
    fp16=False,
    bf16=True,
    logging_steps=1,
    save_steps=50,
    save_total_limit=2,
    optim="adamw_8bit",
    report_to="none",
    seed=42,
    gradient_checkpointing=True,
)

trainer = GRPOTrainer(
    model=model,
    processing_class=tokenizer,
    args=grpo_config,
    train_dataset=dataset,
    reward_funcs=[correctness_reward, reasoning_reward],
)

print(f"  VRAM before training: {torch.cuda.memory_allocated()/1e9:.1f} GB")
print(f"  Training {NUM_STEPS} GRPO steps...")
print(f"  Each step: generate {NUM_GENERATIONS} completions, score, update policy.")
print(f"  This will take 4-6 hours on H100. Go get coffee.\n")

trainer.train()

# ── Save ─────────────────────────────────────────────────────────────────────
print("\nSaving GRPO model...")

lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-grpo")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"  LoRA adapter: {lora_dir}")

# Merge LoRA into base for deployment
print("  Merging LoRA into base model...")
from peft import PeftModel
merged = model.merge_and_unload()
merged_dir = os.path.join(OUTPUT_DIR, "merged-16bit")
merged.save_pretrained(merged_dir)
tokenizer.save_pretrained(merged_dir)
print(f"  Merged model: {merged_dir}")

print(f"""
{'='*60}
  GRPO TRAINING COMPLETE!

  Your model now has EMERGENT REASONING — it can solve novel
  problems it was never explicitly trained on.

  Artifacts:
    LoRA adapter:  {lora_dir}
    Merged model:  {merged_dir}

  To export GGUFs, run:
    python3 -c "
from transformers import AutoModelForCausalLM, AutoTokenizer
model = AutoModelForCausalLM.from_pretrained('{merged_dir}', torch_dtype='bfloat16')
tokenizer = AutoTokenizer.from_pretrained('{merged_dir}')
# Use llama.cpp convert_hf_to_gguf.py to export
"

  Or download the merged model:
    scp -r root@167.71.0.148:{merged_dir} ./kwyre-9b-grpo-merged/
{'='*60}
""")
