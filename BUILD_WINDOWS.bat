@echo off
rem Builds dist\EconPulse\EconPulse.exe and dist\EconPulse-<version>-Windows.zip.
rem Uses a private virtual environment (.build-venv) with hash-checked, pinned
rem tools, so your own Python packages are never changed.
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Python 3.10 or newer is needed to build EconPulse: https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
if not exist ".build-venv\Scripts\python.exe" (
 py -3 -m venv .build-venv
 if errorlevel 1 goto failed
)
".build-venv\Scripts\python.exe" -m pip install --quiet --require-hashes -r requirements-build.lock
if errorlevel 1 (
 echo Could not install the build tools. Check your internet connection.
 goto failed
)
".build-venv\Scripts\python.exe" -m unittest discover -s tests
if errorlevel 1 (
 echo Tests failed; build cancelled.
 goto failed
)
".build-venv\Scripts\python.exe" tools\build_windows.py
if errorlevel 1 (
 echo The build failed. If EconPulse is running, exit it from the tray icon and try again.
 goto failed
)
echo.
echo Keep EconPulse.exe together with its _internal folder. Put the folder in its
echo final place before enabling "Start automatically at login" (moving it later is detected).
pause
endlocal
exit /b 0

:failed
pause
endlocal
exit /b 1
