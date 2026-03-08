# Kwyre AI — Incident Response Procedures

**Document ID:** KWYRE-IR-001
**Purpose:** Procedures for security events, Layer 6 triggers, and anomaly handling.

---

## Incident Classification

| Severity | Trigger | Automated Response | Manual Action Required |
|----------|---------|-------------------|----------------------|
| **CRITICAL** | L6 intrusion detection (debugger/analyzer found) | All sessions wiped, server terminated | Investigate cause, review machine security |
| **CRITICAL** | L6 unexpected outbound connection detected | All sessions wiped, server terminated | Investigate compromised process, check dependencies |
| **HIGH** | L3 dependency hash mismatch at startup | Server refuses to start | Identify changed package, reinstall from clean source |
| **HIGH** | L4 model weight hash mismatch at startup | Server refuses to start | Verify model files, re-download if corrupted |
| **MEDIUM** | L3 unexpected package detected | Warning logged | Audit package, remove if unauthorized |
| **LOW** | Authentication failure (invalid API key) | Request rejected (401) | Review access logs if repeated |

---

## CRITICAL: Layer 6 Intrusion Detection

### What Happened

The background watchdog detected one of the following:

1. **Suspicious process running:** A debugging or traffic analysis tool was detected on the system (e.g., Wireshark, x64dbg, IDA Pro, Fiddler, Process Hacker, Ghidra, mitmproxy, Burp Suite).

2. **Unexpected outbound connection:** The inference process was found to have a network connection to an address other than `127.0.0.1`.

The watchdog requires **two consecutive detections** (10 seconds apart) to avoid false positives from briefly opened applications.

### Automated Response (Immediate)

The following actions occur automatically, in order:

1. All active conversation sessions are enumerated
2. Each session's message content is overwritten with `secrets.token_hex()` random bytes
3. Each session's metadata is cleared
4. Session objects are dereferenced
5. The event is logged (metadata only: timestamp, trigger type, session count)
6. The server process is terminated with exit code 1

**Total elapsed time from detection to wipe: < 2 seconds**

### Manual Response Procedure

After an L6 trigger:

1. **Do not restart the server immediately.** Investigate first.

2. **Identify the trigger:**
   - Check the server's last log output for the specific detection:
     ```
     [Layer 6] INTRUSION DETECTED: <tool_name or connection_details>
     [Layer 6] Emergency wipe: X sessions destroyed
     ```

3. **If triggered by a legitimate tool** (e.g., you intentionally opened Wireshark for verification):
   - Close the tool
   - Restart the Kwyre server
   - Resume normal operations
   - No further action required

4. **If triggered by an unexpected outbound connection:**
   - This is a serious security event
   - **Do not reconnect the machine to any network**
   - Run a full dependency audit:
     ```bash
     python security/verify_deps.py verify
     python security/verify_deps.py audit
     ```
   - Check for recently modified files:
     ```bash
     find / -mmin -60 -type f 2>/dev/null | head -50
     ```
   - Review running processes for anomalies
   - Consider reimaging the machine from a known-good backup

5. **If triggered by an unknown process:**
   - Identify the process that triggered detection
   - Determine if it is a legitimate system tool or potential threat
   - If uncertain, treat as a security incident and escalate

### Reporting

Document the following for any L6 trigger:

| Field | Value |
|-------|-------|
| Date/Time | |
| Trigger Type | Suspicious process / Outbound connection |
| Trigger Details | |
| Active Sessions at Time of Wipe | |
| Cause Identified | Yes / No |
| Legitimate Trigger | Yes / No |
| Remediation Taken | |
| Server Restarted | Yes / No — Time: |
| Reported By | |

---

## HIGH: Layer 3 Dependency Failure

### What Happened

At startup, the SHA256 hash of one or more installed Python packages does not match the recorded manifest. This could indicate:

- A pip package was updated (intentionally or via automated update)
- A supply-chain attack modified package files post-install
- The manifest is outdated after a legitimate upgrade

### Response Procedure

1. **Review the failure output:**
   ```
   [Layer 3] *** DEPENDENCY INTEGRITY FAILURES ***
     [FAIL] VERSION MISMATCH: transformers (expected 4.x.x, got 4.y.y)
   ```

2. **If the change was intentional** (you ran `pip install --upgrade`):
   - Re-run manifest generation:
     ```bash
     python security/verify_deps.py generate
     ```
   - Commit the updated manifest
   - Restart the server

3. **If the change was NOT intentional:**
   - **Do not start the server**
   - Investigate how the package was modified
   - Check `pip list --outdated` for unexpected version changes
   - Review pip installation logs
   - Reinstall from clean source:
     ```bash
     pip install --force-reinstall <package_name>==<expected_version>
     ```
   - Re-verify:
     ```bash
     python security/verify_deps.py verify
     ```

---

## HIGH: Layer 4 Model Weight Failure

### What Happened

At startup, the SHA256 hash of model configuration files does not match the expected values. This could indicate:

- Model files were corrupted (disk error, incomplete download)
- Model was intentionally replaced or modified
- An attacker substituted a trojaned model

### Response Procedure

1. **Do not start the server with unverified weights.**

2. **Check for corruption:**
   ```bash
   # Re-download and verify
   python -c "from transformers import AutoModelForCausalLM; \
   AutoModelForCausalLM.from_pretrained('Qwen/Qwen3.5-9B', force_download=True)"
   ```

3. **Re-compute expected hashes** from the fresh download and update the server configuration.

4. **If substitution is suspected:**
   - Preserve the modified files for forensic analysis
   - Do not use them for inference
   - Investigate how files were modified
   - Consider reimaging the machine

---

## Data Breach Assessment

Because Kwyre stores conversations only in RAM and never transmits data externally, the scope of a potential data breach is limited to:

| Scenario | Data at Risk | Duration of Exposure |
|----------|-------------|---------------------|
| L6 auto-wipe triggered | None — sessions wiped before attacker can extract | < 2 seconds |
| Machine physically seized while server is running | Active RAM contents (current sessions only) | Until power loss (RAM is volatile) |
| Machine physically seized while server is stopped | None — no persistent conversation storage | N/A |
| Compromised dependency detected at startup | None — server refuses to start | N/A |

**In all normal operational scenarios, there is no persistent data to breach.** Conversations exist only in volatile RAM during active sessions and are cryptographically wiped on session end.

---

## Escalation Contacts

| Role | Contact | When to Escalate |
|------|---------|-----------------|
| System Administrator | [your IT contact] | Any L6 trigger from unknown cause |
| Security Officer | [your security contact] | Suspected supply-chain attack, model substitution |
| Legal Counsel | [your legal contact] | Any incident involving active case data |
| Apollo CyberSentinel | security@kwyre.com | Software defects, vulnerability reports |

---

## Incident Log Template

Maintain a log of all security events for compliance auditing:

```
Date: YYYY-MM-DD HH:MM
Severity: CRITICAL / HIGH / MEDIUM / LOW
Layer: L3 / L4 / L6 / Auth
Description:
Root Cause:
Sessions Active at Time:
Data Exposure: None / Potential (describe)
Remediation:
Time to Resolution:
Reported By:
Reviewed By:
```

---

*All incident response procedures can be executed entirely by the customer's IT and security team. No vendor access, credentials, or cooperation is required.*
