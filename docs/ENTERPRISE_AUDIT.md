# Kwyre AI — Enterprise Audit Package

**Document ID:** KWYRE-AUDIT-001
**Version:** 1.0
**Effective Date:** March 2026
**Issuer:** Apollo CyberSentinel LLC
**Classification:** Customer-Facing — For Enterprise Security, Compliance, and Audit Teams

---

## 1. Purpose

This document extends the compliance attestation in `COMPLIANCE_LETTER.md` with detailed technical specifications required by enterprise security teams, internal audit functions, and external auditors. It covers audit log formats, data flow analysis, cryptographic controls, penetration test results, supply chain security, incident response integration, and regulatory mapping.

---

## 2. Audit Log Specification

### 2.1 Audit Endpoint (`GET /audit`)

**Authentication:** Required (`Authorization: Bearer <api-key>`)

**Response Format:**

```json
{
  "server": "kwyre-4b-spikeserve",
  "version": "0.3.0",
  "timestamp": "2026-03-08T14:30:00Z",
  "uptime_seconds": 3600,
  "active_sessions": 2,
  "total_sessions_created": 15,
  "total_sessions_wiped": 13,
  "security_controls": {
    "layer_1_network_binding": "127.0.0.1:8000 (localhost only)",
    "layer_2_process_isolation": "enabled",
    "layer_3_dependency_integrity": "verified_at_startup",
    "layer_4_model_integrity": "verified_at_startup",
    "layer_5_storage": "RAM-only",
    "layer_5_session_wipe": "on_close + idle_timeout_1hr + shutdown + intrusion",
    "layer_6_intrusion_watchdog": {
      "running": true,
      "triggered": false,
      "scan_interval_seconds": 5,
      "violation_threshold": 2,
      "intrusion_events": []
    },
    "content_logging": "NEVER",
    "telemetry": "NONE"
  },
  "authentication": {
    "method": "bearer_token",
    "timing_safe": true,
    "eval_tier_active": false
  },
  "model": {
    "id": "kwyre-4b",
    "tier": "personal",
    "quantization": "nf4_4bit",
    "speculative_decoding": true
  },
  "note": "Metadata only. No conversation content is ever logged or persisted."
}
```

### 2.2 Metadata Captured

| Field | Description | Contains User Content? |
|-------|-------------|----------------------|
| `timestamp` | ISO 8601 timestamp of audit query | No |
| `active_sessions` | Count of currently active session buffers | No |
| `total_sessions_created` | Cumulative count since server start | No |
| `total_sessions_wiped` | Cumulative wipe count since server start | No |
| `security_controls` | Status of all 6 security layers | No |
| `intrusion_events` | Array of intrusion detection events (timestamp, type, details) | No |
| `model` | Model tier, quantization method, feature status | No |

**Content never captured:** User prompts, model responses, conversation history, session content, personally identifiable information, query text, or any derivative of user input.

### 2.3 Server Log Output (stdout/stderr)

| Log Event | Format | Content |
|-----------|--------|---------|
| Startup: L3 verification | `[Layer 3] <package>: [OK] / [FAIL]` | Package name + hash match result |
| Startup: L4 verification | `[Layer 4] Model integrity check: PASSED/FAILED` | Verification result only |
| Session created | `[SessionStore] New session: <id_prefix>...` | First 8 chars of session ID |
| Session wiped | `[SecureBuffer] <id_prefix>... wiped (N msgs, reason=<reason>)` | Session ID prefix, message count, wipe reason |
| Intrusion detected | `[Layer 6] INTRUSION DETECTED: <details>` | Tool name or connection details |
| Emergency wipe | `[Layer 6] Emergency wipe: N sessions destroyed` | Session count |
| Auth failure | `[Auth] 401 from <ip>` | Client IP only |
| Request served | `[Request] POST /v1/chat/completions 200 <tokens> tokens` | Endpoint, status, token count |

### 2.4 Retention Policy

| Data Type | Retention | Rationale |
|-----------|-----------|-----------|
| Audit endpoint data | In-memory only; reset on server restart | No persistent audit log by design — prevents disk forensic recovery of session metadata |
| Server stdout/stderr | Determined by process supervisor (systemd journal, Docker logs, etc.) | Customer controls retention via their log management infrastructure |
| Conversation content | Zero retention — RAM-only, wiped on session end | Architectural guarantee: no persistent conversation data exists |
| Intrusion event log | In-memory until process exit | Ephemeral by design; customers should configure process supervisor to capture stdout for retention |
| Dependency manifest | Persistent on disk (`security/kwyre_dep_manifest.json`) | Required for L3 verification at every startup |

