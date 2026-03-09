#!/bin/bash
################################################################################
# KWYRE AI — Training Only (traces already generated)
# Runs distillation → GRPO → export
################################################################################
set -euo pipefail

export ANTHROPIC_API_KEY='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'
export PYTHONUNBUFFERED=1

LOGDIR="$HOME/.kwyre/logs"

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

python3 /root/training/train_distillation.py 2>&1 | tee "$LOGDIR/02-distillation.log"

echo ""
echo "  Distillation complete!"
echo ""

# ── STEP 3: GRPO Reinforcement Learning ────────────────────────────────────
echo "========================================"
echo "  STEP 3: GRPO reinforcement learning"
echo "  Estimated: 2-4 hours on H100"
echo "========================================"

python3 /root/training/train_grpo.py 2>&1 | tee "$LOGDIR/03-grpo.log"

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
echo "    scp -r root@167.71.0.148:~/.kwyre/models/trained/ ./trained-models/"
echo "    scp -r root@167.71.0.148:~/.kwyre/lora-adapters/ ./lora-adapters/"
echo ""

ls -lhR ~/.kwyre/models/trained/ 2>/dev/null | head -30
echo ""
echo "  Training finished. You can destroy this droplet now."
