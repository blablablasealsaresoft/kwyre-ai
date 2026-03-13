# ═══════════════════════════════════════════════════════════════════════════════
# model/train_qat.py — PATCHES
# 1. Replace the name_map in _resolve_model_path
# 2. Replace the default --model_id in parse_args
# ═══════════════════════════════════════════════════════════════════════════════

# In _resolve_model_path(), replace name_map:
    name_map = {
        "HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive": "kwyre-4b",
        "Qwen/Qwen3.5-9B": "kwyre-9b",
    }

# In parse_args(), replace --model_id default:
    p.add_argument("--model_id", type=str, default="Qwen/Qwen3.5-9B",
                    help="Model ID or path. QAT is designed for the 9B professional model. "
                         "Personal tier uses HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive.")
