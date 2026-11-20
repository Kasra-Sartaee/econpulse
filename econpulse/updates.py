"""Opt-in update notice (off by default).

When enabled in Settings, EconPulse asks GitHub at most once a day for the
latest published release of this project and shows a small notice if it is
newer. Nothing about the user or their settings is sent; the request carries
only the app's User-Agent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import re

from . import REPO, REPO_URL
from .providers.base import ProviderError, http_get_json

log = logging.getLogger('econpulse')
API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_URL = f'{REPO_URL}/releases/latest'
INTERVAL = timedelta(days=1)
_VERSION = re.compile(r'v?(\d+)\.(\d+)(?:\.(\d+))?')


def parse_version(text) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(str(text or '').strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_newer(candidate, current) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def due(last_check, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    try:
        return now - datetime.fromisoformat(last_check) >= INTERVAL
    except (TypeError, ValueError):
        return True


def latest_release(timeout: float = 10) -> str | None:
    """Tag of the latest published (non-draft, non-prerelease) release, or None."""
    if REPO.startswith('OWNER/'):
        return None  # repository not configured yet
    try:
        body = http_get_json(API, headers={'Accept': 'application/vnd.github+json'}, timeout=timeout)
    except ProviderError as exc:
        log.info('update check failed: %s', exc)
        return None
    tag = body.get('tag_name') if isinstance(body, dict) else None
    return tag.lstrip('v') if isinstance(tag, str) and parse_version(tag) else None
