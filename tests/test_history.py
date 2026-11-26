"""The local release history behind the details window's "Recent releases"."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse import history
from econpulse.core import parse_feed, series_key

NOW = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)


def release(months_ago, actual='1.0%', forecast='0.9%', title='CPI y/y', utc_offset_hours=0):
    """A released CPI print ``months_ago`` months back, written with the given UTC offset."""
    when = (NOW - timedelta(days=30 * months_ago)).replace(hour=13, minute=30)
    stamp = when.astimezone(timezone(timedelta(hours=utc_offset_hours))).isoformat()
    return parse_feed([{'title': title, 'country': 'USD', 'date': stamp, 'actual': actual, 'forecast': forecast}])[0]


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_releases_accumulate_newest_last_and_show_newest_first(self):
        for months in (3, 1, 2):  # downloads arrive in any order
            history.record([release(months)], NOW, self.folder)
        current = release(0, actual='')
        past = history.for_event(current, folder=self.folder)
        self.assertEqual([p['at'] for p in past], sorted((p['at'] for p in past), reverse=True))
        self.assertEqual(len(past), 3)

    def test_the_same_release_is_kept_once_and_revisions_replace_it(self):
        history.record([release(1, actual='2.0%')], NOW, self.folder)
        history.record([release(1, actual='2.0%')], NOW, self.folder)
        history.record([release(1, actual='2.1%')], NOW, self.folder)  # revised later
        series = history.load(self.folder)[series_key(release(1))]
        self.assertEqual([item['actual'] for item in series], ['2.1%'])

    def test_unpublished_future_and_untimed_items_are_not_recorded(self):
        future = replace(release(1), instant=NOW + timedelta(hours=1))
        no_actual = release(2, actual='')
        untimed = replace(release(3), time_label='Tentative')
        history.record([future, no_actual, untimed], NOW, self.folder)
        self.assertEqual(history.load(self.folder), {})

    def test_size_is_capped_per_indicator_and_overall(self):
        archive: dict = {}
        history.merge(archive, [release(m) for m in range(30)], NOW)
        self.assertEqual(len(archive[series_key(release(0))]), history.PER_SERIES)
        many = [release(0, title=f'Indicator {i}') for i in range(history.MAX_SERIES + 20)]
        history.merge(archive, many, NOW)
        self.assertLessEqual(len(archive), history.MAX_SERIES)

    def test_different_utc_offsets_sort_by_real_time(self):
        # 13:30 UTC reported as 08:30-05:00 must sort with, not before, other UTC entries.
        early = release(2, utc_offset_hours=-5)
        late = release(1)
        history.record([late, early], NOW, self.folder)
        past = history.for_event(release(0, actual=''), folder=self.folder)
        self.assertEqual([p['at'] for p in past], [late.instant.isoformat(), early.instant.isoformat()])

    def test_a_damaged_file_is_ignored(self):
        (self.folder / history.HISTORY_FILE).write_text(json.dumps({'x': 'not a list', 'y': [1, {'at': 3}]}))
        self.assertEqual(history.load(self.folder), {})
        history.record([release(1)], NOW, self.folder)  # and is replaced by a good one
        self.assertEqual(len(history.load(self.folder)), 1)


class UtcTests(unittest.TestCase):
    def test_parsed_instants_are_always_utc(self):
        e = parse_feed([{'title': 'CPI', 'country': 'USD', 'date': '2026-11-20T08:30:00-05:00'}])[0]
        self.assertEqual(e.instant.utcoffset(), timedelta(0))
        self.assertEqual(e.instant, datetime(2026, 11, 20, 13, 30, tzinfo=UTC))


if __name__ == '__main__':
    unittest.main()
