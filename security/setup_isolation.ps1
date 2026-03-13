#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Kwyre Layer 2: Process Network Isolation for Windows.

.DESCRIPTION
    Prevents the Kwyre inference server from making ANY outbound connections,
    even if the process is compromised.

    Creates a restricted local user "kwyre" and Windows Firewall rules that
    block all outbound traffic from the kwyre executable except loopback.

.PARAMETER Uninstall
    Remove all Kwyre firewall rules and the kwyre local user.

.PARAMETER Status
    Show current Kwyre firewall rules, user status, and running processes.

.PARAMETER KwyreExePath
    Path to the kwyre server executable.
    Default: $env:LOCALAPPDATA\Kwyre\kwyre-server.exe

.EXAMPLE
    .\setup_isolation.ps1
    Installs firewall rules and creates the kwyre user.

.EXAMPLE
    .\setup_isolation.ps1 -Status
    Shows current isolation status.

.EXAMPLE
    .\setup_isolation.ps1 -Uninstall
    Removes all isolation rules and the kwyre user.
#>

param(
    [switch]$Uninstall,
    [switch]$Status,
    [string]$KwyreExePath = "$env:LOCALAPPDATA\Kwyre\kwyre-server.exe"
)

$ErrorActionPreference = 'Stop'

$KwyreUser = 'kwyre'
$RulePrefix = 'Kwyre'
$BlockRuleName = "$RulePrefix-BlockOutbound"
$AllowLoopbackName = "$RulePrefix-AllowLoopback"

function Install-KwyreIsolation {
    Write-Host "`n[Layer 2] Installing Windows network isolation..." -ForegroundColor Cyan

    # --- Create restricted local user ---
    try {
        $null = Get-LocalUser -Name $KwyreUser -ErrorAction Stop
        Write-Host "[Layer 2] User '$KwyreUser' already exists." -ForegroundColor Yellow
    }
    catch {
        $securePass = ConvertTo-SecureString -String ([guid]::NewGuid().ToString()) -AsPlainText -Force
        New-LocalUser -Name $KwyreUser `
            -Password $securePass `
            -Description 'Kwyre restricted service account — no interactive logon' `
            -AccountNeverExpires `
            -UserMayNotChangePassword | Out-Null

        Disable-LocalUser -Name $KwyreUser
        Write-Host "[Layer 2] Created restricted user: $KwyreUser (disabled for logon)" -ForegroundColor Green
    }

    # --- Validate executable path ---
    if (-not (Test-Path $KwyreExePath)) {
        Write-Host "[Layer 2] WARNING: Executable not found at $KwyreExePath" -ForegroundColor Yellow
        Write-Host "[Layer 2] Firewall rules will be created anyway — they activate once the exe exists." -ForegroundColor Yellow
    }

    # --- Remove old rules if present ---
    Remove-NetFirewallRule -DisplayName $BlockRuleName -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName $AllowLoopbackName -ErrorAction SilentlyContinue

    # --- Block ALL outbound from the kwyre executable ---
    New-NetFirewallRule `
        -DisplayName $BlockRuleName `
        -Description 'Kwyre Layer 2: Block all outbound traffic from kwyre-server' `
        -Direction Outbound `
        -Action Block `
        -Program $KwyreExePath `
        -Profile Any `
        -Enabled True | Out-Null

    Write-Host "[Layer 2] Firewall rule created: $BlockRuleName (block all outbound)" -ForegroundColor Green

    # --- Allow loopback (127.0.0.1) only ---
    New-NetFirewallRule `
        -DisplayName $AllowLoopbackName `
        -Description 'Kwyre Layer 2: Allow outbound to localhost only' `
        -Direction Outbound `
        -Action Allow `
        -Program $KwyreExePath `
        -RemoteAddress '127.0.0.1' `
        -Profile Any `
        -Enabled True | Out-Null

    Write-Host "[Layer 2] Firewall rule created: $AllowLoopbackName (allow 127.0.0.1)" -ForegroundColor Green

    # --- Create launcher script ---
    $launcherPath = Join-Path (Split-Path $KwyreExePath) 'Start-Kwyre.ps1'
    $launcherContent = @"
#Requires -RunAsAdministrator
# Kwyre server launcher — runs inference process under the restricted kwyre user
`$exePath = '$KwyreExePath'
`$credential = New-Object System.Management.Automation.PSCredential('.\$KwyreUser', (New-Object System.Security.SecureString))
Start-Process -FilePath `$exePath -Credential `$credential -NoNewWindow -Wait @args
"@
    Set-Content -Path $launcherPath -Value $launcherContent -Encoding UTF8
    Write-Host "[Layer 2] Launcher created: $launcherPath" -ForegroundColor Green

    Write-Host "`n[Layer 2] Installation complete." -ForegroundColor Cyan
    Write-Host "[Layer 2] All outbound blocked except 127.0.0.1 for:" -ForegroundColor Cyan
    Write-Host "          $KwyreExePath" -ForegroundColor White
    Write-Host ""
}

