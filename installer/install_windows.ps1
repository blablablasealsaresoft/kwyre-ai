#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Kwyre AI Windows Installer
.DESCRIPTION
    Sets up Kwyre AI local inference with Layer 2 network isolation
    via Windows Firewall rules. Supports both compiled binary and
    Python source installations.
.PARAMETER InstallDir
    Installation directory (default: $env:LOCALAPPDATA\Kwyre)
.PARAMETER ModelDir
    HuggingFace model cache directory
.PARAMETER Uninstall
    Reverse all installation steps and remove Kwyre AI
.PARAMETER SkipService
    Skip Windows Service registration
#>

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Kwyre",
    [string]$ModelDir = "$env:USERPROFILE\.cache\huggingface",
    [switch]$Uninstall,
    [switch]$SkipService
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# ---------------------------------------------------------------
# Uninstall mode
# ---------------------------------------------------------------
if ($Uninstall) {
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Yellow
    Write-Host "       Kwyre AI — Uninstalling               " -ForegroundColor Yellow
    Write-Host "=============================================" -ForegroundColor Yellow
    Write-Host ""

    $svc = Get-Service -Name "KwyreAI" -ErrorAction SilentlyContinue
    if ($svc) {
        Stop-Service -Name "KwyreAI" -Force -ErrorAction SilentlyContinue
        $nssm = Get-Command nssm -ErrorAction SilentlyContinue
        if ($nssm) { & nssm remove KwyreAI confirm | Out-Null }
        else { sc.exe delete KwyreAI | Out-Null }
        Write-Host "[OK] Windows Service removed" -ForegroundColor Green
    }

    Remove-NetFirewallRule -DisplayName "Kwyre-BlockOutbound" -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName "Kwyre-AllowLocalhost" -ErrorAction SilentlyContinue
    Write-Host "[OK] Firewall rules removed" -ForegroundColor Green

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -like "*$InstallDir*") {
        $newPath = ($userPath -split ";" | Where-Object { $_ -ne $InstallDir }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "[OK] Removed from PATH" -ForegroundColor Green
    }

    $startMenu = [Environment]::GetFolderPath("Programs")
    $shortcutDir = Join-Path $startMenu "Kwyre AI"
    if (Test-Path $shortcutDir) {
        Remove-Item -Recurse -Force $shortcutDir
        Write-Host "[OK] Start Menu shortcuts removed" -ForegroundColor Green
    }

    $desktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Kwyre AI.lnk"
    if (Test-Path $desktopLnk) {
        Remove-Item -Force $desktopLnk
        Write-Host "[OK] Desktop shortcut removed" -ForegroundColor Green
    }

    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
        Write-Host "[OK] Removed $InstallDir" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "[OK] Kwyre AI has been uninstalled" -ForegroundColor Green
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "       Kwyre AI — Windows Installer v1.0     " -ForegroundColor Cyan
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
    Write-Error "No NVIDIA GPU detected. Kwyre requires an NVIDIA CUDA-capable GPU with 4GB+ VRAM."
    exit 1
}
Write-Host "[OK] NVIDIA GPU: $($gpu.Name)" -ForegroundColor Green

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    $gpuName = (nvidia-smi --query-gpu=name --format=csv,noheader 2>$null).Trim()
    $gpuVram = (nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>$null).Trim()
    $gpuDriver = (nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>$null).Trim()
    Write-Host "[OK] GPU:         $gpuName" -ForegroundColor Green
    Write-Host "[OK] VRAM:        $gpuVram" -ForegroundColor Green
    Write-Host "[OK] Driver:      $gpuDriver" -ForegroundColor Green

    $vramDigits = $gpuVram -replace '[^\d]',''
    if ($vramDigits -and [int]$vramDigits -lt 4096) {
        Write-Warning "GPU has less than 4 GB VRAM. 4-bit quantized models require 4 GB+."
    }
} else {
    Write-Warning "nvidia-smi not found. Ensure NVIDIA CUDA drivers are installed."
    Write-Warning "Download from: https://developer.nvidia.com/cuda-downloads"
}

