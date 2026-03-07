#!/usr/bin/env bash
# =============================================================================
# Kwyre Layer 2: Process Network Isolation
# =============================================================================
# Prevents the Kwyre inference server from making ANY outbound connections,
# even if the process is compromised.
#
# Two approaches:
#   A) WSL2 / Linux: iptables rules scoped to the server process UID
#   B) Windows:      netsh / Windows Firewall rules (run from PowerShell)
#
# Usage:
#   chmod +x setup_isolation.sh
#   sudo ./setup_isolation.sh install     # Install rules
#   sudo ./setup_isolation.sh remove      # Remove rules
#   sudo ./setup_isolation.sh status      # Check current rules
# =============================================================================

KWYRE_USER="kwyre"
KWYRE_PORT=8000
SCRIPT_NAME="Kwyre-NetworkIsolation"

# ---------------------------------------------------------------------------
# Detect environment
# ---------------------------------------------------------------------------
is_wsl() {
    grep -qi microsoft /proc/version 2>/dev/null
}

# ---------------------------------------------------------------------------
# APPROACH A: WSL2 / Linux iptables isolation
# ---------------------------------------------------------------------------
# Creates a dedicated system user "kwyre" with no shell and no home dir.
# iptables OUTPUT rules block all outbound traffic from that UID except
# to 127.0.0.1 (localhost).
# The server process runs as this user — even if fully compromised,
# it cannot reach the internet.

install_linux() {
    echo "[Layer 2] Installing Linux/WSL2 network isolation..."

    # Create restricted system user if not exists
    if ! id "$KWYRE_USER" &>/dev/null; then
        useradd --system --no-create-home --shell /usr/sbin/nologin "$KWYRE_USER"
        echo "[Layer 2] Created restricted user: $KWYRE_USER"
    else
        echo "[Layer 2] User $KWYRE_USER already exists."
    fi

    KWYRE_UID=$(id -u "$KWYRE_USER")
    echo "[Layer 2] Kwyre UID: $KWYRE_UID"

    # Flush any existing Kwyre rules
    remove_linux_quiet

    # Block ALL outbound traffic from kwyre UID
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP

    # Allow loopback (127.0.0.1) — server needs to accept localhost connections
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" \
        -d 127.0.0.1 -j ACCEPT

    # Allow established/related (responses to incoming localhost requests)
    iptables -I OUTPUT -m owner --uid-owner "$KWYRE_UID" \
        -m state --state ESTABLISHED,RELATED -j ACCEPT

    echo "[Layer 2] iptables rules installed for UID $KWYRE_UID"
    echo "[Layer 2] All outbound blocked except 127.0.0.1"

    # Make rules persist across reboots
    if command -v iptables-save &>/dev/null; then
        RULES_FILE="/etc/iptables/rules.v4"
        mkdir -p /etc/iptables
        iptables-save > "$RULES_FILE"
        echo "[Layer 2] Rules persisted to $RULES_FILE"
    fi

    # Create wrapper script to launch server as kwyre user
    cat > /usr/local/bin/kwyre-serve << 'EOF'
#!/usr/bin/env bash
# Kwyre server launcher — runs inference process as restricted user
KWYRE_DIR="$(dirname "$(readlink -f "$0")")/../kwyre"
exec sudo -u kwyre python "$KWYRE_DIR/serve_local_4bit.py" "$@"
EOF
    chmod +x /usr/local/bin/kwyre-serve

    echo "[Layer 2] Done. Launch server with: kwyre-serve"
    echo "[Layer 2] Or manually: sudo -u $KWYRE_USER python serve_local_4bit.py"
}

remove_linux_quiet() {
    KWYRE_UID=$(id -u "$KWYRE_USER" 2>/dev/null) || return
    # Remove all rules matching kwyre UID silently
    while iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -j DROP 2>/dev/null; do :; done
    while iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -d 127.0.0.1 -j ACCEPT 2>/dev/null; do :; done
    while iptables -D OUTPUT -m owner --uid-owner "$KWYRE_UID" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null; do :; done
}

