#!/bin/bash
set -euo pipefail
cd /root/kwyre-ai
export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"

DOMAINS=("legal_compliance" "insurance_actuarial" "defense_intelligence" "financial_trading" "healthcare_lifesciences")

echo "Queuing ${#DOMAINS[@]} domains (wait for GPU slots)"

for DOMAIN in "${DOMAINS[@]}"; do
    while true; do
        USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null || echo 99999)
        if [ "$USED" -lt 45000 ]; then
            break
        fi
        sleep 60
    done
    echo "=== TRAINING: $DOMAIN (GPU at ${USED}MB) ==="
    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_distillation.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-distill-v3.log"
    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_grpo_domain.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-grpo-v3.log"
    echo "=== DONE: $DOMAIN ==="
done
echo "ALL 5 REMAINING DOMAINS COMPLETE"
