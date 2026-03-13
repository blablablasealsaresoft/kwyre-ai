# Kwyre AI — Model Migration Quick Reference
# Qwen3 → Qwen3.5 (Uncensored)

## New Model Stack

| Role | Old ID | New ID |
|------|--------|--------|
| Base (Personal) | `Qwen/Qwen3.5-4B` | `HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive` |
| Draft (speculative) | `Qwen/Qwen3.5-0.8B` | `Qwen/Qwen3.5-0.8B` |
| Draft (GGUF/Air) | (self-converted) | `unsloth/Qwen3.5-0.8B-GGUF` (pre-built) |
| Professional | `Qwen/Qwen3.5-9B` | `Qwen/Qwen3.5-9B` (unchanged) |

## Files in This Package

```
output/
├── .env.example                          # Updated env config (drop-in replacement)
├── migrate_models.sh                     # Automated sed-based migration script
├── docker/
│   └── entrypoint.sh                     # Updated Docker entrypoint
├── patches/
│   ├── serve_local_4bit_config.py        # Config block for serve_local_4bit.py
│   ├── serve_vllm_config.py              # Config block for serve_vllm.py
│   ├── serve_mlx_config.py               # Config block for serve_mlx.py
│   ├── quantize_nf4_docstring.py         # Docstring for model/quantize_nf4.py
│   ├── gguf_awq_patches.py              # Patches for convert_gguf.py + quantize_awq.py
│   └── train_qat_patches.py             # Patches for model/train_qat.py
└── training/
    └── scripts/
        ├── train_distillation.py         # Domain-aware distillation (full replacement)
        ├── train_grpo_domain.py          # Domain-specific GRPO (new file)
        ├── run_domain_training.sh        # Single-domain pipeline runner (new file)
        └── run_all_domains.sh            # All 6 domains sequentially (new file)
```

## How to Apply

### Option A: Automated (recommended)
```bash
cd /path/to/kwyre-ai
bash migrate_models.sh
```
Then manually apply the training scripts and weight hash regeneration.

### Option B: Manual
1. Replace `.env.example` with the new one
2. In `serve_local_4bit.py`, replace the config block (MODEL_ID through KNOWN_WEIGHT_HASHES)
   with the content from `patches/serve_local_4bit_config.py`
3. Same for `serve_vllm.py` and `serve_mlx.py`
4. Replace `docker/entrypoint.sh`
5. Update docstrings in `model/quantize_nf4.py` and `model/convert_gguf.py`
6. Update `model/quantize_awq.py` DEFAULT_MODEL_ID and _TIER_NAMES
7. Update `model/train_qat.py` name_map and default model_id
8. Copy new training scripts to `training/scripts/`

### After First Model Download
```bash
# Download the new model
huggingface-cli download HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive

# Generate new weight hashes
python3 -c "
import hashlib, os, json
model_path = os.path.expanduser('~/.cache/huggingface/hub/models--HauhauCS--Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/snapshots/')
snap = os.listdir(model_path)[0]
full_path = os.path.join(model_path, snap)
hashes = {}
for f in ['config.json', 'tokenizer_config.json', 'tokenizer.json']:
    fp = os.path.join(full_path, f)
    if os.path.exists(fp):
        with open(fp, 'rb') as fh:
            hashes[f] = hashlib.sha256(fh.read()).hexdigest()
print(json.dumps(hashes, indent=2))
"

# Paste the output into WEIGHT_HASHES_4B in:
#   - server/serve_local_4bit.py
#   - server/serve_mlx.py
```

### Pre-Quantize for Distribution
```bash
# Base model (Personal tier)
python model/quantize_nf4.py \
  --model HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive \
  --output ./dist/kwyre-4b-nf4

# Draft model
python model/quantize_nf4.py \
  --model Qwen/Qwen3.5-0.8B \
  --output ./dist/kwyre-draft-nf4
```

### Train Domain Adapters
```bash
# Single domain
export ANTHROPIC_API_KEY=sk-ant-...
KWYRE_DOMAIN=blockchain_crypto bash training/scripts/run_domain_training.sh

# All 6 domains
bash training/scripts/run_all_domains.sh
```
