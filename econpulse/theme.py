"""Design tokens: colour, typography, icons, anti-aliased shapes and HiDPI scaling.

Design language
---------------
* Neutral graphite surfaces; colour is reserved for meaning (impact level,
  better/worse results, the current-time marker). Primary actions are
  monochrome (light-on-dark / dark-on-light) rather than a template blue.
* Hierarchy comes from size, weight and three text tones (``text``, ``soft``,
  ``faded``), not from boxes, borders and upper-case labels.
* Every number uses a font with tabular digits, so ticking countdowns and
  right-aligned columns never jitter.

All layout code works in *logical* pixels (96 dpi) converted with :func:`px`.
Tk already scales point-sized fonts by the monitor DPI, so scaling geometry by
the same factor keeps text and boxes in proportion at any Windows scale.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont

from . import i18n

DARK = dict(
    bg='#0F1012',
    side='#0B0C0E',
    card='#141517',
    raised='#202125',
    inset='#141517',
    line='#222327',
    line_strong='#2E2F34',
    text='#EDEDEF',
    soft='#A1A2A9',
    faded='#6B6C74',
    hover='#1A1B1E',
    row_hover='#18191C',
    input='#141517',
    track='#2C2D32',
    primary='#EDEDEF',
    primary_hover='#FFFFFF',
    primary_fg='#0F1012',
    seg='#18191C',
    thumb='#2B2C31',
    red='#F2555A',
    amber='#E9A53E',
    green='#3FCF8E',
    purple='#A594F9',
    blue='#7AA2F7',
    now='#F2555A',
    white='#FFFFFF',
    shadow='#000000',
)
LIGHT = dict(
    bg='#F7F7F8',
    side='#F0F0F2',
    card='#FFFFFF',
    raised='#E9E9EC',
    inset='#FFFFFF',
    line='#E6E6E9',
    line_strong='#D6D6DB',
    text='#111113',
    soft='#5C5D64',
    faded='#909198',
    hover='#EFEFF1',
    row_hover='#F6F6F7',
    input='#FFFFFF',
    track='#D4D4D9',
    primary='#111113',
    primary_hover='#2B2B30',
    primary_fg='#FFFFFF',
    seg='#EBEBEE',
    thumb='#FFFFFF',
    red='#D93D42',
    amber='#B4730A',
    green='#18885A',
    purple='#6E56CF',
    blue='#2F6FEB',
    now='#D93D42',
    white='#FFFFFF',
    shadow='#000000',
)
SEV_COLOR = {'High': 'red', 'Medium': 'amber', 'Low': 'faded', 'Holiday': 'purple'}
IMPACT_LEVEL = {'High': 3, 'Medium': 2, 'Low': 1}


def palette(name: str) -> dict:
    return DARK if name == 'dark' else LIGHT


# --------------------------------------------------------------------------
# HiDPI
# --------------------------------------------------------------------------
_scale = 1.0


def enable_dpi_awareness() -> None:
    """Opt in to crisp rendering; must run before the first Tk() is created.

    System-DPI awareness (not per-monitor) is deliberate: Tk 8.6 does not
    handle WM_DPICHANGED, so Windows still bitmap-scales correctly when the
    widget is dragged to a monitor with a different scale factor.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # pragma: no cover - never block startup on cosmetics
        pass


def init_scale(root: tk.Misc) -> float:
    global _scale
    try:
        _scale = max(1.0, min(3.0, root.winfo_fpixels('1i') / 96.0))
    except tk.TclError:
        _scale = 1.0
    return _scale


def scale() -> float:
    return _scale


def px(value: float) -> int:
    """Logical (96-dpi) pixels -> physical pixels."""
    return round(value * _scale)


def unpx(value: float) -> int:
    """Physical pixels -> logical pixels (for persisting window geometry)."""
    return round(value / _scale)


# --------------------------------------------------------------------------
# Per-interpreter caches (fonts and images belong to one Tk root)
# --------------------------------------------------------------------------
_cache_root = None


def _check_root():
    global _cache_root, _family_cache
    root = getattr(tk, '_default_root', None)
    if root is not _cache_root:
        # Never reuse fonts/images after their root is destroyed (tests, or a
        # re-created root) - Tk raises "application has been destroyed".
        _fonts.clear()
        _images.clear()
        fitter.reset()
        _family_cache = None
        _cache_root = root


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
# (regular, semibold) families in order of preference. Segoe UI Variable is
# the Windows 11 system face; plain Segoe UI is the Windows 10 fallback.
if sys.platform == 'win32':
    _TEXT_FACES = [('Segoe UI Variable Text', 'Segoe UI Variable Text Semibold'), ('Segoe UI', 'Segoe UI Semibold')]
    _DISPLAY_FACES = [
        ('Segoe UI Variable Display', 'Segoe UI Variable Display Semib'),
        ('Segoe UI', 'Segoe UI Semibold'),
    ]
    # Segoe UI regular/bold has tabular digits; the Variable and Semibold faces do not.
    _NUMERIC_FACE = 'Segoe UI'
    _ICON_FACES = ['Segoe Fluent Icons', 'Segoe MDL2 Assets']
    # Segoe UI Variable has no Arabic-script shaping for Persian (words come
    # out in the wrong order); plain Segoe UI renders Persian correctly.
    _RTL_FACES = [('Segoe UI', 'Segoe UI Semibold')]
