#!/bin/bash
################################################################################
# KWYRE AI — Launch Parallel Domain Training (run ON the H100 server)
#
# Splits 13 domains across 3 tmux sessions for parallel GPU training.
# Run AFTER trace generation is complete.
#
# NOTE: With a single GPU, only one training job runs at a time.
# The 3 sessions queue their domains so if you have multiple GPUs
# (CUDA_VISIBLE_DEVICES), each session can target a different GPU.
# With 1 GPU, use the sequential train_all_products.sh instead.
#
# Usage (on the H100 server):
#   bash training/launch_parallel_training.sh
################################################################################
set -euo pipefail

cd /root/kwyre-ai

export KWYRE_BASE_MODEL="${KWYRE_BASE_MODEL:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}"
export KWYRE_TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-5000}"
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)/scripts"

# Check traces exist
TRACE_DIR="$HOME/.kwyre/training-data/kwyre-traces"
TRACE_COUNT=$(ls "$TRACE_DIR"/*.jsonl 2>/dev/null | wc -l)
if [ "$TRACE_COUNT" -lt 10 ]; then
    echo "ERROR: Only $TRACE_COUNT trace files found in $TRACE_DIR"
    echo "  Run generate_traces_batch.py first to generate traces for all 13 domains."
    exit 1
fi
echo "Found $TRACE_COUNT domain trace files. Starting training..."
echo ""

# Kill existing sessions
tmux kill-session -t kwyre-train-a 2>/dev/null || true
tmux kill-session -t kwyre-train-b 2>/dev/null || true
tmux kill-session -t kwyre-train-c 2>/dev/null || true

# Group A: 5 domains (product-critical first)
tmux new-session -d -s kwyre-train-a -x 200 -y 50
tmux send-keys -t kwyre-train-a "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='$KWYRE_BASE_MODEL' && for d in financial_trading software_engineering scientific_research dental_clinical legal_compliance; do echo '=== Training: '\$d' ===' && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_distillation.py && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_grpo_domain.py && echo '=== Done: '\$d' ==='; done && echo 'GROUP A COMPLETE'" C-m

# Group B: 4 domains
tmux new-session -d -s kwyre-train-b -x 200 -y 50
tmux send-keys -t kwyre-train-b "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='$KWYRE_BASE_MODEL' && for d in career_placement relationship_matching sports_analytics college_basketball; do echo '=== Training: '\$d' ===' && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_distillation.py && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_grpo_domain.py && echo '=== Done: '\$d' ==='; done && echo 'GROUP B COMPLETE'" C-m

# Group C: 4 domains
tmux new-session -d -s kwyre-train-c -x 200 -y 50
tmux send-keys -t kwyre-train-c "cd /root/kwyre-ai && export PYTHONUNBUFFERED=1 && export KWYRE_BASE_MODEL='$KWYRE_BASE_MODEL' && for d in insurance_actuarial healthcare_lifesciences defense_intelligence blockchain_crypto; do echo '=== Training: '\$d' ===' && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_distillation.py && KWYRE_DOMAIN=\$d python3 $SCRIPT_DIR/train_grpo_domain.py && echo '=== Done: '\$d' ==='; done && echo 'GROUP C COMPLETE'" C-m

echo "========================================"
echo "  3 Training Sessions Launched"
echo "========================================"
echo ""
echo "  Group A (5 domains): financial_trading, software_engineering,"
echo "                        scientific_research, dental_clinical, legal_compliance"
echo "  Group B (4 domains): career_placement, relationship_matching,"
echo "                        sports_analytics, college_basketball"
echo "  Group C (4 domains): insurance_actuarial, healthcare_lifesciences,"
echo "                        defense_intelligence, blockchain_crypto"
echo ""
echo "  Monitor:"
echo "    tmux attach -t kwyre-train-a"
echo "    tmux attach -t kwyre-train-b"
echo "    tmux attach -t kwyre-train-c"
echo ""
echo "  NOTE: With 1 GPU, only 1 session trains at a time (GPU contention)."
echo "  For true parallelism, assign GPUs: CUDA_VISIBLE_DEVICES=0,1,2"
echo ""
echo "  When done, copy adapters:"
echo "    rsync -avz ~/.kwyre/adapters/ user@local:~/.kwyre/adapters/"
echo ""
