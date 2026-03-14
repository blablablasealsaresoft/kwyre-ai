#!/bin/bash
set -euo pipefail
cd /root/kwyre-ai

echo "=== Verify Training Scripts ==="
python3 -c "
import ast
files = [
    'training/scripts/generate_traces_batch.py',
    'training/scripts/train_grpo_domain.py',
    'training/scripts/train_distillation.py',
    'training/scripts/scrape_repos.py',
    'training/scripts/product_domains.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'  {f}: OK')
print('All scripts: PASS')
"

echo ""
echo "=== Domain Count ==="
python3 training/scripts/product_domains.py

echo ""
echo "=== GPU Status ==="
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader

echo ""
echo "=== API Key ==="
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "  ANTHROPIC_API_KEY set (${#ANTHROPIC_API_KEY} chars)"
else
    echo "  WARNING: ANTHROPIC_API_KEY not set!"
    echo "  Set it with: export ANTHROPIC_API_KEY=sk-ant-..."
fi

echo ""
echo "=== Existing Traces ==="
ls ~/.kwyre/training-data/kwyre-traces/*.jsonl 2>/dev/null | wc -l
echo "  trace files found"

echo ""
echo "=== Ready to Train ==="
echo "  To launch: bash training/scripts/train_all_products.sh"
