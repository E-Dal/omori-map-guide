#!/usr/bin/env python3
"""Bake each contiguous run of decorations into one PNG.

Why this exists
---------------
179 decorations are stitched into the world, and 165 of them are there to
bridge a hole: 91 hang over a gap between maps with nothing behind them, 74
straddle a map edge. The layout genuinely cannot tile — OMORI's maps were never
drawn to butt together — so the trees are the patch.

That patch leaks. stitcher_all.html keeps every map and decoration inside one
`#world` div and scales the lot with a single `transform: scale(zoom)`, so
sprites that touch at 1:1 keep touching at every zoom. index.html draws through
Leaflet, which sizes and positions each overlay on its own in fractional CSS
pixels; each rounds separately, hairline cracks open between neighbouring
sprites, and #map's background shows through them. Around a tree that reads as
a black outline — the exact thing people report and the exact reason it goes
away at 1:1, where there is no rounding to do. Verified by setting #map's
background to magenta: the "outline" comes back magenta.

One image cannot crack against itself. Baking a whole run of trees into a
single PNG removes every seam inside it, which is the same thing the stitcher
gets for free, and drops 179 overlays to about 17.

What counts as one cluster
--------------------------
Two decorations join a cluster when all three hold:

  * their boxes are within PAD px of each other,
  * index.html would put them in the same region pane (nearestMapTo below is a
    transcription of the one in index.html, crop and all),
  * no map of that same region has a zOrder between theirs *and* a box that
    overlaps the cluster — baking would otherwise flatten a tree that the
    layout deliberately put behind a map.

The third rule is why a spatial cluster can still come out as two or three
files. Only the big Vast Forest run needs it today (3 maps sit inside its
zOrder range).

Output
------
  web/assets/decorations/baked/deco_<region>_<n>.png
  data/stitched/deco_clusters.json

The manifest names, for each cluster, the uids it swallowed. index.html checks
every uid still matches the decoration it was baked from and that the clusters
between them cover the whole decorations array; anything off and it silently
falls back to drawing the sprites one by one, so a stale manifest degrades to
the old behaviour rather than to a wrong picture.

--all-below
-----------
Drops the third rule and puts every cluster underneath every map instead, so a
spatial cluster is always exactly one file. The trees that the layout had in
front of a map go behind it, which in this world is barely visible — nearly all
of them hang over a hole with no map to be in front of. Fewer, larger files and
nothing to re-split when maps move; the cost is that the layout's z-order for
decorations stops being honoured.

Run it after every layout import, next to 33_recolor_close_routes.py, with the
same flag each time — the manifest records which mode wrote it:

    python3 scripts/36_bake_deco_clusters.py
    python3 scripts/36_bake_deco_clusters.py --all-below
    python3 scripts/36_bake_deco_clusters.py --dry-run
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
LAYOUT = DATA / 'stitched' / 'all_regions_layout.json'
ART_DIR = ROOT / 'web' / 'assets' / 'decorations'
OUT_DIR = ART_DIR / 'baked'
MANIFEST = DATA / 'stitched' / 'deco_clusters.json'

TILE_PX = 32
PAD = 8          # gap, in world px, that still counts as "touching"

# Mirrors DECO_ART in index.html and DECOS in stitcher_all.html.
DECO_ART = {
    'tree_part':  ('tree_part.png',  61, 65),
    'tree_full':  ('tree_full.png',  61, 60),
    'pinwheel':   ('pinwheel.png',   59, 59),
    'pinwheel_2': ('pinwheel_2.png', 68, 69),
    'pinwheel_3': ('pinwheel_3.png', 57, 56),
}

# Both mirror index.html. First region to claim a map keeps it, in this order.
ALL_REGIONS = ['faraway', 'vast_forest', 'orange_oasis', 'snowglobe_mountain',
               'otherworld', 'junkyard', 'pyrefly_forest', 'sweethearts_castle',
               'deep_well', 'deeper_well', 'humphrey', 'last_resort',
               'white_space', 'forest_playground']
REGION_OVERRIDE = {'327': 'orange_oasis'}


def crop_height(crop, meta):
    """index.html's cropRect, height only."""
    return meta['height'] / 3 if crop in ('top3', 'mid3', 'bot3') else meta['height']


