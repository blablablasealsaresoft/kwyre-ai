#!/bin/bash
################################################################################
# KWYRE AI — Package Adapter for CDN Upload
#
# Zips a trained adapter directory, computes SHA-256, and prints the manifest
# entry to paste into chat/adapters/manifest.json.
#
# Usage:
#   bash scripts/package_adapter.sh <domain> <version> [model_tier]
#
# Example:
#   bash scripts/package_adapter.sh blockchain_crypto 1.0.0 4b
#
# Output:
#   ~/.kwyre/adapters/<domain>-<tier>-v<version>.zip  (upload this to R2)
#   Manifest JSON snippet to paste into chat/adapters/manifest.json
#
# After packaging, upload the zip to Cloudflare R2:
#   rclone copy <zip> r2:kwyre-adapters/
#   # or: wrangler r2 object put kwyre-adapters/<zip> --file <zip>
#
# Then update chat/adapters/manifest.json with the version, url, and sha256,
# and redeploy: npx wrangler pages deploy chat/ --project-name kwyre-ai
################################################################################
set -euo pipefail

DOMAIN="${1:-}"
VERSION="${2:-}"
TIER="${3:-4b}"

if [ -z "$DOMAIN" ] || [ -z "$VERSION" ]; then
    echo "Usage: $0 <domain> <version> [model_tier]"
    echo "  domain:     blockchain_crypto | legal_compliance | insurance_actuarial"
    echo "              defense_intelligence | financial_trading | healthcare_lifesciences"
    echo "  version:    e.g. 1.0.0"
    echo "  model_tier: 4b (default) | 9b"
    exit 1
fi

ADAPTER_DIR="$HOME/.kwyre/adapters/${DOMAIN}-${TIER}"
if [ ! -d "$ADAPTER_DIR" ]; then
    echo "ERROR: Adapter directory not found: $ADAPTER_DIR"
    echo "Run training first: KWYRE_DOMAIN=$DOMAIN bash training/scripts/run_domain_training.sh"
    exit 1
fi

OUTPUT_DIR="$HOME/.kwyre/adapter-packages"
mkdir -p "$OUTPUT_DIR"
ZIP_NAME="${DOMAIN//_/-}-${TIER}-v${VERSION}.zip"
ZIP_PATH="$OUTPUT_DIR/$ZIP_NAME"

echo "Packaging $ADAPTER_DIR → $ZIP_PATH ..."
cd "$HOME/.kwyre/adapters"
zip -r "$ZIP_PATH" "${DOMAIN}-${TIER}/"
echo "Done: $(du -sh "$ZIP_PATH" | cut -f1)"

SHA=$(sha256sum "$ZIP_PATH" | cut -d' ' -f1)
CDN_URL="https://cdn.kwyre.com/adapters/$ZIP_NAME"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  SHA-256: $SHA"
echo "  Upload:  $ZIP_PATH"
echo ""
echo "  Paste into chat/adapters/manifest.json:"
echo ""
cat <<MANIFEST
  "$DOMAIN": {
    "version": "$VERSION",
    "url": "$CDN_URL",
    "sha256": "$SHA",
    "model_tier": "$TIER"
  }
MANIFEST
echo ""
echo "  Then redeploy:"
echo "    npx wrangler pages deploy chat/ --project-name kwyre-ai"
echo "════════════════════════════════════════════════════════════════"
