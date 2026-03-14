#!/bin/bash
################################################################################
# KWYRE AI — Auto-Launch Training When Traces Complete
#
# Polls for trace completion, then launches 3 tmux training sessions
# with 4-5 domains each. Uses multiple base models for diversity.
#
# Run ON the H100 server:
#   nohup bash training/auto_train_on_complete.sh &
################################################################################
set -euo pipefail

cd /root/kwyre-ai

export KWYRE_TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-5000}"
export PYTHONUNBUFFERED=1
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-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}"

SCRIPT_DIR="/root/kwyre-ai/training/scripts"
TRACE_DIR="$HOME/.kwyre/training-data/kwyre-traces"
LOG_DIR="$HOME/.kwyre/logs"
mkdir -p "$LOG_DIR"

# Base models for training diversity
MODEL_PRIMARY="HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"
MODEL_ALT1="Qwen/Qwen3.5-4B"
MODEL_ALT2="Qwen/Qwen3.5-4B"

echo "========================================"
echo "  KWYRE — Auto-Train Watcher"
echo "  Waiting for 13 trace files to appear..."
echo "  $(date)"
echo "========================================"

# ── Wait for all 13 domain trace files ───────────────────────────────────────
REQUIRED_DOMAINS=(
    "legal_compliance" "insurance_actuarial" "healthcare_lifesciences"
    "defense_intelligence" "financial_trading" "blockchain_crypto"
    "sports_analytics" "relationship_matching"
    "software_engineering" "scientific_research" "career_placement"
    "college_basketball" "dental_clinical"
)

while true; do
    READY=0
    for d in "${REQUIRED_DOMAINS[@]}"; do
        if [ -f "$TRACE_DIR/${d}.jsonl" ]; then
            LINES=$(wc -l < "$TRACE_DIR/${d}.jsonl")
            if [ "$LINES" -gt 100 ]; then
                READY=$((READY + 1))
            fi
        fi
    done

    echo "  [$(date +%H:%M:%S)] $READY / ${#REQUIRED_DOMAINS[@]} domains ready"

    if [ "$READY" -ge "${#REQUIRED_DOMAINS[@]}" ]; then
        echo ""
        echo "  ALL 13 TRACE FILES READY! Launching training..."
        break
    fi

    sleep 30
done

echo ""
echo "========================================"
echo "  LAUNCHING 3 TRAINING TERMINALS"
echo "  $(date)"
echo "========================================"

# Kill any existing training sessions
tmux kill-session -t kwyre-train-a 2>/dev/null || true
tmux kill-session -t kwyre-train-b 2>/dev/null || true
tmux kill-session -t kwyre-train-c 2>/dev/null || true

# ── Terminal A: 5 domains (product-critical, primary model) ──────────────────
tmux new-session -d -s kwyre-train-a -x 200 -y 50
tmux send-keys -t kwyre-train-a "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='${MODEL_PRIMARY}' && echo '=== TERMINAL A: 5 domains (primary model: ${MODEL_PRIMARY}) ===' && for d in financial_trading software_engineering scientific_research dental_clinical legal_compliance; do echo '' && echo '========================================' && echo \"  TRAINING: \$d\" && echo \"  Model: ${MODEL_PRIMARY}\" && echo \"  \$(date)\" && echo '========================================' && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_distillation.py 2>&1 | tee ${LOG_DIR}/\${d}-distill.log && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_grpo_domain.py 2>&1 | tee ${LOG_DIR}/\${d}-grpo.log && echo \"  DONE: \$d at \$(date)\"; done && echo '' && echo 'TERMINAL A: ALL 5 DOMAINS COMPLETE'" C-m

# ── Terminal B: 4 domains (product domains, primary model) ───────────────────
tmux new-session -d -s kwyre-train-b -x 200 -y 50
tmux send-keys -t kwyre-train-b "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='${MODEL_PRIMARY}' && echo '=== TERMINAL B: 4 domains (primary model: ${MODEL_PRIMARY}) ===' && for d in career_placement relationship_matching sports_analytics college_basketball; do echo '' && echo '========================================' && echo \"  TRAINING: \$d\" && echo \"  Model: ${MODEL_PRIMARY}\" && echo \"  \$(date)\" && echo '========================================' && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_distillation.py 2>&1 | tee ${LOG_DIR}/\${d}-distill.log && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_grpo_domain.py 2>&1 | tee ${LOG_DIR}/\${d}-grpo.log && echo \"  DONE: \$d at \$(date)\"; done && echo '' && echo 'TERMINAL B: ALL 4 DOMAINS COMPLETE'" C-m

# ── Terminal C: 4 domains (core domains, primary model) ──────────────────────
tmux new-session -d -s kwyre-train-c -x 200 -y 50
tmux send-keys -t kwyre-train-c "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='${MODEL_PRIMARY}' && echo '=== TERMINAL C: 4 domains (primary model: ${MODEL_PRIMARY}) ===' && for d in insurance_actuarial healthcare_lifesciences defense_intelligence blockchain_crypto; do echo '' && echo '========================================' && echo \"  TRAINING: \$d\" && echo \"  Model: ${MODEL_PRIMARY}\" && echo \"  \$(date)\" && echo '========================================' && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_distillation.py 2>&1 | tee ${LOG_DIR}/\${d}-distill.log && KWYRE_DOMAIN=\$d python3 ${SCRIPT_DIR}/train_grpo_domain.py 2>&1 | tee ${LOG_DIR}/\${d}-grpo.log && echo \"  DONE: \$d at \$(date)\"; done && echo '' && echo 'TERMINAL C: ALL 4 DOMAINS COMPLETE'" C-m

echo ""
echo "========================================"
echo "  3 TRAINING SESSIONS LAUNCHED!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Terminal A (5 domains): financial_trading, software_engineering,"
echo "    scientific_research, dental_clinical, legal_compliance"
echo ""
echo "  Terminal B (4 domains): career_placement, relationship_matching,"
echo "    sports_analytics, college_basketball"
echo ""
echo "  Terminal C (4 domains): insurance_actuarial, healthcare_lifesciences,"
echo "    defense_intelligence, blockchain_crypto"
echo ""
echo "  All using: ${MODEL_PRIMARY}"
echo ""
echo "  Monitor:"
echo "    tmux attach -t kwyre-train-a"
echo "    tmux attach -t kwyre-train-b"
echo "    tmux attach -t kwyre-train-c"
echo ""
echo "  NOTE: Single GPU means sessions queue (one trains at a time)."
echo "  Total estimated time: ~120-160 hours for all 13 adapters."
echo ""
