<#
.SYNOPSIS
    Kwyre AI — Domain Adapter Training Pipeline.

.DESCRIPTION
    Trains a single domain adapter: traces -> distillation -> GRPO -> export.
    Requires H100 or A100 GPU with 24GB+ VRAM.

.EXAMPLE
    $env:KWYRE_DOMAIN = 'legal_compliance'
    .\run_domain_training.ps1

.EXAMPLE
    $env:KWYRE_DOMAIN = 'blockchain_crypto'
    .\run_domain_training.ps1
#>

$ErrorActionPreference = 'Stop'

$env:PYTHONUNBUFFERED = '1'

# ── Validate inputs ──────────────────────────────────────────────────────────
$Domain = $env:KWYRE_DOMAIN
if (-not $Domain) {
    Write-Host "ERROR: Set `$env:KWYRE_DOMAIN to one of:" -ForegroundColor Red
    Write-Host "  legal_compliance" -ForegroundColor Yellow
    Write-Host "  insurance_actuarial" -ForegroundColor Yellow
    Write-Host "  healthcare_lifesciences" -ForegroundColor Yellow
    Write-Host "  defense_intelligence" -ForegroundColor Yellow
    Write-Host "  financial_trading" -ForegroundColor Yellow
    Write-Host "  blockchain_crypto" -ForegroundColor Yellow
    Write-Host "  sports_analytics" -ForegroundColor Yellow
    Write-Host "  relationship_matching" -ForegroundColor Yellow
    Write-Host "  software_engineering" -ForegroundColor Yellow
    Write-Host "  scientific_research" -ForegroundColor Yellow
    Write-Host "  career_placement" -ForegroundColor Yellow
    Write-Host "  college_basketball" -ForegroundColor Yellow
    Write-Host "  dental_clinical" -ForegroundColor Yellow
    exit 1
}

if (-not $env:KWYRE_BASE_MODEL) {
    $env:KWYRE_BASE_MODEL = 'HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive'
}
if (-not $env:KWYRE_TRACES_PER_DOMAIN) {
    $env:KWYRE_TRACES_PER_DOMAIN = '300'
}

$LogDir = Join-Path $HOME '.kwyre\logs'
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$ModelTag = '4b'
if ($env:KWYRE_BASE_MODEL -match '9B') {
    $ModelTag = '9b'
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  KWYRE - Domain Adapter Training" -ForegroundColor Cyan
Write-Host "  Domain:  $Domain" -ForegroundColor White
Write-Host "  Base:    $env:KWYRE_BASE_MODEL" -ForegroundColor White
Write-Host "  Tag:     $ModelTag" -ForegroundColor White
Write-Host "  Traces:  $env:KWYRE_TRACES_PER_DOMAIN" -ForegroundColor White
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Cyan

$nvSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvSmi) {
    & nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
}
else {
    Write-Host "  (no GPU detected)" -ForegroundColor Yellow
}
Write-Host ""

$ScriptDir = $PSScriptRoot

# ── Step 1: Generate traces (skip if already exists) ─────────────────────────
$TraceFile = Join-Path $HOME ".kwyre\training-data\kwyre-traces\$Domain.jsonl"

if (Test-Path $TraceFile) {
    $TraceCount = (Get-Content $TraceFile).Count
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  STEP 1: Traces already exist ($TraceCount samples)" -ForegroundColor Cyan
    Write-Host "  File: $TraceFile" -ForegroundColor White
    Write-Host "  Skipping generation. Delete file to regenerate." -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Cyan
}
else {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  STEP 1: Generating reasoning traces via Claude" -ForegroundColor Cyan
    Write-Host "  Domain: $Domain" -ForegroundColor White
    Write-Host "  Target: $env:KWYRE_TRACES_PER_DOMAIN traces" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Cyan

    if (-not $env:ANTHROPIC_API_KEY) {
        Write-Host "  ERROR: ANTHROPIC_API_KEY not set. Required for trace generation." -ForegroundColor Red
        Write-Host "  Set it or provide pre-generated traces at $TraceFile" -ForegroundColor Yellow
        exit 1
    }

    python "$ScriptDir\generate_traces_parallel.py" 2>&1 |
        Tee-Object -FilePath (Join-Path $LogDir "$Domain-01-traces.log")
}

Write-Host ""

# ── Step 2: Distillation ─────────────────────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)" -ForegroundColor Cyan
Write-Host "  Domain: $Domain" -ForegroundColor White
Write-Host "  Estimated: 2-4 hours on H100" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$ScriptDir\train_distillation.py" 2>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "$Domain-02-distillation-$ModelTag.log")

Write-Host "`n  Distillation complete!`n" -ForegroundColor Green

# ── Step 3: GRPO ─────────────────────────────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 3: Domain GRPO reinforcement learning" -ForegroundColor Cyan
Write-Host "  Domain: $Domain" -ForegroundColor White
Write-Host "  Estimated: 2-4 hours on H100" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$ScriptDir\train_grpo_domain.py" 2>&1 |
    Tee-Object -FilePath (Join-Path $LogDir "$Domain-03-grpo-$ModelTag.log")

Write-Host "`n  GRPO complete!`n" -ForegroundColor Green

# ── Summary ───────────────────────────────────────────────────────────────────
$DomainHyphenated = $Domain -replace '_', '-'
$AdapterDir = Join-Path $HOME ".kwyre\adapters\$DomainHyphenated"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DOMAIN TRAINING COMPLETE!" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Domain:     $Domain" -ForegroundColor White
Write-Host "  Base model: $env:KWYRE_BASE_MODEL" -ForegroundColor White
Write-Host "  Adapter:    $AdapterDir" -ForegroundColor White
Write-Host ""

if (Test-Path $AdapterDir) {
    Write-Host "  Adapter files:" -ForegroundColor White
    Get-ChildItem -Path $AdapterDir | Format-Table Name, Length -AutoSize

    $adapterSize = (Get-ChildItem -Path $AdapterDir -Recurse |
        Measure-Object -Property Length -Sum).Sum
    $sizeMB = [math]::Round($adapterSize / 1MB, 1)
    Write-Host "  Total adapter size: ${sizeMB}MB" -ForegroundColor White
}

Write-Host ""
Write-Host "  To use this adapter:" -ForegroundColor White
Write-Host "    1. Copy $AdapterDir to your Kwyre installation" -ForegroundColor Gray
Write-Host "    2. Set `$env:KWYRE_ADAPTER_DIR = '~\.kwyre\adapters'" -ForegroundColor Gray
Write-Host "    3. Start Kwyre, then:" -ForegroundColor Gray
Write-Host "       curl -X POST http://127.0.0.1:8000/v1/adapter/load ``" -ForegroundColor Gray
Write-Host "         -H 'Authorization: Bearer sk-kwyre-dev-local' ``" -ForegroundColor Gray
Write-Host "         -d '{`"domain`": `"$DomainHyphenated`"}'" -ForegroundColor Gray
Write-Host ""
