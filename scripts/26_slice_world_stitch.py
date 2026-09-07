#!/usr/bin/env python3
"""Cut per-region stitched images out of the all-regions world layout.

Stitched view wants two files per region: a layout naming where each map sits
and one PNG with them all drawn. Those used to come from per-region stitching
sessions, and most regions never got one. The world layout has every map
already placed, so each region's share can simply be lifted out of it.

Maps are assigned to a region the same way the world view assigns them — the
first region whose <region>_maps.json lists a map keeps it — so a map borrowed
by two regions is drawn once, under its owner.

A route is carried over when every point it snaps to belongs to the region.
One that reaches out of the region has nothing to land on here and would trail
off the edge of the image.

Written as the "world" variant, so it appears alongside any hand-stitched
version rather than overwriting it:

    data/stitched/<region>_layout_world.json
    data/stitched/stitched_<region>_world.png

    python3 scripts/26_slice_world_stitch.py
    python3 scripts/26_slice_world_stitch.py junkyard deep_well
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
OUT = DATA / 'stitched'
TILE = 32
WORLD = OUT / 'all_regions_layout.json'
VARIANT = 'world'

# Same order the atlas loads them in — first claim wins.
REGIONS = ['faraway', 'vast_forest', 'orange_oasis', 'snowglobe_mountain', 'otherworld',
           'junkyard', 'pyrefly_forest', 'sweethearts_castle', 'deep_well', 'deeper_well',
           'last_resort', 'white_space', 'forest_playground']


def crop_height(crop, meta):
    """Mirror of the atlas's cropRect, in tiles."""
    if crop in ('top3', 'mid3', 'bot3'):
        return meta['height'] / 3
    return meta['height']


def crop_top(crop, meta):
    if crop == 'mid3':
        return meta['height'] / 3
    if crop == 'bot3':
        return meta['height'] * 2 / 3
    return 0


def main():
    wanted = set(sys.argv[1:])
    world = json.loads(WORLD.read_text())
    layout, routes = world.get('layout', {}), world.get('routes', [])

    meta, owner = {}, {}
    for r in REGIONS:
        f = DATA / f'{r}_maps.json'
        if not f.exists():
            continue
        for map_id, m in json.loads(f.read_text()).items():
            meta.setdefault(map_id, m)
            owner.setdefault(map_id, r)

    for region in REGIONS:
        if wanted and region not in wanted:
            continue
        ids = [i for i in layout if owner.get(i) == region and i in meta]
        if not ids:
            print(f'  · {region}: no maps placed in the world layout')
            continue

        x0 = min(layout[i]['x'] for i in ids)
        y0 = min(layout[i]['y'] for i in ids)
        x1 = max(layout[i]['x'] + meta[i]['width'] * TILE for i in ids)
        y1 = max(layout[i]['y'] + crop_height(layout[i].get('crop', 'full'), meta[i]) * TILE
                 for i in ids)
        canvas = Image.new('RGBA', (int(x1 - x0), int(y1 - y0)), (0, 0, 0, 0))

        drawn = missing = 0
        for i in sorted(ids, key=lambda k: layout[k].get('zOrder', 0)):
            path = DATA / 'raw_pngs' / (meta[i].get('image') or f'map{i}.png')
            if not path.exists():
                missing += 1
                continue
            im = Image.open(path).convert('RGBA')
            crop = layout[i].get('crop', 'full')
            if crop != 'full':
                top = int(crop_top(crop, meta[i]) * TILE)
                im = im.crop((0, top, im.width, top + int(crop_height(crop, meta[i]) * TILE)))
            canvas.alpha_composite(im, (int(layout[i]['x'] - x0), int(layout[i]['y'] - y0)))
            drawn += 1

        own = set(ids)
        kept = [r for r in routes
                if r.get('pts') and len(r['pts']) >= 2
                and all(not p.get('snap') or str(p['snap']['mapId']) in own for p in r['pts'])]

        # Coordinates stay in world space; the atlas recomputes the bbox on load
        # exactly as it does for a hand-stitched layout.
        (OUT / f'{region}_layout_{VARIANT}.json').write_text(json.dumps(
            {'layout': {i: layout[i] for i in ids}, 'routes': kept}, indent=1))
        canvas.save(OUT / f'stitched_{region}_{VARIANT}.png')
        print(f'  ✓ {region}: {drawn} map(s), {len(kept)} route(s), '
              f'{canvas.width}×{canvas.height}px'
              + (f'  [{missing} PNG missing]' if missing else ''))


if __name__ == '__main__':
    main()
