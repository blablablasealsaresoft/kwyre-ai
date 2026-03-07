# Kwyre AI — Full Build Plan
> Air-gapped compliance inference. Local. Private. Uncompromisable.

---

## CURRENT STATE
- Model: Qwen3.5-9B + SpikeServe activation encoding
- QAT training run in progress (stopping now)
- 6-layer security stack coded
- Target market: forensic investigators, law firms, financial analysts, cleared contractors

---

## PHASE 0 — STOP TRAINING + SAVE CHECKPOINT

### Step 0.1 — Kill the training process cleanly
```bash
# In the WSL2 terminal running train_qat.py
# Press Ctrl+C once — let it save the current checkpoint gracefully
# Do NOT force kill or the checkpoint will be corrupt
```

### Step 0.2 — Verify checkpoint was saved
```bash
ls -la ~/qat_output/
ls -la ~/qat_output/checkpoint-*/
# You should see checkpoint-XXX folders with pytorch_model files
# Note the highest checkpoint number — that's your resume point
```

### Step 0.3 — Free the VRAM
```bash
# Restart WSL2 from Windows PowerShell to release all orphaned VRAM
wsl --shutdown
# Then reopen WSL2 and verify
nvidia-smi
# Should show ~0 VRAM used
```

### Step 0.4 — Record what you have
```bash
# Check what sparsity and loss the partial run achieved
cat ~/qat_output/trainer_state.json | python -c "
import json, sys
state = json.load(sys.stdin)
print('Steps completed:', state.get('global_step'))
print('Best loss:', state.get('best_metric'))
print('Log history (last 5):')
for entry in state.get('log_history', [])[-5:]:
    print(' ', entry)
"
```

---

## PHASE 1 — REPOSITORY STRUCTURE

### Step 1.1 — Create clean project structure
```
kwyre/
├── model/
│   ├── spike_qat.py              # (existing — your STE training hooks)
│   ├── spike_serve.py            # (existing — inference hooks)
│   └── train_qat.py              # (existing — QAT training pipeline)
├── server/
│   ├── serve_local_4bit.py       # (new full version with all 6 security layers)
│   └── tools.py                  # (existing — tool routing)
├── security/
│   ├── setup_isolation.sh        # (new — Layer 2 network isolation)
│   └── verify_deps.py            # (new — Layer 3 dependency integrity)
├── chat/
│   └── chat.html                 # (existing — frontend)
├── installer/
│   ├── install_windows.ps1       # (todo — Phase 4)
│   └── install_linux.sh          # (todo — Phase 4)
├── docs/
│   ├── DATA_RESIDENCY.md         # (todo — Phase 3)
│   └── SECURITY_ARCHITECTURE.md  # (todo — Phase 3)
├── requirements.in               # (todo — unpinned deps)
├── requirements.txt              # (todo — pinned with hashes)
├── docker-compose.yml            # (todo — Phase 4)
└── README.md                     # (todo — Phase 5)
```

### Step 1.2 — Initialize git repo
```bash
cd ~/kwyre
git init
echo "*.safetensors" >> .gitignore
echo "*.bin" >> .gitignore
echo "qat_output/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo ".env" >> .gitignore
echo "kwyre_dep_manifest.json" >> .gitignore  # generated per-machine
git add .
git commit -m "initial: kwyre base structure"
```

---

## PHASE 2 — SECURITY STACK (all 6 layers)

### Step 2.1 — Deploy the full server (Layers 1, 4, 5, 6)
```bash
# Copy serve_local_4bit_full.py into your server directory
cp serve_local_4bit_full.py kwyre/server/serve_local_4bit.py

# Install psutil (required for Layer 6 watchdog)
pip install psutil --break-system-packages
```

### Step 2.2 — Generate weight integrity hashes (Layer 4)
```bash
# Run ONCE on your clean model install
# Generates SHA256 hashes for config files
python -c "
import sys
sys.path.insert(0, './server')
from serve_local_4bit import generate_weight_hashes
import json

model_path = '/root/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a'
hashes = generate_weight_hashes(model_path)
print(json.dumps(hashes, indent=2))
"
# Copy the output into KNOWN_WEIGHT_HASHES dict in serve_local_4bit.py
```

### Step 2.3 — Install Layer 2 (network isolation)
```bash
# WSL2 Linux side
chmod +x kwyre/security/setup_isolation.sh
sudo kwyre/security/setup_isolation.sh install

# Windows Firewall side (print PowerShell commands)
sudo kwyre/security/setup_isolation.sh windows
# Then run those commands in elevated PowerShell on Windows
```

