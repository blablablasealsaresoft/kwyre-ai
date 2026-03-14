"""
Kwyre AI — Customer Adapter Fine-Tuner
=======================================
Accepts customer-provided training examples and fine-tunes a domain-specific
LoRA adapter on top of an existing domain adapter (or the base model).

This runs as a background job so the main inference server is not blocked.

Usage (standalone):
    python server/adapter_trainer.py --domain legal_compliance --data examples.jsonl

API (called from serve_local_4bit.py adapter routes):
    POST /v1/adapter/train
    Body: {"domain": "legal_compliance", "examples": [...], "base_adapter": "legal_compliance", "epochs": 1}
    Returns: {"job_id": "...", "status": "queued"}

    GET /v1/adapter/train/<job_id>
    Returns: {"job_id": "...", "status": "running|complete|failed", "progress": 0.0-1.0, "output_path": "..."}
"""

import os
import json
import time
import uuid
import threading
import argparse

KWYRE_HOME = os.path.expanduser("~/.kwyre")
ADAPTER_DIR = os.environ.get("KWYRE_ADAPTER_DIR", os.path.join(KWYRE_HOME, "adapters"))
CUSTOM_ADAPTER_DIR = os.environ.get("KWYRE_CUSTOM_ADAPTER_DIR", os.path.join(KWYRE_HOME, "custom-adapters"))
os.makedirs(CUSTOM_ADAPTER_DIR, exist_ok=True)

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _update_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get_job_status(job_id: str) -> dict | None:
    with _jobs_lock:
        return dict(_jobs.get(job_id, {})) if job_id in _jobs else None


def _run_finetune(job_id: str, domain: str, examples: list, base_adapter: str | None,
                  epochs: int, base_model_id: str):
    """Background thread: fine-tune a LoRA adapter on customer examples."""
    _update_job(job_id, status="running", progress=0.0, started_at=time.time())
    output_path = os.path.join(CUSTOM_ADAPTER_DIR, f"{domain}-custom-{job_id[:8]}")

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, get_peft_model, PeftModel, TaskType
        from torch.utils.data import Dataset, DataLoader

        _update_job(job_id, progress=0.05, status_detail="Loading base model...")

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

        tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            trust_remote_code=True,
            quantization_config=quant_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
        )

        _update_job(job_id, progress=0.15, status_detail="Applying base adapter...")

        # Load base domain adapter if specified
        if base_adapter:
            base_adapter_path = os.path.join(ADAPTER_DIR, base_adapter)
            if os.path.isdir(base_adapter_path):
                model = PeftModel.from_pretrained(model, base_adapter_path)
                model = model.merge_and_unload()

        # Add new LoRA for customer fine-tuning
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=16,
            lora_alpha=32,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
            lora_dropout=0.05,
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        _update_job(job_id, progress=0.25, status_detail="Preparing training data...")

        class ExampleDataset(Dataset):
            def __init__(self, examples, tokenizer, max_length=2048):
                self.items = []
                for ex in examples:
                    if isinstance(ex, dict) and "messages" in ex:
                        text = tokenizer.apply_chat_template(
                            ex["messages"], tokenize=False, add_generation_prompt=False
                        )
                    elif isinstance(ex, dict) and "text" in ex:
                        text = ex["text"]
                    else:
                        text = str(ex)
                    enc = tokenizer(text, truncation=True, max_length=max_length,
                                    return_tensors="pt")
                    self.items.append({k: v.squeeze(0) for k, v in enc.items()})

            def __len__(self): return len(self.items)
            def __getitem__(self, i): return self.items[i]

        dataset = ExampleDataset(examples, tokenizer)

        def collate_fn(batch):
            input_ids = torch.nn.utils.rnn.pad_sequence(
                [b["input_ids"] for b in batch], batch_first=True,
                padding_value=tokenizer.pad_token_id
            )
            attention_mask = torch.nn.utils.rnn.pad_sequence(
                [b["attention_mask"] for b in batch], batch_first=True, padding_value=0
            )
            return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": input_ids.clone()}

        loader = DataLoader(dataset, batch_size=1, shuffle=True, collate_fn=collate_fn)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-4)
        model.train()

        total_steps = len(loader) * epochs
        step = 0

        _update_job(job_id, progress=0.30, status_detail="Training...")

        for epoch in range(epochs):
            for batch in loader:
                batch = {k: v.to(model.device) for k, v in batch.items()}
                outputs = model(**batch)
                loss = outputs.loss
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()
                step += 1
                progress = 0.30 + (step / total_steps) * 0.60
                _update_job(job_id, progress=round(progress, 2),
                            status_detail=f"Epoch {epoch+1}/{epochs}, step {step}/{total_steps}, loss={loss.item():.4f}")

        _update_job(job_id, progress=0.90, status_detail="Saving adapter...")

        os.makedirs(output_path, exist_ok=True)
        model.save_pretrained(output_path)
        tokenizer.save_pretrained(output_path)

        # Write metadata
        metadata = {
            "domain": f"{domain}-custom",
            "display_name": f"{domain.replace('_', ' ').title()} (Custom)",
            "version": "1.0.0",
            "base_adapter": base_adapter,
            "base_model": base_model_id,
            "training_examples": len(examples),
            "epochs": epochs,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(os.path.join(output_path, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        _update_job(job_id, status="complete", progress=1.0,
                    output_path=output_path, completed_at=time.time(),
                    status_detail="Done")

    except Exception as e:
        _update_job(job_id, status="failed", error=str(e), completed_at=time.time())
        raise


def submit_finetune_job(domain: str, examples: list, base_adapter: str | None = None,
                        epochs: int = 1, base_model_id: str | None = None) -> str:
    """Submit a fine-tuning job. Returns job_id."""
    if not base_model_id:
        base_model_id = os.environ.get(
            "KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"
        )

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "domain": domain,
            "status": "queued",
            "progress": 0.0,
            "examples": len(examples),
            "epochs": epochs,
            "base_adapter": base_adapter,
            "queued_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_finetune,
        args=(job_id, domain, examples, base_adapter, epochs, base_model_id),
        daemon=True,
    )
    thread.start()
    return job_id


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kwyre customer adapter fine-tuner")
    parser.add_argument("--domain", required=True, help="Domain name (e.g. legal_compliance)")
    parser.add_argument("--data", required=True, help="Path to JSONL training data")
    parser.add_argument("--base-adapter", default=None, help="Base domain adapter to build on")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--model", default=None, help="Override base model ID")
    args = parser.parse_args()

    with open(args.data) as f:
        examples = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(examples)} examples for domain '{args.domain}'")
    job_id = submit_finetune_job(
        domain=args.domain,
        examples=examples,
        base_adapter=args.base_adapter,
        epochs=args.epochs,
        base_model_id=args.model,
    )
    print(f"Job submitted: {job_id}")

    # Poll until done
    while True:
        status = get_job_status(job_id)
        print(f"  [{status['progress']*100:.0f}%] {status['status']} — {status.get('status_detail', '')}")
        if status["status"] in ("complete", "failed"):
            if status["status"] == "complete":
                print(f"Adapter saved to: {status['output_path']}")
            else:
                print(f"Error: {status.get('error')}")
            break
        time.sleep(5)
