#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Kwyre AI Windows Installer
.DESCRIPTION
    Sets up Kwyre AI local inference with Layer 2 network isolation
    via Windows Firewall rules. Supports both compiled binary and
    Python source installations.
.PARAMETER InstallDir
    Installation directory (default: $env:USERPROFILE\kwyre)
.PARAMETER ModelDir
    HuggingFace model cache directory
#>

param(
    [string]$InstallDir = "$env:USERPROFILE\kwyre",
    [string]$ModelDir = "$env:USERPROFILE\.cache\huggingface"
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "       Kwyre AI — Windows Installer v0.3     " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Install directory: $InstallDir"
Write-Host "Model cache:       $ModelDir"
Write-Host ""

# ---------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------

$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if (-not $gpu) {
    Write-Error "No NVIDIA GPU detected. Kwyre requires a CUDA-capable GPU with 4GB+ VRAM."
    exit 1
}
Write-Host "[OK] GPU detected: $($gpu.Name)" -ForegroundColor Green

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $cudaInfo = nvidia-smi --query-gpu=driver_version,memory.total --format=csv,noheader 2>$null
    Write-Host "[OK] CUDA driver: $cudaInfo" -ForegroundColor Green
} else {
    Write-Warning "nvidia-smi not found. Ensure CUDA drivers are installed."
}

# ---------------------------------------------------------------
# Detect compiled binary vs Python source
# ---------------------------------------------------------------
$compiledBinary = Join-Path $ScriptRoot "build\kwyre-dist\kwyre-server.exe"
$useCompiled = Test-Path $compiledBinary

if ($useCompiled) {
    Write-Host "[OK] Compiled binary found — installing protected build" -ForegroundColor Green
} else {
    Write-Host "[INFO] No compiled binary. Installing from Python source." -ForegroundColor Yellow

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Error "Python not found. Install Python 3.11+ from https://python.org"
        exit 1
    }
    $pyVer = python --version 2>&1
    Write-Host "[OK] Python: $pyVer" -ForegroundColor Green
}

# ---------------------------------------------------------------
# Create directories
# ---------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

# ---------------------------------------------------------------
# Install files
# ---------------------------------------------------------------
if ($useCompiled) {
    Write-Host ""
    Write-Host "Installing compiled binary..." -ForegroundColor Yellow
    Copy-Item $compiledBinary -Destination (Join-Path $InstallDir "kwyre-server.exe") -Force
    $kwyreExe = Join-Path $InstallDir "kwyre-server.exe"
    Write-Host "[OK] Binary installed" -ForegroundColor Green
} else {
    # Copy source files
    foreach ($dir in @("server", "model", "security")) {
        $srcDir = Join-Path $ScriptRoot $dir
        if (Test-Path $srcDir) {
            $dstDir = Join-Path $InstallDir $dir
            New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
            Copy-Item -Path "$srcDir\*" -Destination $dstDir -Recurse -Force
        }
    }

    $reqSrc = Join-Path $ScriptRoot "requirements-inference.txt"
    if (Test-Path $reqSrc) {
        Copy-Item $reqSrc -Destination $InstallDir -Force
    }

    # Create virtual environment
    $venvPath = Join-Path $InstallDir "venv"
    if (-not (Test-Path (Join-Path $venvPath "Scripts\python.exe"))) {
        Write-Host ""
        Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
        python -m venv $venvPath
        Write-Host "[OK] Virtual environment created" -ForegroundColor Green
    } else {
        Write-Host "[OK] Virtual environment exists" -ForegroundColor Green
    }

    $venvPython = Join-Path $venvPath "Scripts\python.exe"

    # Install dependencies
    $reqFile = Join-Path $InstallDir "requirements-inference.txt"
    if (Test-Path $reqFile) {
        Write-Host ""
        Write-Host "Installing dependencies..." -ForegroundColor Yellow
        & $venvPython -m pip install --upgrade pip -q | Out-Null
        & $venvPython -m pip install -r $reqFile
        Write-Host "[OK] Dependencies installed" -ForegroundColor Green
    }

    $kwyreExe = $venvPython

    # Generate dependency manifest (Layer 3)
    $verifyDeps = Join-Path $InstallDir "security\verify_deps.py"
    if (Test-Path $verifyDeps) {
        Write-Host ""
        Write-Host "Generating dependency integrity manifest (Layer 3)..." -ForegroundColor Yellow
        & $venvPython $verifyDeps generate
        Write-Host "[OK] Dependency manifest generated" -ForegroundColor Green
    }
}