### Step 2.4 — Generate dependency manifest (Layer 3)
```bash
# Run ONCE on clean install — generates hash manifest
python kwyre/security/verify_deps.py generate
# Commit kwyre_dep_manifest.json to repo
```

### Step 2.5 — Add Layer 3 to server startup
```python
# Add these two lines to serve_local_4bit.py startup section
# (before model loading, after integrity check)
from verify_deps import startup_check
startup_check(abort_on_failure=True)
```

### Step 2.6 — Test all security layers
```bash
# Start server
python kwyre/server/serve_local_4bit.py

# Verify health endpoint shows all layers active
curl http://127.0.0.1:8000/health | python -m json.tool
# Should show:
# - bind_address: 127.0.0.1:8000
# - weight_integrity: configured
# - conversation_storage: RAM-only
# - watchdog: running: true

# Verify audit endpoint
curl -H "Authorization: Bearer sk-kwyre-dev-local" \
     http://127.0.0.1:8000/audit | python -m json.tool

# Verify server is NOT reachable from network
# From a different machine or WSL2 instance:
curl http://0.0.0.0:8000/health  # Should fail/refuse connection
```

---

## PHASE 3 — TRAINING (proper run)

### Step 3.1 — Fix the k-curriculum for your actual step count
```python
# In train_qat.py, update build_k_schedule() for smaller runs
# The original schedule was designed for 30K steps
# For ~3K steps (50K samples, 1 epoch):

def build_k_schedule(args, total_steps):
    if args.k_schedule == "step":
        n_phases = 5
        phase_len = max(total_steps // n_phases, 1)
        k_values = [50.0, 25.0, 12.0, 8.0, 5.0]
        schedule = [(i * phase_len, kv) for i, kv in enumerate(k_values)]
        return KCurriculumScheduler(
            mode="step", k_schedule=schedule,
            total_steps=total_steps, start_k=args.k_start, end_k=args.k_end,
        )
    return KCurriculumScheduler(
        mode="linear", total_steps=total_steps,
        warmup_steps=args.warmup_steps, start_k=args.k_start, end_k=args.k_end,
    )
```

### Step 3.2 — Run proper training (optimized for 16GB VRAM)
```bash
python kwyre/model/train_qat.py \
  --dataset teknium/OpenHermes-2.5 \
  --max_samples 50000 \
  --num_epochs 1 \
  --batch_size 1 \
  --grad_accum 16 \
  --lora_rank 64 \
  --lora_alpha 128 \
  --max_seq_len 2048 \
  --layer_stride 2 \
  --k_start 50.0 \
  --k_end 5.0 \
  --k_schedule step \
  --lr 2e-5 \
  --output_dir ./qat_output_v1 \
  --save_steps 500 \
  --eval_steps 250 \
  --logging_steps 25
# Estimated: ~3,125 steps at ~44s/it = ~38 hours
# Monitor: watch -n 300 nvidia-smi
```

### Step 3.3 — Evaluate after training
```bash
# Check final sparsity and loss
cat ./qat_output_v1/trainer_state.json | python -c "
import json, sys
state = json.load(sys.stdin)
print('Final step:', state['global_step'])
print('Best eval loss:', state['best_metric'])
print('Final log entry:', state['log_history'][-1])
"

# Load the final checkpoint and check sparsity via health endpoint
# Update serve_local_4bit.py MODEL_ID to point at ./qat_output_v1/final
# Restart server and check:
curl http://127.0.0.1:8000/health
# spike_analysis.projected_sparsity_pct should be meaningfully higher
# than the base model — target is 40%+
```

### Step 3.4 — Merge LoRA adapters for deployment
```bash
python -c "
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base_model_id = 'Qwen/Qwen3.5-9B'
lora_path = './qat_output_v1/final'
output_path = './kwyre-9b-v1-merged'

print('Loading base model...')
model = AutoModelForCausalLM.from_pretrained(
    base_model_id, torch_dtype=torch.bfloat16, device_map='cpu'
)
tokenizer = AutoTokenizer.from_pretrained(base_model_id)

print('Loading LoRA adapters...')
model = PeftModel.from_pretrained(model, lora_path)

print('Merging...')
model = model.merge_and_unload()

print(f'Saving merged model to {output_path}')
model.save_pretrained(output_path)
tokenizer.save_pretrained(output_path)
print('Done.')
"
```

---

## PHASE 4 — INSTALLER + DOCKER

### Step 4.1 — Create docker-compose.yml
```yaml
# kwyre/docker-compose.yml
version: '3.8'

services:
  kwyre:
    build: .
    container_name: kwyre-inference
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - KWYRE_API_KEYS=${KWYRE_API_KEYS:-sk-kwyre-dev-local:admin}
    ports:
      - "127.0.0.1:8000:8000"   # Localhost only — never 0.0.0.0
    volumes:
      - ${HF_CACHE:-~/.cache/huggingface}:/root/.cache/huggingface:ro  # Read-only
      - kwyre_logs:/var/log/kwyre  # Metadata logs only
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  kwyre_logs:
```

