#!/bin/bash
################################################################################
# KWYRE AI — Deploy to H100 and Launch Product Training
#
# Syncs code to the H100 server, then launches the full 13-domain
# product training pipeline in parallel sessions using tmux.
#
# Architecture:
#   Session 1 (tmux: kwyre-traces)  → Batch trace generation (all 13 domains)
#   Session 2 (tmux: kwyre-train-a) → Train domains 1-5 (after traces complete)
#   Session 3 (tmux: kwyre-train-b) → Train domains 6-9
#   Session 4 (tmux: kwyre-train-c) → Train domains 10-13
#
# Usage (from your local machine):
#   export ANTHROPIC_API_KEY=sk-ant-...
#   bash training/deploy_and_train.sh
#
# Prerequisites:
#   - SSH key auth to root@165.227.47.89
#   - ANTHROPIC_API_KEY set
################################################################################
set -euo pipefail

SERVER="root@165.227.47.89"
REMOTE_DIR="/root/kwyre-ai"
TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-5000}"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: Set ANTHROPIC_API_KEY before running."
    echo "  export ANTHROPIC_API_KEY=sk-ant-..."
    exit 1
fi

echo "========================================"
echo "  KWYRE — Deploy & Train on H100"
echo "  Server: $SERVER"
echo "  Traces: ${TRACES_PER_DOMAIN}/domain x 13 domains = $((TRACES_PER_DOMAIN * 13)) total"
echo "========================================"
echo ""

# ── Step 1: Sync code to server ──────────────────────────────────────────────
echo "[1/3] Syncing code to $SERVER:$REMOTE_DIR ..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'node_modules' \
    --exclude 'dist/' --exclude '.env' --exclude '*.pyc' \
    ./ "$SERVER:$REMOTE_DIR/"
echo "  Sync complete."
echo ""

# ── Step 2: Install deps on server ───────────────────────────────────────────
echo "[2/3] Installing dependencies on server..."
ssh "$SERVER" << 'REMOTE_SETUP'
cd /root/kwyre-ai
pip install anthropic httpx 2>/dev/null | tail -1
echo "  Deps ready."
REMOTE_SETUP
echo ""

# ── Step 3: Launch training via tmux ─────────────────────────────────────────
echo "[3/3] Launching training sessions on server..."

DOMAIN_GROUP_A="financial_trading software_engineering scientific_research dental_clinical legal_compliance"
DOMAIN_GROUP_B="career_placement relationship_matching sports_analytics college_basketball"
DOMAIN_GROUP_C="insurance_actuarial healthcare_lifesciences defense_intelligence blockchain_crypto"

ssh "$SERVER" << REMOTE_TRAIN
cd /root/kwyre-ai
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
export KWYRE_TRACES_PER_DOMAIN=${TRACES_PER_DOMAIN}
export KWYRE_BASE_MODEL="HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"
export PYTHONUNBUFFERED=1

# Kill any existing training sessions
tmux kill-session -t kwyre-traces 2>/dev/null || true
tmux kill-session -t kwyre-train-a 2>/dev/null || true
tmux kill-session -t kwyre-train-b 2>/dev/null || true
tmux kill-session -t kwyre-train-c 2>/dev/null || true

# Session 1: Generate ALL traces first (batch API, runs in background)
tmux new-session -d -s kwyre-traces -x 200 -y 50
tmux send-keys -t kwyre-traces "cd /root/kwyre-ai && export ANTHROPIC_API_KEY='${ANTHROPIC_API_KEY}' && export KWYRE_TRACES_PER_DOMAIN=${TRACES_PER_DOMAIN} && export PYTHONUNBUFFERED=1 && python3 training/scripts/scrape_repos.py 2>&1 | tee ~/.kwyre/logs/00-scrape.log && python3 training/scripts/generate_traces_batch.py 2>&1 | tee ~/.kwyre/logs/01-traces.log && echo 'TRACES COMPLETE — start training sessions now'" C-m

echo ""
echo "========================================"
echo "  TRAINING LAUNCHED!"
echo "========================================"
echo ""
echo "  Trace generation running in tmux session: kwyre-traces"
echo ""
echo "  Monitor progress:"
echo "    ssh $SERVER"
echo "    tmux attach -t kwyre-traces"
echo ""
echo "  Once traces are done (~2-6 hours), launch training groups:"
echo ""
echo "    # Group A (5 domains)"
echo "    tmux new-session -d -s kwyre-train-a"
echo "    tmux send-keys -t kwyre-train-a 'cd /root/kwyre-ai && for d in ${DOMAIN_GROUP_A}; do KWYRE_DOMAIN=\\\$d python3 training/scripts/train_distillation.py && KWYRE_DOMAIN=\\\$d python3 training/scripts/train_grpo_domain.py; done' C-m"
echo ""
echo "    # Group B (4 domains)"
echo "    tmux new-session -d -s kwyre-train-b"
echo "    tmux send-keys -t kwyre-train-b 'cd /root/kwyre-ai && for d in ${DOMAIN_GROUP_B}; do KWYRE_DOMAIN=\\\$d python3 training/scripts/train_distillation.py && KWYRE_DOMAIN=\\\$d python3 training/scripts/train_grpo_domain.py; done' C-m"
echo ""
echo "    # Group C (4 domains)"
echo "    tmux new-session -d -s kwyre-train-c"
echo "    tmux send-keys -t kwyre-train-c 'cd /root/kwyre-ai && for d in ${DOMAIN_GROUP_C}; do KWYRE_DOMAIN=\\\$d python3 training/scripts/train_distillation.py && KWYRE_DOMAIN=\\\$d python3 training/scripts/train_grpo_domain.py; done' C-m"
echo ""
echo "  When all training is done, copy adapters back:"
echo "    rsync -avz root@165.227.47.89:~/.kwyre/adapters/ ~/.kwyre/adapters/"
echo ""
REMOTE_TRAIN

echo ""
echo "  Done! Trace generation is now running on the server."
echo "  SSH in and monitor: ssh $SERVER && tmux attach -t kwyre-traces"
echo ""
