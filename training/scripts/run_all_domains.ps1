<#
.SYNOPSIS
    Kwyre AI — Train All 8 Domain Adapters.

.DESCRIPTION
    Runs the full training pipeline for each domain sequentially on a single GPU.
    Total time estimate: ~48-64 hours on H100.
    Total cost estimate: ~$90 API + ~$200 GPU = ~$290.

.EXAMPLE
    $env:ANTHROPIC_API_KEY = 'sk-ant-...'
    .\run_all_domains.ps1
#>

$ErrorActionPreference = 'Stop'

if (-not $env:KWYRE_BASE_MODEL) {
    $env:KWYRE_BASE_MODEL = 'HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive'
}
if (-not $env:KWYRE_TRACES_PER_DOMAIN) {
    $env:KWYRE_TRACES_PER_DOMAIN = '300'
}
$env:PYTHONUNBUFFERED = '1'

$ScriptDir = $PSScriptRoot

$Domains = @(
    'blockchain_crypto'
    'legal_compliance'
    'insurance_actuarial'
    'defense_intelligence'
    'financial_trading'
    'healthcare_lifesciences'
    'sports_analytics'
    'relationship_matching'
)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  KWYRE - All Domain Adapter Training" -ForegroundColor Cyan
Write-Host "  Base model: $env:KWYRE_BASE_MODEL" -ForegroundColor White
Write-Host "  Domains: $($Domains.Count)" -ForegroundColor White
Write-Host "  Traces/domain: $env:KWYRE_TRACES_PER_DOMAIN" -ForegroundColor White
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Cyan

$TotalStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Completed = 0
$Failed = 0

for ($i = 0; $i -lt $Domains.Count; $i++) {
    $domain = $Domains[$i]

    Write-Host ""
    Write-Host ([char]0x2554 + ("=" * 42) + [char]0x2557) -ForegroundColor Magenta
    Write-Host "$([char]0x2551)  Starting domain: $domain" -ForegroundColor Magenta
    Write-Host "$([char]0x2551)  Progress: $($i + 1) / $($Domains.Count)" -ForegroundColor Magenta
    Write-Host ([char]0x255A + ("=" * 42) + [char]0x255D) -ForegroundColor Magenta
    Write-Host ""

    $DomainStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

    $env:KWYRE_DOMAIN = $domain
    try {
        & "$ScriptDir\run_domain_training.ps1"
        $Completed++
        $DomainElapsed = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $DomainStart
        $hours = [math]::Floor($DomainElapsed / 3600)
        $minutes = [math]::Floor(($DomainElapsed % 3600) / 60)
        Write-Host "  [OK] $domain completed in ${hours}h ${minutes}m" -ForegroundColor Green
    }
    catch {
        $Failed++
        Write-Host "  [FAIL] $domain FAILED - continuing to next domain" -ForegroundColor Red
        Write-Host "  Error: $_" -ForegroundColor Red
    }
}

$TotalElapsed = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $TotalStart
$totalHours = [math]::Floor($TotalElapsed / 3600)
$totalMinutes = [math]::Floor(($TotalElapsed % 3600) / 60)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ALL DOMAINS COMPLETE!" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Completed: $Completed / $($Domains.Count)" -ForegroundColor White
Write-Host "  Failed:    $Failed" -ForegroundColor $(if ($Failed -gt 0) { 'Red' } else { 'White' })
Write-Host "  Total time: ${totalHours}h ${totalMinutes}m" -ForegroundColor White
Write-Host ""
Write-Host "  Adapters:" -ForegroundColor White

$adapterBase = Join-Path $HOME '.kwyre\adapters'
if (Test-Path $adapterBase) {
    Get-ChildItem -Path $adapterBase -Directory | ForEach-Object {
        $size = (Get-ChildItem -Path $_.FullName -Recurse -File |
            Measure-Object -Property Length -Sum).Sum
        $sizeMB = [math]::Round($size / 1MB, 1)
        Write-Host "    $($_.Name) (${sizeMB}MB)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "  Copy all adapters to deployment:" -ForegroundColor White
Write-Host "    scp -r ~\.kwyre\adapters\ user@kwyre-server:~/.kwyre/adapters/" -ForegroundColor Gray
Write-Host ""
