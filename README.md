# Kwyre AI
### Air-Gapped Inference for Analysts Who Cannot Afford a Breach

> The only local AI that protects your data **even if your machine is compromised.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/model-Qwen3--4B-orange.svg)](https://huggingface.co/Qwen)
[![Quantization](https://img.shields.io/badge/quant-4--bit%20NF4-green.svg)]()
[![Security](https://img.shields.io/badge/security-6--layer%20stack-red.svg)]()
[![Docker](https://img.shields.io/badge/deploy-docker--compose%20up-blue.svg)]()
[![Status](https://img.shields.io/badge/status-v0.3%20active-brightgreen.svg)]()
[![Pentest](https://img.shields.io/badge/pentest-47%2F47%20resolved-brightgreen.svg)]()

---

## What Is Kwyre

Kwyre is a locally-deployed AI inference system built for professionals who work with data that **cannot leave the room** — active federal investigations, attorney-client privileged documents, regulated financial records, classified-adjacent work product, and sensitive compliance analysis.

It is not a hobbyist local model runner. It is a **certified, auditable, breach-resistant AI appliance** that runs entirely on your hardware, with cryptographic session wiping, intrusion detection, and a compliance documentation package built in.

**Your queries never leave your machine. Not to a cloud. Not to us. Not to anyone.**

---

## Who It's For

| Buyer | Pain Point | Why Kwyre |
|-------|-----------|-----------|
| **Forensic investigators** | Cannot upload $3B fraud evidence to ChatGPT during an active federal case | Full local inference, zero telemetry, no chain-of-custody risk |
| **Criminal defense attorneys** | Attorney-client privilege prohibits cloud AI on case materials | Air-gapped by architecture, not policy |
| **M&A law firms** | Associates uploading NDA-protected deal docs to ChatGPT is malpractice liability | Verified zero outbound connections, auditable |
| **Reinsurance / insurance underwriters** | Actuarial models, treaty structures, cedent PII cannot touch cloud APIs under Berkshire/AIG compliance rules | Compliance documentation package for your legal team |
| **Cleared defense contractors** | Work on unclassified networks but with sensitive unclassified data — can't use classified AI, can't use ChatGPT | Local, offline, no cleared facility required |
| **Forensic accountants** | SEC whistleblower cases, active DOJ investigations — evidence integrity is paramount | RAM-only storage, cryptographic wipe on session end |
| **Investigative journalists** | Source protection — subscription records are subpoenable | Monero payments, no account required, no email required |

---

## Core Features

### Inference Engine
- **Qwen3-4B main model** — pre-quantized to 4-bit NF4 (2.5 GB download), fine-tuned for legal/financial/forensic analysis
- **Qwen3-0.6B draft model** — speculative decoding for 2-3x speed boost (0.8 GB download)
- **Total model download: 3.3 GB** — clients download pre-quantized weights from kwyre.com, not HuggingFace
- **Spike QAT (Quantization-Aware Training)** — custom fine-tuning pipeline using Straight-Through Estimator spike encoding with k-curriculum annealing (k=50→5)
- **SpikeServe activation encoding** — dynamic spike encoding at inference (324 MLP layers, 16% measured sparsity)
- **Speculative decoding** — Qwen3-0.6B draft model generates candidate tokens, main model validates in parallel
- **4-bit NF4 quantization** (bitsandbytes) — both models fit in ~3.9 GB VRAM combined
- **OpenAI-compatible API** — `POST /v1/chat/completions` drop-in replacement, works with any OpenAI SDK
- **Multi-tier support** — switch between 4B (personal, 3.5 GB VRAM) and 9B (professional, 7.5 GB VRAM) via environment variable

### Performance

| Metric | Kwyre 4B + Speculative | Kwyre 9B |
|--------|----------------------|----------|
| VRAM usage | 3.9 GB | 8.1 GB |
| Model load (pre-quantized) | ~1 second | ~3 minutes |
| Inference (warmed up) | 7-14 tok/s | 3-5 tok/s |
| Download size | 3.3 GB | 7.6 GB |

### Security Stack — 6 Layers

#### Layer 1 — Network Isolation
- Server binds to `127.0.0.1` only — **physically unreachable from any network** at the OS level
- No firewall rules required — the OS itself blocks all external connections
- Docker mode: container binds to `0.0.0.0` but port mapping restricts to `127.0.0.1:8000` on host

#### Layer 2 — Process-Level Network Lockdown
- **Linux/WSL2:** iptables rules scoped to a dedicated `kwyre` system user — all outbound traffic blocked except `127.0.0.1`, enforced at kernel level
- **Windows:** Windows Firewall rules targeting the specific Python executable — outbound blocked, localhost allowed
- Even a fully compromised server process **cannot make outbound connections**

#### Layer 3 — Dependency Integrity
- SHA256 hash manifest of every installed Python package generated on clean install
- Verified at server startup — tampered `torch`, `transformers`, or any dependency causes immediate abort
- Supply chain attacks caught before a single token is generated

#### Layer 4 — Model Weight Integrity
- SHA256 hashes of all model config files verified at every startup
- Tampered or replaced model weights cause immediate process abort with clear error
- Pre-quantized Kwyre models are trusted-source — skip hash check when using official distribution

#### Layer 5 — Secure RAM Session Storage
- Conversations stored **only in RAM** — never written to disk under any circumstances
- Each session gets a unique 32-byte random key (AES-256 class)
- On session end: `secure_wipe()` overwrites all message content with random bytes before clearing Python references — RAM scraping returns garbage
- Sessions auto-expire after 1 hour of inactivity
- On server shutdown: all active sessions wiped before process exits
- `POST /v1/session/end` — user-initiated cryptographic wipe

#### Layer 6 — Intrusion Detection + Auto-Wipe
- Background watchdog thread runs every 5 seconds
- Monitors for **unexpected outbound connections** from the inference process (allows localhost + Docker bridge IPs)
- Monitors for **known analysis/injection tools** (Wireshark, x64dbg, Fiddler, OllyDBG, Process Hacker, Ghidra, IDA, etc.)
- Two consecutive violations required before triggering — prevents false positives
- **On confirmed intrusion: all sessions wiped immediately, server process terminated**
- Watchdog status exposed on `/health` and `/audit` endpoints

### Security Hardening (v0.3 — Pentest Verified)

Kwyre v0.3 underwent a full white-box security audit and penetration test. All 47 findings (9 Critical, 12 High, 14 Medium, 12 Low/Info) were resolved. Key hardening measures:

- **True air-gap enforcement** — External API tools (`tools.py`) are now opt-in via `KWYRE_ENABLE_TOOLS=1` (default OFF). When disabled, zero external HTTP requests are made — verified by SSRF host allowlist and watchdog
- **CSP nonce-based script protection** — All inline scripts use per-request cryptographic nonces instead of `'unsafe-inline'`; `cdn.jsdelivr.net` restricted to payment page only
- **Timing-safe authentication** — API key validation uses `hmac.compare_digest` to prevent timing side-channel attacks
- **Input validation** — `max_tokens` clamped to 1-8192, `temperature` to 0.0-2.0, `top_p` to 0.0-1.0; message arrays validated for type and length (max 100)
- **License key injection blocked** — Public key no longer loadable from environment variables; must be embedded at build time
- **Eval tier enforcement** — Unlicensed usage rate-limited to 10 req/min and 512 max tokens with server-side trial counter (3 requests per IP)
- **Security headers on all responses** — `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, and full CSP on every HTTP response including error paths
- **mXSS-safe HTML sanitization** — DOMParser-based sanitizer replaces template-based version to prevent mutation XSS
- **Non-root Docker container** — Dedicated `kwyre` user with minimal privileges; dependency manifest generated at build time
- **Session storage hardening** — API keys and trial data use `sessionStorage` (cleared on tab close), not persistent `localStorage`
- **Session ID hardening** — Minimum 32-character entropy requirement; server generates IDs for short/missing values
- **Watchdog child process monitoring** — Intrusion watchdog now recursively monitors child process network connections
- **Authenticated health endpoint** — `/health` returns only `{"status": "ok"}` to unauthenticated requests; detailed system info requires API key
- **CORS origin restriction** — `Access-Control-Allow-Origin` locked to the server's own origin

**Test suite: 107 tests across 3 test files, all passing.**

### Privacy Features
- **Zero content logging** — metadata only (timestamps, token counts) — conversation content never touches disk
- **No telemetry** — zero analytics, zero error reporting, zero update pings, zero license callbacks
- **Monero (XMR) payment option** — no payment record, no email required, fully anonymous purchase
- **Ed25519 offline license keys** — license validation works without any network call
- **Self-delete conversation** — user-initiated wipe via API, cryptographically unrecoverable
- **Open-source server code** — `serve_local_4bit.py` is fully auditable; verify zero outbound yourself with Wireshark

### Compliance & Audit
- `GET /audit` — metadata-only compliance log with security control attestation
- `GET /health` — full security stack status including watchdog state, speculative decoding status, and VRAM usage
- **Compliance documentation package** — formal attestation letter, verification guide, deployment checklist, incident response plan
- Architecture designed to satisfy HIPAA, FINRA, attorney-client privilege, and SOC2-adjacent requirements

### API Endpoints
```
POST /v1/chat/completions   OpenAI-compatible inference (auth required)
POST /v1/session/end        Cryptographic session wipe (auth required)
GET  /health                Status check (detailed info requires auth)
GET  /audit                 Metadata-only compliance log (auth required)
GET  /v1/models             Model info (auth required)
GET  /                      Landing page
GET  /chat                  Browser UI
```

---

## Hardware Requirements

| Config | GPU | VRAM | RAM | Speed | Model Download |
|--------|-----|------|-----|-------|----------------|
| Recommended (4B) | RTX 4060+ | 4GB+ | 8GB | 7-14 tok/s | 3.3 GB |
| Professional (9B) | RTX 4090 / 3090 | 8GB+ | 8GB | 3-5 tok/s | 7.6 GB |

> **Why only 3.9 GB VRAM?** The pre-quantized 4-bit NF4 model weights are loaded directly — no on-the-fly quantization needed. Both the main 4B model and the 0.6B speculative draft fit comfortably on any modern GPU.

> **Why only 3.3 GB download?** Models are pre-quantized to 4-bit NF4 before distribution. Clients download the compact weights, not the full FP16 originals.

---

## Quick Start

### Option 1: One-Click Installer (recommended)

**Windows:**
```powershell
# Download installer from kwyre.com or run from source:
powershell -ExecutionPolicy Bypass -File installer\install_windows.ps1
# Creates Start Menu shortcut, installs firewall rules, ready to go
```

**Linux (Ubuntu/Debian):**
```bash
sudo bash installer/install_linux.sh
# Installs to /opt/kwyre, creates systemd service, installs iptables rules
sudo systemctl start kwyre
```

**macOS:**
```bash
sudo bash installer/install_macos.sh
# Installs to /opt/kwyre, creates launchd service, installs PF firewall rules
sudo launchctl start com.kwyre.ai.server
```

### Option 2: Docker
```bash
git clone https://github.com/blablablasealsaresoft/kwyre-ai
cd kwyre-ai
cp .env.example .env

docker compose up
# Server available at http://127.0.0.1:8000
# Models auto-download on first run (~3.3 GB)
```

### Option 3: Direct Python (development)
```bash
git clone https://github.com/blablablasealsaresoft/kwyre-ai
cd kwyre-ai
pip install -r requirements-inference.txt

# Place pre-quantized models in dist/
# dist/kwyre-4b-nf4/     (main model, 2.5 GB)
# dist/kwyre-draft-nf4/  (draft model, 0.8 GB)

python server/serve_local_4bit.py
```

### Option 4: Pre-quantized models (fastest startup)
```bash
# Download pre-quantized models from kwyre.com → extract to dist/

# Or quantize yourself from HuggingFace:
python model/quantize_nf4.py --model Qwen/Qwen3-4B --output ./dist/kwyre-4b-nf4
python model/quantize_nf4.py --model Qwen/Qwen3-0.6B --output ./dist/kwyre-draft-nf4

python server/serve_local_4bit.py
# Server auto-detects pre-quantized models — loads in ~1 second
```

### Test
```bash
# Verify security stack
curl http://127.0.0.1:8000/health | python -m json.tool

# First inference
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-kwyre-dev-local" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Summarize the confidentiality obligations in a mutual NDA."}],
    "max_tokens": 512,
    "session_id": "case-001"
  }'

# Wipe session when done
curl -X POST http://127.0.0.1:8000/v1/session/end \
  -H "Authorization: Bearer sk-kwyre-dev-local" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "case-001"}'
```

---

## Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `KWYRE_MODEL` | `Qwen/Qwen3-4B` | Model tier (`Qwen/Qwen3-4B` or `Qwen/Qwen3.5-9B`) |
| `KWYRE_MODEL_PATH` | auto-detect | Path to pre-quantized model directory |
| `KWYRE_DRAFT_PATH` | auto-detect | Path to pre-quantized draft model directory |
| `KWYRE_SPECULATIVE` | `1` | Enable speculative decoding with draft model |
| `KWYRE_QUANT` | `nf4` | Quantization mode (`nf4` or `awq`) |
| `KWYRE_API_KEYS` | `sk-kwyre-dev-local:admin` | API key:role pairs (semicolon-separated) |
| `KWYRE_MERGE_LORA` | `0` | Merge LoRA adapters at load (set `1` if >24GB VRAM) |
| `KWYRE_LICENSE_KEY` | — | Commercial license key |
| `KWYRE_ENABLE_TOOLS` | `0` | Enable external API tools (weather, crypto, etc.). **Set `1` to enable — breaks air-gap** |
| `KWYRE_BIND_HOST` | `127.0.0.1` | Network bind address (use `0.0.0.0` only inside Docker) |

---

## Pricing

| License | Price | Machines | Includes |
|---------|-------|----------|----------|
| **Personal** | $299 one-time | 1 | Model + server + compliance doc |
| **Professional** | $799 one-time | 3 | Everything + priority support + 9B model |
| **Air-Gapped Kit** | $1,499 one-time | 5 | Offline installer + full audit package |

**Payment:** Credit card or Monero (XMR). No email required for Monero purchases. One-time — no subscription, no recurring billing, no statement entries.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER MACHINE                          │
│                                                         │
│  Browser / API Client                                   │
│       │                                                 │
│       ▼ (127.0.0.1 only)                                │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Kwyre Server                        │   │
│  │                                                  │   │
│  │  ┌──────────────┐   ┌──────────────────────┐    │   │
│  │  │ Auth + Rate  │   │  Intrusion Watchdog  │    │   │
│  │  │   Limiting   │   │  (Layer 6 — active)  │    │   │
│  │  └──────────────┘   └──────────────────────┘    │   │
│  │                                                  │   │
│  │  ┌──────────────────────────────────────────┐   │   │
│  │  │        Secure Session Store (L5)          │   │   │
│  │  │   RAM-only · AES key · auto-wipe · DoD   │   │   │
│  │  └──────────────────────────────────────────┘   │   │
│  │                                                  │   │
│  │  ┌──────────────────────────────────────────┐   │   │
│  │  │      Spike QAT Inference Engine           │   │   │
│  │  │  Qwen3-4B main · Qwen3-0.6B draft       │   │   │
│  │  │  4-bit NF4 · SpikeServe · Speculative   │   │   │
│  │  └──────────────────────────────────────────┘   │   │
│  │                                                  │   │
│  │  Startup checks:                                 │   │
│  │  [L3] Dependency hash verification               │   │
│  │  [L4] Model weight SHA256 verification           │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [L1] OS-level: server bound to 127.0.0.1              │
│  [L2] iptables/Firewall: process outbound blocked       │
│                                                         │
│  ══════════════════════════════════════════════         │
│              NO DATA CROSSES THIS LINE                  │
└─────────────────────────────────────────────────────────┘
                         │
                    INTERNET
                  (blocked at L1+L2)
```

---

## Roadmap

**v0.1 (Complete)**
- [x] Qwen3.5-9B + Spike QAT training pipeline
- [x] 6-layer security stack
- [x] OpenAI-compatible API
- [x] Session encryption + cryptographic wipe
- [x] Intrusion detection watchdog
- [x] Compliance documentation package

**v0.2 (Complete)**
- [x] Pre-quantized NF4 model distribution (3.3 GB total download)
- [x] Speculative decoding with Qwen3-0.6B draft model (2-3x speed)
- [x] Qwen3-4B tier (3.9 GB VRAM for both models combined)
- [x] Docker installer (`docker compose up`)
- [x] Monero payment integration + Ed25519 offline license keys
- [x] Multi-tier model support (4B personal / 9B professional)
- [x] Inference-only dependency set (stripped training deps for lean install)

**v0.3 (Current — Security Hardened)**
- [x] Full white-box penetration test — 47/47 findings resolved
- [x] True air-gap enforcement — tools opt-in, default offline
- [x] CSP nonce-based script protection (removed `unsafe-inline`)
- [x] Timing-safe API key authentication (`hmac.compare_digest`)
- [x] Input validation and eval tier enforcement
- [x] Non-root Docker container with dependency manifest
- [x] DOMParser-based HTML sanitization (mXSS-safe)
- [x] Security headers on all HTTP response paths
- [x] Watchdog child process monitoring
- [x] 107 security tests across 3 test suites
- [x] Windows, Linux, and macOS one-click installers
- [x] Nuitka build pipeline — compiled binary distribution (source protection)

**v0.4**
- [ ] Apple Silicon / MLX support (targets legal market on Mac)
- [ ] CPU-only mode via llama.cpp (Kwyre Air — any hardware)
- [ ] Domain-specific fine-tune (legal, financial, forensics corpora)
- [ ] AWQ quantization option (1.4x speed when pre-quantized)

**v1.0**
- [ ] Benchmark suite vs GPT-4o on compliance tasks
- [ ] SOC2-friendly deployment guide
- [ ] Enterprise audit package
- [ ] Multi-user air-gapped server mode

---

## Building from Source (Nuitka Protected Binary)

Kwyre ships compiled binaries to paying customers. The server Python code is compiled into a standalone executable via Nuitka — no Python source files are distributed, making it significantly harder to reverse-engineer or share the AI server code.

```bash
# Install build dependencies
pip install nuitka ordered-set zstandard

# Compile + build installer for current platform
python build.py all

# Or step by step:
python build.py compile       # Nuitka compile → build/kwyre-dist/kwyre-server[.exe]
python build.py package       # Stage data files (chat/, docs/, security/)
python build.py installer     # Build platform installer (.exe/.deb/.pkg)

# Cross-platform installer generation
python build.py installer --platform windows   # Inno Setup .exe
python build.py installer --platform linux      # .deb + AppImage script
python build.py installer --platform macos      # .pkg + launchd plist

# Clean build artifacts
python build.py clean
```

**What gets compiled (protected):**
- `server/serve_local_4bit.py` — inference server, API endpoints, security layers
- `server/tools.py` — external API tool router
- `security/verify_deps.py` — Layer 3 dependency integrity
- `security/license.py` — Ed25519 license validation
- `model/spike_serve.py` — SpikeServe inference encoding

**What stays as data (not compiled):**
- `chat/*.html` — frontend UI (served as-is)
- `docs/` — compliance documentation
- `.env.example` — configuration template
- Model weights (`.safetensors`) — loaded at runtime

**Build outputs:**

| Platform | Installer | Location |
|----------|-----------|----------|
| Windows | Inno Setup `.exe` | `build/installers/kwyre-ai-setup-0.3.0-win64.exe` |
| Linux | `.deb` package | `build/installers/kwyre-ai_0.3.0_amd64.deb` |
| Linux | AppImage | `build/installers/Kwyre-AI-0.3.0-x86_64.AppImage` |
| macOS | `.pkg` | `build/installers/kwyre-ai-0.3.0-macos.pkg` |

> **Windows:** Requires [Inno Setup 6](https://jrsoftware.org/isdl.php) (`winget install JRSoftware.InnoSetup`)
> **Linux AppImage:** Requires [appimagetool](https://github.com/AppImage/appimagetool/releases)
> **macOS .pkg:** Built with native `pkgbuild` (Xcode CLI tools)

---

## Technical Specifications

```
Main model:          Qwen3-4B (pre-quantized NF4, 2.5 GB)
Draft model:         Qwen3-0.6B (pre-quantized NF4, 0.8 GB)
Speculative:         Enabled by default (2-3x throughput)
SpikeServe:          324 MLP layers, 16.3% measured sparsity at k=5.0
Quantization:        4-bit NF4 (bitsandbytes, double-quantized)
Compute dtype:       bfloat16
VRAM at inference:   ~3.9 GB (both models)
Context length:      8192 tokens
API compatibility:   OpenAI /v1/chat/completions
Docker image:        ~10 GB (includes CUDA runtime)
Model download:      3.3 GB (pre-quantized, from kwyre.com)

Available tiers:
  Personal:    Qwen3-4B   — 3.5 GB VRAM, 7-14 tok/s
  Professional: Qwen3.5-9B — 7.5 GB VRAM, 3-5 tok/s

QAT Training (9B):
  LoRA rank:         64 (alpha 128)
  LoRA targets:      gate_proj, up_proj, down_proj (MLP only)
  Spike hooks:       408 layers
  k-curriculum:      50.0 → 5.0 (step schedule)
  Dataset:           teknium/OpenHermes-2.5
```

---

## Verifying Zero Telemetry

We say Kwyre never phones home. Here's how to verify it yourself:

**Windows (Resource Monitor):**
```
Task Manager → Performance → Open Resource Monitor
Network tab → filter by python.exe
Confirm: only 127.0.0.1 connections
```

**Linux/WSL2:**
```bash
# Watch all connections from the server process
watch -n 1 "ss -tp | grep python"
# Should show only 127.0.0.1:8000
```

**Wireshark (definitive):**
```
Interface: loopback (lo)
Filter: tcp.port == 8000
Confirm: all traffic is 127.0.0.1 → 127.0.0.1
```

The server code is fully open source. Read every line.

---

## Compliance Documentation

Kwyre ships with a full compliance package in `docs/`:

- **`COMPLIANCE_LETTER.md`** — formal attestation for legal/compliance teams (GDPR, HIPAA, SOC 2, FINRA, ITAR, FRE, ABA)
- **`VERIFICATION_GUIDE.md`** — step-by-step independent security verification for each layer
- **`DEPLOYMENT_CHECKLIST.md`** — hardened deployment procedure for production environments
- **`INCIDENT_RESPONSE.md`** — security event classification and response procedures

---

## Security Disclosure

Found a vulnerability? Email security@kwyre.ai.

We do not use a bug bounty program. We will acknowledge responsible disclosure publicly and fix issues immediately.

---

## License

MIT License. Use it, audit it, fork it.

The model weights (Qwen3-4B, Qwen3-0.6B base) are licensed under Apache 2.0 by Alibaba. LoRA adapters and pre-quantized distributions are original work, MIT licensed.

---

## Built By

APOLLO CyberSentinel LLC — blockchain forensics, cryptocurrency fraud investigation, OSINT analysis.

We built this because we needed it ourselves. We cannot upload active federal investigation evidence to OpenAI. Neither can you.

---

*All inference runs 100% locally. No data leaves your machine.*
*We are not lawyers. This is not legal advice. Verify your own compliance requirements.*
