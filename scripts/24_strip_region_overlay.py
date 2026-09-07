#!/usr/bin/env python3
"""Erase RPG Maker's region-number squares from the shipped map PNGs.

A Tiled map carries a REGION layer holding the numbered squares the editor
paints to mark encounter zones, water, ladders and so on. They are authoring
marks; the game never draws them. 13_render_tiled_map.py skips any layer whose
name says REGION, but the goats.dev renders did not, so the squares are baked
into the PNGs — twenty of them scattered across PYREFLY V, a run of them down
the middle of OTHERWORLD LADDER II.

The names are not uniform ("REGION - 20", "REGION 28", "Region L0", "region
90"), which is why matching the substring beats listing them.

This also names the "1" square in HOTEL ROOMS that 20_find_dev_boxes.py was
written to chase. It was never a DEV_TEST frame — hence its colours being half
strength and no event standing under it. Map 193 has a layer called "REGION -
1" holding exactly one tile, at (52,52), the tile that square sat on. It was
repainted by hand long before this script existed, so the sweep finds nothing
left to do there; what it explains is why nothing in the event tables ever
matched.

Each marked tile is repainted from a fresh tiles-only render of the same map,
which is the same map minus the region layers, so the floor comes back and
nothing else moves. A tile is left alone when the fresh render is empty there
(repainting would punch a hole) or when the shipped PNG already matches it
(nothing was baked in) — the second case is why the count of tiles touched is
lower than the count of tiles marked.

    python3 scripts/24_strip_region_overlay.py --dry-run
    python3 scripts/24_strip_region_overlay.py --backup /tmp/bk
    python3 scripts/24_strip_region_overlay.py 160
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TILE = 32
DIFF_THRESHOLD = 20   # per-pixel channel-sum delta that counts as painted on
REGION_TILESET = 'Tile_Regions_32x32.json'
FIT_ALPHAS = [i / 40 for i in range(4, 41)]   # 0.10 … 1.00
FIT_MAX_RESIDUAL = 14    # mean channel error the blend must get under
FIT_MIN_GAIN = 2.0       # and it must beat "no square here" by this factor

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)


def atlas_maps():
    meta = {}
    for f in sorted((ROOT / 'data').glob('*_maps.json')):
        meta.update(json.loads(f.read_text()))
    return meta


def region_tiles(tiled):
    """(x, y) -> gid for every tile any REGION layer marks, hidden or not."""
    w = tiled['width']
    out = {}
    for layer in tiled.get('layers', []):
        if layer.get('type') != 'tilelayer':
            continue
        if 'REGION' not in (layer.get('name') or '').upper():
            continue
        for i, gid in enumerate(layer.get('data', [])):
            if gid:
                out[(i % w, i // w)] = gid
    return dict(sorted(out.items()))


def region_square(tiled, gid):
    """The Tile_Regions_32x32 bitmap this gid names, as RGB, or None."""
    info = _r13['load_tileset'](REGION_TILESET)
    if not info or info['image'] is None:
        return None
    first = max((ts['firstgid'] for ts in tiled.get('tilesets', [])
                 if ts.get('source') == REGION_TILESET and ts['firstgid'] <= gid), default=None)
    if first is None:
        return None
    local = gid - first
    cols = info['columns']
    sx, sy = (local % cols) * TILE, (local // cols) * TILE
    if sy + TILE > info['image'].height:
        return None
    return np.array(info['image'].crop((sx, sy, sx + TILE, sy + TILE)).convert('RGB')).astype(float)


def blended_square(shipped, tiles, square):
    """Best (alpha, residual) for shipped == (1-a)*tiles + a*square, else None.

    None when no opacity explains the difference — the case for a tile that
    differs because something real is drawn on it.
    """
    base = np.abs(shipped - tiles).mean()
    best = None
    for a in FIT_ALPHAS:
        res = np.abs(shipped - ((1 - a) * tiles + a * square)).mean()
        if best is None or res < best[1]:
            best = (a, res)
    if best[1] > FIT_MAX_RESIDUAL or best[1] * FIT_MIN_GAIN > base:
        return None
    return best


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    if dry:
        args.remove('--dry-run')
    backup_dir = None
    if '--backup' in args:
        i = args.index('--backup')
        backup_dir = Path(args[i + 1]); backup_dir.mkdir(parents=True, exist_ok=True)
        del args[i:i + 2]
    only = {int(a) for a in args}

    meta = atlas_maps()
    scratch = Path(tempfile.mkdtemp(prefix='region-'))
    _r13['OUT_DIR'] = scratch
    total_maps = total_tiles = 0

    for key in sorted(meta, key=lambda k: int(k)):
        map_id = int(key)
        if only and map_id not in only:
            continue
        src = _r13['MAPS_DIR'] / f'map{map_id}.AUBREY'
        target = ROOT / 'data' / 'raw_pngs' / f'map{map_id}.png'
        if not src.exists() or not target.exists():
            continue
        try:
            tiled = _r13['load_aubrey_json'](src)
        except Exception as exc:                        # noqa: BLE001
            print(f'  !! map{map_id}: {exc}', file=sys.stderr)
            continue
        marks = region_tiles(tiled)
        if not marks:
            continue

        try:
            _r13['render_map'](map_id)
        except Exception as exc:                        # noqa: BLE001
            print(f'  !! map{map_id} render failed: {exc}', file=sys.stderr)
            continue
        fresh_path = scratch / f'map{map_id}.png'
        if not fresh_path.exists():
            continue
        canvas = Image.open(target).convert('RGBA')
        fresh = Image.open(fresh_path).convert('RGBA')
        fresh_path.unlink()
        if canvas.size != fresh.size:
            print(f'  !! map{map_id}: size mismatch {canvas.size} vs {fresh.size}', file=sys.stderr)
            continue

        arr, und = np.array(canvas), np.array(fresh)
        painted = empty = clean = other = 0
        alphas = []
        for (tx, ty), gid in marks.items():
            sy, sx = slice(ty * TILE, (ty + 1) * TILE), slice(tx * TILE, (tx + 1) * TILE)
            if sy.stop > arr.shape[0] or sx.stop > arr.shape[1]:
                continue
            tile = und[sy, sx]
            if not (tile[:, :, 3] > 0).any():
                empty += 1
                continue
            delta = int((np.abs(arr[sy, sx].astype(int) - tile.astype(int)).sum(axis=2)
                         > DIFF_THRESHOLD).sum())
            if not delta:
                clean += 1
                continue
            square = region_square(tiled, gid)
            fit = None if square is None else blended_square(
                arr[sy, sx, :3].astype(float), tile[:, :, :3].astype(float), square)
            if fit is None:
                # Differs, but not by a square — something real is drawn here.
                other += 1
                continue
            alphas.append(fit[0])
            arr[sy, sx] = tile
            painted += 1
        if painted:
            total_maps += 1
            total_tiles += painted
            span = f'{min(alphas):.2f}' if len(set(alphas)) == 1 else f'{min(alphas):.2f}-{max(alphas):.2f}'
            print(f'  map{map_id} [{meta[key]["name"]}]: {painted} square(s) erased @ opacity {span}'
                  + (f', {other} left (real art)' if other else '')
                  + (f', {clean} already clean' if clean else '')
                  + (f', {empty} skipped (no tiles beneath)' if empty else ''))
            if not dry:
                if backup_dir:
                    shutil.copy2(target, backup_dir / target.name)
                Image.fromarray(arr).save(target)

    scratch.rmdir()
    print(f'\n{total_tiles} square(s) erased across {total_maps} map(s)'
          + (' [dry run]' if dry else ''))


if __name__ == '__main__':
    main()
