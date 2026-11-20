# Adding a data source

EconPulse gets its calendar from *providers* in `econpulse/providers/`. Each one turns a service's response into the app's `Event` records. `feed.py` handles fallback and caching, and the app handles polling and backoff.

## First: check the terms

Only add a source whose terms allow an open-source desktop app to fetch its data directly on each user's computer. **Never read web pages from sites whose terms forbid automated access**, and don't work around blocking, rate limits or API keys. If a service requires attribution, set `attribution` so the app shows it, and mention the source in the README's data-source table.

Good sources are official APIs and feeds published for this use. Official statistics agencies are usually the safest choice.

## The interface

```python
from datetime import datetime

from ..core import Event, parse_feed
from .base import Provider, ProviderError, http_get_json


class ExampleProvider(Provider):
    id = 'example'  # stored in settings
    name = 'Example Data'  # shown in Settings and the status line
    homepage = 'https://example.org/'  # opened by clicking the attribution
    attribution = 'Data: Example'  # shown under the calendar (add it to the translations)
    terms_url = 'https://example.org/terms'
    needs_key = False  # True: a key field must be added to Settings
    has_actuals = True  # False: the app shows "Schedule only"

    def fetch(self, now: datetime, *, key: str = '', timeout: float = 17) -> list[Event]:
        rows = http_get_json('https://api.example.org/calendar', params={...}, timeout=timeout)
        return parse_feed([to_record(row) for row in rows])
```

Register the instance in `econpulse/providers/__init__.py` (`PROVIDERS`) and add its id to the `provider` check in `storage._validators`.

### Records

`fetch` returns `parse_feed(records)`, where each record is a dict:

| Key | Meaning |
|---|---|
| `id` | Stable unique id; prefix it with your provider (`ex:123`) so alerts don't repeat |
| `title` | Event name as published |
| `country` | **Currency code** (`USD`, `EUR`, ...) |
| `date` | ISO 8601 time **with an offset** (`2026-11-11T13:30:00Z`) |
| `impact` | `High`, `Medium`, `Low` or `Holiday` |
| `actual`, `forecast`, `previous` | Display-ready text, such as `0.2%`, `165K` or `-1.2M` |
| `time_label` | `All Day` or `Tentative` for releases without a confirmed time; empty otherwise |
| `source_day` | `YYYY-MM-DD` civil date for all-day and tentative items |
| `url` | Optional https link to the source page |
| `source`, `period` | Shown in the details window |

`parse_feed` validates every record, caps the length of each text field and drops rows without a valid time, so a malformed response can't break the app.

### Errors

`http_get_json` enforces HTTPS, a timeout, a size limit and the honest `EconPulse/<version>` User-Agent. It raises:

- `RateLimited(retry_after)` on HTTP 429/503. The app waits at least `retry_after`.
- `KeyRejected` on HTTP 401/403.
- `ProviderError` for anything else.

Raise `ProviderError` yourself for an unexpected response shape. The app then falls back to the Forex Factory export, or to the cache.

## Tests

Add tests to `tests/test_providers.py` with an **invented** payload in the real response shape. Never commit real data copied from a service. Mock `http_get_json` so tests never touch the network.
