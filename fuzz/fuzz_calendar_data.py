"""Fuzz the code that reads downloaded calendar data.

Calendar data comes from the internet, so the parsers must survive anything:
wrong types, huge numbers, impossible dates, hostile text. This target turns
each fuzzer input into realistically shaped but hostile provider payloads, runs
them through every source's parser, and checks the rules the rest of the app
relies on.

Run with Atheris (Linux or macOS, Python 3.12+):

    python -m pip install --require-hashes -r requirements-fuzz.lock
    python fuzz/fuzz_calendar_data.py -max_total_time=60 fuzz/corpus

The same target also runs as a quick, deterministic unit test on every
platform without Atheris (tests/test_fuzz.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from econpulse.core import _CURRENCY, parse_feed
from econpulse.exports import _PLAIN_NUMBER, csv_cell, fold, ics_text
from econpulse.feed import serialize
from econpulse.providers import biquote, financecalendar

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
ZONES = [UTC, ZoneInfo('Pacific/Kiritimati'), ZoneInfo('Etc/GMT+12'), ZoneInfo('America/New_York')]

# Every field name any provider reads, so random records hit real code paths.
FIELDS = [
    'id', 'name', 'title', 'eventName', 'currency', 'country', 'time', 'date', 'release_at_utc', 'time_utc',
    'timeMode', 'type', 'importance', 'impact', 'actual', 'forecast', 'previous', 'revisedPrevious', 'consensus',
    'prior', 'unit', 'multiplier', 'digits', 'sourceUrl', 'url', 'source', 'source_name', 'period', 'category',
    'holiday_status', 'all_day', 'time_precision', 'status', 'time_label', 'source_day', 'actual_tone',
]  # fmt: skip
WORDS = [
    'high', 'medium', 'low', 'none', 'holiday', 'Holiday', 'percent', 'thousands', 'millions', 'billions',
    'trillions', 'date', 'tentative', 'exact', 'US', 'GB', 'EU', 'JP', 'USD', 'EUR', 'usd', 'better', 'worse',
    'minute', 'day', 'market-holidays', '=cmd|"/c calc"!A0', '+1+1', '-1,200', '@SUM(A1)', '\t=1', 'https://x.test/a',
    'javascript:alert(1)', '‮evil', 'Ж' * 90, ' ' * 5, '',
]  # fmt: skip
YEARS = [1, 2, 999, 1969, 1970, 2000, 2026, 2027, 2100, 9998, 9999]
OFFSETS = ['Z', '+00:00', '+14:00', '-12:00', '+05:30', '+23:59', '-23:59', '', '+99:00']


class Stream:
    """Reads fuzzer bytes as a sequence of choices; runs out gracefully."""

    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def byte(self) -> int:
        value = self.data[self.pos] if self.pos < len(self.data) else 0
        self.pos += 1
        return value

    def pick(self, options):
        return options[self.byte() % len(options)]

    def text(self) -> str:
        size = self.byte() % 64
        chunk = self.data[self.pos : self.pos + size]
        self.pos += size
        return chunk.decode('utf-8', 'replace')

    def number(self):
        kind = self.byte() % 9
        b = self.byte()
        return [
            b,
            -b,
            b / 7,
            float('inf'),
            float('nan'),
            10 ** (b * 15),  # integers far beyond float range
            -0.0,
            1e308 * (b or 1),
            int.from_bytes(self.data[self.pos : self.pos + 8] or b'\0', 'big', signed=True),
        ][kind]

    def stamp(self) -> str:
        year, month, day = self.pick(YEARS), self.byte() % 14, self.byte() % 33
        hour, minute = self.byte() % 26, self.byte() % 62
        return f'{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00{self.pick(OFFSETS)}'

    def value(self, depth=0):
        kind = self.byte() % (10 if depth < 2 else 7)
        if kind == 0:
            return None
        if kind == 1:
            return bool(self.byte() & 1)
        if kind == 2:
            return self.number()
        if kind == 3:
            return self.text()
        if kind in (4, 5):
            return self.pick(WORDS)
        if kind == 6:
            return self.stamp()
        if kind == 7:
            return [self.value(depth + 1) for _ in range(self.byte() % 4)]
        return self.record(depth + 1)

    def record(self, depth=0) -> dict:
        row = {}
        if self.byte() & 1:  # half the time, start from a row that parses, so deeper code runs
            row = {
                'title': self.pick(WORDS) or 'CPI',
                'country': self.pick(['USD', 'EUR', 'GBP']),
                'date': self.stamp(),
            }
        row.update({self.pick(FIELDS): self.value(depth) for _ in range(self.byte() % 14)})
        return row

    def payload(self):
        if self.byte() % 8 == 0:
            return self.value()  # sometimes not even a list
        return [self.record() for _ in range(self.byte() % 12)]


def decode(data: bytes):
    """JSON inputs (like the seed corpus) are used as is; anything else is decoded as choices."""
    if data[:1] in (b'[', b'{'):
        try:
            return json.loads(data)
        except (UnicodeDecodeError, ValueError, RecursionError):
            pass
    return Stream(data).payload()


def check_events(records) -> None:
    try:
        events = parse_feed(records)
    except ValueError:
        return  # documented: not a list, absurdly large, or nothing usable
    uids = [e.uid for e in events]
    assert len(uids) == len(set(uids)), 'duplicate events'
    for e in events:
        assert e.uid and len(e.uid) <= 120 and not any(ch in e.uid for ch in '\r\n\t ;,'), repr(e.uid)
        assert len(e.time_label) <= 40 and not any(ch in e.time_label for ch in '\r\n'), repr(e.time_label)
        assert _CURRENCY.fullmatch(e.currency), e.currency
        assert e.title and e.title == e.title.strip() and len(e.title) <= 300, repr(e.title)
        assert len(e.url) <= 2000 and all(len(v) <= 40 for v in (e.actual, e.forecast, e.previous))
        assert e.instant.tzinfo is not None
        for tz in ZONES:  # every event must render in every time zone
            e.display_day(tz)
            e.when_text(tz)
        e.countdown(NOW)
        for cell in (e.title, e.actual, e.forecast, e.previous):
            safe = csv_cell(cell)
            assert safe[:1] not in ('=', '+', '@', '|', '\t', '\r', '\n') or _PLAIN_NUMBER.fullmatch(safe), repr(safe)
            assert not safe.startswith('-') or _PLAIN_NUMBER.fullmatch(safe), repr(safe)
        summary = ics_text(e.title)
        assert '\r' not in summary and '\n' not in summary, repr(summary)
        line = fold(f'SUMMARY:{e.currency} - {summary}')
        assert all(len(part.encode('utf-8')) <= 75 for part in line.split('\r\n ')), line
        json.dumps(serialize(e))
    again = parse_feed([serialize(e) for e in events]) if events else []
    assert [(e.uid, e.title, e.instant) for e in again] == [(e.uid, e.title, e.instant) for e in events], 'cache'


def TestOneInput(data: bytes) -> None:
    payload = decode(data)
    check_events(payload)
    check_events(biquote.to_records(payload))  # must never raise
    rows = payload.get('events') if isinstance(payload, dict) else payload
    check_events(financecalendar.to_records(rows))
    if isinstance(payload, list):  # the Forex Factory export path
        check_events([{**row, 'source': 'Forex Factory', 'actual': ''} for row in payload if isinstance(row, dict)])


def main() -> None:
    import atheris  # Python fuzzing by way of Atheris (https://github.com/google/atheris)

    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == '__main__':
    main()
