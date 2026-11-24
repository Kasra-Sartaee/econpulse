"""Event list rendering, text fitting, widget geometry and tray routing."""

from datetime import UTC, timedelta
import queue
import sys
import types
import unittest
from unittest.mock import patch

from helpers import NOW, collect_tk_garbage, tk_root

from econpulse import theme
from econpulse.app import EconPulse
from econpulse.core import parse_feed


class TextFitterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk_root()

    @classmethod
    def tearDownClass(cls):
        for pending in cls.root.tk.splitlist(cls.root.tk.call('after', 'info')):
            cls.root.tk.call('after', 'cancel', pending)
        cls.root.destroy()
        cls.root = None
        collect_tk_garbage()

    def test_fit_and_wrap(self):
        ft = theme.font(10)
        fitter = theme.TextFitter()
        text = 'Non-Farm Employment Change and a very long revised descriptor'
        width = ft.measure('Non-Farm Employment')
        fitted = fitter.fit(ft, text, width)
        self.assertTrue(fitted.endswith('…'))
        self.assertLessEqual(ft.measure(fitted), width)
        self.assertEqual(fitter.fit(ft, 'CPI', width), 'CPI')
        lines = fitter.wrap(ft, text, width)
        self.assertEqual(' '.join(lines), text)
        self.assertTrue(all(ft.measure(line) <= width or ' ' not in line for line in lines))


class VirtualisedListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk_root()

    @classmethod
    def tearDownClass(cls):
        for pending in cls.root.tk.splitlist(cls.root.tk.call('after', 'info')):
            cls.root.tk.call('after', 'cancel', pending)
        cls.root.destroy()
        cls.root = None
        collect_tk_garbage()

    def make(self, mode, n=300):
        from econpulse.event_list import EventCanvas

        opened = []
        events = parse_feed(
            [
                dict(
                    id=f'e{i}',
                    title=f'Indicator {i}',
                    country='USD',
                    impact='High',
                    date=(NOW - timedelta(hours=40) + timedelta(minutes=20 * i)).isoformat(),
                    actual='1%' if i < 120 else '',
                )
                for i in range(n)
            ]
        )
        events.sort(key=lambda e: (e.display_day(UTC), e.instant))
        lst = EventCanvas(self.root, theme.DARK, mode, opened.append, lambda: NOW, period='week')
        lst.pack(fill='both', expand=True)
        self.root.geometry('900x600')
        self.root.deiconify()
        self.root.update()
        lst.update_data(events, UTC)
        self.root.update()
        return lst, events, opened

    def test_only_rows_near_viewport_are_drawn(self):
        for mode in ('table', 'widget'):
            lst, events, _ = self.make(mode)
            self.assertEqual(len([r for r in lst.rows if r.kind == 'event']), len(events))  # all laid out
            self.assertLess(len(lst.drawn), 40)  # but few drawn
            lst.cv.yview_moveto(1.0)
            self.root.update()
            self.assertIn(len(lst.rows) - 1, lst.drawn)
            self.assertNotIn(0, lst.drawn)
            lst.destroy()

    def test_now_marker_click_and_countdowns(self):
        lst, _events, opened = self.make('table')
        kinds = [r.kind for r in lst.rows]
        self.assertEqual(kinds.count('now'), 1)
        now_idx = kinds.index('now')
        self.assertTrue(lst.rows[now_idx + 1].value.instant > NOW)
        row = next(r for r in lst.rows if r.kind == 'event' and r.y > 0)
        lst.cv.yview_moveto(0)
        self.root.update()
        lst.clicked(type('E', (), {'y': row.y + 5})())
        self.assertIs(opened[0], row.value)
        self.assertTrue(lst.countdowns)
        lst.tick()
        lst.destroy()


class WindowTests(unittest.TestCase):
    def test_widget_geometry_is_stored_in_logical_pixels(self):
        app = EconPulse.__new__(EconPulse)
        app.cfg = {'widget_x': 1000, 'widget_y': 100, 'widget_w': 452, 'widget_h': 615}
        app.workarea = lambda: (0, 0, 3840, 2100)
        app.all_workareas = lambda: [(0, 0, 3840, 2100)]
        old = theme._scale
        try:
            theme._scale = 1.5
            self.assertEqual(app.widget_geometry(), (678, 922, 1500, 150))
            theme._scale = 1.0
            self.assertEqual(app.widget_geometry(), (452, 615, 1000, 100))
        finally:
            theme._scale = old

    def test_restore_routes_to_the_last_view(self):
        app = EconPulse.__new__(EconPulse)
        calls = []
        app.show_full = lambda: calls.append('full')
        app.show_widget = lambda: calls.append('widget')
        app.last_view = 'full'
        app.restore_last_view()
        app.last_view = 'widget'
        app.restore_last_view()
        self.assertEqual(calls, ['full', 'widget'])

    def test_tray_default_item_queues_a_ui_action(self):
        class Item:
            def __init__(self, text, action=None, **kw):
                self.text, self.action, self.default = text, action, kw.get('default', False)

        class Menu:
            SEPARATOR = object()

            def __init__(self, *items):
                self.items = items

        class Icon:
            def __init__(self, _name, _image, _title, menu):
                self.menu = menu

            def run(self):
                pass

        fake = types.SimpleNamespace(Menu=Menu, MenuItem=Item, Icon=Icon)
        app = EconPulse.__new__(EconPulse)
        app.ui_queue = queue.Queue()
        app.update_info = None
        app.restore_last_view = lambda: None
        with patch.dict(sys.modules, {'pystray': fake}):
            app.init_tray()
        first = app.tray.menu.items[0]
        self.assertTrue(first.default)
        first.action(None, None)
        self.assertIs(app.ui_queue.get_nowait(), app.restore_last_view)


if __name__ == '__main__':
    unittest.main()
