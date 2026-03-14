#!/bin/bash
################################################################################
# Train a pair of domains in parallel on a single GPU.
# Each distillation+GRPO uses ~28GB, so 2 fit on an 80GB H100.
#
# Usage:
#   PAIR=1 bash training/run_parallel_pair.sh  # domains 1-2
#   PAIR=2 bash training/run_parallel_pair.sh  # domains 3-4
#   PAIR=3 bash training/run_parallel_pair.sh  # domains 5-6
#   PAIR=4 bash training/run_parallel_pair.sh  # domain 7
################################################################################
set -euo pipefail
cd /root/kwyre-ai

export PYTHONUNBUFFERED=1
export KWYRE_BASE_MODEL="Qwen/Qwen3.5-4B"
SCRIPT_DIR="/root/kwyre-ai/training/scripts"
LOG_DIR="$HOME/.kwyre/logs"

ALL_DOMAINS=(
    "software_engineering"
    "scientific_research"
    "career_placement"
    "dental_clinical"
    "college_basketball"
    "relationship_matching"
    "sports_analytics"
)

PAIR="${PAIR:-1}"

case $PAIR in
    1) DOMAINS=("${ALL_DOMAINS[0]}" "${ALL_DOMAINS[1]}") ;;
    2) DOMAINS=("${ALL_DOMAINS[2]}" "${ALL_DOMAINS[3]}") ;;
    3) DOMAINS=("${ALL_DOMAINS[4]}" "${ALL_DOMAINS[5]}") ;;
    4) DOMAINS=("${ALL_DOMAINS[6]}") ;;
    *) echo "Invalid PAIR=$PAIR"; exit 1 ;;
esac

train_domain() {
    local domain=$1
    echo "[$(date +%H:%M:%S)] Starting: $domain"
    KWYRE_DOMAIN="$domain" python3 "$SCRIPT_DIR/train_distillation.py" \
        2>&1 | tee "$LOG_DIR/${domain}-distill-v2.log"
    KWYRE_DOMAIN="$domain" python3 "$SCRIPT_DIR/train_grpo_domain.py" \
        2>&1 | tee "$LOG_DIR/${domain}-grpo-v2.log"
    echo "[$(date +%H:%M:%S)] Complete: $domain"
}

echo "========================================"
echo "  Pair $PAIR: ${DOMAINS[*]}"
echo "  $(date)"
echo "========================================"

if [ ${#DOMAINS[@]} -eq 2 ]; then
    train_domain "${DOMAINS[0]}" &
    PID1=$!
    sleep 30
    train_domain "${DOMAINS[1]}" &
    PID2=$!
    wait $PID1 $PID2
elif [ ${#DOMAINS[@]} -eq 1 ]; then
    train_domain "${DOMAINS[0]}"
fi

echo "========================================"
echo "  Pair $PAIR COMPLETE"
echo "  $(date)"
echo "========================================"
