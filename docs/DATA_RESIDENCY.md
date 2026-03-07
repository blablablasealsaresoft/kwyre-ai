# Kwyre Data Residency & Privacy Architecture

## Summary

All inference processing occurs exclusively on the user's local hardware.
No data, queries, or responses are transmitted to any external server.
This document describes the technical controls that enforce this guarantee.

## Data Flow

```
[User Input] --> [Local RAM] --> [Local GPU] --> [Local RAM] --> [User Output]
                                    |
                        No network path exists
```

Every stage of the inference pipeline executes within the user's own machine.
There is no cloud component, no telemetry endpoint, no update server.

## Technical Controls

| Layer | Control | Implementation |
|-------|---------|----------------|
| L1 | Network binding | Server binds to `127.0.0.1` only -- OS-level enforcement, unreachable from LAN or internet |
| L2 | Outbound firewall | Process-scoped outbound block via `iptables` (Linux/WSL2) and Windows Firewall rules -- even a fully compromised server process cannot reach the internet |
| L3 | Dependency integrity | SHA256 manifest of all installed Python packages verified at every startup -- detects supply-chain tampering |
| L4 | Weight integrity | SHA256 hashes of model configuration files verified at every startup -- detects model substitution or tampering |
| L5 | Conversation storage | RAM only -- conversations are never written to disk, never logged, never persisted in any form |
| L5a | Session wipe | Cryptographic overwrite (random bytes) of conversation buffer on session end, idle timeout (1 hour), server shutdown, or intrusion detection |
| L6 | Intrusion detection | Background watchdog monitors for debugging tools, traffic analyzers, and unexpected outbound connections -- triggers immediate session wipe and process termination on confirmed violation |
| -- | Telemetry | **None.** Zero analytics, zero error reporting, zero update checks, zero phone-home of any kind |

## Conversation Lifecycle

1. **Creation**: Client sends first message with a `session_id`. Server creates an in-memory `SecureConversationBuffer` with a per-session 256-bit random key.

2. **Usage**: Messages are appended to the RAM buffer. The buffer is accessed only by the inference thread handling that session.

3. **Termination** (any of the following triggers):
   - Client calls `POST /v1/session/end` with the session ID
   - Session idle for >1 hour (automatic reaping)
   - Server process shuts down (graceful `SIGTERM` handler)
   - Intrusion watchdog triggers lockdown

4. **Wipe procedure**:
   - Every message's content is overwritten with `secrets.token_hex()` random bytes
   - Every message's role field is overwritten with random bytes
   - The message list is cleared
   - The per-session key is zeroed
   - The buffer object is dereferenced for garbage collection
   - The wipe is logged as metadata only (session ID prefix + message count + reason)

**No conversation content is ever written to the wipe log or any other log.**

## Audit Endpoint

`GET /audit` returns metadata-only compliance information:

```json
{
  "server": "kwyre-9b-spikeserve",
  "timestamp": "2026-03-07T12:00:00Z",
  "active_sessions": 1,
  "security_controls": {
    "network_binding": "127.0.0.1:8000 (localhost only)",
    "weight_integrity": "enabled",
    "conversation_storage": "RAM-only",
    "session_wipe": "on_close + idle_timeout_1hr + shutdown + intrusion",
    "intrusion_watchdog": { "running": true, "triggered": false },
    "content_logging": "NEVER"
  },
  "note": "Metadata only. No conversation content is ever logged or persisted."
}
```

## Independent Verification

Users and auditors can independently verify zero outbound network activity:

| Platform | Command |
|----------|---------|
| Windows | Resource Monitor > Network tab -- filter by `python.exe` |
| Windows (PowerShell) | `Get-NetTCPConnection -OwningProcess (Get-Process python).Id` |
| Linux / WSL2 | `ss -tp \| grep python` |
| Any platform | Wireshark capture on all interfaces -- only `127.0.0.1` traffic visible |

## What Kwyre Does NOT Do

- Does NOT send queries to any API (OpenAI, Anthropic, Google, or otherwise)
- Does NOT phone home for updates, analytics, or crash reports
- Does NOT write conversation content to disk (no logs, no database, no temp files)
- Does NOT require an internet connection after initial model download
- Does NOT transmit model weights, activations, or inference results off-device
- Does NOT collect or store any user-identifiable information

## Regulatory Alignment

This architecture is designed to satisfy requirements under:

- **GDPR** Article 25 (Data Protection by Design) -- personal data never leaves the controller's infrastructure
- **HIPAA** Technical Safeguards -- encryption at rest is moot when data is never at rest; access controls are OS-level process isolation
- **SOC 2 Type II** -- audit trail via `/audit` endpoint, access controls via API key authentication, data handling via RAM-only storage
- **ITAR / EAR** -- no data export occurs because no data leaves the machine
- **Attorney-Client Privilege** -- conversations never traverse third-party infrastructure

## Contact

For security architecture questions or compliance audits: security@kwyre.com
