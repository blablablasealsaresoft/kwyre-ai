#!/usr/bin/env bash
# Kwyre Cloud — H100 GPU Server Setup
# Target: ubuntu-gpu-h100x1-80gb-tor1 (165.227.47.89)
#
# Usage:
#   scp -r deploy/cloud/ root@165.227.47.89:/tmp/kwyre-setup/
#   ssh root@165.227.47.89 'bash /tmp/kwyre-setup/setup-h100.sh'
#
# Or from this repo:
#   ssh root@165.227.47.89 'bash -s' < deploy/cloud/setup-h100.sh

set -euo pipefail

KWYRE_USER="kwyre"
KWYRE_HOME="/opt/kwyre"
KWYRE_REPO="https://github.com/blablablasealsaresoft/kwyre-ai.git"
KWYRE_BRANCH="main"

MODEL_ID="Qwen/Qwen3.5-9B"
DRAFT_MODEL_ID="Qwen/Qwen3.5-0.8B"
KWYRE_PORT="8000"

echo "============================================================"
echo "  Kwyre Cloud — H100 Server Setup"
echo "  Host:  $(hostname) ($(curl -s ifconfig.me 2>/dev/null || echo 'unknown'))"
echo "  GPU:   $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "============================================================"
echo ""

# --- System packages ---
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip git curl jq ufw > /dev/null

# --- Firewall ---
echo "[2/7] Configuring firewall..."
ufw --force reset > /dev/null 2>&1
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
ufw allow ssh > /dev/null
ufw allow ${KWYRE_PORT}/tcp > /dev/null
ufw --force enable > /dev/null
echo "  Firewall: SSH + port ${KWYRE_PORT} open, all else denied"

# --- User + directory ---
echo "[3/7] Creating kwyre user and workspace..."
id -u ${KWYRE_USER} &>/dev/null || useradd -r -m -d ${KWYRE_HOME} -s /bin/bash ${KWYRE_USER}
mkdir -p ${KWYRE_HOME}
chown -R ${KWYRE_USER}:${KWYRE_USER} ${KWYRE_HOME}

# --- Clone repo ---
echo "[4/7] Cloning Kwyre repository..."
if [ -d "${KWYRE_HOME}/repo" ]; then
    cd "${KWYRE_HOME}/repo"
    sudo -u ${KWYRE_USER} git pull --ff-only || true
else
    sudo -u ${KWYRE_USER} git clone --depth 1 -b ${KWYRE_BRANCH} ${KWYRE_REPO} ${KWYRE_HOME}/repo
fi

# --- Python venv + deps ---
echo "[5/7] Installing Python dependencies..."
VENV="${KWYRE_HOME}/venv"
if [ ! -d "${VENV}" ]; then
    sudo -u ${KWYRE_USER} python3.11 -m venv ${VENV}
fi
sudo -u ${KWYRE_USER} ${VENV}/bin/pip install --upgrade pip -q
sudo -u ${KWYRE_USER} ${VENV}/bin/pip install -r ${KWYRE_HOME}/repo/requirements.txt -q
echo "  Python deps installed"

# --- Download models ---
echo "[6/7] Downloading models (this may take 10-20 minutes)..."
sudo -u ${KWYRE_USER} ${VENV}/bin/python -c "
from huggingface_hub import snapshot_download
import os
os.environ.pop('HF_HUB_OFFLINE', None)
os.environ.pop('TRANSFORMERS_OFFLINE', None)
print('  Downloading ${MODEL_ID}...')
snapshot_download('${MODEL_ID}', cache_dir='${KWYRE_HOME}/.cache/huggingface')
print('  Downloading ${DRAFT_MODEL_ID}...')
snapshot_download('${DRAFT_MODEL_ID}', cache_dir='${KWYRE_HOME}/.cache/huggingface')
print('  Models ready.')
"

# HF cache compatibility — snapshot_download puts models directly under cache_dir,
# but serve_local_4bit.py expects HF_HOME/hub/models--*/snapshots/
ln -sfn ${KWYRE_HOME}/.cache/huggingface ${KWYRE_HOME}/.cache/huggingface/hub 2>/dev/null || true

# --- Systemd service ---
echo "[7/7] Creating systemd service..."
cat > /etc/systemd/system/kwyre.service << UNIT
[Unit]
Description=Kwyre AI Cloud Inference Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${KWYRE_USER}
Group=${KWYRE_USER}
WorkingDirectory=${KWYRE_HOME}/repo
ExecStart=${VENV}/bin/python server/serve_local_4bit.py

Environment=PYTHONUNBUFFERED=1
Environment=KWYRE_MODEL=${MODEL_ID}
Environment=KWYRE_DRAFT_MODEL=${DRAFT_MODEL_ID}
Environment=KWYRE_SPECULATIVE=1
Environment=KWYRE_BIND_HOST=0.0.0.0
Environment=KWYRE_PORT=${KWYRE_PORT}
Environment=KWYRE_API_KEYS=sk-kwyre-cloud-proxy:cloud
Environment=KWYRE_MULTI_USER=0
Environment=KWYRE_ENABLE_TOOLS=1
Environment=KWYRE_SKIP_DEP_CHECK=1
Environment=HF_HOME=${KWYRE_HOME}/.cache
Environment=TORCHDYNAMO_DISABLE=1

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kwyre

# Hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=${KWYRE_HOME}
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable kwyre
systemctl restart kwyre

echo ""
echo "============================================================"
echo "  Kwyre Cloud — Setup Complete"
echo ""
echo "  Service:   systemctl status kwyre"
echo "  Logs:      journalctl -u kwyre -f"
echo "  Endpoint:  http://$(curl -s ifconfig.me 2>/dev/null || echo '165.227.47.89'):${KWYRE_PORT}/health"
echo ""
echo "  Test:"
echo "    curl http://localhost:${KWYRE_PORT}/health"
echo "    curl -X POST http://localhost:${KWYRE_PORT}/v1/chat/completions \\"
echo "      -H 'Authorization: Bearer sk-kwyre-cloud-proxy' \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
echo ""
echo "  Next steps:"
echo "    1. Set real API key: edit KWYRE_API_KEYS in /etc/systemd/system/kwyre.service"
echo "    2. Deploy Cloudflare Worker: cd deploy/cloud && npx wrangler deploy"
echo "    3. Set Worker secrets: wrangler secret put JWT_SECRET"
echo "                           wrangler secret put UPSTREAM_API_KEY"
echo "============================================================"
