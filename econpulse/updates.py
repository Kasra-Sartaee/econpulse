"""Opt-in update notice (off by default).

When enabled in Settings, EconPulse asks GitHub at most once a day for the
latest published release of this project and shows a small notice if it is
newer. Nothing about the user or their settings is sent; the request carries
only the app's User-Agent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
import re

from . import REPO, REPO_URL
from .providers.base import ProviderError, http_download, http_get_json

log = logging.getLogger('econpulse')
API = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_URL = f'{REPO_URL}/releases/latest'
INTERVAL = timedelta(days=1)
_VERSION = re.compile(r'v?(\d+)\.(\d+)(?:\.(\d+))?')


def parse_version(text: object) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(str(text or '').strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_newer(candidate: object, current: object) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def due(last_check: object, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if not isinstance(last_check, str):
        return True
    try:
        return now - datetime.fromisoformat(last_check) >= INTERVAL
    except (TypeError, ValueError):  # unparseable, or a naive stamp compared with an aware one
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


# --------------------------------------------------------------------------
# Installing an update (only for copies installed with the Setup.exe)
# --------------------------------------------------------------------------
MAX_INSTALLER = 200_000_000


class UpdateError(Exception):
    """The update could not be downloaded or failed a check; nothing was run."""


def installed_copy() -> bool:
    """Running from an installation made by the Setup.exe (its uninstaller sits next to the app).

    Portable copies (the zip) are never replaced in place: they get the releases page instead.
    """
    import sys

    return bool(getattr(sys, 'frozen', False)) and (Path(sys.executable).parent / 'unins000.exe').is_file()


def installer_name(version: str) -> str:
    return f'EconPulse-{version}-Setup.exe'


def _asset_urls(version: str) -> dict[str, str]:
    body = http_get_json(
        f'https://api.github.com/repos/{REPO}/releases/tags/v{version}',
        headers={'Accept': 'application/vnd.github+json'},
    )
    prefix = f'https://github.com/{REPO}/releases/download/v{version}/'
    urls: dict[str, str] = {}
    for asset in body.get('assets', []) if isinstance(body, dict) else []:
        url = asset.get('browser_download_url') if isinstance(asset, dict) else None
        if isinstance(url, str) and url.startswith(prefix):  # this repository's own release, nothing else
            urls[url[len(prefix) :]] = url
    return urls


def _expected_digest(sums: str, name: str) -> str:
    match = re.search(rf'(?m)^([0-9a-f]{{64}})\s+\*?{re.escape(name)}\s*$', sums)
    if not match:
        raise UpdateError(f'the release has no checksum for {name}')
    return match.group(1)


def attested(digest: str) -> bool:
    """GitHub holds a build attestation for this exact file, made by this repository's CI."""
    body = http_get_json(
        f'https://api.github.com/repos/{REPO}/attestations/sha256:{digest}',
        headers={'Accept': 'application/vnd.github+json'},
    )
    return isinstance(body, dict) and bool(body.get('attestations'))


def download_installer(version: str, folder: Path) -> Path:
    """Download the release's Setup.exe and verify it before anything runs it.

    Three checks: the URL is this repository's release asset; the file's SHA-256 matches the
    release's SHA256SUMS.txt; and GitHub has a build attestation for that digest from this
    repository's release workflow. Any failure deletes the file and raises UpdateError.
    """
    if not parse_version(version):
        raise UpdateError(f'not a version: {version!r}')
    name = installer_name(version)
    try:
        urls = _asset_urls(version)
        if name not in urls or 'SHA256SUMS.txt' not in urls:
            raise UpdateError(f'release {version} has no installer')
        folder.mkdir(parents=True, exist_ok=True)
        sums_path = folder / f'SHA256SUMS-{version}.txt'
        http_download(urls['SHA256SUMS.txt'], sums_path, max_bytes=100_000)
        expected = _expected_digest(sums_path.read_text(encoding='utf-8', errors='replace'), name)
        sums_path.unlink(missing_ok=True)
        path = folder / name
        digest = http_download(urls[name], path, max_bytes=MAX_INSTALLER)
        if digest != expected:
            path.unlink(missing_ok=True)
            raise UpdateError('the download does not match the published checksum')
        if not attested(digest):
            path.unlink(missing_ok=True)
            raise UpdateError('the download has no build attestation from this project')
        return path
    except ProviderError as exc:
        raise UpdateError(str(exc)) from None
