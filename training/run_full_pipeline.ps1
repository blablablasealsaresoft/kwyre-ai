<#
.SYNOPSIS
    Kwyre AI — Full Training Pipeline.

.DESCRIPTION
    Runs trace generation, distillation, GRPO, and export in sequence.
    Requires GPU with 24GB+ VRAM and ANTHROPIC_API_KEY set.

.EXAMPLE
    .\run_full_pipeline.ps1
#>

$ErrorActionPreference = 'Stop'

$env:ANTHROPIC_API_KEY = 'sk-ant-api03-PLACEHOLDER-SET-YOUR-KEY-HERE'
$env:KWYRE_TRACES_PER_DOMAIN = '50'
$env:PYTHONUNBUFFERED = '1'

$LogDir = Join-Path $HOME '.kwyre\logs'
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  KWYRE - Full Training Pipeline" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Cyan

& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
Write-Host ""

# ── STEP 1: Generate Reasoning Traces ────────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 1: Generating reasoning traces via Claude" -ForegroundColor Cyan
Write-Host "  Target: $env:KWYRE_TRACES_PER_DOMAIN traces per domain" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$PSScriptRoot\generate_traces_parallel.py" 2>&1 | Tee-Object -FilePath (Join-Path $LogDir '01-traces.log')

Write-Host ""
Write-Host "  Traces complete. Files:" -ForegroundColor Green
$traceDir = Join-Path $HOME '.kwyre\training-data\kwyre-traces'
$traceFiles = Get-ChildItem -Path $traceDir -Filter '*.jsonl' -ErrorAction SilentlyContinue
if ($traceFiles) {
    $traceFiles | Format-Table Name, Length, LastWriteTime -AutoSize
}
else {
    Write-Host "  (no trace files found)" -ForegroundColor Yellow
}

# ── STEP 2: Distillation Fine-Tuning ─────────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 2: Distillation fine-tuning (Unsloth QLoRA)" -ForegroundColor Cyan
Write-Host "  This will take 2-6 hours on H100" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$PSScriptRoot\train_distillation.py" 2>&1 | Tee-Object -FilePath (Join-Path $LogDir '02-distillation.log')

Write-Host "`n  Distillation complete.`n" -ForegroundColor Green

# ── STEP 3: GRPO Reinforcement Learning ──────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 3: GRPO reinforcement learning" -ForegroundColor Cyan
Write-Host "  This will take 2-4 hours on H100" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$PSScriptRoot\train_grpo.py" 2>&1 | Tee-Object -FilePath (Join-Path $LogDir '03-grpo.log')

Write-Host "`n  GRPO complete.`n" -ForegroundColor Green

# ── SUMMARY ───────────────────────────────────────────────────────────────────
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FULL PIPELINE COMPLETE!" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Artifacts:" -ForegroundColor White
Write-Host "    Traces:      ~\.kwyre\training-data\kwyre-traces\" -ForegroundColor Gray
Write-Host "    Distilled:   ~\.kwyre\models\trained\kwyre-9b-distilled\" -ForegroundColor Gray
Write-Host "    GRPO:        ~\.kwyre\models\trained\kwyre-9b-grpo\" -ForegroundColor Gray
Write-Host "    LoRA:        ~\.kwyre\lora-adapters\" -ForegroundColor Gray
Write-Host "    GGUFs:       ~\.kwyre\models\trained\kwyre-9b-*-gguf\" -ForegroundColor Gray
Write-Host ""

$trainedDir = Join-Path $HOME '.kwyre\models\trained'
if (Test-Path $trainedDir) {
    Get-ChildItem -Path $trainedDir -Recurse | Select-Object -First 30 |
        Format-Table FullName, Length -AutoSize
}
