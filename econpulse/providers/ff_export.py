"""Forex Factory's official weekly calendar export (schedule only).

This JSON export is the calendar feed Fair Economy itself publishes for
calendar apps. It has the week's schedule, impact, forecast and previous
values but no Actual results. It is only requested at most once an hour and
the response is cached. EconPulse does not read forexfactory.com pages.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..core import Event, parse_feed
from ..storage import data_dir, read_json, safe_write_json
from .base import Provider, ProviderError, http_get_json

EXPORT = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
CACHE = 'ff-export-v4.json'
MIN_INTERVAL = timedelta(minutes=62)


def _serialize(e: Event) -> dict:
    return {
        'id': e.uid,
        'title': e.title,
        'country': e.currency,
        'date': e.instant.isoformat(),
        'impact': e.impact,
        'forecast': e.forecast,
        'previous': e.previous,
        'source': e.source,
        'time_label': e.time_label,
        'source_day': e.source_day,
    }


class ForexFactoryExportProvider(Provider):
    id = 'ff_export'
    name = 'Forex Factory weekly export'
    homepage = 'https://www.forexfactory.com/'
    attribution = 'Schedule: Forex Factory weekly export'
    has_actuals = False

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        saved = read_json(data_dir() / CACHE, {})
        if not isinstance(saved, dict):
            saved = {}
        week = (now.date() - timedelta(days=(now.weekday() + 1) % 7)).isoformat()
        try:
            stamp = datetime.fromisoformat(saved.get('at', ''))
        except (TypeError, ValueError):
            stamp = None
        if stamp and saved.get('week') == week and now - stamp < MIN_INTERVAL:
            try:
                return parse_feed(saved['events'])
            except (KeyError, TypeError, ValueError):
                pass
        body = http_get_json(EXPORT, timeout=timeout)
        records = []
        for row in body if isinstance(body, list) else []:
            if isinstance(row, dict):
                records.append({**row, 'source': self.name, 'actual': ''})
        try:
            events = parse_feed(records)
        except ValueError as exc:
            raise ProviderError(str(exc)) from None
        if not events:
            raise ProviderError('the weekly export is empty')
        safe_write_json(
            data_dir() / CACHE, {'at': now.isoformat(), 'week': week, 'events': [_serialize(e) for e in events]}
        )
        return events
