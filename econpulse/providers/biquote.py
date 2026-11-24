"""biquote.io economic calendar: free, no key, Actual/Forecast/Previous values.

Terms (https://biquote.io/terms.html): free "for both commercial and
non-commercial projects"; a visible credit is appreciated, not required.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
import math
import threading

from ..core import Event, parse_feed
from .base import Provider, ProviderError, http_get_json

API = 'https://biquote.io/api/calendar'
log = logging.getLogger('econpulse')
PAGE_LIMIT = 500
_SUFFIX = {'thousands': 'K', 'millions': 'M', 'billions': 'B', 'trillions': 'T'}
_IMPACT = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}


def format_value(value, unit, multiplier, digits) -> str:
    """0.2 + percent -> '0.2%', 3.38 + millions -> '3.38M', 165 + thousands -> '165K'.

    Values arrive already scaled to the multiplier, with ``digits`` decimals.
    """
    # Anything can arrive here, so every type is handled (found by fuzzing; see fuzz/).
    if value is None or isinstance(value, bool):
        return ''
    try:
        number = float(value)
    except OverflowError:  # an integer too large for a float
        return ''
    except (TypeError, ValueError):
        return str(value)[:40] if isinstance(value, str) else ''
    if not math.isfinite(number):
        return ''
    places = digits if isinstance(digits, int) and not isinstance(digits, bool) and 0 <= digits <= 6 else 2
    text = f'{number:.{places}f}'
    if text.startswith('-') and float(text) == 0:
        text = text[1:]
    if unit == 'percent':
        return text + '%'
    return text + (_SUFFIX.get(multiplier, '') if isinstance(multiplier, str) else '')


def _period(value) -> str:
    try:
        day = datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except (TypeError, ValueError):
        return ''
    return day.strftime('%b %Y') if day.day == 1 else day.strftime('%d %b %Y')


def to_records(items) -> list[dict]:
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

        def value(name, row=item):
            return format_value(row.get(name), row.get('unit'), row.get('multiplier'), row.get('digits'))

        previous = item.get('revisedPrevious')
        records.append(
            {
                'id': f'bq:{item.get("id")}' if item.get('id') else '',
                'title': item.get('name'),
                'country': item.get('currency'),
                'date': when,
                'impact': 'Holiday' if holiday else _IMPACT.get(str(item.get('importance')), 'Low'),
                'actual': value('actual'),
                'forecast': value('forecast'),
                'previous': value('revisedPrevious') if previous is not None else value('previous'),
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

    def _fetch_span(self, start, stop, timeout: float, budget: list[int], lock: threading.Lock) -> list[dict]:
        rows = http_get_json(
            API, params={'from': start.isoformat(), 'to': stop.isoformat(), 'limit': PAGE_LIMIT}, timeout=timeout
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

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        """Ten days back to ten days ahead, in concurrent weekly requests (the API
        caps a response at 500 rows; a busy week has about 400)."""
        today = now.date()
        spans = []
        start, end = today - timedelta(days=10), today + timedelta(days=10)
        while start <= end:
            stop = min(start + timedelta(days=6), end)
            spans.append((start, stop))
            start = stop + timedelta(days=1)
        budget = [self.MAX_EXTRA_REQUESTS]
        lock = threading.Lock()
        records: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(3, len(spans))) as pool:
            futures = [pool.submit(self._fetch_span, a, b, timeout, budget, lock) for a, b in spans]
            for fut in futures:
                records.extend(fut.result())
        events = parse_feed(records)
        if not events:
            raise ProviderError('biquote returned no events')
        return events
