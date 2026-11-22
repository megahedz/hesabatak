#!/usr/bin/env python3
"""Generate the حساباتك launcher icon — v3 «نظيف».

A calm, minimal mark that matches the app's v2 design system:
  * deep navy → teal diagonal tile, generous corner radius
  * three rising bars (white, soft white, mint) — the "ledger" idea
  * a single mint arrow sweeping up-right over the bars — growth
  * nothing else: no sparkles, no circuit, no text, no baked-in lettering,
    so the icon stays legible at 48dp and never looks like clip-art.

The artwork sits inside the 66% adaptive-icon safe zone, so it survives the
circular/squircle masks Android launchers apply.

Outputs (next to this script):
  * icon.png            — 1024×1024 launcher source (flutter_launcher_icons)
  * icon_foreground.png — same artwork for the adaptive foreground

Usage:  python3 generate_icon.py   (requires: pip install pillow)
"""
from PIL import Image, ImageDraw

S = 1024
SS = 3                      # supersampling factor for smooth edges
W = S * SS

NAVY = (10, 37, 64)
MID = (13, 78, 90)
EMERALD = (14, 124, 107)

WHITE = (255, 255, 255, 255)
SOFT_WHITE = (255, 255, 255, 205)
MINT = (127, 233, 195, 255)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(size):
    """Diagonal navy → teal gradient."""
    small = 512
    img = Image.new("RGB", (small, small))
    px = img.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            px[x, y] = lerp(NAVY, MID, t / 0.6) if t < 0.6 else lerp(MID, EMERALD, (t - 0.6) / 0.4)
    return img.resize((size, size), Image.LANCZOS).convert("RGBA")


def draw_mark(size, scale=1.0):
    """Transparent layer with the bars + arrow, centred on `size`.

    Geometry is laid out on a 1024 grid spanning ~640px so the mark fills the
    adaptive-icon safe zone instead of shrinking into the middle.
    """
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def p(v):
        return size / 2 + (v - 512) * scale

    bar_w, gap, base_y = 126, 58, 752
    heights = [240, 386, 526]
    colors = [(255, 255, 255, 150), (255, 255, 255, 205), (255, 255, 255, 245)]
    group_left = 512 - (3 * bar_w + 2 * gap) / 2

    for i, (h, c) in enumerate(zip(heights, colors)):
        left = p(group_left + i * (bar_w + gap))
        right = p(group_left + i * (bar_w + gap) + bar_w)
        d.rounded_rectangle(
            [left, p(base_y - h), right, p(base_y)],
            radius=34 * scale,
            fill=c,
        )

    # Growth arrow: thick mint stroke sweeping over the bars, angled up-right.
    import math

    x0, y0 = p(238), p(556)
    x1, y1 = p(792), p(296)
    stroke = 56 * scale
    d.line([(x0, y0), (x1, y1)], fill=MINT, width=int(stroke))
    d.ellipse([x0 - stroke / 2, y0 - stroke / 2, x0 + stroke / 2, y0 + stroke / 2], fill=MINT)

    # Arrowhead: two base corners around the tip, perpendicular to the stroke.
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    px_, py_ = -uy, ux
    head_len, head_half = 150 * scale, 108 * scale
    d.polygon(
        [
            (x1 + ux * 6, y1 + uy * 6),
            (x1 - ux * head_len + px_ * head_half, y1 - uy * head_len + py_ * head_half),
            (x1 - ux * head_len - px_ * head_half, y1 - uy * head_len - py_ * head_half),
        ],
        fill=MINT,
    )
    return layer


def main():
    tile_mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(tile_mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=int(W * 0.225), fill=255)

    bg = gradient(W)
    tile = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    tile.paste(bg, (0, 0), tile_mask)

    # 1.02 keeps the mark inside the adaptive-icon safe zone (~66% diameter)
    # while still filling the tile the way a launcher icon should.
    tile.alpha_composite(draw_mark(W, scale=1.02))

    icon = tile.resize((S, S), Image.LANCZOS)
    icon.convert("RGB").save("icon.png", optimize=True)
    icon.save("icon_foreground.png", optimize=True)
    print("wrote icon.png and icon_foreground.png")


if __name__ == "__main__":
    main()
