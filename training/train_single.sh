#!/bin/bash
set -euo pipefail
cd /root/kwyre-ai
export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"

DOMAIN="$1"
echo "=== TRAINING: $DOMAIN ==="
echo "$(date)"

KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_distillation.py \
    2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-distill-v2.log"

KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_grpo_domain.py \
    2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-grpo-v2.log"

echo "=== DONE: $DOMAIN at $(date) ==="
