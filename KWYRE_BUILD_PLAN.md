# Kwyre AI — Build Plan
> Air-gapped compliance inference. Local. Private. Uncompromisable.

---

## COMPLETED PHASES (v0.1 — v1.1)

All original build phases have been completed and shipped.

### Phase 0 — Training + Checkpoint (DONE)
- QAT training with Spike STE hooks on Qwen3.5-9B
- k-curriculum annealing (k=50 to 5) over 5 phases
- LoRA rank 64, alpha 128, targeting MLP layers
- Checkpoints saved, LoRA adapters merged for deployment

### Phase 1 — Repository Structure (DONE)
- Full project structure with server/, model/, security/, chat/, installer/, finetune/, benchmarks/, docs/, tests/
- Git repo initialized, .gitignore for weights, manifests, .env, build artifacts

### Phase 2 — Security Stack (DONE)
- 6-layer defense: L1 localhost bind, L2 process firewall, L3 dependency integrity, L4 weight integrity, L5 RAM-only sessions + crypto wipe, L6 intrusion watchdog
- Shared security infrastructure in `server/security_core.py`
- All backends (GPU, CPU, MLX) use the same security stack
- 110 security tests across 3 test suites, all passing

### Phase 3 — Training + Evaluation (DONE)
- Qwen3-4B (personal tier) and Qwen3.5-9B (professional tier)
- Pre-quantized NF4 models in dist/ (~2.5 GB main, ~0.8 GB draft)
- SpikeServe on draft model (84 MLP layers, measure-only mode)
- Speculative decoding with Qwen3-0.6B draft model

### Phase 4 — Docker + Installers (DONE)
- Dockerfile (CUDA 12.4.1, non-root kwyre user, entrypoint with model download)
- docker-compose.yml (GPU reservation, localhost-only port, HF cache volume)
- Windows installer (CLI + tkinter GUI wizard)
- Linux installer (systemd + iptables)
- macOS installer (launchd + PF firewall)

### Phase 5 — Compliance Documentation (DONE)
- DATA_RESIDENCY.md, SECURITY_ARCHITECTURE.md
- SOC2_DEPLOYMENT_GUIDE.md, ENTERPRISE_AUDIT.md
- COMPLIANCE_LETTER.md (GDPR, HIPAA, SOC 2, FINRA, ITAR, FRE, ABA)
- VERIFICATION_GUIDE.md, DEPLOYMENT_CHECKLIST.md, INCIDENT_RESPONSE.md
- Benchmark suite vs GPT-4o (3 datasets, 30 tasks, LLM-as-judge scoring)

### Phase 6 — Payments + Distribution (DONE)
- Monero (XMR) payment integration (no email required)
- Ed25519 offline license keys with hardware-bound machine fingerprinting
- pay.html with CC/XMR payment flow
- kwyre.com live on Cloudflare Pages

### Phase 7 — Production Hardening (DONE — v1.0 + v1.1)
- Nuitka build pipeline (compiled binary, source protection)
- Code signing (Ed25519-signed MANIFEST.sig.json)
- Air-gap safe update mechanism (.kwyre-update packages)
- Flash Attention 2 (auto-detected, +20-40% throughput)
- TF32 matmul + cuDNN benchmark
- torch.inference_mode() for reduced overhead
- Session reaper race condition fixed
- Stream error surfacing (finish_reason: "error")
- Memory leak prevention (rate_tracker cleanup, intrusion_log cap)
- Thread-safe SpikeServe stats
- Default system prompt (professional legal/forensic persona)
- repetition_penalty + top_k parameter support
- Markdown rendering, copy-to-clipboard, conversation export, dark/light mode
- Chat UI consolidated into main.html (chat.html removed)
- Integration test suite (HTTP endpoints, SSE, KV cache, sessions)

---

## CURRENT STATE (v1.1)

```
Server:     serve_local_4bit.py (GPU), serve_cpu.py (CPU), serve_mlx.py (MLX)
Model:      Qwen3-4B main + Qwen3-0.6B draft (pre-quantized NF4 in dist/)
VRAM:       3.9 GB total (both models + KV cache)
Speed:      6.7 tok/s warmed up (RTX 4090 Laptop), target 7-14 tok/s
Security:   6 layers active, 110 tests passing
Frontend:   main.html — markdown, copy, export, dark/light, session management
Deployed:   GitHub (main branch), Cloudflare Pages (kwyre.com)
Tests:      110 security + integration suite
```

---

## PHASE 8 — GROWTH + SCALE (NEXT)

### 8.1 — First Customer Acquisition
```
1. Use Kwyre on an APOLLO CyberSentinel investigation
   - Document the task, the data sensitivity, the output quality
   - This becomes the first case study

2. r/netsec technical writeup
   - Spike QAT + privacy architecture deep dive
   - Title: "I built a local LLM with hardware-level isolation for
            air-gapped security work. Here's the architecture."

3. OSINT/forensics communities (Trace Labs, DFIR Discord)
   - Lead with the investigator use case

4. Direct outreach to 5 solo forensic accountants on LinkedIn
   - "Do you use AI tools for case analysis?"

5. Do NOT launch on ProductHunt until 10 happy users.
```

