"""Portable calendar exports: CSV (UTF-8 BOM) and RFC 5545 style ICS."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
import re

# A figure such as -0.2%, +1.5K, 3.38M or -1,200: safe in a spreadsheet as is.
_PLAIN_NUMBER = re.compile(r'[-+]?\d[\d,]*(\.\d+)?\s*[%KMBTkmbt]?')


def csv_cell(value) -> str:
    """Neutralise spreadsheet formulas (CSV injection).

    Text from a data feed that starts with = + - @ (or a tab/CR) could be run
    as a formula by Excel or LibreOffice; such cells get a leading apostrophe.
    Plain figures like "-0.2%" are left alone so they stay numbers.
    """
    text = str(value)
    if text[:1] in ('=', '+', '-', '@', '\t', '\r') and not _PLAIN_NUMBER.fullmatch(text):
        return "'" + text
    return text


def save_csv(path, events, tz):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Time', 'Currency', 'Impact', 'Event', 'Actual', 'Forecast', 'Previous'])
        for e in events:
            row = [
                e.display_day(tz).isoformat(),
                e.when_text(tz),
                e.currency,
                e.impact,
                e.title,
                e.actual,
                e.forecast,
                e.previous,
            ]
            writer.writerow([csv_cell(cell) for cell in row])


def ics_text(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def fold(line):
    """RFC 5545 §3.1: lines longer than 75 octets are folded with CRLF + space."""
    raw = line.encode('utf-8')
    if len(raw) <= 75:
        return line
    parts = []
    limit = 75
    while raw:
        cut = min(limit, len(raw))
        while cut < len(raw) and (raw[cut] & 0xC0) == 0x80:  # never split a UTF-8 sequence
            cut -= 1
        parts.append(raw[:cut].decode('utf-8'))
        raw = raw[cut:]
        limit = 74
    return '\r\n '.join(parts)


def save_ics(path, events, tz):
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//EconPulse//Economic Calendar//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]
    for e in events:
        lines.extend(
            [
                'BEGIN:VEVENT',
                f'UID:{e.uid}@econpulse.local',
                f'DTSTAMP:{stamp}',
                f'SUMMARY:{ics_text(e.currency + " - " + e.title)}',
                'DESCRIPTION:' + ics_text(f'Impact: {e.impact} / Forecast: {e.forecast} / Previous: {e.previous}'),
            ]
        )
        if e.is_untimed:
            d = e.display_day(tz)
            lines.extend([f'DTSTART;VALUE=DATE:{d:%Y%m%d}', f'DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}'])
        else:
            dt = e.instant.astimezone(UTC)
            end = dt + timedelta(minutes=15)
            lines.extend([f'DTSTART:{dt:%Y%m%dT%H%M%SZ}', f'DTEND:{end:%Y%m%dT%H%M%SZ}'])
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    Path(path).write_bytes(('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8'))
