#!/usr/bin/env python3
"""Generate the حساباتك launcher icon set — v2 «حيوية» refresh.

Artwork (same brand identity as the reference, restyled to POP):
  * vivid diagonal gradient tile: deep navy → rich blue → emerald
    (replaces the plain white tile — the icon now reads instantly on any
    launcher background, light or dark)
  * bold WHITE tile-filling M: left leg carries 3 vivid rising chart bars,
    right leg carries a blue circuit pattern + the EGP circuit badge
  * thick mint→cyan→green gradient growth ribbon sweeping the whole tile
    (bottom-left → top-right) ending in a large arrowhead, with a soft
    white glow behind the tip
  * playful 4-point sparkles for liveliness

Outputs (next to this script):
  * icon.png            — 1024×1024 launcher source (flutter_launcher_icons)
  * icon_foreground.png — 1024×1024 adaptive foreground: gradient background
    baked in + artwork scaled into the 66% circular safe zone (the white
    adaptive background never shows through)

Usage:  python3 generate_icon.py   (requires: pip install pillow)
"""
import math

from PIL import Image, ImageDraw

S = 1024

# ---------------------------------------------------------------- palette
TILE_STOPS = [                      # diagonal gradient (navy → blue → emerald)
    (0.00, (12, 40, 84, 255)),
    (0.45, (21, 95, 168, 255)),
    (0.75, (17, 139, 156, 255)),
    (1.00, (13, 158, 118, 255)),
]
M_TOP = (255, 255, 255, 255)        # white M blocks (top)
M_BOT = (226, 238, 252, 255)        # soft blue-white (bottom)
BAR_COLORS = ((16, 185, 129, 255), (34, 211, 238, 255), (59, 130, 246, 255))
CIRCUIT = (31, 111, 208, 255)       # vivid blue circuit on the white leg
BADGE_BG = (14, 43, 84, 255)
BADGE_FG = (125, 240, 199, 255)
MINT = (150, 236, 168, 255)
CYAN = (44, 205, 222, 255)
GREEN = (53, 216, 154, 255)
BLUE = (47, 160, 230, 255)
DEEP_GREEN = (42, 164, 107, 255)
TEAL = (37, 183, 168, 255)
WHITE = (255, 255, 255, 255)
SPARKLE_A = (255, 255, 255, 235)
SPARKLE_B = (190, 245, 255, 225)


def lerp(c0, c1, t):
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * t)) for i in range(4))


def _stop_color(stops, t):
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            return lerp(c0, c1, (t - t0) / max(1e-6, t1 - t0))
    return stops[-1][1]


def dgrad(w, h, stops):
    """Diagonal gradient (top-left → bottom-right) — the lively tile base."""
    g = Image.new("RGBA", (w, h))
    px = g.load()
    denom = max(1, (w + h - 2))
    for y in range(h):
        for x in range(w):
            px[x, y] = _stop_color(stops, (x + y) / denom)
    return g


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def dot(draw, p, r, color):
    draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=color)