### 8.2 — Domain Fine-Tuning (Legal/Forensic Specialization)
```
Use the existing finetune/ pipeline to train domain adapters:

1. Legal adapter — NDA analysis, privilege review, contract extraction
   - Use finetune/templates.py legal templates (12 scenarios)
   - Target: beat GPT-4o on contract clause extraction

2. Forensic adapter — chain of custody, evidence analysis, expert reports
   - Use finetune/templates.py forensic templates (12 scenarios)
   - Target: beat GPT-4o on financial fraud pattern detection

3. Financial adapter — SEC filings, BSA/AML, forensic accounting
   - Use finetune/templates.py financial templates (12 scenarios)
   - Target: beat GPT-4o on regulatory citation accuracy

Run benchmarks/benchmark.py after each adapter to track quality.
```

### 8.3 — RAG / Document Ingestion
```
Biggest value-add for the legal/forensic buyer:

1. Local document upload (PDF, DOCX, TXT)
2. Chunking + embedding (local model, no cloud)
3. Vector search (FAISS or similar, RAM-only)
4. Retrieval-augmented generation for case files
5. All data stays in RAM, wiped on session end

This is the feature that makes Kwyre a case analysis tool,
not just a chat interface.
```

### 8.4 — Performance Targets
```
Current:  6.7 tok/s warmed up (RTX 4090 Laptop)
Target:   10-14 tok/s

Remaining optimizations:
- Flash Attention 2 (already implemented, needs flash-attn pip install)
- Continuous batching (if multi-user demand grows)
- vLLM backend option for production deployments
- PagedAttention for larger KV cache with less VRAM waste
```

### 8.5 — Enterprise Features
```
- Multi-tenant deployment guide (one server, isolated users)
- SAML/SSO integration for enterprise auth
- Audit log export to SIEM (Splunk, QRadar)
- Kubernetes Helm chart for cloud-hosted air-gapped deployments
- FedRAMP documentation package
```

---

## PROJECT STRUCTURE (current)

```
kwyre/
├── server/
│   ├── serve_local_4bit.py    # GPU inference (Flash Attn, speculative, KV cache, SSE)
│   ├── serve_cpu.py           # CPU inference via llama.cpp (Kwyre Air)
│   ├── serve_mlx.py           # Apple Silicon inference via MLX
│   ├── security_core.py       # Shared security infrastructure (all 6 layers)
│   ├── users.py               # Multi-user management (Fernet-encrypted)
│   ├── audit.py               # Per-user audit logging (RAM-only)
│   └── tools.py               # External API tool router
├── model/
│   ├── spike_serve.py         # SpikeServe activation encoding hooks
│   ├── spike_qat.py           # QAT training hooks (STE, k-curriculum)
│   ├── train_qat.py           # QAT training pipeline
│   ├── quantize_nf4.py        # NF4 pre-quantization
│   ├── quantize_awq.py        # AWQ quantization
│   ├── convert_gguf.py        # HuggingFace → GGUF
│   ├── convert_mlx.py         # HuggingFace → MLX
│   └── merge_and_export.py    # LoRA merge + export
├── security/
│   ├── verify_deps.py         # Layer 3 — dependency integrity
│   ├── license.py             # Ed25519 license + hardware fingerprint
│   ├── codesign.py            # Ed25519 release signing
│   ├── updater.py             # Air-gap safe update mechanism
│   └── setup_isolation.sh     # Layer 2 network isolation
├── chat/
│   ├── main.html              # Product page + chat UI (all features)
│   ├── landing.html           # Marketing landing page
│   ├── index.html             # Entry / splash page
│   └── pay.html               # Payment + license download
├── installer/
│   ├── install_windows.ps1    # Windows CLI installer
│   ├── install_windows_gui.py # Windows GUI installer (tkinter)
│   ├── install_linux.sh       # Linux installer (systemd + iptables)
│   └── install_macos.sh       # macOS installer (launchd + PF)
├── finetune/                  # Domain-specific fine-tuning pipeline
├── benchmarks/                # Benchmark suite vs GPT-4o (3 datasets, 30 tasks)
├── docs/                      # Compliance documentation package
├── tests/                     # 110 security tests + integration suite
├── dist/                      # Pre-quantized model weights
│   ├── kwyre-4b-nf4/          # Main model (~2.5 GB)
│   └── kwyre-draft-nf4/       # Draft model (~0.8 GB)
├── build.py                   # Nuitka build + installer pipeline
├── Dockerfile                 # CUDA 12.4.1 runtime container
├── docker-compose.yml         # One-command deployment
└── .env.example               # Configuration template
```

---

## NOTES FOR DEVELOPMENT

- Server entry point: `server/serve_local_4bit.py` (GPU), `serve_cpu.py` (CPU), `serve_mlx.py` (MLX)
- All three backends share `server/security_core.py` — never duplicate security code
- Frontend is a single page: `chat/main.html` (no separate chat.html)
- `/chat` route serves `main.html` (same as `/main.html`)
- Never commit: model weights (.safetensors), .env, dep manifest, API keys, .cache/
- Always commit: server code, security scripts, tests, docs, HTML
- `KNOWN_WEIGHT_HASHES` in each server must be populated per deployment
- License keys use Ed25519 (not HMAC) — public key embedded at build time
- Tests run without GPU: `python -m unittest discover -s tests -p "test_*.py"`
- Integration tests require running server: `python -m unittest tests.test_integration`
- Deploy to Cloudflare: `npx wrangler pages deploy chat/ --project-name kwyre-ai`
