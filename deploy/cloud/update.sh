#!/usr/bin/env bash
# Kwyre Cloud — Pull latest code and restart the server
# Usage: ssh root@165.227.47.89 'bash -s' < deploy/cloud/update.sh
set -euo pipefail

KWYRE_HOME="/opt/kwyre"

echo "[update] Pulling latest code..."
cd ${KWYRE_HOME}/repo
sudo -u kwyre git pull --ff-only

echo "[update] Restarting kwyre service..."
systemctl restart kwyre

echo "[update] Waiting for health check..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "[update] Server healthy after ${i}s"
        curl -s http://localhost:8000/health | jq .
        exit 0
    fi
    sleep 2
done

echo "[update] WARNING: Server did not become healthy within 60s"
echo "[update] Check logs: journalctl -u kwyre -n 50"
exit 1
