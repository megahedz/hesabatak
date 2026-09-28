#!/usr/bin/env python3
"""Generate the حساباتك launcher icon set.

Artwork (matches the approved brand image):
  * white rounded tile on a transparent background
  * navy "M" built from two blocks — the left holds rising chart bars,
    the right holds a cyan circuit pattern
  * mint→cyan gradient growth ribbon forming the M's diagonals with a
    doubled green stroke underneath, ending in an arrow head

Outputs (next to this script):
  * icon.png            — 1024×1024 legacy/launcher source (flutter_launcher_icons image_path)
  * icon_foreground.png — 1024×1024 adaptive-icon foreground (artwork only, safe-zone scaled)

Usage:  python3 generate_icon.py   (requires: pip install pillow)
"""
from PIL import Image, ImageDraw

S = 1024

# palette
WHITE = (255, 255, 255, 255)
TILE_BORDER = (214, 221, 230, 255)
NAVY_TOP = (24, 64, 112, 255)
NAVY_BOT = (13, 40, 76, 255)
MINT = (143, 232, 160, 255)
CYAN = (46, 201, 216, 255)
GREEN = (53, 216, 154, 255)
BLUE = (47, 160, 230, 255)
DEEP_GREEN = (42, 164, 107, 255)
TEAL = (37, 183, 168, 255)
BAR_COLORS = ((79, 195, 161, 255), (62, 155, 216, 255), (127, 196, 238, 255))
CIRCUIT = (63, 198, 232, 255)


def lerp(c0, c1, t):
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * t)) for i in range(4))


def vgrad(w, h, c0, c1):
    """Vertical gradient image."""
    g = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        gd.line([(0, y), (w, y)], fill=lerp(c0, c1, y / max(1, h - 1)))
    return g


def rounded_mask(size, box, radius):
    """Rounded-rect mask matching `size` (block-local coords)."""
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle(box, radius=radius, fill=255)
    return m


def dot(draw, p, r, color):
    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def grad_polyline(draw, pts, stops, width):
    """Polyline whose color interpolates along its length (stops: list of (t, color)).
    Round caps/joints faked with dots at every sub point."""
    assert stops[0][0] == 0.0 and stops[-1][0] == 1.0
    total = sum(
        ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
        for i in range(len(pts) - 1)
    )
    n = 14  # sub-segments per unit segment
    acc = 0.0
    sub = []
    sub_t = []
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        seg = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        for k in range(n + 1):
            t = k / n
            sub.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            sub_t.append((acc + seg * t) / total)
        acc += seg
    r = width / 2
    for i in range(len(sub) - 1):
        color = _stop_color(stops, sub_t[i])
        draw.line([sub[i], sub[i + 1]], fill=color, width=width)
    for p in sub:
        dot(draw, p, r, _stop_color(stops, sub_t[sub.index(p)]))


def _stop_color(stops, t):
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            return lerp(c0, c1, (t - t0) / max(1e-6, t1 - t0))
    return stops[-1][1]