**Recommendation for SOC 2 environments:** Configure the process supervisor (systemd, Docker, or equivalent) to capture and retain Kwyre's stdout output according to your organization's log retention policy. This provides a persistent audit trail of session lifecycle events and security events without Kwyre itself writing to disk.

---

## 3. Data Flow Diagram

### 3.1 Where User Data Goes

```
┌─────────────────────────────────────────────────────────────────┐
│                          USER MACHINE                           │
│                                                                 │
│  ┌──────────────┐     HTTP POST (127.0.0.1)     ┌───────────┐  │
│  │  Browser /   │ ─────────────────────────────► │  Kwyre    │  │
│  │  API Client  │ ◄───────────────────────────── │  Server   │  │
│  └──────────────┘     HTTP Response (127.0.0.1)  └─────┬─────┘  │
│                                                        │        │
│                                          ┌─────────────┼────┐   │
│                                          │    RAM ONLY  │    │   │
│                                          │             ▼    │   │
│                                          │  ┌────────────┐  │   │
│                                          │  │  Session    │  │   │
│                                          │  │  Buffer     │  │   │
│                                          │  │  (messages) │  │   │
│                                          │  └──────┬─────┘  │   │
│                                          │         │        │   │
│                                          │         ▼        │   │
│                                          │  ┌────────────┐  │   │
│                                          │  │  Tokenizer  │  │   │
│                                          │  │  (encode)   │  │   │
│                                          │  └──────┬─────┘  │   │
│                                          │         │        │   │
│                                          └─────────┼────────┘   │
│                                                    │            │
│                                          ┌─────────┼────────┐   │
│                                          │  GPU VRAM ONLY   │   │
│                                          │         ▼        │   │
│                                          │  ┌────────────┐  │   │
│                                          │  │  Model      │  │   │
│                                          │  │  Inference  │  │   │
│                                          │  │  (forward   │  │   │
│                                          │  │   pass)     │  │   │
│                                          │  └──────┬─────┘  │   │
│                                          │         │        │   │
│                                          └─────────┼────────┘   │
│                                                    │            │
│                                          ┌─────────┼────────┐   │
│                                          │    RAM ONLY  │    │   │
│                                          │         ▼        │   │
│                                          │  ┌────────────┐  │   │
│                                          │  │  Tokenizer  │  │   │
│                                          │  │  (decode)   │  │   │
│                                          │  └──────┬─────┘  │   │
│                                          │         │        │   │
│                                          │         ▼        │   │
│                                          │  HTTP Response   │   │
│                                          │  to client       │   │
│                                          └──────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Where User Data Does NOT Go

| Destination | Status | Technical Control |
|-------------|--------|------------------|
| **Disk (any file)** | BLOCKED | L5: RAM-only architecture — no disk I/O for conversation data |
| **Log files** | BLOCKED | Zero content logging — only metadata (timestamps, counts) is logged |
| **Database** | BLOCKED | No database component exists — all state is in-memory |
| **Temporary files** | BLOCKED | No temp file I/O in inference pipeline |
| **Network (any destination)** | BLOCKED | L1: localhost-only binding + L2: process outbound denied |
| **Vendor (Apollo CyberSentinel)** | BLOCKED | Zero telemetry, zero phone-home, zero callbacks |
| **Cloud services** | BLOCKED | L1 + L2 + `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` |
| **DNS** | BLOCKED | No hostname resolution needed — no external endpoints |
| **Swap / page file** | RISK | OS may page RAM to disk under memory pressure — mitigate with `swapoff` (Linux) or locked pages |
| **Core dumps** | RISK | OS may write core dump on crash — mitigate by disabling core dumps (`ulimit -c 0`) |

### 3.3 Session Lifecycle Data Flow

```
1. CREATE   User sends POST /v1/chat/completions with session_id
            → Server creates SecureConversationBuffer in RAM
            → 256-bit random session key generated
            → Message appended to in-memory buffer

2. USE      Subsequent messages append to same buffer
            → Buffer passed to tokenizer (RAM)
            → Tokens passed to GPU (VRAM)
            → Output tokens decoded (RAM)
            → Response returned via loopback HTTP
            → Response appended to buffer

