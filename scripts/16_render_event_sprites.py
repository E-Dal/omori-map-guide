#!/usr/bin/env python3
"""Draw event sprites that a map's PNG is missing — chiefly warp pads.

Most things the player sees in OMORI are events, not tiles, and the goats.dev
renders already include them. Warp pads are the exception: they live on a later
event *page*, one that only becomes active mid-puzzle, so the render shows bare
floor and there is no sign of where the portals are.

This composites those sprites onto the existing PNG. It does not re-render the
map: a tiles-only pass would drop every other event with it — doing that to
MOLLY ROOM RIGHT 2 cost 361 tiles of holograms, computers and puzzle parts.

    python3 scripts/16_render_event_sprites.py              # PORTALS below
    python3 scripts/16_render_event_sprites.py 240
    python3 scripts/16_render_event_sprites.py 240 --events 1,3,24
    python3 scripts/16_render_event_sprites.py 240 --sprite DW_PuzzleObjects5

For each event the *first page carrying the wanted sprite* is used, not page 0
— Map240's pads sit on page 1 behind an invisible DEV_TEST placeholder on
page 0, which is why a page-0-only scan reported the map as having no portals.

Character sheets are img/characters/<name>.rpgmvp. A normal sheet packs 8
characters as 4 across x 2 down, each 3 animation frames across x 4 facings
down; a sheet whose name starts with '$' holds a single character, so the whole
image is the 3x4 grid. Sprites anchor at the bottom centre of their tile.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
TILE = 32
PORTAL_SPRITE = 'DW_PuzzleObjects5'

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)

# Warp pads through the Molly wing, by map. Everything else on the DW_
# PuzzleObjects5 sheet is furniture — candles, oven doors, gate doors, a prize
# wheel — and is already drawn, so only these are listed.
PORTALS = {
    235: [1, 4],                    # MOLLY ENTRANCE
    236: [2, 3, 4, 29],             # MOLLY MAIN ROOM
    237: [1],                       # MOLLY ROOM RIGHT 1
    238: [2, 8, 9],                 # MOLLY ROOM RIGHT 2
    239: [1, 2, 4],                 # MOLLY ROOM LEFT 1 (42/43 are conveyor bots)
    240: [1, 3, 24, 28, 84, 87],    # MOLLY ROOM LEFT 2
    241: [1, 2, 3, 4],              # MOLLY LOST ROOM 1
    242: [1, 2],                    # BOSS RUSH BATTLE ROOM
    243: [1, 2, 3, 4],              # MOLLY LOST ROOM 3
    244: [1],                       # BOSS RUSH LOBBY
    245: [1, 2, 3, 6],              # MOLLY LOST ROOM 5
    247: [1, 2],                    # MOLLY LOST ROOM 7
    248: [1],                       # MOLLY BOSS ROOM
}


def walkable_grid(map_id):
    """Per-tile passability from the map's hidden COLLISION layer, or None."""
    src = _r13['MAPS_DIR'] / f'map{map_id}.AUBREY'
    if not src.exists():
        return None
    tiled = _r13['load_aubrey_json'](src)
    layer = next((l for l in tiled.get('layers', []) if l.get('name') == 'COLLISION'), None)
    if not layer or 'data' not in layer:
        return None
    w, h = tiled['width'], tiled['height']
    data = layer['data']
    return w, h, [[data[y * w + x] == 0 for x in range(w)] for y in range(h)]


def clip_to_headroom(frame, grid, ex, ey):
    """Trim the top of a tall sprite where a wall would cover it.

    A warp pad is two tiles tall: the pad on its own tile and a beam of light
    above. In game the wall tiles draw over the player layer, so a pad at the
    top edge of the floor has its beam hidden. Compositing the whole frame on
    top instead leaves the beam standing in the wall, reading as a portal
    floating a tile above the ground.
    """
    rows = frame.height // TILE
    if rows <= 1 or grid is None:
        return frame
    w, h, walk = grid
    keep = 1
    for i in range(1, rows):
        ty = ey - i
        if ty < 0 or not (0 <= ex < w) or not walk[ty][ex]:
            break
        keep += 1
    if keep == rows:
        return frame
    return frame.crop((0, frame.height - keep * TILE, frame.width, frame.height))