def draw_blocks(layer):
    """Navy M blocks: chart bars (left) + circuit (right)."""
    # ---- left block with rising bars
    lb = (195, 255, 428, 815)
    lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    mask = rounded_mask((lw, lh), (0, 0, lw, lh), 14)
    grad = vgrad(lw, lh, NAVY_TOP, NAVY_BOT)
    bars = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bars)
    bw, gap, bottom = 44, 21, (lb[3] - lb[1]) - 28
    for i, (color, top) in enumerate(
        [(BAR_COLORS[0], 245), (BAR_COLORS[1], 145), (BAR_COLORS[2], 55)]
    ):
        x0 = 30 + i * (bw + gap)
        bd.rounded_rectangle([x0, top, x0 + bw, bottom], radius=8, fill=color)
    grad.alpha_composite(bars)
    layer.paste(grad, (lb[0], lb[1]), mask)

    # ---- right block with circuit pattern
    rb = (612, 492, 845, 815)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    mask = rounded_mask((rw, rh), (0, 0, rw, rh), 14)
    grad = vgrad(rw, rh, NAVY_TOP, NAVY_BOT)
    circ = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(circ)
    w = 9
    lines = [((53, 48), (53, 253)), ((53, 108), (113, 148)), ((113, 148), (158, 108)),
             ((53, 208), (108, 263))]
    for (x0, y0), (x1, y1) in lines:
        cd.line([(x0, y0), (x1, y1)], fill=CIRCUIT, width=w)
    for (x, y) in [(53, 48), (158, 108), (108, 263)]:
        cd.ellipse([x - 16, y - 16, x + 16, y + 16], outline=CIRCUIT, width=w)
    for (x, y) in [(53, 108), (53, 208), (113, 148)]:
        dot(cd, (x, y), 7, CIRCUIT)
    grad.alpha_composite(circ)
    layer.paste(grad, (rb[0], rb[1]), mask)


def draw_ribbon(layer):
    """Gradient growth ribbon + doubled green stroke + arrow head."""
    p0, p1, p2, p3 = (150, 835), (505, 398), (612, 556), (838, 175)
    d = ImageDraw.Draw(layer)

    # doubled green stroke under the first segment (white gap drawn first)
    import math

    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    px, py = 0.771, 0.637  # perpendicular, pointing lower-right
    off = 92
    b0 = (p0[0] + ux * 10 + px * off, p0[1] + uy * 10 + py * off)
    b1 = (p0[0] + dx * 0.92 + px * off, p0[1] + dy * 0.92 + py * off)
    grad_polyline(d, [b0, b1], [(0.0, WHITE), (1.0, WHITE)], 84)
    grad_polyline(d, [b0, b1], [(0.0, DEEP_GREEN), (1.0, TEAL)], 58)

    # main ribbon with white separation channel
    path = [p0, p1, p2, p3]
    grad_polyline(d, path, [(0.0, WHITE), (1.0, WHITE)], 88)
    grad_polyline(
        d, path,
        [(0.0, MINT), (0.4, CYAN), (0.7, GREEN), (1.0, GREEN)],
        62,
    )

    # arrow head at the end of the path
    ax, ay = p3[0] - p2[0], p3[1] - p2[1]
    aln = math.hypot(ax, ay)
    ax, ay = ax / aln, ay / aln
    tip = (p3[0] + ax * 54, p3[1] + ay * 54)
    qx, qy = -ay, ax
    half = 68
    a1 = (p3[0] + qx * half, p3[1] + qy * half)
    a2 = (p3[0] - qx * half, p3[1] - qy * half)
    cx = (tip[0] + a1[0] + a2[0]) / 3
    cy = (tip[1] + a1[1] + a2[1]) / 3
    big = [(cx + (p[0] - cx) * 1.22, cy + (p[1] - cy) * 1.22) for p in (tip, a1, a2)]
    d.polygon(big, fill=WHITE)
    d.polygon([tip, a1, a2], fill=GREEN)
    mid = ((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2)
    d.polygon([tip, mid, a1], fill=BLUE)


def render(with_tile=True):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if with_tile:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([26, 26, S - 26, S - 26], radius=225, fill=WHITE,
                            outline=TILE_BORDER, width=3)
    draw_blocks(img)
    draw_ribbon(img)
    return img


def main():
    render(with_tile=True).save("icon.png")

    # adaptive foreground: artwork only, scaled into the circular safe zone
    art = render(with_tile=False)
    fg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 0.60 keeps the arrow tip inside the ~66% adaptive-icon safe zone circle
    scale = 0.60
    small = art.resize((int(S * scale), int(S * scale)), Image.LANCZOS)
    fg.alpha_composite(small, ((S - small.width) // 2, (S - small.height) // 2))
    fg.save("icon_foreground.png")
    print("icon.png + icon_foreground.png generated")


if __name__ == "__main__":
    main()
