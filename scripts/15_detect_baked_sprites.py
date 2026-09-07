#!/usr/bin/env python3
"""Report which raw_pngs carry event sprites baked into the image.

goats.dev renders maps with their event sprites drawn on (party members, NPCs,
debug markers). 13_render_tiled_map.py composites only the Tiled tile layers,
so re-rendering a map strips those sprites. That is usually what an atlas wants
— but not always: chests, signs and portals are events too, and dropping them
leaves the map looking empty.

So this only reports. It renders every map that ships an .AUBREY into a scratch
directory, diffs against the PNG on disk, and lists what differs and which
events sit in the changed tiles, so the replacements can be chosen by hand.

    python3 scripts/15_detect_baked_sprites.py [--out report.json] [map_id ...]
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
TILE = 32
DIFF_THRESHOLD = 20      # per-pixel channel-sum delta that counts as "changed"

# Reuse the renderer without triggering its CLI.
_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)


def region_of_maps():
    out = {}
    for f in sorted((ROOT / 'data').glob('*_maps.json')):
        region = f.name[:-len('_maps.json')]
        for map_id in json.loads(f.read_text()):
            out.setdefault(map_id, region)
    return out


def events_of(map_id):
    p = DECRYPTED / f'Map{map_id:03d}.json'
    if not p.exists():
        return []
    return [e for e in (json.loads(p.read_text()).get('events') or []) if e]


def main():
    args = sys.argv[1:]
    out_path = None
    if '--out' in args:
        i = args.index('--out')
        out_path = Path(args[i + 1])
        del args[i:i + 2]

    regions = region_of_maps()
    ids = [int(a) for a in args] if args else sorted(int(i) for i in regions)
    pngs = ROOT / 'data' / 'raw_pngs'
    scratch = Path(tempfile.mkdtemp(prefix='baked-sprites-'))
    _r13['OUT_DIR'] = scratch          # render beside, never over, the real PNGs

    report, skipped = [], []
    for n, map_id in enumerate(ids, 1):
        have = pngs / f'map{map_id}.png'
        if not have.exists() or not (_r13['MAPS_DIR'] / f'map{map_id}.AUBREY').exists():
            skipped.append(map_id)
            continue
        try:
            _r13['render_map'](map_id)
        except Exception as exc:                     # noqa: BLE001 - report and move on
            skipped.append(map_id)
            print(f'  !! map{map_id} render failed: {exc}', file=sys.stderr)
            continue
        fresh = scratch / f'map{map_id}.png'
        if not fresh.exists():
            skipped.append(map_id)
            continue

        a = Image.open(have).convert('RGBA')
        b = Image.open(fresh).convert('RGBA')
        if a.size != b.size:
            report.append({'mapId': map_id, 'region': regions.get(str(map_id)),
                           'sizeMismatch': [list(a.size), list(b.size)]})
            fresh.unlink()
            continue

        na, nb = np.array(a).astype(int), np.array(b).astype(int)
        diff = np.abs(na - nb).sum(axis=2) > DIFF_THRESHOLD
        fresh.unlink()
        if not diff.any():
            continue

        th, tw = diff.shape[0] // TILE, diff.shape[1] // TILE
        tiles = diff[:th * TILE, :tw * TILE].reshape(th, TILE, tw, TILE).any(axis=(1, 3))
        changed = {(int(y), int(x)) for y, x in zip(*np.where(tiles))}

        # Name the events sitting in changed tiles — that's what would be lost.
        hits = []
        for ev in events_of(map_id):
            if any(abs(ev['y'] - y) <= 1 and abs(ev['x'] - x) <= 1 for y, x in changed):
                sprite = (ev.get('pages') or [{}])[0].get('image', {}).get('characterName') or ''
                hits.append({'evId': ev['id'], 'name': ev.get('name', ''),
                             'x': ev['x'], 'y': ev['y'], 'sprite': sprite})
        report.append({
            'mapId': map_id, 'region': regions.get(str(map_id)),
            'changedTiles': len(changed), 'changedPixels': int(diff.sum()),
            'events': hits,
        })
        print(f'[{n}/{len(ids)}] map{map_id}: {len(changed)} tiles differ, '
              f'{len(hits)} event(s) in them')

    scratch.rmdir()
    report.sort(key=lambda r: -r.get('changedTiles', 0))
    print(f'\n{len(report)} map(s) differ from a fresh render; {len(skipped)} skipped.')
    if out_path:
        out_path.write_text(json.dumps(report, indent=2))
        print(f'Wrote {out_path}')


if __name__ == '__main__':
    main()
