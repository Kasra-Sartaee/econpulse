"""The release list (virtualised canvas with sticky day headings) and the
"next high-impact release" hero."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import timezone
import tkinter as tk

from . import i18n
from .controls import (
    Mirror,
    TinyScrollbar,
    _tags,
    actual_color,
    dot,
    impact_mark,
    impact_width,
    parent_bg,
    rounded,
    wheel_units,
)
from .core import Event, weekly_sections
from .i18n import tr
from .theme import fitter, font, glyph, num, px


class NextUp(tk.Canvas):
    HEIGHT = 84

    def __init__(self, parent, palette, open_event, bg=None):
        self.p = palette
        self.open_event = open_event
        self.event = None
        self.tz = timezone.utc
        self.count_item = None
        self.count_text = ''
        self.count_colour = ''
        super().__init__(
            parent,
            height=px(self.HEIGHT),
            bg=bg or parent_bg(parent, palette['bg']),
            highlightthickness=0,
            borderwidth=0,
        )
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<ButtonRelease-1>', lambda _e: self.event and self.open_event(self.event))
        self._now = None

    def set(self, event, tz, now):
        if event is not None and event == self.event and tz == self.tz and self.count_item is not None:
            self.tick(now)  # same release (the per-minute render): only the countdown moves
            return
        self.event, self.tz, self._now = event, tz, now
        self.configure(cursor='hand2' if event else '')
        self.redraw()

    def _countdown(self, now):
        e = self.event
        left = (e.instant - now).total_seconds()
        text = e.countdown(now) if left >= 0 else tr('Now')
        colour = self.p['red'] if left < 15 * 60 else self.p['text']
        return text, colour

    def redraw(self):
        self.delete('all')
        p = self.p
        w = max(px(240), self.winfo_width())
        m = Mirror(w)
        left, right = px(18), w - px(18)
        dot(self, m.x(left + px(3)), px(19), px(6), p['red'])
        self.create_text(
            m.x(left + px(12)),
            px(19),
            text=i18n.bidi(tr('Next high impact')),
            anchor=m.a('w'),
            fill=p['faded'],
            font=font(9),
        )
        e = self.event
        if e is None:
            self.create_text(
                m.x(left),
                px(47),
                text=i18n.bidi(tr('No high-impact releases ahead')),
                anchor=m.a('w'),
                fill=p['soft'],
                font=font(12, 'semibold'),
            )
            self.count_item = None
            return
        from datetime import datetime
        from datetime import timezone as _tz

        now = self._now or datetime.now(_tz.utc)
        text, colour = self._countdown(now)
        big = num(20)
        self.count_item = self.create_text(m.x(right), px(47), text=text, anchor=m.a('e'), fill=colour, font=big)
        self.count_text, self.count_colour = text, colour
        reserve = big.measure('0d 00:00:00' if 'd' in text else '00:00:00') + px(16)
        title_font = font(12, 'semibold')
        self.create_text(
            m.x(left),
            px(46),
            text=fitter.fit(title_font, e.title, right - left - reserve),
            anchor=m.a('w'),
            fill=p['text'],
            font=title_font,
        )
        # Meta line drawn as separate runs separated by pixel gaps: Tk's bidi
        # handling misplaces Latin figures, punctuation and edge spaces that
        # share one text item with Persian words.
        when = e.local_dt(self.tz)
        gap, wide = px(5), px(10)
        sep = [wide, (font(9), '·', p['faded']), wide]
        runs = [
            (font(9), e.currency, p['soft']),
            *sep,
            (font(9), i18n.date_text(when.date(), 'medium'), p['soft']),
            gap,
            (num(9), f'{when:%H:%M}', p['soft']),
        ]
        if e.forecast:
            runs += [*sep, (font(9), tr('Forecast'), p['faded']), gap, (num(9), e.forecast, p['soft'])]
        x = left
        for run in runs:
            if isinstance(run, int):
                x += run
                continue
            f, text, colour = run
            width = fitter.measure(f, text)
            if x + width > right:
                break
            self.create_text(m.x(x), px(68), text=i18n.bidi(text), anchor=m.a('w'), fill=colour, font=f)
            x += width

    def tick(self, now):
        self._now = now
        if self.event is None or self.count_item is None:
            return
        text, colour = self._countdown(now)
        if (text, colour) != (self.count_text, self.count_colour):
            self.itemconfigure(self.count_item, text=text, fill=colour)
            self.count_text, self.count_colour = text, colour


@dataclass(slots=True)
class Row:
    kind: str  # 'section' | 'event' | 'now'
    y: int
    height: int
    value: object  # date, Event or None
    count: int = 0  # events in a section
    holidays: int = 0


def day_label(day, today):
    """('Today', 'Thu 12 Nov') / ('امروز', 'پنجشنبه ۲۱ آبان') heading parts."""
    return i18n.day_label(day, today)


class EventCanvas(tk.Frame):
    """Scrollable, virtualised list of releases (table rows or widget rows).

    Layout (row positions) is computed for every event, which is cheap
    arithmetic, but canvas items are only created for rows inside or near the
    viewport.  A three-week Forex Factory range is ~400 events; drawing all
    of them produced ~18 000 canvas items per redraw and made typing in the
    search box lag by over a second per keystroke.

    Day headings are sticky: the current day's heading stays pinned to the
    top of the list and is pushed away by the next one.
    """

    TABLE_ROW = 46
    TABLE_SECTION = 44
    WEEK_SECTION = 44
    NOW_ROW = 22
    CARD_GAP = 0
    WIDGET_ROW = 64
    WIDGET_LINE = 19

    def __init__(self, parent, palette, mode, open_event, clock, period='day'):
        self.surface = palette['card'] if mode == 'table' else palette['bg']
        super().__init__(parent, bg=self.surface)
        self.p = palette
        self.mode = mode
        self.open_event = open_event
        self.clock = clock
        self.period = period
        self.events: list[Event] = []
        self.tz = timezone.utc
        self.rows: list[Row] = []
        self._tops: list[int] = []
        self._sections: list[int] = []
        self.content_height = 1
        self.drawn: dict[int, str] = {}  # row index -> canvas tag
        self.countdowns: dict[str, tuple] = {}  # uid -> (item, event, text, colour)
        self.hover_idx = None
        self.pending_focus = False
        self._layout_job = None
        self._size = (0, 0)
        self._sticky_state = None
        self._sticky_y = None
        self.sticky = None
        self._layout_key = None  # (today, now-marker uid) the current drawing was laid out for
        self.rtl = i18n.rtl()
        self._m = Mirror(1, self.rtl)
        list_col, bar_col = (1, 0) if self.rtl else (0, 1)

        self.grid_columnconfigure(list_col, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.header = None
        if mode == 'table':
            self.header = tk.Canvas(self, height=px(36), bg=self.surface, highlightthickness=0, borderwidth=0)
            self.header.grid(row=0, column=0, columnspan=2, sticky='ew')
            self.header.bind('<Configure>', lambda _e: self.draw_header())
        self.cv = tk.Canvas(self, bg=self.surface, highlightthickness=0, borderwidth=0, yscrollincrement=px(14))
        self.cv.grid(row=2, column=list_col, sticky='nsew')
        self.scroll = TinyScrollbar(self, self.cv, palette)
        self.scroll.configure(bg=self.surface)
        self.scroll.grid(row=2, column=bar_col, sticky='ns')
        self.cv.configure(yscrollcommand=self.scrolled)
        self.cv.bind('<Configure>', self.on_resize)
        self.cv.bind('<ButtonPress-1>', lambda _e: self.cv.focus_set())  # so arrow/page keys scroll it
        self.cv.bind('<ButtonRelease-1>', self.clicked)
        self.cv.bind('<Motion>', self.on_motion)
        self.cv.bind('<Leave>', lambda _e: self.set_hover(None))
        self.cv.bind('<MouseWheel>', self.wheel)
        self.cv.bind('<Button-4>', lambda e: self.unixwheel(-1))
        self.cv.bind('<Button-5>', lambda e: self.unixwheel(1))

    # ------------------------------------------------------------------ api
    def set_period(self, period):
        if period == self.period:
            return
        self.period = period
        self.draw(keep_scroll=False)

    def update_data(self, events, tz, focus=False, keep_scroll=True):
        events = list(events)
        if (
            self._layout_key is not None
            and tz == self.tz
            and events == self.events
            and self._layout_key == self._layout_state()
        ):
            # Unchanged feed (the app re-renders every minute): keep the canvas
            # items, hover highlight and scroll position; only the NOW label moves.
            self.cv.itemconfigure('nowlabel', text=self.clock().astimezone(tz).strftime('%H:%M'))
            if focus and events:
                self.focus_upcoming()
            return
        was_empty = not self.events
        self.events = events
        self.tz = tz
        if self.mode == 'widget':
            self.pending_focus = bool(focus or (was_empty and bool(self.events)))
        else:
            self.pending_focus = bool(focus and self.events)
        self.draw(keep_scroll=keep_scroll)

    # ------------------------------------------------------------ scrolling
    def scrolled(self, start, end):
        self.scroll.set(start, end)
        self._sync()
        self.refresh_sticky()

    def wheel(self, e):
        self.cv.yview_scroll(wheel_units(self.cv, e), 'units')
        return 'break'

    def unixwheel(self, step):
        self.cv.yview_scroll(step * 3, 'units')
        return 'break'

    def key_scroll(self, key):
        """Keyboard scrolling: arrows, Page Up/Down, Home/End (Tk keysyms)."""
        if key in ('Up', 'Down'):
            self.cv.yview_scroll(-3 if key == 'Up' else 3, 'units')
        elif key in ('Prior', 'Next'):
            self.cv.yview_scroll(-1 if key == 'Prior' else 1, 'pages')
        elif key in ('Home', 'End'):
            self.cv.yview_moveto(0 if key == 'Home' else 1)

    def on_resize(self, e):
        size = (e.width, e.height)
        if abs(size[0] - self._size[0]) <= 2 and abs(size[1] - self._size[1]) <= 2:
            return
        self._size = size
        # Coalesce the burst of <Configure> events produced by a drag-resize.
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(16, self._resized)

    def _resized(self):
        self._layout_job = None
        self.draw()
        if self.header:
            self.draw_header()
        if self.events and self.pending_focus:
            self.after_idle(self.focus_upcoming)

    # ---------------------------------------------------------- interaction
    def _row_at(self, canvas_y):
        if self._sticky_y is not None and canvas_y < self._sticky_y + px(self.section_height()):
            return None  # the pinned day heading covers this area
        i = bisect_right(self._tops, canvas_y) - 1
        if 0 <= i < len(self.rows):
            row = self.rows[i]
            if row.kind == 'event' and row.y <= canvas_y < row.y + row.height:
                return i
        return None

    def clicked(self, e):
        i = self._row_at(self.cv.canvasy(e.y))
        if i is not None:
            self.open_event(self.rows[i].value)

    def on_motion(self, e):
        self.set_hover(self._row_at(self.cv.canvasy(e.y)))

    def set_hover(self, idx):
        if idx == self.hover_idx:
            return
        self.cv.delete('hover')
        self.hover_idx = idx
        if idx is not None and idx in self.drawn:
            row = self.rows[idx]
            x1, x2 = Mirror(self.view_width(), self.rtl).span(px(6), self.view_width() - px(4))
            rounded(
                self.cv,
                x1,
                row.y + px(2),
                x2,
                row.y + row.height - px(2),
                px(8),
                self.p['row_hover'] if self.mode == 'table' else self.p['hover'],
                tags=('hover',),
            )
            self.cv.tag_lower('hover')
        self.cv.configure(cursor='hand2' if idx is not None else '')

    def focus_upcoming(self):
        """Align the next event without hiding earlier events or breaking date headers.

        In the table this scrolls today's heading (or the next day with
        releases) to the top, keeping earlier days reachable above it.
        """
        if not self.events:
            return
        now = self.clock()
        today = now.astimezone(self.tz).date()
        if self.mode == 'table':
            sections = [self.rows[i] for i in self._sections]
            target = next((r for r in sections if r.value >= today), sections[-1] if sections else None)
            if target is not None:
                self.cv.yview_moveto(target.y / max(1, self.content_height))
                self.refresh_sticky()
            return
        upcoming = [e for e in self.events if not e.is_untimed and not e.is_holiday and e.instant >= now]
        holidays = [e for e in self.events if e.is_holiday and e.display_day(self.tz) == today]
        target = upcoming[0] if upcoming else holidays[0] if holidays else self.events[-1]
        for idx, row in enumerate(self.rows):
            if row.kind == 'event' and row.value is target:
                # Keep a day separator / "now" marker immediately above in view.
                while idx > 0 and self.rows[idx - 1].kind in ('section', 'now'):
                    idx -= 1
                y = self.rows[idx].y
                if self.has_sections() and self.rows[idx].kind != 'section':
                    y -= px(self.section_height())  # stay clear of the pinned day heading
                self.cv.yview_moveto(max(0, y) / max(1, self.content_height))
                self.refresh_sticky()
                break

    # --------------------------------------------------------------- layout
    def view_width(self):
        return max(px(280), self.cv.winfo_width())

    def has_sections(self):
        return self.mode == 'table' or self.period == 'week'

    def section_height(self):
        return self.TABLE_SECTION if self.mode == 'table' else self.WEEK_SECTION

    def _title_x(self):
        return px(78)

    def _title_width(self, width):
        return max(px(140), width - self._title_x() - px(14) - px(78))

    def card_height(self, e, width):
        lines = min(2, len(fitter.wrap(font(10, 'semibold'), e.title, self._title_width(width))))
        return px(self.WIDGET_ROW) + (lines - 1) * px(self.WIDGET_LINE)

    def _now_target(self, now, today):
        """First upcoming timed release today, if earlier ones already happened."""
        seen_past = False
        for e in self.events:
            if e.is_untimed:
                continue
            if e.instant <= now:
                seen_past = seen_past or e.display_day(self.tz) == today
                continue
            return e if seen_past and e.display_day(self.tz) == today else None
        return None

    def _layout_state(self):
        """What, besides the events themselves, the row layout depends on."""
        if not self.events:
            return ('empty',)
        now = self.clock()
        today = now.astimezone(self.tz).date()
        marker = self._now_target(now, today)
        return (today, marker.uid if marker else None)

    def layout(self):
        width = self.view_width()
        now = self.clock()
        today = now.astimezone(self.tz).date()
        marker = self._now_target(now, today)
        rows: list[Row] = []
        y = 0 if self.has_sections() else px(6)
        table = self.mode == 'table'
        for day, events in weekly_sections(self.events, self.tz):
            if self.has_sections():
                h = px(self.section_height())
                rows.append(Row('section', y, h, day, len(events), sum(e.is_holiday for e in events)))
                y += h
            for e in events:
                if e is marker:
                    rows.append(Row('now', y, px(self.NOW_ROW), now))
                    y += px(self.NOW_ROW)
                h = px(self.TABLE_ROW) if table else self.card_height(e, width)
                rows.append(Row('event', y, h, e))
                y += h
            if self.has_sections():
                y += px(8)
        if table:
            bottom = y + px(12)
        else:
            bottom = y + max(px(24), self.cv.winfo_height() - px(150))
        self.rows = rows
        self._layout_key = (today, marker.uid if marker else None)
        self._tops = [r.y for r in rows]
        self._sections = [i for i, r in enumerate(rows) if r.kind == 'section']
        self.content_height = max(bottom, self.cv.winfo_height())
        fitter.trim()

    def draw(self, keep_scroll=True):
        cv = self.cv
        top_px = cv.canvasy(0) if keep_scroll else 0
        cv.delete('all')
        self.drawn.clear()
        self.countdowns.clear()
        self.hover_idx = None
        self._sticky_state = None
        self._sticky_y = None
        width = self.view_width()
        if not self.events:
            self.rows, self._tops, self._sections = [], [], []
            self._layout_key = ('empty',)
            self.content_height = max(px(220), cv.winfo_height())
            cv.configure(scrollregion=(0, 0, width, self.content_height))
            self._empty_state(width)
            return
        self.layout()
        cv.configure(scrollregion=(0, 0, width, self.content_height))
        cv.yview_moveto(top_px / self.content_height if self.content_height else 0)
        self._sync()
        self.refresh_sticky(force=True)
        if self.pending_focus and cv.winfo_width() > 60:
            self.pending_focus = False
            self.focus_upcoming()

    def _empty_state(self, width):
        p = self.p
        cy = max(px(110), self.cv.winfo_height() // 2 - px(30))
        text, f = glyph('search', 20)
        self.cv.create_text(width / 2, cy - px(34), text=text, fill=p['faded'], font=f)
        self.cv.create_text(
            width / 2, cy + px(4), text=i18n.bidi(tr('Nothing to show')), fill=p['text'], font=font(11, 'semibold')
        )
        self.cv.create_text(
            width / 2,
            cy + px(26),
            text=i18n.bidi(tr('No releases match these filters.')),
            fill=p['faded'],
            font=font(9),
        )

    def _sync(self):
        """Create items for rows near the viewport and drop those far away."""
        if not self.rows:
            return
        cv = self.cv
        top = cv.canvasy(0)
        h = max(1, cv.winfo_height())
        lo, hi = top - h * 0.75, top + h * 1.75
        start = max(0, bisect_right(self._tops, lo) - 1)
        wanted = set()
        i = start
        while i < len(self.rows) and self.rows[i].y < hi:
            wanted.add(i)
            i += 1
        for idx in [k for k in self.drawn if k not in wanted]:
            cv.delete(self.drawn.pop(idx))
            row = self.rows[idx] if idx < len(self.rows) else None
            if row and row.kind == 'event':
                self.countdowns.pop(row.value.uid, None)
            if idx == self.hover_idx:
                self.set_hover(None)
        missing = wanted - self.drawn.keys()
        if missing:
            now = self.clock()
            width = self.view_width()
            for idx in sorted(missing):
                self._draw_row(idx, width, now)
            if cv.find_withtag('sticky'):
                cv.tag_raise('sticky')

    def _draw_row(self, idx, width, now):
        row = self.rows[idx]
        tag = f'r{idx}'
        self._m = Mirror(width, self.rtl)
        if row.kind == 'section':
            self.draw_section(row, width, now, (tag,))
        elif row.kind == 'now':
            self.draw_now_marker(row, width, now, tag)
        elif self.mode == 'table':
            self.draw_table_row(row.value, row.y, width, now, tag, idx)
        else:
            self.draw_widget_row(row.value, row, width, now, tag, idx)
        self.drawn[idx] = tag

    def _separator_after(self, idx):
        nxt = idx + 1
        return nxt < len(self.rows) and self.rows[nxt].kind == 'event'

    # -------------------------------------------------------------- drawing
    def t(self, x, y, text, fill, size=10, weight='normal', anchor='w', width=None, tags=(), numeric=False):
        """Text at logical (left-to-right) x; mirrored in right-to-left mode."""
        ft = num(size, weight) if numeric else font(size, weight)
        text = str(text)
        if width and text:
            text = fitter.fit(ft, text, int(width))
        return self.cv.create_text(
            self._m.x(x), y, text=i18n.bidi(text), font=ft, fill=fill, anchor=self._m.a(anchor), tags=_tags(tags)
        )

    def hline(self, x1, x2, y, fill, tags):
        a, b = self._m.span(x1, x2)
        self.cv.create_line(a, y, b, y, fill=fill, tags=_tags(tags))

    def mark(self, x, cy, impact, tags):
        impact_mark(self.cv, self._m.box(x, impact_width(impact)), cy, impact, self.p, tags=tags)

    def when_label(self, e):
        return tr('All day') if e.is_holiday else tr(e.time_label)

    def table_columns(self, width):
        """Single source of truth for header and row column positions.

        Numeric columns are right-aligned on these x positions.
        """
        right = width - px(20)
        return dict(
            time=px(20),
            impact=px(80),
            ccy=px(104),
            event=px(152),
            actual=right - px(300),
            forecast=right - px(208),
            previous=right - px(116),
            status=right,
        )

    def draw_header(self):
        if not self.header:
            return
        c, p = self.header, self.p
        w = max(c.winfo_width(), px(500))
        c.delete('all')
        cols = self.table_columns(self.view_width())
        m = Mirror(self.view_width(), self.rtl)
        offset = int(self.scroll.cget('width')) if self.rtl else 0
        y = px(19)
        f = font(9)
        for text, key, anchor in (
            ('Time', 'time', 'w'),
            ('Cur.', 'ccy', 'w'),
            ('Event', 'event', 'w'),
            ('Actual', 'actual', 'e'),
            ('Forecast', 'forecast', 'e'),
            ('Previous', 'previous', 'e'),
            ('Countdown', 'status', 'e'),
        ):
            c.create_text(
                offset + m.x(cols[key]), y, text=i18n.bidi(tr(text)), fill=p['faded'], font=f, anchor=m.a(anchor)
            )
        c.create_line(px(12), px(35), w - px(2), px(35), fill=p['line'])

    def _section_items(self, canvas, y, width, day, count, holidays, today, tags):
        """Draw one day heading at canvas y (used for rows and the sticky copy)."""
        p = self.p
        h = px(self.section_height())
        left = px(20) if self.mode == 'table' else px(18)
        right = width - px(16)
        cy = y + h - px(18)
        name, date_text = day_label(day, today)
        is_today = day == today
        m = Mirror(width, self.rtl)
        f = font(10, 'semibold')
        canvas.create_text(
            m.x(left),
            cy,
            text=i18n.bidi(name),
            anchor=m.a('w'),
            fill=p['text'] if is_today else p['soft'],
            font=f,
            tags=tags,
        )
        x = left + fitter.measure(f, name) + px(8)
        canvas.create_text(
            m.x(x), cy, text=i18n.bidi(date_text), anchor=m.a('w'), fill=p['faded'], font=font(9), tags=tags
        )
        if is_today:
            dot(canvas, m.x(x + fitter.measure(font(9), date_text) + px(9)), cy, px(5), p['now'], tags)
        caption = i18n.count(count, 'release')
        if holidays:
            caption += '  ·  ' + i18n.count(holidays, 'holiday')
        canvas.create_text(
            m.x(right), cy, text=i18n.bidi(caption), anchor=m.a('e'), fill=p['faded'], font=font(8), tags=tags
        )
        a, b = m.span(left, right)
        canvas.create_line(a, y + h - 1, b, y + h - 1, fill=p['line'], tags=tags)

    def draw_section(self, row, width, now, tags):
        today = now.astimezone(self.tz).date()
        self._section_items(self.cv, row.y, width, row.value, row.count, row.holidays, today, tags)

    def draw_now_marker(self, row, width, now, tag):
        p, c = self.p, self.cv
        y = row.y + row.height // 2
        left = px(20) if self.mode == 'table' else px(18)
        label = now.astimezone(self.tz).strftime('%H:%M')
        ft = num(8, 'bold')
        m = Mirror(width, self.rtl)
        c.create_text(m.x(left), y, text=label, anchor=m.a('w'), fill=p['now'], font=ft, tags=(tag, 'nowlabel'))
        x = left + fitter.measure(ft, label) + px(8)
        dot(c, m.x(x + px(3)), y, px(7), p['now'], (tag,))
        a, b = m.span(x + px(6), width - px(16))
        c.create_rectangle(a, y, b, y + max(1, px(1)), fill=p['now'], outline='', tags=(tag,))

    def status(self, e, now):
        """(text, colour) for the countdown/status cell."""
        p = self.p
        if e.is_untimed:
            return (tr('Holiday') if e.is_holiday else tr(e.time_label)), p['faded']
        left = (e.instant - now).total_seconds()
        if left <= 0:
            return tr('Released'), p['faded']
        if e.impact == 'High' and left < 3600:
            return e.countdown(now), p['red']
        return e.countdown(now), p['soft'] if e.impact != 'High' else p['text']

    def _values(self, e, now):
        p = self.p
        released = not e.is_untimed and e.instant <= now
        if e.actual:
            actual = (e.actual, actual_color(p, e))
        elif released and (e.forecast or e.previous):
            actual = (tr('Not posted'), p['faded'])
        else:
            actual = ('—', p['faded'])
        return (
            actual,
            (e.forecast or '—', p['soft'] if e.forecast else p['faded']),
            (e.previous or '—', p['soft'] if e.previous else p['faded']),
        )

    def draw_table_row(self, e, y, w, now, tag, idx=None):
        p = self.p
        cols = self.table_columns(w)
        cy = y + px(self.TABLE_ROW) // 2
        released = not e.is_untimed and e.instant <= now
        if e.is_untimed:
            self.t(
                cols['time'],
                cy,
                self.when_label(e),
                p['faded'],
                9,
                width=cols['impact'] - cols['time'] - px(6),
                tags=tag,
            )
        else:
            self.t(
                cols['time'],
                cy,
                e.local_dt(self.tz).strftime('%H:%M'),
                p['faded'] if released else p['text'],
                10,
                numeric=True,
                tags=tag,
            )
        self.mark(cols['impact'], cy, e.impact, tag)
        self.t(cols['ccy'], cy, e.currency, p['text'], 9, 'semibold', tags=tag)
        title_w = cols['actual'] - px(84) - cols['event']
        self.t(cols['event'], cy, e.title, p['text'], 10, width=title_w, tags=tag)
        if e.is_holiday:
            self.t(
                cols['actual'] - px(70),
                cy,
                tr('Bank holiday  ·  markets may close early'),
                p['faded'],
                9,
                width=cols['status'] - cols['actual'],
                tags=tag,
            )
        else:
            (actual, actual_fg), (forecast, f_fg), (previous, p_fg) = self._values(e, now)
            self.t(
                cols['actual'],
                cy,
                actual,
                actual_fg,
                10,
                'bold' if e.actual else 'normal',
                'e',
                width=px(86),
                tags=tag,
                numeric=bool(e.actual),
            )
            self.t(cols['forecast'], cy, forecast, f_fg, 10, anchor='e', width=px(84), tags=tag, numeric=True)
            self.t(cols['previous'], cy, previous, p_fg, 10, anchor='e', width=px(84), tags=tag, numeric=True)
            text, colour = self.status(e, now)
            item = self.t(cols['status'], cy, text, colour, 10, anchor='e', tags=tag, numeric=True)
            if not e.is_untimed:
                self.countdowns[e.uid] = (item, e, text, colour)
        if idx is not None and self._separator_after(idx):
            self.hline(px(20), w - px(16), y + px(self.TABLE_ROW) - 1, p['line'], tag)

    def draw_widget_row(self, e, row, w, now, tag, idx=None):
        p = self.p
        y, h = row.y, row.height
        left, tx, right = px(18), self._title_x(), w - px(14)
        released = not e.is_untimed and e.instant <= now
        ty = y + px(22)
        vy = y + h - px(21)
        # Time + currency/impact column
        if e.is_untimed:
            self.t(left, ty, self.when_label(e), p['faded'], 9, width=tx - left - px(6), tags=tag)
        else:
            self.t(
                left,
                ty,
                e.local_dt(self.tz).strftime('%H:%M'),
                p['faded'] if released else p['text'],
                10,
                numeric=True,
                tags=tag,
            )
        cf = font(8, 'semibold')
        self.t(left, vy, e.currency, p['soft'], 8, 'semibold', tags=tag)
        self.mark(left + fitter.measure(cf, e.currency) + px(6), vy, e.impact, tag)
        # Title (max two lines)
        title_font = font(10, 'semibold')
        title_w = self._title_width(w)
        lines = fitter.wrap(title_font, e.title, title_w)
        if len(lines) > 2:
            lines = [lines[0], fitter.fit(title_font, ' '.join(lines[1:]), title_w)]
        for i, line in enumerate(lines):
            self.t(tx, ty + i * px(self.WIDGET_LINE), line, p['text'], 10, 'semibold', width=title_w, tags=tag)
        # Status
        if not e.is_holiday:
            text, colour = self.status(e, now)
            item = self.t(right, ty, text, colour, 9, anchor='e', tags=tag, numeric=True)
            if not e.is_untimed:
                self.countdowns[e.uid] = (item, e, text, colour)
        # Values
        if e.is_holiday:
            self.t(tx, vy, tr('Bank holiday  ·  markets may close early'), p['faded'], 8, width=right - tx, tags=tag)
        elif e.actual or e.forecast or e.previous:  # speeches etc. carry no figures: no row of dashes
            col = (right - tx) / 3
            lf = font(8)
            raw = (e.actual, e.forecast, e.previous)
            for i, (label, (value, fg)) in enumerate(
                zip(('Actual', 'Forecast', 'Previous'), self._values(e, now), strict=True)
            ):
                x = tx + i * col
                label = tr(label)
                self.t(x, vy, label, p['faded'], 8, tags=tag)
                lw = fitter.measure(lf, label) + px(5)
                strong = i == 0 and bool(e.actual)
                self.t(
                    x + lw,
                    vy,
                    value,
                    fg,
                    9,
                    'bold' if strong else 'normal',
                    width=col - lw - px(8),
                    tags=tag,
                    numeric=bool(raw[i]),
                )
        if idx is not None and self._separator_after(idx):
            self.hline(tx, right, y + h - 1, p['line'], tag)

    def refresh_sticky(self, force=False):
        """Pin the current day heading to the top; the next heading pushes it away."""
        cv = self.cv
        if not self.has_sections() or not self._sections:
            if self._sticky_y is not None:
                cv.delete('sticky')
                self._sticky_y = None
            return
        top = cv.canvasy(0)
        h = px(self.section_height())
        active = None
        nxt = None
        for i in self._sections:
            if self.rows[i].y <= top:
                active = i
            else:
                nxt = i
                break
        if active is None:
            if self._sticky_y is not None:
                cv.delete('sticky')
                self._sticky_y = None
                self._sticky_state = None
            return
        y = top
        if nxt is not None:
            y = min(top, self.rows[nxt].y - h - px(8))
        width = self.view_width()
        today = self.clock().astimezone(self.tz).date()
        state = (active, width, today)
        if not force and state == self._sticky_state and self._sticky_y is not None:
            cv.move('sticky', 0, y - self._sticky_y)
            self._sticky_y = y
            return
        self._sticky_state = state
        cv.delete('sticky')
        row = self.rows[active]
        cv.create_rectangle(0, y, width, y + h, fill=self.surface, outline='', tags=('sticky',))
        self._section_items(cv, y, width, row.value, row.count, row.holidays, today, ('sticky',))
        self._sticky_y = y
        cv.tag_raise('sticky')

    def tick(self):
        """Per-second countdown update; only touches visible, changed items."""
        if not self.countdowns:
            return
        now = self.clock()
        crossed = False
        released = tr('Released')
        for uid, (item, e, last, last_colour) in list(self.countdowns.items()):
            text, colour = self.status(e, now)
            if text == last and colour == last_colour:
                continue
            if last != released and text == released:
                crossed = True
            try:
                self.cv.itemconfigure(item, text=text, fill=colour)
            except tk.TclError:
                continue
            self.countdowns[uid] = (item, e, text, colour)
        if crossed:
            self.draw()  # colours/labels/now-marker change at the release instant
