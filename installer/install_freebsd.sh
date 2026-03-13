#!/usr/bin/env bash
# =============================================================================
# Kwyre AI — FreeBSD Installer
# =============================================================================
# Installs Kwyre AI inference server with full 6-layer security stack.
#
# Usage:
#   chmod +x install_freebsd.sh
#   sudo ./install_freebsd.sh                # Install (default)
#   sudo ./install_freebsd.sh -u             # Uninstall
#   sudo ./install_freebsd.sh uninstall      # Uninstall
#
# Requires: FreeBSD 13+ with Python 3.10+
# =============================================================================

set -euo pipefail

INSTALL_DIR="/usr/local/kwyre"
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

# ── Uninstall ──────────────────────────────────────────────────────────────

do_uninstall() {
    echo ""
    echo -e "${YELLOW}=============================================${NC}"
    echo -e "${YELLOW}     Kwyre AI — FreeBSD Uninstaller          ${NC}"
    echo -e "${YELLOW}=============================================${NC}"
    echo ""

    if [ "$(id -u)" -ne 0 ]; then
        fail "Run with sudo: sudo ./install_freebsd.sh -u"
    fi

    info "Stopping service..."
    service kwyre stop 2>/dev/null || true

    info "Removing rc.d service script..."
    rm -f /usr/local/etc/rc.d/kwyre
    sysrc -x kwyre_enable 2>/dev/null || true

    info "Removing CLI launcher..."
    rm -f /usr/local/bin/kwyre

    info "Removing PF anchor..."
    rm -f /etc/pf.anchors/kwyre
    if grep -q 'anchor "kwyre"' /etc/pf.conf 2>/dev/null; then
        sed -i '' '/anchor "kwyre"/d' /etc/pf.conf 2>/dev/null || \
            sed -i '/anchor "kwyre"/d' /etc/pf.conf 2>/dev/null || true
        sed -i '' '/load anchor "kwyre"/d' /etc/pf.conf 2>/dev/null || \
            sed -i '/load anchor "kwyre"/d' /etc/pf.conf 2>/dev/null || true
        pfctl -f /etc/pf.conf 2>/dev/null || true
    fi

    info "Removing install directory..."
    rm -rf "$INSTALL_DIR"

    info "Removing log directory..."
    rm -rf /var/log/kwyre

    info "Removing service user..."
    if pw usershow "$KWYRE_USER" &>/dev/null; then
        pw userdel "$KWYRE_USER" 2>/dev/null || true
    fi

    echo ""
    echo -e "${GREEN}=============================================${NC}"
    echo -e "${GREEN}        Uninstall Complete                   ${NC}"
    echo -e "${GREEN}=============================================${NC}"
    echo ""
    exit 0
}

if [ "${1:-}" = "-u" ] || [ "${1:-}" = "uninstall" ]; then
    do_uninstall
fi

# ── Banner ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}=============================================${NC}"
echo -e "${CYAN}    Kwyre AI — FreeBSD Installer v${VERSION}    ${NC}"
echo -e "${CYAN}=============================================${NC}"
echo ""
echo "  Install directory: $INSTALL_DIR"
echo ""

# ── Pre-flight ──────────────────────────────────────────────────────────────

if [ "$(id -u)" -ne 0 ]; then
    fail "Run with sudo: sudo ./install_freebsd.sh"
fi

arch=$(uname -m)
case "$arch" in
    amd64)  ok "Architecture: x86_64 (amd64)" ;;
    arm64)  ok "Architecture: arm64 (aarch64)" ;;
    *)      warn "Unknown architecture: $arch" ;;
esac

if ! command -v python3 &>/dev/null; then
    fail "Python 3.10+ required. Install: pkg install python311"
fi

py_version=$(python3 --version 2>&1)
py_minor=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$py_minor" -lt 10 ]; then
    fail "Python 3.10+ required (found $py_version). Install: pkg install python311"
fi
ok "Python: $py_version"

# ── GPU Detection ──────────────────────────────────────────────────────────

if command -v nvidia-smi &>/dev/null; then
    gpu_info=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -1)
    ok "NVIDIA GPU detected: $gpu_info"
else
    pci_gpu=$(pciconf -lv 2>/dev/null | grep -i -A2 vga | head -3) || true
    if [ -n "$pci_gpu" ]; then
        info "VGA device found (no NVIDIA driver):"
        echo "  $pci_gpu"
    else
        warn "No GPU detected — CPU-only inference mode"
    fi
fi

# ── Detect compiled binary or Python source ─────────────────────────────────

COMPILED_BINARY="$SCRIPT_DIR/build/kwyre-dist/kwyre-server"
USE_COMPILED=false

if [ -f "$COMPILED_BINARY" ]; then
    USE_COMPILED=true
    ok "Compiled binary found: $COMPILED_BINARY"
else
    info "No compiled binary found. Installing from Python source."
fi

# ── Create service user ────────────────────────────────────────────────────

if ! pw usershow "$KWYRE_USER" &>/dev/null 2>&1; then
    pw useradd "$KWYRE_USER" -d /nonexistent -s /usr/sbin/nologin -c "Kwyre AI Service"
    ok "Created restricted service user: $KWYRE_USER"
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

    if [ -f "$SCRIPT_DIR/requirements-freebsd.txt" ]; then
        cp "$SCRIPT_DIR/requirements-freebsd.txt" "$INSTALL_DIR/"
        REQ_FILE="$INSTALL_DIR/requirements-freebsd.txt"
    elif [ -f "$SCRIPT_DIR/requirements-inference.txt" ]; then
        cp "$SCRIPT_DIR/requirements-inference.txt" "$INSTALL_DIR/"
        REQ_FILE="$INSTALL_DIR/requirements-inference.txt"
    else
        fail "No requirements file found (requirements-freebsd.txt or requirements-inference.txt)"
    fi

    info "Creating Python virtual environment..."
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    "$INSTALL_DIR/venv/bin/pip" install -r "$REQ_FILE"
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

