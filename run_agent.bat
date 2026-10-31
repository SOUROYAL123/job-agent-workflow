@echo off
setlocal
cd /d "%~dp0"

set "TASK=JobAgent"
set "TARGET=%~f0"
set "WORKDIR=%~dp0"

if /i "%~1"=="install"   goto install
if /i "%~1"=="uninstall" goto uninstall
if /i "%~1"=="status"    goto status
if /i "%~1"=="scheduled" goto scheduled
goto manual

:install
set "RUNAT=%~2"
if "%RUNAT%"=="" set "RUNAT=09:00"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a=New-ScheduledTaskAction -Execute ([char]34+$env:TARGET+[char]34) -Argument 'scheduled' -WorkingDirectory $env:WORKDIR; $t=New-ScheduledTaskTrigger -Daily -At $env:RUNAT; $s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 3); Register-ScheduledTask -TaskName $env:TASK -Action $a -Trigger $t -Settings $s -Description 'Daily job agent run' -Force | Out-Null"
if errorlevel 1 goto installfail
echo Scheduled "%TASK%" to run daily at %RUNAT%.
echo Missed runs start as soon as possible, and the laptop wakes to run it.
pause
exit /b 0

:installfail
echo [ERROR] Could not create the scheduled task. Try right-click, Run as administrator.
pause
exit /b 1

:uninstall
schtasks /delete /tn "%TASK%" /f
pause
exit /b 0

:status
schtasks /query /tn "%TASK%" /v /fo list
echo.
if exist "LAST_RUN_STATUS.txt" type "LAST_RUN_STATUS.txt"
pause
exit /b 0

:manual
set "MODE="
goto run

:scheduled
set "MODE=--scheduled"
goto run

:run
if not exist ".venv\Scripts\python.exe" goto novenv
if not exist ".env" goto noenv

rem Start Ollama only if it is installed and not already running (used as fallback model)
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" >nul
if errorlevel 1 where ollama >nul 2>nul && start "" /min ollama serve && ping -n 6 127.0.0.1 >nul

rem auto_runner.py already runs job_agent.py, networking_helper.py, followup_reminder.py and weekly_summary.py
".venv\Scripts\python.exe" auto_runner.py %MODE%
set "RC=%errorlevel%"

if "%MODE%"=="" pause
exit /b %RC%

:novenv
echo [ERROR] .venv\Scripts\python.exe not found next to this file.
if "%MODE%"=="" pause
exit /b 1

:noenv
echo [ERROR] .env not found. Copy .env.example to .env and fill in your keys.
if "%MODE%"=="" pause
exit /b 1