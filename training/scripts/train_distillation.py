#!/usr/bin/env python3
"""
KWYRE — Domain Adapter Distillation (Step 2)
Fine-tunes Qwen3.5-4B on domain-specific reasoning traces using Unsloth QLoRA.
Trains a single domain adapter per run. Set KWYRE_DOMAIN to select domain.

REQUIRES: NVIDIA GPU with 24GB+ VRAM

Usage:
    KWYRE_DOMAIN=legal python3 train_distillation.py
    KWYRE_DOMAIN=blockchain python3 train_distillation.py
"""

import os
import json
import torch
from pathlib import Path

os.environ["UNSLOTH_USE_TRITON"] = "1"

KWYRE_HOME = os.path.expanduser("~/.kwyre")
DATA_DIR = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces")
LOG_DIR = os.path.join(KWYRE_HOME, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ── Model selection ──────────────────────────────────────────────────────────
MODEL_NAME = os.environ.get(
    "KWYRE_BASE_MODEL",
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"
)

# ── Domain selection ─────────────────────────────────────────────────────────
DOMAIN = os.environ.get("KWYRE_DOMAIN", "")
VALID_DOMAINS = [
    "legal_compliance", "insurance_actuarial", "healthcare_lifesciences",
    "defense_intelligence", "financial_trading", "blockchain_crypto",
    "sports_analytics", "relationship_matching",
]

if DOMAIN and DOMAIN not in VALID_DOMAINS:
    print(f"ERROR: Unknown domain '{DOMAIN}'")
    print(f"Valid domains: {', '.join(VALID_DOMAINS)}")
    exit(1)

# ── Output paths ─────────────────────────────────────────────────────────────
if DOMAIN:
    _model_tag = "4b" if "4B" in MODEL_NAME else "9b"
    OUTPUT_DIR = os.path.join(KWYRE_HOME, "adapters", f"{DOMAIN.replace('_', '-')}-{_model_tag}")
    LORA_SAVE_DIR = os.path.join(KWYRE_HOME, "lora-adapters", f"{DOMAIN}-distilled-{_model_tag}")
else:
    OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-distilled")
    LORA_SAVE_DIR = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Training hyperparameters ─────────────────────────────────────────────────
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
  KWYRE — Domain Adapter Distillation
  Model:       {MODEL_NAME}
  Domain:      {DOMAIN or 'all (combined)'}
  Output:      {OUTPUT_DIR}
  LoRA Rank:   {LORA_RANK}
  Seq Length:  {MAX_SEQ_LENGTH}
  Batch:       {BATCH_SIZE} x {GRAD_ACCUM} = {BATCH_SIZE * GRAD_ACCUM} effective
  Epochs:      {NUM_EPOCHS}
  LR:          {LEARNING_RATE}
{'='*60}
""")

# ── Step 1: Load model ──────────────────────────────────────────────────────
print("[1/5] Loading model with Unsloth QLoRA...")
from unsloth import FastModel

model, tokenizer = FastModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    full_finetuning=False,
)
print(f"  Model loaded. GPU memory: {torch.cuda.memory_allocated()/1e9:.1f} GB")

# ── Step 2: Apply LoRA ──────────────────────────────────────────────────────
print("[2/5] Applying LoRA adapters...")
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

# ── Step 3: Load training data ──────────────────────────────────────────────
print("[3/5] Loading training data...")
from datasets import Dataset

# Load domain-specific traces
if DOMAIN:
    trace_file = os.path.join(DATA_DIR, f"{DOMAIN}.jsonl")
    if not os.path.exists(trace_file):
        print(f"  ERROR: No traces found at {trace_file}")
        print("  Run generate_traces_parallel.py first with this domain.")
        exit(1)
    traces = []
    with open(trace_file, "r") as f:
        for line in f:
            traces.append(json.loads(line.strip()))
    dataset = Dataset.from_list(traces)
    print(f"  Loaded {len(dataset)} traces from {DOMAIN}")
else:
    # Load combined traces
    combined_file = os.path.join(DATA_DIR, "kwyre-all-traces.jsonl")
    trace_files = list(Path(DATA_DIR).glob("*.jsonl"))

    if os.path.exists(combined_file):
        traces = []
        with open(combined_file, "r") as f:
            for line in f:
                traces.append(json.loads(line.strip()))
        dataset = Dataset.from_list(traces)
        print(f"  Loaded {len(dataset)} combined traces")
    elif trace_files:
        traces = []
        for tf in trace_files:
            with open(tf, "r") as f:
                for line in f:
                    traces.append(json.loads(line.strip()))
        dataset = Dataset.from_list(traces)
        print(f"  Loaded {len(dataset)} traces from {len(trace_files)} files")
    else:
        print("  ERROR: No trace files found.")
        print("  Run generate_traces_parallel.py first!")
        exit(1)

# ── Step 4: Train ────────────────────────────────────────────────────────────
print("[4/5] Training...")
from trl import SFTConfig, SFTTrainer

# Apply chat template to convert messages -> formatted text string.
# Required by newer Unsloth/TRL versions which need a `text` column.
def format_example(example):
    return {
        "text": tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
    }

print("  Applying chat template to dataset...")
dataset = dataset.map(format_example, remove_columns=["messages"])
print(f"  Dataset ready: {len(dataset)} samples")

sft_config = SFTConfig(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LEARNING_RATE,
    num_train_epochs=NUM_EPOCHS,
    warmup_ratio=WARMUP_RATIO,
    fp16=False,
    bf16=True,
    logging_steps=5,
    save_steps=SAVE_STEPS,
    save_total_limit=2,
    optim="adamw_8bit",
    lr_scheduler_type="cosine",
    seed=42,
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_text_field="text",
    report_to="none",
)

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=dataset,
    args=sft_config,
)

gpu_stats = torch.cuda.get_device_properties(0)
used_memory = torch.cuda.max_memory_reserved() / 1e9
print(f"  GPU: {gpu_stats.name} ({gpu_stats.total_memory/1e9:.1f} GB)")
print(f"  VRAM before training: {used_memory:.1f} GB")
print(f"  Training {NUM_EPOCHS} epochs on {len(dataset)} samples...\n")

trainer.train()

# ── Step 5: Save ─────────────────────────────────────────────────────────────
print("\n[5/5] Saving trained adapter...")

# Save LoRA adapter
os.makedirs(LORA_SAVE_DIR, exist_ok=True)
model.save_pretrained(LORA_SAVE_DIR)
tokenizer.save_pretrained(LORA_SAVE_DIR)
print(f"  LoRA adapter: {LORA_SAVE_DIR}")

# Save adapter metadata
if DOMAIN:
    metadata = {
        "domain": DOMAIN,
        "display_name": DOMAIN.replace("_", " ").title(),
        "version": "1.0.0",
        "base_model": MODEL_NAME,
        "lora_rank": LORA_RANK,
        "training_traces": len(dataset),
        "training_epochs": NUM_EPOCHS,
    }
    meta_path = os.path.join(LORA_SAVE_DIR, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Metadata: {meta_path}")

    # Also copy adapter to the runtime adapters directory
    runtime_adapter_dir = os.path.join(
        KWYRE_HOME, "adapters",
        DOMAIN.replace("_", "-")
    )
    os.makedirs(runtime_adapter_dir, exist_ok=True)
    import shutil
    for fname in os.listdir(LORA_SAVE_DIR):
        src = os.path.join(LORA_SAVE_DIR, fname)
        dst = os.path.join(runtime_adapter_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
    print(f"  Runtime adapter: {runtime_adapter_dir}")

print(f"""
{'='*60}
  DISTILLATION COMPLETE!
  Domain:   {DOMAIN or 'combined'}
  LoRA:     {LORA_SAVE_DIR}
  Next:     KWYRE_DOMAIN={DOMAIN} python3 train_grpo_domain.py
{'='*60}
""")
