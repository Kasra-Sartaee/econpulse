"""CSV and ICS exports, including spreadsheet-formula neutralisation."""

import csv
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from helpers import NOW

from econpulse.core import parse_feed
from econpulse.exports import csv_cell, fold, save_csv, save_ics


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.events = parse_feed(
            [
                {'country': 'USD', 'title': 'Bank Holiday', 'date': '2026-11-11T00:00:00-05:00', 'impact': 'Holiday'},
                {
                    'country': 'USD',
                    'title': 'CPI, headline',
                    'date': '2026-11-11T08:30:00-05:00',
                    'impact': 'High',
                    'forecast': '0.2%',
                },
            ]
        )

    def test_csv_utf8_and_rows(self):
        with TemporaryDirectory() as td:
            p = Path(td) / 'events.csv'
            save_csv(p, self.events, timezone.utc)
            data = p.read_text('utf-8-sig')
        self.assertIn('ALL DAY', data)
        self.assertIn('"CPI, headline"', data)

    def test_ics_all_day_and_timed(self):
        with TemporaryDirectory() as td:
            p = Path(td) / 'events.ics'
            save_ics(p, self.events, timezone.utc)
            data = p.read_text('utf-8')
        self.assertIn('DTSTART;VALUE=DATE:20261111', data)
        self.assertIn('DTSTART:20261111T133000Z', data)
        self.assertIn('SUMMARY:USD - CPI\\, headline', data)

    def test_ics_long_lines_folded_and_dtstamp_present(self):
        events = parse_feed([{'title': 'Ж' * 80, 'country': 'USD', 'date': NOW.isoformat(), 'impact': 'High'}])
        with TemporaryDirectory() as td:
            path = Path(td) / 'x.ics'
            save_ics(path, events, timezone.utc)
            raw = path.read_bytes()
        self.assertIn(b'DTSTAMP:', raw)
        for line in raw.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')  # never split inside a multi-byte character
        self.assertIn('SUMMARY:USD - ' + 'Ж' * 80, raw.decode('utf-8').replace('\r\n ', ''))
        self.assertEqual(fold('SUMMARY:short'), 'SUMMARY:short')


class FormulaInjectionTests(unittest.TestCase):
    def test_formula_like_cells_are_neutralised(self):
        for evil in ('=HYPERLINK("http://x","y")', '+1+cmd|"/c calc"!A0', '-2+3', '@SUM(A1)', '\t=1', '\r=1'):
            self.assertTrue(csv_cell(evil).startswith("'"), evil)

    def test_plain_figures_stay_numbers(self):
        for value in ('-0.2%', '+1.5K', '-1,200', '3.38M', '0.3%', '-0.865M', 'CPI m/m', ''):
            self.assertEqual(csv_cell(value), value)

    def test_hostile_title_is_neutralised_in_the_file(self):
        events = parse_feed([{'title': '=cmd|" /C calc"!A0', 'country': 'USD', 'date': NOW.isoformat()}])
        with TemporaryDirectory() as td:
            p = Path(td) / 'x.csv'
            save_csv(p, events, timezone.utc)
            with p.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.reader(stream))
        self.assertEqual(rows[1][4], '\'=cmd|" /C calc"!A0')


if __name__ == '__main__':
    unittest.main()
