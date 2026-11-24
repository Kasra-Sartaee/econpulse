@echo off
rem Run EconPulse from source. The first run creates a private .venv folder here and
rem installs the hash-checked packages from requirements.lock into it, so your own
rem Python installation is never changed.
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Python 3.11 or newer is needed: https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 (
 echo Python 3.11 or newer is needed: https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
rem Reinstall when requirements.lock changed since the last install (after an update).
if exist ".venv\installed.lock" fc /b requirements.lock ".venv\installed.lock" >nul 2>&1 || rmdir /s /q .venv
if not exist ".venv\installed.lock" (
 echo Setting up EconPulse for the first time...
 if exist .venv rmdir /s /q .venv
 py -3 -m venv .venv
 if errorlevel 1 goto :failed
 ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.lock
 if errorlevel 1 goto :failed
 copy /y requirements.lock ".venv\installed.lock" >nul
)
start "" ".venv\Scripts\pythonw.exe" main.py --widget
endlocal
exit /b 0

:failed
if exist .venv rmdir /s /q .venv
echo Could not install the required packages. Check your internet connection and retry.
pause
exit /b 1
