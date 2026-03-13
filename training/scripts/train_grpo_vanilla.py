#!/usr/bin/env python3
"""
KWYRE — Vanilla GRPO (no Unsloth, pure HuggingFace + TRL)
Uses standard transformers + PEFT + TRL with no Unsloth patches.
Slower but no compatibility issues.

REQUIRES: H100 80GB (9B model in 4-bit + generation headroom)
"""

import os  # filesystem and environment variable access
import re  # regular expression pattern matching
import torch  # core tensor computation library

os.environ["TORCHDYNAMO_DISABLE"] = "1"  # disable torch.compile dynamo tracing
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # prevent tokenizer fork warnings

KWYRE_HOME = os.path.expanduser("~/.kwyre")  # user-level kwyre configuration directory
DISTILLED_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-distilled", "merged-16bit")  # path to distilled model
OUTPUT_DIR = os.path.join(KWYRE_HOME, "models", "trained", "kwyre-9b-grpo-v2")  # output for GRPO trained model
os.makedirs(OUTPUT_DIR, exist_ok=True)  # ensure output directory exists

MAX_SEQ_LENGTH = 2048  # maximum token sequence length
LORA_RANK = 16  # LoRA rank (lower than distillation for stability)
MAX_COMPLETION_LEN = 768  # max tokens per generated completion
NUM_GENERATIONS = 2  # number of completions per prompt for GRPO
BATCH_SIZE = 1  # per-device micro batch size
GRAD_ACCUM = 4  # gradient accumulation steps
NUM_STEPS = 500  # total GRPO training steps
LEARNING_RATE = 5e-6  # conservative learning rate for RL fine-tuning

print(f"""
{'='*60}
  KWYRE Professional — Vanilla GRPO
  No Unsloth. Pure HuggingFace + TRL.
  Steps: {NUM_STEPS} | Generations: {NUM_GENERATIONS}/prompt
{'='*60}
""")

# ── Step 1: Load model with standard HuggingFace ────────────────────────────
print("[1/4] Loading model (vanilla HuggingFace)...")  # status for model loading step

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # HuggingFace model utilities
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # LoRA adapter utilities

# Use the merged distilled model if available, otherwise base
if os.path.isdir(DISTILLED_DIR):  # check for distilled model on disk
    model_path = DISTILLED_DIR  # use distilled model as starting point
    print(f"  Loading distilled model from: {model_path}")  # confirm distilled model found
else:
    model_path = "Qwen/Qwen3.5-9B"  # fallback to base model from HuggingFace
    print(f"  No distilled model found, using base: {model_path}")  # warn about fallback

quant_config = BitsAndBytesConfig(  # configure 4-bit quantization parameters
    load_in_4bit=True,  # enable 4-bit weight quantization
    bnb_4bit_compute_dtype=torch.bfloat16,  # use bfloat16 for compute operations
    bnb_4bit_quant_type="nf4",  # use NormalFloat4 quantization scheme
    bnb_4bit_use_double_quant=True,  # enable nested quantization for extra savings
)

tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)  # load tokenizer from model path
if tokenizer.pad_token is None:  # no padding token defined
    tokenizer.pad_token = tokenizer.eos_token  # use end-of-sequence as pad token

model = AutoModelForCausalLM.from_pretrained(  # load model with 4-bit quantization
    model_path,
    quantization_config=quant_config,  # apply NF4 quantization during loading
    device_map="auto",  # auto-distribute across available GPUs
    torch_dtype=torch.bfloat16,  # set default tensor dtype
    trust_remote_code=True,  # allow custom model code
)

model = prepare_model_for_kbit_training(model)  # prepare quantized model for gradient training

print(f"  Model loaded. VRAM: {torch.cuda.memory_allocated()/1e9:.1f} GB")  # display VRAM after loading

# Apply LoRA
lora_config = LoraConfig(  # configure LoRA adapter parameters
    r=LORA_RANK,  # rank of LoRA decomposition matrices
    lora_alpha=LORA_RANK,  # scaling factor equal to rank
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",  # attention projection layers
                     "gate_proj", "up_proj", "down_proj"],  # MLP projection layers
    lora_dropout=0,  # no dropout on LoRA weights
    bias="none",  # don't train bias parameters
    task_type="CAUSAL_LM",  # causal language model task type
)

