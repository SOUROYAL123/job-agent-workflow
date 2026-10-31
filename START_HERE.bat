@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Cloud Job Agent - START HERE
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: .venv not found. Put this file in the job agent folder.
  pause
  exit /b 1
)
if not exist ".env" (
  echo ERROR: .env not found in this folder.
  pause
  exit /b 1
)
for %%F in (job_agent.py auto_runner.py networking_helper.py followup_reminder.py weekly_summary.py remote_feeds.py ats_finder.py) do (
  if not exist "%%F" (
    echo ERROR: missing file %%F - copy all agent files into this folder.
    pause
    exit /b 1
  )
)

echo ================================================
echo  CLOUD JOB AGENT - one-touch run
echo  Started %date% %time%
echo  Close cloud_jobs_backup.xlsx and networking_kit.xlsx in Excel first.
echo ================================================
echo.

REM ---------- one-time setup, runs only on the first launch of this version ----------
if not exist ".setup_v2_done" (
  echo [1/5] First launch: applying recommended settings to .env ...
  if exist apply_recommended_settings.ps1 powershell -NoProfile -ExecutionPolicy Bypass -File apply_recommended_settings.ps1
  echo.
  echo [2/5] Running the offline self-test ...
  "%PY%" test_pipeline.py
  if errorlevel 1 (
    echo.
    echo SELF-TEST FAILED. Nothing was run. Copy the last 20 lines above and send them for help.
    pause
    exit /b 1
  )
  echo done> .setup_v2_done
  echo.
)

REM Run the self-test again any time with:  START_HERE.bat test
if /i "%~1"=="test" (
  echo [test] Running the offline self-test ...
  "%PY%" test_pipeline.py
  if errorlevel 1 (
    echo SELF-TEST FAILED.
    pause
    exit /b 1
  )
)

REM ---------- weekly: find company job feeds and write them into .env ----------
echo [3/5] Company job feeds, refreshed once a week ...
"%PY%" ats_finder.py --apply --weekly
if errorlevel 1 echo Company feed check had a problem. Continuing anyway.
echo.

REM ---------- is the automatic 8:30 AM / 4:30 PM task installed? ----------
echo [4/5] Checking the automatic schedule ...
schtasks /query /tn "CloudJobAgent_AutoPipeline" >nul 2>&1
if errorlevel 1 (
  echo   Automatic schedule NOT found. To create it: open PowerShell as administrator, then run
  echo   cd to this folder and run .\setup_automation.ps1
) else (
  echo   Automatic schedule is active ^(8:30 AM and 4:30 PM^).
)
echo.

REM ---------- the real work ----------
echo [5/5] Finding jobs, scoring them, emailing matches, updating your networking kit,
echo       sending follow-up reminders and the weekly summary. This takes 10 to 20 minutes ...
echo.
"%PY%" auto_runner.py
set RC=%ERRORLEVEL%

echo.
echo ============ LAST RUN STATUS ============
if exist LAST_RUN_STATUS.txt type LAST_RUN_STATUS.txt
echo =========================================

if not "%RC%"=="0" (
  echo.
  echo The run reported a problem, exit code %RC%. Last log lines:
  powershell -NoProfile -Command "Get-Content run_log.txt -Tail 15"
  echo.
  pause
  exit /b %RC%
)

echo.
echo Last lines of the log:
powershell -NoProfile -Command "Get-Content run_log.txt -Tail 15"

if exist cloud_jobs_backup.xlsx start "" "cloud_jobs_backup.xlsx"
if exist networking_kit.xlsx start "" "networking_kit.xlsx"

echo.
echo DONE.
echo  1. cloud_jobs_backup.xlsx : open Top_60_Plus, check the job, apply, then write Applied 26 Oct in the notes column.
echo  2. networking_kit.xlsx    : click recruiter links, send the notes yourself, fill Status and Date sent.
echo  3. Your email             : job digest, follow-up reminders and the weekly summary.
echo.
pause
endlocal
