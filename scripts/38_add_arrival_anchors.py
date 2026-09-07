#!/usr/bin/env python3
"""Put a snap anchor on a tile the game sends you to but never sends you from.

The stitcher can only snap a route dot to a point some edge's FROM side sits on,
and FROM sides come from transfer events. A room you are *dropped into* by a
transfer somewhere else, with no way out of its own, therefore has nothing to
grab: the route can attach at the departure end and hangs loose at the arrival
end.

SWEETHEART DUNGEON 1's top-left cell is the case that prompted this. Twelve
`dressmole` events stand in it and not one of them is a transfer, so map182 has
six snap points and none of them is in that room — but map171 ev76
"Sweetheart's Quest For Heartsz" sends you straight to (7, 8), right into it.
The anchor goes on the tile you land on, which is the tile a route drawn to
that room should meet.

Each entry is checked against the edges before it is written: the target has to
be a real arrival tile in this region's data, or the entry is stale and gets
reported rather than silently placed. Re-running is safe — anchors this script
wrote before are dropped and rebuilt.

    python3 scripts/38_add_arrival_anchors.py                 # every region listed below
    python3 scripts/38_add_arrival_anchors.py sweethearts_castle
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ANCHOR_EV = 903
KIND = 'anchor'

# region -> [(mapId, x, y, name)]. Hand-written: "has no exit of its own" is
# true of a great many interiors, and anchoring all of them would bury the
# stitcher in dots. These are the rooms a route actually needs to reach.
ARRIVALS = {
    'sweethearts_castle': [
        # Reached from map171 (and its slice map1711) ev76, the Sweetheart's
        # quest warp. The cell is a dead end otherwise — the other three cells
        # on this row each have a "To Dungeon B1" hole and this one does not.
        (182, 7, 8, 'Arrival anchor (top-left cell)'),
    ],
}


def main(argv):
    regions = argv or sorted(ARRIVALS)
    total = 0
    for region in regions:
        entries = ARRIVALS.get(region)
        if entries is None:
            print(f'  {region}: nothing listed — skipped')
            continue
        maps_path = ROOT / 'data' / f'{region}_maps.json'
        edges_path = ROOT / 'data' / f'{region}_edges.json'
        if not edges_path.exists():
            print(f'  {region}: no {edges_path.name} — run 01 first')
            continue
        meta = json.loads(maps_path.read_text())
        edges = json.loads(edges_path.read_text())
        internal = edges.get('internal', [])

        internal = [e for e in internal
                    if not (e.get('kind') == KIND and e['from'].get('evId') == ANCHOR_EV)]

        for map_id, x, y, name in entries:
            m = meta.get(str(map_id))
            if not m:
                print(f'  ⚠ map{map_id}: not in {region}_maps.json — skipped')
                continue
            senders = [e for e in edges.get('internal', []) + edges.get('external', [])
                       if e['to']['mapId'] == map_id
                       and (e['to']['x'], e['to']['y']) == (x, y)]
            if not senders:
                print(f'  ⚠ map{map_id} ({x}, {y}): nothing in {region}_edges.json '
                      f'arrives there — stale entry?')
                continue
            internal.append({
                # A point anchor, so both axes stay pinned: this stands for one
                # tile, not for a whole side the way 34's anchors do.
                'from': {'mapId': map_id, 'evId': ANCHOR_EV, 'evName': name,
                         'x': x, 'y': y, 'hitbox': {'L': 0, 'R': 0, 'T': 0, 'B': 0}},
                'to': {'mapId': map_id, 'x': x, 'y': y},
                'kind': KIND,
            })
            total += 1
            who = ', '.join(sorted({f"map{e['from']['mapId']} ev{e['from']['evId']}"
                                    for e in senders}))
            print(f'  map{map_id} {m["name"]}: {name} at ({x}, {y})  ← arrives from {who}')

        edges['internal'] = internal
        edges_path.write_text(json.dumps(edges, indent=2))

    print(f'\n{total} arrival anchor(s) written')


if __name__ == '__main__':
    main(sys.argv[1:])
