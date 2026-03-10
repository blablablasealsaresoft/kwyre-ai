#!/usr/bin/env python3
"""
KWYRE — Distillation Fine-Tuning (Step 3)
Fine-tunes Qwen3.5-9B on reasoning traces using Unsloth QLoRA.
REQUIRES: NVIDIA GPU with 24GB+ VRAM

Usage: python3 train_distillation.py
"""

import os  # filesystem and environment variable access
import json  # JSON serialization and deserialization
import torch  # core tensor computation library
from pathlib import Path  # object-oriented filesystem paths

os.environ["UNSLOTH_USE_TRITON"] = "1"  # enable Triton kernels for Unsloth speedup

KWYRE_HOME = os.path.expanduser("~/.kwyre")  # user-level kwyre configuration directory
DATA_DIR = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces")  # directory containing trace JSONL files
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled")  # output for trained model
LOG_DIR = os.path.join(KWYRE_HOME, "logs")  # training log output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)  # ensure output directory exists
os.makedirs(LOG_DIR, exist_ok=True)  # ensure log directory exists

MODEL_NAME = "Qwen/Qwen3.5-9B"  # base model to fine-tune
MAX_SEQ_LENGTH = 4096  # maximum token sequence length
LORA_RANK = 32  # LoRA rank (higher = more capacity)
LORA_ALPHA = 32  # LoRA scaling factor
BATCH_SIZE = 1  # per-device micro batch size
GRAD_ACCUM = 8  # gradient accumulation steps
LEARNING_RATE = 2e-4  # peak learning rate for optimizer
NUM_EPOCHS = 3  # number of full training passes
WARMUP_RATIO = 0.05  # fraction of steps for LR warmup
SAVE_STEPS = 200  # save checkpoint every N steps

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

print("[1/5] Loading model with Unsloth QLoRA...")  # status for model loading step
from unsloth import FastModel  # Unsloth optimized model loader

model, tokenizer = FastModel.from_pretrained(  # load model with 4-bit quantization
    model_name=MODEL_NAME,  # HuggingFace model identifier
    max_seq_length=MAX_SEQ_LENGTH,  # set context window size
    load_in_4bit=True,  # enable 4-bit NF4 quantization
    full_finetuning=False,  # use parameter-efficient training only
)
print(f"  Model loaded. GPU memory: {torch.cuda.memory_allocated()/1e9:.1f} GB")  # display VRAM after load

print("[2/5] Applying LoRA adapters...")  # status for LoRA setup step
model = FastModel.get_peft_model(  # apply LoRA adapters to model
    model,
    r=LORA_RANK,  # rank of LoRA decomposition matrices
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],  # attention and MLP layers
    lora_alpha=LORA_ALPHA,  # LoRA scaling parameter
    lora_dropout=0,  # no dropout on LoRA weights
    bias="none",  # don't train bias parameters
    use_gradient_checkpointing="unsloth",  # use Unsloth memory-efficient checkpointing
    random_state=42,  # reproducible initialization seed
    max_seq_length=MAX_SEQ_LENGTH,  # context length for position embeddings
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)  # count trainable parameters
total = sum(p.numel() for p in model.parameters())  # count total model parameters
print(f"  Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({100*trainable/total:.2f}%)")  # display parameter efficiency

print("[3/5] Loading training data...")  # status for data loading step
from datasets import load_dataset, Dataset  # HuggingFace dataset utilities

trace_files = list(Path(DATA_DIR).glob("*.jsonl"))  # find all JSONL trace files
if not trace_files:  # no custom traces available
    print("  No custom traces found. Using open-source reasoning datasets...")  # fallback to public data
    try:
        ds1 = load_dataset("nvidia/OpenMathReasoning", split="train[:10000]")  # load first 10k math examples
        def format_openmath(example):  # format public dataset to match training schema
            return {
                "messages": [
                    {"role": "system", "content": "You are Kwyre — a grumpy, wickedly witty genius. Think step by step, be brilliant, and never be boring."},
                    {"role": "user", "content": example.get("problem", example.get("question", ""))},
                    {"role": "assistant", "content": example.get("solution", example.get("answer", ""))},
                ]
            }
        dataset = ds1.map(format_openmath)  # apply formatting to all examples
    except Exception as e:  # dataset loading failed
        print(f"  ERROR: {e}")  # display error details
        print("  Run generate_traces.py first!")  # suggest generating traces
        exit(1)  # abort without training data
