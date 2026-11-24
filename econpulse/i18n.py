"""Interface language, right-to-left layout and localised dates.

Languages live in :mod:`econpulse.locales` (one module each) and are listed in
:data:`LANGUAGES`. A locale supplies ``STRINGS`` and may override the hooks
used below (digits, counts, dates...); English is the built-in default.

Right-to-left languages also mirror the layout: :func:`install_rtl_geometry`
makes every ``pack`` call swap left/right sides, anchors and asymmetric
padding, and the canvas widgets mirror their own drawing. Clock times,
countdowns and data values keep Latin digits, as trading terminals do, so
columns stay tabular.

Tk on Windows renders right-to-left text correctly per text item with Segoe
UI (not Segoe UI Variable), but its bidi handling breaks when a percent sign
or number sits next to Persian words, so labels and values are drawn as
separate items and Persian strings get a leading right-to-left mark.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import ModuleType

from .locales import fa


class _English:
    CODE = 'en'
    NAME = 'English'
    RTL = False
    STRINGS: dict[str, str] = {}


LANGUAGES: dict[str, type | ModuleType] = {'en': _English, 'fa': fa}
_locale: type | ModuleType = _English


def set_language(lang: str) -> None:
    global _locale
    _locale = LANGUAGES.get(lang, _English)


def language() -> str:
    return _locale.CODE


def rtl() -> bool:
    return bool(_locale.RTL)


def language_choices() -> list[tuple[str, str]]:
    """(code, native name) pairs for the language picker."""
    return [(code, module.NAME) for code, module in LANGUAGES.items()]


def _hook(name):
    return getattr(_locale, name, None)


def tr(text: str) -> str:
    return _locale.STRINGS.get(text, text)


RLM = '\u200f'  # RIGHT-TO-LEFT MARK (written as an escape: never paste the raw character)


def _has_arabic_script(text: str) -> bool:
    return any('؀' <= ch <= 'ۿ' or 'ﭐ' <= ch <= '﷿' or 'ﹰ' <= ch <= '﻾' for ch in text)


def bidi(text) -> str:
    """Prepare a string for display.

    Tk on Windows lays every text item out with a left-to-right base
    direction, so a Persian string that starts with a digit or ends with a
    comma or space is reordered wrongly. A leading RLM makes the base
    direction right-to-left. Strings without Arabic-script letters (event
    titles, figures such as "5.62|2.5") are returned unchanged so they can
    never be reordered.
    """
    text = '' if text is None else str(text)
    if _locale.RTL and text and not text.startswith(RLM) and _has_arabic_script(text):
        return RLM + text
    return text


def digits(value) -> str:
    """Locale digits inside prose; unchanged in English."""
    hook = _hook('digits')
    return hook(value) if hook else str(value)


_NOUNS = {'release': ('release', 'releases'), 'holiday': ('holiday', 'holidays')}


def count(n: int, noun: str) -> str:
    """'28 releases' / '۲۸ رویداد'."""
    hook = _hook('count')
    if hook:
        return hook(n, noun)
    one, many = _NOUNS[noun]
    return f'{n} {one if n == 1 else many}'


def minutes(n: int) -> str:
    hook = _hook('minutes')
    return hook(n) if hook else f'{n} min'


def alert_heading(stage: int) -> str:
    if stage == 0:
        return tr('Releasing now')
    hook = _hook('alert_heading')
    return hook(stage) if hook else f'High-impact release in {stage} min'


def impact_text(impact: str) -> str:
    hook = _hook('impact_text')
    return hook(impact) if hook else f'{impact} impact'


def sync_detail(stamp: str, age_minutes: int) -> str:
    """Short sync subtitle in the sidebar, e.g. 'Synced 14:30 · 5m ago'."""
    hook = _hook('sync_detail')
    if hook:
        return hook(stamp, age_minutes)
    return f'Synced {stamp}' + (f' · {age_minutes}m ago' if age_minutes >= 1 else '')


def sync_status(source: str, stamp: str, age_minutes: int) -> str:
    """Footer status line, e.g. 'biquote  ·  last sync 14:30 (5m ago)'."""
    hook = _hook('sync_status')
    if hook:
        return hook(source, stamp, age_minutes)
    return f'{source}  ·  last sync {stamp} ({age_minutes}m ago)'


def countdown_in(text: str) -> str:
    """'in 00:12:30' / '00:12:30 مانده'."""
    hook = _hook('countdown_in')
    return hook(text) if hook else f'in {text}'


def weekday(d: date) -> str:
    hook = _hook('weekday')
    return hook(d) if hook else d.strftime('%A')


def date_text(d: date, style: str = 'long') -> str:
    """Localised date. styles: 'full' (weekday, day, month, year), 'long'
    (weekday, day, month), 'medium' (short weekday, day, month), 'short' (day, month)."""
    hook = _hook('date_text')
    if hook:
        return hook(d, style)
    return d.strftime({'full': '%A %d %B %Y', 'long': '%A %d %B', 'medium': '%a %d %b', 'short': '%d %b'}[style])


def day_label(day: date, today: date) -> tuple[str, str]:
    """('Today', 'Thu 12 Nov') / ('امروز', 'پنجشنبه ۲۱ آبان') heading parts."""
    relative = {today: 'Today', today + timedelta(days=1): 'Tomorrow', today - timedelta(days=1): 'Yesterday'}
    if day in relative:
        return tr(relative[day]), date_text(day, 'medium')
    return weekday(day), date_text(day, 'short')


# Kept as plain names: the Jalali helpers are part of the Persian locale.
gregorian_to_jalali = fa.gregorian_to_jalali


# --------------------------------------------------------------------------
# Layout mirroring
# --------------------------------------------------------------------------
_ANCHOR_SWAP = {'w': 'e', 'e': 'w', 'nw': 'ne', 'ne': 'nw', 'sw': 'se', 'se': 'sw'}


def mirror_anchor(anchor: str) -> str:
    """Swap east/west compass anchors; 'center', 'n' and 's' are unchanged."""
    return _ANCHOR_SWAP.get(anchor, anchor) if isinstance(anchor, str) else anchor


def mirror_pack_options(options: dict) -> dict:
    """Mirror pack() options horizontally (side, anchor, asymmetric padx)."""
    kw = dict(options)
    side = kw.get('side')
    if side in ('left', 'right'):
        kw['side'] = 'right' if side == 'left' else 'left'
    if 'anchor' in kw:
        kw['anchor'] = mirror_anchor(kw['anchor'])
    padx = kw.get('padx')
    if isinstance(padx, (tuple, list)) and len(padx) == 2:
        kw['padx'] = (padx[1], padx[0])
    return kw


_installed = False


def install_rtl_geometry() -> None:
    """Make ``pack`` mirror itself while the interface language is RTL.

    Every screen is written once, left-to-right; in a right-to-left language
    the packer lays it out mirrored, the way Qt's layout direction works.
    Calls are untouched in left-to-right languages.
    """
    global _installed
    if _installed:
        return
    import tkinter as tk

    original = tk.Pack.pack_configure

    def pack_configure(self, cnf=None, **kw):
        if _locale.RTL:
            if cnf:
                kw = {**cnf, **kw}
                cnf = None
            kw = mirror_pack_options(kw)
        return original(self, cnf or {}, **kw)

    pack_configure.__doc__ = original.__doc__
    tk.Pack.pack_configure = pack_configure
    tk.Pack.pack = pack_configure
    _installed = True
