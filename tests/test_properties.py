"""Property-based tests (Hypothesis): rules that must hold for *any* input.

The fuzzer (fuzz/) looks for crashes; these check that the answers are right.
Hypothesis is a dev dependency (requirements-dev.lock), so these tests are
skipped where it isn't installed; CI runs them in the coverage job.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

import helpers  # noqa: F401  (makes the package importable)

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - plain test runs without dev tools
    raise unittest.SkipTest('hypothesis is not installed (pip install -r requirements-dev.lock)') from None

from econpulse import state, storage
from econpulse.core import AlertEngine, _clean_uid, parse_feed, surprise
from econpulse.exports import _PLAIN_NUMBER, csv_cell, ics_text
from econpulse.feed import serialize
from econpulse.providers.biquote import format_value

NOW = datetime(2026, 11, 20, 13, 30, tzinfo=UTC)
json_scalars = st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=60)
json_values = st.recursive(
    json_scalars,
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=5), inner, max_size=3),
    max_leaves=6,
)
SAFE_UID = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:@/-')
CI = settings(max_examples=300, deadline=None)


def record(**overrides):
    base = {'title': 'CPI', 'country': 'USD', 'impact': 'High', 'date': NOW.isoformat()}
    return {**base, **overrides}


class ParsingProperties(unittest.TestCase):
    @CI
    @given(json_values, json_values, json_values, json_values)
    def test_format_value_always_returns_short_text(self, value, unit, multiplier, digits):
        text = format_value(value, unit, multiplier, digits)
        self.assertIsInstance(text, str)
        self.assertLessEqual(len(text), 40)  # never cut off later by the 40-character field cap

    @CI
    @given(
        st.lists(
            st.dictionaries(
                st.sampled_from(['id', 'title', 'country', 'date', 'impact', 'actual', 'forecast', 'time_label']),
                json_values,
            ),
            max_size=8,
        )
    )
    def test_parse_feed_output_is_always_safe_and_round_trips(self, records):
        try:
            events = parse_feed(records)
        except ValueError:
            return  # documented: a non-empty feed with nothing usable is an error, not an empty calendar
        uids = [e.uid for e in events]
        self.assertEqual(len(uids), len(set(uids)))
        for e in events:
            self.assertTrue(e.uid)
            self.assertLessEqual(len(e.uid), 120)
            self.assertTrue(set(e.uid) <= SAFE_UID, e.uid)
            self.assertNotIn('\n', e.time_label + e.title)
        self.assertEqual(parse_feed([serialize(e) for e in events]), events)

    @CI
    @given(st.text(min_size=1, max_size=200), st.text(min_size=1, max_size=200))
    def test_different_provider_ids_never_merge(self, a, b):
        if a.strip() != b.strip():
            self.assertNotEqual(_clean_uid(a, 'fp'), _clean_uid(b, 'fp'))
        self.assertEqual(_clean_uid(a, 'fp'), _clean_uid(a, 'fp'))  # and stay stable


class ExportProperties(unittest.TestCase):
    @CI
    @given(st.text(max_size=80))
    def test_csv_cells_never_start_a_formula(self, text):
        cell = csv_cell(text)
        if not _PLAIN_NUMBER.fullmatch(text):
            self.assertFalse(cell.lstrip(' \t\r\n')[:1] in ('=', '+', '-', '@', '|') and not cell.startswith("'"))
            self.assertNotIn(cell[:1], ('=', '+', '-', '@', '|', '\t', '\r', '\n'))

    @CI
    @given(st.text(max_size=120))
    def test_ics_text_never_contains_a_line_break(self, text):
        out = ics_text(text)
        self.assertNotIn('\r', out)
        self.assertNotIn('\n', out)


class SurpriseProperties(unittest.TestCase):
    @CI
    @given(
        st.decimals(min_value=-10_000, max_value=10_000, places=2, allow_nan=False, allow_infinity=False),
        st.decimals(min_value=-10_000, max_value=10_000, places=2, allow_nan=False, allow_infinity=False),
        st.sampled_from(['', '%', 'K', 'M', 'B']),
    )
    def test_surprise_is_exactly_actual_minus_forecast(self, actual, forecast, unit):
        gap = surprise(f'{actual:.2f}{unit}', f'{forecast:.2f}{unit}')
        number = gap.removesuffix(' pp').removesuffix(unit) if unit else gap
        self.assertEqual(Decimal(number), actual - forecast)


class AlertProperties(unittest.TestCase):
    @CI
    @given(st.lists(st.integers(min_value=-60, max_value=3600), min_size=1, max_size=40))
    def test_no_alert_ever_fires_twice(self, offsets):
        event = parse_feed([record(id='bq:1')])[0]
        engine, seen = AlertEngine(), []
        for seconds in sorted(offsets):
            seen += [stage for _e, stage in engine.check([event], event.instant - timedelta(seconds=seconds))]
        self.assertEqual(len(seen), len(set(seen)))

    @CI
    @given(st.lists(st.integers(min_value=0, max_value=400), min_size=1, max_size=60), st.integers(1, 6))
    def test_post_release_checks_are_bounded_per_release_time(self, ticks, releases):
        events = parse_feed([record(id=f'bq:{i}', title=f'Figure {i}') for i in range(releases)])
        fired: set[str] = set()
        tokens = [state.due_burst_poll(events, NOW + timedelta(seconds=s), fired_bursts=fired) for s in sorted(ticks)]
        self.assertLessEqual(len([t for t in tokens if t]), len(state.BURST_DELAYS))


class SettingsProperties(unittest.TestCase):
    @CI
    @given(st.dictionaries(st.sampled_from([*storage.SCHEMA, 'junk']), json_values))
    def test_any_settings_file_loads_to_a_valid_complete_config(self, raw):
        result = storage.validate_settings(raw)
        self.assertEqual(set(result), set(storage.SCHEMA))
        for name, (_default, check) in storage.SCHEMA.items():
            self.assertTrue(check(result[name]), name)


if __name__ == '__main__':
    unittest.main()
