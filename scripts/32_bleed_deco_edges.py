#!/usr/bin/env python3
"""Bleed each decoration sprite's edge colour into its transparent pixels.

The sprites were cut out of map renders, so every pixel outside the artwork
came out fully transparent *black* — alpha 0, RGB (0, 0, 0). At 1:1 that is
invisible and nothing is wrong with them. It stops being invisible the moment
anything samples the image at a fractional scale: GPU compositing filters the
texture in non-premultiplied space, so a screen pixel near the edge of a tree
mixes the canopy colour with the black sitting in those "empty" texels and the
tree comes out wearing a black outline. Zoom to 1:1 and the outline disappears,
because at 1:1 nothing is being filtered — which is exactly the symptom.

The fix is the standard one for texture bleeding: keep alpha exactly as it is
and give the transparent pixels the colour of the nearest opaque pixel, so
there is no black left to bleed. Nothing visible changes; only what the filter
finds when it reaches past the edge.

Idempotent — running it twice is a no-op.
"""
import sys
from pathlib import Path

from PIL import Image

DECO_DIR = Path(__file__).resolve().parent.parent / 'web' / 'assets' / 'decorations'


def bleed(im):
    """Nearest-opaque-neighbour flood into transparent pixels. Alpha untouched."""
    im = im.convert('RGBA')
    w, h = im.size
    px = im.load()
    # Seed the frontier with every opaque pixel; walk outwards one ring at a
    # time, and the first ring to reach a transparent pixel owns its colour.
    known = [[px[x, y][3] > 0 for x in range(w)] for y in range(h)]
    frontier = [(x, y) for y in range(h) for x in range(w) if known[y][x]]
    if not frontier:
        return im, 0
    filled = 0
    while frontier:
        nxt = []
        for x, y in frontier:
            r, g, b, _ = px[x, y]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and not known[ny][nx]:
                    known[ny][nx] = True
                    px[nx, ny] = (r, g, b, 0)   # colour only — still invisible
                    nxt.append((nx, ny))
                    filled += 1
        frontier = nxt
    return im, filled


def main(argv):
    files = sorted(DECO_DIR.glob('*.png'))
    if not files:
        sys.exit(f'no decoration PNGs under {DECO_DIR}')
    for f in files:
        im = Image.open(f)
        before = sum(1 for p in im.convert('RGBA').getdata()
                     if p[3] == 0 and p[:3] == (0, 0, 0))
        out, filled = bleed(im)
        out.save(f)
        after = sum(1 for p in out.getdata() if p[3] == 0 and p[:3] == (0, 0, 0))
        print(f'{f.name:16} recoloured {filled:5} transparent px · '
              f'transparent-black {before} -> {after}')


if __name__ == '__main__':
    main(sys.argv[1:])
