# Kwyre AI — Independent Verification Guide

**Document ID:** KWYRE-VER-001
**Purpose:** Step-by-step procedures for independently verifying every security claim Kwyre makes, without trusting the vendor.

---

## Prerequisites

- Kwyre installed and running on the target machine
- Administrator/root access for network verification
- Wireshark or tcpdump installed (for packet capture)
- 15-30 minutes

---

## Layer 1: Localhost-Only Binding

**Claim:** The server binds to `127.0.0.1` only and is unreachable from any other machine on the network.

### Windows (PowerShell)

```powershell
# Check which address the server is listening on
Get-NetTCPConnection -LocalPort 8000 | Format-Table LocalAddress, LocalPort, State
```

**Expected output:** `LocalAddress` shows `127.0.0.1` only. If you see `0.0.0.0`, the claim is violated.

### Linux / WSL2

```bash
ss -tlnp | grep 8000
```

**Expected output:** `127.0.0.1:8000` — not `0.0.0.0:8000` or `*:8000`.

### Cross-Machine Test

From a different machine on the same network:

```bash
curl http://<kwyre-machine-ip>:8000/health
```

**Expected result:** Connection refused or timeout. If you receive a response, L1 is misconfigured.

---

## Layer 2: Process Outbound Network Block

**Claim:** The inference process cannot make any outbound network connections, even if compromised.

### Wireshark Verification

1. Open Wireshark on the Kwyre machine
2. Capture on all interfaces
3. Apply display filter: `ip.src != 127.0.0.1 and tcp.srcport != 8000`
4. Send several queries to the Kwyre API
5. Wait 60 seconds

**Expected result:** Zero packets from the Python/Kwyre process to any external IP address.

### PowerShell (Windows)

```powershell
# Find the Kwyre process PID
$pid = (Get-Process python | Where-Object { $_.CommandLine -like '*serve_local*' }).Id

# Check all connections for that PID
Get-NetTCPConnection -OwningProcess $pid | Where-Object {
    $_.RemoteAddress -ne '127.0.0.1' -and $_.RemoteAddress -ne '::1'
}
```

**Expected result:** Empty output (no non-localhost connections).

### Linux

```bash
# Find connections from the server process
ss -tp | grep python | grep -v '127.0.0.1'
```

**Expected result:** Empty output.

### Firewall Rule Verification

```powershell
# Windows: verify firewall rules exist
Get-NetFirewallRule -DisplayName "Kwyre-*" | Format-Table DisplayName, Direction, Action, Enabled
```

```bash
# Linux: verify iptables rules exist
sudo iptables -L OUTPUT -v -n | grep kwyre
```

---

## Layer 3: Dependency Integrity

**Claim:** All installed Python packages are verified against a known-good SHA256 manifest at startup.

### Manual Verification

```bash
# Run the dependency verifier directly
python security/verify_deps.py verify
```

**Expected output:** All packages show `[OK]` with matching versions and hashes.

### Tampering Test

```bash
# Intentionally tamper with a package (non-destructive test)
# 1. Note the current hash of a package
python security/verify_deps.py verify-core

# 2. Modify a single byte in a package file
# (e.g., add a comment to transformers/__init__.py)

# 3. Re-run verification
python security/verify_deps.py verify

# Expected: HASH MISMATCH detected for the tampered package
```

### Audit for Unexpected Packages

```bash
python security/verify_deps.py audit
```

**Expected output:** No unexpected packages, or only packages you intentionally installed.

---

## Layer 4: Model Weight Integrity

**Claim:** Model configuration files are verified via SHA256 at every startup.

### Startup Log Verification

Check server startup output for:

```
[Layer 4] Model integrity check: PASSED
```

### Tampering Test

1. Stop the Kwyre server
2. Modify a single character in the model's `config.json`
3. Restart the server

**Expected result:** Server refuses to start with `[Layer 4] ABORTING: Model integrity check failed`.

4. Restore the original file and verify the server starts normally.

---

## Layer 5: RAM-Only Conversation Storage

**Claim:** Conversations are never written to disk. Session wipe overwrites memory with random bytes.

### Disk Artifact Scan

After a conversation session:

```powershell
# Windows: search for any Kwyre-related files modified in last hour
Get-ChildItem -Recurse -Path C:\Users\$env:USERNAME -File |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-1) } |
    Select-String -Pattern "your query text here" -List
```