3. END      Any of: user calls POST /v1/session/end
                     session idle > 1 hour
                     server shutdown (SIGTERM)
                     L6 intrusion detection
            → Every message content overwritten with secrets.token_hex()
            → Every message role overwritten with random bytes
            → Message list cleared
            → Session key zeroed (32 null bytes)
            → Buffer object dereferenced for GC
            → Wipe logged: session_id[:8], msg_count, reason (METADATA ONLY)

4. GONE     After wipe, no recoverable data exists:
            → RAM contains random bytes (overwritten)
            → No disk artifact was ever created
            → Process memory scan returns garbage
```

---

## 4. Cryptographic Controls Inventory

### 4.1 Cryptographic Primitives in Use

| Primitive | Algorithm | Key Size | Usage | Implementation |
|-----------|-----------|----------|-------|---------------|
| **License Signing** | Ed25519 | 256-bit | Offline license key validation. Public key embedded at build time. Licenses are signed by vendor, verified locally without network. | `security/license.py` — `nacl.signing.VerifyKey` |
| **Session Keys** | Random bytes | 256-bit (32 bytes) | Per-session cryptographic key generated via `secrets.token_bytes(32)`. Used for session identification and future encryption-at-rest capability. Zeroed on wipe. | `server/serve_local_4bit.py` — `SecureConversationBuffer.__init__` |
| **Session Wipe** | CSPRNG overwrite | Variable | Conversation content overwritten with `secrets.token_hex()` output (cryptographically random) before deallocation. Prevents RAM scraping recovery. | `server/serve_local_4bit.py` — `SecureConversationBuffer.secure_wipe` |
| **Dependency Integrity** | SHA-256 | 256-bit digest | Hash of each Python package's `RECORD` file computed at install time, verified at every startup. Detects any modification to installed packages. | `security/verify_deps.py` |
| **Model Weight Integrity** | SHA-256 | 256-bit digest | Hash of model configuration files (`config.json`, `tokenizer_config.json`, `generation_config.json`, `tokenizer.json`) verified at startup. | `server/serve_local_4bit.py` — `verify_model_integrity()` |
| **API Key Comparison** | HMAC-based timing-safe compare | Variable | API keys validated using `hmac.compare_digest()` to prevent timing side-channel attacks that could leak key bytes through response time variations. | `server/serve_local_4bit.py` — request authentication handler |
| **Session ID Generation** | CSPRNG | 256-bit minimum | Server-side session ID generation using `secrets.token_hex()` when client-provided IDs have insufficient entropy (< 32 characters). | `server/serve_local_4bit.py` — session ID validation |
| **CSP Nonces** | CSPRNG | 128-bit | Per-request cryptographic nonces for Content-Security-Policy `script-src` directives. Prevents inline script injection. | `server/serve_local_4bit.py` — CSP header generation |

### 4.2 Cryptographic Libraries

| Library | Version | Purpose | Supply Chain Protection |
|---------|---------|---------|------------------------|
| Python `secrets` | stdlib | CSPRNG for session keys, wipe data, nonces | Part of Python stdlib — verified via L3 |
| Python `hashlib` | stdlib | SHA-256 for L3/L4 integrity verification | Part of Python stdlib — verified via L3 |
| Python `hmac` | stdlib | Timing-safe API key comparison | Part of Python stdlib — verified via L3 |
| `PyNaCl` / `nacl` | pinned | Ed25519 license key verification | Pinned version in requirements; L3 manifest verified |

### 4.3 What Is NOT Encrypted

| Data | Encryption Status | Rationale |
|------|-------------------|-----------|
| HTTP traffic (localhost) | Unencrypted | Loopback traffic (`127.0.0.1 → 127.0.0.1`) never touches a physical network interface. TLS would add latency and complexity without security benefit — there is no wire to protect. |
| Conversation content in RAM | Unencrypted during session | Encrypting RAM buffers provides minimal benefit against an attacker with process memory access (they would also have access to the encryption key in the same process). RAM is volatile and wiped on session end. |
| Model weights on disk | Unencrypted | Model weights are not sensitive data — they are publicly available base models. Protection is provided by L4 integrity verification (detecting tampering), not encryption. Disk encryption (BitLocker/LUKS) recommended for the host. |
| Audit log output | Unencrypted | Contains metadata only (timestamps, counts). No sensitive content to protect. |

---

## 5. Penetration Test Summary

### 5.1 Test Parameters

| Parameter | Value |
|-----------|-------|
| **Test Type** | White-box (full source code access) |
| **Target Version** | Kwyre v0.3 |
| **Scope** | All server code, client-side HTML/JS, Docker configuration, security modules, API endpoints |
| **Methodology** | OWASP Testing Guide v4, SANS Top 25, custom air-gap verification |
| **Duration** | Comprehensive assessment |
| **Status** | All findings resolved |

### 5.2 Finding Summary

| Severity | Count | Status | Examples |
|----------|-------|--------|----------|
| **Critical** | 9 | All resolved | CSP `unsafe-inline` allowing script injection; API key timing side-channel; license key injectable via environment variable; SSRF via tools endpoint; missing auth on sensitive endpoints |
| **High** | 12 | All resolved | Missing input validation on `max_tokens`/`temperature`; localStorage for API keys (persistent); insufficient session ID entropy; root Docker container; missing security headers on error paths |
| **Medium** | 14 | All resolved | CORS misconfiguration; missing rate limiting for eval tier; watchdog not monitoring child processes; template-based sanitizer vulnerable to mXSS; verbose error messages leaking internals |
| **Low / Info** | 12 | All resolved | Missing `Permissions-Policy` header; `X-Powered-By` leaking framework info; development API keys in default config; inconsistent content-type handling |
| **TOTAL** | **47** | **47/47 resolved** | |

### 5.3 Key Remediations

| Finding | Severity | Remediation |
|---------|----------|-------------|
| CSP allowed `unsafe-inline` scripts | Critical | Implemented per-request cryptographic nonce system; all inline scripts require valid nonce |
| API key comparison vulnerable to timing attack | Critical | Replaced `==` with `hmac.compare_digest()` for constant-time comparison |
| License public key loadable from env var | Critical | Public key must be embedded at build time; environment variable path removed |
| SSRF via external tools endpoint | Critical | Tools disabled by default (`KWYRE_ENABLE_TOOLS=0`); SSRF host allowlist when enabled |
| Docker container running as root | High | Dedicated `kwyre` user with minimal privileges; dependency manifest generated at build |
| API keys stored in localStorage | High | Moved to `sessionStorage` (cleared on tab close) |
| Missing input validation | High | `max_tokens` clamped to 1-8192, `temperature` to 0.0-2.0, `top_p` to 0.0-1.0; message array validated |
| Template-based sanitizer (mXSS) | Medium | Replaced with DOMParser-based sanitizer immune to mutation XSS |
| Watchdog not checking child processes | Medium | Recursive child process network connection monitoring added |

### 5.4 Verification

All 47 findings were individually retested after remediation. An automated test suite of 107 tests was created to prevent regression:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_security.py` | Primary security test suite | Authentication, headers, CSP, input validation, session management |
| `tests/test_layer3_dependency_integrity.py` | L3 dependency integrity | Manifest generation, verification, tampering detection |
| Additional test modules | Integration tests | API endpoint behavior, rate limiting, eval tier enforcement |

