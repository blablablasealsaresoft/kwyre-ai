# Kwyre AI — SOC 2 Type II Deployment Guide

**Document ID:** KWYRE-SOC2-001
**Version:** 1.0
**Effective Date:** March 2026
**Issuer:** Apollo CyberSentinel LLC
**Classification:** Customer-Facing — For Auditors and Compliance Teams

---

## 1. Purpose

This guide maps Kwyre AI's 6-layer security architecture to SOC 2 Type II Trust Service Criteria, provides a pre-deployment hardening checklist for SOC 2 environments, and documents the evidence artifacts Kwyre produces for auditor review.

Kwyre is a locally-deployed, air-gapped AI inference server. Because all processing occurs on the customer's own hardware with zero external data transmission, many traditional SOC 2 controls (cloud access management, vendor risk, data-in-transit encryption) are rendered unnecessary by architectural elimination of the attack surface.

---

## 2. Trust Service Criteria Mapping

### 2.1 CC6 — Logical and Physical Access Controls

#### CC6.1 — Logical and Physical Access Controls

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L1 — Network Binding** | Server binds exclusively to `127.0.0.1` at the OS socket level. No configuration, reverse proxy, or firewall rule can expose the server to LAN or internet traffic. | `netstat -an \| findstr 8000` shows `127.0.0.1:8000` only. Cross-machine connection attempts fail. |
| **L2 — Process Isolation** | OS-level firewall rules (iptables on Linux, Windows Firewall on Windows) block all outbound network connections from the inference process. Even a fully compromised server cannot exfiltrate data. | `Get-NetFirewallRule -DisplayName "Kwyre-*"` (Windows) or `iptables -L OUTPUT` (Linux) shows per-process outbound deny rules. |
| **API Key Auth** | All inference and audit endpoints require `Authorization: Bearer <key>` headers. Keys validated with `hmac.compare_digest` (timing-safe). | Unauthenticated requests return HTTP 401. `/health` returns limited info without auth. |

**How this satisfies CC6.1:** Access to the inference system is restricted to processes running on the same machine (L1) and authenticated via API key. No remote access path exists. The process itself cannot establish outbound connections (L2), preventing data exfiltration even under full server compromise.

#### CC6.6 — System Boundaries

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L1 + L2** | The system boundary is the loopback interface (`127.0.0.1`). No data crosses this boundary in either direction. Inbound: server only accepts localhost connections. Outbound: process-level firewall blocks all egress. | Wireshark capture during full operational session shows zero non-localhost packets. Zero DNS queries from process. |

**How this satisfies CC6.6:** The system boundary is defined and enforced at two independent layers. L1 prevents inbound access from outside the machine. L2 prevents outbound access from the inference process. Together they create a true air gap at the application and OS level.

#### CC6.7 — Data in Transit

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L1 — Localhost Binding** | All data transit occurs exclusively over the loopback interface (`127.0.0.1 → 127.0.0.1`). Loopback traffic never touches a physical network interface, NIC, or wire. There is no network path for interception. | Wireshark capture on physical interfaces shows zero Kwyre-related traffic. All communication is loopback-only. |

**How this satisfies CC6.7:** Traditional transit encryption (TLS) protects data traversing networks. Kwyre eliminates the need for transit encryption by eliminating transit. Data never leaves the machine's memory space. Loopback traffic is not routable and cannot be intercepted by network-based attackers.

#### CC6.8 — Data at Rest

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L5 — Secure RAM Buffer** | Conversations exist only in volatile RAM. No conversation content is ever written to disk, database, log file, temp file, or any persistent storage. On session end, content is overwritten with `secrets.token_hex()` random bytes before deallocation. | Disk search for conversation content returns zero matches. `/audit` endpoint confirms `"content_logging": "NEVER"`. |

**How this satisfies CC6.8:** Kwyre eliminates data at rest by never creating it. Conversations are volatile — they exist only in RAM during active sessions and are cryptographically destroyed on termination. There is no persistent data to encrypt, protect, or manage retention for.

---