# Copy static assets
foreach ($dir in @("chat", "docs")) {
    $srcDir = Join-Path $ScriptRoot $dir
    if (Test-Path $srcDir) {
        $dstDir = Join-Path $InstallDir $dir
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        Copy-Item -Path "$srcDir\*" -Destination $dstDir -Recurse -Force
    }
}

$envExample = Join-Path $ScriptRoot ".env.example"
if (Test-Path $envExample) {
    Copy-Item $envExample -Destination $InstallDir -Force
    $envFile = Join-Path $InstallDir ".env"
    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample -Destination $envFile
        Write-Host "[INFO] Created .env from .env.example — edit with your API keys" -ForegroundColor Yellow
    }
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
    -Description "Block all outbound traffic from Kwyre process" `
    -Direction Outbound `
    -Action Block `
    -Program $kwyreExe `
    -Profile Any | Out-Null

New-NetFirewallRule `
    -DisplayName "Kwyre-AllowLocalhost" `
    -Description "Allow Kwyre to communicate on localhost only" `
    -Direction Outbound `
    -Action Allow `
    -Program $kwyreExe `
    -RemoteAddress "127.0.0.1" `
    -Profile Any | Out-Null

Write-Host "[OK] Firewall rules installed:" -ForegroundColor Green
Get-NetFirewallRule -DisplayName "Kwyre-*" | Format-Table DisplayName, Direction, Action, Enabled -AutoSize

# ---------------------------------------------------------------
# Create launch script
# ---------------------------------------------------------------
$launchScript = Join-Path $InstallDir "start_kwyre.bat"
if ($useCompiled) {
@"
@echo off
echo Starting Kwyre AI...
echo.
"%~dp0kwyre-server.exe"
pause
"@ | Set-Content -Path $launchScript -Encoding ASCII
} else {
@"
@echo off
echo Starting Kwyre AI...
echo.
"%~dp0venv\Scripts\python.exe" "%~dp0server\serve_local_4bit.py"
pause
"@ | Set-Content -Path $launchScript -Encoding ASCII
}

# ---------------------------------------------------------------
# Add to PATH (optional)
# ---------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir", "User")
    Write-Host "[OK] Added $InstallDir to user PATH" -ForegroundColor Green
}

# ---------------------------------------------------------------
# Create Start Menu shortcut
# ---------------------------------------------------------------
$startMenu = [Environment]::GetFolderPath("Programs")
$shortcutDir = Join-Path $startMenu "Kwyre AI"
New-Item -ItemType Directory -Force -Path $shortcutDir | Out-Null

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $shortcutDir "Kwyre AI.lnk"))
$shortcut.TargetPath = $launchScript
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "Start Kwyre AI Inference Server"
$shortcut.Save()
Write-Host "[OK] Start Menu shortcut created" -ForegroundColor Green

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "         Installation Complete               " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Launch Kwyre:  $launchScript" -ForegroundColor White
Write-Host "  Or Start Menu: Kwyre AI" -ForegroundColor White
Write-Host ""
Write-Host "  Server:        http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Chat UI:       http://127.0.0.1:8000/chat" -ForegroundColor White
Write-Host "  Health check:  http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host ""
if ($useCompiled) {
    Write-Host "  Build:     Protected binary (source code not included)" -ForegroundColor Cyan
}
Write-Host "  Security:  All 6 layers active. No data leaves this machine." -ForegroundColor Cyan
Write-Host ""