---

## 6. Supply Chain Security

### 6.1 Dependency Management

| Control | Implementation | Evidence |
|---------|---------------|----------|
| **Pinned versions** | All dependencies pinned in `requirements-inference.txt` with exact versions | Requirements file review |
| **Minimal dependency set** | Inference-only requirements stripped of training dependencies | 13 direct dependencies vs full ML stack |
| **SHA-256 manifest** | `security/verify_deps.py generate` computes SHA-256 of every installed package's `RECORD` file | `security/kwyre_dep_manifest.json` |
| **Startup verification** | `verify_deps.py verify` runs at every server startup — any hash mismatch aborts before inference | Server startup log: `[Layer 3] ...` |
| **Unexpected package detection** | `verify_deps.py audit` identifies packages not in the original manifest | Audit output lists any unmanifested packages |

### 6.2 Docker Security

| Control | Implementation |
|---------|---------------|
| **Non-root execution** | `USER kwyre` — dedicated user with no shell, no home directory, minimal privileges |
| **Build-time manifest** | Dependency manifest generated during Docker build, not at runtime |
| **Minimal base image** | NVIDIA CUDA base with only required system packages |
| **No network access** | Container-level: `BIND_HOST=0.0.0.0` (internal) mapped to `127.0.0.1:8000` (host) |
| **Read-only model weights** | Model files mounted read-only where possible |
| **No secrets in image** | API keys, license keys passed via environment variables at runtime |

