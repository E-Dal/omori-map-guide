#!/usr/bin/env python3
"""Slice OMORI Faraway house interior PNGs into individual rooms.

Each house interior is a single 90x80 (or 90x64) tile canvas with multiple
disconnected rooms scattered across it (separated by transparent void).
We flood-fill the non-transparent pixels to find each room's connected
component, snap its bbox to the 32px tile grid, crop, and save.

Output:
  data/raw_pngs/houses/map{mid}_room{n}.png  — individual room images
  data/faraway_houses.json                   — metadata bundle
"""
import json, os, sys
from pathlib import Path
from PIL import Image
import numpy as np

TILE = 32
MIN_ROOM_TILES = 3 * 3   # discard noise smaller than 3x3 tiles
RAW_DIR = Path('data/raw_pngs')
OUT_DIR = Path('data/raw_pngs/houses')
OUT_DIR.mkdir(exist_ok=True)

# Faraway house map IDs to slice (excluding player's house: 14, 18, 78)
HOUSE_IDS = [
    15, 16, 17, 19, 20, 21,   # KEL&HERO, CRIS, MAVERICK (day+sunset)
    23, 24, 25, 26, 27, 28, 29, 30,   # BRENT, KIM, JOY, CHARLIE
    32, 33, 34, 35, 36, 37, 38, 39,   # VANCE, SHAWN&KAREN, SARAH, AUBREY
    41,                       # CHURCH INTERIOR (no sunset variant)
    46, 47, 48, 49, 50, 51, 52, 53,   # BASIL, JESSE, BEBE, ARTIST
    79, 80,                   # KEL&HERO NIGHT, BASIL NIGHT
    393,                      # TREEHOUSE
]

def flood_components(mask):
    """Iterative flood-fill on a 2D boolean mask. Returns list of pixel-index lists."""
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    comps = []
    for y0 in range(h):
        for x0 in range(w):
            if not mask[y0, x0] or visited[y0, x0]:
                continue
            stack = [(y0, x0)]
            comp = []
            while stack:
                y, x = stack.pop()
                if y < 0 or x < 0 or y >= h or x >= w: continue
                if visited[y, x] or not mask[y, x]: continue
                visited[y, x] = True
                comp.append((y, x))
                stack.extend([(y+1,x),(y-1,x),(y,x+1),(y,x-1)])
            comps.append(comp)
    return comps

def slice_house(mid):
    src = RAW_DIR / f'map{mid}.png'
    if not src.exists():
        print(f'  skip map{mid}: no PNG')
        return []
    im = Image.open(src).convert('RGBA')
    arr = np.array(im)
    alpha = arr[:, :, 3] > 0   # H × W boolean

    # Down-sample to tile-grid for component discovery (any opaque pixel in tile → tile occupied)
    H_tiles = (alpha.shape[0] + TILE - 1) // TILE
    W_tiles = (alpha.shape[1] + TILE - 1) // TILE
    tile_mask = np.zeros((H_tiles, W_tiles), dtype=bool)
    for ty in range(H_tiles):
        for tx in range(W_tiles):
            tile_mask[ty, tx] = alpha[ty*TILE:(ty+1)*TILE, tx*TILE:(tx+1)*TILE].any()

    comps = flood_components(tile_mask)
    rooms = []
    for comp in comps:
        if len(comp) < MIN_ROOM_TILES: continue
        ys = [c[0] for c in comp]; xs = [c[1] for c in comp]
        y0, y1 = min(ys), max(ys)
        x0, x1 = min(xs), max(xs)
        # Crop in tile coords → pixel coords
        px0, py0 = x0 * TILE, y0 * TILE
        px1, py1 = (x1 + 1) * TILE, (y1 + 1) * TILE
        crop = im.crop((px0, py0, px1, py1))
        rooms.append({
            'tx': x0, 'ty': y0,                  # tile-coord origin in parent map
            'tw': x1 - x0 + 1, 'th': y1 - y0 + 1,
            'crop_box': (px0, py0, px1, py1),
            'image': crop,
        })
    # Sort rooms by (ty, tx) for stable IDs
    rooms.sort(key=lambda r: (r['ty'], r['tx']))
    out = []
    for i, r in enumerate(rooms):
        out_path = OUT_DIR / f'map{mid}_room{i}.png'
        r['image'].save(out_path)
        out.append({
            'roomIdx': i,
            'file': str(out_path.relative_to('data/raw_pngs')),
            'tx': r['tx'], 'ty': r['ty'],
            'tw': r['tw'], 'th': r['th'],
        })
    print(f'  map{mid}: {len(out)} rooms')
    return out

def main():
    import re
    # Load map names to build house→phase grouping
    maps_meta = json.loads(Path('data/faraway_maps.json').read_text())

    # Build per-map name + phase
    def parse_name(name):
        n = name.replace('-- ', '').strip()
        m = re.search(r'\((DAY|SUNSET|NIGHT)\)\s*$', n)
        phase = m.group(1).lower() if m else 'day'
        base = re.sub(r'\s*\((DAY|SUNSET|NIGHT)\)\s*$', '', n).strip()
        # Normalize 'HOME' vs 'HOUSE' and 'AND' vs '&' for night variants
        base = base.replace("'S HOME", "'S HOUSE")
        base = base.replace(' AND ', ' & ')
        return base, phase

    # Group rooms by house base name
    houses = {}  # houseName -> { phase: { mapId, rooms: [...] } }
    per_map_rooms = {}
    for mid in HOUSE_IDS:
        per_map_rooms[mid] = slice_house(mid)

    for mid, rooms in per_map_rooms.items():
        meta = maps_meta.get(str(mid), {})
        if not meta: continue
        base, phase = parse_name(meta.get('name', ''))
        houses.setdefault(base, {})[phase] = {
            'mapId': mid,
            'rooms': rooms,
        }

    out = {
        'tile': TILE,
        'houses': houses,
    }
    out_json = Path('data/faraway_houses_sliced.json')
    out_json.write_text(json.dumps(out, indent=2))
    total = sum(len(p['rooms']) for h in houses.values() for p in h.values())
    print(f'\nWrote {out_json} ({len(houses)} houses, {total} room images total)')

if __name__ == '__main__':
    main()