### 2.2 CC7 — System Operations

#### CC7.1 — System Monitoring

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L6 — Intrusion Watchdog** | Background thread scans every 5 seconds for: (1) unexpected outbound connections from the inference process, (2) known debugging/traffic analysis tools (Wireshark, x64dbg, Ghidra, IDA, Fiddler, mitmproxy, Burp Suite, Process Hacker, etc.). Two consecutive detections required before triggering to prevent false positives. | `/health` endpoint shows `"intrusion_watchdog": {"running": true, "triggered": false}`. Server logs show scan activity. |
| **Audit Endpoint** | `GET /audit` returns metadata-only compliance log: active sessions, security control status, watchdog state. No conversation content is ever included. | Audit output is JSON with timestamps, session counts, and control attestation. |

**How this satisfies CC7.1:** The system continuously monitors for both internal anomalies (unexpected outbound connections indicating compromise) and external threats (debugging/analysis tools indicating active attack). Monitoring is automated, continuous, and produces auditable metadata.

#### CC7.2 — Incident Response

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L6 — Auto-Wipe** | On confirmed intrusion: (1) all active sessions enumerated, (2) every message overwritten with random bytes, (3) session keys zeroed, (4) session objects dereferenced, (5) event logged (metadata only), (6) server process terminated. Total time from detection to wipe: < 2 seconds. | `INCIDENT_RESPONSE.md` documents classification, automated response, manual follow-up procedures, and reporting templates. |
| **INCIDENT_RESPONSE.md** | Documented procedures for all severity levels (Critical/High/Medium/Low). Includes escalation contacts, data breach assessment, and incident log templates. | Document is versioned in the compliance package and reviewed quarterly. |

**How this satisfies CC7.2:** Incident response is both automated (immediate cryptographic destruction of sensitive data) and documented (manual follow-up procedures for root cause analysis). The automated component eliminates human latency in the most critical scenarios.

---

### 2.3 CC8 — Change Management

#### CC8.1 — Change Management

| Kwyre Layer | Implementation | Evidence |
|-------------|---------------|----------|
| **L3 — Dependency Integrity** | SHA256 hash manifest of every installed Python package generated on clean install. Verified at every server startup. Detects: version changes, file tampering, unexpected packages. Any mismatch aborts startup immediately. | `python security/verify_deps.py verify` output shows per-package hash verification. Manifest stored at `security/kwyre_dep_manifest.json`. |
| **L4 — Model Weight Integrity** | SHA256 hashes of model configuration files (`config.json`, `tokenizer_config.json`, `generation_config.json`, `tokenizer.json`) hardcoded in server. Verified at every startup. Any mismatch aborts startup. | Server startup log shows `[Layer 4] Model integrity check: PASSED` or `FAILED`. |

**How this satisfies CC8.1:** All software components (dependencies and model weights) are cryptographically baselined and verified before every execution. Unauthorized changes — whether from supply-chain attacks, accidental upgrades, or deliberate tampering — are detected and blocked before any inference occurs.

---

### 2.4 CC3 — Risk Assessment

#### CC3.1 — Risk Assessment

| Activity | Details | Evidence |
|----------|---------|----------|
| **White-Box Penetration Test** | Full security audit of Kwyre v0.3 conducted with complete source code access. 47 findings identified across all severity levels. | Pentest report with finding details, severity classifications, and remediation verification. |
| **Finding Resolution** | All 47 findings resolved: 9 Critical, 12 High, 14 Medium, 12 Low/Informational. Zero open findings. | Individual finding remediation documented with code changes and re-test confirmation. |
| **Security Test Suite** | 107 automated security tests across 3 test files covering authentication, session management, input validation, intrusion detection, and integrity verification. | `pytest tests/` — all 107 tests passing. Test coverage documented. |
| **Threat Model** | Documented threat model covering network interception, remote access, data exfiltration, model poisoning, disk forensics, active debugging, and crash scenarios. | `SECURITY_ARCHITECTURE.md` — Threat Model section with layer-by-layer mitigation mapping. |

