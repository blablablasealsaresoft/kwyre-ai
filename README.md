# Kwyre AI
### Air-Gapped Inference for Analysts Who Cannot Afford a Breach

> The only local AI that protects your data **even if your machine is compromised.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Model](https://img.shields.io/badge/model-Qwen3.5--4B%20%2B%209B-orange.svg)](https://huggingface.co/Qwen)
[![Quantization](https://img.shields.io/badge/quant-4--bit%20NF4-green.svg)]()
[![Security](https://img.shields.io/badge/security-6--layer%20stack-red.svg)]()
[![Docker](https://img.shields.io/badge/deploy-docker--compose%20up-blue.svg)]()
[![Status](https://img.shields.io/badge/status-v1.6%20production-brightgreen.svg)]()
[![E2E](https://img.shields.io/badge/e2e-29%2F29%20×%204%20backends-brightgreen.svg)]()
[![Pentest](https://img.shields.io/badge/pentest-47%2F47%20resolved-brightgreen.svg)]()
[![Streaming](https://img.shields.io/badge/SSE-streaming-blue.svg)]()
[![GRPO](https://img.shields.io/badge/training-GRPO%20%2B%20distillation-purple.svg)]()
[![Adapters](https://img.shields.io/badge/adapters-6%20domains-blueviolet.svg)]()
[![Analytics](https://img.shields.io/badge/analytics-predictive%20engine-ff6f00.svg)]()
[![AMD ROCm](https://img.shields.io/badge/GPU-AMD%20ROCm-ed1c24.svg)]()
[![NVIDIA CUDA](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-76b900.svg)]()
[![Windows](https://img.shields.io/badge/OS-Windows%20x86__64-blue.svg)]()
[![macOS](https://img.shields.io/badge/OS-macOS%20Apple%20Silicon-999999.svg)]()
[![FreeBSD](https://img.shields.io/badge/OS-FreeBSD-AB2B28.svg)]()
[![AdaptiveK](https://img.shields.io/badge/sparsity-AdaptiveK%20per--layer-00bcd4.svg)]()

---

## What Is Kwyre

Kwyre is a locally-deployed AI inference system built for professionals who work with data that **cannot leave the room** — active federal investigations, attorney-client privileged documents, regulated financial records, classified-adjacent work product, and sensitive compliance analysis.

It runs on **Linux x86_64** (AMD ROCm), **Windows x86_64** (NVIDIA CUDA), **macOS** (Apple Silicon MLX / Metal MPS), and **FreeBSD** (NVIDIA CUDA), shipping a full predictive analytics engine (VaR, CVaR, time series forecasting, pattern analysis), adaptive speculative decoding, six hot-swappable domain adapters, and a cryptographic security stack — all executing entirely on your hardware with zero network egress.

It is not a hobbyist local model runner. It is a **certified, auditable, breach-resistant AI appliance** with cryptographic session wiping, intrusion detection, and a compliance documentation package built in.

**Your queries never leave your machine. Not to a cloud. Not to us. Not to anyone.**

---

## Platform

Kwyre targets **Linux x86_64**, **Windows x86_64**, **macOS** (Apple Silicon and Intel), and **FreeBSD** (amd64). GPU inference requires an AMD discrete GPU with ROCm support (Linux), an NVIDIA GPU with CUDA support (Windows / FreeBSD), or Apple Silicon with Metal MPS / MLX (macOS).

### Hardware Requirements

| Config | GPU | VRAM | RAM | Speed | Download |
|--------|-----|------|-----|-------|----------|
| **Personal (4B GPU)** | AMD RX 7900 XT / RX 7900 XTX | 8 GB+ | 16 GB | 7–14 tok/s | 3.3 GB |
| **Professional (9B GPU)** | AMD MI210 / MI250 / MI300 | 16 GB+ | 32 GB | 3–5 tok/s | 7.6 GB |
| **Kwyre Air (CPU)** | None | — | 8 GB+ | 2–8 tok/s | 2–4 GB |
| **Apple Silicon (MLX)** | None (M1/M2/M3/M4) | — | 8 GB+ unified | 5–15 tok/s | 2–4 GB |

#### Linux Requirements

| Requirement | Value |
|-------------|-------|
| **OS** | Linux x86_64 (Ubuntu 22.04+ recommended) |
| **GPU driver** | AMD ROCm 6.0+ |
| **GPU visibility** | `HIP_VISIBLE_DEVICES` (not `NVIDIA_VISIBLE_DEVICES`) |
| **Docker base** | `rocm/pytorch` |
| **Device passthrough** | `/dev/kfd` + `/dev/dri` |
| **Helm GPU resource** | `amd.com/gpu` |
| **Build artifacts** | `.deb` + AppImage |

#### Windows Requirements

| Requirement | Value |
|-------------|-------|
| **OS** | Windows 10/11 x86_64 |
| **GPU (Personal)** | NVIDIA RTX 3060+, 8 GB+ VRAM, 16 GB RAM |
| **GPU (Professional)** | NVIDIA RTX 4090 / A100 / H100, 16 GB+ VRAM, 32 GB RAM |
| **GPU driver** | NVIDIA CUDA 12.4+ |
| **GPU visibility** | `CUDA_VISIBLE_DEVICES` |
| **Docker base** | `nvidia/cuda` (via Docker Desktop + WSL2) |
| **Build artifacts** | `.exe` installer + portable ZIP |

#### macOS Requirements

| Requirement | Value |
|-------------|-------|
| **OS** | macOS 12+ (Monterey or later) |
| **Hardware** | Apple M1/M2/M3/M4 (recommended) or Intel x86_64 |
| **GPU acceleration** | Metal MPS (Apple Silicon) or NVIDIA eGPU (Intel Mac) |
| **ML framework** | MLX (Apple Silicon native) |
| **Build artifacts** | `.pkg` installer + portable tarball |

#### FreeBSD Requirements

| Requirement | Value |
|-------------|-------|
| **OS** | FreeBSD 13+ (amd64) |
| **GPU driver** | NVIDIA (optional, for GPU inference) |
| **GPU visibility** | `CUDA_VISIBLE_DEVICES` |
| **Firewall** | PF (Packet Filter) |
| **Service management** | rc.d |
| **Build artifacts** | `.txz` package + portable tarball |

---

## Five Products, One Mission

Every Kwyre product runs 100% locally with zero data leaving your machine.

| Product | Model | Hardware | VRAM / RAM | Speed | Price | Identity |
|---------|-------|----------|-----------|-------|-------|----------|
| **Kwyre Personal** | Qwen3.5-4B + 0.8B draft | AMD ROCm GPU (RX 7900 XT+) | 4.1 GB VRAM | 7–14 tok/s | $299 | Speed-optimized with speculative decoding, SpikeServe, RAG, predictive analytics, **1 domain adapter** |
| **Kwyre Professional** | Qwen3.5-9B + 0.8B draft | AMD ROCm GPU (MI210/MI250/MI300) | 7.5 GB VRAM | 3–5 tok/s | $799 | Domain specialist — Claude-distilled reasoning + GRPO emergent problem-solving, full analytics engine, **all 6 domain adapters** |
| **Kwyre Air** | Any GGUF model | Any CPU | 8+ GB RAM | 2–8 tok/s | $299 | Lightweight portable — runs on any hardware, no GPU required |
| **Kwyre (Apple Silicon)** | Any MLX model | M1/M2/M3/M4 Mac | 8+ GB unified | 5–15 tok/s | $299 | Native Metal acceleration on Apple Silicon, zero ROCm dependency |
| **Custom LLM** | Domain-specific (we train) | Any (we configure) | Varies | Varies | Contact | Turnkey appliance or self-hosted — legal, financial, crypto, insurance, defense, healthcare |

**All products share:** 6-layer security stack, OpenAI-compatible API, SSE streaming, cryptographic session wipe, intrusion detection, offline license validation, predictive analytics engine.

**GPU products add:** Adaptive speculative decoding, SpikeServe with AdaptiveK per-layer optimization, per-session KV cache, RAG document ingestion, multi-user RBAC, Flash Attention 2, hot-swap domain adapters.

---

## What's New in v1.6

### Predictive Analytics Engine

A full statistical forecasting and risk assessment engine, available across all backends via the new Analytics API.

- **Time series forecasting** — Holt-Winters triple exponential smoothing with automatic seasonality detection
- **Value at Risk (VaR)** — historical simulation, parametric, and Monte Carlo methods
- **Conditional VaR (CVaR)** — tail-risk quantification beyond the VaR threshold
- **Pattern analysis** — anomaly detection, trend decomposition, distribution fitting
- **Document analytics** — statistical extraction and summarization from ingested documents

```
POST /v1/analytics/predict   Time series forecasting + confidence intervals
POST /v1/analytics/risk      VaR, CVaR, and portfolio risk metrics
```

### Adaptive Speculative Decoding

Speculative decoding no longer uses a static `early_exit` threshold. The new `AdaptiveSpeculator` tracks a rolling window of acceptance rates and dynamically adjusts the draft model's exit threshold between **2 and 8** tokens per speculation step.

- Acceptance rate > 80% → increase speculation depth (more aggressive, higher throughput)
- Acceptance rate < 40% → decrease speculation depth (fewer wasted draft tokens)
- Thread-safe, per-request adaptation with configurable window size (default: 20 samples)
- Stats exposed at `/health` under `speculative.adaptive`

### Adaptive Per-Layer K (AdaptiveKController)

`AdaptiveKController` replaces the global spike threshold with per-layer optimization. During the first 10 forward passes (calibration phase), the controller profiles each layer's activation distribution — variance, kurtosis, mean absolute magnitude — then locks in an optimal k value per layer.

- Low-variance layers → aggressive k (minimum 2.0, maximum sparsity)
- Heavy-tail layers → conservative k (up to 8.0, preserving signal)
- Typical layers → base k (3.0)
- Calibration results reported at `/health` under `spike_analysis.adaptive_k`

### Harder Sparsity Targets

Sparsity parameters tightened across the board to push inference efficiency:

| Parameter | v1.5 | v1.6 | Change |
|-----------|------|------|--------|
| `SPIKE_K` | 5.0 | **3.0** | 40% more aggressive quantization grid |
| `SPIKE_MAX` | 31 | **15** | Tighter clamp, more compression headroom |
| QAT k-curriculum end | 5.0 | **3.0** | Final curriculum stage matches inference k |
| LoRA rank (QAT) | 64 | **128** | Doubled capacity to compensate for harder sparsity |
| LoRA alpha (QAT) | 128 | **256** | Scaled with rank |

### QAT for Both Model Tiers

Quantization-Aware Training now supports both the 4B Personal and 9B Professional models. Previously QAT was 9B-only — the 4B model now benefits from spike-tolerant fine-tuning, enabling higher sparsity inference on consumer AMD GPUs without quality regression.

```bash
python model/train_qat.py --model_id Qwen/Qwen3.5-4B --output_dir ./qat_output_4b
python model/train_qat.py --model_id Qwen/Qwen3.5-9B --output_dir ./qat_output_9b
```

---

## Domain Adapters — Professional Verticals

Kwyre ships with six hot-swappable LoRA domain adapters, each trained on 1,000 Claude-generated expert reasoning traces. Adapters load onto the base model at runtime with no restart required.

### The Six Domains

| Adapter | Size | Expertise |
|---------|------|-----------|
| `legal_compliance` | ~150 MB | NDA analysis, privilege screening, SEC/FINRA compliance, M&A, contract review, Stark Law |
| `insurance_actuarial` | ~150 MB | Reinsurance treaties, loss development triangles, IBNR reserving, Solvency II/RBC, catastrophe XL |
| `healthcare_lifesciences` | ~150 MB | HIPAA/PHI, 21 CFR Parts 11/50/312, FDA 510(k), ICD-10 coding, Stark Law, clinical trials |
| `defense_intelligence` | ~150 MB | CUI handling, NIST 800-171/CMMC, MITRE ATT&CK, OSINT per ICD 203/206, OPSEC, SCRM |
| `financial_trading` | ~150 MB | Algorithmic trading, VaR/CVaR, options pricing, Reg SCI/MiFID II, HFT microstructure, factor models |
| `blockchain_crypto` | ~150 MB | On-chain tracing, MEV/sandwich attacks, RICO/BSA/AML, wallet clustering, rug pull detection, Tornado Cash analysis |

### How It Works

```
Customer installs:
  Base model (Qwen3.5-4B or Qwen3.5-9B)  →  ~2.5 GB or ~7.6 GB
  + Domain adapter (LoRA weights)          →  ~150 MB each

Runtime:
  POST /v1/adapter/load   { "domain": "legal_compliance" }
  POST /v1/adapter/unload
  GET  /v1/adapter/list
  POST /v1/adapter/stack  { "adapters": ["legal_compliance", "blockchain_crypto"], "weights": [0.6, 0.4] }
```

Adapters use PEFT LoRA — swapping takes ~2 seconds and requires no model reload. Multiple adapters can be merged with weighted combination for hybrid use cases (e.g., a crypto lawyer loading both `legal_compliance` + `blockchain_crypto`).

---

## How Kwyre Compares

### Model Quality Benchmarks

| Model | Size | MMLU-Pro | GPQA Diamond | GSM8K | Context | Runs Locally |
|-------|------|----------|-------------|-------|---------|-------------|
| **Kwyre Professional** | 9B (custom-trained) | ~82.5 | ~81.7 | 95.0 | 32K | Yes (air-gapped) |
| GPT-4o | ~200B+ | ~85 | ~80 | ~95 | 128K | No (cloud only) |
| Claude Sonnet | ~70B+ | ~84 | ~78 | ~93 | 200K | No (cloud only) |
| DeepSeek R1 7B | 7B | 82.4 | — | 91.2 | 128K | Yes (no security) |
| Llama 4 Scout | 17B | 79.8 | — | 85.1 | 10M | Yes (no security) |
| Mistral 3 | 24B | 82.8 | — | — | 128K | Yes (no security) |

*Kwyre Professional inherits Qwen3.5-9B's base benchmark scores. Custom domain adapters add vertical-specific capabilities not measured by standard benchmarks.*

### Competitive Feature Matrix

| Capability | Kwyre | ChatGPT | Ollama | LM Studio | Jan.ai | LocalAI |
|-----------|-------|---------|--------|-----------|--------|---------|
| **Fully local (zero network)** | Yes | No | Yes | Yes | Yes | Yes |
| **6-layer active security** | Yes | No | No | No | No | No |
| **Predictive analytics (VaR/CVaR)** | Yes | No | No | No | No | No |
| **Process-level outbound block** | Yes | No | No | No | No | No |
| **Intrusion detection + auto-wipe** | Yes | No | No | No | No | No |
| **Cryptographic session wipe** | Yes | No | No | No | No | No |
| **RAM-only storage (never disk)** | Yes | No | No | No | No | No |
| **Dependency integrity (SHA-256)** | Yes | No | No | No | No | No |
| **Model weight verification** | Yes | No | No | No | No | No |
| **Hot-swap domain adapters** | Yes | No | No | No | No | No |
| **Adapter stacking (weighted merge)** | Yes | No | No | No | No | No |
| **Adaptive speculative decoding** | Yes | N/A | No | No | No | No |
| **Per-layer adaptive sparsity** | Yes | N/A | No | No | No | No |
| **Compliance documentation** | Yes | No | No | No | No | No |
| **SOC2 / HIPAA / FINRA ready** | Yes | Partial | No | No | No | No |
| **Anonymous payment (Monero)** | Yes | No | N/A | N/A | N/A | N/A |
| **Custom-trained for forensics** | Yes | No | No | No | No | No |
| **RAG document ingestion** | Yes | Yes | Plugin | Plugin | Plugin | Plugin |
| **Speculative decoding** | Yes | N/A | Yes | Yes | No | No |

---

## Who It's For

| Buyer | Pain Point | Why Kwyre |
|-------|-----------|-----------|
| **Forensic investigators** | Cannot upload $3B fraud evidence to ChatGPT during an active federal case | Full local inference, zero telemetry, no chain-of-custody risk |
| **Criminal defense attorneys** | Attorney-client privilege prohibits cloud AI on case materials | Air-gapped by architecture, not policy |
| **M&A law firms** | Associates uploading NDA-protected deal docs to ChatGPT is malpractice liability | Verified zero outbound connections, auditable |
| **Reinsurance / insurance underwriters** | Actuarial models, treaty structures, cedent PII cannot touch cloud APIs | Compliance documentation package + built-in VaR/CVaR analytics |
| **Cleared defense contractors** | Sensitive unclassified data — can't use classified AI, can't use ChatGPT | Local, offline, no cleared facility required |
| **Forensic accountants** | SEC whistleblower cases, active DOJ investigations — evidence integrity is paramount | RAM-only storage, cryptographic wipe on session end |
| **Investigative journalists** | Source protection — subscription records are subpoenable | Monero payments, no account required, no email required |

---

## Security Stack — 6 Layers

| Layer | Name | What It Does | Implementation |
|-------|------|-------------|----------------|
| **1** | Network Isolation | Server binds to `127.0.0.1` only — physically unreachable from any network at the OS level | `KWYRE_BIND_HOST=127.0.0.1`; Docker binds `127.0.0.1:8000:8000` on host |
| **2** | Process-Level Network Lockdown | All outbound traffic blocked for the Kwyre process except loopback | `iptables` (Linux) / Windows Firewall (Windows) / PF (macOS / FreeBSD) rules scoped to dedicated `kwyre` system user — even a compromised server process cannot phone home |
| **3** | Dependency Integrity | SHA-256 hash manifest of every installed Python package, verified at startup | Tampered `torch`, `transformers`, or any dependency → immediate abort before a single token is generated |
| **4** | Model Weight Integrity | SHA-256 hashes of all model config files verified at every startup | Tampered or replaced model weights → immediate process abort |
| **5** | Secure RAM Session Storage | Conversations exist only in RAM — never written to disk under any circumstance | 256-bit random session key; `secure_wipe()` overwrites all content with random bytes on session end; 1-hour idle expiry |
| **6** | Intrusion Detection + Auto-Wipe | Background watchdog scans every 5 seconds for unexpected outbound connections and analysis/injection tools | Two consecutive violations → all sessions wiped, KV cache destroyed, server process terminated |

---

## Building from Source

Kwyre builds on Linux x86_64, Windows x86_64, macOS, and FreeBSD.

```bash
# Linux: Prerequisites: Ubuntu 22.04+, Python 3.10+, AMD ROCm 6.x
pip install nuitka ordered-set zstandard

python build.py all              # Full pipeline: compile + package + installer + sign

# Or step by step:
python build.py compile          # Nuitka compile → build/kwyre-dist/kwyre-server
python build.py package          # Stage data files + version.json into build/kwyre-dist/
python build.py installer        # .deb + AppImage
python build.py sign             # Ed25519 sign all build artifacts (MANIFEST.sig.json)
python build.py verify           # Verify signed release (signature + file hashes)
python build.py update-package   # Create .kwyre-update ZIP for air-gap updates
python build.py clean            # Remove build/ directory

python build.py -V               # Print version
```

```powershell
# Windows: Prerequisites: Windows 10/11 x64, Python 3.10+, NVIDIA CUDA 12.x
pip install nuitka ordered-set zstandard
python build.py all              # Full pipeline: compile + package + installer + sign
```

```bash
# macOS: Prerequisites: macOS 12+, Python 3.10+, Xcode CLI tools
pip install nuitka ordered-set zstandard
python build.py all    # .pkg + tarball
```

```bash
# FreeBSD: Prerequisites: FreeBSD 13+, Python 3.10+
pip install nuitka ordered-set zstandard
python build.py all    # .txz + tarball
```

The installer step produces platform-specific artifacts:

| Format | Target | Notes |
|--------|--------|-------|
| `.deb` | Debian / Ubuntu | `dpkg -i kwyre-server_*.deb`, registers systemd unit |
| AppImage | Any Linux x86_64 | Single-file portable, no install required |
| `.exe` installer | Windows x86_64 | Standard Windows installer, registers Windows Service |
| Portable ZIP | Windows x86_64 | No install required, extract and run |
| `.pkg` | macOS | Standard macOS installer package |
| Portable tarball | macOS | No install required, extract and run |
| `.txz` | FreeBSD amd64 | `pkg add kwyre-server_*.txz`, registers rc.d service |
| Portable tarball | FreeBSD amd64 | No install required, extract and run |

---

## Technical Specifications

```
Platform:                   Linux x86_64 + AMD ROCm 6.x | Windows x86_64 + NVIDIA CUDA 12.x | macOS Apple Silicon (MLX / Metal MPS) | FreeBSD amd64 + NVIDIA CUDA
Main model (Personal):     Qwen/Qwen3.5-4B (pre-quantized NF4, 2.5 GB)
Main model (Professional): Qwen/Qwen3.5-9B (pre-quantized NF4, 7.6 GB)
Draft model:               Qwen/Qwen3.5-0.8B (pre-quantized NF4, 0.8 GB) — shared by both tiers
Quantization:              4-bit NF4 (bitsandbytes) or AWQ (1.4x faster)
Compute dtype:             bfloat16
VRAM at inference:         Personal ~4.1 GB | Professional ~7.5 GB (models + KV cache budget)
KV cache:                  Per-session, LRU eviction, 2 GB VRAM cap default
Streaming:                 SSE (text/event-stream), token-by-token
Concurrency:               Inference queue (serialized GPU) + threaded HTTP
Context length:            32768 tokens
API compatibility:         OpenAI /v1/chat/completions (blocking + streaming)
Docker image:              ~12 GB (includes ROCm runtime)
Model download:            Personal 3.3 GB | Professional 7.6 GB (pre-quantized, from kwyre.com)

SpikeServe (v1.6):
  MLP hooks:           84 layers on draft model, main at full fidelity
  SPIKE_K:             3.0 (top-k sparsity ratio)
  SPIKE_MAX:           15 (maximum spike activations per layer)

Speculative Decoding (v1.6):
  Strategy:            Adaptive speculative decoding (AdaptiveSpeculator)
  Exit threshold:      Dynamic range 2–8 (adjusts per-token based on draft confidence)
  Throughput:          2–3x over sequential decoding

Adaptive k Calibration (v1.6):
  Controller:          AdaptiveKController
  Calibration:         10-pass profiling on first inference run
  Per-layer k:         Optimized individually per MLP layer after calibration
  Fallback:            SPIKE_K=3.0 until calibration completes

Analytics Engine (v1.6):
  Module:              server/analytics.py
  TimeSeriesPredictor: Holt-Winters, double exponential, linear regression, moving average
  PatternAnalyzer:     Distribution fitting, anomaly detection, clustering, periodicity
  RiskEngine:          VaR/CVaR, Monte Carlo simulation, portfolio risk, tail risk
  DocumentAnalytics:   Entity extraction, topic modeling, similarity scoring, summarization

Domain Adapters (v1.5):
  Format:              PEFT LoRA checkpoint (safetensors)
  Size per adapter:    ~150 MB
  Total (6 adapters):  ~900 MB
  Domains:             legal_compliance, insurance_actuarial, healthcare_lifesciences,
                       defense_intelligence, financial_trading, blockchain_crypto
  Base model:          Qwen/Qwen3.5-4B (4B adapters) | Qwen/Qwen3.5-9B (9B adapters)
  LoRA rank:           32 (distillation)
  LoRA targets:        q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
  Training traces:     1,000 per domain (6,000 total)
  Trace generation:    Anthropic Batch API — 2-phase (expansion + generation), ~$32 total
  Distillation:        Unsloth QLoRA on H100 80GB, 3 epochs, 375 steps/domain
  Loss per domain:     1.2 → 0.53 (consistent convergence across all 6 domains)
  Training time:       ~2h per domain × 6 = ~12h total on H100 80GB

Custom Training Pipeline (Professional 9B):
  Pipeline:            Claude traces → Unsloth QLoRA distillation → GRPO RL → GGUF export
  Trace generation:    Anthropic Batch API (resumable, 50% cheaper than real-time)
  Distillation:        Unsloth QLoRA on H100 80GB, LoRA rank 32
  GRPO RL:             HuggingFace + TRL, 500 steps, LoRA rank 16
  Domains:             blockchain forensics, legal/financial, physics/math, conversational
  Personality:         Kwyre persona baked into weights (not just system prompt)
  Reasoning:           Chain-of-thought via <think>...</think> tags + emergent problem-solving
  Export:              Q5_K_M (6.1 GB) + Q4_K_M (5.3 GB) GGUFs
  Hardware:            DigitalOcean H100 80GB GPU Droplet

QAT Training (v1.6 — Spike encoding):
  LoRA rank:           128 (alpha 256)
  LoRA targets:        gate_proj, up_proj, down_proj (MLP only)
  Spike hooks:         408 layers (main model training)
  k-curriculum:        50.0 → 3.0 (step schedule)
  Models:              Qwen3.5-4B + Qwen3.5-9B (both supported)
  Dataset:             teknium/OpenHermes-2.5
```

---

## Pricing

| License | Price | Machines | Includes |
|---------|-------|----------|----------|
| **Personal** | $299 one-time | 1 | Base model + 1 domain adapter of choice + compliance doc |
| **Professional** | $799 one-time | 3 | Base model + all 6 domain adapters + priority support + 9B model |
| **Air-Gapped Kit** | $1,499 one-time | 5 | Everything + offline adapter installer + full audit package |

**Payment:** Credit card or Monero (XMR). No email required for Monero purchases. One-time — no subscription.

**Adapter delivery:** ~150 MB per adapter, downloaded from kwyre.com CDN alongside base model. Versioned updates delivered silently via `GET /v1/adapter/check-update`.

---

## Project Structure

```
kwyre/
├── server/
│   ├── serve_local_4bit.py    # GPU inference (streaming, KV cache, RAG, speculative, adapters)
│   ├── serve_vllm.py          # vLLM backend (continuous batching, PagedAttention)
│   ├── serve_cpu.py           # CPU inference via llama.cpp (Kwyre Air)
│   ├── serve_mlx.py           # Apple Silicon inference via MLX
│   ├── analytics.py           # Predictive analytics engine (time-series, risk, patterns, documents)
│   ├── adapter_trainer.py     # Customer fine-tuning background job system
│   ├── security_core.py       # Shared security infrastructure (all 6 layers)
│   ├── platform_gpu.py        # Cross-platform GPU detection (ROCm / CUDA)
│   ├── platform_paths.py      # Cross-platform path resolution (Linux / Windows)
│   ├── rag.py                 # RAG document ingestion (FAISS + embeddings)
│   ├── users.py               # Multi-user management (Fernet-encrypted)
│   └── audit.py               # Per-user audit logging + SIEM export
├── model/
│   ├── spike_serve.py         # SpikeServe activation encoding hooks
│   ├── quantize_nf4.py        # NF4 pre-quantization (Qwen/Qwen3.5-4B)
│   ├── quantize_awq.py        # AWQ pre-quantization
│   ├── convert_gguf.py        # HuggingFace → GGUF converter
│   ├── convert_mlx.py         # HuggingFace → MLX converter
│   ├── train_qat.py           # Spike QAT training pipeline
│   └── merge_and_export.py    # Merge LoRA + export
├── security/
│   ├── verify_deps.py         # Layer 3 — dependency integrity
│   ├── license.py             # Ed25519 license + hardware fingerprint binding
│   ├── codesign.py            # Ed25519 release signing and verification
│   ├── updater.py             # Air-gap safe update mechanism
│   ├── setup_isolation.ps1    # Windows Firewall + process isolation setup
│   ├── setup_isolation.sh     # Linux iptables + process isolation setup
│   └── setup_isolation_freebsd.sh  # FreeBSD PF + process isolation setup
├── training/
│   ├── run_full_pipeline.sh   # Automated: traces → distillation → GRPO → export
│   ├── run_full_pipeline.ps1  # Windows: same pipeline via PowerShell
│   ├── setup_gpu.sh           # AMD ROCm GPU environment setup
│   ├── setup_gpu.ps1          # NVIDIA CUDA GPU environment setup (Windows)
│   └── scripts/
│       ├── generate_traces_batch.py    # Batch API trace generation (1,000/domain, resumable)
│       ├── generate_traces_parallel.py # Real-time parallel trace generation (fallback)
│       ├── train_distillation.py       # Unsloth QLoRA domain adapter distillation
│       ├── train_grpo_domain.py        # Domain-specific GRPO with custom reward functions
│       ├── train_grpo.py               # Base GRPO training
│       ├── run_domain_training.sh      # Single-domain pipeline runner
│       ├── run_domain_training.ps1     # Windows: single-domain pipeline runner
│       ├── run_all_domains.sh          # All 6 domains sequentially
│       └── run_all_domains.ps1         # Windows: all 6 domains sequentially
├── benchmarks/
│   ├── benchmark.py           # Domain benchmark suite (--with-adapter comparison mode)
│   └── datasets/              # financial_analysis.json, compliance_tasks.json, etc.
├── deploy/
│   └── helm/kwyre/            # Kubernetes Helm chart (GPU, probes, PVC)
├── chat/
│   ├── index.html             # Cinematic intro sequence
│   ├── main.html              # Chat UI (adapter dropdown, domain auto-detection)
│   ├── landing.html           # Alternate landing page
│   ├── technology.html        # Data privacy — cloud AI incidents
│   ├── products.html          # Product lineup + competitive comparison
│   ├── custom.html            # Custom LLM service + request form
│   ├── security.html          # Penetration testing + compliance
│   ├── platform.html          # Installation + deployment guides
│   └── pay.html               # Payment + license download gate
├── scripts/
│   └── package_adapter.ps1    # Windows adapter packaging script
├── installer/
│   ├── install_linux.sh       # Linux installer (systemd + iptables)
│   ├── install_macos.sh       # macOS installer (launchd + PF)
│   └── install_freebsd.sh     # FreeBSD installer (rc.d + PF)
├── finetune/                  # Domain-specific fine-tuning pipeline
├── docs/                      # Compliance documentation package
├── tests/                     # 110 security tests + integration suite
├── build.py                   # Nuitka build + installer pipeline
├── .env.example               # Full config reference (30+ variables)
├── requirements-windows.txt   # Windows-specific Python dependencies (CUDA)
├── requirements-macos.txt     # macOS-specific Python dependencies (MLX / Metal)
├── requirements-freebsd.txt   # FreeBSD-specific Python dependencies
└── dist/                      # Pre-quantized model weights
    ├── kwyre-4b-nf4/          # Main model (2.5 GB)
    └── kwyre-draft-nf4/       # Draft model (0.8 GB)

~/.kwyre/                      # Runtime data (never in project root)
├── adapters/
│   ├── legal-compliance-4b/   # PEFT LoRA checkpoint (~150 MB)
│   ├── insurance-actuarial-4b/
│   ├── healthcare-lifesciences-4b/
│   ├── defense-intelligence-4b/
│   ├── financial-trading-4b/
│   └── blockchain-crypto-4b/
├── training-data/kwyre-traces/ # 6,000 Claude reasoning traces
└── logs/                       # Training logs
```

---

## Roadmap

**v0.1–v1.5 (Complete)**
- [x] 6-layer security stack, speculative decoding, SpikeServe, SSE streaming, KV cache, RAG, OpenAI-compatible API
- [x] Multi-backend (GPU / vLLM / CPU-GGUF / Apple Silicon-MLX), multi-user RBAC, Nuitka binary builds, Ed25519 code signing
- [x] 47/47 pentest findings resolved, 110 security tests passing, SOC2/HIPAA/FINRA compliance documentation
- [x] 6 hot-swap LoRA domain adapters (legal, insurance, healthcare, defense, trading, blockchain) + adapter stacking, CDN versioning, customer fine-tuning endpoint

**v1.6 (Current)**
- [x] Predictive analytics engine — `TimeSeriesPredictor`, `PatternAnalyzer`, `RiskEngine`, `DocumentAnalytics` (`server/analytics.py`)
- [x] Adaptive speculative decoding — `AdaptiveSpeculator` with dynamic exit threshold (range 2–8)
- [x] Adaptive per-layer k — `AdaptiveKController` calibrates optimal k per MLP layer during first 10 inference passes
- [x] Harder sparsity defaults — `SPIKE_K=3.0` (was 5.0), `SPIKE_MAX=15` (was 31)
- [x] QAT LoRA rank 128 (alpha 256), k-curriculum 50→3, supports both Qwen3.5-4B and Qwen3.5-9B
- [x] Linux x86_64 + AMD ROCm migration — single-platform build (.deb + AppImage), Docker image ~12 GB with ROCm runtime
- [x] Windows x86_64 + NVIDIA CUDA support — .exe installer + portable ZIP, Docker Desktop + WSL2, PowerShell training scripts
- [x] macOS Apple Silicon + MLX support — `.pkg` installer + portable tarball, Metal MPS acceleration, native MLX inference
- [x] FreeBSD amd64 + NVIDIA CUDA support — `.txz` package + portable tarball, PF firewall isolation, rc.d service management

**v1.7 (Planned)**
- [ ] Credit card payment integration
- [ ] Adapter marketplace — community-trained adapters with verified metadata + revenue sharing
- [ ] Custom LLM service launch — turnkey domain-specific model delivery

---

## Verifying Zero Telemetry

**Linux:**
```bash
# Watch for any outbound connections from the inference process
watch -n 1 "ss -tp | grep python"

# Confirm: only 127.0.0.1 connections appear. Any external IP = compromised environment.
```

**Windows (PowerShell):**
```powershell
# Watch for any outbound connections from the inference process
Get-NetTCPConnection | Where-Object { $_.OwningProcess -eq (Get-Process kwyre-server).Id }

# Confirm: only 127.0.0.1 connections appear. Any external IP = compromised environment.
```

**macOS:**
```bash
# Watch for any outbound connections from the inference process
lsof -i -n -P | grep python

# Confirm: only 127.0.0.1 connections appear. Any external IP = compromised environment.
```

**FreeBSD:**
```bash
# Watch for any outbound connections from the inference process
sockstat -4 | grep python

# Confirm: only 127.0.0.1 connections appear. Any external IP = compromised environment.
```

**Wireshark:**
```
Interface: loopback (lo) | Filter: tcp.port == 8000
Confirm: all traffic is 127.0.0.1 → 127.0.0.1
```

---

## Compliance Documentation

- **`docs/COMPLIANCE_LETTER.md`** — formal attestation (GDPR, HIPAA, SOC 2, FINRA, ITAR, FRE, ABA)
- **`docs/VERIFICATION_GUIDE.md`** — independent security verification for each layer
- **`docs/DEPLOYMENT_CHECKLIST.md`** — hardened deployment procedure
- **`docs/INCIDENT_RESPONSE.md`** — security event classification and response
- **`docs/SOC2_DEPLOYMENT_GUIDE.md`** — SOC2 Type II deployment guide
- **`docs/ENTERPRISE_AUDIT.md`** — enterprise audit package

---

## Security Disclosure

Found a vulnerability? Email security@kwyre.ai.

We do not use a bug bounty program. We will acknowledge responsible disclosure publicly and fix issues immediately.

---

## License

MIT License. Use it, audit it, fork it.

The model weights (Qwen3.5-4B, Qwen3.5-9B, Qwen3.5-0.8B base) are licensed under Apache 2.0 by Alibaba. LoRA domain adapters and pre-quantized distributions are original work, MIT licensed.

---

## Built By

Mint Rail LLC — blockchain forensics, cryptocurrency fraud investigation, OSINT analysis.

We built this because we needed it ourselves. We cannot upload active federal investigation evidence to OpenAI. Neither can you.

---

## Website

**[kwyre.com](https://kwyre.com)** — Live product site deployed on Cloudflare Pages.

| Page | URL | Description |
|------|-----|-------------|
| Landing | `/` | Animated intro sequence with neural canvas |
| Main | `/main.html` | Product overview + security stack + chat UI with adapter selector |
| Data Privacy | `/technology.html` | Cloud AI incident tracker, company orbs |
| Products | `/products.html` | All 5 products with specs + competitive comparison |
| Custom | `/custom.html` | Custom LLM service, industry orbs, request form |
| Security | `/security.html` | Penetration testing, privacy guarantees, compliance |
| Platform | `/platform.html` | Installation guides, deployment options, build pipeline |
| Purchase | `/pay.html` | Monero payment, license verification, downloads |

---

*All inference runs 100% locally. No data leaves your machine.*
*We are not lawyers. This is not legal advice. Verify your own compliance requirements.*
