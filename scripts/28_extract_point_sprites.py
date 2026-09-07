#!/usr/bin/env python3
"""Cut out the sprite each collectible marker should be drawn as.

Watermelons, belt machines and HANGMAN keys are drawn with their real art, and
that is what makes them read as the thing rather than as an annotation. The
rest of the layers cover too many different objects for one icon to stand in
for — a charm marker could be a wardrobe, a shelf, an NPC; a mechanism could be
a lever, a console, a pinwheel — so each point is drawn as its own event's
frame.

23_extract_collectibles.js records that frame on each point as
"<sheet>|<index>|<direction>". Points share frames heavily (around 500 points,
around 200 distinct frames), so they are written once each and referenced by
name. Frames that resolve to nothing — a missing sheet, a blank cell — are
reported and simply left without art; the atlas falls back to the layer's emoji.

Each point also gets the pixel rectangle its sprite occupies, written back into
collectibles.json as `art`. A marker pinned to the tile centre does not sit on
the thing it labels: the game anchors most frames by the bottom of their drawn
pixels, and a few sheets by the frame's top-left corner (see 16), so a tall
sparkle or a two-tile machine ends up visibly off. With the rectangle recorded,
the atlas puts the marker exactly where the sprite is.

Run after 23 — it reads what 23 wrote and writes the rectangles back in. Both
are idempotent, so re-running the pair costs nothing.

    python3 scripts/28_extract_point_sprites.py
"""
import json
import re
from pathlib import Path

DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
POINTS = ROOT / 'data' / 'collectibles.json'
OUT = ROOT / 'web' / 'assets' / 'points'
MAX_PX = 96          # a five-tile decoration makes a hopeless map pin

_r16 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/16_render_event_sprites.py')}
exec(compile((ROOT / 'scripts/16_render_event_sprites.py').read_text(), 'r16', 'exec'), _r16)