**How this satisfies CC3.1:** Risk has been systematically assessed through professional penetration testing with 100% finding remediation, a comprehensive threat model with documented mitigations, and an automated regression test suite that runs on every build.

---

## 3. Pre-Deployment Checklist for SOC 2 Environments

### Phase 1: Environment Preparation

- [ ] **Dedicated machine identified** — Kwyre runs on a single-purpose machine or VM
- [ ] **OS hardened** — latest security patches applied, unnecessary services disabled
- [ ] **Disk encryption enabled** — BitLocker (Windows) or LUKS (Linux) for model weight protection
- [ ] **Physical access controls documented** — machine location, access restrictions, visitor logs
- [ ] **Network segmentation confirmed** — machine on restricted VLAN or fully air-gapped
- [ ] **Administrative access restricted** — only authorized personnel have OS-level login

### Phase 2: Kwyre Installation

- [ ] **Clean Python environment created** — dedicated venv, no shared packages
- [ ] **Dependencies installed from locked requirements** — `pip install -r requirements-inference.txt`
- [ ] **Dependency manifest generated** — `python security/verify_deps.py generate`
- [ ] **Manifest committed to version control** with reviewer approval
- [ ] **Model weights downloaded and verified** — SHA256 hashes recorded
- [ ] **Pre-quantized models deployed** (if using Kwyre distribution packages)

### Phase 3: Security Stack Verification

- [ ] **L1 verified** — `netstat` confirms `127.0.0.1:8000` binding only
- [ ] **L1 cross-machine test** — connection from another machine fails
- [ ] **L2 installed** — firewall rules block process outbound (iptables/Windows Firewall)
- [ ] **L2 verified** — `Get-NetFirewallRule` or `iptables -L` shows Kwyre rules active
- [ ] **L3 verified** — `verify_deps.py verify` shows all packages `[OK]`
- [ ] **L4 verified** — server startup log shows `[Layer 4] Model integrity check: PASSED`
- [ ] **L5 verified** — disk search for conversation content returns zero results
- [ ] **L6 verified** — `/health` shows `"intrusion_watchdog": {"running": true}`
- [ ] **L6 trigger test** — opening monitored tool causes server shutdown (optional but recommended)

### Phase 4: Authentication and Access Control

- [ ] **Production API keys generated** — `secrets.token_hex(32)` minimum entropy
- [ ] **Development keys removed** — `sk-kwyre-dev-local` is not in production config
- [ ] **Key distribution documented** — who has keys, when issued, revocation procedure
- [ ] **Unauthenticated access confirmed blocked** — requests without Bearer token return 401
- [ ] **Eval tier enforcement confirmed** — unlicensed usage is rate-limited

### Phase 5: Network Verification

- [ ] **Full Wireshark capture test** — 10+ queries sent, zero non-localhost packets observed
- [ ] **DNS monitoring test** — zero DNS queries from Kwyre process during operation
- [ ] **CORS restriction confirmed** — `Access-Control-Allow-Origin` locked to server origin
- [ ] **Security headers confirmed** — CSP, X-Frame-Options, X-Content-Type-Options present on all responses

### Phase 6: Compliance Documentation

- [ ] **Compliance letter reviewed** — `COMPLIANCE_LETTER.md` current and signed
- [ ] **Verification guide executed** — all 14 checks in `VERIFICATION_GUIDE.md` passed
- [ ] **Incident response plan reviewed** — `INCIDENT_RESPONSE.md` customized with org contacts
- [ ] **Data residency confirmed** — `DATA_RESIDENCY.md` reviewed with legal team
- [ ] **Deployment metadata recorded** — machine, GPU, date, version, deployer, reviewer

### Phase 7: Ongoing Operations

- [ ] **Startup verification** — L3 + L4 checks run automatically at every server start
- [ ] **Weekly audit log review** — `/audit` endpoint output reviewed for anomalies
- [ ] **Post-update verification** — `verify_deps.py verify` after any system/package update
- [ ] **Quarterly full verification** — complete `VERIFICATION_GUIDE.md` execution and documentation
- [ ] **Annual penetration test** — or when significant changes are made to the codebase
- [ ] **Incident response drill** — tabletop exercise of L6 trigger scenario annually

