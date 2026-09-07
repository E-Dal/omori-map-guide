#!/usr/bin/env python3
"""
Cut polygon-clipped sub-maps from raw_pngs/map<src>.png.

Reads data/<region>_maps.json. For each entry that has a `polygon` field,
masks pixels outside the polygon to transparent and crops to the polygon's
bounding box. Output: data/raw_pngs/map<id>.png.

Usage: python3 scripts/05_cut_submaps.py <region>
"""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw

T = 32  # tile size in px

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/05_cut_submaps.py <region>", file=sys.stderr)
        sys.exit(1)
    region = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    meta_path = root / 'data' / f'{region}_maps.json'
    pngs_dir = root / 'data' / 'raw_pngs'
    if not meta_path.exists():
        print(f"Missing {meta_path}. Run: node scripts/01_extract_adjacency.js {region}", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(meta_path.read_text())
    n_cut = 0
    for fake_id, m in meta.items():
        poly = m.get('polygon')
        if not poly:
            continue
        # Source PNG: any entry that links to a real ID via cropX/cropY+polygon
        # belongs to a sub-map. We need to know the source map ID; recover from
        # the metadata by matching the name prefix (sub maps' names start with
        # the source name) OR by scanning subMap declarations. Simplest: scan
        # all entries to find one with same name prefix and no polygon.
        # Cleaner: stash src on the meta entry. We'll search by name prefix.
        src_id = None
        for sid, sm in meta.items():
            if sm is m: continue
            if sm.get('polygon'): continue
            if m['name'].startswith(sm['name'] + ' '):
                src_id = sid; break
        if src_id is None:
            print(f"!! Cannot find source for sub-map {fake_id} ({m['name']}), skipping", file=sys.stderr)
            continue

        src_png = pngs_dir / f'map{src_id}.png'
        if not src_png.exists():
            print(f"!! Missing source PNG {src_png}", file=sys.stderr)
            continue

        im = Image.open(src_png).convert('RGBA')
        # Build mask at source resolution
        mask = Image.new('L', im.size, 0)
        ImageDraw.Draw(mask).polygon([(c*T, r*T) for c, r in poly], fill=255)
        # Apply mask
        masked = Image.new('RGBA', im.size, (0,0,0,0))
        masked.paste(im, (0,0), mask)
        # Crop to polygon bbox
        cx, cy, w, h = m['cropX'], m['cropY'], m['width'], m['height']
        bbox = (cx*T, cy*T, (cx+w)*T, (cy+h)*T)
        out = masked.crop(bbox)
        out_path = pngs_dir / f'map{fake_id}.png'
        out.save(out_path)
        print(f"  cut map{fake_id} from map{src_id}: {len(poly)}-gon, "
              f"bbox cols {cx}-{cx+w} rows {cy}-{cy+h} → {out_path.name} ({out.size[0]}×{out.size[1]} px)")
        n_cut += 1
    print(f"\nDone. Cut {n_cut} polygon sub-maps.")

if __name__ == '__main__':
    main()
