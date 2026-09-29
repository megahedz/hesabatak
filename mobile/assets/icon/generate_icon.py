#!/usr/bin/env python3
"""Generate the حساباتك launcher icon set.

Artwork (mirrors the approved brand reference closely):
  * white rounded tile, artwork fills the tile edge-to-edge
  * bold navy "M": left block with 3 rising chart bars, right block with a
    cyan circuit pattern (taller, like the reference)
  * thick mint→cyan gradient growth ribbon forming the M's V-dip, with the
    doubled green stroke under its first diagonal, ending in a large arrowhead

Outputs (next to this script):
  * icon.png            — 1024×1024 launcher source (flutter_launcher_icons)
  * icon_foreground.png — 1024×1024 adaptive foreground (safe-zone scaled)

Usage:  python3 generate_icon.py   (requires: pip install pillow)
"""
from PIL import Image, ImageDraw

S = 1024

# palette
WHITE = (255, 255, 255, 255)
TILE_BORDER = (219, 226, 235, 255)
NAVY_TOP = (26, 68, 118, 255)
NAVY_BOT = (12, 38, 74, 255)
MINT = (150, 236, 168, 255)
CYAN = (44, 205, 222, 255)
GREEN = (53, 216, 154, 255)
BLUE = (47, 160, 230, 255)
DEEP_GREEN = (42, 164, 107, 255)
TEAL = (37, 183, 168, 255)
BAR_COLORS = ((79, 195, 161, 255), (62, 155, 216, 255), (127, 196, 238, 255))
CIRCUIT = (63, 198, 232, 255)


def lerp(c0, c1, t):
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * t)) for i in range(4))


def vgrad(w, h, c0, c1):
    g = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        gd.line([(0, y), (w, y)], fill=lerp(c0, c1, y / max(1, h - 1)))
    return g


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def dot(draw, p, r, color):
    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def _stop_color(stops, t):
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            return lerp(c0, c1, (t - t0) / max(1e-6, t1 - t0))
    return stops[-1][1]


def grad_polyline(draw, pts, stops, width):
    """Polyline with per-length color interpolation; round caps via dots."""
    assert stops[0][0] == 0.0 and stops[-1][0] == 1.0
    segs = [
        ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
        for i in range(len(pts) - 1)
    ]
    total = sum(segs)
    n = 16
    sub, sub_t = [], []
    acc = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        seg = segs[i]
        for k in range(n + 1):
            t = k / n
            sub.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            sub_t.append((acc + seg * t) / total)
        acc += seg
    r = width / 2
    for i in range(len(sub) - 1):
        draw.line([sub[i], sub[i + 1]], fill=_stop_color(stops, sub_t[i]), width=width)
    for p, t in zip(sub, sub_t):
        dot(draw, p, r, _stop_color(stops, t))


def draw_blocks(layer):
    """Navy M blocks — bold and tile-filling, exactly like the reference."""
    # ---- left block (tall, starts high like the reference's M left leg)
    lb = (168, 218, 452, 822)
    lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    mask = rounded_mask((lw, lh), 18)
    grad = vgrad(lw, lh, NAVY_TOP, NAVY_BOT)
    bars = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bars)
    bw, gap, bottom = 56, 26, lh - 30
    for i, (color, top) in enumerate(
        [(BAR_COLORS[0], 300), (BAR_COLORS[1], 190), (BAR_COLORS[2], 80)]
    ):
        x0 = 28 + i * (bw + gap)
        bd.rounded_rectangle([x0, top, x0 + bw, bottom], radius=10, fill=color)
    grad.alpha_composite(bars)
    layer.paste(grad, (lb[0], lb[1]), mask)

    # ---- right block (starts higher — the reference's right M leg)
    rb = (578, 420, 856, 822)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    mask = rounded_mask((rw, rh), 18)
    grad = vgrad(rw, rh, NAVY_TOP, NAVY_BOT)
    circ = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(circ)
    w = 11
    lines = [((62, 60), (62, 290)), ((62, 130), (130, 172)), ((130, 172), (188, 124)),
             ((62, 240), (124, 302))]
    for (x0, y0), (x1, y1) in lines:
        cd.line([(x0, y0), (x1, y1)], fill=CIRCUIT, width=w)
    for (x, y) in [(62, 60), (188, 124), (124, 302)]:
        cd.ellipse([x - 19, y - 19, x + 19, y + 19], outline=CIRCUIT, width=w)
    for (x, y) in [(62, 130), (62, 240), (130, 172)]:
        dot(cd, (x, y), 9, CIRCUIT)
    grad.alpha_composite(circ)
    layer.paste(grad, (rb[0], rb[1]), mask)


def draw_ribbon(layer):
    """Thick gradient ribbon with white separation + doubled green stroke."""
    import math

    p0, p1, p2, p3 = (128, 878), (512, 356), (618, 560), (888, 140)
    d = ImageDraw.Draw(layer)

    # doubled green stroke under the first diagonal (white gap then green)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    px, py = 0.771, 0.637  # perpendicular, pointing lower-right
    off = 104
    b0 = (p0[0] + ux * 14 + px * off, p0[1] + uy * 14 + py * off)
    b1 = (p0[0] + dx * 0.92 + px * off, p0[1] + dy * 0.92 + py * off)
    grad_polyline(d, [b0, b1], [(0.0, WHITE), (1.0, WHITE)], 96)
    grad_polyline(d, [b0, b1], [(0.0, DEEP_GREEN), (1.0, TEAL)], 66)

    # main ribbon: white separation channel then the gradient stroke
    path = [p0, p1, p2, p3]
    grad_polyline(d, path, [(0.0, WHITE), (1.0, WHITE)], 102)
    grad_polyline(
        d, path,
        [(0.0, MINT), (0.4, CYAN), (0.7, GREEN), (1.0, GREEN)],
        72,
    )

    # large arrowhead at the end
    ax, ay = p3[0] - p2[0], p3[1] - p2[1]
    aln = math.hypot(ax, ay)
    ax, ay = ax / aln, ay / aln
    tip = (p3[0] + ax * 58, p3[1] + ay * 58)
    qx, qy = -ay, ax
    half = 78
    a1 = (p3[0] + qx * half, p3[1] + qy * half)
    a2 = (p3[0] - qx * half, p3[1] - qy * half)
    cx = (tip[0] + a1[0] + a2[0]) / 3
    cy = (tip[1] + a1[1] + a2[1]) / 3
    big = [(cx + (p[0] - cx) * 1.24, cy + (p[1] - cy) * 1.24) for p in (tip, a1, a2)]
    d.polygon(big, fill=WHITE)
    d.polygon([tip, a1, a2], fill=GREEN)
    mid = ((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2)
    d.polygon([tip, mid, a1], fill=BLUE)


def render(with_tile=True):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if with_tile:
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([24, 24, S - 24, S - 24], radius=228, fill=WHITE,
                            outline=TILE_BORDER, width=3)
    draw_blocks(img)
    draw_ribbon(img)
    return img


def main():
    render(with_tile=True).save("icon.png")

    # adaptive foreground: artwork only, scaled into the circular safe zone
    art = render(with_tile=False)
    fg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # 0.57 keeps the bold new artwork inside the ~66% adaptive safe circle
    scale = 0.57
    small = art.resize((int(S * scale), int(S * scale)), Image.LANCZOS)
    fg.alpha_composite(small, ((S - small.width) // 2, (S - small.height) // 2))
    fg.save("icon_foreground.png")
    print("icon.png + icon_foreground.png generated")


if __name__ == "__main__":
    main()