elif sys.platform == 'darwin':  # pragma: no cover
    _TEXT_FACES = _DISPLAY_FACES = [('Helvetica Neue', None)]
    _NUMERIC_FACE = 'Helvetica Neue'
    _ICON_FACES = []
    _RTL_FACES = _TEXT_FACES
else:
    _TEXT_FACES = _DISPLAY_FACES = [('Inter', 'Inter Semi Bold'), ('DejaVu Sans', None)]
    _NUMERIC_FACE = 'DejaVu Sans'
    _ICON_FACES = []
    _RTL_FACES = [('Vazirmatn', None), ('DejaVu Sans', None)]
MONO = 'Consolas' if sys.platform == 'win32' else 'DejaVu Sans Mono'

_fonts: dict[tuple, tkfont.Font] = {}
_family_cache: set[str] | None = None


def _families() -> set[str]:
    global _family_cache
    if _family_cache is None:
        try:
            _family_cache = set(tkfont.families())
        except tk.TclError:
            _family_cache = set()
    return _family_cache


def _face(faces, weight):
    available = _families()
    for regular, semibold in faces:
        if regular not in available:
            continue
        if weight == 'semibold':
            if semibold and semibold in available:
                return semibold, 'normal'
            return regular, 'bold'
        return regular, 'bold' if weight == 'bold' else 'normal'
    regular = faces[-1][0]
    return regular, 'bold' if weight in ('bold', 'semibold') else 'normal'


def font(size: int, weight: str = 'normal') -> tkfont.Font:
    """Shared UI font. weight is 'normal', 'semibold' or 'bold'."""
    _check_root()
    rtl = i18n.rtl()
    key = ('ui', size, weight, rtl)  # keyed by script: fonts in use are never deleted on a switch
    cached = _fonts.get(key)
    if cached is None:
        faces = _RTL_FACES if rtl else _DISPLAY_FACES if size >= 14 else _TEXT_FACES
        family, tk_weight = _face(faces, weight)
        cached = _fonts[key] = tkfont.Font(family=family, size=size, weight=tk_weight)
    return cached


def num(size: int, weight: str = 'normal') -> tkfont.Font:
    """Tabular-figure font for times, countdowns and data values."""
    _check_root()
    key = ('num', size, weight)
    cached = _fonts.get(key)
    if cached is None:
        family = _NUMERIC_FACE if _NUMERIC_FACE in _families() else _face(_TEXT_FACES, 'normal')[0]
        cached = _fonts[key] = tkfont.Font(
            family=family, size=size, weight='bold' if weight in ('bold', 'semibold') else 'normal'
        )
    return cached


# --------------------------------------------------------------------------
# Icons: native Windows icon font, with plain-text fallbacks elsewhere
# --------------------------------------------------------------------------
ICONS = {
    #            Fluent/MDL2  fallback
    'settings': ('\ue713', '⚙'),
    'refresh': ('\ue72c', '↻'),
    'close': ('\ue711', '×'),
    'search': ('\ue721', '⌕'),
    'clear': ('\ue711', '×'),
    'calendar': ('\ue787', '▦'),
    'today': ('\ue8bf', '◷'),
    'upcoming': ('\ue823', '◷'),
    'released': ('\ue73e', '✓'),
    'holiday': ('\ue706', '✦'),
    'export': ('\ue896', '↓'),
    'widget': ('\ue8a7', '↗'),
    'notes': ('\ue70b', '✎'),
    'chevron': ('\ue70d', '▾'),
    'globe': ('\ue774', '◍'),
    'target': ('\ue81d', '◎'),
    'link': ('\ue8a7', '↗'),
}


def icon_font(size: int = 11):
    """Icon font (or None when the platform has no icon face)."""
    _check_root()
    key = ('icon', size)
    if key in _fonts:
        return _fonts[key]
    family = next((f for f in _ICON_FACES if f in _families()), None)
    _fonts[key] = tkfont.Font(family=family, size=size) if family else None
    return _fonts[key]


def glyph(name: str, size: int = 11):
    """(text, font) for an icon; falls back to a text glyph in the UI font."""
    code, fallback = ICONS[name]
    f = icon_font(size)
    return (code, f) if f is not None else (fallback, font(size))


# --------------------------------------------------------------------------
# Anti-aliased shapes (Tk's canvas does not anti-alias polygons or ovals)
# --------------------------------------------------------------------------
_images: dict[tuple, object] = {}
_SS = 4  # supersampling factor

try:  # Pillow ships with the app (tray icon); degrade gracefully without it.
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # pragma: no cover
    Image = None