### Step 4.2 — Create Dockerfile
```dockerfile
# kwyre/Dockerfile
FROM nvidia/cuda:12.1-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3.11 python3-pip curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install deps with hash verification
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

# Copy server code
COPY server/ ./
COPY security/verify_deps.py ./
COPY model/spike_serve.py ./

# No model weights in image — mounted from host at runtime
# This keeps the image small and weights under user control

EXPOSE 8000
CMD ["python", "serve_local_4bit.py"]
```

### Step 4.3 — Create Windows installer script
```powershell
# kwyre/installer/install_windows.ps1
# Run in elevated PowerShell

param(
    [string]$InstallDir = "$env:USERPROFILE\kwyre",
    [string]$ModelDir = "$env:USERPROFILE\.cache\huggingface"
)

Write-Host "=== Kwyre AI Installer ===" -ForegroundColor Cyan
Write-Host "Install directory: $InstallDir"

# Check NVIDIA GPU
$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if (-not $gpu) {
    Write-Error "No NVIDIA GPU detected. Kwyre requires CUDA-capable GPU."
    exit 1
}
Write-Host "GPU detected: $($gpu.Name)" -ForegroundColor Green

# Check VRAM (need at least 8GB)
# Create install directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

# Clone repo (or copy files)
# Download model weights via huggingface-cli
# Install Python deps
# Apply Windows Firewall rules
# Create desktop shortcut

Write-Host "Installing Windows Firewall isolation rules..." -ForegroundColor Yellow
$pythonPath = "$InstallDir\venv\Scripts\python.exe"
Remove-NetFirewallRule -DisplayName "Kwyre-*" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" -Direction Outbound `
    -Action Block -Program $pythonPath -Profile Any
New-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" -Direction Outbound `
    -Action Allow -Program $pythonPath -RemoteAddress "127.0.0.1" -Profile Any
Write-Host "Firewall rules installed." -ForegroundColor Green

Write-Host "Installation complete." -ForegroundColor Green
Write-Host "Launch Kwyre: $InstallDir\start_kwyre.bat"
```

---

## PHASE 5 — COMPLIANCE DOCUMENTATION

### Step 5.1 — Write DATA_RESIDENCY.md
```markdown
# Kwyre Data Residency & Privacy Architecture

## Summary
All inference processing occurs exclusively on the user's local hardware.
No data, queries, or responses are transmitted to any external server.

## Data Flow
[User Input] → [Local RAM] → [Local GPU] → [Local RAM] → [User Output]
                                ↑
                    No network path exists

## Technical Controls
| Control | Implementation |
|---------|---------------|
| Network binding | 127.0.0.1 only — OS-level block |
| Outbound firewall | Process-scoped block via iptables/Windows Firewall |
| Conversation storage | RAM only — never written to disk |
| Session wipe | Cryptographic overwrite on session end |
| Weight integrity | SHA256 verification at every startup |
| Dependency integrity | SHA256 manifest verified at startup |
| Intrusion response | Auto-wipe + process termination on detection |
| Telemetry | None. Zero. No analytics, no error reporting, no update checks. |

## Audit Trail
GET /audit returns metadata-only log:
- Timestamp
- Active session count
- Security control status
NO conversation content is ever logged.

## Verification
Users can independently verify zero outbound connections using:
- Windows: Resource Monitor → Network tab
- Linux/WSL2: ss -tp | grep python
- Any: Wireshark on loopback interface shows only 127.0.0.1 traffic
```

### Step 5.2 — Benchmark against GPT-4o on three tasks
```
Target tasks for your buyers:
1. Contract clause extraction (law firm buyers)
   → Feed 10 NDAs, extract confidentiality clauses
   → Compare accuracy vs GPT-4o

2. Transaction pattern summarization (forensic investigator buyers)
   → Feed blockchain transaction logs, summarize patterns
   → Compare accuracy vs Claude Sonnet

3. Regulatory citation lookup (compliance buyers)
   → Ask about specific FINRA/SEC rules
   → Compare accuracy vs GPT-4o

Publish results. You only need to win on YOUR tasks.
```

---

## PHASE 6 — PAYMENTS + DISTRIBUTION

### Step 6.1 — Monero payment integration
```
Options (in order of complexity):
1. BTCPay Server (self-hosted, accepts XMR natively)
   → Run on a separate VPS, not on inference machine
   → Never touches user data

