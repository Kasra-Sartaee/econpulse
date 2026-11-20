"""Calendar data providers. See docs/PROVIDERS.md for how to add one."""

from .base import FeedResult, KeyRejected, Provider, ProviderError, RateLimited, http_get_json
from .biquote import BiquoteProvider
from .ff_export import ForexFactoryExportProvider
from .financecalendar import FinanceCalendarProvider

PROVIDERS: dict[str, Provider] = {
    p.id: p for p in (BiquoteProvider(), ForexFactoryExportProvider(), FinanceCalendarProvider())
}
DEFAULT = 'biquote'
FALLBACK = 'ff_export'

__all__ = [
    'DEFAULT',
    'FALLBACK',
    'PROVIDERS',
    'FeedResult',
    'KeyRejected',
    'Provider',
    'ProviderError',
    'RateLimited',
    'http_get_json',
]
