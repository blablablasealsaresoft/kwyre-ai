<#
.SYNOPSIS
    Kwyre AI — GPU Training Environment Setup for Windows.

.DESCRIPTION
    Checks for NVIDIA GPU, guides CUDA toolkit installation, installs Python
    training dependencies, and verifies torch.cuda availability.

.EXAMPLE
    .\setup_gpu.ps1
#>

$ErrorActionPreference = 'Stop'

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  KWYRE - GPU Training Environment Setup" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ── Step 1: Check NVIDIA drivers ─────────────────────────────────────────────
Write-Host "[1/4] Checking NVIDIA drivers..." -ForegroundColor White

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $nvidiaSmi) {
    Write-Host "[1/4] nvidia-smi not found. NVIDIA drivers are not installed." -ForegroundColor Red
    Write-Host ""
    Write-Host "  To install:" -ForegroundColor Yellow
    Write-Host "    1. Download CUDA Toolkit 12.4 from:" -ForegroundColor Yellow
    Write-Host "       https://developer.nvidia.com/cuda-12-4-0-download-archive" -ForegroundColor White
    Write-Host "    2. Run the installer (includes drivers)" -ForegroundColor Yellow
    Write-Host "    3. Reboot if prompted" -ForegroundColor Yellow
    Write-Host "    4. Re-run this script" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "[1/4] NVIDIA drivers detected:" -ForegroundColor Green
& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ── Step 2: Install Python dependencies ──────────────────────────────────────
Write-Host "`n[2/4] Installing Python training dependencies..." -ForegroundColor White

python -m pip install --quiet --upgrade pip

$packages = @(
    'unsloth[cu124-torch260] @ git+https://github.com/unslothai/unsloth.git'
    'torch', 'torchvision', 'torchaudio'
    'transformers', 'accelerate', 'peft', 'trl', 'datasets'
    'bitsandbytes', 'scipy', 'sentencepiece', 'protobuf'
    'openai'
)
python -m pip install --quiet @packages

Write-Host "[2/4] Python dependencies installed." -ForegroundColor Green

# ── Step 3: Create directory structure ───────────────────────────────────────
Write-Host "`n[3/4] Creating directory structure..." -ForegroundColor White

$kwyreHome = Join-Path $HOME '.kwyre'
$dirs = @(
    'models\trained'
    'models\export'
    'lora-adapters'
    'training-data\kwyre-traces'
    'logs'
)
foreach ($dir in $dirs) {
    $fullPath = Join-Path $kwyreHome $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}
Write-Host "[3/4] Directories created under $kwyreHome" -ForegroundColor Green

# ── Step 4: Verify GPU via PyTorch ───────────────────────────────────────────
Write-Host "`n[4/4] Verifying GPU via PyTorch..." -ForegroundColor White

python -c @"
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"@

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Cyan
Write-Host "  Next: Upload traces to $kwyreHome\training-data\kwyre-traces\" -ForegroundColor White
Write-Host "  Then: python train_distillation.py" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Cyan
