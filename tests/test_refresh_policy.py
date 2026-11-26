"""The refresh rules (econpulse/refresh.py): polite polling, backoff, supersede. No Tk needed."""

from datetime import UTC, datetime, timedelta
import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse.core import parse_feed

NOW = datetime(2026, 11, 12, 12, 0, 30, tzinfo=UTC)


class RefreshPolicyTests(unittest.TestCase):
    """The politeness rules, with a fake clock (econpulse/refresh.py)."""

    def setUp(self):
        from econpulse.refresh import RefreshPolicy

        self.policy = RefreshPolicy()

    def test_failures_back_off_30_60_120_then_reset(self):
        policy, waits = self.policy, []
        for _ in range(4):
            policy.finished(NOW, failed=True)
            waits.append(int((policy.next_attempt - NOW).total_seconds() // 60))
        self.assertEqual(waits, [30, 60, 120, 120])
        self.assertFalse(policy.due(NOW + timedelta(minutes=119)))
        self.assertTrue(policy.due(NOW + timedelta(minutes=120)))
        policy.finished(NOW, failed=False)
        self.assertEqual((policy.failures, policy.next_attempt), (0, None))

    def test_retry_after_is_honoured(self):
        self.policy.finished(NOW, failed=True, retry_after=3 * 3600)
        self.assertFalse(self.policy.due(NOW + timedelta(hours=2, minutes=59)))
        self.assertEqual(self.policy.refusal(NOW + timedelta(hours=1), force=True), 'wait')  # even manual ones
        self.assertTrue(self.policy.due(NOW + timedelta(hours=3)))

    def test_normal_interval_never_below_15_minutes(self):
        policy = self.policy
        self.assertTrue(policy.due(NOW))
        policy.start(NOW)
        policy.accept(policy.generation)
        self.assertFalse(policy.due(NOW + timedelta(minutes=14)))
        self.assertTrue(policy.due(NOW + timedelta(minutes=15)))
        self.assertFalse(policy.due(NOW + timedelta(minutes=14), interval_minutes=5))  # 15 is the floor
        self.assertFalse(policy.due(NOW + timedelta(minutes=50), interval_minutes=60))

    def test_one_fetch_at_a_time_and_manual_refreshes_are_spaced(self):
        policy = self.policy
        first = policy.start(NOW)
        self.assertFalse(policy.due(NOW + timedelta(hours=1)))  # never while one is running
        self.assertEqual(policy.refusal(NOW, force=True), 'busy')
        self.assertTrue(policy.accept(first))
        self.assertEqual(policy.refusal(NOW + timedelta(seconds=90)), 'soon')
        self.assertIsNone(policy.refusal(NOW + timedelta(seconds=90), force=True))
        self.assertIsNone(policy.refusal(NOW + timedelta(minutes=2)))

    def test_a_provider_switch_supersedes_the_running_fetch(self):
        policy = self.policy
        old = policy.start(NOW)
        self.assertIsNone(policy.refusal(NOW, supersede=True))
        new = policy.start(NOW)
        self.assertFalse(policy.accept(old))  # the old answer arrives late and is dropped
        self.assertTrue(policy.inflight)
        self.assertTrue(policy.accept(new))
        self.assertFalse(policy.inflight)

    def test_post_release_checks_only_while_the_source_is_healthy(self):
        just_out = parse_feed(
            [{'id': 'x:1', 'title': 'CPI', 'country': 'USD', 'impact': 'High', 'date': NOW.isoformat()}]
        )
        later = NOW + timedelta(seconds=50)
        common = {'watched': None, 'starred': None}
        self.assertFalse(self.policy.burst_due(just_out, later, has_actuals=False, **common))
        self.policy.finished(NOW, failed=True)
        self.assertFalse(self.policy.burst_due(just_out, later, has_actuals=True, **common))
        self.policy.reset_backoff()
        self.assertTrue(self.policy.burst_due(just_out, later, has_actuals=True, **common))
        self.assertFalse(self.policy.burst_due(just_out, later, has_actuals=True, **common))  # once per stage

    def test_post_release_checks_follow_the_users_watchlist_and_the_sources_wait(self):
        # Found by mutation testing: nothing checked that these arguments reach the decision.
        from econpulse.core import series_key
        from econpulse.refresh import RefreshPolicy

        usd_cpi, eur_pmi = parse_feed(
            [
                {'id': 'x:1', 'title': 'CPI', 'country': 'USD', 'impact': 'High', 'date': NOW.isoformat()},
                {'id': 'x:2', 'title': 'PMI', 'country': 'EUR', 'impact': 'Medium', 'date': NOW.isoformat()},
            ]
        )
        later = NOW + timedelta(seconds=50)
        unwatched = RefreshPolicy()
        self.assertFalse(
            unwatched.burst_due([usd_cpi, eur_pmi], later, has_actuals=True, watched={'EUR'}, starred=None)
        )
        starred = RefreshPolicy()
        self.assertTrue(
            starred.burst_due([eur_pmi], later, has_actuals=True, watched={'EUR'}, starred={series_key(eur_pmi)})
        )
        asked_to_wait = RefreshPolicy()
        asked_to_wait.finished(NOW, failed=False, retry_after=600)
        self.assertFalse(asked_to_wait.burst_due([usd_cpi], later, has_actuals=True, watched=None, starred=None))


if __name__ == '__main__':
    unittest.main()