def submap_parent(map_id):
    """(parent id, cropX, cropY) when map_id is a sliced sub-map, else None.

    Sub-maps carry cropX/cropY and a name that extends their parent's, so a
    sprite belonging to the parent map can be placed on the slice by shifting
    it by the crop origin. Needed because the two versions of an alcove differ
    only by a sprite the shipped render never drew.
    """
    meta = {}
    for f in sorted((ROOT / 'data').glob('*_maps.json')):
        meta.update(json.loads(f.read_text()))
    m = meta.get(str(map_id))
    if not m or 'cropX' not in m:
        return None
    for pid, pm in meta.items():
        if pid != str(map_id) and 'cropX' not in pm and m['name'].startswith(pm['name'] + ' '):
            return int(pid), m['cropX'], m['cropY']
    return None


def load_events(map_id):
    p = DECRYPTED / f'Map{map_id:03d}.json'
    if not p.exists():
        raise SystemExit(f'Missing {p}')
    return {e['id']: e for e in (json.loads(p.read_text()).get('events') or []) if e}


def page_with_sprite(ev, sprite=None):
    """First page holding a drawable sprite, preferring `sprite` if named."""
    pages = ev.get('pages') or []
    if sprite:
        for p in pages:
            if (p.get('image') or {}).get('characterName') == sprite:
                return p.get('image')
    # DEV_TEST is RPG Maker's placeholder — an invisible marker the game never
    # draws, and page 0 of a great many events wears it while the real graphic
    # waits on a later page. Taking the first page with *any* graphic stamped a
    # debug box on MOONWALK MAP where the CLUB SANDWICH door belongs, which is
    # the same kind of box 20_find_dev_boxes.py exists to hunt down.
    for p in pages:
        img = p.get('image') or {}
        if img.get('characterName') and img['characterName'] != 'DEV_TEST':
            return img
    return None


# Sheets that do not sit where the bottom-centre rule puts them.
#
# The rule works for most things, but the conveyor machine landed 17px left and
# 3px low. That is measurable rather than arguable: JUNKYARD (III) already has
# four of these machines painted into its shipped PNG — BlueBot 1-1/1-2 and
# PinkBot 2-1/2-2, all DW_PuzzleObjects_2 — so matching the sprite against the
# art gives the true position. All four agree exactly: the 64x32 frame's
# top-left corner sits on the tile's top-left corner, so the machine occupies
# its own tile and the one to its right.
#
# This is deliberately a table of measured sheets, not a new global rule. A
# sweep across ten maps found the conventions disagree — a 32x36 frame follows
# bottom-centre exactly, a 32x64 warp pad does not — so changing the default
# would move the pads that are already right.
ANCHOR_FRAME_TOPLEFT = {'DW_PuzzleObjects_2'}


def trim_to_content(frame):
    """Crop a frame down to its drawn pixels.

    These object frames are not drawn against the bottom of their cell. A warp
    pad occupies rows 13-37 of a 64px frame with 26 blank pixels beneath it, so
    anchoring the *frame* to the tile — RPG Maker's bottom-centre rule taken
    literally — lands the pad a tile above the floor it belongs to, standing in
    the wall. Anchoring the drawn pixels instead puts it under the player's
    feet, which is where the game shows it.
    """
    box = content_box(frame)
    return frame.crop(box) if box else frame


