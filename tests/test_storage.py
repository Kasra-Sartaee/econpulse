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


if __name__ == '__main__':
    unittest.main()
