"""Display-window tests: releases never disappear just because time passed."""

from datetime import datetime, timedelta, timezone
import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse.app import EconPulse
from econpulse.core import parse_feed

NOW = datetime(2026, 11, 11, 17, 30, tzinfo=timezone.utc)


class WidgetSelectionTests(unittest.TestCase):
    def setUp(self):
        obj = EconPulse.__new__(EconPulse)
        obj.cfg = {'currencies': [], 'impacts': ['High', 'Medium', 'Low'], 'holiday': True}
        obj.now = lambda: NOW
        obj.tz = lambda: timezone.utc
        obj.tab = 'all'
        obj.widget_period = 'day'

        class V:
            def get(self):
                return ''

        obj.search_var = V()
        records = []
        for i in range(55):
            records.append(
                dict(
                    country='USD',
                    title=f'Event {i}',
                    impact='High',
                    date=(NOW.replace(hour=0, minute=0) + timedelta(minutes=i * 20)).isoformat(),
                    actual=str(i) + 'K' if i * 20 < 1050 else '',
                )
            )
        records.extend(
            [
                dict(country='USD', title='Bank Holiday', impact='Holiday', date='2026-11-11T13:00:00+00:00'),
                dict(country='CAD', title='Bank Holiday', impact='Holiday', date='2026-11-11T13:00:00+00:00'),
                dict(country='EUR', title='Bank Holiday', impact='Holiday', date='2026-11-11T13:00:00+00:00'),
                dict(country='USD', title='Next week indicator', impact='High', date='2026-11-15T13:00:00+00:00'),
            ]
        )
        obj.events = parse_feed(records)
        self.obj = obj

    def test_today_contains_all_past_releases_and_holidays_no_cap(self):
        events = self.obj.visible(widget=True)
        self.assertEqual(len(events), 58)
        self.assertEqual(len([e for e in events if e.is_holiday]), 3)
        self.assertEqual(len([e for e in events if e.actual]), 53)

    def test_week_excludes_next_sunday(self):
        self.obj.widget_period = 'week'
        events = self.obj.visible(widget=True)
        self.assertEqual(len(events), 58)

    def test_currency_selector_filters_holidays_and_releases(self):
        self.obj.cfg['currencies'] = ['CAD']
        events = self.obj.visible(widget=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].impact, 'Holiday')

    def test_holiday_filter_can_be_switched_off(self):
        self.obj.cfg['holiday'] = False
        events = self.obj.visible(widget=True)
        self.assertEqual(len(events), 55)


if __name__ == '__main__':
    unittest.main()
