"""Daily check that the live data sources still look the way EconPulse expects.

    python tools/canary.py

Run once a day by .github/workflows/canary.yml: one biquote request for today and
one download of the Forex Factory weekly export (that's all, so it stays polite).
It fails, so the maintainers are told, when a field the app relies on disappears
or changes type: an early warning before users report an empty calendar.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from econpulse.core import parse_feed
from econpulse.providers import biquote, ff_export
from econpulse.providers.base import http_get_json

# Field -> allowed JSON types, for the fields the app reads (see providers/biquote.py).
BIQUOTE_FIELDS = {
    'id': (str, int),
    'time': (str,),
    'currency': (str,),
    'name': (str,),
    'importance': (str,),
    'type': (str,),
    'timeMode': (str,),
    'actual': (int, float, str, type(None)),
    'forecast': (int, float, str, type(None)),
    'previous': (int, float, str, type(None)),
}
FF_FIELDS = {'title': (str,), 'country': (str,), 'date': (str,), 'impact': (str,)}


def check_rows(name: str, rows: object, fields: dict[str, tuple[type, ...]]) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return [f'{name}: expected a non-empty JSON list, got {type(rows).__name__}']
    problems = []
    for field, types in fields.items():
        present = [row for row in rows if isinstance(row, dict) and field in row]
        if len(present) < len(rows) * 0.9:
            problems.append(f'{name}: field {field!r} is missing from {len(rows) - len(present)} of {len(rows)} rows')
        wrong = [row[field] for row in present if not isinstance(row[field], types)]
        if wrong:
            problems.append(f'{name}: field {field!r} has unexpected types, e.g. {wrong[0]!r}')
    return problems


def main() -> int:
    day = datetime.now(UTC).date()
    today, tomorrow = day.isoformat(), (day + timedelta(days=1)).isoformat()
    problems: list[str] = []

    # 'to' is an exclusive midnight (the provider relies on that; see BiquoteProvider._fetch_span).
    rows = http_get_json(biquote.API, params={'from': today, 'to': tomorrow, 'limit': biquote.PAGE_LIMIT})
    problems += check_rows('biquote', rows, BIQUOTE_FIELDS)
    if isinstance(rows, list) and rows:
        late = [r for r in rows if isinstance(r, dict) and str(r.get('time', ''))[:10] == tomorrow]
        if len(late) > len(rows) / 2:
            problems.append("biquote: 'to' now looks inclusive; the provider's date spans need changing")
    if not problems:
        events = parse_feed(biquote.to_records(rows))
        print(f'biquote: {len(rows)} rows for {today}, {len(events)} events parsed')
        if len(events) < len(rows) * 0.8:
            problems.append(f'biquote: only {len(events)} of {len(rows)} rows could be parsed')

    export = http_get_json(ff_export.EXPORT)
    problems += check_rows('Forex Factory export', export, FF_FIELDS)
    if isinstance(export, list):
        print(f'Forex Factory export: {len(export)} rows')

    for problem in problems:
        print(f'::error::{problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
