"""Data providers and the fetch/fallback/cache pipeline.

Every payload here is invented: same field shapes as the real services, made-up
events and figures. No network access.
"""

from datetime import date, timedelta, timezone
import io
import os
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError

from helpers import NOW, collect_tk_garbage

from econpulse import USER_AGENT, feed
from econpulse.providers import PROVIDERS, KeyRejected, ProviderError, RateLimited, base, biquote, financecalendar


def biquote_days(params):
    """The days a real biquote request covers: 'from' inclusive, 'to' an exclusive midnight."""
    first, until = date.fromisoformat(params['from']), date.fromisoformat(params['to'])
    if until <= first:
        raise ProviderError('HTTP 400')  # biquote: "'to' must be after 'from'"
    return [(first + timedelta(days=i)).isoformat() for i in range((until - first).days)]


def setUpModule():
    # biquote fetches on worker threads; free earlier modules' Tk roots on this thread first.
    collect_tk_garbage()


BIQUOTE_ROWS = [
    {
        'id': 'demo:1',
        'eventId': 'demo:e1',
        'time': '2026-11-11T13:30:00Z',
        'period': '2026-10-01T00:00:00Z',
        'countryCode': 'US',
        'currency': 'USD',
        'name': 'Sample Payrolls',
        'importance': 'high',
        'type': 'indicator',
        'unit': 'job',
        'multiplier': 'thousands',
        'digits': 0,
        'actual': 101,
        'forecast': 90,
        'previous': 80,
        'revisedPrevious': 85,
        'timeMode': 'exact',
        'sourceUrl': 'https://example.org/payrolls',
    },
    {
        'id': 'demo:2',
        'time': '2026-11-11T09:00:00Z',
        'currency': 'EUR',
        'name': 'Sample Price Index m/m',
        'importance': 'medium',
        'type': 'indicator',
        'unit': 'percent',
        'multiplier': 'none',
        'digits': 1,
        'actual': -0.2,
        'forecast': 0.0,
        'previous': 0.1,
        'revisedPrevious': None,
        'timeMode': 'exact',
    },
    {
        'id': 'demo:3',
        'time': '2026-11-12T00:00:00Z',
        'currency': 'JPY',
        'name': 'Sample Holiday',
        'importance': 'none',
        'type': 'holiday',
        'unit': 'none',
        'multiplier': 'none',
        'digits': 0,
        'actual': None,
        'forecast': None,
        'previous': None,
        'timeMode': 'date',
    },
    {
        'id': 'demo:4',
        'time': '2026-11-13T10:00:00Z',
        'currency': 'GBP',
        'name': 'Sample Speech',
        'importance': 'low',
        'type': 'event',
        'unit': None,
        'multiplier': None,
        'digits': 0,
        'actual': None,
        'forecast': None,
        'previous': None,
        'timeMode': 'tentative',
    },
    {
        'id': 'demo:5',
        'time': '2026-11-13T15:30:00Z',
        'currency': 'USD',
        'name': 'Sample Stocks Change',
        'importance': 'low',
        'type': 'indicator',
        'unit': 'barrel',
        'multiplier': 'millions',
        'digits': 3,
        'actual': -0.865,
        'forecast': None,
        'previous': 1.5,
        'timeMode': 'exact',
    },
]

FC_BODY = {
    'from': '2026-11-01',
    'to': '2026-11-21',
    'count': 2,
    'total': 2,
    'events': [
        {
            'id': 'sample-cpi',
            'name': 'Sample CPI',
            'title': 'Sample CPI October',
            'country': 'US',
            'impact': 'high',
            'date': '2026-11-11',
            'release_at_utc': '2026-11-11T13:30:00+00:00',
            'all_day': False,
            'period': '2026-10',
            'consensus': '2.9',
            'prior': '3.0',
            'actual': '3.1',
            'unit': '% y/y',
            'time_precision': 'minute',
            'source_name': 'Sample Agency',
            'url': 'https://www.financecalendar.com/event/sample-cpi/',
        },
        {
            'id': 'sample-holiday',
            'name': 'Sample Holiday',
            'country': 'GB',
            'impact': 'low',
            'date': '2026-11-12',
            'release_at_utc': None,
            'all_day': True,
            'holiday_status': 'closed',
            'time_precision': 'day',
        },
        {
            'id': 'skip-me',
            'name': 'Unknown country',
            'country': 'ZZ',
            'impact': 'high',
            'release_at_utc': '2026-11-11T13:30:00+00:00',
        },
    ],
}


