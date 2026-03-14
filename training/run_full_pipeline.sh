#!/bin/bash
################################################################################
# KWYRE AI — Full Training Pipeline
# Runs trace generation → distillation → GRPO → export in sequence
# Usage: bash run_full_pipeline.sh
################################################################################
set -euo pipefail

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set. Export it before running this script."
    exit 1
fi
export KWYRE_TRACES_PER_DOMAIN=${KWYRE_TRACES_PER_DOMAIN:-1000}
export PYTHONUNBUFFERED=1

LOGDIR="$HOME/.kwyre/logs"
mkdir -p "$LOGDIR"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

python3 "$SCRIPT_DIR/scripts/generate_traces_batch.py" 2>&1 | tee "$LOGDIR/01-traces.log"

echo ""
echo "  Traces complete. Files:"
ls -la ~/.kwyre/training-data/kwyre-traces/*.jsonl 2>/dev/null || echo "  (no trace files found)"
echo ""

# ── STEP 2: Distillation Fine-Tuning ────────────────────────────────────────
echo "========================================"
echo "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)"
echo "  This will take 2-6 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/scripts/train_distillation.py" 2>&1 | tee "$LOGDIR/02-distillation.log"

echo ""
echo "  Distillation complete."
echo ""

# ── STEP 3: GRPO Reinforcement Learning ────────────────────────────────────
echo "========================================"
echo "  STEP 3: GRPO reinforcement learning"
echo "  This will take 2-4 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/scripts/train_grpo.py" 2>&1 | tee "$LOGDIR/03-grpo.log"

echo ""
echo "  GRPO complete."
echo ""

# ── STEP 4: Merge LoRA + Export ──────────────────────────────────────────────
echo "========================================"
echo "  STEP 4: Merging LoRA adapters and exporting"
echo "========================================"

GRPO_LORA="$HOME/.kwyre/lora-adapters/kwyre-grpo"
MERGED_OUT="$HOME/.kwyre/models/trained/kwyre-9b-merged"

if [ -f "$SCRIPT_DIR/../model/merge_and_export.py" ] && [ -d "$GRPO_LORA" ]; then
    python3 "$SCRIPT_DIR/../model/merge_and_export.py" \
        --adapter_path "$GRPO_LORA" \
        --output_dir "$MERGED_OUT" \
        --merge_method adapter_only \
        2>&1 | tee "$LOGDIR/04-merge-export.log"
    echo ""
    echo "  Merge + export complete."
elif [ -f "$SCRIPT_DIR/../model/merge_and_export.py" ]; then
    echo "  SKIPPED — GRPO adapter not found at $GRPO_LORA"
    echo "  Run Step 3 first to generate GRPO LoRA."
else
    echo "  SKIPPED — model/merge_and_export.py not found"
fi
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
