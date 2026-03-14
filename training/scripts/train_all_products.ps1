<#
.SYNOPSIS
    Kwyre AI — Train All Product Adapters (Batch Pipeline).

.DESCRIPTION
    Trains domain adapters for all 9 Mint Rail products:
    1. Scrapes GitHub repos for training context
    2. Generates 13,000 traces via Anthropic Batch API (50% cheaper)
    3. Trains distillation + GRPO for each domain

    Cost: ~$310-400 API + ~$400 GPU = ~$710-800
    Time: ~120-160 hours on H100 (5000 traces per domain)

.EXAMPLE
    $env:ANTHROPIC_API_KEY = 'sk-ant-...'
    .\train_all_products.ps1
#>

$ErrorActionPreference = 'Stop'

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Host "ERROR: ANTHROPIC_API_KEY not set." -ForegroundColor Red
    Write-Host "  `$env:ANTHROPIC_API_KEY = 'sk-ant-...'" -ForegroundColor Yellow
    exit 1
}

if (-not $env:KWYRE_BASE_MODEL) {
    $env:KWYRE_BASE_MODEL = 'HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive'
}
if (-not $env:KWYRE_TRACES_PER_DOMAIN) {
    $env:KWYRE_TRACES_PER_DOMAIN = '5000'
}
$env:PYTHONUNBUFFERED = '1'

$ScriptDir = $PSScriptRoot
$LogDir = Join-Path $HOME '.kwyre\logs'
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  KWYRE - Product Adapter Batch Training" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Base model:       $env:KWYRE_BASE_MODEL" -ForegroundColor White
Write-Host "  Traces/domain:    $env:KWYRE_TRACES_PER_DOMAIN" -ForegroundColor White
Write-Host "  Total domains:    13" -ForegroundColor White
Write-Host ""

$nvSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvSmi) {
    & nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
}

# ── STEP 1: Scrape repos ─────────────────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  STEP 1: Scraping GitHub repos for training context" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

try {
    python "$ScriptDir\scrape_repos.py" 2>&1 |
        Tee-Object -FilePath (Join-Path $LogDir '00-scrape-repos.log')
    Write-Host "  Scraping complete." -ForegroundColor Green
}
catch {
    Write-Host "  WARNING: Repo scraping failed - continuing without enrichment." -ForegroundColor Yellow
}

# ── STEP 2: Batch trace generation ───────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  STEP 2: Generating traces (Anthropic Batch API)" -ForegroundColor Cyan
Write-Host "  Target: $env:KWYRE_TRACES_PER_DOMAIN traces x 13 domains" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan

python "$ScriptDir\generate_traces_batch.py" 2>&1 |
    Tee-Object -FilePath (Join-Path $LogDir '01-batch-traces.log')

Write-Host "`n  Traces complete.`n" -ForegroundColor Green

# ── STEP 3: Train each domain ────────────────────────────────────────────────
$Domains = @(
    'financial_trading'
    'software_engineering'
    'scientific_research'
    'dental_clinical'
    'legal_compliance'
    'career_placement'
    'relationship_matching'
    'sports_analytics'
    'college_basketball'
    'insurance_actuarial'
    'healthcare_lifesciences'
    'defense_intelligence'
    'blockchain_crypto'
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  STEP 3: Training $($Domains.Count) domain adapters" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$TotalStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Completed = 0
$Failed = 0

for ($i = 0; $i -lt $Domains.Count; $i++) {
    $domain = $Domains[$i]
    $idx = $i + 1

    Write-Host "`n========================================" -ForegroundColor Magenta
    Write-Host "  [$idx/$($Domains.Count)] Training: $domain" -ForegroundColor Magenta
    Write-Host "  $(Get-Date)" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Magenta

    $DomainStart = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $env:KWYRE_DOMAIN = $domain

    try {
        Write-Host "  [distillation] Starting..." -ForegroundColor White
        python "$ScriptDir\train_distillation.py" 2>&1 |
            Tee-Object -FilePath (Join-Path $LogDir "$domain-distillation.log")

        Write-Host "  [grpo] Starting..." -ForegroundColor White
        python "$ScriptDir\train_grpo_domain.py" 2>&1 |
            Tee-Object -FilePath (Join-Path $LogDir "$domain-grpo.log")

        $Completed++
        $elapsed = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $DomainStart
        $h = [math]::Floor($elapsed / 3600)
        $m = [math]::Floor(($elapsed % 3600) / 60)
        Write-Host "  [OK] $domain completed in ${h}h ${m}m" -ForegroundColor Green
    }
    catch {
        $Failed++
        Write-Host "  [FAIL] $domain FAILED - $_" -ForegroundColor Red
    }
}

$TotalElapsed = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - $TotalStart
$totalH = [math]::Floor($TotalElapsed / 3600)
$totalM = [math]::Floor(($TotalElapsed % 3600) / 60)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  PRODUCT BATCH TRAINING COMPLETE!" -ForegroundColor Cyan
Write-Host "  $(Get-Date)" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Completed: $Completed / $($Domains.Count)" -ForegroundColor White
Write-Host "  Failed:    $Failed" -ForegroundColor $(if ($Failed -gt 0) { 'Red' } else { 'White' })
Write-Host "  Total time: ${totalH}h ${totalM}m" -ForegroundColor White
Write-Host ""
Write-Host "  Product -> Adapter mapping:" -ForegroundColor White
Write-Host "    QuantEdge       -> financial-trading" -ForegroundColor Gray
Write-Host "    CodeForge       -> software-engineering" -ForegroundColor Gray
Write-Host "    LabMind         -> scientific-research" -ForegroundColor Gray
Write-Host "    DentAI          -> dental-clinical" -ForegroundColor Gray
Write-Host "    TaxShield       -> legal-compliance" -ForegroundColor Gray
Write-Host "    LaunchPad       -> career-placement" -ForegroundColor Gray
Write-Host "    SoulSync        -> relationship-matching" -ForegroundColor Gray
Write-Host "    NFL PlayCaller  -> sports-analytics" -ForegroundColor Gray
Write-Host "    MarchMind       -> college-basketball" -ForegroundColor Gray
Write-Host ""

$adapterBase = Join-Path $HOME '.kwyre\adapters'
if (Test-Path $adapterBase) {
    Write-Host "  Adapters:" -ForegroundColor White
    Get-ChildItem -Path $adapterBase -Directory | ForEach-Object {
        $size = (Get-ChildItem -Path $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        $sizeMB = [math]::Round($size / 1MB, 1)
        Write-Host "    $($_.Name) (${sizeMB}MB)" -ForegroundColor Gray
    }
}
Write-Host ""
