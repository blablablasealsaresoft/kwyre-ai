# Kwyre AI — Compliance Attestation

**Document ID:** KWYRE-COMP-001
**Effective Date:** March 2026
**Issuer:** Apollo CyberSentinel LLC
**Contact:** compliance@kwyre.com

---

## Purpose

This document provides a formal attestation of Kwyre AI's data handling architecture for use by compliance officers, legal counsel, data protection officers, and regulatory auditors. It is intended to support due diligence assessments for organizations subject to data protection, attorney-client privilege, or information security requirements.

---

## Attestation

Apollo CyberSentinel LLC ("the Company") attests that the Kwyre AI inference system ("Kwyre") operates under the following technical constraints, enforced by verifiable software controls:

### 1. Zero Data Transmission

Kwyre does not transmit any user data — including prompts, responses, session metadata, or model activations — to any external server, API, cloud service, or third party. This includes the Company itself. There is no telemetry, analytics, crash reporting, update checking, or phone-home functionality of any kind.

**Verification:** Independent packet capture (Wireshark, tcpdump) on the host machine confirms zero outbound traffic from the inference process.

### 2. Local-Only Execution

All inference processing occurs on the user's local hardware. The server binds exclusively to the loopback interface (`127.0.0.1`), making it physically unreachable from any network at the OS level. No firewall configuration is required — the operating system's TCP/IP stack enforces this binding.

### 3. RAM-Only Conversation Storage

Conversations are stored exclusively in volatile memory (RAM). No conversation content is ever written to disk, database, log file, temporary file, or any persistent storage medium. On session termination, all conversation data is overwritten with cryptographically random bytes before memory deallocation.

### 4. No Content Logging

Kwyre maintains metadata-only audit logs (timestamps, session IDs, message counts). The content of user prompts and model responses is never recorded in any log, at any verbosity level, under any configuration.

### 5. Verified Integrity

At every startup, Kwyre verifies the cryptographic hashes of all installed dependencies and model configuration files against a known-good manifest. Any tampering — including supply-chain attacks via compromised Python packages — causes immediate process termination.

### 6. Intrusion Response

A background watchdog monitors for active debugging tools, traffic analyzers, and unexpected outbound connections. Upon confirmed detection, all sessions are immediately wiped and the inference process is terminated.

---

## Regulatory Alignment

| Regulation | Relevant Requirement | Kwyre Compliance Posture |
|-----------|---------------------|-------------------------|
| **GDPR** Art. 25 | Data Protection by Design and Default | Personal data never leaves the data controller's infrastructure. No processing by third parties. |
| **GDPR** Art. 28 | Processor Obligations | Not applicable — Kwyre does not act as a data processor. All processing is local to the controller. |
| **GDPR** Art. 44-49 | International Data Transfers | Not applicable — no data transfer occurs. |
| **HIPAA** § 164.312 | Technical Safeguards | Access controls via API key authentication. Transmission security is moot (no transmission). Audit controls via `/audit` endpoint. |
| **SOC 2** CC6/CC7 | Logical Access / System Operations | API key authentication, session isolation, integrity monitoring, incident response (L6 auto-wipe). |
| **FINRA** Rule 3110 | Supervision of Communications | No communications leave the supervised environment. Full audit trail of session metadata. |
| **ITAR** § 120.17 | Defense Articles / Technical Data | No export occurs — technical data remains on the user's machine within the controlled environment. |
| **FRE** Rule 901(b)(9) | Authentication of Evidence | Chain of custody preserved — evidence data never traverses third-party systems. |
| **ABA** Model Rule 1.6 | Confidentiality of Information | Attorney-client communications never leave the attorney's machine. No third-party access. |

---

## Scope and Limitations

This attestation covers the Kwyre AI inference server software as distributed by Apollo CyberSentinel LLC. It does not cover:

- The security posture of the user's host operating system, hardware, or network
- Physical security of the deployment environment
- User-introduced modifications to the Kwyre source code
- Third-party tools or scripts that interact with the Kwyre API
- Kernel-level attacks, cold boot attacks, or DMA-based memory extraction

Users are responsible for their own host-level security, physical access controls, and compliance determinations. This document provides technical facts about the software's architecture — it is not legal advice.

---

## Independent Verification

All claims in this attestation can be independently verified by the user or their auditor without cooperation from the Company. See the companion document `VERIFICATION_GUIDE.md` for step-by-step procedures.

---

**Apollo CyberSentinel LLC**
compliance@kwyre.com
