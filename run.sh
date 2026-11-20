#!/usr/bin/env sh
# Run EconPulse from source on Linux or macOS (experimental).
# Needs Python 3.10+ with Tk (Debian/Ubuntu: sudo apt install python3-tk).
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi
exec .venv/bin/python main.py "$@"
