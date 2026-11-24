"""EconPulse application core: state, data refresh, rendering, clock, alerts and tray.

The window-building code lives in mixins (:mod:`.ui_calendar`, :mod:`.ui_widget`,
:mod:`.dialogs`); all of them share this object's state through ``self``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
import logging
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from . import REPO_URL, __version__, i18n, state, system, theme, updates
from .controls import (
    FlatButton,
    IconButton,
    Label,
    Mirror,
)
from .core import AlertEngine, desired_timezone
from .demo import demo_events
from .dialogs import DialogsMixin
from .feed import fetch_events, load_cache
from .providers import FALLBACK, PROVIDERS, ProviderError
from .storage import data_dir, load_settings, read_json, safe_write_json, save_settings
from .system import native_round
from .theme import fitter, font, num, px
from .ui_calendar import CalendarWindowMixin
from .ui_widget import WidgetWindowMixin

log = logging.getLogger('econpulse')
BACKOFF_MINUTES = (30, 60, 120)  # after 1, 2, 3+ failed refreshes in a row


def asset(name: str) -> Path:
    """Bundled resource (icons), from a source checkout or a PyInstaller build."""
    return Path(__file__).resolve().parent / 'assets' / name


class EconPulse(CalendarWindowMixin, WidgetWindowMixin, DialogsMixin):
    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.cfg = load_settings()
        i18n.set_language(self.cfg.get('language', 'en'))
        i18n.install_rtl_geometry()
        self.p = theme.palette(self.cfg['theme'])
        self.events = []
        self.at = None
        self.source = '—'
        self.state = 'loading'
        self.warning = ''
        self.coverage = 'unverified'
        self.provider = self.cfg.get('provider', 'biquote')
        self.has_actuals = True
        self.inflight = False
        self._fetch_id = 0
        self.last_attempt = None
        self.failures = 0
        self.next_attempt = None  # backoff after failures
        self.retry_until = None  # a source asked us to wait (HTTP 429/503 Retry-After)
        self.update_info = None  # (version, url) when a newer release exists
        self.io_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self.alerts = AlertEngine(read_json(data_dir() / 'fired.json', []))
        self.tab = 'all'
        self.search_var = tk.StringVar()
        self._search_traces = []
        self.widget = None
        self.tray = None
        self.main_list = None
        self.widget_list = None
        self.widget_hero = None
        self.setting_window = None
        self.detail_window = None
        self.last_render_min = None
        self.widget_offset = None
        self.resize_offset = None
        self._timer = None
        self._refresh_timer = None
        self._search_job = None
        self._next_high = None
        self._focus_main = False
        self._full_frames = []
        self._burst_fired = set()
        self.toasts = []
        self.demo = args.demo
        self.widget_period = 'day'  # always start in Today; Week is a session choice
        self.last_view = 'full' if args.full else 'widget' if args.widget else self.cfg.get('mode', 'widget')
        self._closing = False
        self._dirty = False
        self.widget_refocus = True

        theme.init_scale(root)
        root.report_callback_exception = self.report_exception
        self.size_root()
        root.title('EconPulse')
        root.configure(bg=self.p['bg'])
        root.protocol('WM_DELETE_WINDOW', self.close_full)
        root.bind('<Escape>', lambda _e: self.show_widget())
        root.bind('<F5>', lambda _e: self.refresh(False))
        root.bind('<Control-f>', lambda _e: self.focus_search())
        self.bind_scroll_keys(root, 'main_list')
        self.apply_icon(root)
        root.option_add('*tearOff', False)
        if args.demo:
            self.events = demo_events()
            self.state = 'demo'
            self.source = 'DEMO'
        else:
            cached = load_cache()
            self.events, self.at, self.source = cached.events, cached.at, cached.source
            self.coverage, self.has_actuals = cached.coverage, cached.has_actuals
            self.provider = cached.provider or self.provider
            self.state = 'cached' if cached.events else 'loading'
            system.repair_startup()  # the app folder may have moved since Startup was enabled
            self._remember_update(self.cfg.get('latest_version', ''))
        self.build_full()
        self.init_tray()
        if args.widget or (not args.full and self.cfg.get('mode') == 'widget'):
            self.show_widget()
        if not args.demo:
            self.refresh(force=True)
        self.root.after(250, self.poll)
        self._timer = self.root.after(1000, self.tick)
        self._refresh_timer = self.root.after(60_000, self.auto_refresh)
        if not args.demo:
            self.root.after(20_000, self.check_for_updates)

    def report_exception(self, exc, value, tb):
        """Tk swallows callback errors under pythonw; record them instead."""
        log.error('Unhandled UI exception', exc_info=(exc, value, tb))

    def tr(self, value):
        return i18n.tr(value)

    def menu_text(self, value):
        return i18n.bidi(i18n.tr(value))

    @staticmethod
    def col(index, last):
        """Grid column for logical ``index`` (0..last), mirrored in right-to-left mode."""
        return last - index if i18n.rtl() else index

    def now(self):
        return datetime.now(UTC)

    def tz(self):
        # Resolved once per setting: tzlocal/zoneinfo lookups ran every second before.
        name = self.cfg.get('timezone', 'System local')
        if getattr(self, '_tz_name', None) != name:
            self._tz_name, self._tz = name, desired_timezone(name)
        return self._tz

    def apply_icon(self, win):
        icon = asset('econpulse.ico')
        if sys.platform == 'win32' and icon.exists():
            try:
                win.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

    def label(self, parent, text, size=10, fg=None, bg=None, bold=False, weight=None, numeric=False, **kw):
        weight = weight or ('bold' if bold else 'normal')
        if i18n.rtl():
            if 'anchor' in kw:
                kw['anchor'] = i18n.mirror_anchor(kw['anchor'])
            if kw.get('justify') == 'left':
                kw['justify'] = 'right'
        return Label(
            parent,
            text=self.tr(text),
            bg=bg or self.p['card'],
            fg=fg or self.p['text'],
            font=num(size, weight) if numeric else font(size, weight),
            **kw,
        )

    def btn(
        self,
        parent,
        text,
        cmd,
        kind='normal',
        width=None,
        height=34,
        size=9,
        dot=None,
        icon=None,
        impact=None,
        tooltip=None,
    ):
        return FlatButton(
            parent,
            self.tr(text),
            cmd,
            self.p,
            kind,
            width,
            height,
            size,
            dot=dot,
            icon=icon,
            impact=impact,
            tooltip=self.tr(tooltip) if tooltip else None,
        )

    def icon_btn(self, parent, icon, cmd, tooltip, size=32):
        return IconButton(parent, icon, cmd, self.p, size, tooltip=self.tr(tooltip))

    def spacer(self, parent, size=10, bg=None):
        tk.Frame(parent, bg=bg or self.p['bg'], height=px(size)).pack(fill='x')

    def hairline(self, parent, side='top', padx=0, bg=None):
        line = tk.Frame(parent, bg=bg or self.p['line'], height=1)
        line.pack(side=side, fill='x', padx=padx)
        return line

    def brand(self, parent, bg, size=22, text_size=11):
        p = self.p
        f = font(text_size, 'semibold')
        width = px(size) + px(9) + fitter.measure(f, 'EconPulse') + px(2)
        c = tk.Canvas(parent, width=width, height=px(size) + 2, bg=bg, highlightthickness=0, borderwidth=0)
        mid = (px(size) + 2) / 2
        m = Mirror(width)
        if theme.has_aa():
            c.create_image(m.x(0), mid, image=theme.brand_image(px(size), p), anchor=m.a('w'))
        c.create_text(m.x(px(size) + px(9)), mid, text='EconPulse', anchor=m.a('w'), fill=p['text'], font=f)
        return c

    def size_root(self):
        l, t, r, b = self.workarea()
        avail_w, avail_h = r - l - px(24), b - t - px(24)
        w, h = min(px(1240), avail_w), min(px(840), avail_h)
        self.root.minsize(min(px(1010), avail_w), min(px(620), avail_h))
        self.root.geometry(f'{w}x{h}+{l + (r - l - w) // 2}+{t + max(0, (b - t - h) // 2 - px(10))}')

    SCROLL_KEYS = ('Up', 'Down', 'Prior', 'Next', 'Home', 'End')

    def bind_scroll_keys(self, window, list_attr):
        def scroll(e, key):
            lst = getattr(self, list_attr)
            if isinstance(e.widget, (tk.Entry, tk.Text)) or not lst or not lst.winfo_exists():
                return None  # keys belong to the field being typed in
            lst.key_scroll(key)
            return 'break'

        for key in self.SCROLL_KEYS:
            window.bind(f'<{key}>', lambda e, k=key: scroll(e, k))

    def watched_currencies(self):
        """Currencies the user follows: the selection, else the majors (unless
        "Show other currencies" is on, in which case None means all)."""
        return state.watched_currencies(self.cfg)

    def starred_keys(self):
        return set(self.cfg.get('starred') or ())

    def toggle_starred(self, e):
        key = state.event_key(e)
        current = list(self.cfg.get('starred') or [])
        if key in current:
            current.remove(key)
        elif len(current) < 100:
            current.append(key)
        self.cfg['starred'] = current
        save_settings(self.cfg)
        self.render_main()
        self.render_widget()
        return key in current

    def next_high(self):
        now = self.now()
        watched = self.watched_currencies()
        upcoming = [
            e
            for e in self.events
            if e.impact == 'High'
            and not e.is_untimed
            and e.instant > now
            and (watched is None or e.currency in watched)
        ]
        return min(upcoming, key=lambda e: e.instant) if upcoming else None

    def visible(self, view=None, widget=False):
        tz = self.tz()
        now = self.now()
        today = now.astimezone(tz).date()
        view = view or self.tab
        chosen = self.watched_currencies()
        impacts = set(self.cfg.get('impacts') or [])
        show_holidays = self.cfg.get('holiday', True)
        query = self.search_var.get().strip().lower() if not widget else ''
        sunday = today - timedelta(days=(today.weekday() + 1) % 7)
        keyed = []
        for e in self.events:
            if chosen is not None and e.currency not in chosen:
                continue
            if e.is_holiday:
                if not show_holidays:
                    continue
            elif e.impact not in impacts:
                continue
            if query and query not in e.title.lower() and query not in e.currency.lower():
                continue
            day = e.display_day(tz)
            if widget:
                # Never discard released events or holidays due to a rolling
                # 'last 3 hours' window. The list is fully scrollable.
                if self.widget_period == 'day' and day != today:
                    continue
                if self.widget_period == 'week' and not sunday <= day <= sunday + timedelta(days=6):
                    continue
            elif (
                (view == 'today' and day != today)
                or (view == 'upcoming' and ((not e.is_untimed and e.instant < now) or (e.is_untimed and day < today)))
                or (view == 'released' and (e.is_untimed or e.instant > now or e.instant < now - timedelta(days=9)))
                or (view == 'holidays' and not e.is_holiday)
                or (view == 'all' and (day < today - timedelta(days=9) or day > today + timedelta(days=8)))
            ):
                continue
            when = datetime.combine(day, time.min, tzinfo=tz) if e.is_holiday else e.instant
            keyed.append(((day, when, e.currency, e.title), e))
        keyed.sort(key=lambda pair: pair[0])
        return [e for _key, e in keyed]

    def render(self):
        self.render_main()
        self.render_widget()
        self.render_stats()
        self.render_status()

    def _status_parts(self):
        """(state label, colour, detail) describing data freshness."""
        p = self.p
        tr = self.tr
        if self.demo:
            return tr('Demo'), p['amber'], tr('Sample data, not live')
        if self.at:
            age = max(0, int((self.now() - self.at).total_seconds() / 60))
            stamp = self.at.astimezone(self.tz()).strftime('%H:%M')
            detail = i18n.sync_detail(stamp, age)
            if self.inflight:
                detail = tr('Syncing…')
            live = self.state == 'live'
            if live and not self.has_actuals:
                return tr('Schedule only'), p['amber'], detail
            colour = p['green'] if live and age <= 45 else p['amber']
            return tr('Live' if live else 'Cached'), colour, detail
        return (
            tr('Connecting' if self.inflight else 'Offline'),
            (p['amber'] if self.inflight else p['red']),
            tr('Fetching calendar…' if self.inflight else 'No calendar data yet'),
        )

    def render_status(self):
        if not hasattr(self, 'status') or not self.status.winfo_exists():
            return
        state, colour, detail = self._status_parts()
        if self.demo:
            msg = self.tr('Demo mode  ·  illustrative values, not live market data')
        elif self.at:
            age = max(int((self.now() - self.at).total_seconds() / 60), 0)
            stamp = f'{self.at.astimezone(self.tz()):%H:%M}'
            msg = i18n.sync_status(self.source, stamp, age)
            if self.inflight:
                msg += '  ·  ' + self.tr('Syncing…')
            if self.warning:
                msg += '  ·  ' + self.tr(self.warning)[:140]
            retry = self.retry_until or self.next_attempt
            if retry and not self.inflight and retry > self.now():
                msg += '  ·  ' + self.tr('Next try') + f' {retry.astimezone(self.tz()):%H:%M}'
            if age > 45:
                msg += '  ·  ' + self.tr('data may be stale')
        else:
            msg = detail + ('  ·  ' + self.warning[:95] if self.warning and not self.inflight else '')
        self.status.config(text=msg, fg=self.p['amber'] if self.warning or self.demo else self.p['faded'])
        self.render_attribution()
        self.rail_source.set(colour, state)
        self.rail_sync.config(text=detail)
        if self.widget and self.widget.winfo_exists() and hasattr(self, 'widget_status'):
            count = len(self.widget_list.events) if self.widget_list else 0
            self.widget_status.set(colour, state, i18n.count(count, 'release'))
            self.widget_timezone.config(text=self.tr(self.cfg.get('timezone', 'System local').split(' (')[0]))

    def tick(self):
        try:
            self._tick()
        except Exception:
            log.exception('tick failed')
        finally:
            if not self._closing:
                self._timer = self.root.after(1000 - datetime.now().microsecond // 1000 + 5, self.tick)

    def _tick(self):
        now = self.now()
        # Windows in the tray / behind the widget skip cosmetic per-second work;
        # the first tick after they reappear catches up (alerts below always run).
        full_visible = bool(self.root.winfo_viewable())
        if self.main_list and full_visible:
            self.main_list.tick()
        if self.widget_list:
            self.widget_list.tick()
        if self.widget_hero is not None and self.widget and self.widget.winfo_exists():
            self.widget_hero.tick(now)
        if getattr(self, 'stat_widgets', None):
            nxt = self._next_high
            if nxt and nxt.instant <= now:
                self.render_stats()
            elif nxt and self.stat_widgets[0][0].winfo_exists():
                self.stat_widgets[0][0].config(text=nxt.countdown(now))
        if full_visible and hasattr(self, 'clock_label') and self.clock_label.winfo_exists():
            local = now.astimezone(self.tz())
            self.clock_label.config(text=f'{i18n.date_text(local.date(), "long")}  ·  {local:%H:%M:%S}')
        minute = now.strftime('%Y%m%d%H%M')
        widget_visible = bool(self.widget and self.widget.winfo_exists())
        if self.last_render_min != minute:
            self.last_render_min = minute
            if full_visible or widget_visible:
                self._dirty = False
                self.render()
            else:
                self._dirty = True
        elif self._dirty and (full_visible or widget_visible):
            self._dirty = False
            self.render()
        if not self.demo and self.cfg.get('notifications', True):
            found = self.alerts.check(
                self.events,
                now=now,
                currencies=self.watched_currencies(),
                enabled_stages=self.cfg.get('notify_minutes', [30, 15, 5, 0]),
                starred=self.starred_keys(),
            )
            if found:
                try:
                    safe_write_json(data_dir() / 'fired.json', sorted(self.alerts.fired))
                except OSError:
                    log.warning('could not persist fired alerts', exc_info=True)
                grouped = defaultdict(list)
                for e, stage in found:
                    grouped[(e.instant, stage)].append(e)
                for (_instant, stage), group in grouped.items():
                    heading = i18n.alert_heading(stage)
                    detail = ', '.join(f'{e.currency} {e.title}' for e in group[:3])
                    if len(group) > 3:
                        detail += f' (+{len(group) - 3})'
                    self.notify(heading, detail, event=group[0])
        if (
            not self.demo
            and self.cfg.get('burst_poll', False)
            and self.has_actuals  # a schedule-only source has nothing to wait for
            and not self.inflight
            and not self.failures  # never add requests while the source is failing or backing off
            and (not self.retry_until or now >= self.retry_until)
        ):
            token = state.due_burst_poll(
                self.events,
                now,
                watched=self.watched_currencies(),
                starred=self.starred_keys(),
                fired_bursts=self._burst_fired,
            )
            if token:
                self.refresh(force=True)

    def notify(self, title, detail, *, event=None, accent='red'):
        if self.tray:
            try:
                self.tray.notify(detail, title)
            except Exception:
                pass
        self.toast(title, detail, event=event, accent=accent)
        if self.cfg.get('sound', True):
            system.play_alert_sound(self.root)

    def toast(self, title, detail, *, event=None, accent='red'):
        p = self.p
        t = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes('-topmost', True)
        rounded_ok = native_round(t, p['line_strong'])
        t.configure(bg=p['line_strong'])
        outer = tk.Frame(t, bg=p['card'])
        outer.pack(fill='both', expand=True, padx=0 if rounded_ok else 1, pady=0 if rounded_ok else 1)
        tk.Frame(outer, bg=p.get(accent, p['red']), width=px(3)).pack(side='left', fill='y')
        inside = tk.Frame(outer, bg=p['card'])
        inside.pack(side='left', fill='both', expand=True)
        head = tk.Frame(inside, bg=p['card'])
        head.pack(fill='x', padx=px(14), pady=(px(14), px(8)))
        self.brand(head, p['card'], 16, 9).pack(side='left')
        self.label(head, self.tr('now'), 8, p['faded']).pack(side='left', padx=(px(6), 0))
        self.label(inside, title, 11, p['text'], weight='semibold', anchor='w').pack(fill='x', padx=px(14))
        self.label(inside, detail[:200], 9, p['soft'], wraplength=px(326), justify='left', anchor='w').pack(
            fill='x', padx=px(14), pady=(px(3), px(16))
        )
        t.update_idletasks()
        a = self.workarea()
        self.toasts = [x for x in self.toasts if x.winfo_exists()]
        w, h = px(376), max(t.winfo_reqheight(), px(96))
        offset = sum(x.winfo_height() + px(10) for x in self.toasts)
        t.geometry(f'{w}x{h}+{a[2] - w - px(16)}+{a[3] - h - px(16) - offset}')
        self.toasts.append(t)
        t.after(8000, t.destroy)

        def dismiss(_e=None):
            t.destroy()
            if event is not None and not self._closing:
                self.event_detail(event)

        def bind_all(widget):
            widget.bind('<Button-1>', dismiss)
            for child in widget.winfo_children():
                bind_all(child)

        bind_all(t)

    def auto_refresh(self):
        """Polite polling: every refresh interval (at least 15 min), backing off
        after failures and honouring a source's Retry-After."""
        try:
            if not self.demo and not self.inflight and self.refresh_due():
                self.refresh(True)
        finally:
            if not self._closing:
                self._refresh_timer = self.root.after(60_000, self.auto_refresh)

    def refresh_due(self, now=None):
        now = now or self.now()
        if self.retry_until and now < self.retry_until:
            return False
        if self.next_attempt:
            return now >= self.next_attempt
        interval = max(15, int(self.cfg.get('refresh_minutes', 15))) * 60
        return not self.last_attempt or (now - self.last_attempt).total_seconds() >= interval

    def refresh(self, force=False, supersede=False):
        if self.demo or (self.inflight and not supersede):
            return
        now = self.now()
        if not supersede and self.retry_until and now < self.retry_until:
            self.warning = self.tr('The data source asked us to wait before the next refresh')
            self.render_status()
            return
        if not force and not supersede and self.last_attempt and (now - self.last_attempt).total_seconds() < 120:
            self.warning = self.tr('Refresh available again in 2 minutes')
            self.render_status()
            return
        self.last_attempt = now
        self.inflight = True
        self._fetch_id += 1
        gen = self._fetch_id
        self.warning = ''
        self.render_status()
        provider = self.cfg.get('provider', 'biquote')
        key = self.cfg.get('financecalendar_key', '') if provider == 'financecalendar' else ''

        def fetch():
            try:
                self.io_queue.put(('ok', gen, fetch_events(provider, key=key)))
            except ProviderError as exc:
                self.io_queue.put(('error', gen, (str(exc), getattr(exc, 'retry_after', None))))
            except Exception as exc:
                log.exception('calendar fetch crashed')
                self.io_queue.put(('error', gen, (str(exc), None)))

        threading.Thread(target=fetch, daemon=True, name='calendar-fetch').start()

    def _after_fetch(self, failed, retry_after=None):
        """Schedule the next automatic attempt (exponential backoff on failure)."""
        now = self.now()
        self.retry_until = now + timedelta(seconds=retry_after) if retry_after else None
        if not failed:
            self.failures, self.next_attempt = 0, None
            return
        self.failures += 1
        minutes = BACKOFF_MINUTES[min(self.failures, len(BACKOFF_MINUTES)) - 1]
        self.next_attempt = now + timedelta(minutes=minutes)

    def poll(self):
        while not self._closing:
            try:
                action = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception:
                log.exception('tray action failed')
        while not self._closing:
            try:
                status, gen, payload = self.io_queue.get_nowait()
            except queue.Empty:
                break
            if gen != self._fetch_id:
                continue  # superseded by a newer refresh (e.g. provider switch)
            self.inflight = False
            if status == 'ok':
                prev_events = self.events
                self.events, self.at, self.source = payload.events, payload.at, payload.source
                self.coverage, self.has_actuals, self.provider = payload.coverage, payload.has_actuals, payload.provider
                self.widget_refocus = True
                self.warning = payload.warning
                self.state = 'cached' if payload.is_cache else 'live'
                self._after_fetch(payload.failed, payload.retry_after)
                if not self.demo and self.cfg.get('notifications', True) and self.cfg.get('alert_actual', True):
                    published = state.detect_published_actuals(
                        prev_events,
                        payload.events,
                        watched=self.watched_currencies(),
                        starred=self.starred_keys(),
                        now=self.now(),
                    )
                    if published:
                        # One notification (and one sound) per refresh, like the pre-release alerts.
                        lines = []
                        for ev in published[:3]:
                            line = f'{ev.currency} {ev.title}: {ev.actual}'
                            if ev.forecast:
                                line += f' ({self.tr("Forecast")} {ev.forecast})'
                            lines.append(line)
                        if len(published) > 3:
                            lines.append(f'+{len(published) - 3}')
                        detail = '\n'.join(lines)
                        self.notify(self.tr('Result published'), detail, event=published[0], accent='green')
            else:
                message, retry_after = payload
                self.warning = message
                self.state = 'cached' if self.events else 'offline'
                self._after_fetch(True, retry_after)
            try:
                self.render()
            except Exception:
                log.exception('render after refresh failed')
        if not self._closing:
            try:
                delay = 80 if self.inflight else (400 if self.tray else 1000)
                self.root.after(delay, self.poll)
            except tk.TclError:
                pass

    def workarea(self):
        return system.workarea(self.root)

    def all_workareas(self):
        """Work areas of every monitor, so the widget reopens on the screen it was on."""
        return system.all_workareas(self.root)

    def show_full(self):
        self.last_view = 'full'
        self._drop_widget()
        self.restore_window(self.root)
        self.render()

    def restore_window(self, window):
        """Explicit user restore from tray, including a withdrawn Tk root."""
        if not window or not window.winfo_exists():
            return
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except tk.TclError:
            pass

    def restore_last_view(self):
        """System-tray double-click returns to the last active view."""
        if self.last_view == 'full':
            self.show_full()
        else:
            self.show_widget()

    def toggle_topmost_from_tray(self):
        value = not bool(self.cfg.get('topmost', True))
        self.cfg['topmost'] = value
        if self.widget and self.widget.winfo_exists():
            self.widget.attributes('-topmost', value)
        save_settings(self.cfg)

    def toggle_startup_from_tray(self):
        if not system.startup_supported():
            return
        enabled = not system.get_startup()
        try:
            system.set_startup(enabled)
        except (OSError, RuntimeError) as exc:
            messagebox.showwarning(self.tr('Start at login'), str(exc), parent=self.root)
            return
        self.cfg['startup'] = enabled
        save_settings(self.cfg)

    def show_tray_widget_period(self, period):
        self.set_widget_period(period)
        self.show_widget()

    def init_tray(self):
        """Windows tray default item handles double-click. UI calls use the Tk poll queue."""
        try:
            from PIL import Image
            import pystray

            image = Image.open(asset('econpulse.png')).convert('RGBA')

            def dispatch(action):
                self.ui_queue.put(action)

            def menu_action(action):
                return lambda _icon, _item: dispatch(action)

            def label(text):
                return lambda _item, s=text: self.menu_text(s)

            menu = pystray.Menu(
                pystray.MenuItem(
                    label('Open last view (double-click)'), menu_action(self.restore_last_view), default=True
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(label('Show widget'), menu_action(self.show_widget)),
                pystray.MenuItem(label('Open full calendar'), menu_action(self.show_full)),
                pystray.MenuItem(label('Widget: Today'), menu_action(lambda: self.show_tray_widget_period('day'))),
                pystray.MenuItem(label('Widget: Week'), menu_action(lambda: self.show_tray_widget_period('week'))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(label('Toggle Always on Top'), menu_action(self.toggle_topmost_from_tray)),
                pystray.MenuItem(
                    label('Toggle start at login'),
                    menu_action(self.toggle_startup_from_tray),
                    visible=system.startup_supported(),
                ),
                pystray.MenuItem(label('Refresh calendar'), menu_action(lambda: self.refresh(False))),
                pystray.MenuItem(
                    label('Get the new version'),
                    menu_action(self.open_update),
                    visible=lambda _item: bool(self.update_info),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(label('Exit EconPulse'), menu_action(self.quit)),
            )
            self.tray = pystray.Icon('EconPulse', image, 'EconPulse — Economic Calendar', menu)
            threading.Thread(target=self.tray.run, daemon=True, name='tray').start()
        except Exception:
            log.info('system tray unavailable', exc_info=True)
            self.tray = None

    # ----------------------------------------------------------- updates
    def check_for_updates(self):
        """Opt-in (off by default): at most once a day ask GitHub for the latest release."""
        if self.demo or not self.cfg.get('check_updates') or not updates.due(self.cfg.get('last_update_check')):
            return
        self.cfg['last_update_check'] = self.now().isoformat()
        save_settings(self.cfg)

        def work():
            latest = updates.latest_release()
            if latest:
                self.ui_queue.put(lambda: self._remember_update(latest, save=True))

        threading.Thread(target=work, daemon=True, name='update-check').start()

    def _remember_update(self, version, save=False):
        if save and version != self.cfg.get('latest_version'):
            self.cfg['latest_version'] = version
            save_settings(self.cfg)
        self.update_info = (version, updates.RELEASES_URL) if updates.is_newer(version, __version__) else None
        self.render_attribution()
        if self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def open_update(self):
        system.safe_open(updates.RELEASES_URL)

    def provider_info(self):
        """(attribution text, homepage) for the data shown right now."""
        if self.demo:
            return self.tr('Demo data'), REPO_URL
        provider = PROVIDERS.get(self.provider) or PROVIDERS[FALLBACK]
        return provider.attribution, provider.homepage

    def close_full(self):
        if self.tray:
            self.root.withdraw()
        else:
            self.quit()

    def quit(self):
        self._closing = True
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            # Cancel pending timers first: firing into destroyed widgets logs
            # "invalid command name" errors on every exit. Cancel at the Tcl
            # level: after_cancel() would also delete callbacks owned by other
            # windows (an alert toast), and destroying that window later fails
            # half-way, leaving the app running with no window.
            for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.tk.call('after', 'cancel', job)
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