### 6.3 Build Pipeline (Nuitka)

| Stage | Description | Integrity Control |
|-------|-------------|-------------------|
| **Source compilation** | `serve_local_4bit.py`, `tools.py`, `verify_deps.py`, `license.py`, `spike_serve.py` compiled to native binary via Nuitka | Source code is not distributed — reverse engineering significantly harder |
| **Data packaging** | `chat/*.html`, `docs/`, `.env.example` bundled as data files | Files are auditable and not compiled |
| **Installer generation** | Platform-specific installers (Inno Setup, .deb, .pkg) | Signed with platform-appropriate code signing |

### 6.4 Offline Operation

| Control | Implementation |
|---------|---------------|
| **HF_HUB_OFFLINE=1** | Hardcoded environment variable — Hugging Face libraries cannot reach the internet |
| **TRANSFORMERS_OFFLINE=1** | Hardcoded environment variable — transformers library runs in offline mode |
| **No update checking** | No auto-update mechanism exists in the codebase |
| **No telemetry endpoints** | No analytics, crash reporting, or usage tracking code exists |
| **No license callbacks** | Ed25519 license validation is purely local (public key verification) |

---

## 7. Incident Response Integration

### 7.1 How Kwyre's Auto-Wipe Fits into Enterprise IR Plans

Kwyre's Layer 6 Intrusion Watchdog provides an automated first-response capability that integrates with — not replaces — your organization's incident response plan.

```
┌──────────────────────────────────────────────────────────────────┐
│                    INCIDENT TIMELINE                              │
│                                                                  │
│  T+0s     Watchdog detects anomaly (suspicious process or        │
│           unexpected outbound connection)                         │
│                                                                  │
│  T+5s     Second consecutive detection confirms (avoids false    │
│           positive from momentary process)                        │
│                                                                  │
│  T+5.1s   AUTOMATED: All sessions enumerated                    │
│  T+5.2s   AUTOMATED: All message content overwritten with        │
│           cryptographically random bytes                          │
│  T+5.3s   AUTOMATED: Session keys zeroed                         │
│  T+5.4s   AUTOMATED: Event logged (metadata: timestamp, type,    │
│           trigger details, session count)                         │
│  T+5.5s   AUTOMATED: Server process terminated (exit code 1)     │
│                                                                  │
│  T+6s     Process supervisor captures shutdown log to persistent  │
│           storage (systemd journal, Docker logs, etc.)            │
│                                                                  │
│  ─── KWYRE AUTOMATED RESPONSE COMPLETE ───                       │
│  ─── ENTERPRISE IR PLAN TAKES OVER ───                           │
│                                                                  │
│  T+Ns     IT team notified via process supervisor alerting        │
│           (systemd failure notification, Docker health check, etc)│
│                                                                  │
│  T+Nm     IR team investigates trigger cause per                  │
│           INCIDENT_RESPONSE.md manual procedures                  │
│                                                                  │
│  T+Nh     Root cause documented, remediation applied,             │
│           server restarted (or machine re-imaged)                 │
└──────────────────────────────────────────────────────────────────┘
```

### 7.2 Integration Points

| Enterprise IR Phase | Kwyre Integration Point |
|--------------------|------------------------|
| **Detection** | Kwyre's L6 watchdog serves as a detection sensor. Configure your process supervisor to send alerts on Kwyre process termination (exit code 1 = intrusion wipe). |
| **Containment** | Auto-wipe provides immediate containment — all sensitive session data is destroyed before an attacker can extract it. No manual containment step is needed for Kwyre data. |
| **Eradication** | Follow `INCIDENT_RESPONSE.md` manual procedures: run `verify_deps.py verify` + `audit`, check for modified files, review running processes. |
| **Recovery** | Restart server after investigation. If triggered by unknown cause, consider re-imaging the machine from a known-good backup. |
| **Lessons Learned** | Kwyre provides metadata for post-incident analysis: trigger type, trigger details, session count at time of wipe, timestamp. |

### 7.3 SIEM/SOAR Integration

Kwyre does not natively integrate with SIEM or SOAR platforms (to maintain air-gap integrity). Integration is achieved via the process supervisor layer:

