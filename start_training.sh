#!/bin/bash
# Kwyre AI — Domain Adapter Training Launcher
# Run on the H100 server at 165.227.47.89
#
# Prerequisites:
#   export ANTHROPIC_API_KEY=sk-ant-...
#   (optional) export KWYRE_TRACES_PER_DOMAIN=300
#   (optional) export KWYRE_DOMAIN=legal_compliance  (for single domain only)

set -euo pipefail
cd /root/kwyre-ai

echo "=================================="
echo "  Kwyre AI — Training Pipeline"
echo "  H100 80GB — $(date)"
echo "=================================="

# Phase 1: Generate traces (requires ANTHROPIC_API_KEY)
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo ""
    echo "[Phase 1] Generating domain traces via Batch API (50% cheaper, resumable)..."
    export KWYRE_TRACES_PER_DOMAIN=${KWYRE_TRACES_PER_DOMAIN:-1000}
    python3 training/scripts/generate_traces_batch.py
    echo "[Phase 1] Done."
else
    echo "[Phase 1] SKIPPED — set ANTHROPIC_API_KEY to generate traces"
    echo "          Looking for existing traces in ~/.kwyre/training-data/kwyre-traces/"
fi

# Phase 2: Train domain adapters
echo ""
echo "[Phase 2] Training domain adapters..."
if [ -n "${KWYRE_DOMAIN:-}" ]; then
    echo "  Single domain mode: $KWYRE_DOMAIN"
    bash training/scripts/run_domain_training.sh
else
    echo "  All 6 domains sequentially..."
    bash training/scripts/run_all_domains.sh
fi

echo ""
echo "=================================="
echo "  Training complete!"
echo "  Adapters saved to: ~/.kwyre/adapters/"
echo "  Copy back to your machine:"
echo "  rsync -avz root@165.227.47.89:~/.kwyre/adapters/ ~/.kwyre/adapters/"
echo "=================================="
