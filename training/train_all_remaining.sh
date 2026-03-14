#!/bin/bash
################################################################################
# Train all remaining domains: 3 new + 6 originals (retrain with 5000 traces)
# Waits for GPU memory before starting each domain.
################################################################################
set -euo pipefail
cd /root/kwyre-ai
export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"

DOMAINS=(
    "college_basketball"
    "relationship_matching"
    "sports_analytics"
    "blockchain_crypto"
    "legal_compliance"
    "insurance_actuarial"
    "defense_intelligence"
    "financial_trading"
    "healthcare_lifesciences"
)

COMPLETED=0
TOTAL=${#DOMAINS[@]}

echo "========================================"
echo "  Training $TOTAL domains (3 new + 6 retrain)"
echo "  Each waits for GPU slot (<45GB used)"
echo "  $(date)"
echo "========================================"
echo ""

for DOMAIN in "${DOMAINS[@]}"; do
    echo "[$(date +%H:%M)] Waiting for GPU slot for $DOMAIN... ($((COMPLETED+1))/$TOTAL)"

    while true; do
        USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null || echo 99999)
        if [ "$USED" -lt 45000 ]; then
            break
        fi
        sleep 60
    done

    echo ""
    echo "========================================"
    echo "  [$((COMPLETED+1))/$TOTAL] TRAINING: $DOMAIN"
    echo "  GPU: ${USED}MB used"
    echo "  $(date)"
    echo "========================================"

    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_distillation.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-distill-v3.log"

    KWYRE_DOMAIN="$DOMAIN" python3 training/scripts/train_grpo_domain.py \
        2>&1 | tee "$HOME/.kwyre/logs/${DOMAIN}-grpo-v3.log"

    COMPLETED=$((COMPLETED + 1))
    echo "  DONE: $DOMAIN ($COMPLETED/$TOTAL complete)"
    echo ""
done

echo ""
echo "========================================"
echo "  ALL $TOTAL DOMAINS COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Adapters:"
du -sh ~/.kwyre/adapters/*/ 2>/dev/null
