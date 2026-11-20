"""Steady-state behaviour: the per-minute render keeps the drawing, rebuilds don't leak."""

from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import helpers

from econpulse import theme
from econpulse.core import parse_feed
from econpulse.event_list import EventCanvas, NextUp

NOW = datetime(2026, 11, 12, 12, 0, 30, tzinfo=timezone.utc)


def feed(*minutes, actual=''):
    return parse_feed(
        [
            dict(
                title=f'Release {m}',
                country='USD',
                impact='High',
                forecast='1.0%',
                actual=actual,
                date=(NOW + timedelta(minutes=m)).isoformat(),
            )
            for m in minutes
        ]
    )


def tk_root():
    root = helpers.tk_root(withdraw=False)
    root.geometry('900x500')
    return root


class RetainedDrawingTests(unittest.TestCase):
    def setUp(self):
        self.root = tk_root()
        self.clock = [NOW]
        self.list = EventCanvas(self.root, theme.DARK, 'table', lambda e: None, lambda: self.clock[0])
        self.list.pack(fill='both', expand=True)
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def items(self):
        return self.list.cv.find_all()

    def now_label(self):
        return [self.list.cv.itemcget(i, 'text') for i in self.list.cv.find_withtag('nowlabel')]

    def test_unchanged_data_keeps_items_hover_and_moves_the_now_label(self):
        events = feed(-120, -60, 60, 120)
        self.list.update_data(events, timezone.utc)
        self.root.update()
        self.assertEqual(self.now_label(), ['12:00'])
        hover = next(i for i, r in enumerate(self.list.rows) if r.kind == 'event')
        self.list.set_hover(hover)
        before = self.items()
        self.clock[0] = NOW + timedelta(minutes=1)
        self.list.update_data(list(events), timezone.utc)  # what the per-minute render does
        self.assertEqual(self.list.hover_idx, hover)
        self.assertEqual(self.now_label(), ['12:01'])
        self.assertEqual(self.items(), before)

    def test_changed_data_day_or_marker_still_redraw(self):
        events = feed(-120, 60, 120)
        self.list.update_data(events, timezone.utc)
        before = self.items()
        revised = [replace(events[0], actual='1.2%'), *events[1:]]
        self.list.update_data(revised, timezone.utc)
        self.assertNotEqual(self.items(), before)
        self.assertEqual(self.list.events[0].actual, '1.2%')
        before = self.items()
        self.clock[0] = NOW + timedelta(minutes=61)  # 'Release 60' passed: marker moves
        self.list.update_data(revised, timezone.utc)
        self.assertNotEqual(self.items(), before)
        before = self.items()
        self.clock[0] = NOW + timedelta(days=1)  # new day: Today/Tomorrow headings change
        self.list.update_data(revised, timezone.utc)
        self.assertNotEqual(self.items(), before)

    def test_first_empty_update_draws_the_empty_state(self):
        self.list.update_data([], timezone.utc)
        texts = [self.list.cv.itemcget(i, 'text') for i in self.items() if self.list.cv.type(i) == 'text']
        self.assertIn('Nothing to show', texts)

    def test_keyboard_scrolling(self):
        self.list.update_data(feed(*range(-600, 600, 20)), timezone.utc)
        self.root.update()
        self.list.key_scroll('End')
        self.assertAlmostEqual(self.list.cv.yview()[1], 1.0)
        self.list.key_scroll('Home')
        self.assertEqual(self.list.cv.yview()[0], 0.0)
        self.list.key_scroll('Next')
        self.assertGreater(self.list.cv.yview()[0], 0.0)


class NextUpTests(unittest.TestCase):
    def test_same_release_only_updates_the_countdown(self):
        root = tk_root()
        try:
            hero = NextUp(root, theme.DARK, lambda e: None)
            hero.pack(fill='x')
            root.update()
            event = feed(90)[0]
            hero.set(event, timezone.utc, NOW)
            before, text = hero.find_all(), hero.count_text
            hero.set(event, timezone.utc, NOW + timedelta(minutes=1))
            self.assertEqual(hero.find_all(), before)
            self.assertNotEqual(hero.count_text, text)
            hero.set(feed(200)[0], timezone.utc, NOW)
            self.assertNotEqual(hero.find_all(), before)
        finally:
            root.destroy()


class AppLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {'APPDATA': self.tmp.name, 'XDG_CONFIG_HOME': self.tmp.name})
        self.env.start()
        from econpulse import app as main

        self.main = main
        self.root = tk_root()
        self.errors = []
        with mock.patch.object(main.EconPulse, 'init_tray', lambda app: setattr(app, 'tray', None)):
            self.app = main.EconPulse(self.root, Namespace(demo=True, full=True, widget=False))
        self.app.report_exception = lambda *exc: self.errors.append(exc)
        self.root.report_callback_exception = self.app.report_exception
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.env.stop()
        self.tmp.cleanup()

    def test_rebuilds_do_not_pile_up_search_callbacks(self):
        for _ in range(3):  # theme / language switches rebuild the window
            self.app.build_full()
        self.root.update()
        self.assertEqual(len(self.app.search_var.trace_info()), 2)
        self.app.search_var.set('CPI')
        self.root.update()
        self.assertEqual(self.errors, [])

    def test_quit_cancels_pending_timers(self):
        self.assertTrue(self.root.tk.call('after', 'info'))
        with mock.patch.object(self.root, 'destroy'):
            self.app.quit()
        self.assertEqual(self.root.tk.call('after', 'info'), '')

    def test_scroll_keys_scroll_the_list_but_not_while_typing(self):
        self.root.deiconify()
        self.root.lift()
        cv = self.app.main_list.cv
        with mock.patch.object(self.app.main_list, 'key_scroll') as scroll:
            self.app.search.focus_force()
            self.root.update()
            self.app.search.event_generate('<End>')  # caret movement in the search box
            self.root.update()
            scroll.assert_not_called()
            cv.event_generate('<ButtonPress-1>', x=40, y=40)  # clicking the list focuses it
            self.root.update()
            self.assertIs(self.root.focus_get(), cv)
            cv.event_generate('<End>')
            self.root.update()
            scroll.assert_called_once_with('End')


class DiagnosticsTests(AppLifecycleTests):
    def test_diagnostics_never_include_the_api_key_or_home_folder(self):
        from econpulse.storage import data_dir

        self.app.cfg['financecalendar_key'] = 'fc_live_SECRET123'
        log_file = data_dir() / 'econpulse.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        line = f'2026-11-20 WARNING econpulse: failed reading {Path.home() / "private"}'
        log_file.write_text(line + '\n', encoding='utf-8')
        text = self.app.diagnostics()
        self.assertNotIn('SECRET123', text)
        self.assertNotIn(str(Path.home()), text)
        self.assertIn('failed reading ~', text)
        self.assertIn('EconPulse', text)


class BackoffTests(unittest.TestCase):
    def make(self):
        from econpulse.app import EconPulse

        app = EconPulse.__new__(EconPulse)
        app.cfg = {'refresh_minutes': 15}
        app.failures, app.next_attempt, app.retry_until, app.last_attempt = 0, None, None, None
        app.now = lambda: NOW
        return app

    def test_failures_back_off_30_60_120_then_reset(self):
        app = self.make()
        waits = []
        for _ in range(4):
            app._after_fetch(True)
            waits.append(int((app.next_attempt - NOW).total_seconds() // 60))
        self.assertEqual(waits, [30, 60, 120, 120])
        self.assertFalse(app.refresh_due(NOW + timedelta(minutes=119)))
        self.assertTrue(app.refresh_due(NOW + timedelta(minutes=120)))
        app._after_fetch(False)
        self.assertEqual((app.failures, app.next_attempt), (0, None))

    def test_retry_after_is_honoured(self):
        app = self.make()
        app._after_fetch(True, retry_after=3 * 3600)
        self.assertFalse(app.refresh_due(NOW + timedelta(hours=2, minutes=59)))
        self.assertTrue(app.refresh_due(NOW + timedelta(hours=3)))

    def test_normal_interval(self):
        app = self.make()
        self.assertTrue(app.refresh_due(NOW))
        app.last_attempt = NOW
        self.assertFalse(app.refresh_due(NOW + timedelta(minutes=14)))
        self.assertTrue(app.refresh_due(NOW + timedelta(minutes=15)))


class StartupRepairTests(unittest.TestCase):
    def test_source_checkout_never_rewrites_the_startup_entry(self):
        from econpulse.system import repair_startup

        self.assertFalse(repair_startup())


if __name__ == '__main__':
    unittest.main()
