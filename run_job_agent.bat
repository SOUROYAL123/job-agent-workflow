@echo off
setlocal
cd /d "%~dp0"
title Cloud Job Agent - one click run

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv not found in this folder. Put this file in the job agent folder.
  pause
  exit /b 1
)
if not exist ".env" (
  echo ERROR: .env not found in this folder.
  pause
  exit /b 1
)

echo ============================================
echo  Cloud Job Agent - started %date% %time%
echo  Close cloud_jobs_backup.xlsx and networking_kit.xlsx in Excel first.
echo ============================================
echo.
echo Finding jobs ^(Indeed, Naukri, Glassdoor, worldwide remote feeds, alert emails^),
echo scoring them, emailing matches, updating your networking kit and follow-up reminders...
echo.

".venv\Scripts\python.exe" auto_runner.py
set RC=%ERRORLEVEL%

echo.
echo ============ LAST RUN STATUS ============
if exist LAST_RUN_STATUS.txt type LAST_RUN_STATUS.txt
echo =========================================

if not "%RC%"=="0" (
  echo.
  echo The run reported a problem ^(exit code %RC%^). Last log lines:
  powershell -NoProfile -Command "Get-Content run_log.txt -Tail 15"
  echo.
  pause
  exit /b %RC%
)

echo.
echo Last lines of the log:
powershell -NoProfile -Command "Get-Content run_log.txt -Tail 12"

if exist cloud_jobs_backup.xlsx start "" "cloud_jobs_backup.xlsx"
if exist networking_kit.xlsx start "" "networking_kit.xlsx"

echo.
echo Done.
echo  - cloud_jobs_backup.xlsx : Top_60_Plus sheet. Check, apply, then note "Applied 26 Oct".
echo  - networking_kit.xlsx    : click recruiter links, send the notes yourself, set Status and Date sent.
echo  - Your email             : job digest, and a reminder when follow-ups are due.
pause
endlocal
