"""Settings validation and atomic file writes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse import storage


class SettingsValidationTests(unittest.TestCase):
    def test_defaults_for_missing_or_garbage_files(self):
        for raw in (None, [], 'text', 42, {}):
            self.assertEqual(storage.validate_settings(raw), storage.DEFAULTS)

    def test_bad_values_fall_back_individually(self):
        raw = {
            'theme': 'neon',
            'language': 'xx',
            'timezone': 'Mars',
            'refresh_minutes': 1,
            'widget_opacity': '100',
            'currencies': ['USD', 'usd', 'X'],
            'impacts': ['High', 'Huge'],
            'notify_minutes': [30, 30],
            'provider': 'scraper',
            'financecalendar_key': 'a key;rm -rf',
            'widget_x': True,
            'topmost': 'yes',
            'unknown_key': 1,
        }
        result = storage.validate_settings(raw)
        for key in raw:
            if key != 'unknown_key':
                self.assertEqual(result[key], storage.DEFAULTS[key], key)
        self.assertNotIn('unknown_key', result)

    def test_unhashable_values_do_not_crash_loading(self):
        # Found by Hypothesis: a hand-edited "timezone": [] used to crash startup.
        for key, (_default, check) in storage.SCHEMA.items():
            for junk in ([], {}, [[]], {'a': []}):
                result = storage.validate_settings({key: junk})
                self.assertTrue(check(result[key]), (key, junk))  # loaded, and valid
        self.assertEqual(storage.validate_settings({'timezone': []})['timezone'], 'System local')

    def test_good_values_are_kept(self):
        raw = {
            'theme': 'light',
            'language': 'fa',
            'timezone': 'UTC',
            'refresh_minutes': 30,
            'currencies': ['USD', 'ZAR'],
            'impacts': ['High'],
            'notify_minutes': [5, 0],
            'provider': 'financecalendar',
            'financecalendar_key': 'fc_live_abc123',
            'widget_x': -300,
            'other_currencies': True,
            'check_updates': True,
        }
        result = storage.validate_settings(raw)
        for key, value in raw.items():
            self.assertEqual(result[key], value, key)

    def test_old_ghosting_opacity_is_migrated(self):
        self.assertEqual(storage.validate_settings({'widget_opacity': 97})['widget_opacity'], 100)
        # A current-version file is taken at its word: 97 is a valid opacity there.
        current = {'schema': storage.SCHEMA_VERSION, 'widget_opacity': 97}
        self.assertEqual(storage.validate_settings(current)['widget_opacity'], 97)

    def test_schema_is_consistent(self):
        for name, (default, check) in storage.SCHEMA.items():
            self.assertTrue(check(default), f'default for {name!r} fails its own check')
        # Every version after 1 has a migration, so a file from any past version can be read.
        self.assertEqual(sorted(storage.MIGRATIONS), list(range(2, storage.SCHEMA_VERSION + 1)))

    def test_files_from_every_version_load_and_are_stamped_current(self):
        for raw in ({}, {'schema': 1}, {'schema': storage.SCHEMA_VERSION}, {'schema': 999}, {'schema': True}):
            result = storage.validate_settings(raw)
            self.assertEqual(result['schema'], storage.SCHEMA_VERSION, raw)
        raw = {'widget_opacity': 97}  # validate_settings never mutates its input
        storage.validate_settings(raw)
        self.assertEqual(raw, {'widget_opacity': 97})

    def test_defaults_are_not_shared_between_calls(self):
        a = storage.validate_settings({})
        a['currencies'].append('USD')
        self.assertEqual(storage.validate_settings({})['currencies'], [])


class AtomicWriteTests(unittest.TestCase):
    def test_failed_write_leaves_no_temp_file_and_keeps_old(self):
        with TemporaryDirectory() as td:
            path = Path(td) / 'settings.json'
            storage.safe_write_json(path, {'ok': 1})
            with self.assertRaises(TypeError):
                storage.safe_write_json(path, {'bad': object()})
            self.assertEqual(json.loads(path.read_text()), {'ok': 1})
            self.assertEqual([p.name for p in Path(td).iterdir()], ['settings.json'])

    def test_safe_write_text_and_secret_roundtrip(self):
        import os
        import sys
        from unittest import mock

        with TemporaryDirectory() as td:
            note = Path(td) / 'notes.txt'
            storage.safe_write_text(note, 'hello world')
            self.assertEqual(note.read_text(encoding='utf-8'), 'hello world')
            with mock.patch.dict(os.environ, {'APPDATA': td, 'XDG_CONFIG_HOME': td, 'HOME': td}):
                cfg = {**storage.DEFAULTS, 'financecalendar_key': 'fc_live_secret_key_99'}
                storage.save_settings(cfg)
                raw = json.loads((storage.data_dir() / 'settings.json').read_text(encoding='utf-8'))
                if sys.platform == 'win32':
                    self.assertTrue(raw['financecalendar_key'].startswith('dpapi:'))
                    self.assertNotIn('fc_live_secret_key_99', raw['financecalendar_key'])
                reloaded = storage.load_settings()
                self.assertEqual(reloaded['financecalendar_key'], 'fc_live_secret_key_99')


class KeychainTests(unittest.TestCase):
    """macOS/Linux: the API key goes to the system keychain when `keyring` is installed."""

    def setUp(self):
        import os
        import sys
        import types
        from unittest import mock

        from econpulse import system

        self.store, self.calls = {}, []
        fake = types.ModuleType('keyring')
        fake.set_password = lambda service, name, value: (self.calls.append('set'), self.store.__setitem__(name, value))
        fake.get_password = lambda service, name: self.store.get(name)
        fake.delete_password = lambda service, name: (self.calls.append('delete'), self.store.pop(name))
        self.fake = fake
        self.tmp = TemporaryDirectory()
        system._keyring_value = None
        self.patches = [
            mock.patch.dict(sys.modules, {'keyring': fake}),
            mock.patch.object(system.sys, 'platform', 'linux'),
            mock.patch.dict(
                os.environ, {'XDG_CONFIG_HOME': self.tmp.name, 'APPDATA': self.tmp.name, 'HOME': self.tmp.name}
            ),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        from econpulse import system

        for patch in reversed(self.patches):
            patch.stop()
        system._keyring_value = None
        self.tmp.cleanup()

    def saved(self):
        return json.loads((storage.data_dir() / 'settings.json').read_text(encoding='utf-8'))

    def test_the_key_lives_in_the_keychain_not_the_file(self):
        storage.save_settings({**storage.DEFAULTS, 'financecalendar_key': 'fc_live_secret_key_99'})
        self.assertEqual(self.saved()['financecalendar_key'], 'keyring:')
        self.assertEqual(self.store, {'financecalendar_key': 'fc_live_secret_key_99'})
        cfg = storage.load_settings()
        self.assertEqual(cfg['financecalendar_key'], 'fc_live_secret_key_99')
        storage.save_settings(cfg)  # every star or drag saves the settings...
        self.assertEqual(self.calls, ['set'])  # ...without rewriting the keychain each time
        storage.save_settings({**cfg, 'financecalendar_key': ''})  # cleared in Settings
        self.assertEqual(self.store, {})
        self.assertEqual(self.calls, ['set', 'delete'])

    def test_a_broken_keychain_falls_back_to_the_private_file(self):
        def refuse(*_args):
            raise RuntimeError('no Secret Service running')

        self.fake.set_password = refuse
        storage.save_settings({**storage.DEFAULTS, 'financecalendar_key': 'fc_live_secret_key_99'})
        self.assertEqual(self.saved()['financecalendar_key'], 'fc_live_secret_key_99')
        self.assertEqual(storage.load_settings()['financecalendar_key'], 'fc_live_secret_key_99')


if __name__ == '__main__':
    unittest.main()
