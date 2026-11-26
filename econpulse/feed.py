"""Fetch the calendar from the selected provider, fall back politely, cache results.

Order of preference on each refresh:

1. the selected provider (biquote by default);
2. if it fails, a recent cached copy from a provider with Actual values
   (better than dropping results already shown);
3. otherwise the schedule-only fallback (Forex Factory's official export);
4. otherwise any cached copy, clearly marked as stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from . import i18n
from .core import Event, parse_feed
from .providers import DEFAULT, FALLBACK, PROVIDERS, FeedResult, KeyRejected, ProviderError, RateLimited
from .storage import data_dir, read_json, safe_write_json

log = logging.getLogger('econpulse')
CACHE_FILE = 'cache-v4.json'
LEGACY_CACHE = 'cache-v3.json'
FRESH_ENOUGH = timedelta(hours=3)


def serialize(e: Event) -> dict[str, str]:
    return e.to_record()


def load_cache() -> FeedResult:
    data = read_json(data_dir() / CACHE_FILE, None)
    if data is None:
        data = read_json(data_dir() / LEGACY_CACHE, {})  # 3.x cache, same record shape
    try:
        events = parse_feed(data['events'])
        stamp = datetime.fromisoformat(data['at'])
        return FeedResult(
            events,
            stamp,
            data.get('source', 'cache'),
            is_cache=True,
            coverage=data.get('coverage', 'cache'),
            has_actuals=data.get('has_actuals', True),
            provider=data.get('provider', ''),
        )
    except (ValueError, KeyError, TypeError, OverflowError):
        return FeedResult([], None, 'no cache', is_cache=True)


def save_cache(result: FeedResult) -> None:
    if result.at is None:
        return  # only fresh downloads are cached, and they always carry their time
    safe_write_json(
        data_dir() / CACHE_FILE,
        {
            'at': result.at.isoformat(),
            'source': result.source,
            'provider': result.provider,
            'coverage': result.coverage,
            'has_actuals': result.has_actuals,
            'events': [serialize(e) for e in result.events],
        },
    )


def _describe(exc: Exception) -> str:
    if isinstance(exc, KeyRejected):
        return i18n.tr('API key rejected')
    if isinstance(exc, RateLimited):
        return i18n.tr('asked to slow down')
    return str(exc) or exc.__class__.__name__


def fetch_events(
    provider_id: str = DEFAULT, *, key: str = '', timeout: float = 17, now: datetime | None = None
) -> FeedResult:
    now = now or datetime.now(UTC)
    primary = PROVIDERS.get(provider_id) or PROVIDERS[DEFAULT]
    try:
        events = primary.fetch(now, key=key, timeout=timeout)
        result = FeedResult(
            events,
            now,
            primary.name,
            provider=primary.id,
            has_actuals=primary.has_actuals,
            coverage='live',
            warning='' if primary.has_actuals else i18n.tr('Schedule only: this source has no Actual values.'),
        )
        save_cache(result)
        return result
    except ProviderError as exc:
        problem = f'{primary.name}: {_describe(exc)}'
        retry_after = exc.retry_after if isinstance(exc, RateLimited) else None
        log.warning('calendar fetch failed (%s)', problem)
    except Exception:
        # A parser bug or a truly malformed response must not skip the fallbacks below.
        log.exception('%s sent data EconPulse could not read', primary.name)
        problem, retry_after = f'{primary.name}: {i18n.tr("unreadable response")}', None

    cached = load_cache()
    if cached.events and cached.has_actuals and cached.at and now - cached.at < FRESH_ENOUGH:
        cached.warning = f'{problem}. {i18n.tr("Showing saved data.")}'
        cached.failed, cached.retry_after = True, retry_after
        return cached

    if primary.id != FALLBACK:
        fallback = PROVIDERS[FALLBACK]
        try:
            events = fallback.fetch(now, timeout=timeout)
            return FeedResult(
                events,
                now,
                fallback.name,
                provider=fallback.id,
                has_actuals=False,
                coverage='fallback',
                failed=True,
                retry_after=retry_after,
                warning=f'{problem}. {i18n.tr("Showing the Forex Factory schedule (no Actual values).")}',
            )
        except ProviderError as exc:
            problem += f'; {fallback.name}: {_describe(exc)}'
            log.warning('fallback fetch failed (%s)', _describe(exc))
        except Exception:
            problem += f'; {fallback.name}: {i18n.tr("unreadable response")}'
            log.exception('%s sent data EconPulse could not read', fallback.name)

    if cached.events:
        cached.warning = f'{i18n.tr("Offline")}. {problem}.'
        cached.failed, cached.retry_after, cached.coverage = True, retry_after, 'stale cache'
        return cached
    error = ProviderError(problem)
    error.retry_after = retry_after
    raise error