def load_placed(layout):
    """Every map the atlas draws, as index.html's `placed`: x, y, w, h, region."""
    meta_all, region_of = {}, {}
    for r in ALL_REGIONS:
        f = DATA / f'{r}_maps.json'
        if not f.exists():
            continue
        for map_id, m in json.loads(f.read_text()).items():
            meta_all[map_id] = m
            region_of.setdefault(map_id, REGION_OVERRIDE.get(map_id, r))
    placed = []
    for map_id, pos in layout.get('layout', {}).items():
        m = meta_all.get(map_id)
        if not m:
            continue
        placed.append({
            'id': map_id, 'x': pos['x'], 'y': pos['y'],
            'w': m['width'] * TILE_PX,
            'h': crop_height(pos.get('crop', 'full'), m) * TILE_PX,
            'z': pos.get('zOrder', 0),
            'region': region_of.get(map_id, ''),
        })
    return placed


def nearest_map_to(cx, cy, placed):
    """index.html's nearestMapTo — squared distance to the box, ties to first."""
    best, best_d = None, float('inf')
    for it in placed:
        dx = max(it['x'] - cx, 0, cx - (it['x'] + it['w']))
        dy = max(it['y'] - cy, 0, cy - (it['y'] + it['h']))
        d = dx * dx + dy * dy
        if d < best_d:
            best_d, best = d, it
    return best


def boxes_touch(a, b, pad):
    return (a[0] - pad < b[2] and b[0] - pad < a[2]
            and a[1] - pad < b[3] and b[1] - pad < a[3])


def boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def spatial_clusters(items, pad):
    """Union-find over index -> list of indices whose boxes chain together."""
    parent = list(range(len(items)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if boxes_touch(items[i]['box'], items[j]['box'], pad):
                parent[find(i)] = find(j)
    out = {}
    for i in range(len(items)):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def split_on_maps(group, items, region_maps):
    """Cut a cluster wherever a map of its own region is stacked inside it.

    Walking the members in draw order, a map whose zOrder lands between the
    previous member and this one has to stay between them, so the run ends
    there. The overlap test is against the *whole* cluster's box, not the part
    walked so far: a map can be stacked between two early sprites and still
    cover a late one, and baking the run at a single zOrder would drop that
    late sprite behind it.
    """
    members = sorted(group, key=lambda i: items[i]['z'])
    boxes = [items[i]['box'] for i in members]
    whole = (min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes))
    inside = [m for m in region_maps
              if boxes_overlap(whole, (m['x'], m['y'], m['x'] + m['w'], m['y'] + m['h']))]
    bands, band = [], []
    for i in members:
        if band and any(items[band[-1]]['z'] < m['z'] < items[i]['z'] for m in inside):
            bands.append(band)
            band = []
        band.append(i)
    if band:
        bands.append(band)
    return bands


_art_cache = {}


def art_image(kind):
    if kind not in _art_cache:
        name = DECO_ART[kind][0]
        _art_cache[kind] = Image.open(ART_DIR / name).convert('RGBA')
    return _art_cache[kind]


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    all_below = '--all-below' in args
    layout = json.loads(LAYOUT.read_text())
    placed = load_placed(layout)
    if not placed:
        sys.exit(f'{LAYOUT} holds no maps this build knows about.')

    items, unknown = [], set()
    for d in layout.get('decorations', []):
        art = DECO_ART.get(d['kind'])
        if not art:
            unknown.add(d['kind'])
            continue
        scale = d.get('scale', 1)
        w, h = art[1] * scale, art[2] * scale
        near = nearest_map_to(d['x'] + w / 2, d['y'] + h / 2, placed)
        if not near:
            continue
        items.append({
            'd': d, 'kind': d['kind'], 'uid': d.get('uid'),
            'x': d['x'], 'y': d['y'], 'w': w, 'h': h,
            'box': (d['x'], d['y'], d['x'] + w, d['y'] + h),
            'z': d.get('zOrder', 0), 'region': near['region'],
            'flip': bool(d.get('flip')), 'scale': scale,
        })
    if unknown:
        print(f'  · no art for decoration kind(s): {", ".join(sorted(unknown))} — skipped')
    if any(i['uid'] is None for i in items):
        sys.exit('Some decorations have no uid; index.html cannot verify the bake. '
                 'Re-export the layout from the stitcher.')

    by_region = {}
    for i, it in enumerate(items):
        by_region.setdefault(it['region'], []).append(i)

    clusters = []
    for region, idx in sorted(by_region.items()):
        region_maps = [m for m in placed if m['region'] == region]
        sub = [items[i] for i in idx]
        for group in spatial_clusters(sub, PAD):
            bands = ([sorted(group, key=lambda i: sub[i]['z'])] if all_below
                     else split_on_maps(group, sub, region_maps))
            for band in bands:
                clusters.append([idx[i] for i in band])
    # Draw order across clusters is the draw order of their first sprite.
    clusters.sort(key=lambda c: min(items[i]['z'] for i in c))

    if not dry:
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        OUT_DIR.mkdir(parents=True)

    entries, seq, total_px = [], {}, 0
    for cluster in clusters:
        members = sorted(cluster, key=lambda i: items[i]['z'])
        boxes = [items[i]['box'] for i in members]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        w, h = int(round(x1 - x0)), int(round(y1 - y0))
        region = items[members[0]]['region']
        n = seq[region] = seq.get(region, 0) + 1
        name = f'deco_{region}_{n}.png'

        canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        for i in members:
            it = items[i]
            sprite = art_image(it['kind'])
            if it['scale'] != 1:
                sprite = sprite.resize((int(round(it['w'])), int(round(it['h']))),
                                       Image.NEAREST)
            if it['flip']:
                sprite = sprite.transpose(Image.FLIP_LEFT_RIGHT)
            canvas.alpha_composite(sprite, (int(round(it['x'] - x0)),
                                            int(round(it['y'] - y0))))
        if not dry:
            canvas.save(OUT_DIR / name)
        total_px += w * h

        entries.append({
            'file': f'assets/decorations/baked/{name}',
            'region': region, 'x': int(round(x0)), 'y': int(round(y0)),
            'w': w, 'h': h,
            'zOrder': min(items[i]['z'] for i in members),
            'uids': [items[i]['uid'] for i in members],
        })
        print(f'  {name:34} {w:5}x{h:<5} {len(members):4} sprite(s)  '
              f'z {min(items[i]["z"] for i in members)}'
              f'..{max(items[i]["z"] for i in members)}')

    if all_below:
        # One slot per cluster below the lowest map, in the order their first
        # sprite had, so the clusters keep their stacking against each other.
        base = min((m['z'] for m in placed), default=0)
        for i, e in enumerate(entries):
            e['zOrder'] = base - len(entries) + i

    manifest = {
        'note': 'Written by scripts/36_bake_deco_clusters.py. index.html verifies '
                'every uid against the layout and falls back to per-sprite '
                'drawing if anything has moved.',
        'mode': 'all-below' if all_below else 'layered',
        'clusters': entries,
    }
    if not dry:
        MANIFEST.write_text(json.dumps(manifest, separators=(',', ':')))

    print(f'\n{len(items)} decoration(s) -> {len(entries)} image(s), '
          f'{total_px / 1e6:.2f} Mpx, '
          f'{"all below the maps" if all_below else "kept in the layout z-order"}'
          + ('  [dry run]' if dry else ''))
    if not dry:
        print(f'wrote {MANIFEST.relative_to(ROOT)} and {OUT_DIR.relative_to(ROOT)}/')


if __name__ == '__main__':
    main()