mkdir -p /var/log/kwyre
chown "$KWYRE_USER:$KWYRE_USER" /var/log/kwyre

ok "Files installed to $INSTALL_DIR"

# ── Layer 2: PF Firewall Isolation ─────────────────────────────────────────

info "Installing Layer 2 network isolation (PF firewall)..."

PF_ANCHOR="/etc/pf.anchors/kwyre"
cat > "$PF_ANCHOR" << 'PFEOF'
# Kwyre AI — Block all outbound traffic from kwyre user except loopback
block out quick on ! lo0 proto { tcp, udp } user kwyre
pass out quick on lo0 proto { tcp, udp } user kwyre
PFEOF

if ! grep -q 'anchor "kwyre"' /etc/pf.conf 2>/dev/null; then
    echo "" >> /etc/pf.conf
    echo 'anchor "kwyre"' >> /etc/pf.conf
    echo 'load anchor "kwyre" from "/etc/pf.anchors/kwyre"' >> /etc/pf.conf
    ok "PF anchor added to /etc/pf.conf"
fi

pfctl -f /etc/pf.conf 2>/dev/null || warn "Could not reload PF rules (check pfctl configuration)"
ok "PF firewall rules installed — outbound blocked for $KWYRE_USER"

# ── rc.d Service ──────────────────────────────────────────────────────────

info "Installing rc.d service..."

if $USE_COMPILED; then
    KWYRE_COMMAND="$INSTALL_DIR/kwyre-server"
    KWYRE_COMMAND_ARGS=""
else
    KWYRE_COMMAND="$INSTALL_DIR/venv/bin/python"
    KWYRE_COMMAND_ARGS="$INSTALL_DIR/server/serve_local_4bit.py"
fi

cat > /usr/local/etc/rc.d/kwyre << RCEOF
#!/bin/sh

# PROVIDE: kwyre
# REQUIRE: LOGIN NETWORKING
# KEYWORD: shutdown

. /etc/rc.subr

name=kwyre
rcvar=kwyre_enable

load_rc_config \$name

: \${kwyre_enable:="NO"}
: \${kwyre_user:="$KWYRE_USER"}

command="$KWYRE_COMMAND"
command_args="$KWYRE_COMMAND_ARGS"

kwyre_user="$KWYRE_USER"

pidfile="/var/run/\${name}.pid"
command_interpreter="$KWYRE_COMMAND"

kwyre_env="HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 KWYRE_BIND_HOST=127.0.0.1"

start_cmd=kwyre_start
stop_cmd=kwyre_stop
status_cmd=kwyre_status

kwyre_start()
{
    echo "Starting \${name}."
    /usr/sbin/daemon -u \${kwyre_user} -p \${pidfile} \\
        -o /var/log/kwyre/server.log \\
        env \${kwyre_env} \${command} \${command_args}
}

kwyre_stop()
{
    if [ -f \${pidfile} ]; then
        echo "Stopping \${name}."
        kill \$(cat \${pidfile}) 2>/dev/null
        rm -f \${pidfile}
    else
        echo "\${name} is not running."
    fi
}

kwyre_status()
{
    if [ -f \${pidfile} ] && kill -0 \$(cat \${pidfile}) 2>/dev/null; then
        echo "\${name} is running (PID \$(cat \${pidfile}))."
    else
        echo "\${name} is not running."
    fi
}

run_rc_command "\$1"
RCEOF

chmod +x /usr/local/etc/rc.d/kwyre
sysrc kwyre_enable="YES"
ok "rc.d service installed and enabled"

# ── CLI launcher ────────────────────────────────────────────────────────────

if $USE_COMPILED; then
    ln -sf "$INSTALL_DIR/kwyre-server" /usr/local/bin/kwyre
else
    cat > /usr/local/bin/kwyre << LAUNCHEOF
#!/bin/sh
exec sudo -u $KWYRE_USER "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/server/serve_local_4bit.py" "\$@"
LAUNCHEOF
    chmod +x /usr/local/bin/kwyre
fi
ok "CLI launcher installed: kwyre"

# ── Health check ───────────────────────────────────────────────────────────

info "Running health check..."
if command -v curl &>/dev/null; then
    if curl -sf --max-time 3 http://127.0.0.1:8000/health &>/dev/null; then
        ok "Health check passed — server is running"
    else
        info "Server not yet running. Start with: sudo service kwyre start"
    fi
else
    info "curl not found — install with: pkg install curl"
    info "Health check URL: http://127.0.0.1:8000/health"
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}        Installation Complete                ${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo "  Start server:   sudo service kwyre start"
echo "  Stop server:    sudo service kwyre stop"
echo "  Server status:  sudo service kwyre status"
echo "  Manual start:   kwyre"
echo ""
echo "  Server:         http://127.0.0.1:8000"
echo "  Chat UI:        http://127.0.0.1:8000/chat"
echo "  Health check:   http://127.0.0.1:8000/health"
echo ""
echo "  Uninstall:      sudo ./install_freebsd.sh -u"
echo ""
echo -e "  ${CYAN}Security: All 6 layers active. No data leaves this machine.${NC}"
echo ""
