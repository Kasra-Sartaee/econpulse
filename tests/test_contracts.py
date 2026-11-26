"""Exact outputs: the contracts other code and users rely on.

Mutation testing (see [tool.mutmut] in pyproject.toml) showed that many lines were run by
the tests without their results being checked. These tests pin the results exactly:
every field of a parsed event, every export byte, every alert boundary.
"""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import helpers  # noqa: F401  (makes the package importable)

from econpulse import core, state
from econpulse.core import AlertEngine, Event, normalize_impact, parse_feed
from econpulse.exports import save_csv, save_ics

NOW = datetime(2026, 11, 20, 13, 30, tzinfo=UTC)
FULL = {
    'id': 'bq:1',
    'title': 'Non-Farm Employment Change',
    'country': 'usd',
    'date': '2026-11-20T08:30:00-05:00',
    'impact': 'high',
    'actual': '165K',
    'forecast': '142K',
    'previous': '188K',
    'revised_from': '180K',
    'url': 'https://example.org/nfp',
    'source': 'example',
    'status': 'released',
    'period': 'Oct 2026',
    'confidence': 'final',
    'actual_tone': 'better',
}


class ParseFeedContract(unittest.TestCase):
    def test_every_field_is_mapped_exactly(self):
        e = parse_feed([FULL])[0]
        self.assertEqual(
            e,
            Event(
                uid='bq:1',
                title='Non-Farm Employment Change',
                currency='USD',
                instant=NOW,
                impact='High',
                forecast='142K',
                previous='188K',
                actual='165K',
                url='https://example.org/nfp',
                source='example',
                status='released',
                period='Oct 2026',
                confidence='final',
                time_label='',
                source_day='',
                actual_tone='better',
                revised_from='180K',
            ),
        )

    def test_defaults_and_alternative_field_names(self):
        e = parse_feed([{'eventName': 'CPI', 'currency': 'eur', 'time': NOW.isoformat()}])[0]
        self.assertEqual((e.title, e.currency, e.impact), ('CPI', 'EUR', 'Low'))
        self.assertEqual((e.source, e.status, e.actual_tone), ('unknown', 'scheduled', ''))

    def test_a_bad_record_does_not_hide_the_good_ones_after_it(self):
        records = [
            'junk',
            {'title': '', 'country': 'USD', 'date': NOW.isoformat()},
            {'title': 'x', 'country': 'US', 'date': NOW.isoformat()},
            {'title': 'x', 'country': 'USD', 'date': 'not a date'},
            {'title': 'x', 'country': 'USD', 'date': '1066-10-14T12:00:00Z'},
            {'title': 'Good', 'country': 'USD', 'date': NOW.isoformat()},
        ]
        self.assertEqual([e.title for e in parse_feed(records)], ['Good'])

    def test_limits_duplicates_order_and_holidays(self):
        with self.assertRaisesRegex(ValueError, 'JSON array'):
            parse_feed({'title': 'x'})
        with self.assertRaisesRegex(ValueError, 'large'):
            parse_feed([{}] * 10_001)
        self.assertEqual(len(parse_feed([dict(FULL, id=f'id{i}') for i in range(10_000)])), 10_000)
        late = dict(FULL, id='b', title='B', date='2026-11-20T14:00:00Z')
        early = dict(FULL, id='a', title='A', date='2026-11-20T09:00:00Z')
        self.assertEqual([e.title for e in parse_feed([late, early, dict(early)])], ['A', 'B'])
        holiday = parse_feed([{'title': 'Bank Holiday', 'country': 'JPY', 'date': NOW.isoformat()}])[0]
        self.assertEqual((holiday.impact, holiday.time_label), ('Holiday', 'All Day'))
        self.assertEqual(parse_feed([dict(FULL, actual_tone='great')])[0].actual_tone, '')
        long = parse_feed([dict(FULL, title='T' * 400, actual='9' * 50, source='s' * 90)])[0]
        self.assertEqual((len(long.title), len(long.actual), len(long.source)), (300, 40, 80))

    def test_records_round_trip_through_the_cache_format(self):
        e = parse_feed([dict(FULL, time_label='Tentative', source_day='2026-11-20')])[0]
        record = e.to_record()
        self.assertEqual(record['date'], '2026-11-20T13:30:00+00:00')
        self.assertEqual(
            set(record),
            {'id', 'title', 'country', 'date', 'impact', 'forecast', 'previous', 'actual', 'url', 'source', 'status'}
            | {'period', 'confidence', 'time_label', 'source_day', 'actual_tone', 'revised_from'},
        )
        self.assertEqual(parse_feed([record])[0], e)


