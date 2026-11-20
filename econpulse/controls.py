"""Canvas-drawn controls: buttons, toggles, selects, scrollbars, panels, tooltips.

Everything is theme-driven (a palette dict from :mod:`econpulse.theme`) and
sized in logical pixels via :func:`econpulse.theme.px`, so it stays crisp on
HiDPI displays. Curves are drawn from cached, supersampled images because
Tk's canvas does not anti-alias polygons or ovals.
"""

from __future__ import annotations

import tkinter as tk

from . import i18n
from .system import native_round
from .theme import IMPACT_LEVEL, SEV_COLOR, corner_images, dot_image, fitter, font, glyph, has_aa, px


def _tags(tags):
    if not tags:
        return ()
    return (tags,) if isinstance(tags, str) else tuple(tags)


class Mirror:
    """Horizontal mirroring for canvas drawing in right-to-left mode.

    Drawing code is written once in left-to-right coordinates; ``x``/``a``
    map positions and anchors for the current direction.
    """

    def __init__(self, width, rtl=None):
        self.w = width
        self.rtl = i18n.rtl() if rtl is None else rtl

    def x(self, x):
        return self.w - x if self.rtl else x

    def a(self, anchor):
        return i18n.mirror_anchor(anchor) if self.rtl else anchor

    def box(self, x, width):
        """Left edge of a box of ``width`` that starts at logical ``x``."""
        return self.w - x - width if self.rtl else x

    def span(self, x1, x2):
        a, b = self.x(x1), self.x(x2)
        return (a, b) if a <= b else (b, a)


def impact_width(impact):
    return px(9) if impact == 'Holiday' else 3 * max(2, px(3)) + 2 * max(1, px(2))


def rounded(canvas, x1, y1, x2, y2, r, fill, outline='', width=1, tags=()):
    """Anti-aliased rounded rectangle (nine-slice: image corners + rectangles)."""
    x1, y1, x2, y2 = round(x1), round(y1), round(x2), round(y2)
    r = int(max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2)))
    tags = _tags(tags)
    if not has_aa() or r < 2:
        r = max(r, 0)
        coords = [
            x1 + r,
            y1,
            x2 - r,
            y1,
            x2,
            y1,
            x2,
            y1 + r,
            x2,
            y2 - r,
            x2,
            y2,
            x2 - r,
            y2,
            x1 + r,
            y2,
            x1,
            y2,
            x1,
            y2 - r,
            x1,
            y1 + r,
            x1,
            y1,
        ]
        canvas.create_polygon(
            coords,
            smooth=bool(r),
            splinesteps=12,
            fill=fill or '',
            outline=outline or fill or '',
            width=width,
            tags=tags,
        )
        return
    c = canvas
    if fill:
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline='', tags=tags)
        if y2 - y1 > 2 * r:
            c.create_rectangle(x1, y1 + r, x1 + r, y2 - r, fill=fill, outline='', tags=tags)
            c.create_rectangle(x2 - r, y1 + r, x2, y2 - r, fill=fill, outline='', tags=tags)
    if outline:
        w = max(1, int(width))
        for box in (
            (x1 + r, y1, x2 - r, y1 + w),
            (x1 + r, y2 - w, x2 - r, y2),
            (x1, y1 + r, x1 + w, y2 - r),
            (x2 - w, y1 + r, x2, y2 - r),
        ):
            if box[2] > box[0] and box[3] > box[1]:
                c.create_rectangle(*box, fill=outline, outline='', tags=tags)
    nw, ne, sw, se = corner_images(r, fill, outline, max(1, int(width)))
    c.create_image(x1, y1, image=nw, anchor='nw', tags=tags)
    c.create_image(x2 - r, y1, image=ne, anchor='nw', tags=tags)
    c.create_image(x1, y2 - r, image=sw, anchor='nw', tags=tags)
    c.create_image(x2 - r, y2 - r, image=se, anchor='nw', tags=tags)


