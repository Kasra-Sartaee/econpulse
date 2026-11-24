"""Floating desktop widget: next-release hero, Today/Week list, drag and resize."""

from __future__ import annotations

import logging
import sys
import tkinter as tk

from . import i18n
from .controls import (
    Segmented,
    StatusLine,
    dot,
)
from .event_list import EventCanvas, NextUp
from .storage import save_settings
from .system import native_round
from .theme import glyph, px, unpx

log = logging.getLogger('econpulse')


class WidgetWindowMixin:
    def set_widget_period(self, period):
        if period not in ('day', 'week') or self.widget_period == period:
            return
        self.widget_period = period
        if self.widget_list:
            self.widget_list.set_period(period)
        self.widget_refocus = True
        self.update_widget_period_buttons()
        self.render_widget()
        self.root.after(100, self.focus_widget_when_ready)

    def focus_widget_when_ready(self):
        if self.widget and self.widget.winfo_exists() and self.widget_list:
            self.widget_list.focus_upcoming()

    def update_widget_period_buttons(self):
        control = getattr(self, 'period_control', None)
        if control is not None and control.winfo_exists():
            control.set(self.widget_period)

    def render_widget(self):
        if not (self.widget_list and self.widget and self.widget.winfo_exists()):
            return
        tz = self.tz()
        self.widget_list.update_data(self.visible('all', True), tz, focus=self.widget_refocus)
        self.widget_refocus = False
        if self.widget_hero is not None:
            self.widget_hero.set(self.next_high(), tz, self.now())
        events = self.widget_list.events
        today = self.now().astimezone(tz).date()
        holidays = list(dict.fromkeys(e.currency for e in events if e.is_holiday and e.display_day(tz) == today))
        row = self.widget_holiday_row
        if holidays:
            self.widget_holiday_badge.config(text=self.tr('Bank holiday today') + '  ·  ' + ', '.join(holidays))
            if not row.winfo_manager():
                row.pack(fill='x', pady=(0, px(12)), after=self.widget_controls)
        elif row.winfo_manager():
            row.pack_forget()
        self.render_status()

    WIDGET_W = (395, 720)

    WIDGET_H = (420, 1000)

    def widget_geometry(self):
        """Saved geometry is in logical (96-dpi) units so it survives scaling changes."""
        l, t, r, b = self.workarea()
        sx, sy = self.cfg.get('widget_x'), self.cfg.get('widget_y')
        has_pos = isinstance(sx, int) and isinstance(sy, int)
        try:
            w = px(max(self.WIDGET_W[0], min(self.WIDGET_W[1], int(self.cfg.get('widget_w') or 452))))
            h = px(max(self.WIDGET_H[0], min(self.WIDGET_H[1], int(self.cfg.get('widget_h') or 615))))
        except (TypeError, ValueError):
            w, h = px(452), px(615)
        if has_pos:
            sx, sy = px(sx), px(sy)
            best_area = 0
            for bounds in self.all_workareas():
                ox = max(0, min(sx + w, bounds[2]) - max(sx, bounds[0]))
                oy = max(0, min(sy + h, bounds[3]) - max(sy, bounds[1]))
                if ox * oy > best_area:
                    best_area = ox * oy
                    l, t, r, b = bounds
        w = min(w, max(px(self.WIDGET_W[0]), r - l - 10))
        h = min(h, max(px(self.WIDGET_H[0]), b - t - 10))
        x = max(l, min(sx, r - w)) if has_pos else r - w - px(18)
        y = max(t, min(sy, b - h)) if has_pos else t + px(18)
        return w, h, x, y

    def show_widget(self):
        if self.widget and self.widget.winfo_exists():
            self.last_view = 'widget'
            self.restore_window(self.widget)
            return
        self.last_view = 'widget'
        self.root.withdraw()
        p = self.p
        w = tk.Toplevel(self.root)
        self.widget = w
        w.overrideredirect(True)
        w.attributes('-topmost', bool(self.cfg.get('topmost', True)))
        try:
            w.attributes('-alpha', int(self.cfg.get('widget_opacity', 100)) / 100)
        except (tk.TclError, TypeError, ValueError):
            pass
        width, height, x, y = self.widget_geometry()
        w.geometry(f'{width}x{height}+{x}+{y}')
        self.apply_icon(w)
        self.bind_scroll_keys(w, 'widget_list')
        native = native_round(w, p['line_strong'])
        w.configure(bg=p['line_strong'])
        shell = tk.Frame(w, bg=p['bg'])
        shell.pack(fill='both', expand=True, padx=0 if native else 1, pady=0 if native else 1)

        # ---- title bar (drag handle)
        top = tk.Frame(shell, bg=p['bg'], height=px(48))
        top.pack(fill='x')
        top.pack_propagate(False)
        mark = self.brand(top, p['bg'], 20, 10)
        mark.pack(side='left', padx=(px(16), 0))
        controls = tk.Frame(top, bg=p['bg'])
        controls.pack(side='right', padx=px(8))
        for icon, func, tip in [
            ('calendar', self.show_full, 'Open calendar'),
            ('settings', self.settings, 'Settings'),
            ('close', self.hide_widget, 'Close'),
        ]:
            self.icon_btn(controls, icon, func, tip, 30).pack(side='left', padx=(px(2), 0))
        for widget in (top, mark):
            widget.bind('<ButtonPress-1>', self.drag_start)
            widget.bind('<B1-Motion>', self.drag_move)
            widget.bind('<ButtonRelease-1>', self.drag_end)
            widget.configure(cursor='fleur')

        # ---- next high-impact release
        self.widget_hero = NextUp(shell, p, self.event_detail)
        self.widget_hero.pack(fill='x')

        # ---- period switch + status
        self.widget_controls = tk.Frame(shell, bg=p['bg'])
        self.widget_controls.pack(fill='x', padx=px(18), pady=(px(4), px(12)))
        self.period_control = Segmented(
            self.widget_controls,
            [('day', self.tr('Today')), ('week', self.tr('Week'))],
            self.widget_period,
            self.set_widget_period,
            p,
            height=30,
            min_width=64,
        )
        self.period_control.pack(side='left')
        self.widget_status = StatusLine(self.widget_controls, p, 8)
        self.widget_status.pack(side='right')
        self.widget_holiday_row = tk.Frame(shell, bg=p['bg'])
        self.widget_holiday_dot = tk.Canvas(
            self.widget_holiday_row, width=px(8), height=px(14), bg=p['bg'], highlightthickness=0, borderwidth=0
        )
        dot(self.widget_holiday_dot, px(4), px(7), px(6), p['purple'])
        self.widget_holiday_dot.pack(side='left', padx=(px(18), px(7)))
        self.widget_holiday_badge = self.label(self.widget_holiday_row, '', 9, p['soft'], p['bg'])
        self.widget_holiday_badge.pack(side='left')
        self.hairline(shell)

        # ---- releases
        self.widget_list = EventCanvas(shell, p, 'widget', self.event_detail, self.now, period=self.widget_period)
        self.widget_list.pack(fill='both', expand=True, padx=(0, px(2)))

        # ---- footer
        foot = tk.Frame(shell, bg=p['bg'], height=px(42))
        foot.pack(fill='x', side='bottom')
        foot.pack_propagate(False)
        self.hairline(shell, side='bottom')
        globe, globe_font = glyph('globe', 9)
        tk.Label(foot, text=globe, bg=p['bg'], fg=p['faded'], font=globe_font).pack(side='left', padx=(px(18), px(6)))
        self.widget_timezone = self.label(
            foot, self.tr(self.cfg.get('timezone', 'System local').split(' (')[0]), 8, p['faded'], p['bg']
        )
        self.widget_timezone.pack(side='left')
        right = tk.Frame(foot, bg=p['bg'])
        right.pack(side='right', padx=(0, px(18)))
        self.btn(
            right,
            'Now',
            self.focus_widget_when_ready,
            'subtle',
            None,
            28,
            9,
            icon='target',
            tooltip='Jump to the next release',
        ).pack(side='left')
        self.icon_btn(right, 'refresh', lambda: self.refresh(False), 'Refresh', 28).pack(side='left', padx=(px(2), 0))
        grip = tk.Canvas(foot, width=px(12), height=px(12), bg=p['bg'], highlightthickness=0, borderwidth=0)
        for gx, gy in ((10, 3), (7, 6), (10, 6), (4, 9), (7, 9), (10, 9)):
            dot(grip, px(gx), px(gy), max(2, px(2)), p['faded'])
        if i18n.rtl():
            grip.place(relx=0, rely=1, x=px(4), y=-px(4), anchor='sw')
            grip.config(cursor='size_ne_sw' if sys.platform == 'win32' else 'bottom_left_corner')
        else:
            grip.place(relx=1, rely=1, x=-px(4), y=-px(4), anchor='se')
            grip.config(cursor='size_nw_se' if sys.platform == 'win32' else 'bottom_right_corner')
        grip.bind('<ButtonPress-1>', self.resize_start)
        grip.bind('<B1-Motion>', self.resize_move)
        grip.bind('<ButtonRelease-1>', self.resize_end)
        self.widget_refocus = True
        self.render_widget()
        self.render_status()
        self.root.after(160, self.focus_widget_when_ready)

    def drag_start(self, e):
        if self.widget:
            self.widget_offset = (e.x_root - self.widget.winfo_x(), e.y_root - self.widget.winfo_y())

    def drag_move(self, e):
        if self.widget_offset and self.widget:
            self.widget.geometry(f'+{e.x_root - self.widget_offset[0]}+{e.y_root - self.widget_offset[1]}')

    def drag_end(self, _e):
        if self.widget and self.widget_offset:
            x, y = unpx(self.widget.winfo_x()), unpx(self.widget.winfo_y())
            if (x, y) != (self.cfg.get('widget_x'), self.cfg.get('widget_y')):
                self.cfg['widget_x'], self.cfg['widget_y'] = x, y
                save_settings(self.cfg)
        self.widget_offset = None

    def resize_start(self, e):
        if self.widget:
            self.resize_offset = (
                e.x_root,
                e.y_root,
                self.widget.winfo_width(),
                self.widget.winfo_height(),
                self.widget.winfo_x(),
                self.widget.winfo_y(),
            )

    def resize_move(self, e):
        if not self.widget or not self.resize_offset:
            return
        sx, sy, sw, sh, wx, wy = self.resize_offset
        height = max(px(self.WIDGET_H[0]), min(px(self.WIDGET_H[1]), sh + e.y_root - sy))
        if i18n.rtl():
            width = max(px(self.WIDGET_W[0]), min(px(self.WIDGET_W[1]), sw - (e.x_root - sx)))
            self.widget.geometry(f'{width}x{height}+{wx + (sw - width)}+{wy}')
        else:
            width = max(px(self.WIDGET_W[0]), min(px(self.WIDGET_W[1]), sw + e.x_root - sx))
            self.widget.geometry(f'{width}x{height}')

    def resize_end(self, _e):
        if self.widget:
            self.cfg['widget_w'] = unpx(self.widget.winfo_width())
            self.cfg['widget_h'] = unpx(self.widget.winfo_height())
            if i18n.rtl():
                self.cfg['widget_x'] = unpx(self.widget.winfo_x())
                self.cfg['widget_y'] = unpx(self.widget.winfo_y())
            save_settings(self.cfg)
        self.resize_offset = None

    def _drop_widget(self):
        if self.widget and self.widget.winfo_exists():
            self.widget.destroy()
        self.widget = None
        self.widget_list = None
        self.widget_hero = None

    def hide_widget(self):
        self._drop_widget()
        if not self.tray:
            self.show_full()