def vgrad(w, h, c0, c1):
    g = Image.new("RGBA", (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        gd.line([(0, y), (w, y)], fill=lerp(c0, c1, y / max(1, h - 1)))
    return g


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


def glow(size, center, radius, color, max_alpha):
    """Soft radial glow baked as concentric alpha rings (one layer)."""
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    cx, cy = center
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps
        r = radius * t
        a = int(max_alpha * (1 - t) ** 1.4)
        if a <= 0:
            continue
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return g


def sparkle(draw, cx, cy, r, color, thin=0.26):
    """4-point star with concave sides — the 'lively' twinkle."""
    k = r * thin
    draw.polygon([
        (cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
        (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k),
    ], fill=color)


def egp_strokes(img, cx, cy, color=BADGE_FG, t=20):
    """Hand-drawn E, G, P inside the badge (PIL's default font is Latin-only
    and too thin, so the letters are built from thick strokes like the ref)."""
    d = ImageDraw.Draw(img)

    def seg(x0, y0, x1, y1, w=t):
        d.line([(x0, y0), (x1, y1)], fill=color, width=w)

    def ring(x, y, r, w=t):
        d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=w)

    # E
    ex = cx - 62
    seg(ex, cy - 26, ex, cy + 26)
    seg(ex, cy - 26, ex + 30, cy - 26)
    seg(ex, cy, ex + 22, cy)
    seg(ex, cy + 26, ex + 30, cy + 26)
    # G
    gx = cx + 2
    ring(gx, cy, 28)
    seg(gx + 28, cy, gx + 28, cy + 10, t - 6)
    seg(gx, cy + 28, gx + 28, cy + 28, t - 6)
    # P
    px = cx + 46
    seg(px, cy - 28, px, cy + 28)
    ring(px + 2, cy - 14, 14, t - 6)


# ======================================================================
# Brand mark: bold tile-filling M (white on the gradient)
# ======================================================================
M_TOP_Y = 150          # top of the left leg
M_BOTTOM = 874         # baseline shared by both legs
LEG_W = 262            # leg thickness — bold like the reference
LX0, LX1 = 148, 148 + LEG_W
RX0, RX1 = 616, 616 + LEG_W


def draw_blocks(layer):
    """White M blocks — bold, tile-filling, right leg shorter (as reference)."""
    # ---- left leg with 3 rising chart bars (vivid on white)
    lb = (LX0, M_TOP_Y, LX1, M_BOTTOM)
    lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    mask = rounded_mask((lw, lh), 20)
    grad = vgrad(lw, lh, M_TOP, M_BOT)
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

    # ---- right leg with blue circuit nodes + EGP circuit badge
    rb = (RX0, 330, RX1, M_BOTTOM)
    rw, rh = rb[2] - rb[0], rb[3] - rb[1]
    mask = rounded_mask((rw, rh), 20)
    grad = vgrad(rw, rh, M_TOP, M_BOT)
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

    # EGP circuit badge near the foot of the right leg
    badge_r = 108
    bx, by = 130, rh - 128
    cd.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
               fill=BADGE_BG, outline=BADGE_FG, width=12)
    egp_strokes(circ, bx, by)
    grad.alpha_composite(circ)
    layer.paste(grad, (rb[0], rb[1]), mask)

    # badge connection node + stem bridging to the left leg
    d = ImageDraw.Draw(layer)
    anchor = (rb[0] + 130, M_BOTTOM - 128)
    stem_end = (LX1 + 4, M_BOTTOM - 128)
    grad_polyline(d, [anchor, (LX1 + 30, M_BOTTOM - 128), stem_end],
                  [(0.0, BADGE_FG), (1.0, BADGE_FG)], 10)
    dot(d, anchor, 12, BADGE_FG)
    dot(d, stem_end, 10, BADGE_FG)


def draw_ribbon(layer):
    """Thick gradient ribbon sweeping the WHOLE tile bottom-left → top-right,
    with the doubled green stroke under its first diagonal and a large
    arrowhead — matching the reference."""
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


def draw_sparkles(layer):
    """4-point twinkles sprinkled in the empty corners — the lively touch."""
    d = ImageDraw.Draw(layer)
    for (x, y, r, c) in [
        (330, 76, 34, SPARKLE_A),
        (505, 208, 22, SPARKLE_B),
        (978, 336, 27, SPARKLE_A),
        (748, 946, 30, SPARKLE_A),
        (90, 470, 20, SPARKLE_B),
    ]:
        sparkle(d, x, y, r, c)


def render(with_tile=True, art_scale=1.0):
    """Full composition. `art_scale` shrinks the mark (adaptive safe zone)."""
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = dgrad(S, S, TILE_STOPS)
    if with_tile:
        mask = rounded_mask((S, S), 232)
        base.paste(grad, (0, 0), mask)
        ImageDraw.Draw(base).rounded_rectangle(
            [20, 20, S - 20, S - 20], radius=232, outline=(255, 255, 255, 70), width=4)
    else:
        base.paste(grad, (0, 0))

    # glows follow the artwork when it is scaled (arrow tip + ribbon start)
    k = art_scale

    def about(p):
        return (S / 2 + (p[0] - S / 2) * k, S / 2 + (p[1] - S / 2) * k)

    base.alpha_composite(glow((S, S), about((935, 95)), 300 * k, (255, 255, 255), 95))
    base.alpha_composite(glow((S, S), about((150, 900)), 260 * k, (120, 240, 255), 70))

    # artwork (M + ribbon + sparkles), scaled into the safe zone when needed
    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_blocks(art)
    draw_ribbon(art)
    draw_sparkles(art)
    if art_scale != 1.0:
        w = int(S * art_scale)
        art = art.resize((w, w), Image.LANCZOS)
    base.alpha_composite(art, ((S - art.width) // 2, (S - art.height) // 2))
    return base


def main():
    render(with_tile=True, art_scale=1.0).save("icon.png")
    # adaptive foreground: gradient baked in + artwork inside the 66% circle
    render(with_tile=False, art_scale=0.57).save("icon_foreground.png")
    print("icon.png + icon_foreground.png generated (v2 lively refresh)")


if __name__ == "__main__":
    main()
