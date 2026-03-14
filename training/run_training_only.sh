#!/bin/bash
################################################################################
# KWYRE AI — Training Only (traces already generated)
# Runs distillation → GRPO → export
################################################################################
set -euo pipefail

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set. Export it before running this script."
    exit 1
fi
export PYTHONUNBUFFERED=1

LOGDIR="$HOME/.kwyre/logs"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "  KWYRE — Training Pipeline (traces done)"
echo "  $(date)"
echo "========================================"

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
echo ""

echo "  Traces: $(wc -l < ~/.kwyre/training-data/kwyre-traces/kwyre-all-traces.jsonl) samples"
echo ""

# ── STEP 2: Distillation Fine-Tuning ────────────────────────────────────────
echo "========================================"
echo "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)"
echo "  Estimated: 2-6 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/scripts/train_distillation.py" 2>&1 | tee "$LOGDIR/02-distillation.log"

echo ""
echo "  Distillation complete!"
echo ""

# ── STEP 3: GRPO Reinforcement Learning ────────────────────────────────────
echo "========================================"
echo "  STEP 3: GRPO reinforcement learning"
echo "  Estimated: 2-4 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/scripts/train_grpo.py" 2>&1 | tee "$LOGDIR/03-grpo.log"

echo ""
echo "  GRPO complete!"
echo ""

# ── SUMMARY ─────────────────────────────────────────────────────────────────
echo "========================================"
echo "  ALL TRAINING COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Download your model:"
echo "    scp -r root@\$(hostname -I | awk '{print \$1}'):~/.kwyre/models/trained/ ./trained-models/"
echo "    scp -r root@\$(hostname -I | awk '{print \$1}'):~/.kwyre/lora-adapters/ ./lora-adapters/"
echo ""

ls -lhR ~/.kwyre/models/trained/ 2>/dev/null | head -30
echo ""
echo "  Training finished."
