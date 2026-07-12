# Mountain Side — build tools

The figures in the game are the real drawings from `../mountain_side.pdf`, cropped
from the scans with the white paper made transparent (never redrawn — the design
sheet says "keep the figures as they are"!).

## Regenerating `../assets.js`

Needs `pdftoppm` (poppler, `brew install poppler`) and Python with Pillow:

```sh
python3 -m venv .venv && .venv/bin/pip install Pillow
.venv/bin/python extract_figures.py
```

This rasterizes the PDF pages into `build/`, cuts out every figure listed in the
`MANIFEST` dict (crop rectangles are in 1160x824 scan pixels), keys out the paper
via a border flood-fill, and writes:

- `../assets.js` — the data-URI sprite sheet the game loads
- `build/sprites/*.png` — individual sprites for inspection
- `build/contact-sheet.png` — all sprites on green, for spotting bad crops

To fix a crop, tweak its rectangle/threshold in `MANIFEST` and re-run.

## three.min.js

`../three.min.js` is Three.js **r160** (the last release with the classic
non-module build), vendored so the game works offline and from `file://`:

```sh
curl -o ../three.min.js https://unpkg.com/three@0.160.0/build/three.min.js
```
