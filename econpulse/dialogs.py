"""Dialogs: release details, preferences, trading notes and export."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from . import REPO_URL, __version__, i18n, state, system, theme
from .controls import (
    FlatSelect,
    Panel,
    Segmented,
    TinyScrollbar,
    Toggle,
    actual_color,
    impact_mark,
    wheel_units,
)
from .core import CURRENCIES, TIMEZONES
from .exports import save_csv, save_ics
from .providers import PROVIDERS
from .storage import data_dir, safe_write_text, save_settings, validate_settings
from .system import native_titlebar
from .theme import font, px

log = logging.getLogger('econpulse')


class DialogsMixin:
    def diagnostics(self) -> str:
        """Plain-text facts for bug reports. Never includes API keys or notes;
        the home folder is masked."""
        import platform

        try:
            tk_version = self.root.tk.call('info', 'patchlevel')
        except tk.TclError:
            tk_version = '?'
        lines = [
            f'EconPulse {__version__}' + (' (packaged)' if getattr(sys, 'frozen', False) else ' (source)'),
            f'OS: {platform.platform()}',
            f'Python: {platform.python_version()}  Tk: {tk_version}',
            f'Language: {i18n.language()}  Theme: {self.cfg.get("theme")}  Scale: {theme.scale():.2f}',
            f'Data source: {self.cfg.get("provider")} -> showing {self.source} '
            f'(actuals: {self.has_actuals}, events: {len(self.events)})',
            f'Last sync: {self.at.isoformat() if self.at else "never"}  Failures in a row: {self.failures}',
            f'Status: {self.warning or "ok"}',
            '',
            'Recent log warnings/errors:',
        ]
        try:
            text = (data_dir() / 'econpulse.log').read_text(encoding='utf-8', errors='replace')
            recent = [line for line in text.splitlines() if ' WARNING ' in line or ' ERROR ' in line][-15:]
            lines.extend(recent or ['(none)'])
        except OSError:
            lines.append('(no log file)')
        report = '\n'.join(lines)
        home = str(Path.home())
        return report.replace(home, '~') if home and home != '/' else report

    def _dialog(self, title, parent=None):
        p = self.p
        parent = parent or (self.widget if self.widget and self.widget.winfo_exists() else self.root)
        d = tk.Toplevel(self.root)
        d.withdraw()
        d.title(title)
        d.configure(bg=p['bg'])
        self.apply_icon(d)
        if parent.winfo_viewable():
            d.transient(parent)
        return d, parent

    def _present(self, d, parent, width, height):
        """Size, centre over the parent (clamped to the work area) and show."""
        d.update_idletasks()
        l, t, r, b = self.workarea()
        w = min(width, r - l - px(20))
        h = min(height or d.winfo_reqheight(), b - t - px(20))
        if parent.winfo_viewable():
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
        else:
            x, y = l + (r - l - w) // 2, t + (b - t - h) // 3
        x, y = max(l, min(x, r - w)), max(t, min(y, b - h))
        d.geometry(f'{w}x{h}+{x}+{y}')
        d.deiconify()
        native_titlebar(d, self.p, self.cfg['theme'] == 'dark')
        d.lift()
        d.focus_force()

    def event_detail(self, e):
        p, tz = self.p, self.tz()
        if self.detail_window and self.detail_window.winfo_exists():
            # Close through the window's own handler so a half-typed note is saved.
            close_previous = getattr(self.detail_window, 'close_detail', None)
            if close_previous:
                close_previous()
            else:
                self.detail_window.destroy()
        d, parent = self._dialog(f'{e.currency} · {e.title}')
        self.detail_window = d
        d.resizable(False, False)
        body = tk.Frame(d, bg=p['bg'])
        body.pack(fill='both', expand=True, padx=px(28), pady=(px(24), px(22)))

        kicker = tk.Frame(body, bg=p['bg'])
        kicker.pack(anchor='w')
        mark = tk.Canvas(kicker, width=px(18), height=px(16), bg=p['bg'], highlightthickness=0, borderwidth=0)
        impact_mark(mark, px(1), px(8), e.impact, p)
        mark.pack(side='left', padx=(0, px(6)))
        impact = self.tr('Bank / market holiday') if e.is_holiday else i18n.impact_text(e.impact)
        parts = [e.currency, impact] + ([e.status.title()] if e.status and e.status != 'scheduled' else [])
        self.label(kicker, '   ·   '.join(parts), 9, p['soft'], p['bg'], weight='semibold').pack(side='left')

        self.label(
            body, e.title, 17, p['text'], p['bg'], weight='semibold', wraplength=px(430), justify='left', anchor='w'
        ).pack(anchor='w', fill='x', pady=(px(10), px(4)))
        now = self.now()
        clock = self.tr('All day') if e.is_holiday else self.tr(e.time_label) if e.is_untimed else e.when_text(tz)
        when = f'{i18n.date_text(e.display_day(tz), "full")}   ·   {clock}'
        if not e.is_untimed:
            if e.instant <= now:
                when += '   ·   ' + self.tr('released')
            else:
                when += '   ·   ' + i18n.countdown_in(e.countdown(now))
        self.label(body, when, 9, p['soft'], p['bg']).pack(anchor='w')

        stats = Panel(body, p, radius=12)
        stats.pack(fill='x', pady=(px(20), px(16)))
        if e.actual:
            actual, actual_fg = e.actual, actual_color(p, e)
        elif e.is_untimed:
            actual, actual_fg = self.tr('n/a'), p['faded']
        else:
            actual, actual_fg = self.tr('Not posted' if e.instant <= now else 'Pending'), p['faded']
        raw = (e.actual, e.forecast, e.previous)
        for col, (name, value, fg) in enumerate(
            [
                ('Actual', actual, actual_fg),
                ('Forecast', e.forecast or '—', p['text'] if e.forecast else p['faded']),
                ('Previous', e.previous or '—', p['text'] if e.previous else p['faded']),
            ]
        ):
            stats.body.grid_columnconfigure(self.col(col * 2, 4), weight=1, uniform='stats')
            cell = tk.Frame(stats.body, bg=p['card'])
            cell.grid(row=0, column=self.col(col * 2, 4), sticky='nsew', padx=px(16), pady=px(12))
            self.label(cell, name, 9, p['faded']).pack(anchor='w')
            numeric = bool(raw[col])
            self.label(
                cell,
                value,
                17 if numeric else 12,
                fg,
                weight='bold' if numeric and col == 0 else 'normal',
                numeric=numeric,
            ).pack(anchor='w', pady=(px(2), 0))
            if col < 2:
                tk.Frame(stats.body, bg=p['line'], width=1).grid(
                    row=0, column=self.col(col * 2 + 1, 4), sticky='ns', pady=px(14)
                )
        tr = self.tr
        info = []
        if e.actual_tone:
            info.append(tr(f'Actual came in {e.actual_tone} than forecast.'))
        if e.revised_from:
            info.append(i18n.revised_from(e.revised_from))
        if e.period:
            info.append(f'{tr("Reference period")}: {e.period}')
        if e.is_holiday:
            info.append(tr('All-day market or bank holiday; trading hours may vary.'))
        info.append(f'{tr("Source")}: {e.source}')
        self.label(body, '\n'.join(info), 9, p['faded'], p['bg'], justify='left').pack(anchor='w')

        # Per-event private trading note (persists across recurring releases of the same indicator)
        note_key = state.event_key(e)
        existing_note = state.load_event_notes().get(note_key, '')
        self.label(body, 'Release note', 9, p['soft'], p['bg'], weight='semibold').pack(
            anchor='w', pady=(px(14), px(4))
        )
        note_panel = Panel(body, p, radius=8, bg=p['bg'], fill=p['input'], outline=p['line_strong'])
        note_panel.pack(fill='x')
        note_box = tk.Text(
            note_panel.body,
            height=2,
            bg=p['input'],
            fg=p['text'],
            insertbackground=p['text'],
            font=font(9),
            wrap='word',
            bd=0,
            highlightthickness=0,
            padx=px(8),
            pady=px(5),
        )
        note_box.pack(fill='x')
        if existing_note:
            note_box.insert('1.0', existing_note)

        def close_detail():
            if not d.winfo_exists():
                return  # already closed (e.g. Escape and the close button in quick succession)
            current = note_box.get('1.0', 'end-1c').strip()
            if current != existing_note:
                try:
                    state.save_event_note(note_key, current)
                except OSError:
                    log.warning('could not save release note', exc_info=True)
            d.destroy()

        buttons = tk.Frame(body, bg=p['bg'])
        buttons.pack(fill='x', pady=(px(18), 0))
        is_starred = note_key in self.starred_keys()
        star_btn = None

        def flip_star():
            now_starred = self.toggle_starred(e)
            star_btn.icon = 'star_fill' if now_starred else 'star'
            star_btn.set_caption(self.tr('Starred' if now_starred else 'Star'))

        star_btn = self.btn(
            buttons,
            'Starred' if is_starred else 'Star',
            flip_star,
            'normal',
            None,
            36,
            icon='star_fill' if is_starred else 'star',
        )
        star_btn.pack(side='left')
        self.btn(buttons, 'Done', close_detail, 'primary', None, 36).pack(side='right')
        if system.is_safe_url(e.url):
            self.btn(
                buttons,
                'Open source page',
                lambda: system.safe_open(e.url),
                'normal',
                None,
                36,
                icon='link',
                tooltip=system.url_host(e.url),
            ).pack(side='right', padx=(0, px(8)))
        d.close_detail = close_detail
        d.protocol('WM_DELETE_WINDOW', close_detail)
        d.bind('<Escape>', lambda _e: close_detail())
        d.bind('<Return>', lambda _e: None if d.focus_get() is note_box else close_detail())
        self._present(d, parent, px(500), None)

    def notes(self):
        p = self.p
        d, parent = self._dialog(self.tr('Trading notes'))
        d.minsize(px(420), px(330))
        self.label(d, 'Trading notes', 17, p['text'], p['bg'], weight='semibold').pack(
            anchor='w', padx=px(28), pady=(px(24), px(2))
        )
        self.label(d, 'Stored on this computer only.', 9, p['faded'], p['bg']).pack(anchor='w', padx=px(28))
        footer = tk.Frame(d, bg=p['bg'])
        footer.pack(side='bottom', fill='x', padx=px(28), pady=(0, px(22)))
        area = Panel(d, p, radius=12, fit=False)
        area.pack(fill='both', expand=True, padx=px(28), pady=px(16))
        t = tk.Text(
            area.body,
            bg=p['card'],
            fg=p['text'],
            insertbackground=p['text'],
            font=font(10),
            wrap='word',
            borderwidth=0,
            highlightthickness=0,
            undo=True,
            padx=px(12),
            pady=px(10),
            selectbackground=p['raised'],
            selectforeground=p['text'],
            spacing1=px(2),
            spacing3=px(2),
        )
        t.pack(side='left', fill='both', expand=True)
        bar = TinyScrollbar(area.body, t, p)
        bar.pack(side='right', fill='y')
        t.configure(yscrollcommand=bar.set)
        try:
            t.insert('1.0', (data_dir() / 'notes.txt').read_text(encoding='utf-8'))
        except OSError:
            pass
        t.edit_reset()

        def save():
            dest = data_dir() / 'notes.txt'
            try:
                safe_write_text(dest, t.get('1.0', 'end-1c'))
            except OSError as exc:
                messagebox.showerror(self.tr('Notes'), f'{self.tr("Could not save notes:")}\n{exc}', parent=d)
                return
            d.destroy()

        self.btn(footer, 'Save', save, 'primary', None, 36).pack(side='right')
        self.btn(footer, 'Cancel', d.destroy, 'normal', None, 36).pack(side='right', padx=px(8))
        self.label(footer, 'Ctrl+S to save', 8, p['faded'], p['bg']).pack(side='left')
        d.bind('<Control-s>', lambda _e: save())
        d.protocol('WM_DELETE_WINDOW', save)
        self._present(d, parent, px(520), px(480))
        t.focus_set()

    def export(self):
        events = self.visible()
        if not events:
            messagebox.showinfo(self.tr('Export'), self.tr('No events in this view.'), parent=self.root)
            return
        filename = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension='.csv',
            filetypes=[('Spreadsheet CSV', '*.csv'), ('Calendar ICS', '*.ics')],
            title=self.tr('Export visible releases'),
        )
        if not filename:
            return
        try:
            if filename.lower().endswith('.ics'):
                save_ics(filename, events, self.tz())
            else:
                save_csv(filename, events, self.tz())
        except OSError as e:
            messagebox.showerror(self.tr('Export failed'), str(e), parent=self.root)

    def settings(self):
        if self.setting_window and self.setting_window.winfo_exists():
            self.setting_window.lift()
            self.setting_window.focus_force()
            return
        p = self.p
        d, parent = self._dialog(self.tr('Preferences'))
        self.setting_window = d
        d.minsize(px(540), px(460))
        header = tk.Frame(d, bg=p['bg'])
        header.pack(fill='x', padx=px(28), pady=(px(24), px(8)))
        self.label(header, 'Preferences', 17, p['text'], p['bg'], weight='semibold').pack(anchor='w')
        self.label(header, 'Appearance, alerts and data sources', 9, p['faded'], p['bg']).pack(
            anchor='w', pady=(px(2), 0)
        )
        footer = tk.Frame(d, bg=p['bg'])
        footer.pack(side='bottom', fill='x', padx=px(28), pady=(px(14), px(20)))
        self.hairline(d, side='bottom')
        area = tk.Frame(d, bg=p['bg'])
        area.pack(fill='both', expand=True, padx=(px(28), px(8)), pady=(px(4), 0))
        scroll = tk.Canvas(area, bg=p['bg'], highlightthickness=0, borderwidth=0)
        scroll.pack(side='left', fill='both', expand=True)
        bar = TinyScrollbar(area, scroll, p)
        bar.configure(bg=p['bg'])
        bar.pack(side='right', fill='y')
        scroll.configure(yscrollcommand=bar.set)
        inner = tk.Frame(scroll, bg=p['bg'])
        winid = scroll.create_window(0, 0, window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _e: scroll.configure(scrollregion=scroll.bbox('all')))
        scroll.bind('<Configure>', lambda e: scroll.itemconfigure(winid, width=e.width - px(14)))
        d.bind('<MouseWheel>', lambda e: scroll.yview_scroll(wheel_units(scroll, e), 'units'))
        d.bind('<Button-4>', lambda _e: scroll.yview_scroll(-3, 'units'))
        d.bind('<Button-5>', lambda _e: scroll.yview_scroll(3, 'units'))
        values = {}

        def group(title):
            self.label(inner, title, 9, p['soft'], p['bg'], weight='semibold').pack(anchor='w', pady=(px(18), px(8)))
            panel = Panel(inner, p, radius=12)
            panel.pack(fill='x')
            panel.rows = 0
            return panel

        def row(panel, caption, clickable=None):
            if panel.rows:
                tk.Frame(panel.body, bg=p['line'], height=1).pack(fill='x', padx=(px(16), 0))
            panel.rows += 1
            line = tk.Frame(panel.body, bg=p['card'], cursor='hand2' if clickable else '')
            line.pack(fill='x', padx=px(16), pady=px(10))
            lab = self.label(line, caption, 10, p['text'], cursor='hand2' if clickable else '')
            lab.pack(side='left')
            if clickable:
                for w in (line, lab):
                    w.bind('<Button-1>', lambda _e: clickable())
            return line

        def segmented(panel, caption, name, options):
            var = tk.StringVar(value=str(self.cfg.get(name)))
            line = row(panel, caption)
            Segmented(line, options, var.get(), var.set, p, height=30, min_width=72).pack(side='right')
            values[name] = var

        def select(panel, caption, name, items):
            var = tk.StringVar(value=str(self.cfg.get(name)))
            line = row(panel, caption)
            FlatSelect(line, var, items, p, width=230, height=32, labels={item: self.tr(item) for item in items}).pack(
                side='right'
            )
            values[name] = var

        def toggle(panel, caption, name, initial=None):
            var = tk.BooleanVar(value=bool(self.cfg.get(name) if initial is None else initial))
            line = row(panel, caption, clickable=lambda: var.set(not var.get()))
            Toggle(line, var, p).pack(side='right')
            values[name] = var

        look = group(self.tr('Appearance'))
        segmented(look, self.tr('Theme'), 'theme', [('dark', self.tr('Dark')), ('light', self.tr('Light'))])
        segmented(look, self.tr('Language'), 'language', i18n.language_choices())
        select(look, self.tr('Time zone'), 'timezone', list(TIMEZONES))
        segmented(
            look, self.tr('Open on launch'), 'mode', [('widget', self.tr('Widget')), ('full', self.tr('Calendar'))]
        )

        money = group(self.tr('Currencies'))
        holder = tk.Frame(money.body, bg=p['card'])
        holder.pack(fill='x', padx=px(16), pady=px(12))
        self.label(
            holder,
            'Show only the selected currencies. With none selected, all major currencies are shown.',
            9,
            p['faded'],
            wraplength=px(480),
            justify='left',
        ).pack(anchor='w')
        selected = set(self.cfg.get('currencies') or [])
        currency_buttons = {}

        def toggle_currency(cur):
            selected.symmetric_difference_update({cur})
            for code, button in currency_buttons.items():
                button.set_kind('primary' if code in selected else 'normal')

        chips = tk.Frame(holder, bg=p['card'])
        chips.pack(anchor='w', pady=(px(10), 0))
        for i, cur in enumerate(CURRENCIES):
            b = self.btn(
                chips, cur, lambda cc=cur: toggle_currency(cc), 'primary' if cur in selected else 'normal', 58, 28, 9
            )
            b.grid(
                row=i // 5, column=self.col(i % 5, 4), padx=(px(6), 0) if i18n.rtl() else (0, px(6)), pady=(0, px(6))
            )
            currency_buttons[cur] = b

        def all_currencies():
            selected.clear()
            for button in currency_buttons.values():
                button.set_kind('normal')

        self.btn(holder, 'Show all', all_currencies, 'subtle', None, 28, 9).pack(anchor='w', pady=(px(2), 0))
        money.rows = 1
        toggle(money, self.tr('Also show other currencies (ZAR, TRY, MXN…)'), 'other_currencies')

        floating = group(self.tr('Widget'))
        toggle(floating, self.tr('Always on top of other windows'), 'topmost')
        if system.startup_supported():
            toggle(floating, self.tr('Start automatically at login'), 'startup', system.get_startup())
        toggle(floating, self.tr('Show bank and market holidays'), 'holiday')

        alerts = group(self.tr('Alerts'))
        toggle(alerts, self.tr('Desktop notifications for high-impact releases'), 'notifications')
        toggle(alerts, self.tr('Notify when Actual is published'), 'alert_actual')
        toggle(alerts, self.tr('Fast check after high-impact releases'), 'burst_poll')
        toggle(alerts, self.tr('Play a sound'), 'sound')
        stages = set(self.cfg.get('notify_minutes', [30, 15, 5, 0]))
        stage_buttons = {}
        stage_line = row(alerts, self.tr('Alert me'))
        stage_box = tk.Frame(stage_line, bg=p['card'])
        stage_box.pack(side='right')

        def toggle_stage(n):
            stages.symmetric_difference_update({n})
            stage_buttons[n].set_kind('primary' if n in stages else 'normal')

        for n, caption in [
            (30, i18n.minutes(30)),
            (15, i18n.minutes(15)),
            (5, i18n.minutes(5)),
            (0, self.tr('At release')),
        ]:
            b = self.btn(
                stage_box, caption, lambda n=n: toggle_stage(n), 'primary' if n in stages else 'normal', None, 28, 9
            )
            b.pack(side='left', padx=(px(4), 0))
            stage_buttons[n] = b

        sources = group(self.tr('Data source'))
        provider_var = tk.StringVar(value=self.cfg.get('provider', 'biquote'))
        line = row(sources, self.tr('Calendar data from'))
        FlatSelect(
            line,
            provider_var,
            list(PROVIDERS),
            p,
            width=230,
            height=32,
            labels={key: provider.name for key, provider in PROVIDERS.items()},
        ).pack(side='right')
        values['provider'] = provider_var
        notes = tk.Frame(sources.body, bg=p['card'])
        notes.pack(fill='x', padx=px(16), pady=(0, px(12)))
        for text in (
            self.tr('biquote: free, no key; Actual, Forecast and Previous values.'),
            self.tr(
                'Forex Factory weekly export: official schedule feed, no Actual values. '
                'Also used automatically if the chosen source is unavailable.'
            ),
            self.tr(
                'FinanceCalendar.com: official-agency data; needs your own API key (the free plan has no figures).'
            ),
        ):
            self.label(notes, text, 9, p['faded'], wraplength=px(480), justify='left', anchor='w').pack(
                anchor='w', fill='x', pady=(0, px(4))
            )
        key_line = row(sources, self.tr('FinanceCalendar.com API key'))
        key_var = tk.StringVar(value=self.cfg.get('financecalendar_key', ''))
        key_box = Panel(key_line, p, radius=8, bg=p['card'], outline=p['line_strong'], fill=p['input'])
        key_box.pack(side='right')
        tk.Entry(
            key_box.body,
            textvariable=key_var,
            show='•',
            width=24,
            bd=0,
            highlightthickness=0,
            bg=p['input'],
            fg=p['text'],
            insertbackground=p['text'],
            font=font(9),
        ).pack(padx=px(8), pady=px(5))
        get_key = row(
            sources,
            self.tr('Get an API key'),
            clickable=lambda: system.safe_open('https://www.financecalendar.com/api/'),
        )
        self.label(get_key, '↗', 10, p['faded']).pack(side='right')

        updates_group = group(self.tr('Updates'))
        toggle(updates_group, self.tr('Tell me when a new version is out (checks GitHub once a day)'), 'check_updates')

        about = group(self.tr('About'))
        facts = tk.Frame(about.body, bg=p['card'])
        facts.pack(fill='x', padx=px(16), pady=px(12))
        self.label(facts, f'EconPulse {__version__}', 11, p['text'], weight='semibold').pack(anchor='w')
        for text in (
            self.tr('Free and open source (MIT licence). By Aref Hosseini, Kasra Sartaee and contributors.'),
            self.tr('Not affiliated with any data provider. Not financial advice.'),
        ):
            self.label(facts, text, 9, p['faded'], wraplength=px(480), justify='left', anchor='w').pack(
                anchor='w', fill='x', pady=(px(2), 0)
            )
        actions = tk.Frame(facts, bg=p['card'])
        actions.pack(anchor='w', pady=(px(10), 0))
        copy_button = None

        def copy_diagnostics():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.diagnostics())
            copy_button.set_caption(self.tr('Copied'))

        for caption, command in (
            (self.tr('Project page'), lambda: system.safe_open(REPO_URL)),
            (self.tr('Report an issue'), lambda: system.safe_open(f'{REPO_URL}/issues/new/choose')),
            (self.tr('Open data folder'), lambda: system.open_folder(data_dir())),
            (self.tr('Copy diagnostics'), copy_diagnostics),
        ):
            b = self.btn(actions, caption, command, 'normal', None, 28, 9)
            b.pack(side='left', padx=(0, px(6)))
            if command is copy_diagnostics:
                copy_button = b
        tk.Frame(inner, bg=p['bg'], height=px(16)).pack(fill='x')

        def cancel():
            d.destroy()
            self.setting_window = None

        def save():
            before = (self.cfg.get('provider'), self.cfg.get('financecalendar_key'), self.cfg.get('check_updates'))
            for name, var in values.items():
                self.cfg[name] = var.get()
            self.cfg['financecalendar_key'] = ''.join(key_var.get().split())[:128]
            extra_cur = sorted(c for c in selected if c not in CURRENCIES)
            self.cfg['currencies'] = [c for c in CURRENCIES if c in selected] + extra_cur
            self.cfg['notify_minutes'] = [n for n in (30, 15, 5, 0) if n in stages]
            if 'startup' in values:
                try:
                    if bool(self.cfg['startup']) != system.get_startup():
                        system.set_startup(bool(self.cfg['startup']))
                except (OSError, RuntimeError) as exc:
                    messagebox.showwarning(self.tr('Start at login'), str(exc), parent=d)
            self.cfg = validate_settings(self.cfg)
            save_settings(self.cfg)
            after = (self.cfg.get('provider'), self.cfg.get('financecalendar_key'), self.cfg.get('check_updates'))
            source_changed = before[:2] != after[:2]
            i18n.set_language(self.cfg.get('language', 'en'))
            if self.tray:
                try:
                    self.tray.update_menu()
                except Exception:
                    pass
            cancel()
            showing = self.widget is not None and self.widget.winfo_exists()
            if showing:
                self._drop_widget()
            self.p = theme.palette(self.cfg['theme'])
            self.root.configure(bg=self.p['bg'])
            self.build_full()
            if showing:
                self.show_widget()
            self.render()
            if source_changed:
                self.failures, self.next_attempt, self.retry_until = 0, None, None
                self.refresh(force=True, supersede=True)
            if after[2] and not before[2]:
                self.check_for_updates()

        self.btn(footer, self.tr('Save'), save, 'primary', None, 36).pack(side='right', padx=(px(8), 0))
        self.btn(footer, self.tr('Cancel'), cancel, 'normal', None, 36).pack(side='right')
        d.protocol('WM_DELETE_WINDOW', cancel)
        d.bind('<Escape>', lambda _e: cancel())
        _l, t, _r, b = self.workarea()
        self._present(d, parent, px(600), min(px(740), b - t - px(40)))
