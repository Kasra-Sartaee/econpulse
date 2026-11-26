"""Full calendar window: sidebar, header and search, summary, filters and the release table."""

from __future__ import annotations

import logging
import tkinter as tk

from . import __version__, i18n, system, theme
from .controls import (
    Label,
    NavItem,
    Panel,
    StatusLine,
    dot,
)
from .core import CURRENCIES
from .event_list import EventCanvas
from .storage import save_settings
from .system import native_titlebar
from .theme import fitter, font, glyph, px

log = logging.getLogger('econpulse')

TAB_NAMES = [
    ('all', 'calendar', 'Calendar'),
    ('today', 'today', 'Today'),
    ('upcoming', 'upcoming', 'Upcoming'),
    ('released', 'released', 'Released'),
    ('holidays', 'holiday', 'Bank holidays'),
]
TAB_TITLES = {
    'all': 'Economic Calendar',
    'today': 'Today',
    'upcoming': 'Upcoming',
    'released': 'Released',
    'holidays': 'Bank holidays',
}


class CalendarWindowMixin:
    def focus_search(self):
        if hasattr(self, 'search') and self.search.winfo_exists() and self.root.winfo_viewable():
            self.search.focus_set()
            self.search.select_range(0, 'end')

    def toggle_summary(self):
        self.cfg['summary_visible'] = not self.cfg.get('summary_visible', True)
        save_settings(self.cfg)
        if self.cfg['summary_visible']:
            self.summary_frame.pack(fill='x', after=self.summary_gap_before)
            self.summary_gap_after.pack(fill='x', after=self.summary_frame)
        else:
            self.summary_frame.pack_forget()
            self.summary_gap_after.pack_forget()
        self.summary_toggle.set_caption(self.tr('Hide summary' if self.cfg['summary_visible'] else 'Show summary'))

    def build_full(self):
        p, root = self.p, self.root
        for frame in self._full_frames:
            if frame.winfo_exists():
                frame.destroy()
        root.configure(bg=p['bg'])
        native_titlebar(root, p, theme.is_dark(self.theme_name()))

        shell = tk.Frame(root, bg=p['bg'])
        shell.pack(fill='both', expand=True)
        self._full_frames = [shell]
        self._focus_main = True  # open the table at today, not nine days ago
        self.build_sidebar(shell)
        tk.Frame(shell, bg=p['line'], width=1).pack(side='left', fill='y')

        body = tk.Frame(shell, bg=p['bg'])
        body.pack(side='left', fill='both', expand=True, padx=px(28), pady=(px(20), px(14)))

        # ---- title row
        heading = tk.Frame(body, bg=p['bg'])
        heading.pack(fill='x')
        titles = tk.Frame(heading, bg=p['bg'])
        titles.pack(side='left', fill='y')
        self.title_label = self.label(titles, TAB_TITLES[self.tab], 19, p['text'], p['bg'], weight='semibold')
        self.title_label.pack(anchor='w')
        meta = tk.Frame(titles, bg=p['bg'])
        meta.pack(anchor='w', pady=(px(1), 0))
        self.clock_label = self.label(meta, '', 9, p['soft'], p['bg'])
        self.clock_label.pack(side='left')
        self.table_count = self.label(meta, '', 9, p['faded'], p['bg'])
        self.table_count.pack(side='left', padx=(px(10), 0))
        actions = tk.Frame(heading, bg=p['bg'])
        actions.pack(side='right')
        self.btn(actions, 'Open widget', self.show_widget, 'primary', None, 34, 9, icon='widget').pack(side='right')
        for icon, func, tip in [
            ('settings', self.settings, 'Settings'),
            ('export', self.export, 'Export'),
            ('refresh', lambda: self.refresh(False), 'Refresh'),
        ]:
            self.icon_btn(actions, icon, func, tip, 34).pack(side='right', padx=(0, px(4)))
        self.build_search(actions)

        # ---- summary
        self.summary_gap_before = tk.Frame(body, bg=p['bg'], height=px(18))
        self.summary_gap_before.pack(fill='x')
        self.summary_frame = Panel(body, p, radius=12)
        inner = self.summary_frame.body
        self.stat_widgets = []
        for i, (caption, value, desc, colour) in enumerate(
            [
                ('Next high impact', '--:--:--', 'Awaiting data', 'text'),
                ('Results published', '0', 'Actual values received', 'text'),
                ('Holidays', '0', 'Bank and market closures', 'text'),
            ]
        ):
            inner.grid_columnconfigure(self.col(i * 2, 4), weight=1, uniform='stat')
            cell = tk.Frame(inner, bg=p['card'])
            cell.grid(row=0, column=self.col(i * 2, 4), sticky='nsew', padx=px(18), pady=(px(12), px(12)))
            top = tk.Frame(cell, bg=p['card'])
            top.pack(anchor='w', fill='x')
            if i == 0:
                mark = tk.Canvas(top, width=px(12), height=px(14), bg=p['card'], highlightthickness=0, borderwidth=0)
                dot(mark, px(4), px(7), px(6), p['red'])
                mark.pack(side='left')
            self.label(top, caption, 9, p['faded']).pack(side='left')
            big = self.label(cell, value, 18, p[colour], numeric=True)
            big.pack(anchor='w', pady=(px(2), 0))
            small = self.label(cell, desc, 9, p['soft'], anchor='w')
            small.pack(anchor='w', fill='x')
            self.stat_widgets.append((big, small))
            if i < 2:
                tk.Frame(inner, bg=p['line'], width=1).grid(
                    row=0, column=self.col(i * 2 + 1, 4), sticky='ns', pady=px(14)
                )
        self.summary_gap_after = tk.Frame(body, bg=p['bg'], height=px(16))
        if self.cfg.get('summary_visible', True):
            self.summary_frame.pack(fill='x')
            self.summary_gap_after.pack(fill='x')
        else:
            self.summary_gap_before.configure(height=px(16))

        # ---- filters
        filters = tk.Frame(body, bg=p['bg'])
        filters.pack(fill='x')
        self.currency_buttons = {}
        for cur in ('ALL', *CURRENCIES):
            b = self.btn(
                filters, 'All' if cur == 'ALL' else cur, lambda c=cur: self.toggle_currency(c), 'chip', None, 28, 9
            )
            b.pack(side='left', padx=(0, px(2)))
            self.currency_buttons[cur] = b
        tk.Frame(filters, bg=p['line_strong'], width=1, height=px(16)).pack(side='left', padx=px(10))
        self.impact_buttons = {}
        for imp in ('High', 'Medium', 'Low', 'Holiday'):
            b = self.btn(filters, imp, lambda a=imp: self.toggle_impact(a), 'chip', None, 28, 9, impact=imp)
            b.pack(side='left', padx=(0, px(2)))
            self.impact_buttons[imp] = b
        self.summary_toggle = self.btn(
            filters,
            'Hide summary' if self.cfg.get('summary_visible', True) else 'Show summary',
            self.toggle_summary,
            'subtle',
            None,
            28,
            9,
        )
        self.summary_toggle.pack(side='right')

        # ---- table
        self.spacer(body, 12)
        table = Panel(body, p, radius=12, fit=False)
        table.pack(fill='both', expand=True)
        self.main_list = EventCanvas(table.body, p, 'table', self.event_detail, self.now)
        self.main_list.pack(fill='both', expand=True, padx=(px(2), px(2)), pady=(px(2), px(4)))

        footer = tk.Frame(body, bg=p['bg'])
        footer.pack(fill='x', pady=(px(10), 0))
        self.status = self.label(footer, 'Loading calendar data…', 8, p['faded'], p['bg'], anchor='w')
        self.status.pack(side='left', fill='x', expand=True)
        self.attribution = self.label(footer, '', 8, p['faded'], p['bg'], cursor='hand2')
        self.attribution.pack(side='right')
        self.attribution.bind('<Button-1>', lambda _e: system.safe_open(self.provider_info()[1]))
        self.update_link = self.label(footer, '', 8, p['text'], p['bg'], cursor='hand2')
        self.update_link.bind('<Button-1>', lambda _e: self.open_update())
        self.update_nav()
        self.update_filter_buttons()
        self.render()

    def build_sidebar(self, parent):
        p = self.p
        rail = tk.Frame(parent, bg=p['side'], width=px(216))
        rail.pack(side='left', fill='y')
        rail.pack_propagate(False)
        self.brand(rail, p['side'], 24, 12).pack(anchor='w', padx=px(20), pady=(px(22), px(26)))
        self.label(rail, 'Views', 8, p['faded'], p['side'], weight='semibold').pack(
            anchor='w', padx=px(22), pady=(0, px(6))
        )
        self.nav = {}
        for key, icon, name in TAB_NAMES:
            item = NavItem(rail, icon, self.tr(name), lambda k=key: self.set_tab(k), p)
            item.pack(fill='x', padx=px(10), pady=px(1))
            self.nav[key] = item
        self.label(rail, 'Tools', 8, p['faded'], p['side'], weight='semibold').pack(
            anchor='w', padx=px(22), pady=(px(22), px(6))
        )
        NavItem(rail, 'notes', self.tr('Trading notes'), self.notes, p).pack(fill='x', padx=px(10), pady=px(1))

        foot = tk.Frame(rail, bg=p['side'])
        foot.pack(side='bottom', fill='x', padx=px(22), pady=px(20))
        self.rail_source = StatusLine(foot, p, 9, bg=p['side'])
        self.rail_source.pack(anchor='w')
        self.rail_sync = self.label(foot, '', 8, p['faded'], p['side'], anchor='w')
        self.rail_sync.pack(anchor='w', pady=(px(2), 0))
        self.label(foot, f'{self.tr("Version")} {__version__}', 8, p['faded'], p['side']).pack(
            anchor='w', pady=(px(10), 0)
        )

    def build_search(self, parent):
        p = self.p
        panel = Panel(parent, p, radius=8, fill=p['input'], outline=p['line_strong'])
        panel.pack(side='right', padx=(0, px(12)))
        box = panel.body
        icon_text, icon_font = glyph('search', 10)
        tk.Label(box, text=icon_text, bg=p['input'], fg=p['faded'], font=icon_font).pack(
            side='left', padx=(px(8), px(6))
        )
        self.search = tk.Entry(
            box,
            textvariable=self.search_var,
            bd=0,
            highlightthickness=0,
            bg=p['input'],
            justify='right' if i18n.rtl() else 'left',
            fg=p['text'],
            insertbackground=p['text'],
            font=font(10),
            width=22,
            selectbackground=p['raised'],
            selectforeground=p['text'],
        )
        self.search.pack(side='left', ipady=px(5))
        placeholder = Label(
            box, text=self.tr('Search events or currency'), bg=p['input'], fg=p['faded'], font=font(10), cursor='xterm'
        )
        clear_text, clear_font = glyph('clear', 8)
        clear = tk.Label(box, text=clear_text, bg=p['input'], fg=p['faded'], font=clear_font, cursor='hand2')
        clear.bind('<Button-1>', lambda _e: (self.search_var.set(''), self.search.focus_set()))
        placeholder.bind('<Button-1>', lambda _e: self.search.focus_set())
        tk.Frame(box, bg=p['input'], width=px(8)).pack(side='right')

        def sync(*_):
            if self.search_var.get():
                placeholder.place_forget()
                clear.pack(side='right', padx=(px(4), 0))
            else:
                if i18n.rtl():
                    placeholder.place(in_=self.search, relx=1, x=0, rely=0.5, anchor='e')
                else:
                    placeholder.place(in_=self.search, x=0, rely=0.5, anchor='w')
                clear.pack_forget()

        def escape(_e):
            if self.search_var.get():
                self.search_var.set('')
            else:
                self.root.focus_set()
            return 'break'

        self.search.bind('<FocusIn>', lambda _e: panel.set_outline(p['faded']))
        self.search.bind('<FocusOut>', lambda _e: panel.set_outline(p['line_strong']))
        self.search.bind('<Escape>', escape)
        # The variable outlives rebuilds (theme/language changes); drop the previous
        # header's callbacks so they don't pile up and fire on destroyed widgets.
        for token in self._search_traces:
            self.search_var.trace_remove('write', token)
        self._search_traces = [
            self.search_var.trace_add('write', sync),
            self.search_var.trace_add('write', lambda *_: self.schedule_search()),
        ]
        sync()

    def schedule_search(self):
        """Debounce: filter once typing pauses instead of on every keystroke."""
        if self._search_job:
            self.root.after_cancel(self._search_job)
        self._search_job = self.root.after(140, self._run_search)

    def _run_search(self):
        self._search_job = None
        self.render_main(keep_scroll=False)

    def update_nav(self):
        for key, item in self.nav.items():
            item.set_active(self.tab == key)
        if hasattr(self, 'title_label') and self.title_label.winfo_exists():
            self.title_label.config(text=self.tr(TAB_TITLES[self.tab]))

    def set_tab(self, view):
        if view == self.tab:
            return
        self.tab = view
        self.update_nav()
        self.render_main(keep_scroll=False, focus=True)

    def update_filter_buttons(self):
        selected = set(self.cfg.get('currencies', []))
        for key, b in self.currency_buttons.items():
            b.set_kind('selected' if (key == 'ALL' and not selected) or (key != 'ALL' and key in selected) else 'chip')
        for key, b in self.impact_buttons.items():
            b.set_kind(
                'selected'
                if key in self.cfg.get('impacts', []) or (key == 'Holiday' and self.cfg.get('holiday'))
                else 'chip'
            )

    def toggle_currency(self, cur):
        selected = set(self.cfg.get('currencies') or [])
        if cur == 'ALL':
            selected = set()
        elif cur in selected:
            selected.remove(cur)
        else:
            selected.add(cur)
        extra = sorted(c for c in selected if c not in CURRENCIES)
        self.cfg['currencies'] = [c for c in CURRENCIES if c in selected] + extra
        self._filters_changed()

    def toggle_impact(self, imp):
        if imp == 'Holiday':
            self.cfg['holiday'] = not self.cfg['holiday']
        else:
            current = set(self.cfg['impacts'])
            if imp in current:
                current.remove(imp)
            else:
                current.add(imp)
            self.cfg['impacts'] = [i for i in ('High', 'Medium', 'Low') if i in current]
        self._filters_changed()

    def _filters_changed(self):
        save_settings(self.cfg)
        self.update_filter_buttons()
        self.render_main(keep_scroll=False, focus=True)
        self.render_widget()
        self.render_stats()

    def render_main(self, keep_scroll=True, focus=False):
        if not self.main_list or not self.main_list.winfo_exists():
            return
        shown = self.visible()
        focus = focus or self._focus_main
        if shown:
            self._focus_main = False
        self.main_list.update_data(shown, self.tz(), focus=focus, keep_scroll=keep_scroll, starred=self.starred_keys())
        if self.table_count.winfo_exists():
            self.table_count.config(text='·   ' + i18n.count(len(shown), 'release'))

    def render_attribution(self):
        """Footer credit for the data source (required by some providers) and the update notice."""
        label = getattr(self, 'attribution', None)
        if label is None or not label.winfo_exists():
            return
        text, _url = self.provider_info()
        label.config(text=i18n.bidi(self.tr(text)))
        link = self.update_link
        if self.update_info:
            link.config(text=i18n.bidi(self.tr('New version available') + f' · {self.update_info[0]}'))
            if not link.winfo_manager():
                link.pack(side='right', padx=(0, px(14)))
        elif link.winfo_manager():
            link.pack_forget()

    def render_stats(self):
        self._next_high = self.next_high()
        if not getattr(self, 'stat_widgets', None) or not self.stat_widgets[0][0].winfo_exists():
            return
        now = self.now()
        watched = self.watched_currencies()
        events = [e for e in self.events if watched is None or e.currency in watched]
        big, small = self.stat_widgets[0]
        nxt = self._next_high
        big.config(text=nxt.countdown(now) if nxt else '—')
        small.config(
            text=fitter.fit(font(9), f'{nxt.currency}  ·  {nxt.title}', px(250))
            if nxt
            else self.tr('No upcoming high-impact release')
        )
        self.stat_widgets[1][0].config(text=str(sum(bool(e.actual) and not e.is_holiday for e in events)))
        self.stat_widgets[2][0].config(text=str(sum(e.is_holiday for e in events)))
