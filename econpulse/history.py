"""A local record of past releases, so the details window can show an indicator's history.

Each successful download adds the released figures it contains to ``history.json``,
keyed by indicator (``core.series_key``), so the record grows the longer EconPulse
runs: a monthly indicator gains one entry a month. Nothing is sent anywhere.

Pure Python and size-capped. It is written from the fetch worker thread and read on
the main thread; atomic writes mean a reader never sees half a file.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
import threading

from .core import Event, series_key
from .storage import data_dir, read_json, safe_write_json

HISTORY_FILE = 'history.json'
PER_SERIES = 12  # the last year of a monthly indicator
MAX_SERIES = 1500  # least recently released indicators are dropped beyond this
_FIELDS = ('actual', 'forecast', 'previous')
_lock = threading.Lock()


def _path(folder: Path | None) -> Path:
    return (folder or data_dir()) / HISTORY_FILE


def load(folder: Path | None = None) -> dict[str, list[dict[str, str]]]:
    """The archive, with anything malformed in it dropped."""
    raw = read_json(_path(folder), {})
    if not isinstance(raw, dict):
        return {}
    archive: dict[str, list[dict[str, str]]] = {}
    for key, entries in raw.items():
        if not isinstance(key, str) or not isinstance(entries, list):
            continue
        clean = [
            {name: str(entry.get(name, ''))[:40] for name in ('at', *_FIELDS)}
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get('at'), str) and entry.get('actual')
        ]
        if clean:
            archive[key[:120]] = clean[-PER_SERIES:]
    return archive


def merge(archive: dict[str, list[dict[str, str]]], events: Iterable[Event], now: datetime) -> bool:
    """Add released figures to ``archive`` in place; returns whether anything changed.

    One entry per release (indicator and time); a later download with a revised figure
    replaces it. Untimed items and releases without an Actual are skipped.
    """
    changed = False
    for e in events:
        if not e.actual or e.is_untimed or e.instant > now:
            continue
        entry = {'at': e.instant.isoformat(), 'actual': e.actual, 'forecast': e.forecast, 'previous': e.previous}
        series = archive.setdefault(series_key(e), [])
        for i, old in enumerate(series):
            if old['at'] == entry['at']:
                if old != entry:
                    series[i] = entry
                    changed = True
                break
        else:
            series.append(entry)
            series.sort(key=lambda item: item['at'])
            del series[:-PER_SERIES]
            changed = True
    if len(archive) > MAX_SERIES:
        newest = sorted(archive, key=lambda k: archive[k][-1]['at'], reverse=True)[:MAX_SERIES]
        for key in set(archive) - set(newest):
            del archive[key]
        changed = True
    return changed


def record(events: Iterable[Event], now: datetime, folder: Path | None = None) -> None:
    """Merge a download into the archive on disk (called from the fetch thread)."""
    with _lock:
        archive = load(folder)
        if merge(archive, events, now):
            safe_write_json(_path(folder), archive)


def for_event(e: Event, limit: int = 6, folder: Path | None = None) -> list[dict[str, str]]:
    """This indicator's earlier releases, newest first, not counting ``e`` itself."""
    series = load(folder).get(series_key(e), [])
    earlier = [item for item in series if item['at'] < e.instant.isoformat()]
    return list(reversed(earlier))[:limit]
