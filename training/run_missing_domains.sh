#!/bin/bash
set -euo pipefail
cd /root/kwyre-ai
export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"

DOMAINS=("software_engineering" "scientific_research" "career_placement" "dental_clinical" "college_basketball" "relationship_matching" "sports_analytics")
SCRIPT_DIR="/root/kwyre-ai/training/scripts"
LOG_DIR="$HOME/.kwyre/logs"

echo "Training ${#DOMAINS[@]} missing domains with Qwen/Qwen3.5-4B"
echo ""

for d in "${DOMAINS[@]}"; do
    echo "========================================"
    echo "  TRAINING: $d"
    echo "  $(date)"
    echo "========================================"

    KWYRE_DOMAIN="$d" python3 "$SCRIPT_DIR/train_distillation.py" 2>&1 | tee "$LOG_DIR/${d}-distill-v2.log"
    KWYRE_DOMAIN="$d" python3 "$SCRIPT_DIR/train_grpo_domain.py" 2>&1 | tee "$LOG_DIR/${d}-grpo-v2.log"

    echo "  DONE: $d at $(date)"
    echo ""
done

echo "ALL 7 MISSING DOMAINS COMPLETE"
