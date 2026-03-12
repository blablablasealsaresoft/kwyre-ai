# ═══════════════════════════════════════════════════════════════════════════════
# serve_local_4bit.py — CONFIG SECTION REPLACEMENT
# Replace the MODEL_ID through KNOWN_WEIGHT_HASHES block with this.
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_ID = os.environ.get("KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
PORT = 8000
SPIKE_K = 5.0
SPIKE_MAX = 31

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": {"name": "kwyre-4b", "vram_4bit": "~4.1GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})

SPECULATIVE_ENABLED = os.environ.get("KWYRE_SPECULATIVE", "1") == "1"
DRAFT_MODEL_ID = os.environ.get("KWYRE_DRAFT_MODEL", "Qwen/Qwen3.5-0.8B")

draft_model = None

QAT_ADAPTER_PATH = os.environ.get(
    "KWYRE_QAT_ADAPTER",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "qat_output_v1", "final"),
)

KWYRE_QUANT = os.environ.get("KWYRE_QUANT", "nf4").lower()
_awq_env_path = os.environ.get("KWYRE_AWQ_MODEL_PATH", "")
_awq_default_path = os.path.join(_project_root, "models", f"{ACTIVE_TIER['name']}-awq")
if _awq_env_path and os.path.isdir(_awq_env_path):
    AWQ_MODEL_PATH = _awq_env_path
else:
    AWQ_MODEL_PATH = _awq_default_path

# ---------------------------------------------------------------------------
# LAYER 4: Model weight integrity
# ---------------------------------------------------------------------------
WEIGHT_HASHES_9B: dict[str, str] = {
    "config.json": "d0883072e01861ed0b2d47be3c16c36a8e81c224c7ffaa310c6558fb3f932b05",
    "tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
    "tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
}
# NOTE: These hashes must be regenerated after downloading the new model.
# Run: python -c "from serve_local_4bit import generate_weight_hashes; print(generate_weight_hashes('<path>'))"
WEIGHT_HASHES_4B: dict[str, str] = {
    # REGENERATE AFTER FIRST DOWNLOAD of HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive
    # Old Qwen3-4B hashes (DO NOT USE — architecture mismatch):
    # "config.json": "2f48fc86f9a91c0c1646a91ad8b2304443404e595ef02dfbeb0fb0ba11c519c0",
}

KNOWN_WEIGHT_HASHES = WEIGHT_HASHES_9B if "9B" in MODEL_ID else WEIGHT_HASHES_4B