class ValueFormattingTests(unittest.TestCase):
    def test_units_and_multipliers(self):
        cases = [
            ((0.2, 'percent', 'none', 1), '0.2%'),
            ((3.38, 'barrel', 'millions', 2), '3.38M'),
            ((165, 'job', 'thousands', 0), '165K'),
            ((443.16, 'usd', 'billions', 2), '443.16B'),
            ((3.405, 'usd', 'trillions', 3), '3.405T'),
            ((51.3, 'none', 'none', 1), '51.3'),
            ((-0.0, 'percent', 'none', 1), '0.0%'),
            ((None, 'percent', 'none', 1), ''),
            ((54.9, None, None, 2), '54.90'),
            ((1e57, None, None, None), ''),  # absurd magnitude: missing, never a truncated wrong number
        ]
        for args, expected in cases:
            self.assertEqual(biquote.format_value(*args), expected, args)


class BiquoteTests(unittest.TestCase):
    def setUp(self):
        PROVIDERS['biquote'].reset()  # the provider remembers its last full download

    def test_mapping(self):
        from econpulse.core import parse_feed

        events = {e.title: e for e in parse_feed(biquote.to_records(BIQUOTE_ROWS))}
        payrolls = events['Sample Payrolls']
        self.assertEqual((payrolls.currency, payrolls.impact), ('USD', 'High'))
        self.assertEqual((payrolls.actual, payrolls.forecast, payrolls.previous), ('101K', '90K', '85K'))
        self.assertEqual(payrolls.revised_from, '80K')
        self.assertEqual(payrolls.uid, 'bq:demo:1')
        self.assertEqual(payrolls.period, 'Oct 2026')
        self.assertEqual(payrolls.url, 'https://example.org/payrolls')
        self.assertEqual(events['Sample Price Index m/m'].actual, '-0.2%')
        holiday = events['Sample Holiday']
        self.assertTrue(holiday.is_holiday and holiday.is_untimed)
        self.assertEqual(holiday.display_day(timezone(timedelta(hours=-10))).isoformat(), '2026-11-12')
        self.assertEqual(events['Sample Speech'].time_label, 'Tentative')
        self.assertEqual(events['Sample Stocks Change'].actual, '-0.865M')

    def test_fetch_requests_weekly_chunks(self):
        calls = []

        def fake(url, params=None, **kw):
            calls.append(params)
            return BIQUOTE_ROWS if params['from'] == '2026-11-01' else []

        with mock.patch.object(biquote, 'http_get_json', side_effect=fake):
            events = PROVIDERS['biquote'].fetch(NOW)
        self.assertEqual(len(events), 5)
        self.assertEqual(min(c['from'] for c in calls), '2026-11-01')
        self.assertEqual(max(c['to'] for c in calls), '2026-11-22')  # 'to' is exclusive
        self.assertLessEqual(len(calls), 3)

    def test_every_day_of_the_window_is_requested(self):
        # Regression: biquote's 'to' is exclusive, so asking for (start, stop) silently
        # dropped the last day of each week: Fridays at the span edges came back empty.
        def fake(url, params=None, **kw):
            return [dict(BIQUOTE_ROWS[0], id=f'{d}', time=f'{d}T13:30:00Z') for d in biquote_days(params)]

        with mock.patch.object(biquote, 'http_get_json', side_effect=fake):
            events = PROVIDERS['biquote'].fetch(NOW)
        days = {e.instant.date() for e in events}
        window = [NOW.date() + timedelta(days=i) for i in range(-10, 11)]
        self.assertEqual(sorted(days), window)

    def test_full_page_is_split(self):
        full = [dict(BIQUOTE_ROWS[0], id=f'x{i}') for i in range(biquote.PAGE_LIMIT)]
        calls = []

        def fake(url, params=None, **kw):
            calls.append(params)
            if params['from'] == '2026-11-01' and params['to'] == '2026-11-08':
                return full
            return BIQUOTE_ROWS

        with mock.patch.object(biquote, 'http_get_json', side_effect=fake):
            events = PROVIDERS['biquote'].fetch(NOW)
        self.assertEqual(len(events), len(BIQUOTE_ROWS))  # the full page was discarded and re-requested
        split_calls = [
            c
            for c in calls
            if ('2026-11-01' <= c['from'] <= '2026-11-07' and c['to'] != '2026-11-08')
            or (c['from'] != '2026-11-01' and c['to'] == '2026-11-08')
        ]
        self.assertGreaterEqual(len(split_calls), 2)

    def test_dense_weeks_never_drop_days_when_the_split_budget_runs_out(self):
        # Every span is over-full: the provider splits within its budget, then keeps capped pages.
        calls = []

        def fake(url, params=None, **kw):
            calls.append(params)
            day = params['from']
            return [dict(BIQUOTE_ROWS[0], id=f'{day}-{i}', time=f'{day}T13:30:00Z') for i in range(biquote.PAGE_LIMIT)]

        with mock.patch.object(biquote, 'http_get_json', side_effect=fake):
            events = PROVIDERS['biquote'].fetch(NOW)
        self.assertLessEqual(len(calls), 3 + biquote.BiquoteProvider.MAX_EXTRA_REQUESTS)
        days = {e.instant.date().isoformat() for e in events}
        for c in calls:
            self.assertIn(c['from'], days)  # nothing fetched was thrown away

    def test_between_hourly_full_refreshes_only_yesterday_to_tomorrow_is_downloaded(self):
        def row(i, day):
            return dict(BIQUOTE_ROWS[0], id=f'{day}-{i}', name=f'Figure {i}', time=f'{day}T13:30:00Z')

        calls = []
        actual = {'2026-11-11': ''}

        def fake(url, params=None, **kw):
            calls.append((params['from'], params['to']))
            return [dict(row(0, d), actual=actual.get(d, 1.0)) for d in biquote_days(params)]

        provider = PROVIDERS['biquote']
        with mock.patch.object(biquote, 'http_get_json', side_effect=fake):
            full = provider.fetch(NOW)
            self.assertEqual(len(calls), 3)
            self.assertEqual(next(e for e in full if e.instant.date().isoformat() == '2026-11-11').actual, '')
            calls.clear()
            actual['2026-11-11'] = 2.5  # today's figure is published
            later = provider.fetch(NOW + timedelta(minutes=15))
            self.assertEqual(calls, [('2026-11-10', '2026-11-13')])  # one request, not three
            self.assertEqual(len(later), len(full))  # the rest of the window is kept
            today = next(e for e in later if e.instant.date().isoformat() == '2026-11-11')
            self.assertEqual(today.actual, biquote.format_value(2.5, 'job', 'thousands', 0))  # refreshed
            calls.clear()
            provider.fetch(NOW + timedelta(minutes=61))
            self.assertEqual(len(calls), 3)  # hourly full refresh
            calls.clear()
            provider.fetch(NOW + timedelta(hours=13))  # past midnight UTC: the window moved
            self.assertEqual(len(calls), 3)


