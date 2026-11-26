"""Settings and local files (atomic JSON writes, validated settings)."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any

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


def safe_write_json(path: Path, value: object, indent: int | None = None) -> None:
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


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return default


_CURRENCY = re.compile(r'[A-Z]{3}')
_KEY = re.compile(r'[A-Za-z0-9._\-]{0,128}')


Check = Callable[[object], bool]


def _choice(*allowed: object) -> Check:
    return lambda v: v in allowed


def _int_range(lo: int, hi: int) -> Check:
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _subset(allowed: tuple[object, ...]) -> Check:
    return lambda v: isinstance(v, list) and all(item in allowed for item in v) and len(set(v)) == len(v)


def _optional_int(v: object) -> bool:
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and -100_000 <= v <= 100_000)


def _short_text(v: object) -> bool:
    return isinstance(v, str) and len(v) <= 64


def _flag(v: object) -> bool:
    return isinstance(v, bool)


def _timezone(v: object) -> bool:
    from .core import TIMEZONES  # imported lazily: settings load before anything else is set up

    return isinstance(v, str) and v in TIMEZONES  # a list or dict here must not crash the lookup


def _language(v: object) -> bool:
    from .i18n import LANGUAGES

    return isinstance(v, str) and v in LANGUAGES


def _currencies(v: object) -> bool:
    return isinstance(v, list) and len(v) <= 60 and all(isinstance(c, str) and _CURRENCY.fullmatch(c) for c in v)


def _starred(v: object) -> bool:
    return isinstance(v, list) and len(v) <= 100 and all(isinstance(k, str) and 0 < len(k) <= 120 for k in v)


SCHEMA_VERSION = 2

# Every setting in one place: name -> (default, check). A value that fails its check
# falls back to the default, so a damaged or hand-edited settings.json can't crash the app.
# Adding a setting = one line here (the tests check every one has a valid default).
SCHEMA: dict[str, tuple[object, Check]] = {
    'schema': (SCHEMA_VERSION, _int_range(1, SCHEMA_VERSION)),
    'summary_visible': (True, _flag),
    'theme': ('dark', _choice('dark', 'light', 'contrast')),
    'text_size': (100, _choice(100, 115, 130)),
    'language': ('en', _language),
    'timezone': ('System local', _timezone),
    'mode': ('widget', _choice('widget', 'full')),
    'topmost': (True, _flag),
    'sound': (True, _flag),
    'notifications': (True, _flag),
    'notify_minutes': ([30, 15, 5, 0], _subset((30, 15, 5, 0))),
    'holiday': (True, _flag),
    'impacts': (['High', 'Medium', 'Low'], _subset(('High', 'Medium', 'Low'))),
    'currencies': ([], _currencies),
    'other_currencies': (False, _flag),
    'refresh_minutes': (15, _int_range(15, 240)),
    'widget_opacity': (100, _int_range(40, 100)),
    'widget_compact': (False, _flag),
    'compact_dock': ('off', _choice('off', 'top', 'bottom')),
    'widget_x': (None, _optional_int),
    'widget_y': (None, _optional_int),
    'widget_w': (452, _int_range(200, 4000)),
    'widget_h': (615, _int_range(200, 4000)),
    'startup': (False, _flag),
    'global_hotkey': (False, _flag),
    'provider': ('biquote', _choice('biquote', 'ff_export', 'financecalendar')),
    'financecalendar_key': ('', lambda v: isinstance(v, str) and bool(_KEY.fullmatch(v))),
    'check_updates': (False, _flag),
    'last_update_check': ('', _short_text),
    'latest_version': ('', _short_text),
    'alert_actual': (True, _flag),
    'burst_poll': (False, _flag),
    'write_status_file': (False, _flag),
    'starred': ([], _starred),
}
DEFAULTS = {name: default for name, (default, _check) in SCHEMA.items()}


def _v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    # 97 % was the old built-in widget opacity (never user-selectable); it let the
    # desktop show through the widget, which read as ghosting.
    if raw.get('widget_opacity') == 97:
        raw['widget_opacity'] = 100
    return raw


# MIGRATIONS[n] upgrades a version n-1 file to version n. Files without 'schema' are version 1.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {2: _v1_to_v2}


def validate_settings(raw: object) -> dict[str, Any]:
    """Upgrade an old file, then keep known keys only, each checked for type and range."""
    raw = dict(raw) if isinstance(raw, dict) else {}
    version = raw.get('schema')
    if not (isinstance(version, int) and not isinstance(version, bool) and 1 <= version <= SCHEMA_VERSION):
        version = 1
    for target in range(version + 1, SCHEMA_VERSION + 1):
        raw = MIGRATIONS[target](raw)
    raw['schema'] = SCHEMA_VERSION
    result = {}
    for key, (default, check) in SCHEMA.items():
        value = raw.get(key, default)
        chosen = value if check(value) else default
        result[key] = list(chosen) if isinstance(chosen, list) else chosen  # never share list objects
    return result


def load_settings() -> dict[str, Any]:
    from .system import unprotect_secret

    raw = read_json(data_dir() / 'settings.json', {})
    if isinstance(raw, dict) and isinstance(raw.get('financecalendar_key'), str):
        raw = {**raw, 'financecalendar_key': unprotect_secret(raw['financecalendar_key'])}
    return validate_settings(raw)


def save_settings(values: dict[str, Any]) -> None:
    from .system import forget_secret, protect_secret

    to_write = dict(values)
    if isinstance(to_write.get('financecalendar_key'), str) and to_write['financecalendar_key']:
        to_write['financecalendar_key'] = protect_secret(to_write['financecalendar_key'])
    else:
        forget_secret()
    safe_write_json(data_dir() / 'settings.json', to_write, indent=2)
