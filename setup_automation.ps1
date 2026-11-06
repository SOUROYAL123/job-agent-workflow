# Automated launcher for the Cloud Job Agent (Windows Task Scheduler).
#
#   .\setup_automation.ps1                  install / update the schedule (default: 07:30, 11:30, 15:30, 19:30 + catch-up at logon)
#   .\setup_automation.ps1 -Times "08:00","14:00","20:00"
#   .\setup_automation.ps1 -NoLogonCatchup  do not add the run-at-logon catch-up trigger
#   .\setup_automation.ps1 -WakeToRun       wake the laptop from sleep for each run
#   .\setup_automation.ps1 -Status          show next/last run and the last result
#   .\setup_automation.ps1 -RunNow          start a run immediately through the scheduler
#   .\setup_automation.ps1 -Uninstall       remove the scheduled task
#
# Run from an elevated (administrator) PowerShell the first time.

param(
    [string[]]$Times = @("07:30", "11:30", "15:30", "19:30"),
    [switch]$NoLogonCatchup,
    [switch]$WakeToRun,
    [switch]$Status,
    [switch]$RunNow,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$TaskName = "CloudJobAgent_AutoPipeline"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] '$TaskName' removed." -ForegroundColor Green
    return
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "'$TaskName' is NOT installed. Run .\setup_automation.ps1 first." -ForegroundColor Yellow
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Task        : $TaskName ($($task.State))"
    Write-Host "Last run    : $($info.LastRunTime)   (result code $($info.LastTaskResult))"
    Write-Host "Next run    : $($info.NextRunTime)"
    $statusFile = Join-Path $ProjectDir "LAST_RUN_STATUS.txt"
    if (Test-Path $statusFile) {
        Write-Host ""
        Get-Content $statusFile
    }
    return
}

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "[OK] Run started. Follow it with:  Get-Content '$ProjectDir\run_log.txt' -Tail 30 -Wait"
    return
}

# ---------- install / update ----------
$PythonConsole = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$PythonW = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $PythonConsole)) {
    Write-Host "Creating virtual environment (.venv) ..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -m venv (Join-Path $ProjectDir ".venv")
    } else {
        & python -m venv (Join-Path $ProjectDir ".venv")
    }
    if (-not (Test-Path $PythonConsole)) {
        Write-Error "Could not create .venv. Install Python 3.11+ and re-run."
    }
}

Write-Host "Installing dependencies ..."
& $PythonConsole -m pip install --quiet --upgrade pip
& $PythonConsole -m pip install --quiet -r (Join-Path $ProjectDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed. Fix the error above and re-run." }

Write-Host "Running self-tests ..."
Push-Location $ProjectDir
try {
    & $PythonConsole test_units.py
    if ($LASTEXITCODE -ne 0) { Write-Error "test_units.py failed; schedule NOT installed." }
    & $PythonConsole test_pipeline.py
    if ($LASTEXITCODE -ne 0) { Write-Error "test_pipeline.py failed; schedule NOT installed." }
    & $PythonConsole test_search_profile.py
    if ($LASTEXITCODE -ne 0) { Write-Error "test_search_profile.py failed; schedule NOT installed." }
} finally {
    Pop-Location
}

$EnvFile = Join-Path $ProjectDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env not found. Copy .env.example to .env and fill in your keys, otherwise runs will fail."
} else {
    $geminiLine = Select-String -Path $EnvFile -Pattern '^\s*GEMINI_API_KEY\s*=' | Select-Object -First 1
    if (-not $geminiLine -or $geminiLine.Line -match 'your_|=\s*$') {
        Write-Warning "GEMINI_API_KEY in .env looks empty or still a placeholder; scoring will fail."
    }
}

if (Test-Path $PythonW) { $ExePath = $PythonW } else { $ExePath = $PythonConsole }
$RunnerPath = Join-Path $ProjectDir "auto_runner.py"
if (-not (Test-Path $RunnerPath)) {
    Write-Error "auto_runner.py not found in $ProjectDir."
}

# Manual on-demand launcher (double-click)
$BatLines = @(
    "@echo off",
    "cd /d `"%~dp0`"",
    "`".venv\Scripts\python.exe`" auto_runner.py",
    "pause"
)
Set-Content -Path (Join-Path $ProjectDir "run_daily.bat") -Value ($BatLines -join "`r`n") -Encoding ASCII

$Action = New-ScheduledTaskAction `
    -Execute $ExePath `
    -Argument "`"$RunnerPath`" --scheduled" `
    -WorkingDirectory $ProjectDir

$TimeTriggers = @()
foreach ($t in $Times) {
    $TimeTriggers += New-ScheduledTaskTrigger -Daily -At $t
}

$settingsArgs = @{
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    StartWhenAvailable         = $true
    RunOnlyIfNetworkAvailable  = $true
    ExecutionTimeLimit         = (New-TimeSpan -Hours 2)
    MultipleInstances          = "IgnoreNew"
}
if ($WakeToRun) { $settingsArgs["WakeToRun"] = $true }
$Settings = New-ScheduledTaskSettingsSet @settingsArgs

$Description = "Automated Cloud Job Agent: scrapes job boards and company feeds, reads Gmail alerts, scores with Gemini, syncs Excel notes and emails top matches."

$withLogon = -not $NoLogonCatchup
$registered = $false
if ($withLogon) {
    try {
        $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $LogonTrigger.Delay = "PT3M"
        Register-ScheduledTask -TaskName $TaskName -Action $Action `
            -Trigger (@($TimeTriggers) + $LogonTrigger) -Settings $Settings `
            -Description $Description -Force | Out-Null
        $registered = $true
    } catch {
        Write-Warning "Could not add the logon catch-up trigger ($($_.Exception.Message)). Installing the timed triggers only."
        $withLogon = $false
    }
}
if (-not $registered) {
    Register-ScheduledTask -TaskName $TaskName -Action $Action `
        -Trigger $TimeTriggers -Settings $Settings `
        -Description $Description -Force | Out-Null
}

Write-Host ""
Write-Host "[SUCCESS] '$TaskName' is now active!" -ForegroundColor Green
Write-Host "  - Schedule   : $($Times -join ', ') daily"
if ($withLogon) {
    Write-Host "  - Catch-up   : also runs ~3 min after you log in (skipped if a run finished recently)"
}
Write-Host "  - Missed runs: start when the laptop is back on and online"
Write-Host "  - Time limit : 2 hours per run, never two runs at once"
Write-Host "  - Status     : .\setup_automation.ps1 -Status"
Write-Host "  - Run now    : .\setup_automation.ps1 -RunNow"
Write-Host "  - Status file: $ProjectDir\LAST_RUN_STATUS.txt"
Write-Host "  - Full log   : $ProjectDir\run_log.txt"