---

## 4. Evidence Collection for Auditors

### 4.1 Artifacts Kwyre Produces

| Artifact | Location | Content | Retention |
|----------|----------|---------|-----------|
| **Audit endpoint output** | `GET /audit` (live) | Active sessions, security control status, watchdog state, timestamps. **Never contains conversation content.** | Live query — reflects current state |
| **Health endpoint output** | `GET /health` (live) | System status, VRAM usage, model info, speculative decoding status, watchdog state. Detailed info requires authentication. | Live query — reflects current state |
| **Server startup log** | stdout/stderr | Layer 3 verification results, Layer 4 integrity check, model loading, watchdog initialization. | Captured by process supervisor (systemd, Docker, etc.) |
| **Intrusion event log** | In-memory `intrusion_log` + stdout | Timestamp, trigger type, trigger details, session count at wipe. **Metadata only.** | In-memory until process exit; stdout captured by supervisor |
| **Session wipe log** | stdout | Session ID prefix (first 8 chars), message count, wipe reason. **No content.** | Captured by process supervisor |
| **Dependency manifest** | `security/kwyre_dep_manifest.json` | SHA256 hashes and versions of all installed Python packages at time of baseline. | Persisted on disk, version-controlled |
| **Model weight hashes** | Hardcoded in `serve_local_4bit.py` | SHA256 hashes of model configuration files. | Compiled into server binary |

### 4.2 Artifacts Kwyre Does NOT Produce

These are intentionally absent. Their absence is itself evidence of the data handling architecture:

| Artifact | Why It Doesn't Exist |
|----------|---------------------|
| Conversation logs | L5: RAM-only storage — content is never written to disk |
| Query logs | Zero content logging by design — only metadata (timestamps, token counts) |
| Database files | No database — all state is in-memory |
| Temp files with user data | No temporary file I/O for inference |
| Network traffic captures showing external comms | L1 + L2: No external network traffic exists |
| Telemetry or analytics data | Zero telemetry by design — no phone-home of any kind |
| Error reports with user content | Error messages contain code paths only, never user input |

### 4.3 Auditor Verification Procedures

Auditors can independently verify all claims without vendor cooperation. See `VERIFICATION_GUIDE.md` for 14 step-by-step verification procedures covering all 6 security layers.

Key verification methods:

1. **Network binding** — `netstat`/`ss` confirms localhost-only binding
2. **Zero outbound traffic** — Wireshark full capture shows zero non-localhost packets
3. **Dependency integrity** — `verify_deps.py verify` shows cryptographic verification
4. **Model integrity** — startup log shows SHA256 verification pass/fail
5. **RAM-only storage** — disk forensic search finds zero conversation content
6. **Intrusion detection** — `/health` confirms watchdog running; trigger test optional
7. **Authentication** — unauthenticated requests confirmed rejected

---