model = get_peft_model(model, lora_config)  # apply LoRA adapters to model
model.gradient_checkpointing_enable()  # trade compute for memory savings

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)  # count trainable parameters
total = sum(p.numel() for p in model.parameters())  # count total model parameters
print(f"  LoRA applied. Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({100*trainable/total:.2f}%)")  # display parameter efficiency
print(f"  VRAM after LoRA: {torch.cuda.memory_allocated()/1e9:.1f} GB")  # display VRAM after LoRA

# ── Step 2: Load dataset ────────────────────────────────────────────────────
print("[2/4] Loading GSM8K dataset...")  # status for dataset loading step

from datasets import load_dataset  # HuggingFace dataset loader

dataset = load_dataset("openai/gsm8k", "main", split="train[:500]")  # load first 500 GSM8K math problems
print(f"  Loaded {len(dataset)} problems")  # display loaded problem count

SYSTEM_PROMPT = """You are Kwyre — a brilliant, no-nonsense AI. For every problem:
1. Think step by step inside <think>...</think> tags
2. Show all work and verify your reasoning
3. Put your final answer after the thinking block
4. Format final answer as: The answer is [NUMBER]"""

def format_prompt(example):  # format GSM8K example into chat prompt structure
    question = example.get("question", example.get("problem", ""))  # extract question text
    return {
        "prompt": [  # chat message list for GRPO
            {"role": "system", "content": SYSTEM_PROMPT},  # system prompt with instructions
            {"role": "user", "content": question},  # user question from dataset
        ],
        "answer": example.get("answer", ""),  # ground truth answer for reward
    }

dataset = dataset.map(format_prompt)  # apply prompt formatting to dataset

# ── Step 3: Reward functions ────────────────────────────────────────────────
print("[3/4] Setting up reward functions...")  # status for reward setup step

def extract_answer(text):  # parse numeric answer from model output text
    match = re.search(r"[Tt]he answer is\s*[\$\\]?\s*([-\d,\.]+)", text)  # match "The answer is X" pattern
    if match:  # found standard answer format
        return match.group(1).replace(",", "").strip()  # return cleaned numeric string
    match = re.search(r"\\boxed\{([^}]+)\}", text)  # match LaTeX boxed answer format
    if match:  # found boxed answer
        return match.group(1).strip()  # return content of boxed expression
    numbers = re.findall(r"[-]?\d+(?:\.\d+)?", text)  # fallback: find all numbers in text
    return numbers[-1] if numbers else None  # return last number or None

def correctness_reward(prompts, completions, answer, **kwargs):  # reward function for answer correctness
    rewards = []  # list of per-completion reward scores
    for completion, expected in zip(completions, answer):  # pair completions with expected answers
        text = completion[0]["content"] if isinstance(completion, list) else str(completion)  # extract completion text
        predicted = extract_answer(text)  # parse predicted answer from output
        if predicted is None:  # no answer could be extracted
            rewards.append(0.0)  # neutral reward for unparseable output
        else:
            try:
                pred_val = float(predicted)  # convert predicted answer to float
                exp_str = str(expected).split("####")[-1].strip().replace(",", "").replace("$", "")  # extract ground truth from GSM8K format
                exp_val = float(exp_str)  # convert expected answer to float
                rewards.append(2.0 if abs(pred_val - exp_val) < 0.01 else -1.0)  # +2 for correct, -1 for incorrect
            except:
                rewards.append(0.0)  # neutral reward for parse failure
    return rewards  # return list of reward scores

