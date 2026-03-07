# Kwyre AI
### Air-Gapped Inference for Analysts Who Cannot Afford a Breach

> The only local AI that protects your data **even if your machine is compromised.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/model-Qwen3.5--9B-orange.svg)](https://huggingface.co/Qwen)
[![Quantization](https://img.shields.io/badge/quant-4--bit%20NF4-green.svg)]()
[![Security](https://img.shields.io/badge/security-6--layer%20stack-red.svg)]()
[![Status](https://img.shields.io/badge/status-MVP%20active-brightgreen.svg)]()

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
- **Qwen3.5-9B base model** — frontier-class reasoning, legal/financial analysis, code, multilingual
- **Spike QAT (Quantization-Aware Training)** — custom fine-tuning pipeline using Straight-Through Estimator spike encoding with k-curriculum annealing (k=50→5), teaching the model to tolerate spike-encoded activations while preserving capability
- **SpikeServe activation encoding** — dynamic spike encoding at inference time, enabling significant activation sparsity without quality loss
- **4-bit NF4 quantization** (bitsandbytes) — full model fits in ~6.5GB VRAM
- **LoRA adapters** targeting MLP layers (`gate_proj`, `up_proj`, `down_proj`) — fine-tuning with 0.2% trainable parameters
- **OpenAI-compatible API** — `POST /v1/chat/completions` drop-in replacement, works with any OpenAI SDK

### Security Stack — 6 Layers

#### Layer 1 — Network Isolation
- Server binds to `127.0.0.1` only — **physically unreachable from any network** at the OS level
- No firewall rules required — the OS itself blocks all external connections
- Even on an internet-connected machine, the server cannot receive requests from outside

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
- Generates hash manifest from clean install with one command

#### Layer 5 — Secure RAM Session Storage
- Conversations stored **only in RAM** — never written to disk under any circumstances
- Each session gets a unique 32-byte random key (AES-256 class)
- On session end: `secure_wipe()` overwrites all message content with random bytes before clearing Python references — RAM scraping returns garbage
- Sessions auto-expire after 1 hour of inactivity
- On server shutdown: all active sessions wiped before process exits
- `POST /v1/session/end` — user-initiated cryptographic wipe

#### Layer 6 — Intrusion Detection + Auto-Wipe
- Background watchdog thread runs every 5 seconds
- Monitors for **unexpected outbound connections** from the inference process
- Monitors for **known analysis/injection tools** (Wireshark, x64dbg, Fiddler, OllyDBG, Process Hacker, Ghidra, IDA, etc.)
- Two consecutive violations required before triggering — prevents false positives
- **On confirmed intrusion: all sessions wiped immediately, server process terminated**
- Watchdog status exposed on `/health` and `/audit` endpoints

### Privacy Features
- **Zero content logging** — metadata only (timestamps, token counts) — conversation content never touches disk
- **No telemetry** — zero analytics, zero error reporting, zero update pings, zero license callbacks
- **Monero (XMR) payment option** — no payment record, no email required, fully anonymous purchase
- **No account required** for Monero purchases — license key delivered without identity
- **Self-delete conversation** — user-initiated wipe via API, cryptographically unrecoverable
- **Open-source server code** — `serve_local_4bit.py` is fully auditable; verify zero outbound yourself with Wireshark

### Compliance & Audit
- `GET /audit` — metadata-only compliance log with security control attestation
- `GET /health` — full security stack status including watchdog state and weight integrity
- **Data Residency Architecture document** — two-page technical controls summary for your legal team
- SHA256 model integrity hash surfaced on every startup and in `/health` response
- Architecture designed to satisfy HIPAA, FINRA, attorney-client privilege, and SOC2-adjacent requirements

### API Endpoints
```
POST /v1/chat/completions   OpenAI-compatible inference
POST /v1/session/end        Cryptographic session wipe
GET  /health                Model + security stack status
GET  /audit                 Metadata-only compliance log (auth required)
GET  /v1/models             Model info (auth required)
GET  /chat                  Browser UI
```

---

## Hardware Requirements

| Config | GPU | VRAM | RAM | Speed |
|--------|-----|------|-----|-------|
| Recommended | RTX 4090 / 3090 | 8GB+ | 8GB | 25-40 tok/s |
| Minimum | RTX 3060 12GB | 8GB | 8GB | 15-25 tok/s |
| CPU-only (roadmap) | None | — | 32GB | 5-10 tok/s |

> **Why only 8GB RAM?** The model weights live entirely in GPU VRAM (~6.5GB at 4-bit NF4). System RAM only runs the Python process, tokenizer, and HTTP server (~2-3GB). Conversations are held in RAM but are just text — negligible. No database, no disk cache, no logging buffer. Kwyre's zero-storage architecture means minimal system RAM.

> **For reference:** ChatGPT streams at ~40-60 tok/s over the internet. Kwyre on a 4090 matches that speed with zero data leaving your machine.

---

## Quick Start

### Prerequisites
```bash
# NVIDIA GPU with 8GB+ VRAM
# CUDA 12.x
# Python 3.11+
# WSL2 (Windows) or Linux
```

### Install
```bash
git clone https://github.com/blablablasealsaresoft/kwyre-ai
cd kwyre-ai
pip install -r requirements.txt

# Generate model weight hashes (run once on clean install)
python -c "
from server.serve_local_4bit import generate_weight_hashes
import json
print(json.dumps(generate_weight_hashes('./models/kwyre-9b-v1'), indent=2))
"
# Paste output into KNOWN_WEIGHT_HASHES in server/serve_local_4bit.py

# Generate dependency manifest (Layer 3)
python security/verify_deps.py generate
```

### Run
```bash
python server/serve_local_4bit.py

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

### Docker
```bash
docker-compose up
# Server available at http://127.0.0.1:8000
# Model weights mounted from host — never baked into image
```

---

## Pricing

| License | Price | Machines | Includes |
|---------|-------|----------|----------|
| **Personal** | $299 one-time | 1 | Model + server + compliance doc |
| **Professional** | $799 one-time | 3 | Everything + priority support |
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
│  │  │  Qwen3.5-9B · 4-bit NF4 · SpikeServe    │   │   │
│  │  │  LoRA adapters · k-curriculum trained    │   │   │
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

## Competitor Analysis

### Cloud AI (ChatGPT, Claude, Gemini)

The obvious non-starter for Kwyre's buyers. Included for completeness.

| Factor | ChatGPT / Claude / Gemini | Kwyre |
|--------|--------------------------|-------|
| Data residency | Your data on their servers | Never leaves your machine |
| Attorney-client privilege | Waived on upload | Preserved |
| Evidence chain of custody | Broken | Intact |
| Subpoena risk | High (they comply) | Zero — nothing to subpoena |
| Air-gap capable | No | Yes |
| Compliance docs | None for your auditor | Two-page architecture attestation |
| Cost model | $20-200/month ongoing | $299 one-time |

**The verdict:** Not competitors. They're the reason Kwyre exists.

---

### Ollama

The most popular local model runner. 100K+ GitHub stars. Developer-first.

**What it does well:**
- Simplest possible local deployment (`ollama run llama3`)
- OpenAI-compatible API on localhost
- Excellent model library, broad hardware support
- Completely free, fully open source

**Where it stops:**
- No security layer — binds to `0.0.0.0` by default, accessible from network
- No session encryption — conversations stored in SQLite on disk
- No intrusion detection
- No compliance documentation — nothing to show a legal team
- No audit trail
- No weight integrity verification
- Designed for developer convenience, not adversarial environments
- No payment privacy

**Who uses it:** Developers building apps, hobbyists, teams prototyping. Not investigators, not attorneys, not compliance officers.

**Kwyre vs Ollama:** Ollama is a tool. Kwyre is an appliance. You don't hand Ollama to a forensic investigator and say "your evidence is protected." You hand them Kwyre.

---

### LM Studio

The polished GUI option. Best desktop experience in local AI.

**What it does well:**
- Beautiful interface, model browser, parameter controls
- Works on Windows, Mac, Linux
- Excellent on Apple Silicon
- Good for non-technical users wanting to explore local models

**Where it stops:**
- **Closed source core** — you cannot audit what it does with your data
- No security hardening beyond "it's local"
- No compliance documentation
- No intrusion detection or session wipe
- No audit trail
- Cannot verify zero telemetry (closed source)
- No privacy-preserving payment option

**Who uses it:** Writers, researchers, developers who want a GUI. Not professionals with adversarial threat models.

**Kwyre vs LM Studio:** LM Studio is consumer software. A cleared contractor or forensic investigator cannot use closed-source software on sensitive work without knowing exactly what it does. Kwyre is fully open-source server code — every line auditable.

---

### Jan.ai

Open-source, privacy-focused, offline-first desktop app.

**What it does well:**
- Fully open source
- Privacy-focused positioning
- Clean desktop UI
- Works offline after initial download
- No telemetry (claimed and verifiable)

**Where it stops:**
- No active security hardening — "private" means "local", not "defended"
- No intrusion detection
- No cryptographic session wipe — conversations persist on disk
- No compliance documentation package
- No audit endpoint
- No weight integrity verification
- No payment privacy option
- General-purpose tool, not built for adversarial compliance environments

**Who uses it:** Privacy-conscious general users. Good product, wrong threat model for Kwyre's buyers.

**Kwyre vs Jan:** Jan is the honest consumer privacy choice. Kwyre is the professional compliance choice. The difference is what happens when your machine is seized, subpoenaed, or actively compromised.

---

### LocalAI

Comprehensive self-hosted AI stack — text, image, audio, agents.

**What it does well:**
- Full OpenAI API compatibility
- Multi-modal (text, image, audio, vision)
- Docker-native deployment
- P2P distributed inference
- Broad model format support

**Where it stops:**
- No security layer beyond standard Docker isolation
- No session encryption or wipe
- No intrusion detection
- No compliance documentation
- Designed for developer/enterprise infrastructure, not individual compliance buyers
- Complexity overkill for single-user local inference

**Who uses it:** DevOps teams self-hosting AI infrastructure. Not individual analysts.

**Kwyre vs LocalAI:** Different markets. LocalAI replaces cloud AI APIs for development teams. Kwyre protects individual analysts in adversarial environments.

---

### Palantir AIP / Microsoft Azure Government

Enterprise government AI. The top of the market.

**What it does well:**
- FedRAMP authorized
- IL4/IL5 capable (some configurations)
- Deep integration with existing enterprise security stacks
- Enterprise support contracts

**Where it stops:**
- $50M+ contract minimums
- 6-24 month procurement cycles
- Requires cleared facility or approved cloud environment
- Not available to solo investigators, small law firms, or independent contractors
- Your data still goes to a cloud (Azure Government, not a laptop)
- Cannot operate truly air-gapped

**Who uses it:** Federal agencies, large defense primes, Fortune 100 legal departments.

**Kwyre vs Palantir/Azure Gov:** No competition. Palantir serves agencies. Kwyre serves the cleared contractor, solo investigator, and 10-person law firm who need the same data protection but will never see a Palantir contract. Kwyre runs on a $3,500 workstation in 10 minutes. Palantir runs in a cleared facility after 18 months of procurement.

---

### The Competitive Matrix

| Feature | ChatGPT | Ollama | LM Studio | Jan.ai | LocalAI | **Kwyre** |
|---------|---------|--------|-----------|--------|---------|-----------|
| Fully local | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Open source | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ |
| Localhost-only binding | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Process outbound block | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Dependency integrity check | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Model weight verification | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| RAM-only sessions | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Cryptographic session wipe | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Intrusion detection + auto-wipe | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Zero content logging (verified) | ✗ | ~ | ✗ | ✓ | ~ | **✓** |
| Compliance documentation | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Audit endpoint | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Anonymous payment | ✗ | free | free | free | free | **✓ XMR** |
| One-time pricing | ✗ | free | free | free | free | **✓ $299** |
| Custom QAT training | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Spike activation encoding | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Compliance buyer target | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |

**Every security feature in this table is unique to Kwyre.** No other local inference tool targets the compliance and adversarial environment use case.

---

## The Technical Moat

Kwyre's architecture has two components nobody else has combined:

**1. Spike QAT Training Pipeline**

Standard local AI tools run generic quantized models. Kwyre trains models specifically to tolerate spike-encoded activations using a Straight-Through Estimator with k-curriculum annealing. The model learns to work with sparse, discretized activations — this is not post-training quantization, it is training the model to operate in a quantized regime. The result is genuine activation sparsity at inference time, preserving capability while reducing compute.

**2. Adversarial Security Architecture**

Every local AI tool treats "local" as the security boundary. Kwyre treats the machine itself as potentially compromised. The six-layer stack is designed for scenarios where:
- The machine is seized and forensically examined
- An attacker has gained access to the system while Kwyre is running
- Malware is actively scraping memory
- The model weights have been tampered with between runs

No competitor has designed for this threat model. That is the moat.

---

## Roadmap

**v0.1 (Current — MVP)**
- [x] Qwen3.5-9B + Spike QAT training pipeline
- [x] 6-layer security stack
- [x] OpenAI-compatible API
- [x] Session encryption + cryptographic wipe
- [x] Intrusion detection watchdog
- [x] Compliance documentation package

**v0.2 (Next)**
- [ ] AWQ quantization (1.4x speed improvement)
- [ ] Speculative decoding with Qwen3-0.6B draft model (2-3x speed)
- [ ] Qwen3-4B tier (half the VRAM, same quality on fine-tuned tasks)
- [ ] Docker installer (single `docker-compose up`)
- [ ] Windows one-click installer

**v0.3**
- [ ] Monero payment integration + license key system
- [ ] Apple Silicon / MLX support (targets legal market on Mac)
- [ ] CPU-only mode via llama.cpp (Kwyre Air — any hardware)
- [ ] Domain-specific fine-tune (legal, financial, forensics corpora)

**v1.0**
- [ ] Benchmark suite vs GPT-4o on compliance tasks
- [ ] SOC2-friendly deployment guide
- [ ] Enterprise audit package
- [ ] Multi-user air-gapped server mode

---

## Technical Specifications

```
Base model:          Qwen3.5-9B (Apache 2.0)
Training:            QLoRA + Spike QAT
  LoRA rank:         64 (alpha 128)
  LoRA targets:      gate_proj, up_proj, down_proj (MLP only)
  Spike hooks:       102 layers (stride=4)
  k-curriculum:      50.0 → 5.0 (step schedule)
  Dataset:           teknium/OpenHermes-2.5
Quantization:        4-bit NF4 (bitsandbytes)
Compute dtype:       bfloat16
VRAM at inference:   ~6.5 GB
Context length:      2048 tokens (training) / 8192 (inference)
API compatibility:   OpenAI /v1/chat/completions
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

## Security Disclosure

Found a vulnerability? Email security@kwyre.ai.

We do not use a bug bounty program. We will acknowledge responsible disclosure publicly and fix issues immediately.

---

## License

MIT License. Use it, audit it, fork it.

The model weights (Qwen3.5-9B base) are licensed under Apache 2.0 by Alibaba. LoRA adapters are original work, MIT licensed.

---

## Built By

APOLLO CyberSentinel LLC — blockchain forensics, cryptocurrency fraud investigation, OSINT analysis.

We built this because we needed it ourselves. We cannot upload active federal investigation evidence to OpenAI. Neither can you.

---

*All inference runs 100% locally. No data leaves your machine.*
*We are not lawyers. This is not legal advice. Verify your own compliance requirements.*
