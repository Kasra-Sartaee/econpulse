"""Shared test helpers. Importing this module also makes the repository root
importable, so the tests run from any working directory."""

from datetime import UTC, datetime
import gc
import logging
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)

# Expected failures are logged by the code under test; keep test output quiet.
logging.getLogger('econpulse').addHandler(logging.NullHandler())
logging.getLogger('econpulse').propagate = False


def collect_tk_garbage():
    """Free destroyed Tk roots now, on the main thread.

    A destroyed root can linger in a reference cycle. If the garbage collector
    later runs on a worker thread (biquote fetches in parallel, the app fetches
    in the background), Tcl aborts the whole process with "Tcl_AsyncDelete:
    async handler deleted by the wrong thread". Call this after dropping the
    last reference to a root, and before tests that start threads.
    """
    gc.collect()


def tk_root(withdraw=True):
    """A Tk root, or skip the test where no display is available (headless CI)."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise unittest.SkipTest(f'Tk unavailable: {exc}') from None
    if withdraw:
        root.withdraw()
    return root
