"""Regenerate the README screenshots and demo animation (Windows; needs Pillow).

    python tools/screenshots.py                 # demo data -> docs/screenshots/
    python tools/screenshots.py --gif           # also docs/assets/demo.gif
    python tools/screenshots.py --live --out shots   # live data, for checking a change

Then run tools/brand_assets.py to rebuild the hero images from the screenshots.

Each shot runs the real app in-process with a throwaway settings folder, so
your own settings, cache and notes are never touched. Windows are captured
from the screen, so keep the desktop clear of other always-on-top windows.
"""

from __future__ import annotations

import argparse
from argparse import Namespace
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse import app as app_module
from econpulse import i18n, storage, theme

# name, language, theme, view, extra step
SHOTS = [
    ('calendar-dark', 'en', 'dark', 'full', None),
    ('calendar-light', 'en', 'light', 'full', None),
    ('widget-today', 'en', 'dark', 'widget', None),
    ('widget-light', 'en', 'light', 'widget', None),
    ('widget-week', 'en', 'dark', 'widget', 'week'),
    ('release-details', 'en', 'dark', 'full', 'detail'),
    ('preferences', 'en', 'dark', 'full', 'settings'),
    ('calendar-persian', 'fa', 'light', 'full', None),
    ('widget-persian', 'fa', 'dark', 'widget', None),
]


def pump(root, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def grab(window, path: Path):
    capture(window).save(path, optimize=True)


def capture(window):
    """Capture only this window's own pixels (Win32 PrintWindow), never the screen,
    so notifications, the taskbar or other apps can't end up in a screenshot."""
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    window.update_idletasks()
    hwnd = window.winfo_id()
    width, height = window.winfo_width(), window.winfo_height()
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    screen_dc = user32.GetDC(0)
    dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, dc, 2):  # PW_RENDERFULLCONTENT
            raise RuntimeError('PrintWindow failed')

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD),
            ]

        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
        return Image.frombuffer('RGB', (width, height), buffer, 'raw', 'BGRX', 0, 1).copy()
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(0, screen_dc)


def shoot(name, lang, palette, view, step, out: Path, live: bool):
    import tkinter as tk

    with (
        tempfile.TemporaryDirectory() as profile,
        mock.patch.dict(os.environ, {'APPDATA': profile, 'XDG_CONFIG_HOME': profile}),
    ):
        storage.save_settings({**storage.DEFAULTS, 'language': lang, 'theme': palette, 'summary_visible': True})
        root = tk.Tk()
        with mock.patch.object(app_module.EconPulse, 'init_tray', lambda a: setattr(a, 'tray', None)):
            app = app_module.EconPulse(root, Namespace(demo=not live, full=view == 'full', widget=view == 'widget'))
        if live:
            deadline = time.monotonic() + 30
            while app.inflight and time.monotonic() < deadline:
                pump(root, 0.2)
        window = app.widget if view == 'widget' else root
        window.attributes('-topmost', True)
        window.lift()
        if step == 'week':
            app.set_widget_period('week')
        pump(root, 1.2)
        target = window
        if step == 'detail':
            event = next(e for e in app.visible() if e.actual and not e.is_holiday)
            app.event_detail(event)
            target = app.detail_window
        elif step == 'settings':
            app.settings()
            target = app.setting_window
        if target is not window:
            target.attributes('-topmost', True)
            pump(root, 1.0)
        grab(target, out / f'{name}.png')
        app.quit()
        i18n.set_language('en')
    print(f'{name}.png')


def demo_gif(out: Path, width=960):
    """A short tour of the full calendar: views, filters, search, theme and language."""
    import tkinter as tk

    from PIL import Image

    frames = []  # (image, milliseconds)

    with (
        tempfile.TemporaryDirectory() as profile,
        mock.patch.dict(os.environ, {'APPDATA': profile, 'XDG_CONFIG_HOME': profile}),
    ):
        storage.save_settings({**storage.DEFAULTS, 'theme': 'dark', 'summary_visible': True})
        root = tk.Tk()
        with mock.patch.object(app_module.EconPulse, 'init_tray', lambda a: setattr(a, 'tray', None)):
            app = app_module.EconPulse(root, Namespace(demo=True, full=True, widget=False))
        root.attributes('-topmost', True)
        root.lift()
        pump(root, 1.2)

        def shot(ms):
            pump(root, 0.35)
            image = capture(root)
            height = round(image.height * width / image.width)
            frames.append((image.resize((width, height), Image.LANCZOS), ms))

        def restyle(palette=None, language=None):
            if palette:
                app.cfg['theme'] = palette
                app.p = theme.palette(palette)
                root.configure(bg=app.p['bg'])
            if language:
                app.cfg['language'] = language
                i18n.set_language(language)
            app.build_full()
            app.render()
            pump(root, 1.2)  # let the clock line catch up after the rebuild

        shot(1000)
        shot(1600)  # the countdown ticks
        for tab in ('today', 'upcoming', 'released', 'holidays', 'all'):
            app.set_tab(tab)
            shot(1300)
        for impact in ('Medium', 'Low'):
            app.toggle_impact(impact)
        shot(1500)
        for impact in ('Medium', 'Low'):
            app.toggle_impact(impact)
        app.toggle_currency('USD')
        shot(1500)
        app.toggle_currency('ALL')
        for typed in ('C', 'CP', 'CPI'):
            app.search_var.set(typed)
            shot(260)
        shot(1600)
        app.search_var.set('')
        restyle(palette='light')
        shot(2200)
        restyle(language='fa')
        shot(2600)
        app.quit()
        i18n.set_language('en')

    # One shared palette keeps colours stable from frame to frame (no flicker).
    sheet = Image.new('RGB', (width, sum(f.height for f, _ in frames)))
    y = 0
    for image, _ms in frames:
        sheet.paste(image, (0, y))
        y += image.height
    palette = sheet.quantize(colors=255, method=Image.Quantize.FASTOCTREE)
    images = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image, _ms in frames]
    target = out / 'demo.gif'
    images[0].save(
        target,
        save_all=True,
        append_images=images[1:],
        duration=[ms for _image, ms in frames],
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f'{target.name}: {len(images)} frames, {target.stat().st_size // 1024} KB')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'screenshots'))
    parser.add_argument('--live', action='store_true', help='fetch real data instead of the demo set')
    parser.add_argument('--only', nargs='*', help='shot names to take')
    parser.add_argument('--gif', action='store_true', help='also record docs/assets/demo.gif')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    theme.enable_dpi_awareness()
    for shot in SHOTS:
        if args.only is None or shot[0] in args.only:
            shoot(*shot, out=out, live=args.live)
    if args.gif:
        assets = ROOT / 'docs' / 'assets'
        assets.mkdir(parents=True, exist_ok=True)
        demo_gif(assets)


if __name__ == '__main__':
    main()
