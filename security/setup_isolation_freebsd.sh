#!/usr/bin/env bash
# =============================================================================
# Kwyre Layer 2: Process Network Isolation (FreeBSD PF)
# =============================================================================
# Prevents the Kwyre inference server from making ANY outbound connections,
# even if the process is compromised. Uses FreeBSD's PF (Packet Filter)
# with user-scoped anchor rules.
#
# Usage:
#   chmod +x setup_isolation_freebsd.sh
#   sudo ./setup_isolation_freebsd.sh install     # Install PF rules + user
#   sudo ./setup_isolation_freebsd.sh remove      # Remove PF rules + user
#   sudo ./setup_isolation_freebsd.sh status      # Check current state
# =============================================================================

set -euo pipefail

KWYRE_USER="kwyre"
PF_ANCHOR_NAME="kwyre"
PF_ANCHOR_FILE="/etc/pf.anchors/kwyre"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[Layer 2]${NC} $*"; }
ok()    { echo -e "${GREEN}[Layer 2]${NC} $*"; }
warn()  { echo -e "${YELLOW}[Layer 2]${NC} $*"; }
fail()  { echo -e "${RED}[Layer 2]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# install — create user, write PF anchor, reload pfctl
# ---------------------------------------------------------------------------
do_install() {
    info "Installing FreeBSD PF network isolation..."

    if ! pw usershow "$KWYRE_USER" &>/dev/null 2>&1; then
        pw useradd "$KWYRE_USER" -d /nonexistent -s /usr/sbin/nologin -c "Kwyre AI Service"
        ok "Created restricted user: $KWYRE_USER"
    else
        ok "User $KWYRE_USER already exists"
    fi

    KWYRE_UID=$(id -u "$KWYRE_USER")
    info "Kwyre UID: $KWYRE_UID"

    info "Writing PF anchor to $PF_ANCHOR_FILE..."
    cat > "$PF_ANCHOR_FILE" << 'PFEOF'
# Kwyre AI — Block all outbound traffic from kwyre user except loopback
block out quick on ! lo0 proto { tcp, udp } user kwyre
pass out quick on lo0 proto { tcp, udp } user kwyre
PFEOF

    if ! grep -q "anchor \"$PF_ANCHOR_NAME\"" /etc/pf.conf 2>/dev/null; then
        echo "" >> /etc/pf.conf
        echo "anchor \"$PF_ANCHOR_NAME\"" >> /etc/pf.conf
        echo "load anchor \"$PF_ANCHOR_NAME\" from \"$PF_ANCHOR_FILE\"" >> /etc/pf.conf
        ok "PF anchor added to /etc/pf.conf"
    else
        ok "PF anchor already present in /etc/pf.conf"
    fi

    pfctl -f /etc/pf.conf 2>/dev/null || warn "Could not reload PF (check pfctl configuration)"

    ok "PF rules installed for user $KWYRE_USER (UID $KWYRE_UID)"
    ok "All outbound blocked except loopback (lo0)"
    echo ""
    info "Launch server with: sudo -u $KWYRE_USER python serve_local_4bit.py"
}

# ---------------------------------------------------------------------------
# remove — remove PF anchor, optionally remove user
# ---------------------------------------------------------------------------
do_remove() {
    info "Removing FreeBSD PF isolation rules..."

    if [ -f "$PF_ANCHOR_FILE" ]; then
        rm -f "$PF_ANCHOR_FILE"
        ok "Removed anchor file: $PF_ANCHOR_FILE"
    else
        info "Anchor file not found (already removed)"
    fi

    if grep -q "anchor \"$PF_ANCHOR_NAME\"" /etc/pf.conf 2>/dev/null; then
        sed -i '' "/anchor \"$PF_ANCHOR_NAME\"/d" /etc/pf.conf 2>/dev/null || \
            sed -i "/anchor \"$PF_ANCHOR_NAME\"/d" /etc/pf.conf 2>/dev/null || true
        sed -i '' "/load anchor \"$PF_ANCHOR_NAME\"/d" /etc/pf.conf 2>/dev/null || \
            sed -i "/load anchor \"$PF_ANCHOR_NAME\"/d" /etc/pf.conf 2>/dev/null || true
        pfctl -f /etc/pf.conf 2>/dev/null || true
        ok "PF anchor removed from /etc/pf.conf"
    else
        info "No PF anchor found in /etc/pf.conf"
    fi

    if pw usershow "$KWYRE_USER" &>/dev/null 2>&1; then
        pw userdel "$KWYRE_USER" 2>/dev/null || true
        ok "Removed user: $KWYRE_USER"
    else
        info "User $KWYRE_USER not found (already removed)"
    fi

    ok "Isolation rules removed."
}

# ---------------------------------------------------------------------------
# status — show current PF rules, user, and process state
# ---------------------------------------------------------------------------
do_status() {
    echo ""
    echo -e "${CYAN}── Kwyre PF Isolation Status ─────────────────────────${NC}"
    echo ""

    echo -e "${CYAN}User:${NC}"
    if pw usershow "$KWYRE_USER" &>/dev/null 2>&1; then
        KWYRE_UID=$(id -u "$KWYRE_USER")
        echo "  $KWYRE_USER exists (UID $KWYRE_UID)"
    else
        echo "  $KWYRE_USER does not exist"
    fi
    echo ""

    echo -e "${CYAN}PF Anchor File:${NC}"
    if [ -f "$PF_ANCHOR_FILE" ]; then
        echo "  $PF_ANCHOR_FILE exists"
        echo "  Contents:"
        sed 's/^/    /' "$PF_ANCHOR_FILE"
    else
        echo "  $PF_ANCHOR_FILE not found"
    fi
    echo ""

    echo -e "${CYAN}PF Configuration:${NC}"
    if grep -q "anchor \"$PF_ANCHOR_NAME\"" /etc/pf.conf 2>/dev/null; then
        echo "  Anchor present in /etc/pf.conf"
    else
        echo "  Anchor NOT present in /etc/pf.conf"
    fi
    echo ""

    echo -e "${CYAN}Active PF Rules (kwyre anchor):${NC}"
    pfctl -a "$PF_ANCHOR_NAME" -sr 2>/dev/null | sed 's/^/  /' || echo "  (no active rules or pfctl not available)"
    echo ""

    echo -e "${CYAN}Kwyre Process:${NC}"
    if pgrep -u "$KWYRE_USER" &>/dev/null 2>&1; then
        pgrep -lu "$KWYRE_USER" | sed 's/^/  /'
    else
        echo "  No processes running as $KWYRE_USER"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
case "${1:-help}" in
    install)
        if [ "$(id -u)" -ne 0 ]; then
            fail "Run with sudo: sudo ./setup_isolation_freebsd.sh install"
        fi
        do_install
        ;;
    remove)
        if [ "$(id -u)" -ne 0 ]; then
            fail "Run with sudo: sudo ./setup_isolation_freebsd.sh remove"
        fi
        do_remove
        ;;
    status)
        do_status
        ;;
    help|*)
        echo "Usage: sudo ./setup_isolation_freebsd.sh [install|remove|status|help]"
        echo ""
        echo "  install  — Create kwyre user, install PF firewall anchor rules"
        echo "  remove   — Remove PF rules and kwyre user"
        echo "  status   — Show current isolation state (rules, user, process)"
        echo "  help     — Show this message"
        echo ""
        ;;
esac