def has_aa() -> bool:
    return Image is not None


def _rgb(colour):
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))


def corner_images(r: int, fill: str, outline: str = '', width: int = 1):
    """Four PhotoImages (nw, ne, sw, se) forming the corners of a rounded box."""
    _check_root()
    key = ('corner', r, fill, outline, width)
    cached = _images.get(key)
    if cached is not None:
        return cached
    size = 2 * r * _SS
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if outline:
        draw.ellipse((0, 0, size - 1, size - 1), fill=(*_rgb(outline), 255))
        inner = width * _SS
        if fill:
            draw.ellipse((inner, inner, size - 1 - inner, size - 1 - inner), fill=(*_rgb(fill), 255))
        else:
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).ellipse((inner, inner, size - 1 - inner, size - 1 - inner), fill=255)
            img.paste((0, 0, 0, 0), mask=mask)
    else:
        draw.ellipse((0, 0, size - 1, size - 1), fill=(*_rgb(fill), 255))
    img = img.resize((2 * r, 2 * r), Image.LANCZOS)
    parts = tuple(
        ImageTk.PhotoImage(img.crop(box))
        for box in ((0, 0, r, r), (r, 0, 2 * r, r), (0, r, r, 2 * r), (r, r, 2 * r, 2 * r))
    )
    _images[key] = parts
    return parts


def dot_image(diameter: int, fill: str):
    _check_root()
    key = ('dot', diameter, fill)
    cached = _images.get(key)
    if cached is None:
        size = diameter * _SS
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((0, 0, size - 1, size - 1), fill=(*_rgb(fill), 255))
        cached = _images[key] = ImageTk.PhotoImage(img.resize((diameter, diameter), Image.LANCZOS))
    return cached


def brand_image(size: int, p: dict):
    """The EconPulse mark: a rounded tile carrying a pulse line and a live dot."""
    _check_root()
    key = ('brand', size, p['primary'], p['primary_fg'], p['red'])
    cached = _images.get(key)
    if cached is None:
        cached = _images[key] = ImageTk.PhotoImage(render_brand(size, p['primary'], p['primary_fg'], p['red']))
    return cached


def render_brand(size: int, tile: str, stroke: str, accent: str):
    """PIL image of the brand mark (also used to generate the app icon)."""
    s = size * _SS
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.27), fill=(*_rgb(tile), 255))
    pts = [(0.18, 0.56), (0.36, 0.56), (0.45, 0.30), (0.56, 0.74), (0.64, 0.50), (0.70, 0.56)]
    pts = [(x * s, y * s) for x, y in pts]
    w = max(_SS, int(s * 0.085))
    d.line(pts, fill=(*_rgb(stroke), 255), width=w, joint='curve')
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=(*_rgb(stroke), 255))
    r = s * 0.075
    cx, cy = s * 0.835, s * 0.56
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*_rgb(accent), 255))
    return img.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------------
# Text measurement
# --------------------------------------------------------------------------
class TextFitter:
    """Memoised width-aware truncation and word wrapping.

    The previous implementation removed one character at a time and called
    Tk's ``measure`` after each removal; this uses a binary search and caches
    results, which matters when hundreds of rows are laid out on each redraw.
    """

    def __init__(self):
        self._width: dict[tuple[str, str], int] = {}
        self._fit: dict[tuple[str, str, int], str] = {}
        self._wrap: dict[tuple[str, str, int], list[str]] = {}

    def measure(self, ft: tkfont.Font, text: str) -> int:
        key = (str(ft), text)
        value = self._width.get(key)
        if value is None:
            value = self._width[key] = ft.measure(text)
        return value

    def fit(self, ft: tkfont.Font, text: str, width: int) -> str:
        key = (str(ft), text, width)
        value = self._fit.get(key)
        if value is not None:
            return value
        if self.measure(ft, text) <= width:
            value = text
        else:
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if self.measure(ft, text[:mid].rstrip() + '…') <= width:
                    lo = mid
                else:
                    hi = mid - 1
            value = text[:lo].rstrip() + '…'
        self._fit[key] = value
        return value

    def wrap(self, ft: tkfont.Font, text: str, width: int) -> list[str]:
        key = (str(ft), text, width)
        value = self._wrap.get(key)
        if value is not None:
            return value
        if self.measure(ft, text) <= width:
            value = [text]
        else:
            value, line = [], ''
            for word in text.split():
                candidate = f'{line} {word}'.strip()
                if line and self.measure(ft, candidate) > width:
                    value.append(line)
                    line = word
                else:
                    line = candidate
            if line:
                value.append(line)
            value = value or ['']
        self._wrap[key] = value
        return value

    def reset(self):
        self._width.clear()
        self._fit.clear()
        self._wrap.clear()

    def trim(self):
        """Bound memory: widths change on resize, so stale keys accumulate."""
        for cache, limit in ((self._width, 20000), (self._fit, 6000), (self._wrap, 6000)):
            if len(cache) > limit:
                cache.clear()


fitter = TextFitter()
