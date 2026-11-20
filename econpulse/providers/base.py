"""Shared plumbing for calendar data providers: a polite HTTP client and the
interface every provider implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .. import USER_AGENT
from ..core import Event

MAX_BYTES = 4_500_000


class ProviderError(Exception):
    """The provider could not deliver usable data (network, HTTP or format)."""


class RateLimited(ProviderError):
    """HTTP 429/503: back off for ``retry_after`` seconds (None = use our own backoff)."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class KeyRejected(ProviderError):
    """HTTP 401/403: the API key is missing, wrong or out of plan scope."""


@dataclass
class FeedResult:
    events: list[Event]
    at: datetime | None
    source: str
    warning: str = ''
    is_cache: bool = False
    coverage: str = 'unverified'
    has_actuals: bool = True
    provider: str = ''
    retry_after: int | None = None  # set when the source asked us to slow down
    failed: bool = False  # the selected provider failed (fallback or cache shown)
    notes: list[str] = field(default_factory=list)


def _retry_after(value) -> int | None:
    if not value:
        return None
    value = str(value).strip()
    if value.isdigit():
        return min(int(value), 24 * 3600)
    try:
        when = parsedate_to_datetime(value)
        return max(0, min(int((when - datetime.now(timezone.utc)).total_seconds()), 24 * 3600))
    except (TypeError, ValueError, OverflowError):
        return None


def http_get_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: float = 17):
    """GET a JSON document over HTTPS, identifying the app honestly.

    Raises :class:`RateLimited`, :class:`KeyRejected` or :class:`ProviderError`.
    """
    if params:
        url = f'{url}?{urlencode(params)}'
    if urlsplit(url).scheme != 'https':
        raise ProviderError('refusing a non-HTTPS request')
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', **(headers or {})}
    request = Request(url, headers=headers)  # noqa: S310  # nosec B310 - https enforced above
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310 - https enforced above
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        if exc.code in (429, 503):
            raise RateLimited(f'HTTP {exc.code}', _retry_after(exc.headers.get('Retry-After'))) from None
        if exc.code in (401, 403):
            raise KeyRejected(f'HTTP {exc.code}') from None
        raise ProviderError(f'HTTP {exc.code}') from None
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', exc)
        raise ProviderError(f'network error: {reason}') from None
    if len(raw) > MAX_BYTES:
        raise ProviderError('response too large')
    try:
        return json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError):
        raise ProviderError('response is not valid JSON') from None


class Provider:
    """A calendar data source. Subclasses implement :meth:`fetch`."""

    id = ''
    name = ''
    homepage = ''
    attribution = ''  # visible credit text shown next to the data
    terms_url = ''
    needs_key = False
    has_actuals = True

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        raise NotImplementedError