## 5. Network Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                        CUSTOMER MACHINE                              ║
║                                                                      ║
║   ┌──────────────────┐                                               ║
║   │  Browser / API   │                                               ║
║   │     Client       │                                               ║
║   └────────┬─────────┘                                               ║
║            │                                                         ║
║            │ HTTP (127.0.0.1:8000 ONLY)                              ║
║            │ ┌─── Auth: Bearer <api-key> ───┐                        ║
║            ▼ ▼                               │                       ║
║   ┌────────────────────────────────────────────────────────────────┐  ║
║   │                    KWYRE INFERENCE SERVER                      │  ║
║   │                                                                │  ║
║   │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐  │  ║
║   │  │  API Router  │  │  Rate Limiter    │  │  CSP Nonce Gen   │  │  ║
║   │  │  + Auth      │  │  + Eval Tier     │  │  + Sec Headers   │  │  ║
║   │  └─────────────┘  └──────────────────┘  └──────────────────┘  │  ║
║   │                                                                │  ║
║   │  ┌──────────────────────────────────────────────────────────┐  │  ║
║   │  │              LAYER 5: Secure Session Store               │  │  ║
║   │  │  ● RAM-only conversation buffers                         │  │  ║
║   │  │  ● 256-bit per-session keys                              │  │  ║
║   │  │  ● Cryptographic wipe on close/timeout/intrusion         │  │  ║
║   │  │  ● 1-hour idle session reaping                           │  │  ║
║   │  └──────────────────────────────────────────────────────────┘  │  ║
║   │                                                                │  ║
║   │  ┌──────────────────────────────────────────────────────────┐  │  ║
║   │  │              INFERENCE ENGINE                             │  │  ║
║   │  │  ● Qwen3-4B main model (4-bit NF4)                      │  │  ║
║   │  │  ● Qwen3-0.6B speculative draft                          │  │  ║
║   │  │  ● SpikeServe activation encoding                        │  │  ║
║   │  │  ● GPU VRAM: ~3.9 GB combined                            │  │  ║
║   │  └──────────────────────────────────────────────────────────┘  │  ║
║   │                                                                │  ║
║   │  ┌──────────────────────────────────────────────────────────┐  │  ║
║   │  │              LAYER 6: Intrusion Watchdog (daemon)         │  │  ║
║   │  │  ● Scans every 5s for outbound connections               │  │  ║
║   │  │  ● Monitors for debug/analysis tools                     │  │  ║
║   │  │  ● 2 consecutive violations → wipe all + terminate       │  │  ║
║   │  └──────────────────────────────────────────────────────────┘  │  ║
║   │                                                                │  ║
║   │  STARTUP GATES (must pass before inference begins):            │  ║
║   │  [L3] SHA256 dependency manifest verification                  │  ║
║   │  [L4] SHA256 model weight integrity verification               │  ║
║   └────────────────────────────────────────────────────────────────┘  ║
║                                                                      ║
║   ┌────────────────────────────────────────────────────────────────┐  ║
║   │                    OS-LEVEL CONTROLS                           │  ║
║   │  [L1] TCP socket bound to 127.0.0.1 — not routable            │  ║
║   │  [L2] iptables / Windows Firewall: outbound DENY for process   │  ║
║   └────────────────────────────────────────────────────────────────┘  ║
║                                                                      ║
║   ════════════════════════════════════════════════════════════════    ║
║                    NO DATA CROSSES THIS LINE                         ║
╚══════════════════════════════════════════════════════════════════════╝
                              │
                         INTERNET / LAN
                       (blocked at L1 + L2)

Data Flow:
  User Input → [RAM] → [GPU VRAM] → [RAM] → User Output
                         │
              No disk. No network. No logs.
