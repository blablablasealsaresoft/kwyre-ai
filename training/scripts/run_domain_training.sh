#!/bin/bash
################################################################################
# KWYRE AI — Domain Adapter Training Pipeline
# Trains a single domain adapter: traces → distillation → GRPO → export
#
# Usage:
#   KWYRE_DOMAIN=legal_compliance bash run_domain_training.sh
#   KWYRE_DOMAIN=blockchain_crypto bash run_domain_training.sh
#
# Environment:
#   KWYRE_DOMAIN          — required: domain to train
#   KWYRE_BASE_MODEL      — optional: base model (default: Qwen3.5-4B uncensored)
#   KWYRE_TRACES_PER_DOMAIN — optional: traces to generate (default: 300)
#   ANTHROPIC_API_KEY     — required for trace generation
#
# Requires: H100 or A100 GPU with 24GB+ VRAM
################################################################################
set -euo pipefail

export PYTHONUNBUFFERED=1

# ── Validate inputs ──────────────────────────────────────────────────────────
DOMAIN="${KWYRE_DOMAIN:-}"
if [ -z "$DOMAIN" ]; then
    echo "ERROR: Set KWYRE_DOMAIN to one of:"
    echo "  legal_compliance"
    echo "  insurance_actuarial"
    echo "  healthcare_lifesciences"
    echo "  defense_intelligence"
    echo "  financial_trading"
    echo "  blockchain_crypto"
    exit 1
fi

export KWYRE_BASE_MODEL="${KWYRE_BASE_MODEL:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}"
export KWYRE_TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-300}"

LOGDIR="$HOME/.kwyre/logs"
mkdir -p "$LOGDIR"

MODEL_TAG="4b"
if echo "$KWYRE_BASE_MODEL" | grep -qi "9B"; then
    MODEL_TAG="9b"
fi

echo "========================================"
echo "  KWYRE — Domain Adapter Training"
echo "  Domain:  $DOMAIN"
echo "  Base:    $KWYRE_BASE_MODEL"
echo "  Tag:     $MODEL_TAG"
echo "  Traces:  $KWYRE_TRACES_PER_DOMAIN"
echo "  $(date)"
echo "========================================"
echo ""

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null || echo "  (no GPU detected)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Step 1: Generate traces (skip if already exists) ─────────────────────────
TRACE_FILE="$HOME/.kwyre/training-data/kwyre-traces/${DOMAIN}.jsonl"

if [ -f "$TRACE_FILE" ]; then
    TRACE_COUNT=$(wc -l < "$TRACE_FILE")
    echo "========================================"
    echo "  STEP 1: Traces already exist ($TRACE_COUNT samples)"
    echo "  File: $TRACE_FILE"
    echo "  Skipping generation. Delete file to regenerate."
    echo "========================================"
else
    echo "========================================"
    echo "  STEP 1: Generating reasoning traces via Claude"
    echo "  Domain: $DOMAIN"
    echo "  Target: $KWYRE_TRACES_PER_DOMAIN traces"
    echo "========================================"

    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "  ERROR: ANTHROPIC_API_KEY not set. Required for trace generation."
        echo "  Set it or provide pre-generated traces at $TRACE_FILE"
        exit 1
    fi

    python3 "$SCRIPT_DIR/generate_traces_parallel.py" 2>&1 | tee "$LOGDIR/${DOMAIN}-01-traces.log"
fi

echo ""

# ── Step 2: Distillation ─────────────────────────────────────────────────────
echo "========================================"
echo "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)"
echo "  Domain: $DOMAIN"
echo "  Estimated: 2-4 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/train_distillation.py" 2>&1 | tee "$LOGDIR/${DOMAIN}-02-distillation-${MODEL_TAG}.log"

echo ""
echo "  Distillation complete!"
echo ""

# ── Step 3: GRPO ─────────────────────────────────────────────────────────────
echo "========================================"
echo "  STEP 3: Domain GRPO reinforcement learning"
echo "  Domain: $DOMAIN"
echo "  Estimated: 2-4 hours on H100"
echo "========================================"

python3 "$SCRIPT_DIR/train_grpo_domain.py" 2>&1 | tee "$LOGDIR/${DOMAIN}-03-grpo-${MODEL_TAG}.log"

echo ""
echo "  GRPO complete!"
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
ADAPTER_DIR="$HOME/.kwyre/adapters/${DOMAIN//_/-}"

echo "========================================"
echo "  DOMAIN TRAINING COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Domain:     $DOMAIN"
echo "  Base model: $KWYRE_BASE_MODEL"
echo "  Adapter:    $ADAPTER_DIR"
echo ""

if [ -d "$ADAPTER_DIR" ]; then
    echo "  Adapter files:"
    ls -lh "$ADAPTER_DIR/"
    echo ""
    ADAPTER_SIZE=$(du -sh "$ADAPTER_DIR" | cut -f1)
    echo "  Total adapter size: $ADAPTER_SIZE"
fi

echo ""
echo "  To use this adapter:"
echo "    1. Copy $ADAPTER_DIR to your Kwyre installation"
echo "    2. Set KWYRE_ADAPTER_DIR=~/.kwyre/adapters"
echo "    3. Start Kwyre, then:"
echo "       curl -X POST http://127.0.0.1:8000/v1/adapter/load \\"
echo "         -H 'Authorization: Bearer sk-kwyre-dev-local' \\"
echo "         -d '{\"domain\": \"${DOMAIN//_/-}\"}'"
echo ""