1. **systemd** — Configure `OnFailure=` to trigger notification scripts
2. **Docker** — Use health checks and restart policies; forward container logs to SIEM
3. **Windows Service** — Use Windows Event Log forwarding for service failure events
4. **Syslog** — Pipe Kwyre stdout to syslog for centralized collection

---

## 8. Regulatory Mapping

### 8.1 HIPAA (Health Insurance Portability and Accountability Act)

| HIPAA Requirement | Section | Kwyre Posture |
|-------------------|---------|---------------|
| Access Controls | § 164.312(a) | API key authentication on all endpoints. Process-level isolation (L2) prevents unauthorized access at OS level. Localhost binding (L1) eliminates remote access path. |
| Audit Controls | § 164.312(b) | `GET /audit` endpoint provides metadata-only audit trail. Server stdout captures session lifecycle and security events. |
| Integrity Controls | § 164.312(c) | L3 dependency integrity and L4 model weight integrity verified at every startup via SHA-256. |
| Transmission Security | § 164.312(e) | Not applicable — no transmission occurs. All processing is local to the covered entity's own hardware. No BAA required because no data is shared with any processor. |
| Encryption at Rest | § 164.312(a)(2)(iv) | PHI is never at rest — RAM-only storage with cryptographic wipe. Disk encryption (BitLocker/LUKS) recommended for model weight protection on the host. |

**HIPAA Summary:** Because Kwyre processes data entirely on the covered entity's own hardware with zero external transmission, it functions as an internal tool — similar to a word processor or spreadsheet. No Business Associate Agreement (BAA) is required with Apollo CyberSentinel because no PHI is shared with or accessible to the vendor.

### 8.2 FINRA (Financial Industry Regulatory Authority)

| FINRA Requirement | Rule | Kwyre Posture |
|-------------------|------|---------------|
| Supervision of Communications | Rule 3110 | All AI-assisted communications remain within the firm's supervised environment. No data leaves the firm's infrastructure. Metadata audit trail available for supervisory review. |
| Books and Records | Rules 4511/4512 | Kwyre does not generate records that must be retained — conversations are ephemeral by design. Firms should implement their own retention if AI-generated content becomes a business record. |
| Business Continuity | Rule 4370 | Kwyre operates independently on local hardware. No dependency on external services, cloud infrastructure, or vendor availability. |
| Cybersecurity | Regulatory Notice 21-18 | 6-layer security stack, penetration-tested, automated intrusion response, supply chain verification. |

**FINRA Summary:** Kwyre enables registered representatives and compliance officers to use AI for analysis without creating regulatory risk from cloud data transmission. The firm maintains full control over all data and can apply existing supervisory procedures to AI-assisted work product.

### 8.3 GDPR (General Data Protection Regulation)

| GDPR Article | Requirement | Kwyre Posture |
|-------------|-------------|---------------|
| Art. 5(1)(f) | Integrity and confidentiality | 6-layer security architecture with cryptographic wipe, process isolation, and intrusion detection. |
| Art. 25 | Data Protection by Design and Default | Zero data transmission, RAM-only storage, and cryptographic wipe are architectural defaults — not configurable options. |
| Art. 28 | Processor obligations | Not applicable — Kwyre does not act as a data processor. All processing occurs on the controller's own infrastructure. No data is accessible to Apollo CyberSentinel. |
| Art. 30 | Records of processing activities | `GET /audit` provides metadata-only processing records. Controllers maintain their own ROPA entries. |
| Art. 32 | Security of processing | Appropriate technical measures: encryption (session keys), access controls (API auth + localhost binding), integrity verification (L3/L4), monitoring (L6 watchdog). |
| Art. 33-34 | Breach notification | Automated containment via L6 auto-wipe. Breach scope is limited to active RAM contents during the session — see `INCIDENT_RESPONSE.md` Data Breach Assessment. |
| Art. 35 | DPIA | Kwyre's architecture significantly reduces risk: no data transmission, no data persistence, no third-party processing. A DPIA should confirm low residual risk. |
| Art. 44-49 | International transfers | Not applicable — no data transfer occurs. Data remains on the controller's hardware in the controller's jurisdiction. |

**GDPR Summary:** Kwyre is designed as a "controller-only" tool. No data processing agreement is required because no data is shared with or accessible to any processor. The controller retains complete sovereignty over all personal data.

### 8.4 ABA Model Rules (American Bar Association)

