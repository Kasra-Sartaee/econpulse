@echo off
rem Run EconPulse from source (installs the few runtime packages if missing).
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Python 3.11 or newer is needed: https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
py -3 -c "import PIL, pystray, tzlocal, tzdata" >nul 2>&1
if errorlevel 1 (
 py -3 -m pip install -r requirements.txt
 if errorlevel 1 (
  echo Could not install the required packages. Check your internet connection and retry.
  pause
  exit /b 1
 )
)
where pyw >nul 2>&1
if errorlevel 1 (
 py -3 main.py --widget
) else (
 start "" pyw -3 main.py --widget
)
endlocal
