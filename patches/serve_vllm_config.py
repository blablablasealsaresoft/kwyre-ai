# ═══════════════════════════════════════════════════════════════════════════════
# serve_vllm.py — CONFIG SECTION REPLACEMENT
# Replace the MODEL_ID through LOCAL_MODEL_PATH block with this.
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_ID = os.environ.get("KWYRE_MODEL", "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive")
PORT = int(os.environ.get("KWYRE_PORT", "8000"))
GPU_MEMORY_FRACTION = float(os.environ.get("KWYRE_VLLM_GPU_MEMORY", "0.85"))
MAX_MODEL_LEN = int(os.environ.get("KWYRE_VLLM_MAX_MODEL_LEN", "8192"))
TENSOR_PARALLEL = int(os.environ.get("KWYRE_VLLM_TENSOR_PARALLEL", "1"))
SPECULATIVE_ENABLED = os.environ.get("KWYRE_SPECULATIVE", "1") == "1"
DRAFT_MODEL_ID = os.environ.get("KWYRE_DRAFT_MODEL", "Qwen/Qwen3.5-0.8B")

MODEL_TIERS = {
    "Qwen/Qwen3.5-9B": {"name": "kwyre-9b", "tier": "professional"},
    "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": {"name": "kwyre-4b", "tier": "personal"},
}
ACTIVE_TIER = MODEL_TIERS.get(MODEL_ID, {"name": "kwyre-custom", "tier": "custom"})