| Rule | Requirement | Kwyre Posture |
|------|-------------|---------------|
| Rule 1.1 (Competence) | Lawyers must understand technology they use | Full source code available for audit. `VERIFICATION_GUIDE.md` enables independent verification. Architecture documentation supports informed adoption decisions. |
| Rule 1.6 (Confidentiality) | Duty to protect confidential client information | Client information never leaves the attorney's machine. No third-party access. Air-gapped architecture eliminates transmission risk. RAM-only storage eliminates persistence risk. |
| Rule 1.6(c) | Reasonable efforts to prevent unauthorized access | 6-layer defense-in-depth: network binding, process isolation, dependency integrity, model integrity, secure RAM storage, intrusion detection with auto-wipe. Penetration tested with all findings resolved. |
| Rule 5.3 | Supervision of non-lawyer assistants | AI tool operates entirely under the attorney's control on their own hardware. No external service involved. Metadata audit trail supports supervision obligations. |

**ABA Summary:** Kwyre is designed specifically for legal professionals who need AI assistance on privileged materials. The air-gapped architecture satisfies Rule 1.6 confidentiality obligations by eliminating — rather than merely encrypting — the transmission and persistence of client information.

### 8.5 ITAR (International Traffic in Arms Regulations)

| Requirement | Section | Kwyre Posture |
|-------------|---------|---------------|
| Export control | § 120.17 | No export occurs — technical data and defense articles remain on the user's machine within the controlled environment. Zero outbound data transmission. |
| Access control | § 120.16 | Localhost-only binding ensures only authorized users on the local machine can access the AI system. Process isolation prevents exfiltration. |
| Electronic transmission | § 120.50 | Not applicable — no electronic transmission of any data occurs. |

**ITAR Summary:** Kwyre can be deployed within ITAR-controlled environments because it does not transmit, export, or make accessible any data to any external system or person. The air-gap is enforced at the OS level, not by policy.

### 8.6 FRE (Federal Rules of Evidence)

| Rule | Applicability | Kwyre Posture |
|------|--------------|---------------|
| Rule 901(b)(9) | Authentication of evidence produced by a system | Chain of custody preserved — evidence data analyzed by Kwyre never traverses third-party systems. Analysis occurs on the investigator's own hardware. |
| Rule 702 | Expert witness testimony about AI-assisted analysis | AI analysis is reproducible on the same hardware with the same model. No cloud dependency means the system can be examined by opposing counsel. |

**FRE Summary:** Kwyre preserves chain of custody for digital evidence by ensuring that evidence data never leaves the investigator's control. AI-assisted analysis can be reproduced and examined because the entire system runs locally.

---

## 9. Compliance Matrix

| Control Area | HIPAA | FINRA | GDPR | ABA | ITAR | SOC 2 | Kwyre Control |
|-------------|-------|-------|------|-----|------|-------|--------------|
| Access control | § 164.312(a) | 3110 | Art. 32 | 1.6(c) | § 120.16 | CC6.1 | L1 + L2 + API auth |
| Data in transit | § 164.312(e) | — | Art. 32 | 1.6 | § 120.50 | CC6.7 | L1 (eliminated) |
| Data at rest | § 164.312(a)(2)(iv) | — | Art. 32 | 1.6 | — | CC6.8 | L5 (eliminated) |
| Integrity | § 164.312(c) | — | Art. 5(1)(f) | — | — | CC8.1 | L3 + L4 |
| Monitoring | § 164.312(b) | 21-18 | Art. 32 | — | — | CC7.1 | L6 + /audit |
| Incident response | — | — | Art. 33-34 | — | — | CC7.2 | L6 auto-wipe + IR procedures |
| Risk assessment | — | — | Art. 35 | 1.1 | — | CC3.1 | Pentest + threat model |
| Data transfers | — | — | Art. 44-49 | — | § 120.17 | CC6.6 | Eliminated (air-gap) |

---

## 10. Contact

| Purpose | Contact |
|---------|---------|
| Security architecture questions | security@kwyre.com |
| Compliance documentation | compliance@kwyre.com |
| Vulnerability reports | security@kwyre.ai |
| General inquiries | info@kwyre.com |

---

**Apollo CyberSentinel LLC**
compliance@kwyre.com

*This document provides technical facts about the Kwyre AI software architecture for enterprise audit purposes. It is not legal advice. Organizations should consult their own legal counsel, compliance officers, and auditors for regulatory compliance determinations.*
