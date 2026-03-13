<#
.SYNOPSIS
    Kwyre AI — Package Adapter for CDN Upload.

.DESCRIPTION
    Zips a trained adapter directory, computes SHA-256, and prints the manifest
    entry to paste into chat/adapters/manifest.json.

.PARAMETER Domain
    Domain name (e.g. blockchain_crypto, legal_compliance).

.PARAMETER Version
    Semantic version string (e.g. 1.0.0).

.PARAMETER ModelTier
    Model tier: 4b (default) or 9b.

.EXAMPLE
    .\package_adapter.ps1 -Domain blockchain_crypto -Version 1.0.0

.EXAMPLE
    .\package_adapter.ps1 -Domain legal_compliance -Version 2.1.0 -ModelTier 9b
#>

param(
    [Parameter(Mandatory)]
    [string]$Domain,

    [Parameter(Mandatory)]
    [string]$Version,

    [string]$ModelTier = '4b'
)

$ErrorActionPreference = 'Stop'

$DomainHyphenated = $Domain -replace '_', '-'
$DomainUnderscored = $Domain -replace '-', '_'

$AdapterDir = $null
$AdapterBase = $null

$candidates = @(
    Join-Path $HOME ".kwyre\adapters\$DomainHyphenated"
    Join-Path $HOME ".kwyre\adapters\$DomainHyphenated-$ModelTier"
    Join-Path $HOME ".kwyre\lora-adapters\$DomainUnderscored-distilled-$ModelTier"
)

foreach ($candidate in $candidates) {
    if (Test-Path $candidate -PathType Container) {
        $AdapterDir = $candidate
        $AdapterBase = Split-Path $candidate -Leaf
        break
    }
}

if (-not $AdapterDir) {
    Write-Host "ERROR: Adapter directory not found. Searched:" -ForegroundColor Red
    foreach ($candidate in $candidates) {
        Write-Host "  - $candidate" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "Run training first: `$env:KWYRE_DOMAIN='$Domain'; .\training\scripts\run_domain_training.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found adapter: $AdapterDir" -ForegroundColor Green

$OutputDir = Join-Path $HOME '.kwyre\adapter-packages'
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ZipName = "$DomainHyphenated-$ModelTier-v$Version.zip"
$ZipPath = Join-Path $OutputDir $ZipName

Write-Host "Packaging $AdapterDir -> $ZipPath ..." -ForegroundColor White

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path "$AdapterDir\*" -DestinationPath $ZipPath

$zipSize = (Get-Item $ZipPath).Length
$sizeMB = [math]::Round($zipSize / 1MB, 1)
Write-Host "Done: ${sizeMB}MB" -ForegroundColor Green

$SHA = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
$CdnUrl = "https://cdn.kwyre.com/adapters/$ZipName"

Write-Host ""
$border = [string]::new([char]0x2550, 60)
Write-Host $border -ForegroundColor Cyan
Write-Host "  SHA-256: $SHA" -ForegroundColor White
Write-Host "  Upload:  $ZipPath" -ForegroundColor White
Write-Host ""
Write-Host "  Paste into chat/adapters/manifest.json:" -ForegroundColor White
Write-Host ""
Write-Host "  `"$DomainHyphenated`": {" -ForegroundColor Gray
Write-Host "    `"version`": `"$Version`"," -ForegroundColor Gray
Write-Host "    `"url`": `"$CdnUrl`"," -ForegroundColor Gray
Write-Host "    `"sha256`": `"$SHA`"," -ForegroundColor Gray
Write-Host "    `"model_tier`": `"$ModelTier`"" -ForegroundColor Gray
Write-Host "  }" -ForegroundColor Gray
Write-Host ""
Write-Host "  Then redeploy:" -ForegroundColor White
Write-Host "    npx wrangler pages deploy chat/ --project-name kwyre-ai" -ForegroundColor Gray
Write-Host $border -ForegroundColor Cyan