def content_box(frame):
    """(x0, y0, x1, y1) of the frame's drawn pixels, or None if it is blank."""
    a = np.array(frame)
    ys, xs = np.where(a[:, :, 3] > 0)
    if not len(ys):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def sprite_frame(char_name, index, direction, pattern):
    """One frame from a character sheet, or None if the sheet is missing."""
    path = _r13['GAME_ROOT'] / 'img/characters' / f'{char_name}.rpgmvp'
    if not path.exists():
        print(f'  !! no sheet {char_name}.rpgmvp', file=sys.stderr)
        return None
    sheet = _r13['load_rpgmvp_png'](path)
    w, h = sheet.size
    single = w % 3 if char_name.startswith('$') else w % 12
    single = single or (h % 4 if char_name.startswith('$') else h % 8)
    if single:
        # Not divisible into the usual grid, so the file is one frame and
        # nothing else. [SF]SW_Cake is 32x37 — slicing that as 12x8 yields a
        # 2x4 pixel "frame", which composites as nothing at all.
        return sheet
    if char_name.startswith('$'):
        fw, fh = w // 3, h // 4
        bx = by = 0
    else:
        fw, fh = w // 12, h // 8
        bx, by = (index % 4) * (w // 4), (index // 4) * (h // 2)
    row = direction // 2 - 1          # 2 down, 4 left, 6 right, 8 up
    col = max(0, min(2, pattern))
    return sheet.crop((bx + col * fw, by + row * fh,
                       bx + (col + 1) * fw, by + (row + 1) * fh))


def main():
    args = sys.argv[1:]
    want_events = None
    want_sprite = PORTAL_SPRITE
    if '--events' in args:
        i = args.index('--events')
        want_events = [int(x) for x in args[i + 1].split(',')]
        del args[i:i + 2]
    no_clip = '--no-clip' in args
    if no_clip:
        args.remove('--no-clip')
    if '--sprite' in args:
        i = args.index('--sprite')
        want_sprite = args[i + 1]
        del args[i:i + 2]
    name_re = None
    if '--name' in args:
        # Pick events by name instead of by id. The conveyors are spread over
        # three different sheets (DW_PuzzleObjects, _1 and _5), so selecting on
        # the sprite would miss two thirds of them, but every one is named
        # 'conveyor…' or 'Conveyor-Bot'.
        import re as _re
        i = args.index('--name')
        name_re = _re.compile(args[i + 1], _re.I)
        del args[i:i + 2]
    ids = [int(a) for a in args] or sorted(PORTALS)

    pngs = ROOT / 'data' / 'raw_pngs'
    for map_id in ids:
        out = pngs / f'map{map_id}.png'
        if not out.exists():
            print(f'  !! no map{map_id}.png', file=sys.stderr)
            continue
        # A slice inherits its sprites from the map it was cut out of.
        parent = submap_parent(map_id)
        src_id, off_x, off_y = parent if parent else (map_id, 0, 0)
        events = load_events(src_id)
        if name_re is not None:
            # DEV_TEST is the editor's placeholder for events with no graphic —
            # a flat labelled square. Map239's conveyorSwitch is one of those, and
            # matching on the name alone pulls it in and stamps an "INIT" box on
            # the map. Nothing wearing that sheet is meant to be seen.
            chosen = []
            for e in events.values():
                if not name_re.search(e.get('name') or ''):
                    continue
                img = page_with_sprite(e, want_sprite)
                if img and img['characterName'] != 'DEV_TEST':
                    chosen.append(e)
            wanted = 'by-name'
        else:
            wanted = want_events if want_events is not None else PORTALS.get(map_id)
        if name_re is not None:
            pass
        elif wanted is None:
            chosen = [e for e in events.values()
                      if page_with_sprite(e, want_sprite)
                      and page_with_sprite(e, want_sprite)['characterName'] == want_sprite]
        else:
            chosen = [events[i] for i in wanted if i in events]
        if not chosen:
            continue

        canvas = Image.open(out).convert('RGBA')
        grid = walkable_grid(src_id)
        drawn = clipped = 0
        for ev in chosen:
            img = page_with_sprite(ev, want_sprite)
            if not img:
                print(f'  · ev{ev["id"]} "{ev.get("name","")}" has no sprite on any page')
                continue
            frame = sprite_frame(img['characterName'], img.get('characterIndex', 0),
                                 img.get('direction', 2), img.get('pattern', 1))
            if frame is None:
                continue
            box = content_box(frame)
            frame = frame.crop(box) if box else frame
            full_h = frame.height
            # Headroom clipping suits the two-tile warp pads it was written for.
            # A large decoration is a different case — the branch coral is nearly
            # five tiles tall and the game lets it stand against the wall behind
            # it, so clipping would leave a stump.
            if not no_clip:
                frame = clip_to_headroom(frame, grid, ev['x'], ev['y'])
            was_clipped = frame.height < full_h
            clipped += was_clipped
            ex, ey = ev['x'] - off_x, ev['y'] - off_y
            if img['characterName'] in ANCHOR_FRAME_TOPLEFT and box:
                px = ex * TILE + box[0]
                py = ey * TILE + box[1]
            else:
                px = ex * TILE + TILE // 2 - frame.width // 2
                py = ey * TILE + TILE - frame.height
            canvas.alpha_composite(frame, (max(0, px), max(0, py)))
            drawn += 1
            print(f'  + map{map_id} ev{ev["id"]} "{ev.get("name","")}" '
                  f'{img["characterName"]}[{img.get("characterIndex",0)}] '
                  f'at tile ({ev["x"]},{ev["y"]})'
                  + (f' — clipped to {frame.height // TILE} tile(s), wall above' if was_clipped else ''))
        if drawn:
            canvas.save(out)
            print(f'  ✓ map{map_id}.png: {drawn} sprite(s) composited\n')



def _refresh_png_manifest():
    """Stamp the manifest so the pages pick the new render up without a
    hard reload — see scripts/35_png_manifest.py."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'png_manifest', Path(__file__).resolve().parent / '35_png_manifest.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.rebuild()
    except Exception as exc:            # a stale manifest is not worth failing a render over
        print(f'  · could not refresh the PNG manifest: {exc}')


if __name__ == '__main__':
    main()
    _refresh_png_manifest()
