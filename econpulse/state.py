"""Pure application state helpers: currency filtering, Actual-published detection,
smart post-release burst polling, starring, and live status snapshots.

No Tkinter dependency — every function here is fast and directly unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from .core import CURRENCIES, Event, series_key
from .storage import data_dir, read_json, safe_write_json

EVENT_NOTES_FILE = 'event-notes.json'
STATUS_FILE = 'next.json'
BURST_DELAYS = (45, 180)  # polite post-release checks (seconds after a watched release time)
PUBLISHED_MAX_AGE = timedelta(minutes=30)  # older releases are not news any more

event_key = series_key  # star / note key for an indicator across recurring releases


def watched_currencies(cfg: dict[str, Any]) -> set[str] | None:
    """Currencies the user follows: explicit selection, else majors (or None for all)."""
    selected = cfg.get('currencies') or []
    if selected:
        return set(selected)
    return None if cfg.get('other_currencies') else set(CURRENCIES)


def is_watched_event(e: Event, watched: set[str] | None, starred: set[str] | None = None) -> bool:
    """True if this release should trigger alerts / burst checks."""
    if e.is_untimed:
        return False
    if starred and event_key(e) in starred:
        return True
    return e.impact == 'High' and (watched is None or e.currency in watched)


def detect_published_actuals(
    previous_events: list[Event],
    new_events: list[Event],
    *,
    watched: set[str] | None = None,
    starred: set[str] | None = None,
    now: datetime | None = None,
) -> list[Event]:
    """Return watched events whose Actual figure just arrived compared to ``previous_events``.

    With ``now``, releases older than :data:`PUBLISHED_MAX_AGE` are skipped: after a
    restart or a laptop wake, the first fetch fills in hours-old figures, which are
    not "just published".
    """
    if not previous_events:
        return []
    old_by_uid = {e.uid: e for e in previous_events}
    published: list[Event] = []
    for e in new_events:
        if not e.actual or not is_watched_event(e, watched, starred):
            continue
        if now is not None and not (timedelta(0) <= now - e.instant <= PUBLISHED_MAX_AGE):
            continue
        old = old_by_uid.get(e.uid)
        if old is not None and not old.actual:
            published.append(e)
    return published


def due_burst_poll(
    events: list[Event],
    now: datetime,
    *,
    watched: set[str] | None = None,
    starred: set[str] | None = None,
    fired_bursts: set[str],
) -> str | None:
    """Return a burst-poll token if a watched release just landed without an Actual figure.

    Tokens are per release *time*, not per release: five US figures at 13:30 share
    one check at +45 s and one at +180 s, so a busy minute costs two extra refreshes
    at most. Only the most recent stage is taken, so a late start never fires both.
    """
    due: dict[str, int] = {}
    for e in events:
        if e.actual or not is_watched_event(e, watched, starred):
            continue
        elapsed = (now - e.instant).total_seconds()
        if elapsed < BURST_DELAYS[0] or elapsed > BURST_DELAYS[-1] + 90:
            continue
        stage = max(idx for idx, delay in enumerate(BURST_DELAYS) if elapsed >= delay)
        due[e.instant.isoformat()] = stage
    for instant, stage in sorted(due.items()):
        tokens = [f'{instant}:b{idx}' for idx in range(stage + 1)]
        if tokens[-1] not in fired_bursts:
            fired_bursts.update(tokens)
            return tokens[-1]
    if len(fired_bursts) > 200:
        # Only tokens for the last few minutes matter; drop the rest.
        horizon = (now - timedelta(minutes=30)).isoformat()
        fired_bursts.intersection_update({t for t in fired_bursts if t.rsplit(':b', 1)[0] >= horizon})
    return None


def status_snapshot(
    events: list[Event],
    next_event: Event | None,
    *,
    state: str,
    source: str,
    at: datetime | None,
    now: datetime,
    tz: tzinfo | None,
) -> dict[str, Any]:
    """Compact JSON payload written to ``next.json`` for OBS / Stream Deck / scripts."""
    payload: dict[str, Any] = {
        'updated_at': now.isoformat(),
        'state': state,
        'source': source,
        'last_sync': at.isoformat() if at else None,
        'event_count': len(events),
        'next_high_impact': None,
    }
    if next_event is not None:
        remaining = max(0, int((next_event.instant - now).total_seconds()))
        payload['next_high_impact'] = {
            'uid': next_event.uid,
            'currency': next_event.currency,
            'title': next_event.title,
            'impact': next_event.impact,
            'instant_utc': next_event.instant.isoformat(),
            'local_time': next_event.local_dt(tz).isoformat(),
            'countdown': next_event.countdown(now),
            'seconds_remaining': remaining,
            'forecast': next_event.forecast,
            'previous': next_event.previous,
            'revised_from': next_event.revised_from,
        }
    return payload


def write_status_snapshot(payload: dict[str, Any], folder: Path | None = None) -> None:
    target = (folder or data_dir()) / STATUS_FILE
    safe_write_json(target, payload, indent=2)


def load_event_notes(folder: Path | None = None) -> dict[str, str]:
    raw = read_json((folder or data_dir()) / EVENT_NOTES_FILE, {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(k)[:120]: str(v)[:4000]
        for k, v in raw.items()
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()
    }


def save_event_note(key: str, text: str, folder: Path | None = None) -> dict[str, str]:
    notes = load_event_notes(folder)
    cleaned = text.strip()[:4000]
    if cleaned:
        notes[key[:120]] = cleaned
    else:
        notes.pop(key[:120], None)
    safe_write_json((folder or data_dir()) / EVENT_NOTES_FILE, notes, indent=2)
    return notes
