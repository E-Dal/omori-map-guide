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
DOOR_EV = 904
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


# Doors the game draws but never wired up — no transfer, no arrival, nothing to
# check them against, so these are placed by eye against the render and the
# comment has to say where. Unlike ARRIVALS they cannot be validated, which is
# why they are a separate table: a wrong entry here is silent.
DOORS = {
    'last_resort': [
        # CASINO, top right: the teal door in the north wall at tile (45, 5).
        # It is the LAST RESORT entrance to CLUB SANDWICH — the same tile the
        # 'Club Sandwich' event stands on — and (45, 6) is its threshold.
        (194, 45, 6, 'Door anchor (Club Sandwich)'),
    ],
    'otherworld': [
        # MOONWALK MAP: the sandwich-shaped door in the north wall at (16, 12),
        # the OTHERWORLD entrance. Floor starts at row 13.
        (348, 16, 13, 'Door anchor (Club Sandwich)'),
    ],
    'orange_oasis': [
        # ORANGE OASIS, east side: the ORANGE OASIS entrance at (83, 29), an
        # unmarked gap in the cake wall between two palms. Floor at row 30.
        (106, 83, 30, 'Door anchor (Club Sandwich)'),
    ],
}


def main(argv):
    regions = argv or sorted(set(ARRIVALS) | set(DOORS))
    total = 0
    for region in regions:
        entries = ARRIVALS.get(region)
        doors = DOORS.get(region)
        if entries is None and doors is None:
            print(f'  {region}: nothing listed — skipped')
            continue
        entries = entries or []
        doors = doors or []
        maps_path = ROOT / 'data' / f'{region}_maps.json'
        edges_path = ROOT / 'data' / f'{region}_edges.json'
        if not edges_path.exists():
            print(f'  {region}: no {edges_path.name} — run 01 first')
            continue
        meta = json.loads(maps_path.read_text())
        edges = json.loads(edges_path.read_text())
        internal = edges.get('internal', [])

        internal = [e for e in internal
                    if not (e.get('kind') == KIND
                            and e['from'].get('evId') in (ANCHOR_EV, DOOR_EV))]

        for map_id, x, y, name in entries:
            m = meta.get(str(map_id))
            if not m:
                print(f'  ⚠ map{map_id}: not in {region}_maps.json — skipped')
                continue
            # Anchors point at themselves, so they would otherwise turn up here
            # as evidence for their own existence.
            senders = [e for e in edges.get('internal', []) + edges.get('external', [])
                       if e['to']['mapId'] == map_id
                       and (e['to']['x'], e['to']['y']) == (x, y)
                       and e.get('kind') != KIND]
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

        for map_id, x, y, name in doors:
            m = meta.get(str(map_id))
            if not m:
                print(f'  ⚠ map{map_id}: not in {region}_maps.json — skipped')
                continue
            if not (0 <= x < m['width'] and 0 <= y < m['height']):
                print(f'  ⚠ map{map_id} ({x}, {y}): outside a {m["width"]}x{m["height"]} map')
                continue
            internal.append({
                'from': {'mapId': map_id, 'evId': DOOR_EV, 'evName': name,
                         'x': x, 'y': y, 'hitbox': {'L': 0, 'R': 0, 'T': 0, 'B': 0}},
                'to': {'mapId': map_id, 'x': x, 'y': y},
                'kind': KIND,
            })
            total += 1
            print(f'  map{map_id} {m["name"]}: {name} at ({x}, {y})  ← placed by eye')

        edges['internal'] = internal
        edges_path.write_text(json.dumps(edges, indent=2))

    print(f'\n{total} anchor(s) written')


if __name__ == '__main__':
    main(sys.argv[1:])