def dot(canvas, cx, cy, diameter, fill, tags=()):
    d = max(2, round(diameter))
    if has_aa():
        canvas.create_image(round(cx), round(cy), image=dot_image(d, fill), anchor='center', tags=_tags(tags))
    else:
        canvas.create_oval(cx - d / 2, cy - d / 2, cx + d / 2, cy + d / 2, fill=fill, outline='', tags=_tags(tags))


def impact_mark(canvas, x, cy, impact, p, tags=()):
    """Signal-strength bars: shape (not only colour) encodes High/Medium/Low."""
    if impact == 'Holiday':
        dot(canvas, x + px(4), cy, px(7), p['purple'], tags)
        return px(9)
    level = IMPACT_LEVEL.get(impact, 1)
    colour = p[SEV_COLOR.get(impact, 'faded')]
    bar, gap = max(2, px(3)), max(1, px(2))
    base = round(cy + px(5))
    for i, height in enumerate((px(5), px(8), px(11))):
        x0 = round(x + i * (bar + gap))
        canvas.create_rectangle(
            x0, base - height, x0 + bar, base, fill=colour if i < level else p['track'], outline='', tags=_tags(tags)
        )
    return 3 * bar + 2 * gap


def actual_color(p, e):
    """Green/red when the provider marks Actual better/worse than forecast."""
    if not e.actual:
        return p['faded']
    return {'better': p['green'], 'worse': p['red']}.get(e.actual_tone, p['text'])


class Label(tk.Label):
    """tk.Label whose text always gets correct right-to-left ordering."""

    def __init__(self, master=None, cnf=None, **kw):
        if 'text' in kw:
            kw['text'] = i18n.bidi(kw['text'])
        super().__init__(master, cnf or {}, **kw)

    def configure(self, cnf=None, **kw):
        if 'text' in kw:
            kw['text'] = i18n.bidi(kw['text'])
        return super().configure(cnf, **kw)

    config = configure


def parent_bg(parent, fallback):
    try:
        return parent.cget('bg')
    except tk.TclError:
        return fallback


def wheel_units(widget, event, per_notch=3):
    """Translate a wheel event into scroll units, accumulating the small
    deltas sent by precision touchpads instead of treating each as a notch."""
    step = 120 / per_notch  # Windows reports 120 per physical notch
    acc = getattr(widget, '_wheel_acc', 0) + event.delta
    units = int(acc / step)
    widget._wheel_acc = acc - units * step
    return -units


