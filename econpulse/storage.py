"""Settings and local files (atomic JSON writes, validated settings)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from . import APP_NAME


def _chmod_private(path: Path, mode: int) -> None:
    if sys.platform != 'win32':
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def _replace_with_retry(src: Path, dst: Path) -> None:
    """Windows Defender / indexers can hold brief locks on newly-replaced files."""
    for delay in (0.025, 0.05, 0.1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if sys.platform != 'win32':
                raise
            time.sleep(delay)
    os.replace(src, dst)


def data_dir() -> Path:
    """Per-user folder for settings, cache, notes and the log."""
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA') or Path.home())
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / APP_NAME


def safe_write_text(path: Path, text: str) -> None:
    """Atomic text write with private POSIX permissions and Windows lock retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private(path.parent, 0o700)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            'w', encoding='utf-8', dir=path.parent, delete=False, prefix='.' + path.name, suffix='.tmp'
        ) as stream:
            tmp = Path(stream.name)
            stream.write(text)
        _chmod_private(tmp, 0o600)
        _replace_with_retry(tmp, path)
    except BaseException:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def safe_write_json(path: Path, value, indent=None):
    """Atomic write: readers never observe a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_private(path.parent, 0o700)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            'w', encoding='utf-8', dir=path.parent, delete=False, prefix='.' + path.name, suffix='.tmp'
        ) as stream:
            tmp = Path(stream.name)
            # Compact for the large cache; settings stay human-readable.
            json.dump(value, stream, ensure_ascii=False, indent=indent, separators=None if indent else (',', ':'))
        _chmod_private(tmp, 0o600)
        _replace_with_retry(tmp, path)
    except BaseException:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return default


DEFAULTS = {
    'summary_visible': True,
    'theme': 'dark',
    'language': 'en',
    'timezone': 'System local',
    'mode': 'widget',
    'topmost': True,
    'sound': True,
    'notifications': True,
    'notify_minutes': [30, 15, 5, 0],
    'holiday': True,
    'impacts': ['High', 'Medium', 'Low'],
    'currencies': [],
    'other_currencies': False,
    'refresh_minutes': 15,
    'widget_opacity': 100,
    'widget_x': None,
    'widget_y': None,
    'widget_w': 452,
    'widget_h': 615,
    'startup': False,
    'provider': 'biquote',
    'financecalendar_key': '',
    'check_updates': False,
    'last_update_check': '',
    'latest_version': '',
}

_CURRENCY = re.compile(r'[A-Z]{3}')
_KEY = re.compile(r'[A-Za-z0-9._\-]{0,128}')


def _choice(*allowed):
    return lambda v: v in allowed


def _int_range(lo, hi):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _subset(allowed):
    return lambda v: isinstance(v, list) and all(item in allowed for item in v) and len(set(v)) == len(v)


def _optional_int(v):
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and -100_000 <= v <= 100_000)


def _short_text(v):
    return isinstance(v, str) and len(v) <= 64


def _validators():
    # Imported here: core/i18n are cheap, but keeping storage import-light
    # lets the settings be read before anything else is set up.
    from .core import TIMEZONES
    from .i18n import LANGUAGES

    return {
        'summary_visible': lambda v: isinstance(v, bool),
        'theme': _choice('dark', 'light'),
        'language': lambda v: v in LANGUAGES,
        'timezone': lambda v: v in TIMEZONES,
        'mode': _choice('widget', 'full'),
        'topmost': lambda v: isinstance(v, bool),
        'sound': lambda v: isinstance(v, bool),
        'notifications': lambda v: isinstance(v, bool),
        'notify_minutes': _subset((30, 15, 5, 0)),
        'holiday': lambda v: isinstance(v, bool),
        'impacts': _subset(('High', 'Medium', 'Low')),
        'currencies': lambda v: (
            isinstance(v, list) and len(v) <= 60 and all(isinstance(c, str) and _CURRENCY.fullmatch(c) for c in v)
        ),
        'other_currencies': lambda v: isinstance(v, bool),
        'refresh_minutes': _int_range(15, 240),
        'widget_opacity': _int_range(40, 100),
        'widget_x': _optional_int,
        'widget_y': _optional_int,
        'widget_w': _int_range(200, 4000),
        'widget_h': _int_range(200, 4000),
        'startup': lambda v: isinstance(v, bool),
        'provider': _choice('biquote', 'ff_export', 'financecalendar'),
        'financecalendar_key': lambda v: isinstance(v, str) and bool(_KEY.fullmatch(v)),
        'check_updates': lambda v: isinstance(v, bool),
        'last_update_check': _short_text,
        'latest_version': _short_text,
    }


def validate_settings(raw) -> dict:
    """Known keys only, each checked for type/range; anything invalid falls back
    to its default, so a damaged or hand-edited settings.json can't crash the app."""
    if not isinstance(raw, dict):
        raw = {}
    checks = _validators()
    result = {}
    for key, default in DEFAULTS.items():
        value = raw.get(key, default)
        chosen = value if checks[key](value) else default
        result[key] = list(chosen) if isinstance(chosen, list) else chosen  # never share list objects
    if raw.get('widget_opacity') == 97:
        # 97 % was the old built-in default (never user-selectable); it let the
        # desktop show through the widget, which read as ghosting.
        result['widget_opacity'] = 100
    return result


def load_settings() -> dict:
    from .system import unprotect_secret

    raw = read_json(data_dir() / 'settings.json', {})
    if isinstance(raw, dict) and isinstance(raw.get('financecalendar_key'), str):
        raw = {**raw, 'financecalendar_key': unprotect_secret(raw['financecalendar_key'])}
    return validate_settings(raw)


def save_settings(values: dict):
    from .system import protect_secret

    to_write = dict(values)
    if isinstance(to_write.get('financecalendar_key'), str) and to_write['financecalendar_key']:
        to_write['financecalendar_key'] = protect_secret(to_write['financecalendar_key'])
    safe_write_json(data_dir() / 'settings.json', to_write, indent=2)
