#!/usr/bin/env python3
"""Extract the hand-drawn figures from mountain_side.pdf as transparent PNG sprites.

The figures must stay EXACTLY as drawn (design doc p.5: "keep the figures as
they are on the sheet") — this script only crops the scans and turns the white
paper around each figure transparent. It never redraws anything.

Pipeline:
  1. `pdftoppm -scale-to-x 1160 -scale-to-y 824` renders each page at the
     embedded scan's native resolution, so MANIFEST rects are in scan pixels.
  2. Crop each rect, flood-fill "near-white paper" inward from the crop border
     to build a paper mask (white INSIDE a figure — eyes, teeth — is kept).
  3. Feather the mask edge, trim to content, downscale, save PNG.
  4. Emit ../assets.js (data URIs) and build/contact-sheet.png for QA.

Usage:  <venv-with-Pillow>/bin/python tools/extract_figures.py
"""

import base64
import io
import subprocess
import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
GAME_DIR = HERE.parent
PDF = GAME_DIR / "mountain_side.pdf"
BUILD = HERE / "build"
SPRITES = BUILD / "sprites"
ASSETS_JS = GAME_DIR / "assets.js"

PAGE_W, PAGE_H = 1160, 824

# name: (page, (x, y, w, h), max_px, paper_threshold)
# paper_threshold: min luminance considered "paper" for the flood fill.
# Faint pencil figures need a higher threshold so light strokes survive.
MANIFEST = {
    # page 1 — goodies, weapons, villains, medkit, scenery
    "title":      (1, (8, 6, 470, 92), 512, 215),
    "sanc":       (1, (168, 88, 116, 122), 256, 195),
    "mutian":     (1, (8, 208, 114, 120), 256, 195),
    "tantion":    (1, (127, 222, 108, 122), 256, 195),
    "denzone":    (1, (242, 288, 122, 64), 256, 195),
    "sword":      (1, (390, 196, 76, 84), 256, 195),
    "shield":     (1, (566, 250, 74, 74), 256, 195),
    "slingshot":  (1, (420, 346, 66, 62), 256, 195),
    "bow":        (1, (483, 322, 115, 120), 256, 200),
    "follower":   (1, (18, 558, 104, 172), 256, 210),
    "boss":       (1, (176, 582, 160, 205), 384, 195),
    "medkit":     (1, (1088, 366, 40, 44), 256, 195),
    "scenery":    (1, (655, 210, 305, 580), 512, 195),
    # page 2 — clean group drawing for select/win screens (faint pencil)
    "group":      (2, (795, 78, 350, 300), 512, 232),
    # page 3 — bota-block
    "botablock":  (3, (793, 524, 56, 70), 256, 195),
    # page 4 — HQ tent, snack
    "tent":       (4, (598, 82, 556, 730), 512, 195),
    "snack":      (4, (300, 510, 56, 72), 256, 215),
    # page 5 — jinky, plane
    "jinky":      (5, (14, 30, 98, 104), 256, 195),
    "plane":      (5, (688, 186, 80, 108), 256, 200),
    # page 6 — riddler, pyramid, mummies
    "riddler":    (6, (45, 127, 352, 128), 384, 195),
    "pyramid":    (6, (580, 118, 365, 320), 512, 195),
    "mummy1":     (6, (628, 465, 178, 352), 320, 215),
    "mummy2":     (6, (902, 395, 190, 330), 320, 215),
}


def rasterize_pages():
    if not all((BUILD / f"page-{p}.png").exists() for p in range(1, 7)):
        BUILD.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["pdftoppm", "-scale-to-x", str(PAGE_W), "-scale-to-y", str(PAGE_H),
             "-png", str(PDF), str(BUILD / "page")],
            check=True,
        )
    return {p: Image.open(BUILD / f"page-{p}.png").convert("RGB") for p in range(1, 7)}


def is_paper(px, thresh):
    r, g, b = px
    lum = (r * 299 + g * 587 + b * 114) // 1000
    return lum >= thresh and (max(r, g, b) - min(r, g, b)) < 48


def key_paper(img, thresh):
    """Flood-fill paper from the borders; return RGBA with paper transparent."""
    w, h = img.size
    px = img.load()
    paper = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            q.append((x, y))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if paper[i] or not is_paper(px[x, y], thresh):
            continue
        paper[i] = 1
        if x > 0: q.append((x - 1, y))
        if x < w - 1: q.append((x + 1, y))
        if y > 0: q.append((x, y - 1))
        if y < h - 1: q.append((x, y + 1))

    alpha = Image.frombytes("L", (w, h), bytes(255 - p * 255 for p in paper))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.7))  # feather the cut edge
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def trim_and_scale(img, max_px):
    bbox = img.getchannel("A").getbbox()
    if bbox:
        x0, y0, x1, y1 = bbox
        img = img.crop((max(0, x0 - 2), max(0, y0 - 2),
                        min(img.width, x1 + 2), min(img.height, y1 + 2)))
    if max(img.size) > max_px:
        s = max_px / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)),
                         Image.LANCZOS)
    return img


def main():
    pages = rasterize_pages()
    SPRITES.mkdir(parents=True, exist_ok=True)
    entries, sheet_cells = [], []

    for name, (page, (x, y, w, h), max_px, thresh) in MANIFEST.items():
        crop = pages[page].crop((x, y, x + w, y + h))
        sprite = trim_and_scale(key_paper(crop, thresh), max_px)
        sprite.save(SPRITES / f"{name}.png", optimize=True)
        buf = io.BytesIO()
        sprite.save(buf, "PNG", optimize=True)
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        entries.append(f'  {name}: "{uri}"')
        sheet_cells.append((name, sprite))
        print(f"{name:12s} {sprite.width:4d}x{sprite.height:<4d} {len(uri)//1024:4d} KB")

    ASSETS_JS.write_text(
        "// GENERATED by tools/extract_figures.py — do not edit by hand.\n"
        "// Sprites are unmodified crops of the drawings in mountain_side.pdf.\n"
        "const ASSETS = {\n" + ",\n".join(entries) + "\n};\n"
    )
    print(f"\nwrote {ASSETS_JS} ({ASSETS_JS.stat().st_size // 1024} KB)")

    # contact sheet on saturated green so leftover paper / over-keying shows up
    cell = 200
    cols = 6
    rows = (len(sheet_cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 18)), (60, 170, 90))
    for i, (name, sp) in enumerate(sheet_cells):
        s = min((cell - 8) / sp.width, (cell - 8) / sp.height, 1.0)
        thumb = sp.resize((max(1, round(sp.width * s)), max(1, round(sp.height * s))),
                          Image.LANCZOS)
        cx, cy = (i % cols) * cell, (i // cols) * (cell + 18)
        sheet.paste(thumb, (cx + (cell - thumb.width) // 2,
                            cy + (cell - thumb.height) // 2), thumb)
    sheet.save(BUILD / "contact-sheet.png")
    print(f"wrote {BUILD / 'contact-sheet.png'}")


if __name__ == "__main__":
    sys.exit(main())