function Show-KwyreStatus {
    Write-Host "`n[Layer 2] Kwyre Isolation Status" -ForegroundColor Cyan
    Write-Host ("=" * 50) -ForegroundColor DarkGray

    # --- Firewall rules ---
    Write-Host "`nFirewall Rules:" -ForegroundColor White
    $rules = Get-NetFirewallRule -DisplayName "$RulePrefix-*" -ErrorAction SilentlyContinue
    if ($rules) {
        $rules | Format-Table DisplayName, Direction, Action, Enabled -AutoSize
    }
    else {
        Write-Host "  (no Kwyre firewall rules found)" -ForegroundColor Yellow
    }

    # --- User ---
    Write-Host "Service User:" -ForegroundColor White
    try {
        $user = Get-LocalUser -Name $KwyreUser -ErrorAction Stop
        Write-Host "  User '$KwyreUser' exists (Enabled: $($user.Enabled))" -ForegroundColor Green
    }
    catch {
        Write-Host "  User '$KwyreUser' does not exist" -ForegroundColor Yellow
    }

    # --- Process ---
    Write-Host "`nRunning Processes:" -ForegroundColor White
    $procs = Get-Process -Name 'kwyre-server' -ErrorAction SilentlyContinue
    if ($procs) {
        $procs | Format-Table Id, ProcessName, StartTime, CPU -AutoSize
    }
    else {
        Write-Host "  (no kwyre-server processes running)" -ForegroundColor Yellow
    }

    Write-Host ""
}

function Uninstall-KwyreIsolation {
    Write-Host "`n[Layer 2] Removing Windows network isolation..." -ForegroundColor Cyan

    # --- Remove firewall rules ---
    $removed = 0
    foreach ($name in @($BlockRuleName, $AllowLoopbackName)) {
        try {
            Remove-NetFirewallRule -DisplayName $name -ErrorAction Stop
            Write-Host "[Layer 2] Removed firewall rule: $name" -ForegroundColor Green
            $removed++
        }
        catch {
            Write-Host "[Layer 2] Rule not found: $name" -ForegroundColor Yellow
        }
    }

    # --- Remove local user ---
    try {
        Remove-LocalUser -Name $KwyreUser -ErrorAction Stop
        Write-Host "[Layer 2] Removed user: $KwyreUser" -ForegroundColor Green
    }
    catch {
        Write-Host "[Layer 2] User '$KwyreUser' not found or already removed." -ForegroundColor Yellow
    }

    # --- Remove launcher ---
    $launcherPath = Join-Path (Split-Path $KwyreExePath) 'Start-Kwyre.ps1'
    if (Test-Path $launcherPath) {
        Remove-Item $launcherPath -Force
        Write-Host "[Layer 2] Removed launcher: $launcherPath" -ForegroundColor Green
    }

    Write-Host "`n[Layer 2] Uninstall complete ($removed firewall rules removed)." -ForegroundColor Cyan
    Write-Host ""
}

# --- Main dispatch ---
if ($Status) {
    Show-KwyreStatus
}
elseif ($Uninstall) {
    Uninstall-KwyreIsolation
}
else {
    Install-KwyreIsolation
}
