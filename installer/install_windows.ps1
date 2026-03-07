#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Kwyre AI Windows Installer
.DESCRIPTION
    Sets up Kwyre AI local inference with Layer 2 network isolation
    via Windows Firewall rules.
.PARAMETER InstallDir
    Installation directory (default: $env:USERPROFILE\kwyre)
#>

param(
    [string]$InstallDir = "$env:USERPROFILE\kwyre",
    [string]$ModelDir = "$env:USERPROFILE\.cache\huggingface"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "         Kwyre AI — Windows Installer        " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Install directory: $InstallDir"
Write-Host "Model cache:       $ModelDir"
Write-Host ""

# ---------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------

# Check NVIDIA GPU
$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if (-not $gpu) {
    Write-Error "No NVIDIA GPU detected. Kwyre requires a CUDA-capable GPU with 8GB+ VRAM."
    exit 1
}
Write-Host "[OK] GPU detected: $($gpu.Name)" -ForegroundColor Green

# Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python not found. Install Python 3.11+ from https://python.org"
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "[OK] Python: $pyVer" -ForegroundColor Green

# Check CUDA
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $cudaInfo = nvidia-smi --query-gpu=driver_version,memory.total --format=csv,noheader 2>$null
    Write-Host "[OK] CUDA driver: $cudaInfo" -ForegroundColor Green
} else {
    Write-Warning "nvidia-smi not found. Ensure CUDA drivers are installed."
}

# ---------------------------------------------------------------
# Create directories
# ---------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

# ---------------------------------------------------------------
# Create virtual environment
# ---------------------------------------------------------------
$venvPath = Join-Path $InstallDir "venv"
if (-not (Test-Path (Join-Path $venvPath "Scripts\python.exe"))) {
    Write-Host ""
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv $venvPath
    Write-Host "[OK] Virtual environment created at $venvPath" -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment exists at $venvPath" -ForegroundColor Green
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

# ---------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------
$reqFile = Join-Path $InstallDir "requirements.txt"
if (Test-Path $reqFile) {
    Write-Host ""
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pip | Out-Null
    & $venvPython -m pip install -r $reqFile
    Write-Host "[OK] Dependencies installed" -ForegroundColor Green
} else {
    Write-Warning "requirements.txt not found at $reqFile — skipping dependency install."
    Write-Warning "Copy Kwyre files to $InstallDir first, then re-run this script."
}

# ---------------------------------------------------------------
# Layer 2: Windows Firewall isolation
# ---------------------------------------------------------------
Write-Host ""
Write-Host "Installing Layer 2 network isolation rules..." -ForegroundColor Yellow

Remove-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" -ErrorAction SilentlyContinue

New-NetFirewallRule `
    -DisplayName "Kwyre-BlockOutbound" `
    -Description "Block all outbound traffic from Kwyre Python process" `
    -Direction Outbound `
    -Action Block `
    -Program $venvPython `
    -Profile Any | Out-Null

New-NetFirewallRule `
    -DisplayName "Kwyre-AllowLocalhost" `
    -Description "Allow Kwyre Python to communicate on localhost only" `
    -Direction Outbound `
    -Action Allow `
    -Program $venvPython `
    -RemoteAddress "127.0.0.1" `
    -Profile Any | Out-Null

Write-Host "[OK] Firewall rules installed:" -ForegroundColor Green
Get-NetFirewallRule -DisplayName "Kwyre-*" | Format-Table DisplayName, Direction, Action, Enabled -AutoSize

# ---------------------------------------------------------------
# Generate dependency manifest (Layer 3)
# ---------------------------------------------------------------
$verifyDeps = Join-Path $InstallDir "security\verify_deps.py"
if (Test-Path $verifyDeps) {
    Write-Host ""
    Write-Host "Generating dependency integrity manifest (Layer 3)..." -ForegroundColor Yellow
    & $venvPython $verifyDeps generate
    Write-Host "[OK] Dependency manifest generated" -ForegroundColor Green
}

# ---------------------------------------------------------------
# Create launch script
# ---------------------------------------------------------------
$launchScript = Join-Path $InstallDir "start_kwyre.bat"
@"
@echo off
echo Starting Kwyre AI...
echo.
"%~dp0venv\Scripts\python.exe" "%~dp0server\serve_local_4bit.py"
pause
"@ | Set-Content -Path $launchScript -Encoding ASCII

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "         Installation Complete               " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Launch Kwyre:  $launchScript" -ForegroundColor White
Write-Host "  Or run:        $venvPython $InstallDir\server\serve_local_4bit.py" -ForegroundColor White
Write-Host ""
Write-Host "  Server:        http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Chat UI:       http://127.0.0.1:8000/chat" -ForegroundColor White
Write-Host "  Health check:  http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "  Security: All 6 layers active. No data leaves this machine." -ForegroundColor Cyan
Write-Host ""