```

---

## 6. Control Attestation Table

| Control ID | SOC 2 Criteria | Control Description | Kwyre Implementation | Evidence Location | Test Frequency |
|-----------|---------------|--------------------|--------------------|------------------|---------------|
| KW-AC-01 | CC6.1 | Logical access restricted to localhost | `BIND_HOST = "127.0.0.1"` in server; OS socket-level enforcement | `netstat -an`, cross-machine test | Every startup |
| KW-AC-02 | CC6.1 | API authentication required | HMAC-compared API key on all endpoints; timing-safe comparison | HTTP 401 on unauth requests | Every request |
| KW-AC-03 | CC6.1 | Process network isolation | iptables/Windows Firewall per-process outbound deny | Firewall rule listing | Persistent OS rules |
| KW-AC-04 | CC6.1 | Eval tier rate limiting | Unlicensed: 10 req/min, 512 max tokens, 3 trial requests per IP | Server logs show enforcement | Every request |
| KW-BD-01 | CC6.6 | System boundary = loopback | No network interface other than `lo` carries Kwyre traffic | Wireshark capture | Quarterly verification |
| KW-BD-02 | CC6.6 | Air-gap enforcement | External tools opt-in (`KWYRE_ENABLE_TOOLS=0` default); SSRF allowlist | Config review, code audit | Every deployment |
| KW-TR-01 | CC6.7 | Data in transit protection | No transit exists — all communication is loopback-only | Wireshark shows zero external packets | Quarterly verification |
| KW-DR-01 | CC6.8 | Data at rest protection | No data at rest exists — RAM-only with cryptographic wipe | Disk forensic search; `/audit` output | Every session end |
| KW-DR-02 | CC6.8 | Session key management | 256-bit random per-session keys; zeroed on wipe | Code review of `SecureConversationBuffer` | Code audit |
| KW-MN-01 | CC7.1 | Continuous system monitoring | Intrusion watchdog: 5s scan interval, outbound + process monitoring | `/health` endpoint; watchdog logs | Continuous (every 5s) |
| KW-MN-02 | CC7.1 | Audit trail | `GET /audit` endpoint: metadata-only session and security status | Audit endpoint output | On demand |
| KW-IR-01 | CC7.2 | Automated incident response | L6 auto-wipe: all sessions destroyed in <2s on confirmed intrusion | Intrusion event log; `INCIDENT_RESPONSE.md` | Continuous monitoring |
| KW-IR-02 | CC7.2 | Documented IR procedures | `INCIDENT_RESPONSE.md`: severity classification, response procedures, escalation, reporting | Document review | Annual review |
| KW-CM-01 | CC8.1 | Dependency change detection | L3: SHA256 manifest of all Python packages verified at startup | `verify_deps.py verify` output | Every startup |
| KW-CM-02 | CC8.1 | Model integrity verification | L4: SHA256 hashes of model configs verified at startup | Startup log: `[Layer 4] PASSED/FAILED` | Every startup |
| KW-CM-03 | CC8.1 | Build integrity | Nuitka-compiled binary distribution; no source-level tampering possible | Build pipeline documentation | Every release |
| KW-RA-01 | CC3.1 | Security risk assessment | White-box pentest: 47/47 findings resolved (9C/12H/14M/12L) | Pentest report; remediation evidence | Annual or on major change |
| KW-RA-02 | CC3.1 | Automated security testing | 107 tests across 3 test suites; all passing | `pytest` output | Every build |

---

## 7. Auditor FAQ

### Q: How does Kwyre protect data in transit without TLS?

Kwyre does not use TLS because there is no transit to protect. The server binds exclusively to `127.0.0.1` (loopback). Loopback traffic never touches a physical network interface — it is handled entirely within the OS kernel's TCP/IP stack. There is no wire, no NIC, and no network path for an attacker to intercept. This is a stronger guarantee than TLS, which protects data on a wire that exists — Kwyre eliminates the wire entirely.

### Q: Where is data stored at rest?

Nowhere. Conversation data exists only in volatile RAM during active sessions. It is never written to disk, database, log file, temporary file, or any persistent storage. On session termination, content is overwritten with cryptographically random bytes before memory deallocation. When the process exits or the machine loses power, all data is irrecoverably destroyed.

### Q: How do we verify the vendor's claims independently?

Every security claim is independently verifiable without vendor cooperation. See `VERIFICATION_GUIDE.md` for 14 step-by-step procedures. Key methods: `netstat` for binding verification, Wireshark for zero-traffic confirmation, `verify_deps.py` for dependency integrity, disk forensics for absence of conversation data. No vendor credentials, special tools, or cooperation required.

### Q: What happens during a security incident?

The Layer 6 Intrusion Watchdog provides automated response: on confirmed detection of debugging tools or unexpected outbound connections (2 consecutive detections, 10s apart), all sessions are immediately wiped (content overwritten with random bytes), the event is logged (metadata only), and the server process terminates. Total detection-to-wipe time: < 2 seconds. See `INCIDENT_RESPONSE.md` for full procedures.

### Q: Does Kwyre have any external dependencies or cloud services?

No. After initial model download (one-time, ~3.3 GB from kwyre.com or HuggingFace), Kwyre operates completely offline. There is no telemetry, no analytics, no update checking, no license callback, no crash reporting, no phone-home functionality of any kind. The environment variables `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are hardcoded to prevent any network access attempts by ML libraries.

