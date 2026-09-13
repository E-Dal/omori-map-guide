#!/usr/bin/env python3
"""Cut the one stitched-houses canvas into one house per image.

The stitcher lays every Faraway interior out on a single plane: 196 room
slices, 124 routes, 32 house-and-time-of-day combinations, all in one
coordinate space. That is the right way to *author* it — a room can be dragged
against its neighbour and the door route snapped across — and the wrong way to
*read* it, because no two houses are related and nothing is ever looked at more
than one house at a time.

So each house is lifted out on its own. A room's parent map is written into its
id (`r24_0` is room 0 of map24, KIM'S HOUSE (DAY)), which is all the grouping
this needs: no house shares a map with another, and every route in the layout
has both ends snapped inside a single house, so nothing has to be cut in half.

Output, per house:
  data/raw_pngs/houses_stitched/map<id>.webp   rooms pasted where they were
                                              placed, transparent between them
  data/faraway_houses_stitched.json           where each room and route landed,
                                              in that image's own pixels

Routes are geometry in the JSON, not ink on the PNG. The atlas draws them as
lines it can restyle, fade and toggle; baking them in would freeze one colour
and one weight into the render.

    python3 scripts/43_split_house_layout.py
    python3 scripts/43_split_house_layout.py 24 28      # just KIM'S HOUSE
"""
import json
import sys
from pathlib import Path

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _img import save  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / 'data' / 'stitched' / 'faraway_houses_layout.json'
SLICED = ROOT / 'data' / 'faraway_houses_sliced.json'
RAW = ROOT / 'data' / 'raw_pngs'
OUT_DIR = RAW / 'houses_stitched'
OUT_JSON = ROOT / 'data' / 'faraway_houses_stitched.json'

TILE = 32


def parent_of(rid):
    """`r24_0` -> 24. Room ids are the only thing tying a slice to its house."""
    return int(str(rid)[1:].split('_')[0])


def main(argv):
    wanted = {int(a) for a in argv} or None
    layout_doc = json.loads(LAYOUT.read_text())
    sliced = json.loads(SLICED.read_text())

    # rid -> the slice it was cut from, and mapId -> which house that is.
    rooms, houses = {}, {}
    for house, phases in sliced['houses'].items():
        for phase, info in phases.items():
            houses[info['mapId']] = (house, phase)
            for r in info['rooms']:
                rooms[f"r{info['mapId']}_{r['roomIdx']}"] = r

    placed = {}
    for rid, pos in layout_doc['layout'].items():
        if rid not in rooms:
            print(f'  ⚠ {rid}: no such room in {SLICED.name} — skipped')
            continue
        placed.setdefault(parent_of(rid), []).append((rid, pos))

    by_house = {}
    for r in layout_doc.get('routes', []):
        ends = {parent_of(p['snap']['mapId']) for p in r['pts'] if p.get('snap')}
        # A route with ends in two houses would have to be cut, and there is no
        # sensible place to cut it; a route snapped to nothing has no house to
        # belong to. Neither exists today — say so rather than lose it quietly.
        if len(ends) == 1:
            by_house.setdefault(ends.pop(), []).append(r)
        else:
            print(f'  ⚠ route across {sorted(ends) or "nothing"} — dropped')

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {'tile': TILE, 'houses': {}}
    for map_id in sorted(placed):
        if wanted and map_id not in wanted:
            continue
        entries = placed[map_id]
        house, phase = houses.get(map_id, ('?', '?'))

        # The canvas is the house's own bounding box, so every image starts at
        # its own (0, 0) and the plane the houses were authored on disappears.
        min_x = min(p['x'] for _, p in entries)
        min_y = min(p['y'] for _, p in entries)
        max_x = max(p['x'] + rooms[rid]['tw'] * TILE for rid, p in entries)
        max_y = max(p['y'] + rooms[rid]['th'] * TILE for rid, p in entries)
        w, h = int(max_x - min_x), int(max_y - min_y)

        canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        room_out = []
        for rid, pos in sorted(entries, key=lambda t: t[1].get('zOrder', 0)):
            r = rooms[rid]
            src = RAW / r['file']
            if not src.exists():
                print(f'  ⚠ {rid}: no {r["file"]} — skipped')
                continue
            x, y = int(pos['x'] - min_x), int(pos['y'] - min_y)
            canvas.alpha_composite(Image.open(src).convert('RGBA'), (x, y))
            room_out.append({'rid': rid, 'roomIdx': r['roomIdx'],
                             'x': x, 'y': y,
                             'w': r['tw'] * TILE, 'h': r['th'] * TILE,
                             # Where this room sat on its parent map, so a
                             # marker known by map tile can still be placed.
                             'srcTx': r['tx'], 'srcTy': r['ty']})

        name = save(canvas, OUT_DIR / f'map{map_id}.webp').name

        routes_out = []
        for r in by_house.get(map_id, []):
            routes_out.append({
                'color': r.get('color'),
                'pts': [{**{k: v for k, v in p.items() if k not in ('x', 'y')},
                         'x': p['x'] - min_x, 'y': p['y'] - min_y}
                        for p in r['pts']],
            })

        out['houses'][str(map_id)] = {
            'mapId': map_id, 'name': house, 'phase': phase,
            'file': str((OUT_DIR / name).relative_to(RAW)),
            'width': w, 'height': h,
            'rooms': room_out, 'routes': routes_out,
        }
        print(f'  map{map_id:<4} {house} ({phase}): {len(room_out)} room(s), '
              f'{len(routes_out)} route(s) → {w}x{h}')

    if not wanted:
        OUT_JSON.write_text(json.dumps(out, indent=1))
        print(f'\n{len(out["houses"])} house(s) → {OUT_DIR.relative_to(ROOT)}/ '
              f'and {OUT_JSON.relative_to(ROOT)}')
    else:
        print(f'\n{len(out["houses"])} house(s) rendered; '
              f'{OUT_JSON.name} left alone (partial run)')


if __name__ == '__main__':
    main(sys.argv[1:])
