#!/usr/bin/env bash
set -euo pipefail

shutdown() {
    echo "[entrypoint] SIGTERM received — shutting down…"
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null
    exit 0
}
trap shutdown SIGTERM SIGINT

# Supported tiers:
#   Personal:     HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive  (~4.1 GB VRAM, 7-14 tok/s)
#   Professional: Qwen/Qwen3.5-9B                                      (~7.5 GB VRAM, 3-5 tok/s)
MODEL="${KWYRE_MODEL:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}"
DRAFT="${KWYRE_DRAFT_MODEL:-Qwen/Qwen3.5-0.8B}"
SPEC="${KWYRE_SPECULATIVE:-1}"
CACHE="${HF_HOME:-/workspace/.cache/huggingface}"

download_model() {
    local model_id="$1"
    local dir="${CACHE}/hub/models--${model_id//\//--}"
    if [ -d "$dir" ]; then
        echo "[entrypoint] ${model_id} cache found — skipping download."
    else
        echo "[entrypoint] Downloading ${model_id}…"
        unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE 2>/dev/null || true
        python -c "from huggingface_hub import snapshot_download; snapshot_download('${model_id}')"
        echo "[entrypoint] ${model_id} download complete."
    fi
}

download_model "$MODEL"

if [ "$SPEC" = "1" ]; then
    download_model "$DRAFT"
fi

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "[entrypoint] Starting Kwyre inference server…"
exec "$@" &
SERVER_PID=$!
wait "$SERVER_PID"