2. GloBee or CoinPayments (hosted XMR processor)
   → Simpler but adds third-party dependency

3. Manual XMR address + license key email
   → Lowest friction to start, not scalable

Start with option 3 for first 10 customers.
Automate later.
```

### Step 6.2 — License key system
```python
# Simple license validation — no phone-home required
# License key encodes: buyer_id + expiry + features
# Validated entirely locally using HMAC-SHA256

import hmac
import hashlib
import base64
import time

LICENSE_SECRET = "your-secret-key-never-committed-to-git"

def generate_license(buyer_id: str, expiry_timestamp: int, tier: str) -> str:
    payload = f"{buyer_id}:{expiry_timestamp}:{tier}"
    sig = hmac.new(
        LICENSE_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:16]
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()

def validate_license(license_key: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(license_key).decode()
        parts = raw.split(":")
        buyer_id, expiry, tier, sig = parts[0], parts[1], parts[2], parts[3]
        
        expected_payload = f"{buyer_id}:{expiry}:{tier}"
        expected_sig = hmac.new(
            LICENSE_SECRET.encode(),
            expected_payload.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        
        if not hmac.compare_digest(sig, expected_sig):
            return {"valid": False, "reason": "invalid signature"}
        
        if int(expiry) < time.time():
            return {"valid": False, "reason": "expired"}
        
        return {"valid": True, "buyer": buyer_id, "tier": tier}
    except Exception:
        return {"valid": False, "reason": "malformed key"}
```

### Step 6.3 — Distribution page (minimal)
```
kwyre.ai landing page needs only:
1. One paragraph: what it is
2. One section: what data it DOESN'T collect (the list)
3. Hardware requirements (4090 or equivalent, 16GB+ VRAM)
4. Pricing table (Personal $299 | Professional $799 | Air-Gapped Kit $1499)
5. Download button (triggers license purchase flow)
6. Link to DATA_RESIDENCY.md

No blog. No social proof yet. No fluff.
Ship the product, get users, add proof later.
```

---

## PHASE 7 — FIRST CUSTOMER

### Step 7.1 — Use it yourself first
```
Run Kwyre on an APOLLO CyberSentinel investigation.
Document specifically:
- What task you used it for
- What data you could NOT have sent to ChatGPT
- How the output compared to ChatGPT
- Time saved

This becomes your first case study.
```

### Step 7.2 — First outreach targets
```
In order:
1. r/netsec — post technical writeup of spike QAT + privacy architecture
   Title: "I built a local LLM inference server with hardware-level 
           isolation for air-gapped security work. Here's the architecture."
   
2. OSINT/forensics communities (Trace Labs, DFIR Discord)
   Lead with the investigator use case

3. Direct outreach to 5 solo forensic accountants on LinkedIn
   One sentence: "Do you use AI tools for case analysis? 
                  Asking because I built something you might need."

Do NOT launch on ProductHunt until you have 10 happy users.
```

---

## PRIORITY ORDER — THIS WEEK

```
Day 1 (today):
  [ ] Stop training, save checkpoint (Phase 0)
  [ ] Set up repo structure (Phase 1)
  [ ] Deploy serve_local_4bit_full.py (Phase 2, Step 2.1)
  [ ] Generate weight hashes (Phase 2, Step 2.2)

Day 2:
  [ ] Install network isolation (Phase 2, Step 2.3)
  [ ] Generate dep manifest (Phase 2, Step 2.4)
  [ ] Test all 6 security layers (Phase 2, Step 2.6)
  [ ] Write DATA_RESIDENCY.md (Phase 5, Step 5.1)

Day 3-4:
  [ ] Start proper training run (Phase 3, Step 3.2)
  [ ] While training: write Docker setup (Phase 4)
  [ ] While training: fix k-curriculum (Phase 3, Step 3.1)

Day 5:
  [ ] Evaluate trained model (Phase 3, Step 3.3)
  [ ] Merge LoRA adapters (Phase 3, Step 3.4)
  [ ] Run first benchmark task

Next week:
  [ ] Installer (Phase 4)
  [ ] Compliance docs (Phase 5)
  [ ] Pricing page (Phase 6)
  [ ] First customer outreach (Phase 7)
```

---

## NOTES FOR CURSOR

- All security files are in `kwyre/security/`
- Server entry point is always `kwyre/server/serve_local_4bit.py`
- Model training is always run from repo root, output goes to `qat_output_v1/`
- Never commit: model weights, .env, dep manifest (machine-specific), API keys
- Always commit: security scripts, server code, training code, docs
- The `KNOWN_WEIGHT_HASHES` dict in serve_local_4bit.py must be populated manually per deployment
- `LICENSE_SECRET` in the license system must come from environment variable, never hardcoded
