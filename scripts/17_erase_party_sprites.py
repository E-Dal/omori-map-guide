#!/usr/bin/env python3
"""Erase the player party from map PNGs, leaving everything else untouched.

goats.dev renders each map with its event sprites drawn on. That is what we
want for furniture, NPCs and machines — in OMORI those are events, not tiles,
so a tiles-only re-render would empty the room. The exception is the party:
OMORI, AUBREY, KEL and HERO are parked on a number of maps and have no business
in an atlas.

So instead of re-rendering, this paints out just those sprites. It renders the
map's tile layers to know what is behind them, then copies those pixels back
over the party sprite's own silhouette (alpha > 0) and nothing else.

The sprite can only be repainted where the tile layers actually describe what
is underneath. Where a party member stands in front of another *event* — a
chair, a sign — the tile render has nothing there, and erasing would punch a
hole. Those sprites are left alone and reported instead.

    python3 scripts/17_erase_party_sprites.py            # every affected map
    python3 scripts/17_erase_party_sprites.py 194 345    # just these
    python3 scripts/17_erase_party_sprites.py --dry-run
    python3 scripts/17_erase_party_sprites.py --backup DIR

Pass --review DIR to also write before/after strips for eyeballing.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
TILE = 32

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)
_r16 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/16_render_event_sprites.py')}
exec(compile((ROOT / 'scripts/16_render_event_sprites.py').read_text(), 'r16', 'exec'), _r16)
sprite_frame = _r16['sprite_frame']

# Curated per map, because no rule separates the party from scenery reliably.
#
# The obvious rule — sprite sheet named DW_OMORI / DW_AUBREY / DW_KEL / DW_HERO
# — finds nothing: those events exist on ~35 maps but are cutscene copies
# parked on void tiles that goats.dev never drew. Every party figure actually
# visible comes from a *_BREAKTIME_* sheet, the rest-spot art. And those sheets
# are shared with props: Map90's sandcastles, Map50's picnic blankets, Map92's
# playing cards and Map166's thirteen treadmills all sit on the same sheets
# under the same naming. Sheet name and event name both lie, so the list is
# built by looking at the maps.
#
# Survey of all 22 maps holding rest-spot events found exactly one where the
# party is drawn: FROZEN LAKE. (FROZEN FOREST I was the other and is already
# fixed by a full re-render.) Re-run the survey if the PNGs are refreshed.
ERASE_EVENTS = {
    131: [17, 18, 19, 20,   # 'Spot 1'-'Spot 4' — the four of them on the pier
          14],              # 'fisher' — OMORI with the fishing rod
    # 131 ev15 'prize' is the hole in the ice, not a character — left alone.
}
# Fraction of a sprite's silhouette that may sit over empty tile-render before
# we call it a hole and back off.
HOLE_TOLERANCE = 0.02
# An event existing in the map data does not mean it was drawn: many maps park
# cutscene copies of the party on void tiles, and goats.dev renders nothing
# there. Painting the tile layers over those spots would stamp the map's black
# void into a transparent area — a silhouette where there had been nothing. So
# require the PNG to actually hold the sprite's own pixels before touching it.
PRESENCE_MATCH = 60      # max per-pixel RGB delta counted as "same colour"
PRESENCE_FRACTION = 0.5  # share of the silhouette that must match
PAINTED_OVER_FRACTION = 0.3  # share that must also differ from the bare tiles


def sprite_present(canvas_arr, under_arr, frame, x0, y0, cx0, cy0, cx1, cy1):
    """Is this sprite actually painted into the PNG at this spot?

    Looking like the sprite is not enough on its own: the party are mostly dark
    pixels, so on a map whose void is black a plain tile render "matches" the
    silhouette by coincidence. Require both that the pixels resemble the sprite
    and that they differ from the tile layers — something has to be drawn *over*
    the tiles for there to be anything to erase.
    """
    fr = np.array(frame)[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    mask = fr[:, :, 3] > 0
    if not mask.any():
        return False, 0.0, 0.0
    cur = canvas_arr[cy0:cy1, cx0:cx1]
    und = under_arr[cy0:cy1, cx0:cx1]
    like = (np.abs(cur[:, :, :3].astype(int) - fr[:, :, :3].astype(int)).sum(axis=2) <= PRESENCE_MATCH)
    like &= (cur[:, :, 3] > 0) & mask
    over = (np.abs(cur.astype(int) - und.astype(int)).sum(axis=2) > PRESENCE_MATCH) & mask
    n = mask.sum()
    like_frac, over_frac = like.sum() / n, over.sum() / n
    present = like_frac >= PRESENCE_FRACTION and over_frac >= PAINTED_OVER_FRACTION
    return present, like_frac, over_frac


def all_map_ids():
    ids = set()
    for f in (ROOT / 'data').glob('*_maps.json'):
        ids.update(json.loads(f.read_text()))
    return sorted(int(i) for i in ids if i.isdigit())


def events_of(map_id):
    p = DECRYPTED / f'Map{map_id:03d}.json'
    if not p.exists():
        return []
    return [e for e in (json.loads(p.read_text()).get('events') or []) if e]


def sprite_box(ev, frame):
    """Destination rect of an event's sprite: anchored bottom-centre on its tile."""
    x = ev['x'] * TILE + TILE // 2 - frame.width // 2
    y = ev['y'] * TILE + TILE - frame.height
    return x, y, x + frame.width, y + frame.height


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    if dry:
        args.remove('--dry-run')
    backup_dir = review_dir = None
    for flag in ('--backup', '--review'):
        if flag in args:
            i = args.index(flag)
            d = Path(args[i + 1]); d.mkdir(parents=True, exist_ok=True)
            if flag == '--backup':
                backup_dir = d
            else:
                review_dir = d
            del args[i:i + 2]

    ids = [int(a) for a in args] if args else sorted(ERASE_EVENTS)
    pngs = ROOT / 'data' / 'raw_pngs'
    scratch = Path(tempfile.mkdtemp(prefix='erase-party-'))
    _r13['OUT_DIR'] = scratch

    n_maps = n_erased = 0
    skipped = []
    for map_id in ids:
        target = pngs / f'map{map_id}.png'
        if not target.exists():
            continue
        wanted = set(ERASE_EVENTS.get(map_id, []))
        if not wanted:
            continue
        evs = events_of(map_id)
        party = [e for e in evs if e['id'] in wanted]
        others = [e for e in evs
                  if e['id'] not in wanted and (e.get('pages') or [{}])[0].get('image', {}).get('characterName')]

        try:
            _r13['render_map'](map_id)
        except Exception as exc:                       # noqa: BLE001
            skipped.append((map_id, 0, f'tile render failed: {exc}'))
            continue
        tiles_png = scratch / f'map{map_id}.png'
        if not tiles_png.exists():
            skipped.append((map_id, 0, 'no .AUBREY to render from'))
            continue

        canvas = Image.open(target).convert('RGBA')
        beneath = Image.open(tiles_png).convert('RGBA')
        tiles_png.unlink()
        if canvas.size != beneath.size:
            skipped.append((map_id, len(party), f'size mismatch {canvas.size} vs {beneath.size}'))
            continue

        before = canvas.copy()
        arr = np.array(canvas)
        under = np.array(beneath)
        done = holes = absent = 0
        for ev in party:
            img = (ev.get('pages') or [{}])[0]['image']
            frame = sprite_frame(img['characterName'], img.get('characterIndex', 0),
                                 img.get('direction', 2), img.get('pattern', 1))
            if frame is None:
                continue
            x0, y0, x1, y1 = sprite_box(ev, frame)
            x0c, y0c = max(0, x0), max(0, y0)
            x1c, y1c = min(canvas.width, x1), min(canvas.height, y1)
            if x0c >= x1c or y0c >= y1c:
                continue
            mask = np.array(frame)[y0c - y0:y1c - y0, x0c - x0:x1c - x0, 3] > 0
            if not mask.any():
                continue

            present, like_frac, over_frac = sprite_present(arr, under, frame, x0, y0, x0c, y0c, x1c, y1c)
            if not present:
                absent += 1
                continue

            # Would this leave a hole? Two ways it can: the tile layers have
            # nothing behind the sprite, or another event's sprite overlaps it
            # and that object only exists in the goats render.
            region_under = under[y0c:y1c, x0c:x1c]
            empty = (region_under[:, :, 3] == 0) & mask
            overlap = None
            for o in others:
                oimg = (o.get('pages') or [{}])[0]['image']
                of = sprite_frame(oimg['characterName'], oimg.get('characterIndex', 0),
                                  oimg.get('direction', 2), oimg.get('pattern', 1))
                if of is None:
                    continue
                ox0, oy0, ox1, oy1 = sprite_box(o, of)
                if ox0 < x1 and ox1 > x0 and oy0 < y1 and oy1 > y0:
                    overlap = o
                    break
            if overlap is not None:
                holes += 1
                print(f'  · map{map_id} ev{ev["id"]} "{ev.get("name","")}" left alone — '
                      f'overlaps event "{overlap.get("name","")}"')
                continue
            if empty.sum() > HOLE_TOLERANCE * mask.sum():
                holes += 1
                print(f'  · map{map_id} ev{ev["id"]} "{ev.get("name","")}" left alone — '
                      f'{100 * empty.sum() / mask.sum():.0f}% of it has no tiles behind')
                continue

            arr[y0c:y1c, x0c:x1c][mask] = region_under[mask]
            done += 1

        if holes:
            skipped.append((map_id, holes, 'sprite(s) would leave a hole'))
        if absent and not done and not holes:
            print(f'  · map{map_id}: {absent} party event(s) present in the data '
                  f'but never drawn into the PNG — nothing to erase')
        if not done:
            continue
        result = Image.fromarray(arr)
        if review_dir:
            strip = Image.new('RGBA', (before.width * 2 + 24, before.height + 16), (30, 30, 34, 255))
            strip.alpha_composite(before, (8, 8))
            strip.alpha_composite(result, (before.width + 16, 8))
            strip.convert('RGB').save(review_dir / f'map{map_id}.png')
        if not dry:
            if backup_dir:
                shutil.copy2(target, backup_dir / f'map{map_id}.png')
            result.save(target)
        n_maps += 1
        n_erased += done
        print(f'  ✓ map{map_id}: erased {done}/{len(party)} party sprite(s)'
              + (' [dry run]' if dry else ''))

    scratch.rmdir()
    print(f'\n{n_erased} sprite(s) erased across {n_maps} map(s).')
    if skipped:
        print(f'{len(skipped)} map(s) with something left alone:')
        for map_id, n, why in skipped:
            print(f'  map{map_id}: {why}' + (f' ({n})' if n else ''))


if __name__ == '__main__':
    main()
