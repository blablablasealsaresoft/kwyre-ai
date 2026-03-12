#!/bin/bash
################################################################################
# Kwyre AI — Model Migration Script
# Migrates from Qwen3-4B + Qwen3-0.6B to Qwen3.5-4B + Qwen3.5-0.8B
#
# OLD:  Qwen/Qwen3-4B (base) + Qwen/Qwen3-0.6B (draft)
# NEW:  HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive (base)
#       Qwen/Qwen3.5-0.8B (draft)
#
# Usage: bash migrate_models.sh
# Run from the kwyre-ai project root.
################################################################################
set -euo pipefail

echo "========================================"
echo "  Kwyre AI — Model Migration"
echo "  Qwen3 → Qwen3.5 (Uncensored)"
echo "========================================"
echo ""

# ── Define old and new model IDs ──────────────────────────────────────────────
OLD_BASE="Qwen/Qwen3-4B"
NEW_BASE="HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive"

OLD_DRAFT="Qwen/Qwen3-0.6B"
NEW_DRAFT="Qwen/Qwen3.5-0.8B"

OLD_DRAFT_ALT="Qwen3-0.6B"
NEW_DRAFT_ALT="Qwen3.5-0.8B"

# ── Files to patch ────────────────────────────────────────────────────────────
echo "[1/6] Patching .env.example..."
sed -i "s|$OLD_BASE|$NEW_BASE|g" .env.example
sed -i "s|$OLD_DRAFT|$NEW_DRAFT|g" .env.example
sed -i "s|Qwen3-0.6B|Qwen3.5-0.8B|g" .env.example
echo "  Done."

echo "[2/6] Patching server files..."
for f in server/serve_local_4bit.py server/serve_vllm.py server/serve_mlx.py; do
    if [ -f "$f" ]; then
        sed -i "s|$OLD_BASE|$NEW_BASE|g" "$f"
        sed -i "s|$OLD_DRAFT|$NEW_DRAFT|g" "$f"
        echo "  Patched $f"
    fi
done

echo "[3/6] Patching model scripts..."
for f in model/quantize_nf4.py model/quantize_awq.py model/convert_gguf.py model/train_qat.py model/merge_and_export.py model/eval_spike.py; do
    if [ -f "$f" ]; then
        sed -i "s|$OLD_BASE|$NEW_BASE|g" "$f"
        sed -i "s|$OLD_DRAFT|$NEW_DRAFT|g" "$f"
        echo "  Patched $f"
    fi
done

echo "[4/6] Patching training scripts..."
for f in training/scripts/train_distillation.py training/scripts/train_grpo.py training/scripts/train_grpo_vanilla.py training/scripts/train_grpo_fixed.py training/scripts/train_math_reasoning.py; do
    if [ -f "$f" ]; then
        sed -i "s|Qwen/Qwen3.5-9B|$NEW_BASE|g" "$f"
        sed -i "s|$OLD_BASE|$NEW_BASE|g" "$f"
        echo "  Patched $f"
    fi
done

echo "[5/6] Patching Docker and installers..."
for f in docker/entrypoint.sh Dockerfile docker-compose.yml; do
    if [ -f "$f" ]; then
        sed -i "s|$OLD_BASE|$NEW_BASE|g" "$f"
        sed -i "s|$OLD_DRAFT|$NEW_DRAFT|g" "$f"
        echo "  Patched $f"
    fi
done

echo "[6/6] Patching build.py and website..."
for f in build.py chat/platform.html; do
    if [ -f "$f" ]; then
        sed -i "s|$OLD_BASE|$NEW_BASE|g" "$f"
        sed -i "s|$OLD_DRAFT|$NEW_DRAFT|g" "$f"
        echo "  Patched $f"
    fi
done

echo ""
echo "========================================"
echo "  Migration complete!"
echo ""
echo "  IMPORTANT: After first model download,"
echo "  regenerate weight hashes:"
echo ""
echo "    python -c \""
echo "    from server.serve_local_4bit import generate_weight_hashes"
echo "    import json"
echo "    h = generate_weight_hashes('<path-to-downloaded-model>')"
echo "    print(json.dumps(h, indent=2))"
echo "    \""
echo ""
echo "  Then paste the new hashes into"
echo "  WEIGHT_HASHES_4B in serve_local_4bit.py"
echo "  and serve_mlx.py."
echo "========================================"
