#!/usr/bin/env python3
"""Work out which conveyor belts each machine drives, and draw their other state.

Hitting a machine reverses some of the belts in the room, not all of them, and
the game says exactly which: every machine's script runs the same loop over a
contiguous block of event ids, ending at itself.

    var len = 66;
    for (var i = 63; i <= len; i++) {
      var key = [mapid, i, 'A'];
      $gameSelfSwitches.setValue(key, trigger);
    }

So ev66 owns events 63-66. A belt inside that block has a page gated on
self-switch A carrying the reversed sprite, which is the belt's other state.
Parsing the loop bounds gives the grouping for free — no guessing from
adjacency, which would have merged belts that only look like one run.

Two machines can drive the same block: JUNKYARD (III) has BlueBot 1-1 and 1-2
both covering 6-87, one at each end of the floor. Those collapse to a single
group with two buttons.

Which state is already on the map is measured, not assumed. MOLLY ROOM LEFT 2
ships with its belts in the unconditional state, but JUNKYARD (III) ships with
all 99 of its belts already in the self-switch-A state — so writing the A-state
overlay for it produced an image identical to what was underneath. Clicking the
machine worked perfectly and changed two pixels. Each map is checked belt by
belt against both sprites, and the overlay is built from whichever state is
*not* the one already drawn.

Output:
  data/conveyors.json        groups, their belts, machine positions
  data/conveyors/*.png       one transparent overlay per group, the other state

The overlay is composited over the map's existing art rather than replacing it.
A belt frame is a solid 32x32 block — at most nine transparent pixels, all in
the rounded corners — so the flipped arrow hides the one underneath.

MOLLY ROOM LEFT 1 is absent on purpose: its belts have the self-switch pages
but nothing in the game ever sets them, so there is no machine to press.

    python3 scripts/22_extract_conveyors.py
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
TILE = 32
OUT_JSON = ROOT / 'data' / 'conveyors.json'
OUT_DIR = ROOT / 'data' / 'conveyors'

_r16 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/16_render_event_sprites.py')}
exec(compile((ROOT / 'scripts/16_render_event_sprites.py').read_text(), 'r16', 'exec'), _r16)

LOOP_LO = re.compile(r'for\s*\(\s*var\s+i\s*=\s*(\d+)\s*;\s*i\s*<=\s*len')
LOOP_HI = re.compile(r'var\s+len\s*=\s*(\d+)')
# The same "flip self-switch A across a block of events" idiom drives plenty of
# things that are not belts — OUTSKIRTS resets a traffic cone with it, FROZEN
# FOREST a pushable box, MARINA MAZE a collapsing bridge, MOLLY ROOM RIGHT 2 a
# row of teleport pads. Only events that say they are conveyors are belts.
IS_BELT = re.compile(r'conveyor', re.I)


def page_source(page):
    return '\n'.join(c['parameters'][0] for c in (page.get('list') or [])
                     if c.get('code') in (355, 655) and c.get('parameters'))


def machine_art(ev):
    """The machine's own frame and where it sits, as {sprite, x, y, w, h}.

    The marker in the atlas should be the machine, in its own colour, over the
    machine — the pink one is a different frame from the blue one, and the
    frame is anchored by its top-left corner rather than centred on the tile
    (see ANCHOR_FRAME_TOPLEFT in 16), so a marker pinned to the tile centre
    lands up and to the left of the thing it labels.
    """
    page = default_page(ev)
    img = page.get('image') if page else None
    if not img:
        return None
    frame = sprite_of(img)
    if frame is None:
        return None
    frame, (px, py) = place(frame, img, ev['x'], ev['y'])
    return {
        # Which layer the renderer paints it on — 29 needs it to know whether
        # the six-pixel character lift applies when it recomputes this.
        'prio': page.get('priorityType', 1),
        # Pattern is part of the key: every machine in the game is drawn on
        # column 0, and a key that leaves it out sends 28 to column 1 — a
        # different frame of the same sheet, drawn into a rectangle measured
        # from this one.
        'sprite': f"{img['characterName']}|{img.get('characterIndex', 0)}|"
                  f"{img.get('direction', 2)}|{img.get('pattern', 1)}",
        'x': px, 'y': py, 'w': frame.width, 'h': frame.height,
    }


def machine_range(ev):
    """(lo, hi) event ids a machine flips, or None if it is not a machine."""
    for page in ev.get('pages') or []:
        src = page_source(page)
        lo, hi = LOOP_LO.search(src), LOOP_HI.search(src)
        if lo and hi and 'setValue' in src:
            return int(lo.group(1)), int(hi.group(1))
    return None


def default_page(ev):
    for page in ev.get('pages') or []:
        cond = page.get('conditions') or {}
        img = page.get('image') or {}
        if not cond.get('selfSwitchValid') and img.get('characterName') \
                and img['characterName'] != 'DEV_TEST':
            return page
    return None


def default_image(ev):
    page = default_page(ev)
    return page.get('image') if page else None


def flipped_image(ev):
    for page in ev.get('pages') or []:
        cond = page.get('conditions') or {}
        img = page.get('image') or {}
        if cond.get('selfSwitchValid') and cond.get('selfSwitchCh') == 'A' \
                and img.get('characterName') and img['characterName'] != 'DEV_TEST':
            return img
    return None


def sprite_of(img):
    frame = _r16['sprite_frame'](img['characterName'], img.get('characterIndex', 0),
                                 img.get('direction', 2), img.get('pattern', 1))
    return None if frame is None else frame


def place(frame, img, ex, ey):
    """Top-left pixel for a frame on tile (ex, ey), matching 16's rules."""
    box = _r16['content_box'](frame)
    if img['characterName'] in _r16['ANCHOR_FRAME_TOPLEFT'] and box:
        return frame.crop(box), (ex * TILE + box[0], ey * TILE + box[1])
    cropped = frame.crop(box) if box else frame
    return cropped, (max(0, ex * TILE + TILE // 2 - cropped.width // 2),
                     max(0, ey * TILE + TILE - cropped.height))


def baked_state(belts, png):
    """'default' or 'flipped' — whichever sprite the shipped PNG already shows.

    Each belt is compared against both candidates over the sprite's own opaque
    pixels and the majority wins. Belts that match neither (covered by
    something, or the sheet is missing) simply do not vote.
    """
    shipped = np.array(Image.open(png).convert('RGB')).astype(int)
    score = {'default': 0, 'flipped': 0}
    for belt in belts:
        for label, img in (('default', default_image(belt)), ('flipped', flipped_image(belt))):
            if not img:
                continue
            frame = sprite_of(img)
            if frame is None:
                continue
            frame, (px, py) = place(frame, img, belt['x'], belt['y'])
            a = np.array(frame).astype(int)
            h = min(a.shape[0], shipped.shape[0] - py)
            w = min(a.shape[1], shipped.shape[1] - px)
            if h <= 0 or w <= 0:
                continue
            mask = a[:h, :w, 3] > 128
            if not mask.any():
                continue
            err = float(np.abs(shipped[py:py + h, px:px + w] - a[:h, :w, :3])[mask].mean())
            if err < 30:
                score[label] += 1
    return 'flipped' if score['flipped'] > score['default'] else 'default'


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = [int(a) for a in sys.argv[1:]]
    out = {}
    for path in sorted(DECRYPTED.glob('Map[0-9][0-9][0-9].json')):
        map_id = int(path.stem[3:])
        if ids and map_id not in ids:
            continue
        png = ROOT / 'data' / 'raw_pngs' / f'map{map_id}.png'
        if not png.exists():
            continue
        events = {e['id']: e for e in (json.loads(path.read_text()).get('events') or []) if e}
        # Group machines by the block they drive, so a floor with a switch at
        # each end reads as one run of belts with two buttons.
        by_range = {}
        for ev in events.values():
            rng = machine_range(ev)
            if rng is None:
                continue
            belts = [e for eid, e in sorted(events.items())
                     if rng[0] <= eid <= rng[1] and IS_BELT.search(e.get('name') or '')
                     and flipped_image(e) and default_image(e)]
            if not belts:
                continue
            by_range.setdefault(rng, {'belts': belts, 'machines': []})['machines'].append(ev)
        if not by_range:
            continue

        size = Image.open(png).size
        # Draw the state the map is not already showing.
        baked = baked_state([b for g in by_range.values() for b in g['belts']], png)
        other = default_image if baked == 'flipped' else flipped_image
        groups = []
        for rng, g in sorted(by_range.items()):
            canvas = Image.new('RGBA', size, (0, 0, 0, 0))
            tiles, x0, y0, x1, y1 = [], size[0], size[1], 0, 0
            for belt in g['belts']:
                img = other(belt)
                frame = sprite_of(img)
                if frame is None:
                    continue
                frame, (px, py) = place(frame, img, belt['x'], belt['y'])
                canvas.alpha_composite(frame, (px, py))
                tiles.append({'x': belt['x'], 'y': belt['y']})
                x0, y0 = min(x0, px), min(y0, py)
                x1, y1 = max(x1, px + frame.width), max(y1, py + frame.height)
            if not tiles:
                continue
            name = f'map{map_id}_ev{g["machines"][0]["id"]}.png'
            canvas.crop((x0, y0, x1, y1)).save(OUT_DIR / name)
            groups.append({
                'evRange': list(rng),
                'baked': baked,
                'shows': 'default' if baked == 'flipped' else 'flipped',
                'machines': [{'evId': m['id'], 'name': m.get('name') or '',
                              'x': m['x'], 'y': m['y'], 'art': machine_art(m)}
                             for m in g['machines']],
                'belts': tiles,
                'overlay': {'file': name, 'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0},
            })
        if groups:
            out[str(map_id)] = {'groups': groups}
            for grp in groups:
                who = ', '.join(f'{m["name"]}({m["x"]},{m["y"]})' for m in grp['machines'])
                print(f'  map{map_id} ev{grp["evRange"][0]}-{grp["evRange"][1]}: '
                      f'{len(grp["belts"])} belt(s), PNG shows {baked}, '
                      f'overlay draws {grp["shows"]} — {who}')

    OUT_JSON.write_text(json.dumps(out, indent=1))
    total = sum(len(v['groups']) for v in out.values())
    print(f'\n{total} group(s) across {len(out)} map(s) → {OUT_JSON.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
