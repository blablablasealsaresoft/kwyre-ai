#!/bin/bash
################################################################################
# KWYRE AI — Full Training Pipeline
# Runs trace generation → distillation → GRPO → export in sequence
# Usage: bash run_full_pipeline.sh
################################################################################
set -euo pipefail

export ANTHROPIC_API_KEY='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'
export KWYRE_TRACES_PER_DOMAIN=50
export PYTHONUNBUFFERED=1

LOGDIR="$HOME/.kwyre/logs"
mkdir -p "$LOGDIR"

echo "========================================"
echo "  KWYRE — Full Training Pipeline"
echo "  $(date)"
echo "========================================"
echo ""

nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo ""

# ── STEP 1: Generate Reasoning Traces ────────────────────────────────────────
echo "========================================"
echo "  STEP 1: Generating reasoning traces via Claude"
echo "  Target: $KWYRE_TRACES_PER_DOMAIN traces per domain"
echo "========================================"

python3 /root/training/generate_traces_parallel.py 2>&1 | tee "$LOGDIR/01-traces.log"

echo ""
echo "  Traces complete. Files:"
ls -la ~/.kwyre/training-data/kwyre-traces/*.jsonl 2>/dev/null || echo "  (no trace files found)"
echo ""

# ── STEP 2: Distillation Fine-Tuning ────────────────────────────────────────
echo "========================================"
echo "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)"
echo "  This will take 2-6 hours on H100"
echo "========================================"

python3 /root/training/train_distillation.py 2>&1 | tee "$LOGDIR/02-distillation.log"

echo ""
echo "  Distillation complete."
echo ""

# ── STEP 3: GRPO Reinforcement Learning ────────────────────────────────────
echo "========================================"
echo "  STEP 3: GRPO reinforcement learning"
echo "  This will take 2-4 hours on H100"
echo "========================================"

python3 /root/training/train_grpo.py 2>&1 | tee "$LOGDIR/03-grpo.log"

echo ""
echo "  GRPO complete."
echo ""

# ── SUMMARY ─────────────────────────────────────────────────────────────────
echo "========================================"
echo "  FULL PIPELINE COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Artifacts:"
echo "    Traces:      ~/.kwyre/training-data/kwyre-traces/"
echo "    Distilled:   ~/.kwyre/models/trained/kwyre-9b-distilled/"
echo "    GRPO:        ~/.kwyre/models/trained/kwyre-9b-grpo/"
echo "    LoRA:        ~/.kwyre/lora-adapters/"
echo "    GGUFs:       ~/.kwyre/models/trained/kwyre-9b-*-gguf/"
echo ""
echo "  Download your model with:"
echo "    scp -r root@$(hostname -I | awk '{print $1}'):~/.kwyre/models/trained/ ./trained-models/"
echo ""
ls -lhR ~/.kwyre/models/trained/ 2>/dev/null | head -30
