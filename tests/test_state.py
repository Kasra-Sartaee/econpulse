"""Pure state logic: Actual-published detection, burst polling, starring, notes and next.json."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import helpers  # noqa: F401

from econpulse import state
from econpulse.core import AlertEngine, parse_feed

NOW = datetime(2026, 11, 20, 13, 30, tzinfo=UTC)


def make_events():
    return parse_feed(
        [
            {
                'id': 'bq:cpi',
                'title': 'CPI y/y',
                'country': 'USD',
                'impact': 'High',
                'forecast': '2.8%',
                'previous': '2.9%',
                'date': NOW.isoformat(),
            },
            {
                'id': 'bq:pmi',
                'title': 'Manufacturing PMI',
                'country': 'EUR',
                'impact': 'Medium',
                'forecast': '50.1',
                'previous': '49.8',
                'date': (NOW + timedelta(minutes=10)).isoformat(),
            },
        ]
    )


class ActualPublishedAndBurstTests(unittest.TestCase):
    def test_detects_newly_published_actual_for_watched_and_starred(self):
        before = make_events()
        after = [replace(before[0], actual='2.7%'), replace(before[1], actual='51.0')]
        # By default only High-impact USD CPI triggers
        got = state.detect_published_actuals(before, after, watched={'USD', 'EUR'})
        self.assertEqual([e.uid for e in got], ['bq:cpi'])
        # Starring Medium-impact EUR PMI includes it too
        got_starred = state.detect_published_actuals(
            before, after, watched={'USD'}, starred={state.event_key(before[1])}
        )
        self.assertEqual([e.uid for e in got_starred], ['bq:cpi', 'bq:pmi'])
        # Already-published Actual does not re-trigger
        self.assertEqual(state.detect_published_actuals(after, after, watched={'USD', 'EUR'}), [])

    def test_burst_poll_fires_at_45s_and_180s_only_while_actual_missing(self):
        events = make_events()
        fired: set[str] = set()
        # Too early (+20s)
        self.assertIsNone(
            state.due_burst_poll(events, NOW + timedelta(seconds=20), watched={'USD'}, fired_bursts=fired)
        )
        # First burst (+50s)
        tok1 = state.due_burst_poll(events, NOW + timedelta(seconds=50), watched={'USD'}, fired_bursts=fired)
        self.assertEqual(tok1, f'{NOW.isoformat()}:b0')
        # Does not repeat at +60s
        self.assertIsNone(
            state.due_burst_poll(events, NOW + timedelta(seconds=60), watched={'USD'}, fired_bursts=fired)
        )
        # Second burst (+185s)
        tok2 = state.due_burst_poll(events, NOW + timedelta(seconds=185), watched={'USD'}, fired_bursts=fired)
        self.assertEqual(tok2, f'{NOW.isoformat()}:b1')
        # Stops after second burst
        self.assertIsNone(
            state.due_burst_poll(events, NOW + timedelta(seconds=200), watched={'USD'}, fired_bursts=fired)
        )
        # Never fires if Actual is already present
        with_actual = [replace(events[0], actual='2.7%')]
        self.assertIsNone(
            state.due_burst_poll(with_actual, NOW + timedelta(seconds=50), watched={'USD'}, fired_bursts=set())
        )

    def test_burst_poll_is_per_release_time_not_per_release(self):
        # Five US figures at 13:30 must cost two extra refreshes, not ten.
        same_minute = parse_feed(
            [
                {'id': f'bq:{i}', 'title': f'Figure {i}', 'country': 'USD', 'impact': 'High', 'date': NOW.isoformat()}
                for i in range(5)
            ]
        )
        fired: set[str] = set()
        tokens = []
        for seconds in range(0, 300, 5):
            token = state.due_burst_poll(same_minute, NOW + timedelta(seconds=seconds), fired_bursts=fired)
            if token:
                tokens.append(token)
        self.assertEqual(tokens, [f'{NOW.isoformat()}:b0', f'{NOW.isoformat()}:b1'])

    def test_burst_poll_after_a_late_start_takes_only_the_latest_stage(self):
        fired: set[str] = set()
        late = NOW + timedelta(seconds=200)
        self.assertEqual(state.due_burst_poll(make_events(), late, fired_bursts=fired), f'{NOW.isoformat()}:b1')
        self.assertIsNone(state.due_burst_poll(make_events(), late + timedelta(seconds=5), fired_bursts=fired))

    def test_old_releases_are_not_announced_as_just_published(self):
        # After a restart or a laptop wake, the first fetch fills in hours-old figures.
        before = make_events()
        after = [replace(before[0], actual='2.7%'), before[1]]
        fresh = state.detect_published_actuals(before, after, now=NOW + timedelta(minutes=3))
        self.assertEqual([e.uid for e in fresh], ['bq:cpi'])
        self.assertEqual(state.detect_published_actuals(before, after, now=NOW + timedelta(hours=3)), [])

    def test_long_titles_can_be_starred(self):
        # The star key is capped at 120 characters (the settings limit) everywhere it is used.
        long = replace(make_events()[1], title='Very long indicator name ' * 8)
        key = state.event_key(long)
        self.assertLessEqual(len(key), 120)
        found = AlertEngine().check([long], NOW, starred={key})
        self.assertEqual([e.uid for e, _stage in found], ['bq:pmi'])

    def test_starred_medium_event_triggers_alert_engine(self):
        events = make_events()
        pmi = events[1]
        engine = AlertEngine()
        # Without star: Medium impact is ignored
        self.assertEqual(engine.check([pmi], NOW), [])
        # With star: fires 15-min stage
        found = engine.check([pmi], NOW, starred={state.event_key(pmi)})
        self.assertEqual([(e.uid, stage) for e, stage in found], [('bq:pmi', 15)])


class StatusSnapshotAndNotesTests(unittest.TestCase):
    def test_status_snapshot_and_file_write(self):
        events = make_events()
        snap = state.status_snapshot(
            events,
            events[0],
            state='live',
            source='biquote',
            at=NOW,
            now=NOW - timedelta(minutes=5),
            tz=UTC,
        )
        self.assertEqual(snap['state'], 'live')
        self.assertEqual(snap['next_high_impact']['currency'], 'USD')
        self.assertEqual(snap['next_high_impact']['seconds_remaining'], 300)
        with TemporaryDirectory() as td:
            state.write_status_snapshot(snap, Path(td))
            loaded = json.loads((Path(td) / 'next.json').read_text(encoding='utf-8'))
            self.assertEqual(loaded['next_high_impact']['title'], 'CPI y/y')

    def test_event_notes_save_reload_and_clear(self):
        with TemporaryDirectory() as td:
            folder = Path(td)
            state.save_event_note('USD|CPI y/y', 'Fade spike if core > 0.4%', folder)
            self.assertEqual(state.load_event_notes(folder), {'USD|CPI y/y': 'Fade spike if core > 0.4%'})
            state.save_event_note('USD|CPI y/y', '   ', folder)
            self.assertEqual(state.load_event_notes(folder), {})


if __name__ == '__main__':
    unittest.main()
