"""End-to-end UI tests: every window opens, saves and closes without errors.

The app runs in demo mode (no network) with its data folder redirected to a
temporary directory, so these tests never touch real settings, the registry
or the clipboard.
"""

from argparse import Namespace
import contextlib
from datetime import UTC
import io
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import helpers

from econpulse import __version__, i18n, theme
from econpulse.controls import FlatButton, Segmented
from econpulse.core import series_key


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(window, command_name):
    """The FlatButton in ``window`` whose callback is the named inner function."""
    for w in descendants(window):
        if isinstance(w, FlatButton) and getattr(w.cmd, '__name__', '') == command_name:
            return w
    raise AssertionError(f'no button running {command_name}()')


def segmented(window, option):
    """The Segmented control in ``window`` that offers ``option``."""
    for w in descendants(window):
        if isinstance(w, Segmented) and option in [value for value, _label in w.options]:
            return w
    raise AssertionError(f'no segmented control offering {option!r}')


class AppTestCase(unittest.TestCase):
    full = True
    demo = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {'APPDATA': self.tmp.name, 'XDG_CONFIG_HOME': self.tmp.name, 'HOME': self.tmp.name}
        self.patches = [
            mock.patch.dict(os.environ, env),
            mock.patch('econpulse.system.set_startup'),
            mock.patch('econpulse.system.safe_open'),
            mock.patch('econpulse.system.open_folder'),
        ]
        for patch in self.patches:
            patch.start()
        from econpulse import app as main

        self.root = helpers.tk_root(withdraw=False)
        self.errors = []
        with mock.patch.object(main.EconPulse, 'init_tray', lambda app: setattr(app, 'tray', None)):
            self.app = main.EconPulse(self.root, Namespace(demo=self.demo, full=self.full, widget=not self.full))
        self.app.report_exception = lambda *exc: self.errors.append(exc)
        self.root.report_callback_exception = self.app.report_exception
        self.root.update()

    def tearDown(self):
        self.app._closing = True
        try:
            for pending in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.tk.call('after', 'cancel', pending)
            self.root.destroy()
        except tk.TclError:
            pass
        self.app = self.root = None
        helpers.collect_tk_garbage()
        i18n.set_language('en')
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()
        self.assertEqual(self.errors, [], 'a Tk callback raised')

    def settle(self):
        self.root.update()
        self.root.update_idletasks()


