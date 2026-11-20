"""Entry point: ``python -m econpulse`` (also used by the packaged app)."""

from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import messagebox

from . import __version__, system, theme
from .app import EconPulse


def main():
    parser = argparse.ArgumentParser(prog='econpulse', description='Economic calendar for your desktop.')
    parser.add_argument('--demo', action='store_true', help='show clearly labelled sample data (no network)')
    view = parser.add_mutually_exclusive_group()
    view.add_argument('--widget', action='store_true', help='open the floating widget')
    view.add_argument('--full', action='store_true', help='open the full calendar window')
    parser.add_argument('--version', action='version', version=f'EconPulse {__version__}')
    args = parser.parse_args()
    system.setup_logging()
    theme.enable_dpi_awareness()  # before any Tk window exists
    if not args.demo and not system.acquire_single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo('EconPulse', 'EconPulse is already running.\nLook for its icon in the system tray.')
        root.destroy()
        return
    root = tk.Tk()
    EconPulse(root, args)
    root.mainloop()


if __name__ == '__main__':
    main()
