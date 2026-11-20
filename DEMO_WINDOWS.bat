@echo off
rem Show EconPulse with clearly labelled sample data (no network access).
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Python 3.10 or newer is needed: https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
py -3 main.py --demo --full
endlocal
