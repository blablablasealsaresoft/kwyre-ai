# Kwyre AI
### Local-First AI for Analysts Who Cannot Afford a Breach

> The only local AI that keeps your data on your hardware — with optional air-gapping for zero-compromise environments.

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
[![Adapters](https://img.shields.io/badge/adapters-8%20domains-blueviolet.svg)]()
[![Analytics](https://img.shields.io/badge/analytics-predictive%20engine-ff6f00.svg)]()
[![AMD ROCm](https://img.shields.io/badge/GPU-AMD%20ROCm-ed1c24.svg)]()
[![NVIDIA CUDA](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-76b900.svg)]()
[![Windows](https://img.shields.io/badge/OS-Windows%20x86__64-blue.svg)]()
[![macOS](https://img.shields.io/badge/OS-macOS%20Apple%20Silicon-999999.svg)]()
[![FreeBSD](https://img.shields.io/badge/OS-FreeBSD-AB2B28.svg)]()
[![AdaptiveK](https://img.shields.io/badge/sparsity-AdaptiveK%20per--layer-00bcd4.svg)]()
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF.svg)]()

---

## What Is Kwyre

Kwyre is a local-first AI inference system built for professionals who work with sensitive data — active federal investigations, attorney-client privileged documents, regulated financial records, classified-adjacent work product, and compliance analysis.

It runs on **Linux x86_64** (AMD ROCm), **Windows x86_64** (NVIDIA CUDA), **macOS** (Apple Silicon MLX / Metal MPS), and **FreeBSD** (NVIDIA CUDA), shipping a full predictive analytics engine (VaR, CVaR, time series forecasting, pattern analysis), adaptive speculative decoding, and eight hot-swappable domain adapters — all executing on your hardware.

For teams that need cloud-scale models, **Kwyre Cloud** provides access to 32B and 72B parameter models running on our GPU clusters (Lambda, DigitalOcean H100s) with dramatically improved reasoning quality and longer context windows.

For the highest security environments, the optional **Air-Gapped Kit** upgrade adds process-level network lockdown, intrusion detection with auto-wipe, dependency and model integrity verification, and a full compliance documentation package — turning any local Kwyre installation into a certified, auditable, breach-resistant appliance.

**Local products:** Your queries never leave your machine.
**Cloud products:** Your queries stay on our infrastructure — no third-party AI providers.

---

## Platform

Kwyre targets **Linux x86_64**, **Windows x86_64**, **macOS** (Apple Silicon and Intel), and **FreeBSD** (amd64). GPU inference requires an AMD discrete GPU with ROCm support (Linux), an NVIDIA GPU with CUDA support (Windows / FreeBSD), or Apple Silicon with Metal MPS / MLX (macOS).

### Hardware Requirements

| Config | GPU | VRAM | RAM | Speed | Download |
|--------|-----|------|-----|-------|----------|
| **Personal (4B GPU)** | AMD RX 7900 XT+ / NVIDIA RTX 3060+ / Apple M1+ | 8 GB+ | 16 GB | 7–14 tok/s | 3.3 GB |
| **Professional (9B GPU)** | AMD MI210+ / NVIDIA RTX 4090 / A100 / H100 / Apple M2 Pro+ | 16 GB+ | 32 GB | 3–8 tok/s | 7.6 GB |
| **Kwyre Air (CPU)** | None | — | 8 GB+ | 2–8 tok/s | 2–4 GB |
| **Apple Silicon (MLX)** | Apple M1/M2/M3/M4 (Metal MPS + MLX) | — | 8 GB+ unified | 5–15 tok/s | 2–4 GB |

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

## Products

### Local Inference

Every local product runs 100% on your hardware. No data leaves your machine.

| Product | Model | Hardware | VRAM / RAM | Speed | Price |
|---------|-------|----------|-----------|-------|-------|
| **Kwyre Personal** | Qwen3.5-4B + 0.8B draft | Any supported GPU (AMD ROCm, NVIDIA CUDA, Apple MLX) | 4–8 GB VRAM | 7–14 tok/s | $299 |
| **Kwyre Professional** | Qwen3.5-9B + 0.8B draft | Any supported GPU (AMD ROCm, NVIDIA CUDA, Apple MLX) | 8–16 GB VRAM | 3–8 tok/s | $799 |
| **Kwyre Air** | Any GGUF model | Any CPU | 8+ GB RAM | 2–8 tok/s | $299 |
| **Kwyre (Apple Silicon)** | Any MLX model | M1/M2/M3/M4 Mac | 8+ GB unified | 5–15 tok/s | $299 |

**Personal** — Speed-optimized with speculative decoding, SpikeServe, RAG, predictive analytics, and **1 domain adapter** of choice.

**Professional** — Domain specialist with Claude-distilled reasoning, GRPO emergent problem-solving, full analytics engine, and **all 8 domain adapters**.

**Air** — Lightweight portable CPU inference. Runs on any hardware, no GPU required.

**Apple Silicon** — Native Metal MPS / MLX acceleration on M-series Macs.

### Cloud Inference

Kwyre Cloud runs on our GPU clusters (Lambda, DigitalOcean H100s) with significantly larger models than local deployment supports. Your data stays on our infrastructure — no third-party cloud AI providers involved.

| Product | Model | Infrastructure | Context | Speed | Price |
|---------|-------|---------------|---------|-------|-------|
| **Kwyre Cloud** | Qwen3.5-32B / 72B | H100 80GB GPU cluster | 128K tokens | 20–40 tok/s | Subscription |
| **Kwyre Cloud Pro** | Qwen3.5-72B + domain adapters | Multi-H100 cluster | 128K tokens | 15–30 tok/s | Subscription |
| **Custom Cloud LLM** | Domain-specific (we train + host) | Dedicated GPU allocation | Configurable | Varies | Contact |

**Cloud** — Access to 32B and 72B parameter models with dramatically improved reasoning, longer context, and higher throughput. Same OpenAI-compatible API as local products.

**Cloud Pro** — Full 72B model with all 8 domain adapters, priority GPU allocation, and dedicated inference capacity.

**Custom Cloud LLM** — We train a domain-specific model on your data and host it on dedicated GPU infrastructure. Turnkey solution for legal, financial, crypto, insurance, defense, and healthcare.

### Air-Gapped Upgrade

Air-gapping is an **optional security upgrade** available for any local product. It is not included by default.

| Upgrade | Price | What It Adds |
|---------|-------|-------------|
| **Air-Gapped Kit** | $1,499 one-time | Process-level network lockdown (iptables / Windows Firewall / PF), intrusion detection + auto-wipe, dependency integrity verification, model weight integrity, full compliance documentation package |

Without the Air-Gapped Kit, local products run on `127.0.0.1` with RAM-only sessions and cryptographic session wipe, but do **not** include process-level outbound blocking, intrusion detection, or automated wipe-on-compromise.

### Shared Features

**All local products:** OpenAI-compatible API, SSE streaming, RAM-only session storage, cryptographic session wipe, offline license validation, predictive analytics engine.

**GPU local products add:** Adaptive speculative decoding, SpikeServe with AdaptiveK per-layer optimization, per-session KV cache, RAG document ingestion, multi-user RBAC, Flash Attention 2, hot-swap domain adapters.

**Cloud products:** OpenAI-compatible API, SSE streaming, predictive analytics engine, domain adapters, multi-user access, SLA-backed uptime.

**Air-Gapped Kit adds:** Process-level network lockdown, dependency integrity (SHA-256 manifest), model weight verification, intrusion detection + auto-wipe, full compliance documentation (SOC2, HIPAA, FINRA, ITAR).

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

Kwyre ships with eight hot-swappable LoRA domain adapters, each trained on 1,000 Claude-generated expert reasoning traces. Adapters load onto the base model at runtime with no restart required.

### The Eight Domains

| Adapter | Size | Expertise |
|---------|------|-----------|
| `legal_compliance` | ~150 MB | NDA analysis, privilege screening, SEC/FINRA compliance, M&A, contract review, Stark Law |
| `insurance_actuarial` | ~150 MB | Reinsurance treaties, loss development triangles, IBNR reserving, Solvency II/RBC, catastrophe XL |
| `healthcare_lifesciences` | ~150 MB | HIPAA/PHI, 21 CFR Parts 11/50/312, FDA 510(k), ICD-10 coding, Stark Law, clinical trials |
| `defense_intelligence` | ~150 MB | CUI handling, NIST 800-171/CMMC, MITRE ATT&CK, OSINT per ICD 203/206, OPSEC, SCRM |
| `financial_trading` | ~150 MB | Algorithmic trading, VaR/CVaR, options pricing, Reg SCI/MiFID II, HFT microstructure, factor models |
| `blockchain_crypto` | ~150 MB | On-chain tracing, MEV/sandwich attacks, RICO/BSA/AML, wallet clustering, rug pull detection, Tornado Cash analysis |
| `sports_analytics` | ~150 MB | NFL play calling, blitz/coverage prediction, scouting reports, player movement profiling, playbook reverse engineering, situational game theory |
| `relationship_matching` | ~150 MB | Big Five personality analysis, attachment style detection, love language identification, compatibility scoring, conversation generation, relationship coaching |

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
| **Kwyre Professional** | 9B (custom-trained) | ~82.5 | ~81.7 | 95.0 | 32K | Yes (local) |
| GPT-4o | ~200B+ | ~85 | ~80 | ~95 | 128K | No (cloud only) |
| Claude Sonnet | ~70B+ | ~84 | ~78 | ~93 | 200K | No (cloud only) |
| DeepSeek R1 7B | 7B | 82.4 | — | 91.2 | 128K | Yes (no security) |
| Llama 4 Scout | 17B | 79.8 | — | 85.1 | 10M | Yes (no security) |
| Mistral 3 | 24B | 82.8 | — | — | 128K | Yes (no security) |

*Kwyre Professional inherits Qwen3.5-9B's base benchmark scores. Custom domain adapters add vertical-specific capabilities not measured by standard benchmarks.*

### Competitive Feature Matrix

| Capability | Kwyre (Base) | Kwyre (Air-Gapped) | Kwyre Cloud | ChatGPT | Ollama |
|-----------|-------------|-------------------|-------------|---------|--------|
| **Fully local (zero network)** | Yes | Yes | No (our infra) | No | Yes |
| **RAM-only storage (never disk)** | Yes | Yes | N/A | No | No |
| **Cryptographic session wipe** | Yes | Yes | N/A | No | No |
| **Process-level outbound block** | — | Yes | N/A | No | No |
| **Intrusion detection + auto-wipe** | — | Yes | N/A | No | No |
| **Dependency integrity (SHA-256)** | — | Yes | N/A | No | No |
| **Model weight verification** | — | Yes | N/A | No | No |
| **Compliance documentation** | — | Yes | Yes | No | No |
| **SOC2 / HIPAA / FINRA ready** | — | Yes | Partial | Partial | No |
| **Predictive analytics (VaR/CVaR)** | Yes | Yes | Yes | No | No |
| **Hot-swap domain adapters** | Yes | Yes | Yes | No | No |
| **Adapter stacking (weighted merge)** | Yes | Yes | Yes | No | No |
| **Adaptive speculative decoding** | Yes | Yes | Yes | N/A | No |
| **Per-layer adaptive sparsity** | Yes | Yes | Yes | N/A | No |
| **32B / 72B model access** | — | — | Yes | Yes | Yes |
| **RAG document ingestion** | Yes | Yes | Yes | Yes | Plugin |
| **Speculative decoding** | Yes | Yes | Yes | N/A | Yes |
| **Custom-trained models** | — | — | Yes | No | No |

---

## Who It's For

### Local Products

| Buyer | Pain Point | Why Kwyre |
|-------|-----------|-----------|
| **Forensic investigators** | Cannot upload $3B fraud evidence to ChatGPT during an active federal case | Local inference, zero telemetry, no chain-of-custody risk |
| **Criminal defense attorneys** | Attorney-client privilege prohibits cloud AI on case materials | Local by default, air-gapped with upgrade |
| **M&A law firms** | Associates uploading NDA-protected deal docs to ChatGPT is malpractice liability | Local inference with optional air-gap for auditable zero-outbound |
| **Cleared defense contractors** | Sensitive unclassified data — can't use classified AI, can't use ChatGPT | Local, offline, no cleared facility required |
| **Investigative journalists** | Source protection — subscription records are subpoenable | Local inference, no account required, no telemetry |

### Cloud Products

| Buyer | Pain Point | Why Kwyre Cloud |
|-------|-----------|----------------|
| **Reinsurance / insurance underwriters** | Need 72B-class reasoning for actuarial models but can't use OpenAI | Kwyre Cloud with VaR/CVaR analytics, no third-party AI |
| **Forensic accountants** | SEC whistleblower cases need better-than-9B reasoning quality | 32B/72B models on dedicated GPU clusters |
| **Law firms (non-classified)** | Want AI-assisted contract review with better quality than 4B/9B local models | Cloud Pro with legal domain adapter on 72B |
| **Financial trading desks** | Need fast, high-quality inference for real-time analysis | Cloud with priority GPU allocation, low-latency API |

### Air-Gapped Kit (Security Upgrade)

| Buyer | Pain Point | Why Air-Gap |
|-------|-----------|------------|
| **Active federal investigations** | Evidence integrity — any outbound connection contaminates chain of custody | Process-level network lockdown, intrusion detection, auto-wipe |
| **HIPAA-regulated healthcare** | PHI exposure is a federal violation | Dependency integrity, model verification, SOC2/HIPAA compliance docs |
| **Defense / ITAR-adjacent work** | CUI handling requires documented zero-egress | Full 6-layer security stack with audit package |

---

## Security Stack

All local products ship with baseline security (Layers 1 and 5). The **Air-Gapped Kit** upgrade activates the full 6-layer stack (Layers 2–4, 6).

| Layer | Name | Included In | What It Does |
|-------|------|------------|-------------|
| **1** | Network Isolation | All local products | Server binds to `127.0.0.1` only — physically unreachable from any network at the OS level |
| **2** | Process-Level Network Lockdown | Air-Gapped Kit | All outbound traffic blocked for the Kwyre process except loopback — `iptables` (Linux) / Windows Firewall / PF (macOS / FreeBSD) |
| **3** | Dependency Integrity | Air-Gapped Kit | SHA-256 hash manifest of every installed Python package, verified at startup — tampered dependency → immediate abort |
| **4** | Model Weight Integrity | Air-Gapped Kit | SHA-256 hashes of all model config files verified at every startup — tampered weights → immediate abort |
| **5** | Secure RAM Session Storage | All local products | Conversations exist only in RAM — 256-bit random session key, `secure_wipe()` on session end, 1-hour idle expiry |
| **6** | Intrusion Detection + Auto-Wipe | Air-Gapped Kit | Background watchdog scans every 5s for unexpected outbound connections — two violations → all sessions wiped, process terminated |

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
  Total (8 adapters):  ~1200 MB
  Domains:             legal_compliance, insurance_actuarial, healthcare_lifesciences,
                       defense_intelligence, financial_trading, blockchain_crypto,
                       sports_analytics, relationship_matching
  Base model:          Qwen/Qwen3.5-4B (4B adapters) | Qwen/Qwen3.5-9B (9B adapters)
  LoRA rank:           32 (distillation)
  LoRA targets:        q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
  Training traces:     1,000 per domain (8,000 total)
  Trace generation:    Anthropic Batch API — 2-phase (expansion + generation), ~$32 total
  Distillation:        Unsloth QLoRA on H100 80GB, 3 epochs, 375 steps/domain
  Loss per domain:     1.2 → 0.53 (consistent convergence across all 8 domains)
  Training time:       ~2h per domain × 6 = ~12h total on H100 80GB

Custom Training Pipeline (Professional 9B):
  Pipeline:            Claude traces → Unsloth QLoRA distillation → GRPO RL → GGUF export
  Trace generation:    Anthropic Batch API (resumable, 50% cheaper than real-time)
  Distillation:        Unsloth QLoRA on H100 80GB, LoRA rank 32
  GRPO RL:             HuggingFace + TRL, 500 steps, LoRA rank 16
  Domains:             legal_compliance, insurance_actuarial, healthcare_lifesciences,
                       defense_intelligence, financial_trading, blockchain_crypto,
                       sports_analytics, relationship_matching
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

### Local Licenses (One-Time)

| License | Price | Machines | Includes |
|---------|-------|----------|----------|
| **Personal** | $299 | 1 | Qwen3.5-4B model + 1 domain adapter of choice |
| **Professional** | $799 | 3 | Qwen3.5-9B model + all 8 domain adapters + priority support |
| **Air** | $299 | 1 | GGUF CPU inference engine |
| **Apple Silicon** | $299 | 1 | MLX inference engine |
| **Air-Gapped Kit** | $1,499 | 5 | Security upgrade for any local product — network lockdown, intrusion detection, compliance docs, offline adapter installer |

### Cloud Subscriptions

| Plan | Price | Includes |
|------|-------|----------|
| **Cloud** | Contact | 32B/72B model access, API key, usage-based billing |
| **Cloud Pro** | Contact | 72B + all domain adapters, priority GPU, dedicated capacity |
| **Custom Cloud LLM** | Contact | Domain-specific model training + dedicated hosted inference |

**Local payment:** Credit card. One-time — no subscription.

**Cloud payment:** Credit card. Monthly or annual billing.

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
│   ├── platform_gpu.py        # Cross-platform GPU detection (ROCm / CUDA / MLX / MPS)
│   ├── platform_paths.py      # Cross-platform path and service resolution
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
│       ├── run_all_domains.sh          # All 8 domains sequentially
│       └── run_all_domains.ps1         # Windows: all 8 domains sequentially
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
│   ├── package_adapter.sh     # Adapter packaging script (Linux / macOS / FreeBSD)
│   └── package_adapter.ps1    # Adapter packaging script (Windows)
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
│   ├── blockchain-crypto-4b/
│   ├── sports-analytics-4b/
│   └── relationship-matching-4b/
├── training-data/kwyre-traces/ # 8,000 Claude reasoning traces
└── logs/                       # Training logs
```

---

## Roadmap

**v0.1–v1.5 (Complete)**
- [x] 6-layer security stack, speculative decoding, SpikeServe, SSE streaming, KV cache, RAG, OpenAI-compatible API
- [x] Multi-backend (GPU / vLLM / CPU-GGUF / Apple Silicon-MLX), multi-user RBAC, Nuitka binary builds, Ed25519 code signing
- [x] 47/47 pentest findings resolved, 110 security tests passing, SOC2/HIPAA/FINRA compliance documentation
- [x] 8 hot-swap LoRA domain adapters (legal, insurance, healthcare, defense, trading, blockchain, sports_analytics, relationship_matching) + adapter stacking, CDN versioning, customer fine-tuning endpoint

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
- [ ] Kwyre Cloud launch — 32B/72B models on Lambda/DO H100 GPU clusters, API access, subscription billing
- [ ] Credit card payment integration (local + cloud)
- [ ] Adapter marketplace — community-trained adapters with verified metadata + revenue sharing
- [ ] Custom Cloud LLM service — domain-specific model training + dedicated hosted inference
- [x] CI/CD pipeline — GitHub Actions for lint, test, build, Docker push, Helm package
- [ ] Backend feature parity — RAG, adapters, analytics across all inference backends (vLLM, CPU, MLX)
- [x] Customer adapter fine-tuning API — POST /v1/adapter/train with background job system
- [ ] 7B SpikingBrain model — custom architecture with sliding-window attention and GLA
- [ ] SpikingBrain VLM — 7B vision-language model for multimodal inference

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

**Mint Rail LLC** — AI infrastructure, blockchain forensics, and applied machine learning.

Kwyre is one product in the Mint Rail family. Each product is a standalone platform with its own brand, built on shared ML infrastructure:

| Product | Domain | Description |
|---------|--------|-------------|
| **Kwyre** | Secure local AI | Air-gappable inference for regulated industries (this repo) |
| **QuantEdge** | Quantitative finance | AI-powered factor modeling, options pricing, and portfolio optimization for quant desks |
| **LabMind** | Scientific research | Literature synthesis, experiment design, and hypothesis generation for researchers |
| **DentAI** | Dental practice | Treatment planning, radiograph analysis, and insurance coding for dental professionals |
| **CodeForge** | Software engineering | Codebase-aware AI with architecture analysis, code review, and refactoring for engineering teams |
| **TaxShield** | Tax strategy | Tax planning optimization, deduction analysis, and compliance for accountants and firms |
| **LaunchPad** | Job placement | AI-powered resume optimization, interview coaching, and job-candidate matching platform |
| **SoulSync** | Dating & relationships | AI-driven compatibility scoring, personality analysis, and soulmate matching platform |

Each product has its own repository, website, and documentation. Visit [mintrail.com](https://mintrail.com) for the full portfolio.

We built Kwyre because we needed it ourselves. We cannot upload active federal investigation evidence to OpenAI. Neither can you.

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
| Purchase | `/pay.html` | Payment, license verification, downloads |

---

*All inference runs 100% locally. No data leaves your machine.*
*We are not lawyers. This is not legal advice. Verify your own compliance requirements.*
