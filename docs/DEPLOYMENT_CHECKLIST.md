# Kwyre AI — Secure Deployment Checklist

**Document ID:** KWYRE-DEP-001
**Purpose:** Step-by-step hardened deployment procedure for production environments.

---

## Pre-Deployment

- [ ] **Hardware requirements verified**
  - NVIDIA GPU with 8+ GB VRAM (RTX 3060 or better)
  - 16+ GB system RAM
  - 20+ GB disk space for model weights
  - Windows 10/11, Ubuntu 20.04+, or WSL2

- [ ] **Network environment assessed**
  - Machine does not need internet access after initial setup
  - No VPN, proxy, or tunneling software required
  - Air-gapped deployment supported (offline installer available)

---

## Phase 1: Clean Installation

### 1.1 Model Download (requires internet — one time only)

- [ ] Download model weights from HuggingFace
  ```bash
  python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
  AutoTokenizer.from_pretrained('Qwen/Qwen3.5-9B'); \
  AutoModelForCausalLM.from_pretrained('Qwen/Qwen3.5-9B', torch_dtype='auto')"
  ```
- [ ] Verify model files exist in HuggingFace cache
- [ ] Note the SHA256 hashes of model config files for L4 verification

### 1.2 Dependency Installation

- [ ] Create isolated Python environment
  ```bash
  python -m venv kwyre-env
  source kwyre-env/bin/activate  # Linux
  kwyre-env\Scripts\activate     # Windows
  ```
- [ ] Install dependencies from locked requirements
  ```bash
  pip install -r requirements.txt
  ```
- [ ] Generate dependency manifest (Layer 3)
  ```bash
  python security/verify_deps.py generate
  ```
- [ ] Commit manifest to version control

### 1.3 Verify Clean Install

- [ ] Run dependency integrity check
  ```bash
  python security/verify_deps.py verify
  ```
- [ ] Run dependency audit
  ```bash
  python security/verify_deps.py audit
  ```
- [ ] Confirm zero unexpected packages

---

## Phase 2: Security Stack Activation

### 2.1 Layer 1 — Localhost Binding

- [ ] Confirm `BIND_HOST = "127.0.0.1"` in `serve_local_4bit.py`
- [ ] Start server and verify binding:
  ```powershell
  # Windows
  Get-NetTCPConnection -LocalPort 8000 | Select LocalAddress
  ```
  ```bash
  # Linux
  ss -tlnp | grep 8000
  ```
- [ ] Confirm output shows `127.0.0.1` only

### 2.2 Layer 2 — Process Network Isolation

- [ ] **Linux/WSL2:** Install iptables rules
  ```bash
  sudo ./security/setup_isolation.sh install
  ```
- [ ] **Windows:** Apply firewall rules (elevated PowerShell)
  ```powershell
  # See setup_isolation.sh windows for full commands
  sudo ./security/setup_isolation.sh windows
  ```
- [ ] Verify rules are active
  ```bash
  sudo ./security/setup_isolation.sh status
  ```

### 2.3 Layer 3 — Dependency Integrity

- [ ] Confirm manifest exists at `security/kwyre_dep_manifest.json`
- [ ] Run verification
  ```bash
  python security/verify_deps.py verify-core
  ```
- [ ] All core packages show `[OK]`

### 2.4 Layer 4 — Model Weight Integrity

- [ ] Start server and confirm startup log shows:
  ```
  [Layer 4] Model integrity check: PASSED
  ```

### 2.5 Layer 5 — RAM Session Storage

- [ ] Confirm no database files, SQLite files, or conversation logs on disk
- [ ] Test session lifecycle:
  1. Create session, send message
  2. End session via API
  3. Search disk for message content — confirm not found

### 2.6 Layer 6 — Intrusion Watchdog

- [ ] Confirm health endpoint shows watchdog running:
  ```bash
  curl http://127.0.0.1:8000/health | python -m json.tool
  ```
- [ ] Test detection (optional): open a monitored tool, confirm server terminates

---

## Phase 3: Network Verification

- [ ] **Wireshark full capture test**
  1. Start capture on all interfaces
  2. Start Kwyre server
  3. Send 5+ queries
  4. Filter: `ip.dst != 127.0.0.1`
  5. Confirm zero external packets
- [ ] **DNS monitoring test**
  ```bash
  sudo tcpdump -i any port 53 -n  # during server operation
  ```
  Confirm zero DNS queries from the Kwyre process

---

## Phase 4: API Key Configuration

- [ ] Generate production API key
  ```bash
  # Use a strong random key
  python -c "import secrets; print(f'sk-kwyre-{secrets.token_hex(32)}')"
  ```
- [ ] Set via environment variable
  ```bash
  export KWYRE_API_KEYS="sk-kwyre-<your-key>:admin"
  ```
- [ ] Test authentication
  ```bash
  curl -H "Authorization: Bearer sk-kwyre-<your-key>" http://127.0.0.1:8000/health
  ```
- [ ] Confirm unauthenticated requests are rejected (401)

---

## Phase 5: Post-Deployment Validation

- [ ] Run full verification guide (`VERIFICATION_GUIDE.md`) — all 14 checks pass
- [ ] Review audit endpoint output
  ```bash
  curl http://127.0.0.1:8000/audit
  ```
- [ ] Document deployment metadata:
  - Machine hostname: ___________________
  - GPU model: ___________________
  - Deployment date: ___________________
  - Kwyre version: ___________________
  - Deployer: ___________________

---

## Ongoing Operations

- [ ] **At every startup:** L3 + L4 integrity checks run automatically
- [ ] **Weekly:** Review audit logs for anomalies
- [ ] **After any system update:** Re-run `verify_deps.py verify` to confirm no packages changed
- [ ] **After any model update:** Regenerate L4 hashes and update server
- [ ] **Quarterly:** Run full verification guide and document results

---

## Air-Gapped Deployment (No Internet)

For environments where the deployment machine has no internet access:

1. On an internet-connected staging machine:
   - Download model weights
   - Install all pip packages
   - Generate dependency manifest
   - Copy the entire Kwyre directory + HuggingFace cache to a USB drive

2. Transfer USB drive to air-gapped machine

3. Install from local files:
   ```bash
   pip install --no-index --find-links ./wheels -r requirements.txt
   ```

4. Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`

5. Follow Phase 2-5 above (no internet required)

---

**Deployer:** _________________________ **Date:** _____________

**Organization:** _________________________ **Signature:** _____________
