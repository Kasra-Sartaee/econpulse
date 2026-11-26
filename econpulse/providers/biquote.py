"""biquote.io economic calendar: free, no key, Actual/Forecast/Previous values.

Terms (https://biquote.io/terms.html): free "for both commercial and
non-commercial projects"; a visible credit is appreciated, not required.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import logging
import math
import threading
from typing import Any

from ..core import Event, parse_feed
from .base import Provider, ProviderError, http_get_json

API = 'https://biquote.io/api/calendar'
log = logging.getLogger('econpulse')
PAGE_LIMIT = 500
_SUFFIX = {'thousands': 'K', 'millions': 'M', 'billions': 'B', 'trillions': 'T'}
_IMPACT = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}


def format_value(value: object, unit: object, multiplier: object, digits: object) -> str:
    """0.2 + percent -> '0.2%', 3.38 + millions -> '3.38M', 165 + thousands -> '165K'.

    Values arrive already scaled to the multiplier, with ``digits`` decimals.
    """
    # Anything can arrive here, so every type is handled (found by fuzzing; see fuzz/).
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return ''  # None, booleans, lists, objects
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float
        return ''
    except (TypeError, ValueError):
        return str(value)[:40] if isinstance(value, str) else ''
    if not math.isfinite(number) or abs(number) >= 1e15:
        # No real figure is this large in its own units; showing it would mean cutting
        # the digits off later (a wrong number), so treat it as missing (found by Hypothesis).
        return ''
    places = digits if isinstance(digits, int) and not isinstance(digits, bool) and 0 <= digits <= 6 else 2
    text = f'{number:.{places}f}'
    if text.startswith('-') and float(text) == 0:
        text = text[1:]
    if unit == 'percent':
        return text + '%'
    return text + (_SUFFIX.get(multiplier, '') if isinstance(multiplier, str) else '')


def _period(value: object) -> str:
    try:
        day = datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except (TypeError, ValueError):
        return ''
    return day.strftime('%b %Y') if day.day == 1 else day.strftime('%d %b %Y')


def to_records(items: object) -> list[dict[str, Any]]:
    """biquote rows -> the neutral record shape understood by :func:`core.parse_feed`."""
    records = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        holiday = item.get('type') == 'holiday'
        mode = item.get('timeMode')
        when = str(item.get('time') or '')
        label = ''
        if holiday or mode == 'date':
            label = 'All Day'
        elif mode == 'tentative':
            label = 'Tentative'

        def value(name: str, row: dict[str, Any] = item) -> str:
            return format_value(row.get(name), row.get('unit'), row.get('multiplier'), row.get('digits'))

        raw_id = item.get('id')
        orig_previous = value('previous')
        revised = item.get('revisedPrevious')
        shown_previous = value('revisedPrevious') if revised is not None else orig_previous
        revised_from = (
            orig_previous if revised is not None and orig_previous and orig_previous != shown_previous else ''
        )
        records.append(
            {
                'id': f'bq:{raw_id}' if raw_id not in (None, '') and not isinstance(raw_id, (dict, list)) else '',
                'title': item.get('name'),
                'country': item.get('currency'),
                'date': when,
                'impact': 'Holiday' if holiday else _IMPACT.get(str(item.get('importance')), 'Low'),
                'actual': value('actual'),
                'forecast': value('forecast'),
                'previous': shown_previous,
                'revised_from': revised_from,
                'url': item.get('sourceUrl') or '',
                'source': 'biquote',
                'period': _period(item.get('period')),
                'time_label': label,
                'source_day': when[:10] if label else '',
            }
        )
    return records


class BiquoteProvider(Provider):
    id = 'biquote'
    name = 'biquote'
    homepage = 'https://biquote.io/'
    attribution = 'Market data by biquote'
    terms_url = 'https://biquote.io/terms.html'

    MAX_EXTRA_REQUESTS = 8  # for splitting over-full weeks; normal fetches take 3 requests

    def _fetch_span(
        self, start: date, stop: date, timeout: float, budget: list[int], lock: threading.Lock
    ) -> list[dict[str, Any]]:
        # biquote's 'to' is an exclusive midnight: to=27 Nov returns 26 Nov plus only 27 Nov 00:00.
        # So request up to the next day; the shared 00:00 rows are de-duplicated by their id.
        until = stop + timedelta(days=1)
        rows = http_get_json(
            API, params={'from': start.isoformat(), 'to': until.isoformat(), 'limit': PAGE_LIMIT}, timeout=timeout
        )
        if not isinstance(rows, list):
            raise ProviderError('unexpected biquote response')
        if len(rows) >= PAGE_LIMIT and stop > start:
            with lock:
                can_split = budget[0] >= 2
                if can_split:
                    budget[0] -= 2  # reserve both halves before either request starts
            if can_split:
                # Too dense for one request: split this span in two halves (recursively).
                mid = start + (stop - start) // 2
                return self._fetch_span(start, mid, timeout, budget, lock) + self._fetch_span(
                    mid + timedelta(days=1), stop, timeout, budget, lock
                )
            # Out of budget: keep the capped page rather than dropping these days.
            log.warning('biquote: %s to %s is capped at %d rows', start, stop, PAGE_LIMIT)
        return to_records(rows)

    WINDOW_DAYS = 10  # days back and ahead
    NEAR_DAYS = 1  # yesterday..tomorrow change all day (Actuals, revisions, reschedules)
    FULL_EVERY = timedelta(minutes=60)  # the rest of the window is refreshed hourly

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Forget the last full download (the next fetch downloads the whole window)."""
        with self._lock:
            self._full_at: datetime | None = None
            self._records: list[dict[str, Any]] = []

    def _spans(self, first: date, last: date) -> list[tuple[date, date]]:
        spans: list[tuple[date, date]] = []
        start = first
        while start <= last:
            stop = min(start + timedelta(days=6), last)
            spans.append((start, stop))
            start = stop + timedelta(days=1)
        return spans

    def _download(self, spans: list[tuple[date, date]], timeout: float) -> list[dict[str, Any]]:
        budget = [self.MAX_EXTRA_REQUESTS]
        lock = threading.Lock()
        records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(3, len(spans))) as pool:
            futures = [pool.submit(self._fetch_span, a, b, timeout, budget, lock) for a, b in spans]
            for fut in futures:
                records.extend(fut.result())
        return records

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        """Ten days back to ten days ahead (the API caps a response at 500 rows; a busy
        week has about 400, so the window goes out as concurrent weekly requests).

        Only yesterday to tomorrow changes during the day, so between hourly full
        refreshes just that span is downloaded (1 request instead of 3), and merged
        with the rest of the last full download.
        """
        today = now.date()
        with self._lock:
            full_at, previous = self._full_at, self._records
        partial = (
            full_at is not None
            and full_at.date() == today  # the window moves at midnight UTC
            and timedelta(0) <= now - full_at < self.FULL_EVERY
            and previous
        )
        if partial:
            near_first, near_last = today - timedelta(days=self.NEAR_DAYS), today + timedelta(days=self.NEAR_DAYS)
            near = {d.isoformat() for d in (near_first + timedelta(days=i) for i in range(2 * self.NEAR_DAYS + 1))}
            fresh = self._download([(near_first, near_last)], timeout)
            records = [r for r in previous if _record_day(r) not in near] + fresh
        else:
            window = timedelta(days=self.WINDOW_DAYS)
            records = self._download(self._spans(today - window, today + window), timeout)
        events = parse_feed(records)
        if not events:
            raise ProviderError('biquote returned no events')
        with self._lock:
            if not partial:
                self._full_at = now
            self._records = records
        return events


def _record_day(record: dict[str, Any]) -> str:
    """The UTC day a record was requested under (biquote filters by UTC date)."""
    return str(record.get('date') or '')[:10]