class DialogTests(AppTestCase):
    def test_release_details_open_for_every_kind_of_event(self):
        events = self.app.events
        samples = [
            next(e for e in events if e.actual),
            next(e for e in events if e.is_holiday),
            next(e for e in events if not e.actual and not e.is_holiday),
        ]
        for event in samples:
            self.app.event_detail(event)
            self.settle()
            self.assertTrue(self.app.detail_window.winfo_exists())
        self.app.detail_window.event_generate('<Escape>')
        self.settle()
        self.assertFalse(self.app.detail_window.winfo_exists())

    def test_release_details_star_and_per_event_note(self):
        from econpulse import state

        event = next(e for e in self.app.events if not e.is_holiday)
        self.app.event_detail(event)
        self.settle()
        window = self.app.detail_window
        button(window, 'flip_star').cmd()
        self.assertIn(state.event_key(event), self.app.starred_keys())
        note_widget = next(w for w in descendants(window) if isinstance(w, tk.Text))
        note_widget.insert('1.0', 'Wait 2 minutes after print')
        button(window, 'close_detail').cmd()
        self.settle()
        self.assertEqual(state.load_event_notes().get(state.event_key(event)), 'Wait 2 minutes after print')

    def test_release_details_show_the_indicators_history(self):
        from dataclasses import replace
        from datetime import timedelta

        from econpulse import history

        event = next(e for e in self.app.events if e.actual and not e.is_holiday)
        earlier = [
            replace(event, instant=event.instant - timedelta(days=30 * n), actual=f'{n}.5%', forecast=f'{n}.0%')
            for n in (1, 2)
        ]
        history.record(earlier, event.instant)
        self.app.event_detail(event)
        self.settle()
        texts = [w.cget('text') for w in descendants(self.app.detail_window) if isinstance(w, tk.Label)]
        self.assertIn('Recent releases', texts)
        self.assertIn('1.5%', texts)
        self.assertIn('+0.5 pp', texts)  # the gap for each past release

    def test_global_shortcut_follows_the_setting_and_reports_conflicts(self):
        started = []

        class FakeHotkey:
            ok = True

            def __init__(self, key, callback):
                self.callback = callback
                started.append(self)

            @staticmethod
            def supported():
                return True

            def start(self):
                return FakeHotkey.ok

            def stop(self):
                started.remove(self)

        with mock.patch('econpulse.system.GlobalHotkey', FakeHotkey), mock.patch.object(self.app, 'demo', False):
            self.app.cfg['global_hotkey'] = True
            self.assertTrue(self.app.apply_global_hotkey())
            self.assertEqual(len(started), 1)
            started[0].callback()  # the key press, from the shortcut's thread
            self.app.ui_queue.get_nowait()()  # ...handled on Tk's thread
            self.settle()
            self.assertTrue(self.app.widget.winfo_exists())
            self.app.cfg['global_hotkey'] = False
            self.app.apply_global_hotkey()
            self.assertEqual(started, [])
            FakeHotkey.ok = False  # another program owns Ctrl+Alt+E
            self.app.cfg['global_hotkey'] = True
            self.assertFalse(self.app.apply_global_hotkey())
            self.assertIsNone(self.app.hotkey)

    def test_new_version_installs_only_in_an_installed_copy_and_only_once_verified(self):
        import time

        from econpulse import system, updates

        self.app.update_info = ('9.9.9', updates.RELEASES_URL)
        with mock.patch.object(updates, 'installed_copy', return_value=False):
            self.app.open_update()  # a portable copy: just the releases page
        system.safe_open.assert_called_with(updates.RELEASES_URL)

        installer = Path(self.tmp.name) / 'EconPulse-9.9.9-Setup.exe'
        with (
            mock.patch.object(updates, 'installed_copy', return_value=True),
            mock.patch('econpulse.app.messagebox.askyesno', return_value=True),
            mock.patch.object(updates, 'download_installer', return_value=installer) as download,
            mock.patch('econpulse.app.subprocess.Popen') as popen,
            mock.patch.object(self.app, 'quit') as quit_app,
        ):
            self.app.open_update()
            deadline = time.monotonic() + 5
            while not popen.called and time.monotonic() < deadline:  # downloaded on a worker thread
                self.app.poll()
                self.root.update()
            download.assert_called_once()
            popen.assert_called_once_with([str(installer), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART'])
            quit_app.assert_called_once()

        with (
            mock.patch.object(updates, 'installed_copy', return_value=True),
            mock.patch('econpulse.app.messagebox.askyesno', return_value=True),
            mock.patch.object(updates, 'download_installer', side_effect=updates.UpdateError('checksum')),
            mock.patch('econpulse.app.subprocess.Popen') as popen,
            mock.patch('econpulse.app.messagebox.showerror') as error,
        ):
            self.app.open_update()
            deadline = time.monotonic() + 5
            while not error.called and time.monotonic() < deadline:
                self.app.poll()
                self.root.update()
            error.assert_called_once()
            popen.assert_not_called()  # a failed check never runs anything

    def test_enter_on_a_focused_button_runs_only_that_button(self):
        event = next(e for e in self.app.events if not e.is_holiday)
        self.app.event_detail(event)
        self.settle()
        window = self.app.detail_window
        star = button(window, 'flip_star')
        star.focus_force()
        self.settle()
        star.event_generate('<Return>')
        self.settle()
        self.assertTrue(window.winfo_exists(), 'Enter on Star must not also close the dialog')
        self.assertIn(series_key(event), self.app.starred_keys())  # ...but it did star the release
        done = button(window, 'close_detail')
        done.focus_force()
        self.settle()
        done.event_generate('<Return>')  # runs close_detail once; a second run must be harmless
        self.settle()
        self.assertFalse(window.winfo_exists())
        window.close_detail()

    def test_opening_another_release_saves_the_open_note(self):
        from econpulse import state

        first, second = [e for e in self.app.events if not e.is_holiday][:2]
        self.app.event_detail(first)
        self.settle()
        note = next(w for w in descendants(self.app.detail_window) if isinstance(w, tk.Text))
        note.insert('1.0', 'half-typed idea')
        self.app.event_detail(second)  # e.g. a toast was clicked
        self.settle()
        self.assertEqual(state.load_event_notes().get(state.event_key(first)), 'half-typed idea')

    def test_letter_shortcuts_are_ignored_while_typing(self):
        action = mock.Mock()
        handler = self.app._unless_typing(action)
        self.assertIsNone(handler(Namespace(widget=tk.Entry(self.root))))
        action.assert_not_called()
        self.assertEqual(handler(Namespace(widget=self.root)), 'break')
        action.assert_called_once()

    def test_status_file_stays_fresh_while_hidden_in_the_tray(self):
        import json

        from econpulse.storage import data_dir

        self.app.cfg['write_status_file'] = True
        self.app.show_widget()
        self.app.hide_widget()
        self.root.withdraw()
        self.settle()
        self.app.last_render_min = None
        self.app._tick()
        status = json.loads((data_dir() / 'next.json').read_text(encoding='utf-8'))
        self.assertIn('next_high_impact', status)

    def test_notes_are_saved_to_the_data_folder(self):
        from econpulse.storage import data_dir

        self.app.notes()
        self.settle()
        window = self.root.winfo_children()[-1]
        text = next(w for w in descendants(window) if isinstance(w, tk.Text))
        text.insert('1.0', 'Watch the CPI print')
        button(window, 'save').cmd()
        self.settle()
        self.assertEqual((data_dir() / 'notes.txt').read_text(encoding='utf-8'), 'Watch the CPI print')
        self.assertFalse(window.winfo_exists())

    def test_settings_save_switches_theme_and_language(self):
        from econpulse.storage import load_settings

        self.app.settings()
        self.settle()
        window = self.app.setting_window
        segmented(window, 'light').command('light')
        segmented(window, 'fa').command('fa')
        button(window, 'save').cmd()
        self.settle()
        self.assertIsNone(self.app.setting_window)
        self.assertEqual(self.app.p, theme.palette('light'))
        self.assertEqual(self.root.cget('bg'), theme.palette('light')['bg'])
        self.assertTrue(i18n.rtl())
        saved = load_settings()
        self.assertEqual((saved['theme'], saved['language']), ('light', 'fa'))
        self.app.settings()  # the whole window again, mirrored
        self.settle()
        button(self.app.setting_window, 'cancel').cmd()
        self.settle()

    def test_high_contrast_and_larger_text_rebuild_every_window(self):
        self.app.settings()
        self.settle()
        window = self.app.setting_window
        segmented(window, 'contrast').command('contrast')
        segmented(window, '130').command('130')
        button(window, 'save').cmd()
        self.settle()
        try:
            self.assertEqual(self.app.p, theme.palette('contrast'))
            self.assertAlmostEqual(theme.scale(), theme._dpi_scale * 1.3)  # layout grows with the text
            self.assertGreater(theme.font(10).actual('size'), 10)  # text really is larger
            self.app.show_widget()
            self.app.event_detail(next(e for e in self.app.events if not e.is_holiday))
            self.app.notes()
            self.settle()
        finally:
            theme.set_text_size(100)  # module-level state: restore for the other tests

    def test_windows_high_contrast_mode_wins_over_the_chosen_theme(self):
        with mock.patch('econpulse.system.high_contrast_active', return_value=True):
            self.assertEqual(self.app.theme_name(), 'contrast')
        self.assertEqual(self.app.theme_name(), self.app.cfg['theme'])

    def test_settings_window_is_reused_and_cancel_discards_changes(self):
        self.app.settings()
        first = self.app.setting_window
        self.app.settings()
        self.assertIs(self.app.setting_window, first)
        segmented(first, 'light').command('light')
        first.event_generate('<Escape>')
        self.settle()
        self.assertEqual(self.app.cfg['theme'], 'dark')

    def test_about_buttons(self):
        from econpulse import system

        self.app.settings()
        self.settle()
        window = self.app.setting_window
        with (
            mock.patch.object(self.root, 'clipboard_append') as append,
            mock.patch.object(self.root, 'clipboard_clear'),
        ):
            button(window, 'copy_diagnostics').cmd()
        self.assertIn(f'EconPulse {__version__}', append.call_args.args[0])
        for w in descendants(window):
            if isinstance(w, FlatButton) and getattr(w.cmd, '__name__', '') == '<lambda>':
                w.cmd()
        opened = [call.args[0] for call in system.safe_open.call_args_list]
        self.assertTrue(any(url.endswith('/issues/new/choose') for url in opened), opened)
        system.open_folder.assert_called_once()

    def test_export_writes_csv_and_ics(self):
        from pathlib import Path

        for name in ('week.csv', 'week.ics'):
            target = Path(self.tmp.name) / name
            with mock.patch('econpulse.dialogs.filedialog.asksaveasfilename', return_value=str(target)):
                self.app.export()
            self.assertGreater(target.stat().st_size, 100, name)
        with mock.patch('econpulse.dialogs.filedialog.asksaveasfilename', return_value=''):
            self.app.export()  # cancelled: nothing happens

    def test_export_with_nothing_visible_says_so(self):
        self.app.search_var.set('no release is called this')
        self.settle()
        with mock.patch('econpulse.dialogs.messagebox.showinfo') as info:
            self.app.export()
        info.assert_called_once()


class WidgetTests(AppTestCase):
    full = False

    def event(self, x, y):
        return mock.Mock(x_root=x, y_root=y)

    def test_widget_periods_drag_and_resize_are_remembered(self):
        from econpulse.storage import load_settings

        self.assertTrue(self.app.widget.winfo_exists())
        for period in ('week', 'day'):
            self.app.set_widget_period(period)
            self.settle()
        x, y = self.app.widget.winfo_x(), self.app.widget.winfo_y()
        self.app.drag_start(self.event(x + 10, y + 10))
        self.app.drag_move(self.event(x + 50, y + 40))
        self.settle()
        self.app.drag_end(None)
        w, h = self.app.widget.winfo_width(), self.app.widget.winfo_height()
        self.app.resize_start(self.event(500, 500))
        self.app.resize_move(self.event(540, 560))
        self.settle()
        self.app.resize_end(None)
        saved = load_settings()
        self.assertNotEqual((saved['widget_x'], saved['widget_y']), (None, None))
        self.assertGreater(saved['widget_h'], 0)
        self.assertNotEqual((self.app.widget.winfo_width(), self.app.widget.winfo_height()), (w, h))

    def test_switching_between_widget_and_calendar(self):
        self.app.hide_widget()  # no tray in tests: falls back to the calendar
        self.settle()
        self.assertIsNone(self.app.widget)
        self.app.show_widget()
        self.settle()
        self.assertTrue(self.app.widget.winfo_exists())

    def test_docked_compact_bar_takes_the_strip_and_gives_it_back(self):
        calls = []

        class FakeAppBar:
            def __init__(self, window):
                self.window = window

            @staticmethod
            def supported():
                return True

            def dock(self, edge, height):
                calls.append(('dock', edge, height))
                return (0, 0, 1200, height)

            def undock(self):
                calls.append(('undock',))

        self.app.cfg.update(widget_compact=True, compact_dock='top')
        with mock.patch('econpulse.ui_widget.AppBar', FakeAppBar):
            self.app._drop_widget()
            self.app.show_widget()
            self.settle()
            self.assertEqual(calls, [('dock', 'top', theme.px(self.app.COMPACT_H))])
            self.assertEqual(self.app.widget.winfo_width(), 1200)
            self.assertEqual(self.app.compact_bar.bind('<B1-Motion>'), '')  # a docked bar can't be dragged
            with mock.patch('econpulse.ui_widget.fullscreen_app_active', return_value=True):
                self.app._tick()  # a full-screen video starts: the bar steps back
            self.assertFalse(self.app.widget.attributes('-topmost'))
            self.app.hide_widget()
        self.assertEqual(calls[-1], ('undock',))
        self.assertIsNone(self.app.appbar)

    def test_compact_ticker_bar_mode_toggles_and_ticks(self):
        self.app.toggle_compact_widget()
        self.settle()
        self.assertTrue(self.app.cfg['widget_compact'])
        self.assertIsNotNone(self.app.compact_bar)
        self.app._tick()
        self.app.toggle_compact_widget()
        self.settle()
        self.assertFalse(self.app.cfg['widget_compact'])
        self.assertIsNone(self.app.compact_bar)
        self.assertIsNotNone(self.app.widget_list)


def live_feed(*minutes_ahead):
    from datetime import datetime, timedelta

    from econpulse.core import parse_feed
    from econpulse.providers.base import FeedResult

    now = datetime.now(UTC)
    rows = [
        {
            'title': f'Invented release {m}',
            'country': 'USD',
            'impact': 'High',
            'forecast': '0.2%',
            'date': (now + timedelta(minutes=m)).isoformat(),
        }
        for m in minutes_ahead
    ]
    return FeedResult(parse_feed(rows), now, 'test', provider='biquote')


class LiveAppTests(AppTestCase):
    """The real refresh path, with the network replaced by a fake provider."""

    demo = False

    def setUp(self):
        self.fetch = mock.patch('econpulse.app.fetch_events', return_value=live_feed(14.5, 120))
        self.fetch.start()
        self.sound = mock.patch('econpulse.system.play_alert_sound')
        self.sound.start()
        with mock.patch('econpulse.system.repair_startup'):
            AppTestCase.setUp(self)
        self.wait_for_refresh()

    def tearDown(self):
        self.fetch.stop()
        self.sound.stop()
        AppTestCase.tearDown(self)

    def wait_for_refresh(self):
        import time

        deadline = time.monotonic() + 10
        while self.app.policy.inflight and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.app.poll()
        self.settle()
        self.assertFalse(self.app.policy.inflight)

    def test_refresh_loads_live_events(self):
        self.assertEqual(self.app.state, 'live')
        self.assertEqual(len(self.app.events), 2)
        self.assertEqual((self.app.policy.failures, self.app.policy.next_attempt), (0, None))

    def test_failed_refresh_backs_off_and_honours_retry_after(self):
        from econpulse.providers import RateLimited

        with mock.patch('econpulse.app.fetch_events', side_effect=RateLimited('slow down', retry_after=600)):
            self.app.refresh(force=True)
            self.wait_for_refresh()
        self.assertEqual(self.app.warning, 'slow down')
        self.assertEqual(self.app.state, 'cached')  # earlier events stay on screen
        self.assertEqual(self.app.policy.failures, 1)
        self.assertIsNotNone(self.app.policy.retry_until)
        self.app.refresh(force=True)  # too early: explained, not sent
        self.assertFalse(self.app.policy.inflight)
        self.assertIn('wait', self.app.warning)

    def test_stale_fetch_result_is_discarded_after_supersede(self):
        old_gen = self.app.policy.generation
        self.app.policy.generation += 1
        self.app.policy.inflight = True
        self.app.io_queue.put(('ok', old_gen, live_feed(999)))
        self.app.poll()
        self.assertTrue(self.app.policy.inflight)
        self.assertEqual(len(self.app.events), 2)

    def test_render_stats_respects_other_currencies_setting(self):
        from datetime import datetime, timedelta

        from econpulse.core import parse_feed

        now = datetime.now(UTC)
        self.app.events = parse_feed(
            [
                {'title': 'US CPI', 'country': 'USD', 'impact': 'High', 'actual': '2%', 'date': now.isoformat()},
                {
                    'title': 'ZA CPI',
                    'country': 'ZAR',
                    'impact': 'High',
                    'actual': '4%',
                    'date': (now + timedelta(minutes=5)).isoformat(),
                },
            ]
        )
        self.app.cfg['other_currencies'] = False
        self.app.render_stats()
        self.assertEqual(self.app.stat_widgets[1][0].cget('text'), '1')
        self.app.cfg['other_currencies'] = True
        self.app.render_stats()
        self.assertEqual(self.app.stat_widgets[1][0].cget('text'), '2')

    def test_burst_check_only_runs_when_enabled_and_the_source_is_healthy(self):
        from datetime import datetime, timedelta

        from econpulse.core import parse_feed

        just_out = datetime.now(UTC) - timedelta(seconds=50)
        self.app.events = parse_feed(
            [{'id': 'x:1', 'title': 'CPI', 'country': 'USD', 'impact': 'High', 'date': just_out.isoformat()}]
        )
        with mock.patch.object(self.app, 'refresh') as refresh:
            self.app._tick()
            refresh.assert_not_called()  # opt-in: off by default
            self.app.cfg['burst_poll'] = True
            self.app.policy.failures = 1
            self.app._tick()
            refresh.assert_not_called()  # never while failing / backing off
            self.app.policy.failures, self.app.has_actuals = 0, False
            self.app._tick()
            refresh.assert_not_called()  # a schedule-only source has nothing to wait for
            self.app.has_actuals = True
            self.app._tick()
            self.app._tick()
            refresh.assert_called_once_with(force=True)

    def test_high_impact_alert_fires_once(self):
        from econpulse.storage import data_dir

        self.app.cfg['notifications'] = True
        self.app._tick()
        self.app._tick()
        self.settle()
        toasts = [t for t in self.app.toasts if t.winfo_exists()]
        self.assertEqual(len(toasts), 1)
        self.assertTrue((data_dir() / 'fired.json').exists())

    def test_quitting_while_an_alert_is_showing_closes_everything(self):
        # Regression: cancelling timers used to break the toast's teardown, so
        # the main window survived quit() and the process kept running.
        import tkinter

        self.app.toast('High-impact release in 15 min', 'USD Invented release')
        self.settle()
        self.app.quit()
        self.assertIsNone(tkinter._default_root)
        with self.assertRaises(tk.TclError):
            self.root.winfo_exists()


class CommandLineTests(unittest.TestCase):
    def test_version_flag(self):
        from econpulse.__main__ import main

        out = io.StringIO()
        with (
            mock.patch.object(sys, 'argv', ['econpulse', '--version']),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as stop,
        ):
            main()
        self.assertEqual(stop.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f'EconPulse {__version__}')

    def test_second_instance_shows_a_message_instead_of_starting(self):
        from econpulse import __main__ as entry

        helpers.tk_root().destroy()  # skip where Tk is unavailable
        with (
            mock.patch.object(sys, 'argv', ['econpulse']),
            mock.patch.object(entry.system, 'setup_logging'),
            mock.patch.object(entry.system, 'acquire_single_instance', return_value=False),
            mock.patch.object(entry.messagebox, 'showinfo') as info,
            mock.patch.object(entry, 'EconPulse') as app,
        ):
            entry.main()
        info.assert_called_once()
        app.assert_not_called()


if __name__ == '__main__':
    unittest.main()
