"""OS integration: safe links, start-at-login files, single instance, update check."""

from datetime import UTC, datetime, timedelta
import plistlib
import sys
import unittest
from unittest import mock

import helpers  # noqa: F401  (makes the package importable)

from econpulse import system, updates


class SafeLinkTests(unittest.TestCase):
    def test_only_plain_https_links(self):
        good = ['https://www.bls.gov/schedule/', 'https://biquote.io/terms.html', 'https://example.org/a?b=1']
        bad = [
            'http://example.org',
            'file:///C:/Windows/System32/calc.exe',
            'javascript:alert(1)',
            'https://user:pass@example.org',
            'https:///nohost',
            'https://localhost/admin',
            'https://127.0.0.1/local',
            'https://169.254.169.254/latest/meta-data/',
            'C:\\evil.exe',
            'https://exa mple.org',
            '',
            None,
            'https://' + 'a' * 3000,
        ]
        for url in good:
            self.assertTrue(system.is_safe_url(url), url)
        for url in bad:
            self.assertFalse(system.is_safe_url(url), url)

    def test_safe_open_refuses_without_launching(self):
        with mock.patch.object(system.webbrowser, 'open') as opened:
            self.assertFalse(system.safe_open('file:///etc/passwd'))
            opened.assert_not_called()
            system.safe_open('https://example.org')
            opened.assert_called_once_with('https://example.org')

    def test_host_shown_on_the_button(self):
        self.assertEqual(system.url_host('https://www.bls.gov/x'), 'bls.gov')


class StartupFileTests(unittest.TestCase):
    def test_desktop_entry_quotes_paths(self):
        text = system.desktop_entry(['/home/me/my apps/python3', '/opt/econ pulse/main.py', '--widget'])
        self.assertIn('Exec="/home/me/my apps/python3" "/opt/econ pulse/main.py" --widget', text)
        self.assertIn('Type=Application', text)

    def test_launch_agent_plist(self):
        data = plistlib.loads(system.launch_agent(['/usr/bin/python3', '-m', 'econpulse', '--widget']))
        self.assertEqual(data['ProgramArguments'][-1], '--widget')
        self.assertTrue(data['RunAtLoad'])

    def test_source_checkout_points_at_main_py(self):
        args = system.startup_args()
        self.assertTrue(args[1].endswith('main.py'))
        self.assertEqual(args[-1], '--widget')

    def test_source_checkout_never_rewrites_the_windows_entry(self):
        self.assertFalse(system.repair_startup())

    @unittest.skipIf(sys.platform == 'win32', 'POSIX lock file')
    def test_single_instance_lock_file(self):  # pragma: no cover - exercised on Linux/macOS CI
        import os
        import tempfile

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}),
            mock.patch.object(system, 'data_dir', return_value=__import__('pathlib').Path(tmp)),
        ):
            system._instance_mutex = None
            self.assertTrue(system.acquire_single_instance())
            import fcntl

            with open(os.path.join(tmp, 'instance.lock'), 'a+') as other, self.assertRaises(OSError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


class UpdateCheckTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(updates.is_newer('3.4.0', '3.3.0'))
        self.assertTrue(updates.is_newer('v4.0', '3.9.9'))
        self.assertFalse(updates.is_newer('3.3.0', '3.3.0'))
        self.assertFalse(updates.is_newer('banana', '3.3.0'))

    def test_daily_interval(self):
        now = datetime(2026, 11, 20, 12, tzinfo=UTC)
        self.assertTrue(updates.due('', now))
        self.assertTrue(updates.due('garbage', now))
        self.assertFalse(updates.due((now - timedelta(hours=3)).isoformat(), now))
        self.assertTrue(updates.due((now - timedelta(hours=25)).isoformat(), now))

    def test_unconfigured_repository_makes_no_request(self):
        with mock.patch.object(updates, 'REPO', 'OWNER/econpulse'), mock.patch.object(updates, 'http_get_json') as get:
            self.assertIsNone(updates.latest_release())
            get.assert_not_called()

    def test_reads_the_latest_tag(self):
        with (
            mock.patch.object(updates, 'REPO', 'someone/econpulse'),
            mock.patch.object(updates, 'http_get_json', return_value={'tag_name': 'v3.4.1'}),
        ):
            self.assertEqual(updates.latest_release(), '3.4.1')


if __name__ == '__main__':
    unittest.main()
