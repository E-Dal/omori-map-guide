#!/usr/bin/env python3
"""
Re-render a stitched composite PNG from layout.json + current raw_pngs.

Mirrors the stitcher_<region>.html exportPNG logic (line 906-967):
  - bbox = bounding box of all placed maps
  - paste each map's PNG at (pos.x - minX, pos.y - minY), with optional
    {full|top3|mid3|bot3} crop
  - draw routes as dashed lines + colored dots on top
  - PNGs are scaled to match meta dims (some goats.dev PNGs are off by a few px)

Usage:
  python3 scripts/06_restitch.py                    # restitch all regions with layouts
  python3 scripts/06_restitch.py junkyard           # one region
  python3 scripts/06_restitch.py faraway day        # one region+variant
"""
import json, math, sys, os
from pathlib import Path
from PIL import Image, ImageDraw

T = 32
ROOT = Path(__file__).resolve().parent.parent
STITCHED = ROOT / 'data' / 'stitched'
RAW = ROOT / 'data' / 'raw_pngs'

def crop_rect(crop, meta):
    if crop == 'top3': return (0,                meta['height']/3)
    if crop == 'mid3': return (meta['height']/3, meta['height']/3)
    if crop == 'bot3': return (meta['height']*2/3, meta['height']/3)
    return (0, meta['height'])

def region_for(prefix):
    """Pull e.g. 'faraway' from 'faraway_layout_day' or 'junkyard' from 'junkyard_layout'."""
    return prefix.split('_layout')[0]

def restitch(layout_path: Path, out_path: Path):
    layout = json.loads(layout_path.read_text())
    region = region_for(layout_path.stem)
    meta_path = ROOT / 'data' / f'{region}_maps.json'
    if not meta_path.exists():
        print(f"  ⚠ skipping {layout_path.name}: {meta_path.name} not generated yet")
        return
    meta = json.loads(meta_path.read_text())

    # 1) bbox
    minX = minY = math.inf
    maxX = maxY = -math.inf
    for mid, pos in layout['layout'].items():
        m = meta.get(mid)
        if not m: continue
        cy, ch = crop_rect(pos.get('crop','full'), m)
        w = m['width'] * T
        ch_px = ch * T
        minX = min(minX, pos['x']);          minY = min(minY, pos['y'])
        maxX = max(maxX, pos['x'] + w);      maxY = max(maxY, pos['y'] + ch_px)
    cw, ch_canvas = int(maxX - minX), int(maxY - minY)

    canvas = Image.new('RGBA', (cw, ch_canvas), (0, 0, 0, 0))

    # 2) paste maps in z-order
    ids = sorted(layout['layout'].keys(),
                 key=lambda i: layout['layout'][i].get('zOrder', 0))
    for mid in ids:
        pos = layout['layout'][mid]
        m = meta.get(mid)
        if not m: continue
        png = RAW / f'map{mid}.png'
        if not png.exists():
            print(f"  ⚠ missing {png.name}, skipping")
            continue
        cy, ch_tiles = crop_rect(pos.get('crop','full'), m)
        img = Image.open(png).convert('RGBA')
        exp_h = m['height'] * T
        sy_scale = img.height / exp_h
        # Source: crop the actual PNG at cy*T*sy_scale, height ch_tiles*T*sy_scale
        src_top = int(cy * T * sy_scale)
        src_h   = int(ch_tiles * T * sy_scale)
        sub = img.crop((0, src_top, img.width, src_top + src_h))
        # Scale to expected px (width = m.width*T, height = ch_tiles*T)
        target_w = m['width'] * T
        target_h = int(ch_tiles * T)
        if sub.size != (target_w, target_h):
            sub = sub.resize((target_w, target_h))
        canvas.alpha_composite(sub, (int(pos['x'] - minX), int(pos['y'] - minY)))

    # 3) draw routes (dashed lines + colored dots), matching stitcher defaults
    if layout.get('routes'):
        d = ImageDraw.Draw(canvas)
        for r in layout['routes']:
            pts = r.get('pts') or []
            if len(pts) < 2: continue
            color = r.get('color', '#ff66d9')
            (x0, y0), (x1, y1) = (pts[0]['x'] - minX, pts[0]['y'] - minY), \
                                  (pts[1]['x'] - minX, pts[1]['y'] - minY)
            # dashed line: pattern [8, 6]
            dx, dy = x1 - x0, y1 - y0
            dist = math.hypot(dx, dy)
            if dist > 0:
                ux, uy = dx/dist, dy/dist
                pos_ = 0
                while pos_ < dist:
                    end = min(pos_ + 8, dist)
                    d.line([(x0+ux*pos_, y0+uy*pos_), (x0+ux*end, y0+uy*end)],
                           fill=color, width=3)
                    pos_ += 14   # 8 dash + 6 gap
            # 9-px radius dots with white outline
            for p in pts:
                cx, cy_ = p['x'] - minX, p['y'] - minY
                d.ellipse([cx-9, cy_-9, cx+9, cy_+9], fill=color, outline='white', width=2)

    canvas.convert('RGB').save(out_path)
    print(f"  ✓ {out_path.name}  ({cw}×{ch_canvas} px, {len(ids)} maps, {len(layout.get('routes',[]))} routes)")

def main(argv):
    target_region = argv[1] if len(argv) > 1 else None
    target_variant = argv[2] if len(argv) > 2 else None
    layouts = sorted(STITCHED.glob('*_layout*.json'))
    if not layouts:
        print('No layouts in', STITCHED); return
    for lp in layouts:
        # Filter by region/variant
        stem = lp.stem  # e.g. 'junkyard_layout' or 'faraway_layout_day'
        region = stem.split('_layout')[0]
        variant = stem.split('_layout_')[1] if '_layout_' in stem else ''
        if target_region and region != target_region: continue
        if target_variant and variant != target_variant: continue
        out = STITCHED / f'stitched_{region}{("_"+variant) if variant else ""}.png'
        print(f"Restitching {lp.name} → {out.name}")
        restitch(lp, out)

if __name__ == '__main__':
    main(sys.argv)
