"""When to fetch the calendar: polite polling, backoff, Retry-After and supersede.

Pure Python with the clock passed in, so every rule here is tested without Tk,
threads or a network (tests/test_refresh.py). The app owns one RefreshPolicy and
asks it before every fetch.

The rules (also in docs/ARCHITECTURE.md):

- automatic refreshes at most every 15 minutes (or the user's longer interval);
- after failures, back off 30, 60, then 120 minutes; a source's Retry-After wins;
- a manual refresh needs 2 minutes since the last attempt;
- one fetch at a time, except a provider switch, which supersedes the running one;
- the opt-in post-release check only while the source is healthy.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from . import state
from .core import Event

BACKOFF_MINUTES = (30, 60, 120)  # after 1, 2, 3+ failed refreshes in a row
MIN_INTERVAL_MINUTES = 15
MANUAL_GAP = timedelta(minutes=2)


class RefreshPolicy:
    def __init__(self) -> None:
        self.inflight = False
        self.generation = 0  # incremented per fetch; a result from an older one is dropped
        self.last_attempt: datetime | None = None
        self.failures = 0
        self.next_attempt: datetime | None = None  # backoff after failures
        self.retry_until: datetime | None = None  # a source asked us to wait (HTTP 429/503 Retry-After)
        self.bursts: set[str] = set()  # post-release checks already made

    def waiting(self, now: datetime) -> bool:
        """The source asked us to wait and the time isn't up yet."""
        return self.retry_until is not None and now < self.retry_until

    def due(self, now: datetime, interval_minutes: int = MIN_INTERVAL_MINUTES) -> bool:
        """Whether an automatic refresh should start now."""
        if self.inflight or self.waiting(now):
            return False
        if self.next_attempt is not None:
            return now >= self.next_attempt
        interval = timedelta(minutes=max(MIN_INTERVAL_MINUTES, int(interval_minutes)))
        return self.last_attempt is None or now - self.last_attempt >= interval

    def refusal(self, now: datetime, *, force: bool = False, supersede: bool = False) -> str | None:
        """Why a refresh can't start now ('busy', 'wait' or 'soon'), or None if it can."""
        if supersede:
            return None
        if self.inflight:
            return 'busy'
        if self.waiting(now):
            return 'wait'
        if not force and self.last_attempt is not None and now - self.last_attempt < MANUAL_GAP:
            return 'soon'
        return None

    def start(self, now: datetime) -> int:
        """Record a fetch starting; returns its generation."""
        self.last_attempt = now
        self.inflight = True
        self.generation += 1
        return self.generation

    def accept(self, generation: int) -> bool:
        """Whether a finished fetch is still the current one. A superseded result is dropped."""
        if generation != self.generation:
            return False
        self.inflight = False
        return True

    def finished(self, now: datetime, *, failed: bool, retry_after: int | None = None) -> None:
        """Schedule the next automatic attempt (exponential backoff on failure)."""
        self.retry_until = now + timedelta(seconds=retry_after) if retry_after else None
        if not failed:
            self.failures, self.next_attempt = 0, None
            return
        self.failures += 1
        minutes = BACKOFF_MINUTES[min(self.failures, len(BACKOFF_MINUTES)) - 1]
        self.next_attempt = now + timedelta(minutes=minutes)

    def reset_backoff(self) -> None:
        """A new source or key: forget the old one's failures."""
        self.failures, self.next_attempt, self.retry_until = 0, None, None

    def burst_due(
        self,
        events: Iterable[Event],
        now: datetime,
        *,
        has_actuals: bool,
        watched: set[str] | None,
        starred: set[str] | None,
    ) -> bool:
        """The opt-in post-release check: never while failing or waiting, or on a schedule-only source."""
        if not has_actuals or self.inflight or self.failures or self.waiting(now):
            return False
        token = state.due_burst_poll(list(events), now, watched=watched, starred=starred, fired_bursts=self.bursts)
        return token is not None