class Tooltip:
    """Small delayed hint for icon-only buttons."""

    def __init__(self, widget, text, palette):
        self.widget, self.text, self.p = widget, text, palette
        self.tip = None
        self.job = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _e=None):
        self._cancel()
        self.job = self.widget.after(450, self._show)

    def _cancel(self):
        if self.job:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _show(self):
        self.job = None
        if self.tip or not self.widget.winfo_exists():
            return
        p = self.p
        t = tk.Toplevel(self.widget)
        t.overrideredirect(True)
        t.attributes('-topmost', True)
        rounded_ok = native_round(t, p['line_strong'], small=True)
        t.configure(bg=p['line_strong'])
        lab = tk.Label(t, text=i18n.bidi(self.text), bg=p['raised'], fg=p['text'], font=font(9), padx=px(8), pady=px(4))
        lab.pack(padx=0 if rounded_ok else 1, pady=0 if rounded_ok else 1)
        t.update_idletasks()
        x = self.widget.winfo_rootx() + (self.widget.winfo_width() - t.winfo_reqwidth()) // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
        if y + t.winfo_reqheight() > self.widget.winfo_screenheight():
            y = self.widget.winfo_rooty() - t.winfo_reqheight() - px(6)
        t.geometry(f'+{max(0, x)}+{y}')
        self.tip = t

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class FlatButton(tk.Canvas):
    """Rounded button. width=None sizes to the content so labels never clip.

    kinds: 'primary' (solid, high contrast), 'normal' (secondary, hairline),
    'subtle' (ghost), 'selected' / 'chip' (filter chips on / off).
    """

    def __init__(
        self,
        parent,
        text,
        command,
        palette,
        kind='normal',
        width=None,
        height=34,
        font_size=10,
        dot=None,
        bg=None,
        icon=None,
        impact=None,
        tooltip=None,
    ):
        self.p = palette
        self.caption = text
        self.cmd = command
        self.kind = kind
        self.dot = dot
        self.icon = icon
        self.impact = impact
        self.is_hover = False
        self.is_down = False
        self.font_size = font_size
        self.fixed_width = width
        self.fixed_height = height
        super().__init__(
            parent,
            width=self._natural_width(),
            height=px(height),
            bg=bg or parent_bg(parent, palette['bg']),
            borderwidth=0,
            highlightthickness=0,
            relief='flat',
            cursor='hand2',
        )
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        if tooltip:
            Tooltip(self, tooltip, palette)
        self.redraw()

    def _font(self):
        return font(self.font_size, 'semibold')

    def _content_width(self):
        w = fitter.measure(self._font(), self.caption) if self.caption else 0
        if self.icon:
            text, f = glyph(self.icon, self.font_size + 1)
            w += f.measure(text) + (px(7) if self.caption else 0)
        if self.dot:
            w += px(13)
        if self.impact:
            w += px(13) + px(7)
        return w

    def _natural_width(self):
        if self.fixed_width:
            return px(self.fixed_width)
        if self.icon and not self.caption:
            return px(self.fixed_height)
        return max(px(30), self._content_width() + px(26 if self.kind in ('selected', 'chip') else 28))

    def set_caption(self, text):
        self.caption = text
        self.configure(width=self._natural_width())
        self.redraw()

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.redraw()

    def on_enter(self, _):
        self.is_hover = True
        self.redraw()

    def on_leave(self, _):
        self.is_hover = self.is_down = False
        self.redraw()

    def _press(self, _e):
        self.is_down = True
        self.redraw()

    def _release(self, e):
        # Fire on release inside the button, like native controls.
        self.is_down = False
        self.redraw()
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.cmd()

    def _style(self):
        p, kind, hover = self.p, self.kind, self.is_hover
        if kind == 'primary':
            return (p['primary_hover'] if hover else p['primary']), p['primary_fg'], ''
        if kind == 'selected':
            return p['raised'], p['text'], ''
        if kind == 'chip':
            return (p['hover'] if hover else ''), (p['text'] if hover else p['soft']), ''
        if kind == 'subtle':
            return (p['hover'] if hover else ''), (p['text'] if hover else p['soft']), ''
        return (p['hover'] if hover else p['card']), p['text'], p['line_strong']

    def redraw(self):
        self.delete('all')
        w = self.winfo_width() if self.winfo_width() > 1 else int(self.cget('width'))
        h = self.winfo_height() if self.winfo_height() > 1 else int(self.cget('height'))
        fill, fg, outline = self._style()
        pill = self.kind in ('selected', 'chip')
        radius = h // 2 if pill else px(7)
        inset = 1 if self.is_down else 0
        if fill or outline:
            rounded(self, inset, inset, w - inset, h - inset, radius, fill, outline)
        f = self._font()
        m = Mirror(w)
        x = (w - self._content_width()) / 2
        cy = h / 2
        if self.icon:
            text, icon_font = glyph(self.icon, self.font_size + 1)
            if not self.caption:
                self.create_text(w / 2, cy, text=text, fill=fg, font=icon_font)
                return
            self.create_text(m.x(x), cy, text=text, fill=fg, font=icon_font, anchor=m.a('w'))
            x += icon_font.measure(text) + px(7)
        if self.dot:
            dot(self, m.x(x + px(4)), cy, px(7), self.dot)
            x += px(13)
        if self.impact:
            impact_mark(self, m.box(x, impact_width(self.impact)), cy, self.impact, self.p)
            x += px(13) + px(7)
        self.create_text(m.x(x), cy, text=i18n.bidi(self.caption), fill=fg, font=f, anchor=m.a('w'))


class IconButton(FlatButton):
    def __init__(self, parent, icon, command, palette, size=32, tooltip=None, font_size=10, bg=None):
        super().__init__(
            parent, '', command, palette, 'subtle', None, size, font_size, icon=icon, tooltip=tooltip, bg=bg
        )