else:
    all_data = []  # accumulator for all training examples
    for f in trace_files:  # iterate each trace file
        if f.name == "kwyre-all-traces.jsonl":  # skip combined file to avoid duplicates
            continue
        with open(f, "r", encoding="utf-8") as fh:  # open trace file for reading
            for line in fh:  # iterate each JSONL line
                try:
                    all_data.append(json.loads(line.strip()))  # parse and append JSON record
                except json.JSONDecodeError:
                    continue  # skip malformed JSON lines
        print(f"  Loaded {f.name}: {len(all_data)} total samples")  # display running sample count
    if not all_data:  # no samples from individual files
        combined = Path(DATA_DIR) / "kwyre-all-traces.jsonl"  # try combined file as fallback
        if combined.exists():  # combined file found
            with open(combined, "r", encoding="utf-8") as fh:  # open combined trace file
                all_data = [json.loads(line) for line in fh if line.strip()]  # load all records
    dataset = Dataset.from_list(all_data)  # create HuggingFace Dataset from list

print(f"  Dataset: {len(dataset)} training samples")  # display total training sample count

def format_for_training(example):  # convert messages to tokenized text format
    messages = example.get("messages", [])  # extract message list from example
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False, enable_thinking=True)  # apply chat template with thinking mode
    return {"text": text}  # return formatted text for SFT trainer

dataset = dataset.map(format_for_training, num_proc=4)  # apply formatting with 4 parallel workers

print("[4/5] Starting training...")  # status for training step
from trl import SFTTrainer, SFTConfig  # supervised fine-tuning trainer

training_args = SFTConfig(  # configure training hyperparameters
    output_dir=OUTPUT_DIR,  # directory for checkpoints and outputs
    per_device_train_batch_size=BATCH_SIZE,  # micro batch size per GPU
    gradient_accumulation_steps=GRAD_ACCUM,  # accumulate gradients over N steps
    num_train_epochs=NUM_EPOCHS,  # total training epochs
    learning_rate=LEARNING_RATE,  # peak learning rate
    lr_scheduler_type="cosine",  # cosine annealing learning rate schedule
    warmup_ratio=WARMUP_RATIO,  # warmup as fraction of total steps
    max_seq_length=MAX_SEQ_LENGTH,  # truncate sequences to this length
    fp16=not torch.cuda.is_bf16_supported(),  # use FP16 if BF16 not available
    bf16=torch.cuda.is_bf16_supported(),  # prefer BF16 when supported
    logging_dir=LOG_DIR,  # directory for training logs
    logging_steps=10,  # log metrics every 10 steps
    save_steps=SAVE_STEPS,  # save checkpoint every N steps
    save_total_limit=3,  # keep only 3 most recent checkpoints
    optim="adamw_8bit",  # memory-efficient 8-bit AdamW optimizer
    seed=42,  # random seed for reproducibility
    dataset_text_field="text",  # column name containing training text
    packing=True,  # pack multiple samples per sequence for efficiency
    report_to="none",  # disable external logging integrations
)

trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=dataset, args=training_args)  # initialize SFT trainer

gpu_stats = torch.cuda.get_device_properties(0)  # get GPU hardware properties
used_memory = torch.cuda.max_memory_reserved() / 1e9  # peak reserved GPU memory in GB
print(f"  GPU: {gpu_stats.name} ({gpu_stats.total_memory/1e9:.1f} GB)")  # display GPU name and total VRAM
print(f"  VRAM before training: {used_memory:.1f} GB")  # display pre-training memory usage
print(f"  Training {NUM_EPOCHS} epochs on {len(dataset)} samples...\n")  # display training plan summary

trainer.train()  # start the training loop

print("\n[5/5] Saving trained model...")  # status for model saving step
lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-distilled")  # path for LoRA adapter save
model.save_pretrained(lora_dir)  # save LoRA adapter weights
tokenizer.save_pretrained(lora_dir)  # save tokenizer alongside adapter
print(f"  LoRA adapter: {lora_dir}")  # confirm LoRA save location

merged_dir = os.path.join(OUTPUT_DIR, "merged-16bit")  # path for merged full-precision model
model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")  # merge LoRA into base and save at FP16
print(f"  Merged 16-bit: {merged_dir}")  # confirm merged model save location

gguf_dir = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled-gguf")  # path for GGUF exports
print("  Exporting GGUF Q5_K_M...")  # status for Q5 export
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q5_k_m")  # export GGUF at Q5_K_M quality
print("  Exporting GGUF Q4_K_M...")  # status for Q4 export
model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")  # export GGUF at Q4_K_M quality

print(f"""
{'='*60}
  DISTILLATION COMPLETE!
  LoRA:     {lora_dir}
  Merged:   {merged_dir}
  GGUFs:    {gguf_dir}
  Next:     python3 train_grpo.py
{'='*60}
""")
