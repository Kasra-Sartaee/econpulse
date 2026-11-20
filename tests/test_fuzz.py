"""The fuzz target as a quick deterministic test, plus regressions for what fuzzing found.

The real fuzzing (coverage-guided, with Atheris) runs in CI: .github/workflows/fuzz.yml.
"""

from datetime import UTC, datetime
import random
import sys
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, str(ROOT / 'fuzz'))

import fuzz_calendar_data as target

from econpulse import feed
from econpulse.core import _text, parse_feed
from econpulse.providers import FALLBACK, PROVIDERS
from econpulse.providers.biquote import format_value


class FuzzTargetTests(unittest.TestCase):
    def test_seed_corpus(self):
        seeds = sorted((ROOT / 'fuzz' / 'corpus').glob('*.json'))
        self.assertGreaterEqual(len(seeds), 3)
        for seed in seeds:
            with self.subTest(seed.name):
                target.TestOneInput(seed.read_bytes())

    def test_random_inputs(self):
        rng = random.Random(2026)
        for _ in range(3000):
            target.TestOneInput(bytes(rng.getrandbits(8) for _ in range(rng.randrange(1, 500))))


class FoundByFuzzingTests(unittest.TestCase):
    def test_format_value_accepts_anything(self):
        cases = [
            ((1.5, 'number', ['millions'], 1), '1.5'),  # a list as the multiplier
            ((10**400, 'number', None, 0), ''),  # an integer too large for a float
            ((0.25, 'percent', None, True), '0.25%'),  # True is an int in Python
            ((float('inf'), 'percent', None, 1), ''),
            (({'a': 1}, None, None, None), ''),
            (('n/a', None, None, None), 'n/a'),
            ((152, 'number', 'thousands', 0), '152K'),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(format_value(*args), expected)

    def test_absurd_dates_are_dropped(self):
        rows = [
            {'title': 'Far future', 'country': 'USD', 'date': '9999-12-31T23:00:00-05:00'},
            {'title': 'Far past', 'country': 'USD', 'date': '0001-01-01T01:00:00+05:00'},
            {'title': 'Normal', 'country': 'USD', 'date': '2026-11-20T08:30:00-05:00'},
        ]
        self.assertEqual([e.title for e in parse_feed(rows)], ['Normal'])

    def test_capped_text_has_no_trailing_space(self):
        self.assertEqual(_text('a' * 299 + '  b', 300), 'a' * 299)

    def test_an_unexpected_parser_error_still_uses_the_fallbacks(self):
        now = datetime(2026, 11, 20, 12, tzinfo=UTC)
        backup = parse_feed([{'title': 'Backup', 'country': 'USD', 'date': now.isoformat()}])
        with (
            mock.patch.object(PROVIDERS['biquote'], 'fetch', side_effect=TypeError('parser bug')),
            mock.patch.object(PROVIDERS[FALLBACK], 'fetch', return_value=backup),
            mock.patch.object(feed, 'load_cache', return_value=feed.FeedResult([], None, 'no cache', is_cache=True)),
        ):
            result = feed.fetch_events('biquote', now=now)
        self.assertEqual(result.provider, FALLBACK)
        self.assertTrue(result.failed)
        self.assertIn('unreadable response', result.warning)


if __name__ == '__main__':
    unittest.main()