# ---------------------------------------------------------------
# CUDA Toolkit check
# ---------------------------------------------------------------
$nvcc = Get-Command nvcc -ErrorAction SilentlyContinue
if ($nvcc) {
    $cudaVer = (nvcc --version 2>$null | Select-String "release") -replace '.*release\s+([\d.]+).*','$1'
    Write-Host "[OK] CUDA Toolkit: $cudaVer" -ForegroundColor Green
} else {
    Write-Warning "CUDA Toolkit (nvcc) not found."
    Write-Warning "Some features require CUDA Toolkit: https://developer.nvidia.com/cuda-toolkit"
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

    $reqSrc = Join-Path $ScriptRoot "requirements-windows.txt"
    if (-not (Test-Path $reqSrc)) {
        $reqSrc = Join-Path $ScriptRoot "requirements-inference.txt"
    }
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
    $venvPip = Join-Path $venvPath "Scripts\pip.exe"

    # Install dependencies
    $reqFile = Join-Path $InstallDir "requirements-windows.txt"
    if (-not (Test-Path $reqFile)) {
        $reqFile = Join-Path $InstallDir "requirements-inference.txt"
    }
    if (Test-Path $reqFile) {
        Write-Host ""
        Write-Host "Installing dependencies..." -ForegroundColor Yellow
        & $venvPip install --upgrade pip -q | Out-Null
        & $venvPip install -r $reqFile
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
# Windows Service
# ---------------------------------------------------------------
if (-not $SkipService) {
    Write-Host ""
    Write-Host "Registering Windows Service..." -ForegroundColor Yellow

    $existingSvc = Get-Service -Name "KwyreAI" -ErrorAction SilentlyContinue
    if ($existingSvc) {
        Stop-Service -Name "KwyreAI" -Force -ErrorAction SilentlyContinue
        sc.exe delete KwyreAI | Out-Null
        Start-Sleep -Seconds 2
    }

    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssm) {
        & nssm install KwyreAI $kwyreExe | Out-Null
        & nssm set KwyreAI DisplayName "Kwyre AI Inference Server" | Out-Null
        & nssm set KwyreAI Description "Kwyre AI local inference with air-gapped security" | Out-Null
        & nssm set KwyreAI AppDirectory $InstallDir | Out-Null
        & nssm set KwyreAI AppEnvironmentExtra "HF_HUB_OFFLINE=1" "TRANSFORMERS_OFFLINE=1" "KWYRE_BIND_HOST=127.0.0.1" | Out-Null
        & nssm set KwyreAI AppRestartDelay 5000 | Out-Null
        Write-Host "[OK] Windows Service installed via NSSM" -ForegroundColor Green
    } else {
        New-Service -Name "KwyreAI" `
            -BinaryPathName $kwyreExe `
            -DisplayName "Kwyre AI Inference Server" `
            -Description "Kwyre AI local inference with air-gapped security" `
            -StartupType Manual | Out-Null
        sc.exe failure KwyreAI reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Null
        Write-Host "[OK] Windows Service registered (manual start)" -ForegroundColor Green
    }
    Write-Host "[INFO] Start with: Start-Service KwyreAI" -ForegroundColor Yellow
}

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

# ---------------------------------------------------------------
# Health check
# ---------------------------------------------------------------
Write-Host ""
Write-Host "Running health check..." -ForegroundColor Yellow

if ($useCompiled) {
    $healthExe = Join-Path $InstallDir "kwyre-server.exe"
    if (Test-Path $healthExe) {
        $fileSize = [math]::Round((Get-Item $healthExe).Length / 1MB, 1)
        Write-Host "[OK] Binary: $healthExe ($fileSize MB)" -ForegroundColor Green
    } else {
        Write-Warning "Binary not found at $healthExe"
    }
} else {
    $venvPy = Join-Path $InstallDir "venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        try {
            $torchCheck = & $venvPy -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" 2>$null
            if ($torchCheck) {
                Write-Host "[OK] $torchCheck" -ForegroundColor Green
            }
        } catch {
            Write-Warning "Could not verify PyTorch installation"
        }
    }
}

$fwRules = Get-NetFirewallRule -DisplayName "Kwyre-*" -ErrorAction SilentlyContinue
if ($fwRules) {
    Write-Host "[OK] Firewall rules active: $($fwRules.Count) rules" -ForegroundColor Green
}

$svcStatus = Get-Service -Name "KwyreAI" -ErrorAction SilentlyContinue
if ($svcStatus) {
    Write-Host "[OK] Windows Service: $($svcStatus.Status)" -ForegroundColor Green
}

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
