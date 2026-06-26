"""Generate AFK app icons (gradient rounded-square + microphone glyph).

Produces assets/icon.png (256), assets/tray.png (32, light glyph for the tray),
and assets/icon.ico (multi-size) used by electron-builder.

Run:  python/.venv/Scripts/python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ACCENT_A = (108, 140, 255)   # #6c8cff
ACCENT_B = (155, 108, 255)   # #9b6cff
BG = (15, 17, 21)            # #0f1115


def _gradient(size, a, b):
    base = Image.new("RGB", (size, size), a)
    top = Image.new("RGB", (size, size), b)
    mask = Image.new("L", (size, size))
    md = mask.load()
    for y in range(size):
        for x in range(size):
            md[x, y] = int(255 * ((x + y) / (2 * size)))
    base.paste(top, (0, 0), mask)
    return base


def _rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _mic(draw, size, color):
    cx = size / 2
    w = size * 0.16
    top = size * 0.22
    bot = size * 0.55
    draw.rounded_rectangle([cx - w, top, cx + w, bot], radius=w, fill=color)
    # arc (mic stand cup)
    r = size * 0.20
    draw.arc([cx - r, bot - r, cx + r, bot + r], start=20, end=160, fill=color, width=int(size * 0.05))
    # stem + base
    draw.line([cx, bot + r * 0.55, cx, size * 0.80], fill=color, width=int(size * 0.05))
    draw.line([cx - size * 0.12, size * 0.80, cx + size * 0.12, size * 0.80], fill=color, width=int(size * 0.05))


def make_app_icon(size=256):
    icon = _gradient(size, ACCENT_A, ACCENT_B)
    # dark inset panel so the glyph reads on any background
    inset = int(size * 0.10)
    pside = size - 2 * inset
    panel = Image.new("RGB", (pside, pside), BG)
    pm = _rounded_mask(pside, int(size * 0.18))
    icon.paste(panel, (inset, inset), pm)
    draw = ImageDraw.Draw(icon)
    _mic(draw, size, (235, 238, 245))
    icon.putalpha(_rounded_mask(size, int(size * 0.22)))
    return icon


def make_tray(size=32):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _mic(draw, size, (235, 238, 245, 255))
    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    app = make_app_icon(256)
    app.save(ASSETS / "icon.png")
    make_tray(32).save(ASSETS / "tray.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    app.save(ASSETS / "icon.ico", sizes=[(s, s) for s in sizes])
    print("Wrote icon.png, tray.png, icon.ico to", ASSETS)


if __name__ == "__main__":
    main()