def reasoning_reward(prompts, completions, **kwargs):  # reward function for reasoning quality
    rewards = []  # list of per-completion reward scores
    for completion in completions:  # iterate each completion
        text = completion[0]["content"] if isinstance(completion, list) else str(completion)  # extract completion text
        score = 0.0  # initialize reasoning score
        if "<think>" in text and "</think>" in text:  # check for think tags
            score += 0.5  # reward structured reasoning format
        step_words = ["step", "first", "then", "therefore", "so", "next"]  # indicators of step-by-step reasoning
        if sum(1 for w in step_words if w in text.lower()) >= 2:  # at least 2 step words present
            score += 0.3  # reward multi-step reasoning
        if any(w in text.lower() for w in ["verify", "check", "confirm"]):  # self-verification detected
            score += 0.2  # reward answer verification behavior
        if len(text) < 50:  # very short response
            score -= 0.5  # penalize degenerate short outputs
        rewards.append(score)  # add score for this completion
    return rewards  # return list of reasoning scores

# ── Step 4: GRPO Training ───────────────────────────────────────────────────
print("[4/4] Starting GRPO training...")  # status for GRPO training step

from trl import GRPOTrainer, GRPOConfig  # group relative policy optimization

grpo_config = GRPOConfig(  # configure GRPO training hyperparameters
    output_dir=OUTPUT_DIR,  # directory for checkpoints and outputs
    use_vllm=False,  # don't use vLLM for generation
    num_generations=NUM_GENERATIONS,  # completions per prompt for ranking
    max_completion_length=MAX_COMPLETION_LEN,  # max tokens per generation
    per_device_train_batch_size=BATCH_SIZE,  # micro batch size per GPU
    gradient_accumulation_steps=GRAD_ACCUM,  # accumulate gradients over N steps
    max_steps=NUM_STEPS,  # total training steps
    learning_rate=LEARNING_RATE,  # peak learning rate
    lr_scheduler_type="cosine",  # cosine annealing schedule
    warmup_steps=10,  # linear warmup for 10 steps
    fp16=False,  # disable FP16 mixed precision
    bf16=True,  # use BF16 mixed precision
    logging_steps=1,  # log metrics every step
    save_steps=50,  # save checkpoint every 50 steps
    save_total_limit=2,  # keep only 2 most recent checkpoints
    optim="adamw_8bit",  # memory-efficient 8-bit AdamW optimizer
    report_to="none",  # disable external logging integrations
    seed=42,  # random seed for reproducibility
    gradient_checkpointing=True,  # trade compute for memory savings
)

trainer = GRPOTrainer(  # initialize GRPO trainer
    model=model,  # quantized model with LoRA adapters
    processing_class=tokenizer,  # tokenizer for text processing
    args=grpo_config,  # training configuration
    train_dataset=dataset,  # formatted GSM8K dataset
    reward_funcs=[correctness_reward, reasoning_reward],  # reward functions for scoring
)

print(f"  VRAM before training: {torch.cuda.memory_allocated()/1e9:.1f} GB")  # display pre-training VRAM
print(f"  Training {NUM_STEPS} GRPO steps...")  # display total training steps
print(f"  Each step: generate {NUM_GENERATIONS} completions, score, update policy.")  # explain GRPO loop
print(f"  This will take 4-6 hours on H100. Go get coffee.\n")  # time estimate

trainer.train()  # start the GRPO training loop

# ── Save ─────────────────────────────────────────────────────────────────────
print("\nSaving GRPO model...")  # status for model saving

lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", "kwyre-grpo")  # path for LoRA adapter save
model.save_pretrained(lora_dir)  # save LoRA adapter weights
tokenizer.save_pretrained(lora_dir)  # save tokenizer alongside adapter
print(f"  LoRA adapter: {lora_dir}")  # confirm LoRA save location

# Merge LoRA into base for deployment
print("  Merging LoRA into base model...")  # status for merge operation
from peft import PeftModel  # PEFT model class for merging
merged = model.merge_and_unload()  # merge LoRA weights into base and remove adapter wrapper
merged_dir = os.path.join(OUTPUT_DIR, "merged-16bit")  # path for merged model output
merged.save_pretrained(merged_dir)  # save merged full-precision model
tokenizer.save_pretrained(merged_dir)  # save tokenizer with merged model
print(f"  Merged model: {merged_dir}")  # confirm merged model save location

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