class FinanceCalendarTests(unittest.TestCase):
    def test_mapping_and_key_header(self):
        seen = {}

        def fake(url, params=None, headers=None, **kw):
            seen.update(headers=headers, params=params)
            return FC_BODY

        with mock.patch.object(financecalendar, 'http_get_json', side_effect=fake):
            events = {e.title: e for e in PROVIDERS['financecalendar'].fetch(NOW, key='fc_live_test')}
        self.assertEqual(seen['headers'], {'X-API-Key': 'fc_live_test'})
        self.assertEqual(seen['params']['include'], 'holidays')
        cpi = events['Sample CPI']
        self.assertEqual((cpi.currency, cpi.actual, cpi.forecast, cpi.previous), ('USD', '3.1%', '2.9%', '3.0%'))
        self.assertIn('Sample Agency', cpi.source)
        self.assertTrue(events['Sample Holiday'].is_holiday)
        self.assertEqual(events['Sample Holiday'].currency, 'GBP')
        self.assertNotIn('Unknown country', events)

    def test_missing_key_fails_cleanly(self):
        with self.assertRaises(ProviderError):
            PROVIDERS['financecalendar'].fetch(NOW, key='')


class HttpClientTests(unittest.TestCase):
    def test_honest_user_agent_and_https_only(self):
        self.assertTrue(USER_AGENT.startswith('EconPulse/'))
        self.assertNotIn('Mozilla', USER_AGENT)
        with self.assertRaises(ProviderError):
            base.http_get_json('http://example.org/x')

    def _http_error(self, code, headers=None):
        return HTTPError('https://example.org', code, 'x', headers or {}, io.BytesIO(b''))

    def test_rate_limit_and_key_errors_are_typed(self):
        error = self._http_error(429, {'Retry-After': '120'})
        with mock.patch.object(base, 'urlopen', side_effect=error), self.assertRaises(RateLimited) as caught:
            base.http_get_json('https://example.org/x')
        self.assertEqual(caught.exception.retry_after, 120)
        with mock.patch.object(base, 'urlopen', side_effect=self._http_error(401)), self.assertRaises(KeyRejected):
            base.http_get_json('https://example.org/x')
        self.assertIsNone(base._retry_after('soon'))
        self.assertEqual(base._retry_after('999999'), 24 * 3600)

    def test_redirects_block_downgrade_localhost_and_strip_api_key_cross_origin(self):
        from urllib.request import Request

        handler = base._SafeRedirectHandler()
        req = Request('https://api.example.org/v1', headers={'X-API-Key': 'secret', 'Accept': 'application/json'})
        for unsafe in ('http://api.example.org/v1', 'https://localhost/secret', 'https://127.0.0.1/secret'):
            with self.assertRaises(ProviderError):
                handler.redirect_request(req, None, 302, 'Found', {}, unsafe)
        cross = handler.redirect_request(req, None, 302, 'Found', {}, 'https://cdn.other.org/data')
        self.assertNotIn('X-api-key', cross.headers)
        self.assertNotIn('X-API-Key', cross.headers)
        same = handler.redirect_request(req, None, 302, 'Found', {}, 'https://api.example.org/v2')
        self.assertEqual(same.get_header('X-api-key'), 'secret')
        with self.assertRaises(ProviderError):
            base.http_get_json('https://127.0.0.1/local')

    def test_gzip_decompression_zip_bomb_cap_and_304(self):
        import gzip

        payload = gzip.compress(b'[{"ok": 1}]')

        class Resp:
            headers = {'Content-Encoding': 'gzip', 'ETag': '"v1"'}

            def read(self, n=-1):
                return payload[:n] if n >= 0 else payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        validators = {}
        with mock.patch.object(base, 'urlopen', return_value=Resp()):
            data = base.http_get_json('https://example.org/x', validators=validators)
        self.assertEqual(data, [{'ok': 1}])
        self.assertEqual(validators['etag'], '"v1"')
        # Zip-bomb cap: decompressing beyond limit must fail cleanly
        bomb = gzip.compress(b'A' * 4096)
        with self.assertRaises(ProviderError):
            base._decompress_gzip(bomb, limit=1024)
        # HTTP 304 raises NotModified
        with (
            mock.patch.object(base, 'urlopen', side_effect=self._http_error(304)),
            self.assertRaises(base.NotModified),
        ):
            base.http_get_json('https://example.org/x', validators=validators)


