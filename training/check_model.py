#!/usr/bin/env python3
"""Check if the base model is available and test Unsloth loading."""
import os
os.environ["HF_HUB_OFFLINE"] = "0"

model_name = os.environ.get("KWYRE_BASE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
print(f"Checking model: {model_name}")

try:
    from huggingface_hub import model_info
    info = model_info(model_name)
    print(f"  HuggingFace: FOUND ({info.id})")
except Exception as e:
    print(f"  HuggingFace: NOT FOUND ({e})")
    print("  Trying Qwen/Qwen3.5-4B as fallback...")
    model_name = "Qwen/Qwen3.5-4B"
    try:
        info = model_info(model_name)
        print(f"  Fallback: FOUND ({info.id})")
    except Exception as e2:
        print(f"  Fallback also failed: {e2}")

try:
    from unsloth import FastModel
    print(f"\n  Testing Unsloth load of {model_name}...")
    model, tokenizer = FastModel.from_pretrained(
        model_name=model_name,
        max_seq_length=2048,
        load_in_4bit=True,
        full_finetuning=False,
    )
    print(f"  Unsloth: LOADED ({sum(p.numel() for p in model.parameters())/1e9:.1f}B params)")
    del model, tokenizer
    import torch
    torch.cuda.empty_cache()
except Exception as e:
    print(f"  Unsloth load FAILED: {e}")
