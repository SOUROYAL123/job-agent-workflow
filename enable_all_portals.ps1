# enable_all_portals.ps1
# Run from the job agent folder. Sets SEARCH_SITES in .env, keeps a backup, never prints keys.
# Usage:  .\enable_all_portals.ps1                 (indeed,naukri,glassdoor)
#         .\enable_all_portals.ps1 -WithLinkedIn   (adds linkedin; may return 429 errors)
param([switch]$WithLinkedIn)

Set-Location $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { Write-Host "ERROR: .env not found in this folder."; exit 1 }

Copy-Item $envFile (Join-Path $PSScriptRoot ".env.bak") -Force

$sites = "indeed,naukri,glassdoor"
if ($WithLinkedIn) { $sites = "linkedin,indeed,naukri,glassdoor" }

$lines = [System.IO.File]::ReadAllLines($envFile)
$found = $false
$out = @(foreach ($l in $lines) {
    if ($l -match '^\s*SEARCH_SITES\s*=') { $found = $true; "SEARCH_SITES=$sites" } else { $l }
})
if (-not $found) { $out += "SEARCH_SITES=$sites" }

# UTF-8 without BOM so python-dotenv reads the first key correctly
[System.IO.File]::WriteAllLines($envFile, $out, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Done. Backup saved as .env.bak"
Select-String -Path $envFile -Pattern '^SEARCH_SITES'
Write-Host ""
Write-Host "Next: python job_agent.py --stage scrape"