class SmallRulesContract(unittest.TestCase):
    def test_impact_names(self):
        cases = {
            ('High', 'x'): 'High',
            (' red ', 'x'): 'High',
            ('3', 'x'): 'High',
            ('Medium', 'x'): 'Medium',
            ('med', 'x'): 'Medium',
            ('orange', 'x'): 'Medium',
            ('2', 'x'): 'Medium',
            ('LOW', 'x'): 'Low',
            ('yellow', 'x'): 'Low',
            ('1', 'x'): 'Low',
            ('', 'x'): 'Low',
            (None, 'x'): 'Low',
            ('unknown', 'x'): 'Low',
            ('Holiday', 'x'): 'Holiday',
            ('high', 'Bank Holiday'): 'Holiday',
            ('low', 'Public Holiday (Thanksgiving)'): 'Holiday',
        }
        for (value, title), expected in cases.items():
            self.assertEqual(normalize_impact(value, title), expected, (value, title))

    def test_countdown_text(self):
        e = parse_feed([dict(FULL, date=NOW.isoformat())])[0]
        for seconds, text in [(0, '00:00:00'), (59, '00:00:59'), (3661, '01:01:01'), (90061, '1d 01:01:01')]:
            self.assertEqual(e.countdown(NOW - timedelta(seconds=seconds)), text)
        self.assertEqual(e.countdown(NOW + timedelta(seconds=1)), 'Released')
        tentative = parse_feed([dict(FULL, time_label='Tentative')])[0]
        self.assertEqual(tentative.countdown(NOW), 'TENTATIVE')
        holiday = parse_feed([{'title': 'Bank Holiday', 'country': 'JPY', 'date': NOW.isoformat()}])[0]
        self.assertEqual(holiday.countdown(NOW), 'HOLIDAY')

    def test_alert_stage_boundaries(self):
        e = parse_feed([dict(FULL, date=NOW.isoformat())])[0]

        def stage_at(seconds_before, stages=(30, 15, 5, 0)):
            found = AlertEngine().check([e], NOW - timedelta(seconds=seconds_before), enabled_stages=stages)
            return [stage for _e, stage in found]

        self.assertEqual(stage_at(1801), [])
        self.assertEqual(stage_at(1800), [30])
        self.assertEqual(stage_at(901), [30])
        self.assertEqual(stage_at(900), [15])
        self.assertEqual(stage_at(301), [15])
        self.assertEqual(stage_at(300), [5])
        self.assertEqual(stage_at(1), [5])
        self.assertEqual(stage_at(0), [0])
        self.assertEqual(stage_at(-30), [0])
        self.assertEqual(stage_at(-31), [])
        self.assertEqual(stage_at(600, stages=(30, 5)), [])  # the 15-minute alert is switched off
        medium = parse_feed([dict(FULL, impact='Medium')])[0]
        self.assertEqual(AlertEngine().check([medium], NOW - timedelta(seconds=60)), [])
        self.assertEqual(AlertEngine().check([e], NOW - timedelta(seconds=60), currencies={'EUR'}), [])

    def test_post_release_check_timing(self):
        events = parse_feed([dict(FULL, actual='', date=NOW.isoformat())])
        for seconds, token in [(44, None), (45, 'b0'), (179, None), (180, 'b1'), (271, None)]:
            fired = set() if seconds != 179 else {f'{NOW.isoformat()}:b0'}
            got = state.due_burst_poll(events, NOW + timedelta(seconds=seconds), fired_bursts=fired)
            self.assertEqual(got, f'{NOW.isoformat()}:{token}' if token else None, seconds)

    def test_time_zone_choices(self):
        self.assertEqual(str(core.desired_timezone('UTC')), 'UTC')
        self.assertEqual(str(core.desired_timezone('Tokyo (UTC+09:00)')), 'Asia/Tokyo')
        self.assertIsNotNone(core.desired_timezone('System local'))
        with mock.patch.object(core, 'ZoneInfo', side_effect=core.ZoneInfoNotFoundError):
            self.assertEqual(core.desired_timezone('Tehran (UTC+03:30)'), timezone(timedelta(hours=3, minutes=30)))
            self.assertEqual(core.desired_timezone('UTC'), UTC)


