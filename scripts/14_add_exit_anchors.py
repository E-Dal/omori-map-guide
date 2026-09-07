#!/usr/bin/env python3
"""Add route-snap anchors on the bottom exit of each sliced sub-map.

Sliced rooms (`subMaps` in 01_extract_adjacency.js, cut by 05_cut_submaps.py)
usually hang off a corridor via a narrow path stub at the bottom — the doorway
the player walks out through. The stitcher can only snap a route to a point
that some edge's FROM side sits on, and most of these stubs carry no event at
all, so there was nothing to snap to and routes could not be attached to the
room's actual exit.

This measures each sub-map's PNG and appends a synthetic anchor edge on the
stub. Runs after 01 (which rewrites edges.json) and 05 (which cuts the PNGs):

    node scripts/01_extract_adjacency.js <region>
    python3 scripts/05_cut_submaps.py     <region>
    python3 scripts/14_add_exit_anchors.py <region>

Re-running is safe: previously added anchors are dropped and recomputed.

A bottom stub is only recognised when the last content row is a sharp
narrowing of the room — 3 tiles or fewer in a room at least 6 wide, or under
40% of the widest row. Rooms that merely taper to a rounded bottom wall
(IGLOO INTERIOR top-L, SWEETHEART DUNGEON 3) are not exits and are left alone.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

T = 32                    # tile size in px
KIND = 'exitStem'         # marks our edges so a re-run can replace them
EV_ID = 900
EV_NAME = 'Exit stem (south)'


def tile_mask(png_path):
    """Per-tile 'has visible content' grid. The maps paint an opaque black
    backdrop behind everything, so alpha alone would mark the whole canvas as
    content — threshold on brightness instead."""
    im = Image.open(png_path).convert('RGBA')
    a = np.array(im)
    content = (a[:, :, 3] > 0) & (a[:, :, :3].astype(int).sum(axis=2) > 30)
    th, tw = im.size[1] // T, im.size[0] // T
    return content[:th * T, :tw * T].reshape(th, T, tw, T).any(axis=(1, 3)), tw, th


def bottom_stem(png_path):
    """Return (x, y) tile of the bottom exit stub's centre, or None."""
    tiles, tw, th = tile_mask(png_path)
    rows = [y for y in range(th) if tiles[y].any()]
    if not rows:
        return None
    last = rows[-1]
    cols = [x for x in range(tw) if tiles[last, x]]
    widest = max(int(tiles[y].sum()) for y in rows)
    if not ((len(cols) <= 3 and widest >= 6) or len(cols) <= 0.4 * widest):
        return None
    return cols[len(cols) // 2], last


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/14_add_exit_anchors.py <region>", file=sys.stderr)
        sys.exit(1)
    region = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    meta_path = root / 'data' / f'{region}_maps.json'
    edges_path = root / 'data' / f'{region}_edges.json'
    pngs = root / 'data' / 'raw_pngs'
    for p in (meta_path, edges_path):
        if not p.exists():
            print(f"Missing {p}. Run: node scripts/01_extract_adjacency.js {region}",
                  file=sys.stderr)
            sys.exit(1)

    meta = json.loads(meta_path.read_text())
    edges = json.loads(edges_path.read_text())
    internal = [e for e in edges.get('internal', []) if e.get('kind') != KIND]

    n_added = n_covered = 0
    for map_id, m in sorted(meta.items(), key=lambda kv: int(kv[0])):
        if not m.get('polygon'):
            continue
        png = pngs / (m.get('image') or f'map{map_id}.png')
        if not png.exists():
            print(f"!! Missing {png.name} for map{map_id}, skipping", file=sys.stderr)
            continue
        stem = bottom_stem(png)
        if stem is None:
            continue
        sx, sy = stem

        # Already snappable? Any edge starting on the stub row does the job.
        if any(str(e['from']['mapId']) == map_id
               and e['from']['y'] >= sy - 1
               and e['from']['x'] == sx
               for e in internal):
            n_covered += 1
            continue

        internal.append({
            'from': {'mapId': int(map_id), 'evId': EV_ID, 'evName': EV_NAME,
                     'x': sx, 'y': sy, 'hitbox': {'L': 0, 'R': 0, 'T': 0, 'B': 1}},
            'to': {'mapId': int(map_id), 'x': sx, 'y': sy},
            'kind': KIND,
        })
        print(f"  anchor map{map_id} at ({sx},{sy})  {m['name']}")
        n_added += 1

    edges['internal'] = internal
    edges_path.write_text(json.dumps(edges, indent=2))
    print(f"\n{region}: added {n_added} exit anchor(s), "
          f"{n_covered} sub-map(s) already had one.")


if __name__ == '__main__':
    main()
