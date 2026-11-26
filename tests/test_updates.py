"""The in-app updater: nothing runs unless the download passes every check."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import helpers  # noqa: F401  (makes the package importable)

from econpulse import REPO, updates
from econpulse.providers import ProviderError, base

INSTALLER = b'MZ pretend installer bytes'
DIGEST = hashlib.sha256(INSTALLER).hexdigest()
PREFIX = f'https://github.com/{REPO}/releases/download/v9.9.9/'


def release(assets=None):
    names = assets or ['EconPulse-9.9.9-Setup.exe', 'SHA256SUMS.txt']
    return {'assets': [{'browser_download_url': name if '://' in name else PREFIX + name} for name in names]}


class FakeNetwork:
    """Stands in for GitHub: the release listing, the attestation API and the two downloads."""

    def __init__(self, *, sums=None, payload=INSTALLER, attested=True, assets=None):
        self.sums = sums if sums is not None else f'{DIGEST}  EconPulse-9.9.9-Setup.exe\n'
        self.payload, self.attested, self.assets = payload, attested, assets
        self.downloaded = []

    def get_json(self, url, **kw):
        if '/attestations/' in url:
            return {'attestations': [{'bundle': {}}]} if self.attested else {'attestations': []}
        return release(self.assets)

    def download(self, url, dest, *, max_bytes, timeout=60):
        self.downloaded.append(url)
        data = self.sums.encode() if url.endswith('SHA256SUMS.txt') else self.payload
        dest.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def patches(self):
        return (
            mock.patch.object(updates, 'http_get_json', side_effect=self.get_json),
            mock.patch.object(updates, 'http_download', side_effect=self.download),
        )


class DownloadInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, network):
        first, second = network.patches()
        with first, second:
            return updates.download_installer('9.9.9', self.folder)

    def test_a_verified_installer_is_returned(self):
        path = self.run_with(FakeNetwork())
        self.assertEqual(path.read_bytes(), INSTALLER)

    def test_a_checksum_mismatch_stops_and_deletes_it(self):
        with self.assertRaisesRegex(updates.UpdateError, 'checksum'):
            self.run_with(FakeNetwork(payload=b'tampered'))
        self.assertFalse(any(self.folder.glob('*.exe')))

    def test_no_build_attestation_stops_and_deletes_it(self):
        with self.assertRaisesRegex(updates.UpdateError, 'attestation'):
            self.run_with(FakeNetwork(attested=False))
        self.assertFalse(any(self.folder.glob('*.exe')))

    def test_only_this_repositorys_release_assets_are_used(self):
        elsewhere = ['https://evil.example/EconPulse-9.9.9-Setup.exe', PREFIX + 'SHA256SUMS.txt']
        network = FakeNetwork(assets=elsewhere)
        with self.assertRaisesRegex(updates.UpdateError, 'no installer'):
            self.run_with(network)
        self.assertEqual(network.downloaded, [])

    def test_a_checksum_file_without_the_installer_stops(self):
        with self.assertRaisesRegex(updates.UpdateError, 'no checksum'):
            self.run_with(FakeNetwork(sums=f'{DIGEST}  something-else.zip\n'))

    def test_network_errors_become_update_errors(self):
        with (
            mock.patch.object(updates, 'http_get_json', side_effect=ProviderError('network error: offline')),
            self.assertRaises(updates.UpdateError),
        ):
            updates.download_installer('9.9.9', self.folder)

    def test_a_portable_copy_is_never_treated_as_installed(self):
        self.assertFalse(updates.installed_copy())  # tests run from source, not the installed exe


class HttpDownloadTests(unittest.TestCase):
    class Response:
        def __init__(self, data):
            self.data = data

        def read(self, n):
            chunk, self.data = self.data[:n], self.data[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_streams_hashes_caps_and_refuses_plain_http(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'file.bin'
            data = b'x' * 200_000
            with mock.patch.object(base, 'urlopen', return_value=self.Response(data)):
                self.assertEqual(
                    base.http_download('https://example.org/f', dest, max_bytes=300_000),
                    hashlib.sha256(data).hexdigest(),
                )
            self.assertEqual(dest.read_bytes(), data)
            with (
                mock.patch.object(base, 'urlopen', return_value=self.Response(data)),
                self.assertRaisesRegex(ProviderError, 'too large'),
            ):
                base.http_download('https://example.org/f', dest, max_bytes=100_000)
            self.assertFalse(dest.exists(), 'a partial download must be deleted')
            with self.assertRaises(ProviderError):
                base.http_download('http://example.org/f', dest, max_bytes=100_000)


if __name__ == '__main__':
    unittest.main()
