"""FinanceCalendar.com (optional, needs the user's own API key).

Official-agency data (BLS, ONS, ECB, ...) with consensus, prior and actual.
Terms (https://www.financecalendar.com/api/terms/) allow personal and
commercial use within the plan's allowance and require a visible attribution
link to https://www.financecalendar.com near the data. The free plan is
schedule-only (no figures, 10 requests a day); the Starter plan covers
15-minute refreshes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..core import Event, parse_feed
from .base import Provider, ProviderError, http_get_json

API = 'https://www.financecalendar.com/wp-json/fc/v1/calendar'
PAGE = 500
MAX_PAGES = 6
COUNTRY_CURRENCY = {
    'US': 'USD',
    'GB': 'GBP',
    'UK': 'GBP',
    'EU': 'EUR',
    'EA': 'EUR',
    'DE': 'EUR',
    'FR': 'EUR',
    'IT': 'EUR',
    'ES': 'EUR',
    'NL': 'EUR',
    'JP': 'JPY',
    'CA': 'CAD',
    'AU': 'AUD',
    'NZ': 'NZD',
    'CH': 'CHF',
    'CN': 'CNY',
    'NO': 'NOK',
    'SE': 'SEK',
    'IN': 'INR',
    'HK': 'HKD',
    'KR': 'KRW',
    'MY': 'MYR',
}
_IMPACT = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}


def _value(value, unit) -> str:
    if value is None or value == '':
        return ''
    text = str(value).strip()[:40]
    return text + '%' if isinstance(unit, str) and unit.strip().startswith('%') else text


def to_records(rows) -> list[dict]:
    records = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        currency = COUNTRY_CURRENCY.get(str(row.get('country') or '').upper())
        if not currency:
            continue
        holiday = bool(row.get('holiday_status')) or row.get('category') == 'market-holidays'
        all_day = bool(row.get('all_day')) or row.get('time_precision') not in (None, 'minute', 'second')
        when = row.get('release_at_utc') or row.get('time_utc')
        if not when and row.get('date'):
            when = f'{row["date"]}T12:00:00+00:00'
        unit = row.get('unit')
        records.append(
            {
                'id': f'fc:{row.get("id")}' if row.get('id') else '',
                'title': row.get('name') or row.get('title'),
                'country': currency,
                'date': when,
                'impact': 'Holiday' if holiday else _IMPACT.get(str(row.get('impact')), 'Low'),
                'actual': _value(row.get('actual'), unit),
                'forecast': _value(row.get('consensus'), unit),
                'previous': _value(row.get('prior'), unit),
                'url': row.get('url') or '',
                'source': f'FinanceCalendar.com · {row["source_name"]}'
                if row.get('source_name')
                else 'FinanceCalendar.com',
                'period': str(row.get('period') or '')[:20],
                'time_label': 'All Day' if (holiday or all_day) else '',
                'source_day': str(row.get('date') or '')[:10] if (holiday or all_day) else '',
            }
        )
    return records


class FinanceCalendarProvider(Provider):
    id = 'financecalendar'
    name = 'FinanceCalendar.com'
    homepage = 'https://www.financecalendar.com/'
    attribution = 'Data: FinanceCalendar.com'
    terms_url = 'https://www.financecalendar.com/api/terms/'
    needs_key = True

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        if not key:
            raise ProviderError('no FinanceCalendar.com API key set')
        today = now.date()
        params = {
            'from': (today - timedelta(days=10)).isoformat(),
            'to': (today + timedelta(days=10)).isoformat(),
            'include': 'holidays',
            'limit': PAGE,
        }
        records: list[dict] = []
        for page in range(MAX_PAGES):
            body = http_get_json(
                API, params={**params, 'offset': page * PAGE}, headers={'X-API-Key': key}, timeout=timeout
            )
            rows = body.get('events') if isinstance(body, dict) else None
            if not isinstance(rows, list):
                raise ProviderError('unexpected FinanceCalendar.com response')
            records.extend(to_records(rows))
            total = body.get('total') if isinstance(body.get('total'), int) else None
            if len(rows) < PAGE or (total is not None and (page + 1) * PAGE >= total):
                break
        try:
            events = parse_feed(records)
        except ValueError as exc:
            raise ProviderError(str(exc)) from None
        if not events:
            raise ProviderError('FinanceCalendar.com returned no events for this key')
        return events
