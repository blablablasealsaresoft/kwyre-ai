# ═══════════════════════════════════════════════════════════════════════════════
# serve_mlx.py — CONFIG SECTION REPLACEMENT
# Replace the MODEL_ID through KNOWN_WEIGHT_HASHES block with this.
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_ID = os.environ.get("KWYRE_MODEL", "Qwen/Qwen3.5-9B")
PORT = int(os.environ.get("KWYRE_MLX_PORT", "8000"))

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "vram_4bit": "~7.5GB", "tier": "professional"},
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": {"name": "kwyre-4b", "vram_4bit": "~4.1GB", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "vram_4bit": "unknown", "tier": "custom"})

# ---------------------------------------------------------------------------
# LAYER 4: Model weight integrity
# ---------------------------------------------------------------------------
WEIGHT_HASHES_9B: dict[str, str] = {
    "config.json": "d0883072e01861ed0b2d47be3c16c36a8e81c224c7ffaa310c6558fb3f932b05",
    "tokenizer_config.json": "316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8",
    "tokenizer.json": "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42",
}
# REGENERATE AFTER FIRST DOWNLOAD
WEIGHT_HASHES_4B: dict[str, str] = {}

KNOWN_WEIGHT_HASHES = WEIGHT_HASHES_9B if "9B" in MODEL_ID else WEIGHT_HASHES_4B
