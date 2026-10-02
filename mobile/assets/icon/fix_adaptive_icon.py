#!/usr/bin/env python3
"""Fix the Android adaptive-icon foreground.

Problem: assets/icon/icon_foreground.png was 497x502 (non-square, tiny) so
the launcher stretched/blurred it on the home screen ("الأيقونة مشوّهة").

Fix: rebuild a 1024x1024 RGBA foreground from the sharp source artwork
(icon.png, 1536x1536) scaled into the adaptive-icon safe zone (~70% of the
canvas, centred) with transparent padding — flutter_launcher_icons composites
it over the white adaptive background.

Usage:  python3 fix_adaptive_icon.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
CANVAS = 1024
SAFE = 0.70  # fraction of the canvas the artwork may occupy (safe zone)

src = Image.open(HERE / "icon.png").convert("RGBA")
target = int(CANVAS * SAFE)
# Centre-crop to square first (never stretch), then scale down sharply.
w, h = src.size
side = min(w, h)
src = src.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
src = src.resize((target, target), Image.LANCZOS)

canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
offset = (CANVAS - target) // 2
canvas.paste(src, (offset, offset), src)
canvas.save(HERE / "icon_foreground.png")

# Also normalise the legacy/source icon to a clean 1024 square.
Image.open(HERE / "icon.png").convert("RGB").resize((1024, 1024), Image.LANCZOS).save(
    HERE / "icon.png"
)
print("OK: icon_foreground.png 1024x1024 (safe-zone", int(SAFE * 100), "%), icon.png 1024x1024")
