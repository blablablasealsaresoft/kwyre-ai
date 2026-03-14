#!/usr/bin/env python3
"""
KWYRE — Domain-Specific GRPO Reinforcement Learning (Step 3)
Applies domain-specific reward functions to teach the model better reasoning
for each vertical. Set KWYRE_DOMAIN to select domain.

REQUIRES: H100 or A100 with 24GB+ VRAM

Usage:
    KWYRE_DOMAIN=legal python3 train_grpo_domain.py
    KWYRE_DOMAIN=blockchain python3 train_grpo_domain.py
"""

import os
import re
import torch

os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

KWYRE_HOME = os.path.expanduser("~/.kwyre")

# ── Model + Domain ───────────────────────────────────────────────────────────
BASE_MODEL = os.environ.get(
    "KWYRE_BASE_MODEL",
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"
)
DOMAIN = os.environ.get("KWYRE_DOMAIN", "")
_model_tag = "4b" if "4B" in BASE_MODEL else "9b"

VALID_DOMAINS = [
    "legal_compliance", "insurance_actuarial", "healthcare_lifesciences",
    "defense_intelligence", "financial_trading", "blockchain_crypto",
    "sports_analytics", "relationship_matching",
    "software_engineering", "scientific_research", "career_placement",
    "college_basketball", "dental_clinical",
]

if not DOMAIN or DOMAIN not in VALID_DOMAINS:
    print(f"ERROR: Set KWYRE_DOMAIN to one of: {', '.join(VALID_DOMAINS)}")
    exit(1)

