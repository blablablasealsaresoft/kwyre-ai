$t = $null
$e = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    'c:\Users\ckthe\kwyre\security\setup_isolation.ps1',
    [ref]$t,
    [ref]$e
)
if ($e.Count -eq 0) {
    Write-Host 'PARSE OK - no syntax errors'
} else {
    Write-Host "PARSE ERRORS: $($e.Count)"
    foreach ($err in $e) {
        Write-Host "  Line $($err.Extent.StartLineNumber): $($err.Message)"
    }
}
