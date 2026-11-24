"""Domain model: parsing, time handling, alerts."""

from datetime import UTC, datetime, timedelta, timezone
import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse.core import AlertEngine, desired_timezone, parse_date, parse_feed, weekly_sections


class EconomicCalendarTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

    def event(self, minutes=10, impact='High', currency='USD', name='CPI m/m'):
        raw = [
            {
                'title': name,
                'country': currency,
                'date': (self.now + timedelta(minutes=minutes)).isoformat(),
                'impact': impact,
                'forecast': '0.3%',
                'previous': '0.2%',
            }
        ]
        return parse_feed(raw)[0]

    def test_bank_holiday_has_own_impact_even_with_low_marker(self):
        e = self.event(impact='Low', name='Bank Holiday')
        self.assertEqual(e.impact, 'Holiday')
        self.assertEqual(e.when_text(UTC), 'ALL DAY')
        self.assertEqual(e.countdown(self.now), 'HOLIDAY')

    def test_holiday_keeps_source_civil_date_across_zone_boundaries(self):
        e = parse_feed(
            [{'title': 'Bank Holiday', 'country': 'USD', 'impact': 'Holiday', 'date': '2026-11-11T00:00:00-05:00'}]
        )[0]
        self.assertEqual(e.display_day(timezone(timedelta(hours=-12))).isoformat(), '2026-11-11')

    def test_timezone_requires_offset(self):
        with self.assertRaises(ValueError):
            parse_date('2026-11-11T10:00:00')
        self.assertEqual(self.event().instant.tzinfo, UTC)

    def test_tehran_offset(self):
        self.assertEqual(self.now.astimezone(desired_timezone('Tehran (UTC+03:30)')).strftime('%H:%M'), '15:30')

    def test_duplication_and_bad_rows(self):
        x = {'title': 'CPI', 'country': 'USD', 'impact': 'High', 'date': self.now.isoformat()}
        result = parse_feed([x, x, {'title': 'Bad', 'date': 'notadate', 'country': 'EUR'}])
        self.assertEqual(len(result), 1)

    def test_untrusted_text_is_capped_and_currency_checked(self):
        rows = [
            {'title': 'X' * 5000, 'country': 'USD', 'date': self.now.isoformat(), 'actual': '9' * 500},
            {'title': 'Bad currency', 'country': 'US DOLLAR', 'date': self.now.isoformat()},
        ]
        events = parse_feed(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].title), 300)
        self.assertEqual(len(events[0].actual), 40)

    def test_unknown_tone_is_ignored(self):
        e = parse_feed([{'title': 'CPI', 'country': 'USD', 'date': self.now.isoformat(), 'actual_tone': 'evil'}])[0]
        self.assertEqual(e.actual_tone, '')

    def test_weekly_sections_keep_every_release(self):
        events = parse_feed(
            [
                {
                    'country': 'USD',
                    'title': 'Mon',
                    'date': '2026-11-09T12:00:00+00:00',
                    'impact': 'High',
                    'actual': '5',
                },
                {'country': 'CAD', 'title': 'Holiday', 'date': '2026-11-11T12:00:00+00:00', 'impact': 'Holiday'},
                {'country': 'EUR', 'title': 'Wed', 'date': '2026-11-11T15:00:00+00:00', 'impact': 'Medium'},
                {'country': 'JPY', 'title': 'Fri', 'date': '2026-11-13T11:00:00+00:00', 'impact': 'High'},
            ]
        )
        events.sort(key=lambda e: (e.display_day(UTC), e.instant))
        groups = weekly_sections(events, UTC)
        self.assertEqual([day.isoformat() for day, _ in groups], ['2026-11-09', '2026-11-11', '2026-11-13'])
        self.assertEqual([len(group) for _, group in groups], [1, 2, 1])

    def test_alerts_staged_and_deduped(self):
        engine, e = AlertEngine(), self.event(25)
        self.assertEqual([stage for _, stage in engine.check([e], self.now)], [30])
        self.assertEqual(engine.check([e], self.now), [])
        self.assertEqual([stage for _, stage in engine.check([e], self.now + timedelta(minutes=13))], [15])
        self.assertEqual([stage for _, stage in engine.check([e], self.now + timedelta(minutes=22))], [5])
        self.assertEqual([stage for _, stage in engine.check([e], self.now + timedelta(minutes=25))], [0])
        self.assertEqual(engine.check([e], self.now + timedelta(minutes=26)), [])
        self.assertEqual(AlertEngine(engine.fired).check([e], self.now + timedelta(minutes=25)), [])

    def test_never_time_alert_holidays(self):
        self.assertEqual(AlertEngine().check([self.event(5, impact='Holiday', name='Bank Holiday')], self.now), [])

    def test_currency_filters_alerts(self):
        self.assertEqual(AlertEngine().check([self.event(5, currency='USD')], self.now, currencies=['EUR']), [])

    def test_time_bounds(self):
        self.assertEqual(AlertEngine().check([self.event(130)], self.now), [])

    def test_uid_and_time_label_are_sanitised_and_capped(self):
        raw = [
            {
                'id': 'evil\r\nBEGIN:VALARM\r\n' + 'x' * 500,
                'title': 'CPI',
                'country': 'USD',
                'date': self.now.isoformat(),
                'time_label': 'Tentative\r\nLINE2',
            }
        ]
        e = parse_feed(raw)[0]
        self.assertLessEqual(len(e.uid), 120)
        self.assertNotIn('\r', e.uid)
        self.assertNotIn('\n', e.uid)
        self.assertNotIn('\r', e.time_label)
        self.assertNotIn('\n', e.time_label)

    def test_provider_ids_never_collide_after_cleaning(self):
        def uid(raw):
            return parse_feed([{'id': raw, 'title': 'CPI', 'country': 'USD', 'date': self.now.isoformat()}])[0].uid

        self.assertEqual(uid('bq:123'), 'bq:123')  # plain ids are kept exactly
        self.assertNotEqual(uid('x y'), uid('x_y'))
        self.assertEqual(uid('x y'), uid('x y'))  # still stable across fetches
        self.assertNotEqual(uid('a' * 130), uid('a' * 131))  # long ids are hashed, not truncated
        self.assertLessEqual(len(uid('a' * 500)), 120)


if __name__ == '__main__':
    unittest.main()
