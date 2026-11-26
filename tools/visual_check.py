"""Visual regression check: render the key screens and compare them with reference images.

    python tools/visual_check.py --out visual                         # just render
    python tools/visual_check.py --out visual --baseline tests/visual # render and compare

Every screen is drawn from the demo data at one fixed moment, so two runs on the same
machine give identical pixels. Fonts and scaling differ between machines, so the
reference images in tests/visual/ come from CI's Windows runner: to accept a visual
change, download the "visual" artifact of a CI run and copy its PNGs there.

A screen fails when more than MAX_CHANGED of its pixels differ noticeably (so tiny
anti-aliasing differences pass); a diff image highlighting the changes is written next
to it. Windows only (it captures with PrintWindow).
"""

from __future__ import annotations

import argparse
from argparse import Namespace
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

from screenshots import capture, pump

from econpulse import app as app_module
from econpulse import i18n, storage, theme
from econpulse.demo import demo_events

FIXED_NOW = datetime(2026, 11, 20, 12, 0, 30, tzinfo=UTC)
MAX_CHANGED = 0.001  # share of pixels allowed to differ (renders on one machine are identical)
THRESHOLD = 8  # per-pixel difference (0-255) that counts: subtle colour changes must show up

# name, settings, view, step
SCREENS = [
    ('calendar-dark', {'theme': 'dark'}, 'full', None),
    ('calendar-light', {'theme': 'light'}, 'full', None),
    ('calendar-contrast', {'theme': 'contrast'}, 'full', None),
    ('calendar-persian', {'theme': 'light', 'language': 'fa'}, 'full', None),
    ('widget-dark', {'theme': 'dark'}, 'widget', None),
    ('widget-persian', {'theme': 'dark', 'language': 'fa'}, 'widget', None),
    ('widget-compact', {'theme': 'dark', 'widget_compact': True}, 'widget', None),
    ('release-details', {'theme': 'dark'}, 'full', 'detail'),
    ('preferences', {'theme': 'dark'}, 'full', 'settings'),
]


def render(name, settings, view, step, out: Path) -> Path:
    import tkinter as tk

    with (
        tempfile.TemporaryDirectory() as profile,
        mock.patch.dict(os.environ, {'APPDATA': profile, 'XDG_CONFIG_HOME': profile, 'TZ': 'UTC'}),
        mock.patch.object(app_module, 'demo_events', lambda: demo_events(FIXED_NOW)),
        mock.patch.object(app_module.EconPulse, 'now', lambda self: FIXED_NOW),
        mock.patch.object(app_module.EconPulse, 'tz', lambda self: UTC),
        mock.patch.object(app_module.EconPulse, 'init_tray', lambda a: setattr(a, 'tray', None)),
    ):
        storage.save_settings({**storage.DEFAULTS, 'summary_visible': True, **settings})
        root = tk.Tk()
        app = app_module.EconPulse(root, Namespace(demo=True, full=view == 'full', widget=view == 'widget'))
        target = app.widget if view == 'widget' else root
        pump(root, 1.0)
        if step == 'detail':
            app.event_detail(next(e for e in app.visible() if e.actual and not e.is_holiday))
            target = app.detail_window
        elif step == 'settings':
            app.settings()
            target = app.setting_window
        pump(root, 0.6)
        path = out / f'{name}.png'
        capture(target).save(path, optimize=True)
        app.quit()
        i18n.set_language('en')
        theme.set_text_size(100)
    return path


def compare(rendered: Path, reference: Path, diff_path: Path) -> str | None:
    """None if they match; otherwise why, and a diff image is written."""
    from PIL import Image, ImageChops

    new, old = Image.open(rendered).convert('RGB'), Image.open(reference).convert('RGB')
    if new.size != old.size:
        return f'size changed from {old.size} to {new.size}'
    delta = ImageChops.difference(new, old).convert('L').point(lambda v: 255 if v > THRESHOLD else 0)
    changed = delta.histogram()[255] / (new.width * new.height)
    if changed <= MAX_CHANGED:
        return None
    highlight = new.copy()
    highlight.paste((255, 0, 80), mask=delta)
    highlight.save(diff_path, optimize=True)
    return f'{changed:.2%} of the pixels changed'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, help='folder of reference PNGs (tests/visual)')
    parser.add_argument('--only', nargs='*', help='screen names to render')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, settings, view, step in SCREENS:
        if args.only and name not in args.only:
            continue
        rendered = render(name, settings, view, step, args.out)
        reference = args.baseline / rendered.name if args.baseline else None
        if reference is None or not reference.exists():
            print(f'rendered  {name}' + ('  (no reference image yet)' if args.baseline else ''))
            continue
        problem = compare(rendered, reference, args.out / f'{name}.diff.png')
        print(f'{"CHANGED " if problem else "same    "}  {name}' + (f': {problem}' if problem else ''))
        if problem:
            failures.append(name)
    if failures:
        print(f'\n{len(failures)} screen(s) changed. If the change is intended, copy the new PNGs from the')
        print('"visual" artifact into tests/visual/; otherwise look at the *.diff.png images.')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
