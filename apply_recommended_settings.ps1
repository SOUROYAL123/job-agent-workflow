# apply_recommended_settings.ps1
# Run from the job agent folder. Backs up .env, sets broader search terms and a 48-hour freshness window,
# and moves the outdated check_models.py into an old_files folder. Never prints your keys.
# Usage: .\apply_recommended_settings.ps1
Set-Location $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { Write-Host "ERROR: .env not found in this folder."; exit 1 }
Copy-Item $envFile (Join-Path $PSScriptRoot ".env.bak2") -Force

$settings = [ordered]@{
  "SEARCH_QUERIES" = "Cloud Support Engineer AWS|Cloud Support Associate AWS|AWS Implementation Engineer|Technical Support Engineer Cloud SaaS|Cloud Operations NOC Engineer AWS|Junior Cloud Engineer AWS|Managed Services Engineer AWS|Linux Support Engineer|DevOps Support Engineer|Application Support Engineer|Production Support Engineer|Customer Onboarding Specialist|SaaS Implementation Specialist"
  "HOURS_OLD"      = "48"
  "RESULTS_WANTED" = "25"
}

$lines = [System.Collections.Generic.List[string]]([System.IO.File]::ReadAllLines($envFile))
foreach ($key in $settings.Keys) {
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match ("^\s*" + [regex]::Escape($key) + "\s*=")) { $lines[$i] = "$key=$($settings[$key])"; $found = $true }
  }
  if (-not $found) { $lines.Add("$key=$($settings[$key])") }
}
# UTF-8 without BOM so python-dotenv reads the first key correctly
[System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "Updated .env (backup saved as .env.bak2). Current values:"
Select-String -Path $envFile -Pattern '^(SEARCH_QUERIES|HOURS_OLD)=' | ForEach-Object { $_.Line }

if (Test-Path "check_models.py") {
  New-Item -ItemType Directory -Force -Path "old_files" | Out-Null
  Move-Item "check_models.py" "old_files\check_models.py" -Force
  Write-Host "Moved check_models.py to old_files (it tests retired Gemini models)."
}
Write-Host ""
Write-Host "Next: python test_pipeline.py   then double-click run_job_agent.bat"