### Q: How are API keys managed?

API keys are set via the `KWYRE_API_KEYS` environment variable as `key:role` pairs. Keys are validated using `hmac.compare_digest` (timing-safe comparison). The system supports multiple keys with role-based access. There is no centralized key management service — keys are managed by the customer's IT team as environment configuration.

### Q: What audit trail does Kwyre maintain?

The `GET /audit` endpoint returns a metadata-only compliance log including: active session count, security control status (all 6 layers), watchdog state, and timestamps. It never includes conversation content. Server stdout captures startup verification results, session lifecycle events (creation, wipe), and intrusion detection events — all metadata only.

### Q: Can Kwyre be deployed in an air-gapped environment?

Yes. This is a primary deployment scenario. Steps: (1) download models and packages on an internet-connected staging machine, (2) transfer to air-gapped machine via approved media, (3) install with `pip install --no-index`, (4) `HF_HUB_OFFLINE=1` is already hardcoded. The server requires no network access for any function after initial setup. See `DEPLOYMENT_CHECKLIST.md` — Air-Gapped Deployment section.

### Q: How does Kwyre handle multi-tenancy?

Kwyre is designed for single-organization deployment on dedicated hardware. Each organization deploys their own instance. There is no shared infrastructure, no multi-tenant data commingling, and no cross-organization access path. Session isolation within a single deployment is enforced by unique session IDs and per-session encryption keys.

### Q: What is the Docker security posture?

The Docker container runs as a non-root `kwyre` user with minimal privileges. The dependency manifest is generated at build time. Port mapping restricts to `127.0.0.1:8000` on the host. The container image includes CUDA runtime but no unnecessary packages. The `Dockerfile` is auditable.

### Q: How does Kwyre handle vulnerability management?

Dependencies are pinned in `requirements-inference.txt` and cryptographically baselined in the L3 manifest. Any change — including security patches — is detected at startup. The process for applying updates: (1) update package, (2) re-run `verify_deps.py generate` to re-baseline, (3) commit new manifest with reviewer approval. The 107-test security suite is run on every build.

### Q: What is the penetration test coverage?

Kwyre v0.3 underwent a full white-box penetration test with complete source code access. 47 findings were identified (9 Critical, 12 High, 14 Medium, 12 Low/Informational). All 47 were resolved and re-tested. Key categories: CSP hardening, authentication timing attacks, input validation, SSRF prevention, session management, Docker privilege reduction. Details are available under NDA.

### Q: Does the system write any sensitive data to logs?

No. All logging is metadata-only. Log entries include timestamps, session ID prefixes (first 8 characters), message counts, token counts, wipe reasons, and security event types. Conversation content (user prompts and model responses) is never included in any log at any verbosity level. This is enforced architecturally, not by configuration.

---

## 8. Supplementary Documents

| Document | ID | Purpose |
|----------|----|---------|
| `COMPLIANCE_LETTER.md` | KWYRE-COMP-001 | Formal compliance attestation for legal/regulatory review |
| `VERIFICATION_GUIDE.md` | KWYRE-VER-001 | 14-step independent security verification procedures |
| `DEPLOYMENT_CHECKLIST.md` | KWYRE-DEP-001 | Step-by-step hardened deployment procedure |
| `INCIDENT_RESPONSE.md` | KWYRE-IR-001 | Security event classification and response procedures |
| `DATA_RESIDENCY.md` | — | Data flow and privacy architecture documentation |
| `SECURITY_ARCHITECTURE.md` | — | Technical description of the 6-layer security model |
| `ENTERPRISE_AUDIT.md` | KWYRE-AUDIT-001 | Extended audit documentation with regulatory mapping |

---

**Apollo CyberSentinel LLC**
compliance@kwyre.com

*This document is provided for SOC 2 Type II audit preparation. It describes verifiable technical controls implemented in the Kwyre AI software. It is not legal advice. Organizations should consult their own auditors and legal counsel for SOC 2 compliance determinations.*
