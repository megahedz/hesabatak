#!/usr/bin/env python3
"""Generate the حساباتك launcher icon set.

Artwork — mirrors the NEW approved brand reference (bold tile-filling M):
  * white rounded tile; the artwork fills the tile edge-to-edge
  * bold navy "M": left leg carries 3 rising chart bars; right leg carries a
    cyan circuit-node pattern AND a small "EGP" circuit badge near its foot
  * thick mint→cyan→green gradient growth ribbon sweeping diagonally across
    the WHOLE tile (bottom-left → top-right), ending in a large arrowhead
    slightly outside the M's right shoulder — like the reference

Outputs (next to this script):
  * icon.png            — 1024×1024 launcher source (flutter_launcher_icons)
  * icon_foreground.png — 1024×1024 adaptive foreground (safe-zone scaled)

Usage:  python3 generate_icon.py   (requires: pip install pillow)
"""
import math

from PIL import Image, ImageDraw

S = 1024

# palette (matches the reference photo exactly)
WHITE = (255, 255, 255, 255)
TILE_BORDER = (219, 226, 235, 255)
NAVY_TOP = (30, 75, 130, 255)
NAVY_BOT = (10, 33, 66, 255)
MINT = (150, 236, 168, 255)
CYAN = (44, 205, 222, 255)
GREEN = (53, 216, 154, 255)
BLUE = (47, 160, 230, 255)
DEEP_GREEN = (42, 164, 107, 255)
TEAL = (37, 183, 168, 255)
BAR_COLORS = ((79, 195, 161, 255), (62, 155, 216, 255), (127, 196, 238, 255))
CIRCUIT = (63, 198, 232, 255)
BADGE_BG = (16, 58, 108, 255)
BADGE_FG = (120, 226, 190, 255)


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


# ======================================================================
# Brand mark: bold tile-filling M (same geometry family as the reference)
# ======================================================================
M_TOP = 150          # top of the left leg (reference M reaches near tile top)
M_BOTTOM = 874       # baseline shared by both legs
LEG_W = 262          # leg thickness — bold like the reference
LX0, LX1 = 148, 148 + LEG_W          # left leg x-range
RX0, RX1 = 616, 616 + LEG_W          # right leg x-range (higher, like ref)


def draw_blocks(layer):
    """Navy M blocks — bold, tile-filling, right leg taller (exactly like ref)."""
    # ---- left leg with 3 rising chart bars
    lb = (LX0, M_TOP, LX1, M_BOTTOM)
    lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    mask = rounded_mask((lw, lh), 20)
    grad = vgrad(lw, lh, NAVY_TOP, NAVY_BOT)
    bars = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bars)
    bw, gap, bottom = 60, 24, lh - 26
    for i, (color, top) in enumerate(
        [(BAR_COLORS[0], 310), (BAR_COLORS[1], 185), (BAR_COLORS[2], 60)]
    ):
        x0 = 28 + i * (bw + gap)
        bd.rounded_rectangle([x0, top, x0 + bw, bottom], radius=10, fill=color)
    grad.alpha_composite(bars)
    layer.paste(grad, (lb[0], lb[1]), mask)

    # ---- right leg with cyan circuit nodes + EGP circuit badge (like ref)
    rb = (RX0, 330, RX1, M_BOTTOM)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    mask = rounded_mask((rw, rh), 20)
    grad = vgrad(rw, rh, NAVY_TOP, NAVY_BOT)
    circ = Image.new("RGBA", grad.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(circ)
    w = 11
    lines = [((66, 56), (66, 200)), ((66, 118), (132, 162)), ((132, 162), (196, 112)),
             ((66, 208), (128, 262))]
    for (x0, y0), (x1, y1) in lines:
        cd.line([(x0, y0), (x1, y1)], fill=CIRCUIT, width=w)
    for (x, y) in [(66, 56), (196, 112), (128, 262)]:
        cd.ellipse([x - 19, y - 19, x + 19, y + 19], outline=CIRCUIT, width=w)
    for (x, y) in [(66, 118), (66, 208), (132, 162)]:
        dot(cd, (x, y), 9, CIRCUIT)
    grad.alpha_composite(circ)

    # EGP circuit badge near the foot of the right leg (reference shows it there)
    badge_r = 108
    bx, by = 130, rh - 128
    cd.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
               fill=BADGE_BG, outline=BADGE_FG, width=12)
    for (px, py) in [(bx, by), (bx + 6, by + badge_r + 6)]:
        pass  # anchor points below are drawn directly on the tile instead
    grad.alpha_composite(circ)
    layer.paste(grad, (rb[0], rb[1]), mask)

    # badge connection node + stem on the tile (spills slightly outside leg —
    # like the reference's circuit badge that bridges both legs)
    d = ImageDraw.Draw(layer)
    anchor = (rb[0] + 130, M_BOTTOM - 128)
    stem_end = (LX1 + 4, M_BOTTOM - 128)
    grad_polyline(d, [anchor, (LX1 + 30, M_BOTTOM - 128), stem_end],
                  [(0.0, BADGE_FG), (1.0, BADGE_FG)], 10)
    dot(d, anchor, 12, BADGE_FG)
    dot(d, stem_end, 10, BADGE_FG)


def _egp_text(rh, by):
    """Draw EGP letters as circuit-like strokes (PIL default font is Latin-only
    and too thin, so we hand-draw E, G, P as thick strokes)."""
    img = Image.new("RGBA", (rh, rh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    t = 20  # stroke thickness
    cx, cy = rh // 2, rh // 2

    def seg(x0, y0, x1, y1, col=BADGE_FG, w=t):
        d.line([(x0, y0), (x1, y1)], fill=col, width=w)

    def ring(x, y, r, col=BADGE_FG, w=t):
        d.ellipse([x - r, y - r, x + r, y + r], outline=col, width=w)

    # E
    ex = cx - 62
    seg(ex, cy - 26, ex, cy + 26)
    seg(ex, cy - 26, ex + 30, cy - 26)
    seg(ex, cy, ex + 22, cy)
    seg(ex, cy + 26, ex + 30, cy + 26)
    # G
    gx = cx + 2
    ring(gx, cy, 28)
    seg(gx + 28, cy, gx + 28, cy + 10, w=t - 6)
    seg(gx, cy + 28, gx + 28, cy + 28, w=t - 6)
    # P
    px = cx + 46
    seg(px, cy - 28, px, cy + 28)
    ring(px + 2, cy - 14, 14, w=t - 6)
    return img


def draw_ribbon(layer):
    """Thick gradient ribbon sweeping the WHOLE tile bottom-left → top-right,
    with the doubled green stroke under its first diagonal and a large
    arrowhead — matching the reference photo."""
    p0, p1, p2, p3 = (118, 892), (512, 352), (618, 560), (896, 140)
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
        d.rounded_rectangle([20, 20, S - 20, S - 20], radius=232, fill=WHITE,
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
