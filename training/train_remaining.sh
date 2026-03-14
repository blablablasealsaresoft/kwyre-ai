#!/bin/bash
set -euo pipefail
cd /root/kwyre-ai
export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"

echo "Waiting for a training slot to free up..."
echo "Will train: college_basketball, relationship_matching, sports_analytics"
echo ""

for DOMAIN in college_basketball relationship_matching sports_analytics; do
    echo "=== Waiting for GPU memory before starting $DOMAIN ==="
    while true; do
        USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
        if [ "$USED" -lt 45000 ]; then
            echo "  GPU memory OK (${USED}MB used). Starting $DOMAIN..."
            break
        fi
        echo "  [$(date +%H:%M)] GPU at ${USED}MB, waiting..."
        sleep 60
    done

    echo "=== TRAINING: $DOMAIN ==="
    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_distillation.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-distill-v2.log"
    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_grpo_domain.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-grpo-v2.log"
    echo "=== DONE: $DOMAIN at $(date) ==="
    echo ""
done

echo "ALL REMAINING DOMAINS COMPLETE"
