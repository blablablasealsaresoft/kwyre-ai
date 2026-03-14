#!/bin/bash
################################################################################
# KWYRE AI — Train All 13 Domain Adapters
# Runs the full pipeline for each domain sequentially on a single GPU.
#
# Usage:
#   export ANTHROPIC_API_KEY=sk-ant-...
#   bash run_all_domains.sh
#
# Total time estimate: ~80-100 hours on H100
# Total cost estimate: ~$120 API + ~$300 GPU = ~$420
################################################################################
set -euo pipefail

export KWYRE_BASE_MODEL="${KWYRE_BASE_MODEL:-HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive}"
export KWYRE_TRACES_PER_DOMAIN="${KWYRE_TRACES_PER_DOMAIN:-300}"
export PYTHONUNBUFFERED=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DOMAINS=(
    "blockchain_crypto"
    "legal_compliance"
    "insurance_actuarial"
    "defense_intelligence"
    "financial_trading"
    "healthcare_lifesciences"
    "sports_analytics"
    "relationship_matching"
    "software_engineering"
    "scientific_research"
    "career_placement"
    "college_basketball"
    "dental_clinical"
)

echo "========================================"
echo "  KWYRE — All Domain Adapter Training"
echo "  Base model: $KWYRE_BASE_MODEL"
echo "  Domains: ${#DOMAINS[@]}"
echo "  Traces/domain: $KWYRE_TRACES_PER_DOMAIN"
echo "  $(date)"
echo "========================================"
echo ""

TOTAL_START=$(date +%s)
COMPLETED=0
FAILED=0

for DOMAIN in "${DOMAINS[@]}"; do
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║  Starting domain: $DOMAIN"
    echo "║  Progress: $((COMPLETED + 1)) / ${#DOMAINS[@]}"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    DOMAIN_START=$(date +%s)

    export KWYRE_DOMAIN="$DOMAIN"
    if bash "$SCRIPT_DIR/run_domain_training.sh"; then
        COMPLETED=$((COMPLETED + 1))
        DOMAIN_ELAPSED=$(( $(date +%s) - DOMAIN_START ))
        echo "  ✓ $DOMAIN completed in $(( DOMAIN_ELAPSED / 3600 ))h $(( (DOMAIN_ELAPSED % 3600) / 60 ))m"
    else
        FAILED=$((FAILED + 1))
        echo "  ✗ $DOMAIN FAILED — continuing to next domain"
    fi
done

TOTAL_ELAPSED=$(( $(date +%s) - TOTAL_START ))

echo ""
echo "========================================"
echo "  ALL DOMAINS COMPLETE!"
echo "  $(date)"
echo "========================================"
echo ""
echo "  Completed: $COMPLETED / ${#DOMAINS[@]}"
echo "  Failed:    $FAILED"
echo "  Total time: $(( TOTAL_ELAPSED / 3600 ))h $(( (TOTAL_ELAPSED % 3600) / 60 ))m"
echo ""
echo "  Adapters:"
ls -d ~/.kwyre/adapters/*/ 2>/dev/null | while read d; do
    NAME=$(basename "$d")
    SIZE=$(du -sh "$d" | cut -f1)
    echo "    $NAME ($SIZE)"
done
echo ""
echo "  Copy all adapters to deployment:"
echo "    scp -r ~/.kwyre/adapters/ user@kwyre-server:~/.kwyre/adapters/"
echo ""
