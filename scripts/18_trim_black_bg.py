#!/usr/bin/env python3
"""Make a map's black backdrop transparent.

Some renders arrive with the area around the map painted opaque black instead
of left transparent. On its own that is invisible; in the stitcher it is a
black slab that hides whatever it overlaps, and once regions are laid on top of
each other that slab covers real map.

Only black that the outside can reach is cleared. A flood fill starts from the
image border and spreads through near-black pixels, so shadows and dark art
enclosed by the map — TRENCH's navy spires, unlit interiors — keep their pixels
even though they are the same colour as the backdrop.

    python3 scripts/18_trim_black_bg.py 212 216
    python3 scripts/18_trim_black_bg.py 212 --threshold 40 --dry-run
    python3 scripts/18_trim_black_bg.py 212 --backup DIR
"""
import shutil
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_THRESHOLD = 30       # max R+G+B still counted as backdrop black


def clear_border_black(img, threshold):
    """Return (new image, pixels cleared)."""
    a = np.array(img.convert('RGBA'))
    h, w = a.shape[:2]
    black = (a[:, :, :3].astype(int).sum(axis=2) <= threshold) & (a[:, :, 3] > 0)

    seen = np.zeros((h, w), bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if black[y, x] and not seen[y, x]:
                seen[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if black[y, x] and not seen[y, x]:
                seen[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and black[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))

    a[seen] = (0, 0, 0, 0)
    return Image.fromarray(a), int(seen.sum())


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    if dry:
        args.remove('--dry-run')
    threshold = DEFAULT_THRESHOLD
    backup_dir = None
    if '--threshold' in args:
        i = args.index('--threshold')
        threshold = int(args[i + 1]); del args[i:i + 2]
    if '--backup' in args:
        i = args.index('--backup')
        backup_dir = Path(args[i + 1]); backup_dir.mkdir(parents=True, exist_ok=True)
        del args[i:i + 2]
    if not args:
        print(__doc__)
        sys.exit(1)

    pngs = ROOT / 'data' / 'raw_pngs'
    for arg in args:
        p = pngs / f'map{int(arg)}.png'
        if not p.exists():
            print(f'  !! {p.name} not found', file=sys.stderr)
            continue
        img = Image.open(p).convert('RGBA')
        before_opaque = int((np.array(img)[:, :, 3] > 0).sum())
        out, cleared = clear_border_black(img, threshold)
        pct = 100 * cleared / (img.width * img.height)
        print(f'  map{int(arg)}: cleared {cleared} px ({pct:.1f}% of canvas), '
              f'{before_opaque - cleared} opaque px remain'
              + (' [dry run]' if dry else ''))
        if not dry:
            if backup_dir:
                shutil.copy2(p, backup_dir / p.name)
            out.save(p)


if __name__ == '__main__':
    main()