def safe_name(key):
    """Frame key -> a filename that survives a URL."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', key)


def parse_key(key):
    """'sheet|index|direction[|pattern]' -> (sheet, index, direction, pattern).

    Keys written before the pattern was part of them mean column 1, which is
    what they were rendered as.
    """
    parts = key.split('|')
    sheet, index, direction = parts[0], int(parts[1]), int(parts[2])
    return sheet, index, direction, int(parts[3]) if len(parts) > 3 else 1


def shift_y(sheet, prio=1):
    """How far above the tile this sprite is drawn, in pixels.

    The engine's half is not a guess — it is
    `Game_CharacterBase.prototype.shiftY` in the game's own rpg_objects.js:

        return this.isObjectCharacter() ? 0 : 6;

    and `ImageManager.isObjectCharacter` is true exactly when the sheet name
    starts with '!'. So a door or a shelf sits flush on its tile and everything
    else — every sparkle, every NPC, every loose object on a plain sheet — is
    drawn six pixels higher. No plugin in the game overrides either function.

    The other half is the renderer's, and it had to be measured: an event set
    to "below characters" is painted with the ground and gets no lift. JUNKYARD
    (III)'s 96 conveyor belts are that case — plain sheet, priority 0, and all
    14 sampled sit exactly on their tiles in the untouched download — while the
    sparkles beside them are priority 1 and all 16 sit exactly six pixels up.

    Two things that look like counter-examples are not events at all. The bed
    on FA_TV and Mari on the picnic blanket match their character frames
    pixel-for-pixel *and* appear in a tiles-only re-render: the artist reused
    the same art in the tileset. Template matching cannot tell those apart, so
    check against a tiles-only render before believing one.
    """
    if prio == 0:
        return 0
    return 0 if sheet.startswith('!') else 6


def placed_rect(sheet, index, direction, tx, ty, pattern=1, prio=1):
    """Where this frame's drawn pixels land on the map: (x, y, w, h) or None.

    The whole *frame* is anchored bottom-centre on the tile — less shiftY — and
    the drawn pixels sit wherever they sit inside it, which is not the same as
    anchoring the drawn pixels themselves. Sprites with blank rows under the art
    ride that much higher: the singing Bass has eight, and a marker placed by
    the trimmed content sat eight pixels low every time.

    This is the fallback. 29_measure_point_art.py overwrites the answer wherever
    the sprite can actually be found in the map's PNG, which is the only way to
    be right about the sheets that break the rule and about the sprites this
    project composited itself under a different one.
    """
    try:
        frame = _r16['sprite_frame'](sheet, int(index), int(direction), pattern)
    except Exception:                                    # noqa: BLE001
        return None
    if frame is None:
        return None
    box = _r16['content_box'](frame)
    if box is None:
        return None
    w, h = box[2] - box[0], box[3] - box[1]
    if sheet in _r16['ANCHOR_FRAME_TOPLEFT']:
        # Measured separately against JUNKYARD's four painted machines.
        return tx * 32 + box[0], ty * 32 + box[1], w, h
    return (tx * 32 + 16 - frame.width // 2 + box[0],
            ty * 32 + 32 - frame.height - shift_y(sheet, prio) + box[1],
            w, h)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(POINTS.read_text())
    keys = {p['sprite'] for p in data['points'] if p.get('sprite')}
    # Belt machines want theirs too: the pink one and the blue one are
    # different frames, and one shared machine.png made them all blue.
    conv = ROOT / 'data' / 'conveyors.json'
    if conv.exists():
        for d in json.loads(conv.read_text()).values():
            for g in d['groups']:
                for m in g['machines']:
                    if m.get('art'):
                        keys.add(m['art']['sprite'])
    keys = sorted(keys)

    written, blank, missing = 0, [], []
    for key in keys:
        sheet, index, direction, pattern = parse_key(key)
        try:
            frame = _r16['sprite_frame'](sheet, index, direction, pattern)
        except Exception:                                # noqa: BLE001
            frame = None
        if frame is None:
            missing.append(key)
            continue
        box = _r16['content_box'](frame)
        if box is None:
            blank.append(key)
            continue
        frame = frame.crop(box)
        # Shrink anything oversized rather than dropping it: a marker wants to
        # be recognisable, not life-size.
        if max(frame.size) > MAX_PX:
            s = MAX_PX / max(frame.size)
            frame = frame.resize((max(1, int(frame.width * s)),
                                  max(1, int(frame.height * s))), Image.NEAREST)
        frame.save(OUT / f'{safe_name(key)}.png')
        written += 1

    # Tell each point how big its art is, so the atlas can keep the aspect
    # ratio without measuring the image at draw time.
    sizes = {}
    for key in keys:
        f = OUT / f'{safe_name(key)}.png'
        if f.exists():
            w, h = Image.open(f).size
            sizes[key] = [w, h]
    (ROOT / 'data' / 'point_sprites.json').write_text(json.dumps(sizes, indent=1))

    # Watermelons come from the region highlight files rather than from
    # collectibles.json, and were the one layer still pinned to the tile centre.
    # They are events like any other, so they get the same treatment: look up
    # the event's sprite and record where it lands.
    melon_rects = {}
    for hl in sorted((ROOT / 'data').glob('*_highlights.json')):
        for m in json.loads(hl.read_text()).get('watermelons', []):
            src = DECRYPTED / f"Map{int(m['mapId']):03d}.json"
            if not src.exists():
                continue
            evs = {e['id']: e for e in (json.loads(src.read_text()).get('events') or []) if e}
            ev = evs.get(m.get('evId'))
            if not ev:
                continue
            page = next((p for p in (ev.get('pages') or [])
                         if (p.get('image') or {}).get('characterName')
                         and p['image']['characterName'] != 'DEV_TEST'), None)
            if not page:
                continue
            img = page['image']
            r = placed_rect(img['characterName'], img.get('characterIndex', 0),
                            img.get('direction', 2), m['x'], m['y'],
                            img.get('pattern', 1), page.get('priorityType', 1))
            if r:
                melon_rects[f"{m['mapId']}:{m['evId']}"] = {'x': r[0], 'y': r[1],
                                                            'w': r[2], 'h': r[3]}
    (ROOT / 'data' / 'melon_art.json').write_text(json.dumps(melon_rects, indent=1))
    print(f'  ✓ {len(melon_rects)} watermelon(s) given their sprite rectangle '
          f'→ data/melon_art.json')

    # Put each point's own rectangle back where the atlas reads it.
    placed = 0
    for p in data['points']:
        key = p.get('sprite')
        if not key or key not in sizes:
            p.pop('art', None)
            continue
        sheet, index, direction, pattern = parse_key(key)
        r = placed_rect(sheet, index, direction, p['x'], p['y'], pattern,
                        p.get('prio', 1))
        if r:
            p['art'] = {'x': r[0], 'y': r[1], 'w': r[2], 'h': r[3]}
            placed += 1
        else:
            p.pop('art', None)
    POINTS.write_text(json.dumps(data, indent=1))
    print(f'  ✓ {placed} point(s) given their sprite rectangle in collectibles.json')

    print(f'  ✓ {written} frame(s) → web/assets/points/')
    if blank:
        print(f'  · {len(blank)} frame(s) drew nothing: {", ".join(blank[:6])}'
              + (' …' if len(blank) > 6 else ''))
    if missing:
        print(f'  · {len(missing)} sheet(s) not found: {", ".join(missing[:6])}'
              + (' …' if len(missing) > 6 else ''))
    per = {}
    for p in data['points']:
        if p.get('sprite') and (OUT / f'{safe_name(p["sprite"])}.png').exists():
            per[p['layer']] = per.get(p['layer'], 0) + 1
    print(f'  points with art, by layer: {per}')


if __name__ == '__main__':
    main()
