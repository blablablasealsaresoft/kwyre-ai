# Kwyre Security Architecture

## Overview

Kwyre implements a 6-layer defense-in-depth security model for local LLM inference.
Each layer operates independently -- compromising one layer does not disable the others.

```
+------------------------------------------------------+
|  Layer 6: Intrusion Watchdog                         |
|    Monitors processes + network, auto-wipes on alert |
+------------------------------------------------------+
|  Layer 5: Secure Conversation Buffer                 |
|    RAM-only storage, cryptographic wipe on close     |
+------------------------------------------------------+
|  Layer 4: Model Weight Integrity                     |
|    SHA256 verification of model files at startup     |
+------------------------------------------------------+
|  Layer 3: Dependency Integrity                       |
|    SHA256 manifest of all Python packages at startup |
+------------------------------------------------------+
|  Layer 2: Process Network Isolation                  |
|    iptables / Windows Firewall per-process rules     |
+------------------------------------------------------+
|  Layer 1: Localhost-Only Binding                     |
|    Server binds to 127.0.0.1, unreachable from LAN  |
+------------------------------------------------------+
```

## Layer 1: Localhost-Only Network Binding

**File**: `server/serve_local_4bit.py` -- `BIND_HOST = "127.0.0.1"`

The HTTP server binds exclusively to the loopback interface. This is enforced at
the OS socket level -- no configuration, reverse proxy, or firewall rule can make
the server respond to requests from other machines on the network.

**Verification**: `netstat -an | findstr 8000` shows `127.0.0.1:8000` only.

## Layer 2: Process Network Isolation

**File**: `security/setup_isolation.sh`

Even if the server process is fully compromised (e.g., via a dependency supply-chain
attack), it cannot exfiltrate data because outbound network access is blocked at
the OS level.

- **Linux/WSL2**: `iptables` OUTPUT rules scoped to a dedicated `kwyre` system user UID
- **Windows**: `New-NetFirewallRule` blocking outbound from the specific Python executable

The server runs as the `kwyre` user, which has no shell, no home directory, and
no outbound network capability.

## Layer 3: Dependency Integrity

**File**: `security/verify_deps.py`

Generates and verifies SHA256 hashes of all installed Python packages' `RECORD`
files. Detects:

- Version changes (pip upgrade/downgrade)
- File tampering (modified package code)
- Unexpected packages (not in the original manifest)

Run once on a clean install to generate the manifest, then verify at every startup.

## Layer 4: Model Weight Integrity

**File**: `server/serve_local_4bit.py` -- `verify_model_integrity()`

SHA256 hashes of model configuration files (`config.json`, `tokenizer_config.json`,
`generation_config.json`, `tokenizer.json`) are computed on a verified clean install
and hardcoded into the server. At every startup, hashes are recomputed and compared.

Detects: model substitution, config tampering, file corruption.

## Layer 5: Secure Conversation Buffer

**File**: `server/serve_local_4bit.py` -- `SecureConversationBuffer`, `SessionStore`

- Conversations exist only in RAM -- never serialized to disk
- Each session gets a 256-bit random key (for future encryption-at-rest if needed)
- Idle sessions are reaped after 1 hour
- On wipe: content overwritten with random bytes before deallocation
- On server shutdown: all sessions wiped before process exit (`SIGTERM` handler)

## Layer 6: Intrusion Watchdog

**File**: `server/serve_local_4bit.py` -- `IntrusionWatchdog`

Background thread scanning every 5 seconds for:

1. **Unexpected outbound connections** from the server process (via `psutil`)
2. **Suspicious processes** running on the system (debuggers, traffic analyzers, etc.)

On confirmed violation (2 consecutive detections to avoid false positives):
- All active sessions are immediately wiped
- Event is logged (metadata only)
- Server process is terminated

Detected tools include: x64dbg, WinDbg, Ghidra, IDA, Wireshark, Fiddler,
mitmproxy, Burp Suite, Process Hacker, Cheat Engine.

## Threat Model

| Threat | Mitigated By |
|--------|-------------|
| Network interception (MITM) | L1 + L2: No network traffic exists to intercept |
| Remote access to inference | L1: Localhost binding blocks all remote connections |
| Data exfiltration via compromised dependency | L2 + L3: Outbound blocked + dependency hashes verified |
| Model substitution / poisoning | L4: SHA256 weight verification at startup |
| Conversation persistence / disk forensics | L5: RAM-only with cryptographic wipe |
| Active debugging / memory inspection | L6: Watchdog detects and terminates |
| Server crash without cleanup | L5: OS reclaims RAM on process exit -- no disk artifacts |

## What This Architecture Does NOT Protect Against

- Physical access to the machine while the server is running (cold boot attacks, DMA)
- Kernel-level rootkits that hide processes from `psutil`
- A determined attacker with root/admin access to the host OS
- Side-channel attacks on GPU memory

These threats require hardware-level controls (TPM, Secure Boot, encrypted RAM)
which are outside the scope of application-level security.