# Check for distilled adapter from Step 2
DISTILLED_LORA = os.path.join(
    KWYRE_HOME, "lora-adapters", f"{DOMAIN}-distilled-{_model_tag}"
)
OUTPUT_DIR = os.path.join(
    KWYRE_HOME, "adapters", f"{DOMAIN.replace('_', '-')}-{_model_tag}"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Hyperparameters ──────────────────────────────────────────────────────────
MAX_SEQ_LENGTH = 2048
LORA_RANK = 16
MAX_COMPLETION_LEN = 768
NUM_GENERATIONS = 2
BATCH_SIZE = 1
GRAD_ACCUM = 4
LEARNING_RATE = 5e-6

# Healthcare gets fewer steps (more conservative)
DOMAIN_STEPS = {
    "legal_compliance": 500,
    "insurance_actuarial": 500,
    "healthcare_lifesciences": 300,
    "defense_intelligence": 500,
    "financial_trading": 500,
    "blockchain_crypto": 500,
    "sports_analytics": 500,
    "relationship_matching": 500,
    "software_engineering": 500,
    "scientific_research": 500,
    "career_placement": 500,
    "college_basketball": 500,
    "dental_clinical": 400,
}
NUM_STEPS = DOMAIN_STEPS.get(DOMAIN, 500)

print(f"""
{'='*60}
  KWYRE — Domain GRPO: {DOMAIN}
  Base:       {BASE_MODEL}
  Distilled:  {DISTILLED_LORA if os.path.exists(DISTILLED_LORA) else '(not found, using base)'}
  Steps:      {NUM_STEPS}
  LoRA Rank:  {LORA_RANK}
  Output:     {OUTPUT_DIR}
{'='*60}
""")

# ── Step 1: Load model (Unsloth for 2x faster training + 60% less VRAM) ────
print("[1/4] Loading model with Unsloth...")
from unsloth import FastModel
from peft import PeftModel

# Start from distilled model if available
_load_model = BASE_MODEL

model, tokenizer = FastModel.from_pretrained(
    model_name=_load_model,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=True,
    full_finetuning=False,
)

if os.path.isdir(DISTILLED_LORA) and os.path.exists(
    os.path.join(DISTILLED_LORA, "adapter_config.json")
):
    print(f"  Loading distilled adapter from {DISTILLED_LORA}")
    model = PeftModel.from_pretrained(model, DISTILLED_LORA)
    model = model.merge_and_unload()
    print("  Distilled adapter merged.")
else:
    print(f"  No distilled adapter found, using base: {BASE_MODEL}")

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

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  Trainable: {trainable/1e6:.1f}M / {total/1e6:.1f}M ({100*trainable/total:.2f}%)")

# ── Step 2: Load dataset ────────────────────────────────────────────────────
print("[2/4] Loading GRPO dataset...")
from datasets import load_dataset

# Use GSM8K for math reasoning (universal) + domain traces for format
dataset = load_dataset("openai/gsm8k", "main", split="train[:500]")
print(f"  Loaded {len(dataset)} GSM8K problems for reasoning training")

SYSTEM_PROMPT = """You are Kwyre — a domain expert AI. For every problem:
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

# ── Step 3: Domain reward functions ─────────────────────────────────────────
print("[3/4] Setting up domain reward functions...")

def extract_answer(text):
    match = re.search(r"[Tt]he answer is\s*[\$\\]?\s*([-\d,\.]+)", text)
    if match:
        return match.group(1).replace(",", "")
    return None

def extract_gold_answer(text):
    match = re.search(r"####\s*([-\d,\.]+)", text)
    if match:
        return match.group(1).replace(",", "")
    return None

# Universal: correctness on math
def correctness_reward(completions, answer, **kwargs):
    rewards = []
    for completion, ans in zip(completions, answer):
        text = completion[0]["content"] if isinstance(completion, list) else completion
        pred = extract_answer(text)
        gold = extract_gold_answer(ans)
        if pred and gold:
            try:
                rewards.append(2.0 if abs(float(pred) - float(gold)) < 0.01 else 0.0)
            except ValueError:
                rewards.append(0.0)
        else:
            rewards.append(0.0)
    return rewards

# Universal: reasoning quality
def reasoning_reward(completions, **kwargs):
    rewards = []
    for completion in completions:
        text = completion[0]["content"] if isinstance(completion, list) else completion
        score = 0.0
        if "<think>" in text and "</think>" in text:
            think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
            if think_match:
                think_text = think_match.group(1)
                if len(think_text) > 100:
                    score += 0.3
                if any(w in think_text.lower() for w in ["step", "first", "therefore", "because", "since"]):
                    score += 0.3
                if re.search(r"\d", think_text):
                    score += 0.2
        if re.search(r"[Tt]he answer is", text):
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# ── Domain-specific reward functions ─────────────────────────────────────────

def legal_correctness_reward(completions, **kwargs):
    """Reward citations of specific legal authorities."""
    rewards = []
    legal_patterns = [
        r"(?:Section|§)\s*\d+",
        r"\d+\s+(?:U\.S\.C\.|C\.F\.R\.)",
        r"(?:FRE|FRCP|FINRA)\s+\d+",
        r"v\.\s+\w+",
    ]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        for pattern in legal_patterns:
            if re.search(pattern, text):
                score += 0.3
        score = min(score, 1.0)
        rewards.append(score)
    return rewards

def insurance_correctness_reward(completions, **kwargs):
    rewards = []
    terms = ["cedent", "retrocession", "IBNR", "loss development",
             "chain ladder", "RBC", "solvency", "cession", "layer"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.15, 0.6)
        if re.search(r"\d+\.?\d*%", text):
            score += 0.2
        if "<think>" in text and "</think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def healthcare_correctness_reward(completions, **kwargs):
    rewards = []
    compliance_terms = ["HIPAA", "21 CFR", "PHI", "BAA", "minimum necessary",
                        "de-identification", "IRB", "informed consent"]
    hedge_phrases = ["compliance analysis", "consult with", "verify with",
                     "subject to", "may require", "recommend reviewing"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in compliance_terms if t in text)
        score += min(term_count * 0.15, 0.5)
        hedge_count = sum(1 for h in hedge_phrases if h.lower() in text.lower())
        score += min(hedge_count * 0.1, 0.3)
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def defense_correctness_reward(completions, **kwargs):
    rewards = []
    structure_markers = ["confidence:", "source:", "assessment:", "alternative",
                        "assumption", "NIST", "CUI", "MITRE", "TTP"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        marker_count = sum(1 for m in structure_markers if m.lower() in text.lower())
        score += min(marker_count * 0.15, 0.6)
        if "<think>" in text:
            score += 0.2
        if any(w in text.lower() for w in ["low confidence", "moderate confidence", "high confidence"]):
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def trading_correctness_reward(completions, **kwargs):
    rewards = []
    quant_terms = ["VaR", "CVaR", "Sharpe", "alpha", "beta", "volatility",
                   "correlation", "cointegration", "mean reversion", "VWAP"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in quant_terms if t in text)
        score += min(term_count * 0.15, 0.5)
        if re.search(r"[\$€]\s*[\d,]+\.?\d*", text):
            score += 0.15
        if re.search(r"\d+\.?\d*[%σ]", text):
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def blockchain_correctness_reward(completions, **kwargs):
    rewards = []
    forensic_terms = ["wallet", "transaction", "hash", "on-chain", "off-chain",
                      "mixer", "bridge", "DEX", "CEX", "clustering", "trace"]
    legal_terms = ["RICO", "BSA", "AML", "SAR", "FinCEN", "wire fraud",
                   "chain of custody", "evidence"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        f_count = sum(1 for t in forensic_terms if t.lower() in text.lower())
        l_count = sum(1 for t in legal_terms if t in text)
        score += min(f_count * 0.1, 0.4)
        score += min(l_count * 0.1, 0.3)
        if re.search(r"0x[a-fA-F0-9]{6,}", text):
            score += 0.1
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def sports_correctness_reward(completions, **kwargs):
    """Reward use of NFL analytics terminology and statistical reasoning."""
    rewards = []
    terms = ["EPA", "DVOA", "formation", "personnel", "blitz", "coverage",
             "pre-snap", "route", "tendency", "win probability", "down and distance"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.12, 0.5)
        if re.search(r"\d+\.?\d*%", text):
            score += 0.15
        if any(w in text.lower() for w in ["11 personnel", "12 personnel", "21 personnel", "shotgun", "under center"]):
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def relationship_correctness_reward(completions, **kwargs):
    """Reward use of personality psychology and relationship science terminology."""
    rewards = []
    terms = ["Big Five", "OCEAN", "attachment", "love language", "compatibility",
             "openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
    hedge_phrases = ["research suggests", "evidence indicates", "studies show",
                     "individual differences", "context-dependent"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.12, 0.5)
        hedge_count = sum(1 for h in hedge_phrases if h.lower() in text.lower())
        score += min(hedge_count * 0.1, 0.3)
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def software_engineering_reward(completions, **kwargs):
    rewards = []
    terms = ["refactor", "SOLID", "dependency injection", "API", "REST", "microservice",
             "CI/CD", "test", "coverage", "security", "OWASP", "latency", "cache"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.1, 0.5)
        if re.search(r"```\w+\n", text):
            score += 0.15
        if any(w in text.lower() for w in ["o(n)", "o(1)", "time complexity", "space complexity"]):
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def scientific_research_reward(completions, **kwargs):
    rewards = []
    terms = ["hypothesis", "p-value", "confidence interval", "control group",
             "randomized", "peer-reviewed", "methodology", "reproducibility",
             "statistical significance", "effect size", "sample size"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.12, 0.5)
        if re.search(r"n\s*=\s*\d+", text, re.IGNORECASE):
            score += 0.1
        if any(w in text.lower() for w in ["limitation", "future work", "caveat"]):
            score += 0.2
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def career_placement_reward(completions, **kwargs):
    rewards = []
    terms = ["ATS", "resume", "quantify", "impact", "STAR", "behavioral",
             "compensation", "equity", "negotiation", "LinkedIn", "portfolio"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.12, 0.5)
        if re.search(r"\d+%|\$\d+[kKmM]?", text):
            score += 0.15
        if any(w in text.lower() for w in ["action verb", "metric", "achievement", "tailored"]):
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def college_basketball_reward(completions, **kwargs):
    rewards = []
    terms = ["KenPom", "AdjEM", "seed", "bracket", "upset", "tempo",
             "efficiency", "conference", "tournament", "March Madness",
             "Sweet 16", "Final Four", "selection committee"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.1, 0.5)
        if re.search(r"\d+\.?\d*%", text):
            score += 0.15
        if re.search(r"#?\d+\s+seed", text, re.IGNORECASE):
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

def dental_clinical_reward(completions, **kwargs):
    rewards = []
    terms = ["CDT", "treatment plan", "SOAP", "radiograph", "caries",
             "periodontal", "crown", "implant", "endodontic", "prophylaxis"]
    hedge_phrases = ["informed consent", "referral", "follow-up", "prognosis",
                     "differential diagnosis", "contraindication"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.12, 0.5)
        hedge_count = sum(1 for h in hedge_phrases if h.lower() in text.lower())
        score += min(hedge_count * 0.1, 0.3)
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# ── Domain-to-reward mapping ────────────────────────────────────────────────
DOMAIN_REWARDS = {
    "legal_compliance": [legal_correctness_reward, reasoning_reward],
    "insurance_actuarial": [insurance_correctness_reward, reasoning_reward],
    "healthcare_lifesciences": [healthcare_correctness_reward, reasoning_reward],
    "defense_intelligence": [defense_correctness_reward, reasoning_reward],
    "financial_trading": [trading_correctness_reward, reasoning_reward],
    "blockchain_crypto": [blockchain_correctness_reward, reasoning_reward],
    "sports_analytics": [sports_correctness_reward, reasoning_reward],
    "relationship_matching": [relationship_correctness_reward, reasoning_reward],
    "software_engineering": [software_engineering_reward, reasoning_reward],
    "scientific_research": [scientific_research_reward, reasoning_reward],
    "career_placement": [career_placement_reward, reasoning_reward],
    "college_basketball": [college_basketball_reward, reasoning_reward],
    "dental_clinical": [dental_clinical_reward, reasoning_reward],
}

reward_funcs = DOMAIN_REWARDS.get(DOMAIN, [correctness_reward, reasoning_reward])
print(f"  Reward functions: {[f.__name__ for f in reward_funcs]}")

# ── Step 4: Train ────────────────────────────────────────────────────────────
print(f"[4/4] Training GRPO — {NUM_STEPS} steps...")
from trl import GRPOConfig, GRPOTrainer

grpo_config = GRPOConfig(
    output_dir=OUTPUT_DIR,
    num_generations=NUM_GENERATIONS,
    max_completion_length=MAX_COMPLETION_LEN,
    per_device_train_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM,
    max_steps=NUM_STEPS,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_steps=10,
    fp16=False, bf16=True,
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
    reward_funcs=reward_funcs,
)

print(f"  VRAM: {torch.cuda.memory_allocated()/1e9:.1f} GB")
print(f"  Training {NUM_STEPS} GRPO steps for domain: {DOMAIN}")
print("  This will take 2-4 hours on H100.\n")

trainer.train()

# ── Save ─────────────────────────────────────────────────────────────────────
print("\nSaving domain GRPO adapter...")

# Save LoRA
lora_dir = os.path.join(KWYRE_HOME, "lora-adapters", f"{DOMAIN}-grpo-{_model_tag}")
model.save_pretrained(lora_dir)
tokenizer.save_pretrained(lora_dir)
print(f"  LoRA adapter: {lora_dir}")

# Merge and save as runtime adapter
print("  Merging LoRA into deployment adapter...")
merged = model.merge_and_unload()

runtime_dir = os.path.join(KWYRE_HOME, "adapters", DOMAIN.replace("_", "-"))
os.makedirs(runtime_dir, exist_ok=True)

# Save as PEFT adapter (not merged weights) for hot-swap
# Re-extract the adapter from the merged model
_fresh_lora = LoraConfig(r=LORA_RANK, lora_alpha=LORA_RANK,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0, bias="none", task_type="CAUSAL_LM")

# Instead, just copy the LoRA adapter files to runtime dir
import shutil
for fname in os.listdir(lora_dir):
    src = os.path.join(lora_dir, fname)
    dst = os.path.join(runtime_dir, fname)
    if os.path.isfile(src):
        shutil.copy2(src, dst)

# Write metadata
import json
metadata = {
    "domain": DOMAIN,
    "display_name": DOMAIN.replace("_", " ").title(),
    "version": "1.0.0",
    "base_model": BASE_MODEL,
    "lora_rank": LORA_RANK,
    "grpo_steps": NUM_STEPS,
    "stage": "grpo",
}
with open(os.path.join(runtime_dir, "metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print(f"""
{'='*60}
  DOMAIN GRPO COMPLETE!
  Domain:     {DOMAIN}
  Adapter:    {runtime_dir}

  To use:
    curl -X POST http://127.0.0.1:8000/v1/adapter/load \\
      -H "Authorization: Bearer sk-kwyre-dev-local" \\
      -d '{{"domain": "{DOMAIN.replace("_", "-")}"}}'
{'='*60}
""")
