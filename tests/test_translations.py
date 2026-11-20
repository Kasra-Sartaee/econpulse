"""Every interface string has a translation in every registered language.

Strings are collected from the source: literals passed to tr(), menu_text(),
the label/btn/icon_btn helpers (which translate their text), tooltips, the
navigation tables and provider attributions. A new language therefore fails
this test until it is complete, and so does an untranslated new string.
"""

import ast
import unittest

from helpers import ROOT

from econpulse import i18n
from econpulse.providers import PROVIDERS
from econpulse.ui_calendar import TAB_NAMES, TAB_TITLES

# Positional index of the user-visible text for helpers that translate it.
TEXT_ARG = {'tr': 0, 'menu_text': 0, 'label': 1, 'btn': 1, 'icon_btn': 3}
NOT_TEXT = {'EconPulse', '↗', ''}


def interface_strings() -> set[str]:
    found = set()
    for path in (ROOT / 'econpulse').rglob('*.py'):
        if 'locales' in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            candidates = []
            if name in TEXT_ARG and len(node.args) > TEXT_ARG[name]:
                candidates.append(node.args[TEXT_ARG[name]])
            candidates += [kw.value for kw in node.keywords if kw.arg == 'tooltip']
            for arg in candidates:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    found |= {name for _key, _icon, name in TAB_NAMES} | set(TAB_TITLES.values())
    found |= {p.attribution for p in PROVIDERS.values()}
    return {s for s in found if s not in NOT_TEXT and any(ch.isalpha() for ch in s)}


class TranslationCoverageTests(unittest.TestCase):
    def test_collector_finds_the_interface(self):
        strings = interface_strings()
        self.assertGreater(len(strings), 80)
        for sample in ('Economic Calendar', 'Preferences', 'Open source page', 'Copy diagnostics'):
            self.assertIn(sample, strings)

    def test_every_language_is_complete(self):
        strings = interface_strings()
        for code, locale in i18n.LANGUAGES.items():
            if code == 'en':
                continue
            missing = sorted(s for s in strings if s not in locale.STRINGS)
            self.assertEqual(missing, [], f'{code}: {len(missing)} untranslated strings')

    def test_registry_shape(self):
        for code, locale in i18n.LANGUAGES.items():
            self.assertEqual(locale.CODE, code)
            self.assertTrue(locale.NAME)
            self.assertIsInstance(locale.STRINGS, dict)


class SourceHygieneTests(unittest.TestCase):
    def test_no_invisible_bidi_controls_in_source(self):
        """Trojan Source guard: direction-control characters must be written as escapes."""
        controls = {chr(c) for c in (0x200E, 0x200F, 0x061C, *range(0x202A, 0x202F), *range(0x2066, 0x206A))}
        for path in [
            *(ROOT / 'econpulse').rglob('*.py'),
            *(ROOT / 'tests').rglob('*.py'),
            *(ROOT / 'tools').rglob('*.py'),
        ]:
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                self.assertFalse(controls & set(line), f'{path.name}:{number}')


if __name__ == '__main__':
    unittest.main()
