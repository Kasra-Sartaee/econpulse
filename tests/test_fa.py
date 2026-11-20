"""Persian (fa) mode: Jalali dates, digits, bidi marks and right-to-left mirroring."""

from datetime import UTC, date, datetime, timedelta
import unittest

import helpers

from econpulse import i18n
from econpulse.core import parse_feed

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


class Persian(unittest.TestCase):
    def setUp(self):
        i18n.set_language('fa')

    def tearDown(self):
        i18n.set_language('en')


class JalaliTests(unittest.TestCase):
    def test_known_dates(self):
        cases = {
            (2024, 3, 20): (1403, 1, 1),  # Nowruz 1403
            (2025, 3, 21): (1404, 1, 1),  # Nowruz 1404
            (2026, 3, 21): (1405, 1, 1),  # Nowruz 1405
            (2026, 11, 12): (1405, 8, 21),  # 21 Aban 1405
            (2000, 1, 1): (1378, 10, 11),
            (2025, 3, 20): (1403, 12, 30),  # last day of a leap year
        }
        for g, j in cases.items():
            self.assertEqual(i18n.gregorian_to_jalali(*g), j, g)

    def test_consecutive_days_never_skip_or_repeat(self):
        day, last = date(2020, 1, 1), None
        for _ in range(3 * 366):
            j = i18n.gregorian_to_jalali(day.year, day.month, day.day)
            if last:
                self.assertTrue(j[2] == last[2] + 1 or (j[2] == 1 and (j[1] == last[1] + 1 or j[1] == 1)), (last, j))
            last, day = j, day + timedelta(days=1)


class StringTests(Persian):
    def test_translation_digits_and_counts(self):
        self.assertEqual(i18n.tr('Today'), 'امروز')
        self.assertEqual(i18n.tr('Unknown phrase'), 'Unknown phrase')
        self.assertEqual(i18n.digits(2026), '۲۰۲۶')
        self.assertEqual(i18n.count(28, 'release'), '۲۸ رویداد')
        self.assertEqual(i18n.minutes(15), '۱۵ دقیقه')
        self.assertEqual(i18n.date_text(date(2026, 11, 12), 'full'), 'پنجشنبه ۲۱ آبان ۱۴۰۵')
        self.assertEqual(i18n.day_label(date(2026, 11, 13), date(2026, 11, 12)), ('فردا', 'جمعه ۲۲ آبان'))

    def test_bidi_marks_only_persian_text(self):
        self.assertEqual(i18n.bidi('۱۰ رویداد'), i18n.RLM + '۱۰ رویداد')
        self.assertEqual(i18n.bidi(i18n.bidi('امروز')), i18n.RLM + 'امروز')  # idempotent
        for latin in ('CPI y/y', '5.62|2.5', '-0.2%', ''):
            self.assertEqual(i18n.bidi(latin), latin)

    def test_english_is_untouched(self):
        i18n.set_language('en')
        self.assertEqual(i18n.tr('Today'), 'Today')
        self.assertEqual(i18n.digits(15), '15')
        self.assertEqual(i18n.count(1, 'release'), '1 release')
        self.assertEqual(i18n.count(2, 'holiday'), '2 holidays')
        self.assertEqual(i18n.bidi('امروز'), 'امروز')
        self.assertEqual(i18n.date_text(date(2026, 11, 12), 'medium'), 'Thu 12 Nov')


class MirrorTests(Persian):
    def test_pack_options(self):
        self.assertEqual(
            i18n.mirror_pack_options({'side': 'left', 'anchor': 'nw', 'padx': (0, 8), 'pady': (1, 2)}),
            {'side': 'right', 'anchor': 'ne', 'padx': (8, 0), 'pady': (1, 2)},
        )
        self.assertEqual(
            i18n.mirror_pack_options({'side': 'top', 'anchor': 'center', 'padx': 4}),
            {'side': 'top', 'anchor': 'center', 'padx': 4},
        )

    def _root(self):
        return helpers.tk_root()

    def test_pack_is_mirrored_only_in_persian(self):
        import tkinter as tk

        i18n.install_rtl_geometry()
        root = self._root()
        try:
            a = tk.Frame(root)
            a.pack(side='left', anchor='w', padx=(0, 5))
            info = a.pack_info()
            self.assertEqual((info['side'], info['anchor'], info['padx']), ('right', 'e', (5, 0)))
            i18n.set_language('en')
            b = tk.Frame(root)
            b.pack(side='left', anchor='w')
            self.assertEqual((b.pack_info()['side'], b.pack_info()['anchor']), ('left', 'w'))
        finally:
            root.destroy()

    def test_event_list_draws_mirrored(self):
        from econpulse import theme
        from econpulse.event_list import EventCanvas

        events = parse_feed(
            [
                dict(
                    id=f'e{i}',
                    title=f'Indicator {i}',
                    country='USD',
                    impact='High',
                    date=(NOW + timedelta(minutes=30 * i)).isoformat(),
                )
                for i in range(6)
            ]
        )
        positions = {}
        for lang in ('en', 'fa'):
            i18n.set_language(lang)
            root = self._root()
            try:
                lst = EventCanvas(root, theme.DARK, 'table', lambda e: None, lambda: NOW)
                lst.pack(fill='both', expand=True)
                root.geometry('900x500')
                root.deiconify()
                root.update()
                lst.update_data(events, UTC)
                root.update()
                width = lst.view_width()
                item = next(
                    i
                    for i in lst.cv.find_all()
                    if lst.cv.type(i) == 'text' and lst.cv.itemcget(i, 'text').endswith('Indicator 0')
                )
                positions[lang] = lst.cv.coords(item)[0] / width
                if lang == 'fa':
                    self.assertTrue(lst.cv.itemcget(item, 'anchor') == 'e')
                    self.assertIn(
                        i18n.RLM + 'شمارش معکوس',
                        [lst.header.itemcget(i, 'text') for i in lst.header.find_all() if lst.header.type(i) == 'text'],
                    )
            finally:
                root.destroy()
        self.assertLess(positions['en'], 0.5)  # title starts near the left edge...
        self.assertGreater(positions['fa'], 0.5)  # ...and near the right edge in Persian


if __name__ == '__main__':
    unittest.main()
