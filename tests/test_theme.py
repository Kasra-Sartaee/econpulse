"""Palettes: readable contrast in every theme (WCAG 2 contrast ratios)."""

import unittest

import helpers  # noqa: F401  (makes the package importable)

from econpulse import theme


def luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


TEXT = ('text', 'soft', 'red', 'amber', 'green', 'purple', 'blue', 'now')


class ContrastTests(unittest.TestCase):
    def test_high_contrast_theme_meets_wcag_aaa(self):
        p = theme.CONTRAST
        for surface in ('bg', 'card', 'input'):
            for colour in (*TEXT, 'faded'):
                self.assertGreaterEqual(ratio(p[colour], p[surface]), 7, f'{colour} on {surface}')
        self.assertGreaterEqual(ratio(p['primary_fg'], p['primary']), 7)
        self.assertGreaterEqual(ratio(p['text'], p['thumb']), 7)  # the selected segment's label
        self.assertGreaterEqual(ratio(p['thumb_line'], p['seg']), 3)  # ...and the selection is visible (WCAG 1.4.11)

    def test_regular_themes_meet_wcag_aa_for_body_text(self):
        for name in ('dark', 'light'):
            p = theme.palette(name)
            for colour in ('text', 'soft'):
                self.assertGreaterEqual(ratio(p[colour], p['card']), 4.5, f'{name}: {colour}')

    def test_every_palette_has_the_same_keys(self):
        self.assertEqual(set(theme.CONTRAST), set(theme.DARK))
        self.assertEqual(set(theme.LIGHT), set(theme.DARK))


if __name__ == '__main__':
    unittest.main()
