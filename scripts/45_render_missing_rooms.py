#!/usr/bin/env python3
"""Draw rooms into a render that arrived without them.

goats.dev's renders are tile renders. A room OMORI draws with a *parallax* —
the image the engine tiles underneath the tile layers — therefore comes out
empty, and if nothing else in that room is a tile, the render has a hole where
the room is and no sign that anything is missing.

SWEETHEART DUNGEON 2 and 3 each hide one that way. The red dais at map435
(41, 57) starts ev6, named 'Heaven and Hell' in the game's own data, which
walks you through a dark red corridor at the bottom of map435 and then a white
one in map438. Both are parallax; both were absent from the render; neither had
a slice cut for it. The atlas had no trace of either until someone reported two
missing maps.

13_render_tiled_map.py can draw them, because it reads the game's own data and
tiles the parallax underneath — but it tiles it across the *whole* canvas, so
its output is opaque everywhere and cannot replace a render whose transparency
is what keeps the rooms apart. 18_trim_black_bg.py would clear the surplus, and
it clears these rooms with it: HELL is dark enough to read as backdrop.

So only the named rectangles are taken, and only where the render is empty.
Where both have pixels the render wins, which makes this safe to re-run and
safe to point at a room that is half there.

    python3 scripts/45_render_missing_rooms.py --dry-run
    python3 scripts/45_render_missing_rooms.py
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from _img import save  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
RAW = ROOT / 'data' / 'raw_pngs'
TILE = 32

# (mapId, col0, row0, col1, row1, what it is). Inclusive tile bounds, taken
# from where the self-render has light in it — see the module docstring.
ROOMS = [
    (435, 7, 76, 53, 83, "HELL — 'Heaven and Hell' first stop"),
    (438, 7, 30, 53, 38, "HEAVEN — 'Heaven and Hell' second stop"),
]


def rendered(map_id, cache={}):
    """map_id drawn from the game's own data, parallax and all."""
    if map_id not in cache:
        g = {'__name__': 'imported',
             '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
        exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(),
                     'r13', 'exec'), g)
        scratch = ROOT / 'data' / 'raw_pngs' / '.render-cache'
        scratch.mkdir(exist_ok=True)
        g['OUT_DIR'] = scratch
        g['render_map'](map_id)
        out = next(scratch.glob(f'map{map_id}.*'))
        cache[map_id] = Image.open(out).convert('RGBA').copy()
        out.unlink()
    return cache[map_id]


def main(argv):
    dry = '--dry-run' in argv
    for map_id, c0, r0, c1, r1, what in ROOMS:
        target = next(iter(RAW.glob(f'map{map_id}.*')), None)
        if target is None:
            print(f'  ⚠ no render for map{map_id}', file=sys.stderr)
            continue
        dst = Image.open(target).convert('RGBA')
        box = (c0 * TILE, r0 * TILE, (c1 + 1) * TILE, (r1 + 1) * TILE)
        room = rendered(map_id).crop(box)

        cur = np.asarray(dst.crop(box))
        empty = cur[:, :, 3] <= 8
        add = int((empty & (np.asarray(room)[:, :, 3] > 8)).sum())
        print(f'  map{map_id} cols {c0}-{c1} rows {r0}-{r1}: '
              f'{100 * empty.mean():.0f}% of that rectangle is empty, '
              f'{add} pixel(s) to draw   [{what}]')
        if dry or not add:
            continue
        # Under, not over: anything the render already has is the render's.
        patch = dst.crop(box)
        room = room.copy()
        room.alpha_composite(patch)
        dst.paste(room, box)
        save(dst, target)
        print(f'    ✓ {target.name}')

    cache_dir = RAW / '.render-cache'
    if cache_dir.exists() and not any(cache_dir.iterdir()):
        cache_dir.rmdir()
    if dry:
        print('\n[dry run]')


if __name__ == '__main__':
    main(sys.argv[1:])
