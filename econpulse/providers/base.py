"""Shared plumbing for calendar data providers: a polite HTTP client and the
interface every provider implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import ipaddress
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import zlib

from .. import USER_AGENT
from ..core import Event

MAX_BYTES = 4_500_000
_SENSITIVE_HEADERS = {'x-api-key', 'authorization', 'cookie'}


class NotModified(Exception):
    """HTTP 304: conditional request matched the cached ETag / Last-Modified."""


def _decompress_gzip(raw: bytes, limit: int = MAX_BYTES) -> bytes:
    """Decompress gzip with a hard output cap (defends against zip bombs)."""
    decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = decomp.decompress(raw, limit + 1)
        if len(out) > limit or decomp.unconsumed_tail:
            raise ProviderError('response too large')
        tail = decomp.flush(limit + 1 - len(out))
        if len(out) + len(tail) > limit or not decomp.eof:
            raise ProviderError('response too large')
        return out + tail
    except zlib.error:
        raise ProviderError('invalid compressed response') from None


def _is_public_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.rstrip('.').lower()
    if host in ('localhost',) or host.endswith('.localhost'):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Allow at most 3 HTTPS redirects to public hosts; strip credentials cross-origin."""

    max_redirections = 3

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != 'https' or not _is_public_host(parts.hostname):
            raise ProviderError('refusing an unsafe redirect')
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        old_parts = urlsplit(req.full_url)
        if (old_parts.hostname or '').lower() != (parts.hostname or '').lower() or old_parts.port != parts.port:
            for store in (new_req.headers, new_req.unredirected_hdrs):
                for key in list(store):
                    if key.lower() in _SENSITIVE_HEADERS:
                        del store[key]
        return new_req


_OPENER = build_opener(HTTPSHandler(context=_tls_context()), _SafeRedirectHandler())


def urlopen(request: Request, timeout: float = 17):
    return _OPENER.open(request, timeout=timeout)


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
        return max(0, min(int((when - datetime.now(UTC)).total_seconds()), 24 * 3600))
    except (TypeError, ValueError, OverflowError):
        return None


def http_get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 17,
    validators: dict[str, str] | None = None,
):
    """GET a JSON document over HTTPS, identifying the app honestly.

    Supports gzip decompression (with a hard size cap) and optional HTTP
    conditional caching via ``validators`` (reads ``etag`` / ``last_modified``
    and updates them in place; raises :class:`NotModified` on HTTP 304).
    Raises :class:`RateLimited`, :class:`KeyRejected` or :class:`ProviderError`.
    """
    if params:
        url = f'{url}?{urlencode(params)}'
    parts = urlsplit(url)
    if parts.scheme != 'https' or not _is_public_host(parts.hostname):
        raise ProviderError('refusing a non-HTTPS request')
    req_headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        **(headers or {}),
    }
    if validators:
        if validators.get('etag'):
            req_headers['If-None-Match'] = validators['etag']
        if validators.get('last_modified'):
            req_headers['If-Modified-Since'] = validators['last_modified']
    # HTTPS scheme and public host are enforced above.
    request = Request(url, headers=req_headers)  # noqa: S310  # nosec B310
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            raw = response.read(MAX_BYTES + 1)
            resp_headers = getattr(response, 'headers', None) or {}
            encoding = str(resp_headers.get('Content-Encoding') or '').lower()
            if validators is not None:
                if resp_headers.get('ETag'):
                    validators['etag'] = str(resp_headers['ETag'])[:200]
                if resp_headers.get('Last-Modified'):
                    validators['last_modified'] = str(resp_headers['Last-Modified'])[:200]
    except HTTPError as exc:
        if exc.code == 304:
            raise NotModified() from None
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
    if 'gzip' in encoding:
        raw = _decompress_gzip(raw, MAX_BYTES)
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
