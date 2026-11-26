"""Pure domain logic for EconPulse. No GUI dependency."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
import hashlib
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CURRENCIES = ('USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'NZD', 'CHF', 'CNY')
IMPACTS = ('High', 'Medium', 'Low', 'Holiday')
TIMEZONES = {
    'System local': None,
    'UTC': 'UTC',
    'New York (DST-aware)': 'America/New_York',
    'Chicago (DST-aware)': 'America/Chicago',
    'Toronto (DST-aware)': 'America/Toronto',
    'Los Angeles (DST-aware)': 'America/Los_Angeles',
    'London (DST-aware)': 'Europe/London',
    'Berlin (DST-aware)': 'Europe/Berlin',
    'Zurich (DST-aware)': 'Europe/Zurich',
    'Istanbul (UTC+03:00)': 'Europe/Istanbul',
    'Tehran (UTC+03:30)': 'Asia/Tehran',
    'Dubai (UTC+04:00)': 'Asia/Dubai',
    'Mumbai (UTC+05:30)': 'Asia/Kolkata',
    'Singapore (UTC+08:00)': 'Asia/Singapore',
    'Hong Kong (UTC+08:00)': 'Asia/Hong_Kong',
    'Shanghai (UTC+08:00)': 'Asia/Shanghai',
    'Tokyo (UTC+09:00)': 'Asia/Tokyo',
    'Sydney (DST-aware)': 'Australia/Sydney',
}


def desired_timezone(name: str) -> tzinfo | None:
    location = TIMEZONES.get(name)
    if location is None:
        try:
            from tzlocal import get_localzone

            local: tzinfo = get_localzone()
            return local
        except (ImportError, RuntimeError, OSError):
            return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(location)
    except ZoneInfoNotFoundError:
        if location == 'Asia/Tehran':
            return timezone(timedelta(hours=3, minutes=30))
        if location == 'UTC':
            return UTC
        return datetime.now().astimezone().tzinfo


_CURRENCY = re.compile(r'[A-Z]{3}')
_UID_UNSAFE = re.compile(r'[^A-Za-z0-9._:@/-]+')


def _text(value: object, limit: int = 300) -> str:
    """Provider text, whitespace-normalised and length-capped (defensive against odd feeds)."""
    return ' '.join(str(value or '').split())[:limit].rstrip()


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode('utf8'), usedforsecurity=False).hexdigest()[:20]


def _clean_uid(value: object, fingerprint: str) -> str:
    """Provider event id, safe for ICS and the cache.

    A plain id (letters, digits, ``._:@/-``, at most 120 characters) is kept as is.
    Anything else is replaced by its hash rather than rewritten, so two different
    ids can never collapse into the same uid (``'a b'`` and ``'a_b'`` stay distinct).
    """
    if value in (None, '') or isinstance(value, (dict, list)):
        return _digest(fingerprint)
    raw = str(value).strip()
    if raw and len(raw) <= 120 and not _UID_UNSAFE.search(raw):
        return raw
    return 'h:' + _digest(raw) if raw else _digest(fingerprint)


_FIGURE = re.compile(r'([-+]?)(\d[\d,]*(?:\.\d+)?)\s*(%|[KMBT])?', re.I)


def _figure(text: str) -> tuple[Decimal, str, int] | None:
    """'-0.2%' -> (Decimal('-0.2'), '%', 1 decimal); None if it isn't one plain figure."""
    match = _FIGURE.fullmatch(text.strip())
    if not match:
        return None
    sign, digits, unit = match.groups()
    number = Decimal(digits.replace(',', ''))
    places = len(digits.partition('.')[2])
    return (-number if sign == '-' else number), (unit or '').upper(), places


def surprise(actual: str, forecast: str) -> str:
    """How far the Actual landed from the forecast, e.g. '+23K', '-0.1 pp', '+2.9'.

    Neutral on purpose: whether higher is good depends on the indicator. Empty when
    either value is missing or they aren't the same kind of figure (e.g. % vs K).
    """
    a, f = _figure(actual or ''), _figure(forecast or '')
    if not a or not f or a[1] != f[1]:
        return ''
    delta = a[0] - f[0]
    places = max(a[2], f[2])
    text = f'{delta:+.{places}f}'
    if delta == 0:
        text = f'{0:.{places}f}'
    return f'{text} pp' if a[1] == '%' else text + a[1]