class PipelineTests(unittest.TestCase):
    """fetch_events: selected source -> recent cache -> official export -> stale cache."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {'APPDATA': self.tmp.name, 'XDG_CONFIG_HOME': self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def patch(self, provider, **kw):
        return mock.patch.object(PROVIDERS[provider], 'fetch', **kw)

    def sample(self, actual='1%'):
        from econpulse.core import parse_feed

        return parse_feed([{'title': 'Sample', 'country': 'USD', 'date': NOW.isoformat(), 'actual': actual}])

    def test_success_is_cached_and_reloaded(self):
        with self.patch('biquote', return_value=self.sample()):
            result = feed.fetch_events('biquote', now=NOW)
        self.assertFalse(result.failed)
        self.assertTrue(result.has_actuals)
        cached = feed.load_cache()
        self.assertEqual([e.title for e in cached.events], ['Sample'])
        self.assertEqual(cached.provider, 'biquote')

    def test_falls_back_to_the_official_export(self):
        with (
            self.patch('biquote', side_effect=RateLimited('HTTP 429', 600)),
            self.patch('ff_export', return_value=self.sample(actual='')),
        ):
            result = feed.fetch_events('biquote', now=NOW)
        self.assertTrue(result.failed)
        self.assertFalse(result.has_actuals)
        self.assertEqual(result.provider, 'ff_export')
        self.assertEqual(result.retry_after, 600)
        self.assertIn('no Actual values', result.warning)

    def test_recent_cache_beats_schedule_only_fallback(self):
        with self.patch('biquote', return_value=self.sample()):
            feed.fetch_events('biquote', now=NOW)
        export = mock.Mock(return_value=self.sample(actual=''))
        with self.patch('biquote', side_effect=ProviderError('down')), self.patch('ff_export', new=export):
            result = feed.fetch_events('biquote', now=NOW + timedelta(minutes=30))
        export.assert_not_called()
        self.assertTrue(result.is_cache and result.failed)
        self.assertEqual(result.events[0].actual, '1%')

    def test_everything_down_without_cache_raises(self):
        with (
            self.patch('biquote', side_effect=ProviderError('down')),
            self.patch('ff_export', side_effect=ProviderError('down too')),
            self.assertRaises(ProviderError),
        ):
            feed.fetch_events('biquote', now=NOW)

    def test_export_requested_at_most_hourly(self):
        provider = PROVIDERS['ff_export']
        body = [{'title': 'Sample', 'country': 'USD', 'date': NOW.isoformat(), 'impact': 'High', 'forecast': '1%'}]
        from econpulse.providers import ff_export

        with mock.patch.object(ff_export, 'http_get_json', return_value=body) as get:
            provider.fetch(NOW)
            provider.fetch(NOW + timedelta(minutes=30))
            self.assertEqual(get.call_count, 1)
            provider.fetch(NOW + timedelta(minutes=70))
            self.assertEqual(get.call_count, 2)

    def test_export_remembers_its_etag_from_the_first_download(self):
        import json

        from econpulse.providers import ff_export
        from econpulse.storage import data_dir

        body = [{'title': 'Sample', 'country': 'USD', 'date': NOW.isoformat(), 'impact': 'High'}]
        seen = []

        def fake(url, *, timeout, validators):
            seen.append(dict(validators))
            validators['etag'] = '"week-46"'
            return body

        with mock.patch.object(ff_export, 'http_get_json', side_effect=fake):
            PROVIDERS['ff_export'].fetch(NOW)
            saved = json.loads((data_dir() / ff_export.CACHE).read_text(encoding='utf-8'))
            self.assertEqual(saved['etag'], '"week-46"')
            PROVIDERS['ff_export'].fetch(NOW + timedelta(minutes=70))
        self.assertEqual(seen, [{}, {'etag': '"week-46"'}])  # the second download is conditional


if __name__ == '__main__':
    unittest.main()
