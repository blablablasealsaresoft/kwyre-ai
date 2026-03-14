#!/bin/bash
################################################################################
# KWYRE AI — Train All Product Adapters (Batch Pipeline)
#
# Trains domain adapters for all 9 Mint Rail products using the Anthropic
# Batch API for trace generation (50% cheaper) + Unsloth QLoRA distillation
# + domain-specific GRPO reinforcement learning.
#
# Pipeline:
#   1. Scrape GitHub repos for training context enrichment
#   2. Generate 13,000 reasoning traces via Anthropic Batch API
#   3. Train distillation + GRPO for each domain sequentially
#
# Usage:
#   export ANTHROPIC_API_KEY=sk-ant-...
#   bash train_all_products.sh
#
# Cost estimate: ~$310-400 API (batch pricing) + ~$400 GPU = ~$710-800
# Time estimate: ~120-160 hours on H100 for all 13 adapters (5000 traces each)
################################################################################
set -euo pipefail

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ERROR: ANTHROPIC_API_KEY not set."
    echo "  export ANTHROPIC_API_KEY=sk-ant-..."
    exit 1
fi

export KWYRE_BASE_MODEL="${KWYRE_BASE_MODEL:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}"
export KWYRE_TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-5000}"
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$HOME/.kwyre/logs"
mkdir -p "$LOGDIR"

echo "========================================"
echo "  KWYRE — Product Adapter Batch Training"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Base model:       $KWYRE_BASE_MODEL"
echo "  Traces/domain:    $KWYRE_TRACES_PER_DOMAIN"
echo "  Total domains:    13"
echo "  Total traces:     ~$((KWYRE_TRACES_PER_DOMAIN * 13)) (${KWYRE_TRACES_PER_DOMAIN}/domain)"
echo ""

nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null || echo "  (no GPU detected)"
echo ""

# ── STEP 1: Scrape GitHub repos for context enrichment ───────────────────────
echo "========================================"
echo "  STEP 1: Scraping GitHub repos for training context"
echo "========================================"

if python3 "$SCRIPT_DIR/scrape_repos.py" 2>&1 | tee "$LOGDIR/00-scrape-repos.log"; then
    echo "  Scraping complete."
else
    echo "  WARNING: Repo scraping failed — continuing without enrichment."
fi
echo ""

# ── STEP 2: Generate traces via Batch API (all 13 domains at once) ───────────
echo "========================================"
echo "  STEP 2: Generating reasoning traces (Anthropic Batch API)"
echo "  Target: $KWYRE_TRACES_PER_DOMAIN traces x 13 domains"
echo "  Estimated cost: ~\$$(( KWYRE_TRACES_PER_DOMAIN * 13 * 6 / 1000 ))"
echo "========================================"

python3 "$SCRIPT_DIR/generate_traces_batch.py" 2>&1 | tee "$LOGDIR/01-batch-traces.log"

echo ""
echo "  Traces complete. Files:"
ls -la ~/.kwyre/training-data/kwyre-traces/*.jsonl 2>/dev/null | wc -l
echo "  domain trace files generated."
echo ""

# ── STEP 3: Train each domain (distillation + GRPO) ─────────────────────────
DOMAINS=(
    "financial_trading"
    "software_engineering"
    "scientific_research"
    "dental_clinical"
    "legal_compliance"
    "career_placement"
    "relationship_matching"
    "sports_analytics"
    "college_basketball"
    "insurance_actuarial"
    "healthcare_lifesciences"
    "defense_intelligence"
    "blockchain_crypto"
)

TOTAL_START=$(date +%s)
COMPLETED=0
FAILED=0

echo "========================================"
echo "  STEP 3: Training ${#DOMAINS[@]} domain adapters"
echo "  (distillation + GRPO per domain)"
echo "========================================"
echo ""

for i in "${!DOMAINS[@]}"; do
    DOMAIN="${DOMAINS[$i]}"
    IDX=$((i + 1))

    echo ""
    echo "========================================"
    echo "  [$IDX/${#DOMAINS[@]}] Training: $DOMAIN"
    echo "  $(date)"
    echo "========================================"

    DOMAIN_START=$(date +%s)
    export KWYRE_DOMAIN="$DOMAIN"

    # Distillation
    echo "  [distillation] Starting..."
    if python3 "$SCRIPT_DIR/train_distillation.py" 2>&1 | tee "$LOGDIR/${DOMAIN}-distillation.log"; then
        echo "  [distillation] Complete."
    else
        echo "  [distillation] FAILED"
        FAILED=$((FAILED + 1))
        continue
    fi

    # Domain GRPO
    echo "  [grpo] Starting..."
    if python3 "$SCRIPT_DIR/train_grpo_domain.py" 2>&1 | tee "$LOGDIR/${DOMAIN}-grpo.log"; then
        echo "  [grpo] Complete."
    else
        echo "  [grpo] FAILED"
        FAILED=$((FAILED + 1))
        continue
    fi

    COMPLETED=$((COMPLETED + 1))
    DOMAIN_ELAPSED=$(( $(date +%s) - DOMAIN_START ))
    echo "  $DOMAIN completed in $(( DOMAIN_ELAPSED / 3600 ))h $(( (DOMAIN_ELAPSED % 3600) / 60 ))m"
done

TOTAL_ELAPSED=$(( $(date +%s) - TOTAL_START ))

echo ""
echo "========================================"
echo "  PRODUCT BATCH TRAINING COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Completed: $COMPLETED / ${#DOMAINS[@]}"
echo "  Failed:    $FAILED"
echo "  Total time: $(( TOTAL_ELAPSED / 3600 ))h $(( (TOTAL_ELAPSED % 3600) / 60 ))m"
echo ""
echo "  Product → Adapter mapping:"
echo "    QuantEdge       → financial-trading"
echo "    CodeForge       → software-engineering"
echo "    LabMind         → scientific-research"
echo "    DentAI          → dental-clinical"
echo "    TaxShield       → legal-compliance"
echo "    LaunchPad       → career-placement"
echo "    SoulSync        → relationship-matching"
echo "    NFL PlayCaller  → sports-analytics"
echo "    MarchMind       → college-basketball"
echo ""
echo "  Adapters:"
ls -d ~/.kwyre/adapters/*/ 2>/dev/null | while read d; do
    NAME=$(basename "$d")
    SIZE=$(du -sh "$d" | cut -f1)
    echo "    $NAME ($SIZE)"
done
echo ""
echo "  Deploy:"
echo "    scp -r ~/.kwyre/adapters/ user@kwyre-server:~/.kwyre/adapters/"
echo ""
