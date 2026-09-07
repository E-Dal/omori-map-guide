#!/usr/bin/env python3
"""Repaint chosen tiles of a map PNG from a fresh tile-layer render.

The goats.dev renders bake event sprites in, which is usually what we want —
furniture and NPCs are events in OMORI. But some of those events are editor
debug markers: the DEV_TEST sheet is full of labelled boxes ("1", "2",
"CAM EVENT", "MAP TELE") and they show up as flat squares sitting on the floor.

Re-rendering the whole map would strip the real furniture with them. This
repaints only the named tiles, taking their pixels from a tiles-only render of
the same map, so the floor underneath comes back and nothing else moves.

    python3 scripts/19_repaint_tiles.py 193 52,52
    python3 scripts/19_repaint_tiles.py 193 52,52 118,28-119,29
    python3 scripts/19_repaint_tiles.py 193 52,52 --dry-run --backup DIR

A tile is left alone if the fresh render has nothing there — that would punch a
hole rather than clean anything up.
"""
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TILE = 32

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)


def parse_rect(spec):
    """'x,y' or 'x0,y0-x1,y1' (inclusive) → (x0, y0, x1, y1)."""
    if '-' in spec:
        a, b = spec.split('-', 1)
        x0, y0 = (int(v) for v in a.split(','))
        x1, y1 = (int(v) for v in b.split(','))
    else:
        x0, y0 = (int(v) for v in spec.split(','))
        x1, y1 = x0, y0
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    if dry:
        args.remove('--dry-run')
    backup_dir = None
    if '--backup' in args:
        i = args.index('--backup')
        backup_dir = Path(args[i + 1]); backup_dir.mkdir(parents=True, exist_ok=True)
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    map_id = int(args[0])
    rects = [parse_rect(a) for a in args[1:]]
    target = ROOT / 'data' / 'raw_pngs' / f'map{map_id}.png'
    if not target.exists():
        raise SystemExit(f'Missing {target}')

    scratch = Path(tempfile.mkdtemp(prefix='repaint-'))
    _r13['OUT_DIR'] = scratch
    _r13['render_map'](map_id)
    fresh_path = scratch / f'map{map_id}.png'
    if not fresh_path.exists():
        raise SystemExit(f'Could not render map{map_id} (no .AUBREY?)')

    canvas = Image.open(target).convert('RGBA')
    fresh = Image.open(fresh_path).convert('RGBA')
    fresh_path.unlink(); scratch.rmdir()
    if canvas.size != fresh.size:
        raise SystemExit(f'Size mismatch: {canvas.size} vs {fresh.size}')

    arr, und = np.array(canvas), np.array(fresh)
    painted = skipped = 0
    for x0, y0, x1, y1 in rects:
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                sy, sx = slice(ty * TILE, (ty + 1) * TILE), slice(tx * TILE, (tx + 1) * TILE)
                if sy.stop > arr.shape[0] or sx.stop > arr.shape[1]:
                    print(f'  !! tile ({tx},{ty}) is off the map', file=sys.stderr)
                    continue
                src = und[sy, sx]
                if not (src[:, :, 3] > 0).any():
                    print(f'  · tile ({tx},{ty}) left alone — tile render is empty there')
                    skipped += 1
                    continue
                changed = int((np.abs(arr[sy, sx].astype(int) - src.astype(int)).sum(axis=2) > 20).sum())
                arr[sy, sx] = src
                painted += 1
                print(f'  + tile ({tx},{ty}) repainted ({changed}/1024 px changed)')

    print(f'\nmap{map_id}: {painted} tile(s) repainted, {skipped} left alone'
          + (' [dry run]' if dry else ''))
    if not dry and painted:
        if backup_dir:
            shutil.copy2(target, backup_dir / target.name)
        Image.fromarray(arr).save(target)


if __name__ == '__main__':
    main()
