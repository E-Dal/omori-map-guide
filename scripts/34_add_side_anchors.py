#!/usr/bin/env python3
"""Add route-snap anchors on the left and right edge of a map.

The stitcher can only snap a route dot to a point some edge's FROM side sits
on. FROZEN FOREST (II) and (VII) are open forest: they run into their
neighbours along the whole of their left and right sides, with no door event
anywhere near either edge — every exit they do have is interior — so the sides
had nothing to snap to at all.

One anchor per side is enough. An anchor whose hitbox is vertical (T/B set)
tells computeSnapTargets() to pin the X and let the Y slide, so a single
anchor on x=0 covers the entire left edge, and one on x=width-1 the entire
right edge.

    python3 scripts/34_add_side_anchors.py <region> <mapId> [<mapId> ...]

Re-running is safe: anchors this script wrote before are dropped and rebuilt.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WEST_EV, EAST_EV = 901, 902
WEST_NAME, EAST_NAME = 'Side anchor (west)', 'Side anchor (east)'
KIND = 'anchor'


def main(argv):
    if len(argv) < 2:
        sys.exit('Usage: python3 scripts/34_add_side_anchors.py <region> <mapId> [<mapId> ...]')
    region, map_ids = argv[0], [str(int(m)) for m in argv[1:]]

    maps_path = ROOT / 'data' / f'{region}_maps.json'
    edges_path = ROOT / 'data' / f'{region}_edges.json'
    meta = json.loads(maps_path.read_text())
    edges = json.loads(edges_path.read_text())
    internal = edges.get('internal', [])

    # Drop anything this script added before, so a re-run cannot stack up.
    internal = [e for e in internal
                if not (e.get('kind') == KIND and e['from'].get('evId') in (WEST_EV, EAST_EV))]

    added = 0
    for map_id in map_ids:
        m = meta.get(map_id)
        if not m:
            print(f'  map{map_id}: not in {region}_maps.json — skipped')
            continue
        mid_y = m['height'] // 2
        for ev_id, name, x in ((WEST_EV, WEST_NAME, 0),
                               (EAST_EV, EAST_NAME, m['width'] - 1)):
            internal.append({
                # A vertical hitbox is the whole point: it makes the snap pin X
                # and leave Y free, so this one point stands for the whole side.
                'from': {'mapId': int(map_id), 'evId': ev_id, 'evName': name,
                         'x': x, 'y': mid_y,
                         'hitbox': {'L': 0, 'R': 0, 'T': 1, 'B': 1}},
                'to': {'mapId': int(map_id), 'x': x, 'y': mid_y},
                'kind': KIND,
            })
            added += 1
            print(f'  map{map_id} {m["name"]}: {name} at ({x}, {mid_y})')

    edges['internal'] = internal
    edges_path.write_text(json.dumps(edges, indent=2))
    print(f'\n{region}: {added} side anchor(s) written to {edges_path.name}')


if __name__ == '__main__':
    main(sys.argv[1:])