def series_key(e: Event) -> str:
    """Key for an indicator across its recurring releases (e.g. ``'USD|CPI y/y'``).

    Used for starred releases and per-release notes, so a star or a note carries
    over to next month's print. Capped to match the settings validator.
    """
    return f'{e.currency}|{e.title}'[:120]


def normalize_impact(value: object, title: str) -> str:
    v = str(value or '').strip().casefold()
    t = title.casefold()
    if 'holiday' in v or 'bank holiday' in t or 'public holiday' in t:
        return 'Holiday'
    if v in ('high', 'red', '3'):
        return 'High'
    if v in ('medium', 'med', 'orange', '2'):
        return 'Medium'
    if v in ('low', 'yellow', '1'):
        return 'Low'
    return 'Low'


def parse_date(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing event timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone offset required in event timestamp')
    return result


@dataclass(frozen=True)
class Event:
    uid: str
    title: str
    currency: str
    instant: datetime
    impact: str
    forecast: str = ''
    previous: str = ''
    actual: str = ''
    url: str = ''
    source: str = 'unknown'
    status: str = 'scheduled'
    period: str = ''
    confidence: str = ''
    time_label: str = ''  # All Day / Tentative / Day 2: no verified release clock
    source_day: str = ''  # source civil date for untimed events
    actual_tone: str = ''  # 'better' / 'worse' vs forecast, as marked by the provider
    revised_from: str = ''  # original previous value when revisedPrevious differs

    def to_record(self) -> dict[str, str]:
        """Canonical dict shape accepted by :func:`parse_feed`."""
        return {
            'id': self.uid,
            'title': self.title,
            'country': self.currency,
            'date': self.instant.isoformat(),
            'impact': self.impact,
            'forecast': self.forecast,
            'previous': self.previous,
            'actual': self.actual,
            'url': self.url,
            'source': self.source,
            'status': self.status,
            'period': self.period,
            'confidence': self.confidence,
            'time_label': self.time_label,
            'source_day': self.source_day,
            'actual_tone': self.actual_tone,
            'revised_from': self.revised_from,
        }

    @property
    def is_untimed(self) -> bool:
        return self.is_holiday or bool(self.time_label)

    @property
    def is_holiday(self) -> bool:
        return self.impact == 'Holiday'

    def local_dt(self, tz: tzinfo | None) -> datetime:
        return self.instant.astimezone(tz)

    def display_day(self, tz: tzinfo | None) -> date:
        # Calendar source associates a holiday with a market's civil date.
        # Never shift that date backward/forward due to the viewer's timezone.
        if self.is_untimed and self.source_day:
            try:
                return date.fromisoformat(self.source_day)
            except ValueError:
                pass
        return self.instant.date() if self.is_untimed else self.local_dt(tz).date()

    def when_text(self, tz: tzinfo | None) -> str:
        return (
            ('ALL DAY' if self.is_holiday else self.time_label)
            if self.is_untimed
            else self.local_dt(tz).strftime('%H:%M')
        )

    def countdown(self, now: datetime) -> str:
        if self.is_untimed:
            return 'HOLIDAY' if self.is_holiday else self.time_label.upper()
        remaining = int((self.instant - now).total_seconds())
        if remaining < 0:
            return 'Released'
        d, s = divmod(remaining, 86400)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f'{d}d {h:02d}:{m:02d}:{s:02d}' if d else f'{h:02d}:{m:02d}:{s:02d}'


def parse_feed(body: object) -> list[Event]:
    if not isinstance(body, list):
        raise ValueError('Expected a JSON array of calendar events')
    if len(body) > 10000:
        raise ValueError('Unreasonably large calendar feed')
    events: list[Event] = []
    seen = set()
    for record in body:
        if not isinstance(record, dict):
            continue
        title = _text(record.get('title') or record.get('eventName'))
        currency = str(record.get('country') or record.get('currency') or '').strip().upper()
        if not title or not _CURRENCY.fullmatch(currency):
            continue
        try:
            stamp = parse_date(record.get('date') or record.get('time'))
            # Absurd years can't be shown in every time zone (found by fuzzing; see fuzz/).
            if not 1970 <= stamp.astimezone(UTC).year <= 2200:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        impact = normalize_impact(record.get('impact'), title)
        time_label = _text(record.get('time_label'), 40)
        if impact == 'Holiday' and not time_label:
            time_label = 'All Day'
        fingerprint = f'{stamp.isoformat()}|{currency}|{title}|{impact}'
        # Stable provider ids survive a rescheduled release and prevent duplicate alerts.
        uid = _clean_uid(record.get('id'), fingerprint)
        if uid in seen:
            continue
        seen.add(uid)
        tone = str(record.get('actual_tone') or '')
        if tone not in ('better', 'worse'):
            tone = ''
        events.append(
            Event(
                uid=uid,
                title=title,
                currency=currency,
                instant=stamp.astimezone(UTC),  # one offset everywhere: ISO strings then sort correctly
                impact=impact,
                forecast=_text(record.get('forecast'), 40),
                previous=_text(record.get('previous'), 40),
                actual=_text(record.get('actual'), 40),
                url=_text(record.get('url'), 2000),
                source=_text(record.get('source'), 80) or 'unknown',
                status=_text(record.get('status'), 40) or 'scheduled',
                period=_text(record.get('period'), 40),
                confidence=_text(record.get('confidence'), 40),
                time_label=time_label,
                source_day=_text(record.get('source_day'), 10),
                actual_tone=tone,
                revised_from=_text(record.get('revised_from'), 40),
            )
        )
    if body and not events:
        raise ValueError('Feed contains no parseable calendar events')
    return sorted(events, key=lambda e: (e.instant, e.currency, e.title))


def weekly_sections(events: Iterable[Event], tz: tzinfo | None) -> list[tuple[date, list[Event]]]:
    """Preserve chronology while grouping by calendar date in the display timezone."""
    result: list[tuple[date, list[Event]]] = []
    for event in events:
        day = event.display_day(tz)
        if not result or result[-1][0] != day:
            result.append((day, []))
        result[-1][1].append(event)
    return result


class AlertEngine:
    """Send each threshold once per event, including after app wake/resume.

    State persisted on disk avoids repeating an alert on restart. All timestamps
    are timezone-aware; holiday events are never alerted as timed releases.
    """

    THRESHOLDS = (30, 15, 5, 0)

    def __init__(self, fired: object = None) -> None:
        if isinstance(fired, (list, set, tuple)):
            self.fired = {k for k in fired if isinstance(k, str) and len(k) <= 160}
        else:
            self.fired = set()

    def check(
        self,
        events: Iterable[Event],
        now: datetime | None = None,
        *,
        currencies: Iterable[str] | None = None,
        enabled_stages: Collection[int] = (30, 15, 5, 0),
        starred: Iterable[str] | None = None,
    ) -> list[tuple[Event, int]]:
        now = now or datetime.now(UTC)
        selected = set(currencies or ())
        starred_keys = set(starred or ())
        found = []
        for e in events:
            if e.is_untimed:
                continue
            is_starred = series_key(e) in starred_keys
            if not is_starred and (e.impact != 'High' or (selected and e.currency not in selected)):
                continue
            left = (e.instant - now).total_seconds()
            if left < -30 or left > 1800:
                continue
            # Choose the most urgent active threshold, so a newly launched
            # app doesn't play all earlier alerts at once.
            stage = 0 if left <= 0 else (5 if left <= 300 else (15 if left <= 900 else 30))
            if stage not in enabled_stages:
                continue
            key = f'{e.uid}:{stage}'
            if key not in self.fired:
                self.fired.add(key)
                found.append((e, stage))
        # Avoid unbounded growth of stored alert keys.
        if len(self.fired) > 4000:
            keep = {e.uid for e in events}
            # Keys are '<uid>:<stage>' and uids may contain ':' (e.g. 'bq:123').
            self.fired = {key for key in self.fired if key.rsplit(':', 1)[0] in keep}
        return found
