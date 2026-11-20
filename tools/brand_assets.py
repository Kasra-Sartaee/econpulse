"""Build the README and website artwork from the screenshots.

    python tools/screenshots.py      # first, if the app's look changed
    python tools/brand_assets.py

Writes to docs/assets/:
    logo.svg                 the EconPulse mark as a vector (same geometry as the app icon)
    hero-dark.png            calendar + widget on a dark backdrop (README, website)
    hero-light.png           the same in the light theme
    social-preview.png       1280x640 card for link previews (Settings -> Social preview on GitHub)

Uses Segoe UI where available (Windows) and Pillow's built-in font elsewhere.
"""

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse.theme import render_brand

SHOTS = ROOT / 'docs' / 'screenshots'
OUT = ROOT / 'docs' / 'assets'

TILE, STROKE, ACCENT = '#111113', '#F2F2F2', '#F2555A'
# Same proportions as theme.render_brand, as fractions of the tile size.
PULSE = [(0.18, 0.56), (0.36, 0.56), (0.45, 0.30), (0.56, 0.74), (0.64, 0.50), (0.70, 0.56)]


def logo_svg(size=256) -> str:
    points = ' '.join(f'{x * size:.1f},{y * size:.1f}' for x, y in PULSE)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        'role="img" aria-label="EconPulse">\n'
        f'  <rect width="{size}" height="{size}" rx="{size * 0.27:.1f}" fill="{TILE}"/>\n'
        f'  <polyline points="{points}" fill="none" stroke="{STROKE}" stroke-width="{size * 0.085:.1f}" '
        'stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'  <circle cx="{size * 0.835:.1f}" cy="{size * 0.56:.1f}" r="{size * 0.075:.1f}" fill="{ACCENT}"/>\n'
        '</svg>\n'
    )


def font(size, bold=False):
    name = 'seguisb.ttf' if bold else 'segoeui.ttf'
    for folder in (Path('C:/Windows/Fonts'), Path.home() / 'AppData/Local/Microsoft/Windows/Fonts'):
        if (folder / name).exists():
            return ImageFont.truetype(str(folder / name), size)
    return ImageFont.load_default(size)


def backdrop(size, dark):
    """Soft vertical gradient with two faint glows: calm, not decorative."""
    w, h = size
    top, bottom = ((24, 25, 30), (9, 9, 11)) if dark else ((248, 248, 250), (230, 231, 236))
    base = Image.new('RGB', (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        base.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    base = base.resize((w, h))
    glow = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    cool = (90, 110, 160, 60) if dark else (120, 140, 200, 50)
    warm = (242, 85, 90, 46) if dark else (242, 85, 90, 34)
    d.ellipse((-w * 0.25, -h * 0.55, w * 0.55, h * 0.55), fill=cool)
    d.ellipse((w * 0.55, h * 0.45, w * 1.25, h * 1.45), fill=warm)
    glow = glow.filter(ImageFilter.GaussianBlur(min(w, h) // 5))
    return Image.alpha_composite(base.convert('RGBA'), glow)


def place(canvas, shot, xy, scale, radius, dark):
    """Paste a window with rounded corners, a hairline edge and a soft shadow."""
    img = shot.convert('RGBA')
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    w, h = img.size
    r = round(radius * scale)
    shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    spread = round(46 * scale)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (xy[0], xy[1] + spread // 2, xy[0] + w, xy[1] + h + spread // 2),
        r,
        fill=(0, 0, 0, 150 if dark else 70),
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(spread)))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    canvas.paste(img, xy, mask)
    edge = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        (xy[0], xy[1], xy[0] + w - 1, xy[1] + h - 1),
        r,
        outline=(255, 255, 255, 34) if dark else (0, 0, 0, 30),
        width=max(1, round(2 * scale)),
    )
    canvas.alpha_composite(edge)


def hero(dark):
    calendar = Image.open(SHOTS / ('calendar-dark.png' if dark else 'calendar-light.png'))
    widget = Image.open(SHOTS / ('widget-today.png' if dark else 'widget-light.png'))
    canvas = backdrop((2000, 1240), dark)
    place(canvas, calendar, (80, 86), 0.8, 18, dark)
    w, h = round(widget.width * 0.8), round(widget.height * 0.8)
    place(canvas, widget, (2000 - w - 84, 1240 - h - 70), 0.8, 18, dark)
    return canvas.convert('RGB')


def social_preview():
    canvas = backdrop((1280, 640), True)
    place(canvas, Image.open(SHOTS / 'calendar-dark.png'), (650, 92), 0.52, 18, True)
    widget = Image.open(SHOTS / 'widget-today.png')
    place(canvas, widget, (1280 - round(widget.width * 0.58) - 56, 74), 0.58, 18, True)
    mark = render_brand(104, TILE, STROKE, ACCENT)
    tile = Image.new('RGBA', (108, 108), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, 107, 107), 30, fill=(255, 255, 255, 40))
    tile.alpha_composite(mark, (2, 2))
    canvas.alpha_composite(tile, (84, 136))
    d = ImageDraw.Draw(canvas)
    d.text((80, 262), 'EconPulse', font=font(88, bold=True), fill=(244, 244, 246))
    for i, line in enumerate(('The economic calendar that lives', 'on your desktop.')):
        d.text((84, 390 + i * 46), line, font=font(34), fill=(178, 180, 188))
    d.text((84, 520), 'Free & open source  ·  Windows · macOS · Linux', font=font(24), fill=(124, 126, 136))
    return canvas.convert('RGB')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'logo.svg').write_text(logo_svg(), encoding='utf-8', newline='\n')
    outputs = {
        'hero-dark.png': hero(True),
        'hero-light.png': hero(False),
        'social-preview.png': social_preview(),
    }
    for name, image in outputs.items():
        image.save(OUT / name, optimize=True)
    for path in sorted(OUT.iterdir()):
        print(f'{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
