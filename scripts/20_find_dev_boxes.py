#!/usr/bin/env python3
"""Find painted-on map content that no event accounts for.

goats.dev renders event sprites into its map images. Usually that is wanted —
furniture and NPCs are events in OMORI. Sometimes it drops an editor debug
marker on the floor instead: the DEV_TEST sheet is a block of labelled squares
("1", "MAP TELE", "CAM EVENT") used as placeholder art for invisible triggers.

Matching those squares by their pixels does not work. The "1" square in HOTEL
ROOMS is alpha-blended into the carpet — its two main colours are half-strength
versions of the floor and only six pixels of the white "1" survive — so it is
not a byte-for-byte copy of any frame, and its shape matches the real frame no
better than chance. Searching the event tables fails too: the tile it sits on,
(52,52), holds no event at all.

So work backwards. Render the tile layers, diff against the shipped PNG, and
every difference is something drawn over the tiles. Group those into blobs and
throw away the ones an event stands under — what remains is unexplained, and
that is where the debug junk lives.

    python3 scripts/20_find_dev_boxes.py --out report.json
    python3 scripts/20_find_dev_boxes.py 193 134

Repaint anything it finds with 19_repaint_tiles.py.
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
TILE = 32
DIFF_THRESHOLD = 20      # per-pixel channel-sum delta that counts as painted on
MAX_BLOB_TILES = 6       # bigger blobs are scenery, not a marker
MIN_BLOB_PIXELS = 150    # smaller ones are anti-aliasing noise along an edge

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)


def events_of(map_id):
    p = DECRYPTED / f'Map{map_id:03d}.json'
    if not p.exists():
        return []
    return [e for e in (json.loads(p.read_text()).get('events') or []) if e]


def region_of_maps():
    out = {}
    for f in sorted((ROOT / 'data').glob('*_maps.json')):
        region = f.name[:-len('_maps.json')]
        for map_id in json.loads(f.read_text()):
            out.setdefault(map_id, region)
    return out


def blobs(tiles):
    """8-connected groups of True tiles → list of (x0, y0, x1, y1, cells)."""
    th, tw = tiles.shape
    seen = np.zeros_like(tiles)
    out = []
    for y in range(th):
        for x in range(tw):
            if not tiles[y, x] or seen[y, x]:
                continue
            stack, cells = [(y, x)], []
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < th and 0 <= nx < tw and tiles[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            ys = [c[0] for c in cells]
            xs = [c[1] for c in cells]
            out.append((min(xs), min(ys), max(xs), max(ys), cells))
    return out


def main():
    args = sys.argv[1:]
    out_path = None
    if '--out' in args:
        i = args.index('--out')
        out_path = Path(args[i + 1]); del args[i:i + 2]

    regions = region_of_maps()
    ids = [int(a) for a in args] if args else sorted(int(i) for i in regions if i.isdigit())
    pngs = ROOT / 'data' / 'raw_pngs'
    scratch = Path(tempfile.mkdtemp(prefix='dev-boxes-'))
    _r13['OUT_DIR'] = scratch

    report = []
    for map_id in ids:
        shipped = pngs / f'map{map_id}.png'
        if not shipped.exists() or not (_r13['MAPS_DIR'] / f'map{map_id}.AUBREY').exists():
            continue
        try:
            _r13['render_map'](map_id)
        except Exception as exc:                       # noqa: BLE001
            print(f'  !! map{map_id} render failed: {exc}', file=sys.stderr)
            continue
        fresh_path = scratch / f'map{map_id}.png'
        if not fresh_path.exists():
            continue
        a = Image.open(shipped).convert('RGBA')
        b = Image.open(fresh_path).convert('RGBA')
        fresh_path.unlink()
        if a.size != b.size:
            continue

        na, nb = np.array(a).astype(int), np.array(b).astype(int)
        # Compare only where both renders have something. They disagree about
        # the backdrop — one leaves it transparent, the other fills it with the
        # map's black void — and that disagreement would otherwise swamp every
        # real difference.
        both = (na[:, :, 3] > 0) & (nb[:, :, 3] > 0)
        diff = (np.abs(na - nb).sum(axis=2) > DIFF_THRESHOLD) & both
        if not diff.any():
            continue
        th, tw = diff.shape[0] // TILE, diff.shape[1] // TILE
        tiles = diff[:th * TILE, :tw * TILE].reshape(th, TILE, tw, TILE).any(axis=(1, 3))

        evs = events_of(map_id)
        unexplained = []
        for x0, y0, x1, y1, cells in blobs(tiles):
            if len(cells) > MAX_BLOB_TILES:
                continue
            px = int(sum(diff[cy * TILE:(cy + 1) * TILE, cx * TILE:(cx + 1) * TILE].sum()
                         for cy, cx in cells))
            if px < MIN_BLOB_PIXELS:
                continue
            # A sprite hangs upward from its event's tile, so an event explains
            # a blob sitting on or just above it.
            if any(x0 - 1 <= e['x'] <= x1 + 1 and y0 <= e['y'] <= y1 + 2 for e in evs):
                continue
            unexplained.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                                'tiles': len(cells), 'pixels': px})
        if unexplained:
            report.append({'mapId': map_id, 'region': regions.get(str(map_id)),
                           'blobs': unexplained})
            where = ', '.join(f"({b['x0']},{b['y0']})" if b['x0'] == b['x1'] and b['y0'] == b['y1']
                              else f"({b['x0']},{b['y0']})-({b['x1']},{b['y1']})"
                              for b in unexplained[:8])
            print(f"  map{map_id} [{regions.get(str(map_id))}] — {len(unexplained)}: {where}"
                  + (' …' if len(unexplained) > 8 else ''))

    scratch.rmdir()
    total = sum(len(r['blobs']) for r in report)
    print(f'\n{total} unexplained blob(s) across {len(report)} map(s).')
    if out_path:
        out_path.write_text(json.dumps(report, indent=2))
        print(f'Wrote {out_path}')


if __name__ == '__main__':
    main()
