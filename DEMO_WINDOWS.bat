@echo off
rem Show EconPulse with clearly labelled sample data (no network access for the calendar).
rem Uses the same private .venv as RUN_WINDOWS.bat, creating it on the first run.
call "%~dp0RUN_WINDOWS.bat" --demo --full