```bash
# Linux: search for conversation content on disk
grep -r "your query text here" /tmp /var /home --include="*.log" --include="*.txt" --include="*.json"
```

**Expected result:** No matches. Conversation content does not exist on disk.

### Memory Verification (Advanced)

```bash
# After ending a session, dump the Python process memory and search
# (requires gdb or equivalent)
gdb -p <python_pid> -batch -ex "dump memory /tmp/kwyre_mem.bin 0x0 0xFFFFFFFF"
strings /tmp/kwyre_mem.bin | grep "your query text"
```

**Expected result after session wipe:** No readable conversation content in process memory (overwritten with random bytes).

### Audit Endpoint

```bash
curl http://127.0.0.1:8000/audit
```

**Expected output:** JSON with metadata only — session counts, security status. No conversation content.

---

## Layer 6: Intrusion Detection and Auto-Wipe

**Claim:** Opening debugging or traffic analysis tools triggers immediate session wipe and server shutdown.

### Detection Test

1. Start a Kwyre session and send a message
2. Open one of the monitored tools:
   - Wireshark
   - x64dbg
   - Process Hacker
   - Fiddler
3. Wait 10 seconds (watchdog scans every 5 seconds, requires 2 consecutive detections)

**Expected result:** Server process terminates. All sessions are wiped. Server log shows:

```
[Layer 6] INTRUSION DETECTED: <tool_name>
[Layer 6] Emergency wipe: X sessions destroyed
[Layer 6] Server terminated.
```

4. Restart the server. Previous sessions should not exist.

### Watchdog Status

```bash
curl http://127.0.0.1:8000/health
```

**Expected output:** Includes `"intrusion_watchdog": {"running": true, "triggered": false}`.

---

## Zero Telemetry Verification

**Claim:** Kwyre sends zero telemetry, analytics, update checks, or phone-home requests.

### Full Network Capture Test

1. Start Wireshark capturing on all interfaces
2. Start the Kwyre server
3. Wait for full startup
4. Send 10+ queries across multiple sessions
5. End all sessions
6. Stop the server
7. Stop Wireshark capture

**Apply filter:** `ip.dst != 127.0.0.1`

**Expected result:** Zero packets. The only network traffic should be `127.0.0.1 ↔ 127.0.0.1`.

### DNS Verification

```bash
# Monitor DNS queries during Kwyre operation
sudo tcpdump -i any port 53 -n
```

**Expected result:** Zero DNS queries originating from the Kwyre process. The server makes no hostname lookups because it has no reason to contact any external server.

---

## Verification Checklist

| # | Layer | Test | Result |
|---|-------|------|--------|
| 1 | L1 | Server binds to 127.0.0.1 only | [ ] PASS / [ ] FAIL |
| 2 | L1 | Unreachable from another machine | [ ] PASS / [ ] FAIL |
| 3 | L2 | Zero non-localhost outbound connections | [ ] PASS / [ ] FAIL |
| 4 | L2 | Firewall rules in place | [ ] PASS / [ ] FAIL |
| 5 | L3 | Dependency manifest verification passes | [ ] PASS / [ ] FAIL |
| 6 | L3 | Tampered package detected | [ ] PASS / [ ] FAIL |
| 7 | L4 | Model integrity check passes at startup | [ ] PASS / [ ] FAIL |
| 8 | L4 | Tampered config detected and blocked | [ ] PASS / [ ] FAIL |
| 9 | L5 | No conversation content on disk | [ ] PASS / [ ] FAIL |
| 10 | L5 | Audit endpoint shows metadata only | [ ] PASS / [ ] FAIL |
| 11 | L6 | Debug tool triggers shutdown + wipe | [ ] PASS / [ ] FAIL |
| 12 | L6 | Watchdog running per health endpoint | [ ] PASS / [ ] FAIL |
| 13 | -- | Zero outbound packets during full session | [ ] PASS / [ ] FAIL |
| 14 | -- | Zero DNS queries from process | [ ] PASS / [ ] FAIL |

**Auditor:** _________________________ **Date:** _____________

**Organization:** _________________________ **Signature:** _____________

---

*This verification can be performed entirely by the customer or their auditor without any involvement from Apollo CyberSentinel LLC. No vendor cooperation, credentials, or special access is required.*
