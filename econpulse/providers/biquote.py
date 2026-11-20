"""biquote.io economic calendar: free, no key, Actual/Forecast/Previous values.

Terms (https://biquote.io/terms.html): free "for both commercial and
non-commercial projects"; a visible credit is appreciated, not required.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..core import Event, parse_feed
from .base import Provider, ProviderError, http_get_json

API = 'https://biquote.io/api/calendar'
PAGE_LIMIT = 500
_SUFFIX = {'thousands': 'K', 'millions': 'M', 'billions': 'B', 'trillions': 'T'}
_IMPACT = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}


def format_value(value, unit, multiplier, digits) -> str:
    """0.2 + percent -> '0.2%', 3.38 + millions -> '3.38M', 165 + thousands -> '165K'.

    Values arrive already scaled to the multiplier, with ``digits`` decimals.
    """
    if value is None or isinstance(value, bool):
        return ''
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)[:40]
    places = digits if isinstance(digits, int) and 0 <= digits <= 6 else 2
    text = f'{number:.{places}f}'
    if text.startswith('-') and float(text) == 0:
        text = text[1:]
    if unit == 'percent':
        return text + '%'
    return text + _SUFFIX.get(multiplier or '', '')


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

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        """Ten days back to ten days ahead, in weekly requests (the API caps a
        response at 500 rows; a busy week has about 400)."""
        today = now.date()
        records: list[dict] = []
        start, end = today - timedelta(days=10), today + timedelta(days=10)
        while start <= end:
            stop = min(start + timedelta(days=6), end)
            rows = http_get_json(
                API, params={'from': start.isoformat(), 'to': stop.isoformat(), 'limit': PAGE_LIMIT}, timeout=timeout
            )
            if not isinstance(rows, list):
                raise ProviderError('unexpected biquote response')
            if len(rows) >= PAGE_LIMIT and stop > start:
                # Too dense for one request: retry this span in two halves.
                end_first = start + (stop - start) // 2
                for a, b in ((start, end_first), (end_first + timedelta(days=1), stop)):
                    part = http_get_json(
                        API, params={'from': a.isoformat(), 'to': b.isoformat(), 'limit': PAGE_LIMIT}, timeout=timeout
                    )
                    records.extend(to_records(part))
            else:
                records.extend(to_records(rows))
            start = stop + timedelta(days=1)
        events = parse_feed(records)
        if not events:
            raise ProviderError('biquote returned no events')
        return events