class OutputsContract(unittest.TestCase):
    def setUp(self):
        self.events = parse_feed(
            [
                FULL,
                {'id': 'h:1', 'title': 'Bank Holiday', 'country': 'JPY', 'date': '2026-11-23T00:00:00Z'},
            ]
        )

    def test_status_file_contents(self):
        cpi = self.events[0]
        snapshot = state.status_snapshot(
            self.events, cpi, state='live', source='biquote', at=NOW, now=NOW - timedelta(minutes=5), tz=UTC
        )
        self.assertEqual(
            snapshot,
            {
                'updated_at': '2026-11-20T13:25:00+00:00',
                'state': 'live',
                'source': 'biquote',
                'last_sync': '2026-11-20T13:30:00+00:00',
                'event_count': 2,
                'next_high_impact': {
                    'uid': 'bq:1',
                    'currency': 'USD',
                    'title': 'Non-Farm Employment Change',
                    'impact': 'High',
                    'instant_utc': '2026-11-20T13:30:00+00:00',
                    'local_time': '2026-11-20T13:30:00+00:00',
                    'countdown': '00:05:00',
                    'seconds_remaining': 300,
                    'forecast': '142K',
                    'previous': '188K',
                    'revised_from': '180K',
                },
            },
        )
        none_ahead = state.status_snapshot([], None, state='cached', source='x', at=None, now=NOW, tz=UTC)
        self.assertEqual((none_ahead['next_high_impact'], none_ahead['last_sync']), (None, None))

    def test_csv_export_bytes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.csv'
            save_csv(path, self.events, UTC)
            self.assertEqual(
                path.read_bytes().decode('utf-8-sig'),
                'Date,Time,Currency,Impact,Event,Actual,Forecast,Previous\r\n'
                '2026-11-20,13:30,USD,High,Non-Farm Employment Change,165K,142K,188K\r\n'
                '2026-11-23,ALL DAY,JPY,Holiday,Bank Holiday,,,\r\n',
            )

    def test_ics_export_bytes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.ics'
            save_ics(path, self.events, UTC)
            text = path.read_bytes().decode('utf-8')
        self.assertRegex(text, r'DTSTAMP:\d{8}T\d{6}Z')
        self.assertEqual(
            re.sub(r'DTSTAMP:\d{8}T\d{6}Z', 'DTSTAMP:<now>', text),
            '\r\n'.join(
                [
                    'BEGIN:VCALENDAR',
                    'VERSION:2.0',
                    'PRODID:-//EconPulse//Economic Calendar//EN',
                    'CALSCALE:GREGORIAN',
                    'METHOD:PUBLISH',
                    'BEGIN:VEVENT',
                    'UID:bq:1@econpulse.local',
                    'DTSTAMP:<now>',
                    'SUMMARY:USD - Non-Farm Employment Change',
                    'DESCRIPTION:Impact: High / Forecast: 142K / Previous: 188K',
                    'DTSTART:20261120T133000Z',
                    'DTEND:20261120T134500Z',
                    'END:VEVENT',
                    'BEGIN:VEVENT',
                    'UID:h:1@econpulse.local',
                    'DTSTAMP:<now>',
                    'SUMMARY:JPY - Bank Holiday',
                    'DESCRIPTION:Impact: Holiday / Forecast:  / Previous: ',
                    'DTSTART;VALUE=DATE:20261123',
                    'DTEND;VALUE=DATE:20261124',
                    'END:VEVENT',
                    'END:VCALENDAR',
                    '',
                ]
            ),
        )


if __name__ == '__main__':
    unittest.main()
