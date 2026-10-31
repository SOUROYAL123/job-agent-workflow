$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

$PythonW = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$PythonConsole = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (Test-Path $PythonW) {
    $ExePath = $PythonW
} elseif (Test-Path $PythonConsole) {
    $ExePath = $PythonConsole
} else {
    Write-Error "Virtual environment python not found at $PythonConsole"
}

$RunnerPath = Join-Path $ProjectDir "auto_runner.py"
if (-not (Test-Path $RunnerPath)) {
    Write-Error "auto_runner.py not found in $ProjectDir. Save Step 1 first."
}

# Create/update run_daily.bat for manual on-demand runs
$BatLines = @(
    "@echo off",
    "cd /d `"%~dp0`"",
    "`".venv\Scripts\python.exe`" auto_runner.py",
    "pause"
)
Set-Content -Path (Join-Path $ProjectDir "run_daily.bat") -Value ($BatLines -join "`r`n") -Encoding ASCII

$TaskName = "CloudJobAgent_AutoPipeline"
$Action = New-ScheduledTaskAction `
    -Execute $ExePath `
    -Argument "`"$RunnerPath`" --scheduled" `
    -WorkingDirectory $ProjectDir

$TriggerMorning = New-ScheduledTaskTrigger -Daily -At "08:30AM"
$TriggerAfternoon = New-ScheduledTaskTrigger -Daily -At "04:30PM"

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($TriggerMorning, $TriggerAfternoon) `
    -Settings $Settings `
    -Description "Automated Cloud Job Agent: scrapes portals, reads Gmail alerts, scores via Gemini, syncs Excel notes, and emails top matches." `
    -Force | Out-Null

Write-Host ""
Write-Host "[SUCCESS] '$TaskName' is now active!" -ForegroundColor Green
Write-Host "  - Schedule   : 8:30 AM & 4:30 PM daily (plus auto-catchup when laptop turns on)"
Write-Host "  - Mode       : 100% silent background execution (no pop-up windows)"
Write-Host "  - Power      : Works on both charger and battery"
Write-Host "  - Status file: $ProjectDir\LAST_RUN_STATUS.txt"
Write-Host "  - Full log   : $ProjectDir\run_log.txt"