remove_linux() {
    echo "[Layer 2] Removing Linux/WSL2 isolation rules..."
    remove_linux_quiet
    echo "[Layer 2] Rules removed."
}

status_linux() {
    echo "[Layer 2] Current iptables OUTPUT rules:"
    iptables -L OUTPUT -v -n --line-numbers | grep -E "(kwyre|owner|DROP|ACCEPT)" || echo "  (no kwyre rules found)"
}

# ---------------------------------------------------------------------------
# APPROACH B: Windows Firewall rules
# Print PowerShell commands the user runs once in an elevated prompt.
# ---------------------------------------------------------------------------
print_windows_rules() {
    cat << 'WINEOF'
# =============================================================================
# Kwyre Layer 2: Windows Firewall Isolation
# Run the following in an ELEVATED PowerShell prompt (Run as Administrator)
# =============================================================================

# --- INSTALL ---
# Block ALL outbound connections for python.exe in the Kwyre venv
$kwyrePath = "C:\Users\$env:USERNAME\kwyre\venv\Scripts\python.exe"

# Remove old rules if they exist
Remove-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" -ErrorAction SilentlyContinue

# Block all outbound from Kwyre python
New-NetFirewallRule `
    -DisplayName "Kwyre-BlockOutbound" `
    -Direction Outbound `
    -Action Block `
    -Program $kwyrePath `
    -Profile Any

# Allow outbound to localhost only (127.0.0.1)
New-NetFirewallRule `
    -DisplayName "Kwyre-AllowLocalhost" `
    -Direction Outbound `
    -Action Allow `
    -Program $kwyrePath `
    -RemoteAddress "127.0.0.1" `
    -Profile Any

Write-Host "[Layer 2] Windows Firewall rules installed."
Write-Host "[Layer 2] Kwyre python.exe blocked from all outbound except localhost."

# --- VERIFY ---
Get-NetFirewallRule -DisplayName "Kwyre-*" | Format-Table DisplayName, Direction, Action, Enabled

# --- REMOVE (when needed) ---
# Remove-NetFirewallRule -DisplayName "Kwyre-BlockOutbound"
# Remove-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost"
WINEOF
}

# ---------------------------------------------------------------------------
# APPROACH C: WSL2 + Windows combined (recommended for your setup)
# ---------------------------------------------------------------------------
print_wsl2_combined() {
    echo ""
    echo "======================================================================"
    echo "  Your environment: WSL2 on Windows"
    echo "  Recommended: Apply BOTH Linux iptables AND Windows Firewall rules"
    echo "======================================================================"
    echo ""
    echo "  Step 1: Run this script with 'install' (applies iptables in WSL2)"
    echo "  Step 2: Also apply Windows Firewall rules (printed below)"
    echo "          to block the WSL2 Python process at the Windows network layer"
    echo ""
    print_windows_rules
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "${1:-help}" in
    install)
        if [ "$EUID" -ne 0 ]; then
            echo "Error: Run with sudo"
            exit 1
        fi
        if is_wsl; then
            echo "[Layer 2] WSL2 detected."
            install_linux
            echo ""
            echo "======================================================================"
            echo "  IMPORTANT: Also apply Windows Firewall rules for full protection."
            echo "  Run: sudo ./setup_isolation.sh windows"
            echo "======================================================================"
        else
            install_linux
        fi
        ;;
    remove)
        if [ "$EUID" -ne 0 ]; then echo "Error: Run with sudo"; exit 1; fi
        remove_linux
        ;;
    status)
        status_linux
        ;;
    windows)
        print_windows_rules
        ;;
    wsl2)
        print_wsl2_combined
        ;;
    help|*)
        echo "Usage: sudo ./setup_isolation.sh [install|remove|status|windows|wsl2]"
        echo ""
        echo "  install  — Install iptables isolation rules (Linux/WSL2)"
        echo "  remove   — Remove isolation rules"
        echo "  status   — Show current rules"
        echo "  windows  — Print Windows Firewall PowerShell commands"
        echo "  wsl2     — Print combined WSL2 + Windows instructions"
        echo ""
        echo "Your environment is WSL2. Run: sudo ./setup_isolation.sh wsl2"
        ;;
esac