class Segmented(tk.Canvas):
    """Two-to-four option segmented control with a raised thumb."""

    def __init__(self, parent, options, value, command, palette, height=30, font_size=9, bg=None, min_width=0):
        self.options = list(options)  # [(value, label)], drawn in reading order
        if i18n.rtl():
            self.options.reverse()
        self.value = value
        self.command = command
        self.p = palette
        self.font_size = font_size
        self.hover = None
        f = font(font_size, 'semibold')
        self.seg_w = max([px(min_width)] + [fitter.measure(f, label) + px(26) for _v, label in self.options])
        self.pad = px(3)
        super().__init__(
            parent,
            width=self.seg_w * len(self.options) + 2 * self.pad,
            height=px(height),
            bg=bg or parent_bg(parent, palette['bg']),
            highlightthickness=0,
            borderwidth=0,
            cursor='hand2',
        )
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda _e: self._set_hover(None))
        self.bind('<ButtonRelease-1>', self._click)
        self.redraw()

    def _index_at(self, x):
        i = int((x - self.pad) // max(1, self.seg_w))
        return i if 0 <= i < len(self.options) else None

    def _motion(self, e):
        self._set_hover(self._index_at(e.x))

    def _set_hover(self, idx):
        if idx != self.hover:
            self.hover = idx
            self.redraw()

    def _click(self, e):
        idx = self._index_at(e.x)
        if idx is None:
            return
        value = self.options[idx][0]
        if value != self.value:
            self.set(value)
            self.command(value)

    def set(self, value):
        self.value = value
        self.redraw()

    def redraw(self):
        self.delete('all')
        p = self.p
        w = int(self.cget('width'))
        h = self.winfo_height() if self.winfo_height() > 1 else int(self.cget('height'))
        rounded(self, 0, 0, w, h, px(8), p['seg'])
        for i, (value, label) in enumerate(self.options):
            x0 = self.pad + i * self.seg_w
            selected = value == self.value
            if selected:
                rounded(
                    self,
                    x0,
                    self.pad,
                    x0 + self.seg_w,
                    h - self.pad,
                    px(6),
                    p['thumb'],
                    p['line_strong'] if p['thumb'] == '#FFFFFF' else '',
                )
            colour = p['text'] if selected or i == self.hover else p['soft']
            self.create_text(
                x0 + self.seg_w / 2, h / 2, text=i18n.bidi(label), fill=colour, font=font(self.font_size, 'semibold')
            )


class Toggle(tk.Canvas):
    """Switch bound to a BooleanVar, with a short eased knob animation."""

    W, H = 36, 20

    def __init__(self, parent, variable, palette, bg=None):
        self.var = variable
        self.p = palette
        self.pos = 1.0 if variable.get() else 0.0
        self._anim = None
        super().__init__(
            parent,
            width=px(self.W),
            height=px(self.H),
            bg=bg or parent_bg(parent, palette['bg']),
            highlightthickness=0,
            borderwidth=0,
            cursor='hand2',
        )
        self.bind('<ButtonRelease-1>', lambda _e: self.toggle())
        self._trace = self.var.trace_add('write', lambda *_: self._animate())
        self.bind('<Destroy>', self._untrace)
        self.redraw()

    def _untrace(self, _e):
        try:
            self.var.trace_remove('write', self._trace)
        except (tk.TclError, ValueError):
            pass

    def toggle(self):
        self.var.set(not self.var.get())

    def _animate(self, step=0):
        target = 1.0 if self.var.get() else 0.0
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        if step >= 6 or abs(self.pos - target) < 0.02:
            self.pos = target
            self.redraw()
            return
        self.pos += (target - self.pos) * 0.5
        self.redraw()
        self._anim = self.after(14, self._animate, step + 1)

    def redraw(self):
        self.delete('all')
        p = self.p
        w, h = px(self.W), px(self.H)
        on = bool(self.var.get())
        rounded(self, 0, 0, w, h, h // 2, p['primary'] if on else p['track'])
        knob = h - px(6)
        cx = Mirror(w).x(h / 2 + (w - h) * self.pos)
        dot(self, cx, h / 2, knob, p['primary_fg'] if on else p['white'])


class FlatSelect(tk.Canvas):
    """Theme-consistent dropdown (no operating-system grey combobox)."""

    ROW = 32

    def __init__(self, parent, value, options, palette, width=242, height=34, labels=None):
        self.value = value
        self.options = [str(x) for x in options]
        self.labels = labels or {}
        self.p = palette
        self.popup = None
        self.is_hover = False
        super().__init__(
            parent,
            width=px(width),
            height=px(height),
            bg=parent_bg(parent, palette['bg']),
            borderwidth=0,
            highlightthickness=0,
            cursor='hand2',
        )
        self.bind('<Button-1>', lambda _e: self.open_popup())
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<Enter>', lambda _e: self._hover(True))
        self.bind('<Leave>', lambda _e: self._hover(False))
        self._trace = self.value.trace_add('write', lambda *_: self.redraw())
        self.bind('<Destroy>', self._cleanup)
        self.redraw()

    def _label(self, item):
        return self.labels.get(item, item)

    def _cleanup(self, _e):
        try:
            self.value.trace_remove('write', self._trace)
        except (tk.TclError, ValueError):
            pass
        self.choose(None)

    def _hover(self, state):
        self.is_hover = state
        self.redraw()

    def redraw(self):
        self.delete('all')
        p = self.p
        w = self.winfo_width() if self.winfo_width() > 1 else int(self['width'])
        h = self.winfo_height() if self.winfo_height() > 1 else int(self['height'])
        border = p['faded'] if self.popup else (p['faded'] if self.is_hover else p['line_strong'])
        rounded(self, 0, 0, w, h, px(7), p['input'], border)
        f = font(10)
        m = Mirror(w)
        self.create_text(
            m.x(px(12)),
            h / 2,
            text=i18n.bidi(fitter.fit(f, self._label(str(self.value.get())), w - px(40))),
            fill=p['text'],
            font=f,
            anchor=m.a('w'),
        )
        text, icon_font = glyph('chevron', 8)
        self.create_text(m.x(w - px(14)), h / 2, text=text, fill=p['soft'], font=icon_font)

    def open_popup(self):
        if self.popup:
            self.choose(None)
            return
        p = self.p
        row = px(self.ROW)
        top = tk.Toplevel(self)
        self.popup = top
        top.overrideredirect(True)
        top.attributes('-topmost', True)
        native = native_round(top, p['line_strong'], small=True)
        top.configure(bg=p['line_strong'])
        popup_w = max(self.winfo_width(), px(222))
        popup_h = min(len(self.options) * row + px(8), px(310))
        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + px(4)
        if ry + popup_h > top.winfo_screenheight() - px(15):
            ry = self.winfo_rooty() - popup_h - px(4)
        top.geometry(f'{popup_w}x{popup_h}+{rx}+{max(0, ry)}')
        wrap = tk.Canvas(top, bg=p['card'], highlightthickness=0, borderwidth=0)
        wrap.pack(fill='both', expand=True, padx=0 if native else 1, pady=0 if native else 1)
        current = str(self.value.get())
        inner_w = popup_w - (0 if native else 2)
        m = Mirror(inner_w)

        def hover(i):
            wrap.delete('hover')
            if i is not None:
                y = i * row + px(4)
                rounded(wrap, px(4), y, inner_w - px(4), y + row, px(6), p['hover'], tags=('hover',))
                wrap.tag_lower('hover')

        for i, item in enumerate(self.options):
            selected = item == current
            y = i * row + px(4)
            wrap.create_rectangle(0, y, inner_w, y + row, fill='', outline='', tags=(f'opt{i}',))
            wrap.create_text(
                m.x(px(14)),
                y + row / 2,
                text=i18n.bidi(self._label(item)),
                anchor=m.a('w'),
                fill=p['text'],
                font=font(10, 'semibold' if selected else 'normal'),
                tags=(f'opt{i}',),
            )
            if selected:
                mark, mark_font = glyph('released', 9)
                wrap.create_text(
                    m.x(inner_w - px(16)), y + row / 2, text=mark, fill=p['text'], font=mark_font, tags=(f'opt{i}',)
                )
            wrap.tag_bind(f'opt{i}', '<ButtonRelease-1>', lambda _e, v=item: self.choose(v))
            wrap.tag_bind(f'opt{i}', '<Enter>', lambda _e, k=i: hover(k))
        wrap.bind('<Leave>', lambda _e: hover(None))
        wrap.configure(scrollregion=(0, 0, popup_w, len(self.options) * row + px(8)))
        wrap.bind('<MouseWheel>', lambda e: wrap.yview_scroll(wheel_units(wrap, e, 1), 'units'))
        top.bind('<Escape>', lambda _e: self.choose(None))
        top.bind('<FocusOut>', lambda _e: self.after(120, self._close_if_unfocused))
        top.focus_set()
        self.redraw()

    def _close_if_unfocused(self):
        if not self.popup:
            return
        try:
            focused = self.popup.focus_get()
        except (tk.TclError, KeyError):
            focused = None
        if focused is None or not str(focused).startswith(str(self.popup)):
            self.choose(None)

    def choose(self, v):
        if v is not None:
            self.value.set(v)
        if self.popup:
            t, self.popup = self.popup, None
            try:
                t.destroy()
            except tk.TclError:
                pass
            try:
                self.redraw()
            except tk.TclError:
                pass


class TinyScrollbar(tk.Canvas):
    """Slim overlay-style scrollbar; no native XP-themed trough."""

    def __init__(self, parent, scroll_canvas, palette):
        self.target = scroll_canvas
        self.p = palette
        self.fractions = (0.0, 1.0)
        self.drag_base = None
        self.is_hover = False
        super().__init__(
            parent,
            width=px(10),
            bg=parent_bg(parent, palette['card']),
            borderwidth=0,
            highlightthickness=0,
            cursor='arrow',
        )
        self.bind('<Configure>', lambda _e: self.render())
        self.bind('<Button-1>', self.jump)
        self.bind('<B1-Motion>', self.drag)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Enter>', lambda _e: self._hover(True))
        self.bind('<Leave>', lambda _e: self._hover(False))
        self.render()

    def _hover(self, state):
        self.is_hover = state
        self.render()

    def _release(self, _e):
        self.drag_base = None
        self.render()

    def set(self, start, end):
        fractions = (float(start), float(end))
        if fractions != self.fractions:
            self.fractions = fractions
            self.render()

    def _geometry(self):
        h = max(1, self.winfo_height())
        pad = px(4)
        a, b = self.fractions
        track = max(1, h - 2 * pad)
        knob_h = max(px(32), (b - a) * track)
        top = pad + a * track
        if top + knob_h > h - pad:
            top = h - pad - knob_h
        return h, pad, track, top, knob_h

    def render(self):
        self.delete('all')
        a, b = self.fractions
        if b - a >= 0.999:
            return
        _h, _pad, _track, top, knob_h = self._geometry()
        w = int(self.cget('width'))
        active = self.is_hover or self.drag_base
        thick = px(6) if active else px(4)
        x0 = (w - thick) // 2
        rounded(
            self, x0, top, x0 + thick, top + knob_h, thick // 2, self.p['faded'] if active else self.p['line_strong']
        )

    def jump(self, e):
        _h, pad, track, top, knob_h = self._geometry()
        if not top <= e.y <= top + knob_h:
            span = self.fractions[1] - self.fractions[0]
            self.target.yview_moveto(max(0.0, min(1.0, (e.y - pad) / track - span / 2)))
        self.drag_base = (e.y, self.target.yview()[0])

    def drag(self, e):
        if not self.drag_base:
            return
        y, start = self.drag_base
        _h, _pad, track, _top, _knob = self._geometry()
        self.target.yview_moveto(max(0.0, min(1.0, start + (e.y - y) / track)))


class Panel(tk.Frame):
    """Rounded surface with a hairline border hosting ordinary Tk widgets.

    Put children in ``panel.body``. The rounded background is a canvas
    *placed* behind the body, so the panel's size comes from normal pack/grid
    geometry (its content, or ``fill``/``expand`` from the caller).
    """

    def __init__(self, parent, palette, radius=12, fill=None, outline=None, fit=True, bg=None, pad=0):
        self.p = palette
        self.radius = px(radius)
        self.fill = fill or palette['card']
        self.outline = palette['line'] if outline is None else outline
        outer = bg or parent_bg(parent, palette['bg'])
        super().__init__(parent, bg=outer)
        self.canvas = tk.Canvas(self, bg=outer, highlightthickness=0, borderwidth=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        inset = max(1, int(self.radius * 0.32)) + px(pad)
        self.body = tk.Frame(self, bg=self.fill)
        self.body.pack(fill='both', expand=True, padx=inset, pady=inset)
        self.canvas.bind('<Configure>', lambda _e: self._draw())

    def _draw(self):
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        c.delete('all')
        if w > 2 and h > 2:
            rounded(c, 0, 0, w, h, self.radius, self.fill, self.outline)

    def set_outline(self, colour):
        self.outline = colour
        self._draw()


class NavItem(tk.Canvas):
    """Sidebar entry: icon + label, rounded highlight for hover / active."""

    def __init__(self, parent, icon, text, command, palette, height=34, bg=None):
        self.p, self.icon, self.text, self.command = palette, icon, text, command
        self.active = False
        self.is_hover = False
        super().__init__(
            parent,
            height=px(height),
            bg=bg or parent_bg(parent, palette['side']),
            highlightthickness=0,
            borderwidth=0,
            cursor='hand2',
        )
        self.bind('<Configure>', lambda _e: self.redraw())
        self.bind('<Enter>', lambda _e: self._hover(True))
        self.bind('<Leave>', lambda _e: self._hover(False))
        self.bind('<ButtonRelease-1>', lambda _e: self.command())

    def _hover(self, state):
        self.is_hover = state
        self.redraw()

    def set_active(self, active):
        if active != self.active:
            self.active = active
            self.redraw()

    def redraw(self):
        self.delete('all')
        p = self.p
        w = max(1, self.winfo_width())
        h = self.winfo_height() if self.winfo_height() > 1 else int(self.cget('height'))
        if self.active or self.is_hover:
            rounded(self, 0, 0, w, h, px(7), p['raised'] if self.active else p['hover'])
        colour = p['text'] if self.active or self.is_hover else p['soft']
        text, f = glyph(self.icon, 11)
        m = Mirror(w)
        self.create_text(m.x(px(13)), h / 2, text=text, fill=colour, font=f, anchor=m.a('w'))
        self.create_text(
            m.x(px(40)),
            h / 2,
            text=i18n.bidi(self.text),
            fill=colour,
            font=font(10, 'semibold' if self.active else 'normal'),
            anchor=m.a('w'),
        )


class StatusLine(tk.Canvas):
    """Coloured dot followed by text, e.g. ● Live · synced 20:52."""

    def __init__(self, parent, palette, size=8, bg=None):
        self.p = palette
        self.size = size
        super().__init__(
            parent,
            height=px(size * 2 + 4),
            width=px(40),
            bg=bg or parent_bg(parent, palette['bg']),
            highlightthickness=0,
            borderwidth=0,
        )
        self.state = None

    def set(self, colour, text, secondary=''):
        state = (colour, text, secondary)
        if state == self.state:
            return
        self.state = state
        self.delete('all')
        h = int(self.cget('height'))
        f, sf = font(self.size, 'semibold'), font(self.size)
        secondary = '  ·  ' + secondary if secondary else ''
        total = px(13) + fitter.measure(f, text) + (fitter.measure(sf, secondary) if secondary else 0) + px(2)
        self.configure(width=total)
        m = Mirror(total)
        dot(self, m.x(px(4)), h / 2, px(6), colour)
        x = px(13)
        self.create_text(m.x(x), h / 2, text=i18n.bidi(text), fill=self.p['soft'], font=f, anchor=m.a('w'))
        if secondary:
            x += fitter.measure(f, text)
            self.create_text(m.x(x), h / 2, text=i18n.bidi(secondary), fill=self.p['faded'], font=sf, anchor=m.a('w'))
