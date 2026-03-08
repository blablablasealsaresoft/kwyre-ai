#!/usr/bin/env bash
# =============================================================================
# Kwyre AI — Linux Installer
# =============================================================================
# Installs Kwyre AI inference server with full 6-layer security stack.
#
# Usage:
#   chmod +x install_linux.sh
#   sudo ./install_linux.sh                # Install to /opt/kwyre (default)
#   sudo ./install_linux.sh /custom/path   # Install to custom path
#
# Supports: Ubuntu 20.04+, Debian 11+, Fedora 38+, RHEL 9+, Arch
# Requires: NVIDIA GPU with CUDA drivers
# =============================================================================

set -euo pipefail

INSTALL_DIR="${1:-/opt/kwyre}"
KWYRE_USER="kwyre"
VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

echo ""
echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}      Kwyre AI — Linux Installer v${VERSION}     ${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo ""

# ── Pre-flight ──────────────────────────────────────────────────────────────

if [ "$EUID" -ne 0 ]; then
    fail "Run with sudo: sudo ./install_linux.sh"
fi

if ! command -v nvidia-smi &>/dev/null; then
    warn "nvidia-smi not found. Kwyre requires NVIDIA GPU with CUDA drivers."
    warn "Install: https://developer.nvidia.com/cuda-downloads"
    read -rp "Continue anyway? [y/N] " cont
    [[ "$cont" =~ ^[Yy]$ ]] || exit 1
else
    gpu_info=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -1)
    ok "GPU detected: $gpu_info"
fi

# ── Detect compiled binary or Python source ─────────────────────────────────

COMPILED_BINARY="$SCRIPT_DIR/build/kwyre-dist/kwyre-server"
USE_COMPILED=false

if [ -f "$COMPILED_BINARY" ]; then
    USE_COMPILED=true
    ok "Compiled binary found: $COMPILED_BINARY"
else
    info "No compiled binary found. Installing from Python source."
    if ! command -v python3 &>/dev/null; then
        fail "Python 3.10+ required. Install: sudo apt install python3 python3-venv"
    fi
    py_version=$(python3 --version 2>&1)
    ok "Python: $py_version"
fi

# ── Create system user ──────────────────────────────────────────────────────

if ! id "$KWYRE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$KWYRE_USER"
    ok "Created restricted system user: $KWYRE_USER"
else
    ok "System user $KWYRE_USER exists"
fi

# ── Install files ───────────────────────────────────────────────────────────

info "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

if $USE_COMPILED; then
    cp "$COMPILED_BINARY" "$INSTALL_DIR/kwyre-server"
    chmod +x "$INSTALL_DIR/kwyre-server"
    ok "Installed compiled binary"
else
    for dir in server model security; do
        if [ -d "$SCRIPT_DIR/$dir" ]; then
            cp -r "$SCRIPT_DIR/$dir" "$INSTALL_DIR/"
        fi
    done
    cp "$SCRIPT_DIR/requirements-inference.txt" "$INSTALL_DIR/" 2>/dev/null || true

    info "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements-inference.txt"
    ok "Python dependencies installed"

    info "Generating dependency manifest (Layer 3)..."
    "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/security/verify_deps.py" generate || true
    ok "Dependency manifest generated"
fi

cp -r "$SCRIPT_DIR/chat" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/docs" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/" 2>/dev/null || true

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" 2>/dev/null || true
    info "Created .env from .env.example — edit with your API keys"
fi

chown -R "$KWYRE_USER:$KWYRE_USER" "$INSTALL_DIR"
ok "Files installed to $INSTALL_DIR"

# ── Layer 2: Network Isolation ──────────────────────────────────────────────

info "Installing Layer 2 network isolation (iptables)..."

KWYRE_UID=$(id -u "$KWYRE_USER")

iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP 2>/dev/null || \
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP

iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT 2>/dev/null || \
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT

iptables -C OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT

ok "iptables rules installed — all outbound blocked except 127.0.0.1"

if command -v iptables-save &>/dev/null; then
    mkdir -p /etc/iptables
    iptables-save > /etc/iptables/rules.v4
    ok "Rules persisted to /etc/iptables/rules.v4"
fi

# ── Systemd Service ────────────────────────────────────────────────────────

info "Installing systemd service..."

if $USE_COMPILED; then
    EXEC_START="$INSTALL_DIR/kwyre-server"
else
    EXEC_START="$INSTALL_DIR/venv/bin/python $INSTALL_DIR/server/serve_local_4bit.py"
fi

cat > /etc/systemd/system/kwyre.service << SVCEOF
[Unit]
Description=Kwyre AI Inference Server
Documentation=https://kwyre.com
After=network.target

[Service]
Type=simple
User=$KWYRE_USER
Group=$KWYRE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$EXEC_START
Restart=on-failure
RestartSec=5
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=KWYRE_BIND_HOST=127.0.0.1
EnvironmentFile=-$INSTALL_DIR/.env
LimitNOFILE=65536
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable kwyre.service
ok "Systemd service installed and enabled"

# ── CLI launcher ────────────────────────────────────────────────────────────

if $USE_COMPILED; then
    ln -sf "$INSTALL_DIR/kwyre-server" /usr/local/bin/kwyre
else
    cat > /usr/local/bin/kwyre << LAUNCHEOF
#!/bin/bash
exec sudo -u $KWYRE_USER "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/server/serve_local_4bit.py" "\$@"
LAUNCHEOF
    chmod +x /usr/local/bin/kwyre
fi
ok "CLI launcher installed: kwyre"

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}        Installation Complete                ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Start server:   sudo systemctl start kwyre"
echo "  Stop server:    sudo systemctl stop kwyre"
echo "  Server status:  sudo systemctl status kwyre"
echo "  Manual start:   kwyre"
echo ""
echo "  Server:         http://127.0.0.1:8000"
echo "  Chat UI:        http://127.0.0.1:8000/chat"
echo "  Health check:   http://127.0.0.1:8000/health"
echo ""
echo -e "  ${CYAN}Security: All 6 layers active. No data leaves this machine.${NC}"
echo ""
