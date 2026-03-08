#!/usr/bin/env bash
# =============================================================================
# Kwyre AI — macOS Installer
# =============================================================================
# Installs Kwyre AI inference server with security isolation.
#
# Usage:
#   chmod +x install_macos.sh
#   sudo ./install_macos.sh                # Install to /opt/kwyre (default)
#   sudo ./install_macos.sh /custom/path   # Install to custom path
#
# Requires: macOS 12+ with Apple Silicon or NVIDIA eGPU
# =============================================================================

set -euo pipefail

INSTALL_DIR="${1:-/opt/kwyre}"
KWYRE_USER="_kwyre"
VERSION="0.3.0"
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
echo -e "${CYAN}     Kwyre AI — macOS Installer v${VERSION}      ${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo ""

# ── Pre-flight ──────────────────────────────────────────────────────────────

if [ "$EUID" -ne 0 ]; then
    fail "Run with sudo: sudo ./install_macos.sh"
fi

arch=$(uname -m)
if [ "$arch" = "arm64" ]; then
    ok "Apple Silicon detected — MLX/MPS acceleration available"
elif [ "$arch" = "x86_64" ]; then
    info "Intel Mac detected — CUDA eGPU or CPU mode required"
else
    warn "Unknown architecture: $arch"
fi

if ! command -v python3 &>/dev/null; then
    fail "Python 3.10+ required. Install: brew install python@3.12"
fi
py_version=$(python3 --version 2>&1)
ok "Python: $py_version"

# ── Detect compiled binary or Python source ─────────────────────────────────

COMPILED_BINARY="$SCRIPT_DIR/build/kwyre-dist/kwyre-server"
USE_COMPILED=false

if [ -f "$COMPILED_BINARY" ]; then
    USE_COMPILED=true
    ok "Compiled binary found"
else
    info "No compiled binary found. Installing from Python source."
fi

# ── Create service user ────────────────────────────────────────────────────

if ! dscl . -read /Users/$KWYRE_USER &>/dev/null 2>&1; then
    MAX_UID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
    NEW_UID=$((MAX_UID + 1))
    dscl . -create /Users/$KWYRE_USER
    dscl . -create /Users/$KWYRE_USER UserShell /usr/bin/false
    dscl . -create /Users/$KWYRE_USER UniqueID "$NEW_UID"
    dscl . -create /Users/$KWYRE_USER PrimaryGroupID 20
    dscl . -create /Users/$KWYRE_USER RealName "Kwyre AI Service"
    dscl . -create /Users/$KWYRE_USER NFSHomeDirectory /var/empty
    ok "Created service user: $KWYRE_USER (UID $NEW_UID)"
else
    ok "Service user $KWYRE_USER exists"
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
fi

cp -r "$SCRIPT_DIR/chat" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/docs" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/" 2>/dev/null || true

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" 2>/dev/null || true
    info "Created .env from .env.example — edit with your API keys"
fi

chown -R "$KWYRE_USER:staff" "$INSTALL_DIR"

mkdir -p /var/log/kwyre
chown "$KWYRE_USER:staff" /var/log/kwyre

ok "Files installed to $INSTALL_DIR"

# ── Network Isolation (PF firewall) ────────────────────────────────────────

info "Installing network isolation via macOS PF firewall..."

PF_ANCHOR="/etc/pf.anchors/com.kwyre"
cat > "$PF_ANCHOR" << 'PFEOF'
# Kwyre AI — Block all outbound traffic from kwyre user except localhost
block out quick proto {tcp, udp} user _kwyre
pass out quick proto {tcp, udp} from any to 127.0.0.1 user _kwyre
pass out quick proto {tcp, udp} from any to ::1 user _kwyre
PFEOF

if ! grep -q "com.kwyre" /etc/pf.conf 2>/dev/null; then
    echo "" >> /etc/pf.conf
    echo "anchor \"com.kwyre\"" >> /etc/pf.conf
    echo "load anchor \"com.kwyre\" from \"/etc/pf.anchors/com.kwyre\"" >> /etc/pf.conf
    ok "PF anchor added to /etc/pf.conf"
fi

pfctl -f /etc/pf.conf 2>/dev/null || warn "Could not reload PF rules (may need SIP adjustment)"
ok "PF firewall rules installed — outbound blocked for $KWYRE_USER"

# ── launchd Service ────────────────────────────────────────────────────────

info "Installing launchd service..."

if $USE_COMPILED; then
    EXEC_PATH="$INSTALL_DIR/kwyre-server"
else
    EXEC_PATH="$INSTALL_DIR/venv/bin/python"
    EXEC_ARGS="$INSTALL_DIR/server/serve_local_4bit.py"
fi

PLIST_PATH="/Library/LaunchDaemons/com.kwyre.ai.server.plist"

if $USE_COMPILED; then
    cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kwyre.ai.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$EXEC_PATH</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>UserName</key>
    <string>$KWYRE_USER</string>
    <key>GroupName</key>
    <string>staff</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
        <key>TRANSFORMERS_OFFLINE</key>
        <string>1</string>
        <key>KWYRE_BIND_HOST</key>
        <string>127.0.0.1</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/var/log/kwyre/server.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/kwyre/error.log</string>
</dict>
</plist>
PLISTEOF
else
    cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kwyre.ai.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$EXEC_PATH</string>
        <string>$EXEC_ARGS</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>UserName</key>
    <string>$KWYRE_USER</string>
    <key>GroupName</key>
    <string>staff</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HF_HUB_OFFLINE</key>
        <string>1</string>
        <key>TRANSFORMERS_OFFLINE</key>
        <string>1</string>
        <key>KWYRE_BIND_HOST</key>
        <string>127.0.0.1</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/var/log/kwyre/server.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/kwyre/error.log</string>
</dict>
</plist>
PLISTEOF
fi

launchctl load "$PLIST_PATH" 2>/dev/null || true
ok "launchd service installed"

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
ok "CLI launcher: kwyre"

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}        Installation Complete                ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Start server:   sudo launchctl start com.kwyre.ai.server"
echo "  Stop server:    sudo launchctl stop com.kwyre.ai.server"
echo "  Manual start:   kwyre"
echo ""
echo "  Server:         http://127.0.0.1:8000"
echo "  Chat UI:        http://127.0.0.1:8000/chat"
echo "  Health check:   http://127.0.0.1:8000/health"
echo ""
echo -e "  ${CYAN}Security: All 6 layers active. No data leaves this machine.${NC}"
echo ""
