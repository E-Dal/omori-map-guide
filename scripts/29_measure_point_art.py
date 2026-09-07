#!/usr/bin/env python3
"""Move every marker rectangle onto the sprite the map PNG actually shows.

28 works out where a sprite *should* land from the engine's rules. That is the
right thing to compute, and it is still wrong often enough to be visible,
because a marker is judged against one thing only: the picture underneath it.
Three ways the rule and the picture come apart, all measured rather than
argued:

  · sheets that do not follow the rule at all. DW_PuzzleObjects_2 is anchored
    by the frame's top-left corner, and it was found by measuring, not deduced.
  · sprites this project composited itself. 16 draws the *trimmed* frame at the
    bottom of the tile, so the Molly warp pads sit 26px below where the rule
    puts them — the rule describes the game, and those pixels came from us.
  · maps whose render is simply offset. All nine of JUNKYARD TUNNELS 1's
    sparkles sit at (+1, -2) from where the rule says, together, and TUNNELS 2's
    at (-2, -2) — a property of those PNGs rather than of any sprite.

So: cut the frame out of the sheet, look for it in the map's own PNG within a
tile of the predicted spot, and if it is there, say where it is. A sprite found
pixel-for-pixel is not an estimate. Anything not found keeps 28's rule and is
marked as such, so the two kinds of answer stay distinguishable.

Corrects data/collectibles.json, data/conveyors.json and data/melon_art.json.
Idempotent: the search always starts from the rule position recomputed from the
event's tile, never from whatever was written last time.

    python3 scripts/29_measure_point_art.py              # everything
    python3 scripts/29_measure_point_art.py 143 427      # only these maps
    python3 scripts/29_measure_point_art.py --radius 48
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
PNGS = ROOT / 'data' / 'raw_pngs'

_r28 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/28_extract_point_sprites.py')}
exec(compile((ROOT / 'scripts/28_extract_point_sprites.py').read_text(), 'r28', 'exec'), _r28)
_r16 = _r28['_r16']

RADIUS = 32          # a tile in every direction; wide enough for the 26px pads
PIXEL_TOL = 12       # channel-sum difference that still counts as the same pixel
HIT = 0.85           # share of the sprite's solid pixels that must agree
NEAR = 0.03          # scores this close to the best are treated as a tie
MIN_OPAQUE = 24      # a handful of solid pixels matches half the map
MAX_HITS = 4         # more places than this and the sprite is not distinctive


def load_png(map_id, _cache={}):
    """The map's image as RGB. One map at a time — the atlas is 637 PNGs."""
    if map_id not in _cache:
        _cache.clear()
        p = PNGS / f'map{map_id}.png'
        _cache[map_id] = np.array(Image.open(p).convert('RGB')).astype(np.int16) \
            if p.exists() else None
    return _cache[map_id]


def trimmed_frame(key, _cache={}):
    """The sprite's drawn pixels as RGBA, or None if it renders to nothing."""
    if key not in _cache:
        sheet, index, direction, pattern = _r28['parse_key'](key)
        try:
            f = _r16['sprite_frame'](sheet, index, direction, pattern)
        except Exception:                                # noqa: BLE001
            f = None
        box = _r16['content_box'](f) if f is not None else None
        _cache[key] = None if box is None else np.array(f.crop(box).convert('RGBA')).astype(np.int16)
    return _cache[key]


def find(png, spr, x0, y0, radius):
    """Where spr sits in png near (x0, y0): (x, y, share) or None.

    Scored as the share of the sprite's fully-opaque pixels that the map agrees
    with. Its blended edges are excluded — they are painted against whatever is
    behind them and say nothing about position — and a share rather than a mean
    error is what lets a sprite standing half behind a counter still be found,
    while a mean would be dragged past any threshold by the covered part.

    Among the positions that pass, the nearest to the predicted one wins. OMORI
    paints six identical drawers in a row; the job here is to correct a few
    pixels of drift, not to go looking for another drawer. A position that
    agrees on every pixel outranks a partial one only if the partial one is
    not clearly better placed — hence the NEAR band rather than a strict max.
    """
    h, w = spr.shape[:2]
    mask = spr[:, :, 3] == 255
    n = int(mask.sum())
    if n < MIN_OPAQUE:
        return None
    ys, xs = max(0, y0 - radius), max(0, x0 - radius)
    ye, xe = min(png.shape[0], y0 + h + radius), min(png.shape[1], x0 + w + radius)
    reg = png[ys:ye, xs:xe]
    if reg.shape[0] < h or reg.shape[1] < w:
        return None
    win = np.lib.stride_tricks.sliding_window_view(reg, (h, w), axis=(0, 1)).transpose(0, 1, 3, 4, 2)
    same = np.abs(win - spr[None, None, :, :, :3]).sum(axis=4) <= PIXEL_TOL
    share = (same & mask[None, None, :, :]).sum(axis=(2, 3)) / n
    top = float(share.max())
    if top < HIT:
        return None
    hit = np.argwhere(share >= max(HIT, top - NEAR))
    # A sprite that is one flat colour agrees with any flat wall. !FA_PLAYERHOUSE
    # _OBJ's beige panel matched 585 places in one window and DW_IMPORTANTOBJ's
    # white blob nine, and each was "found" a couple of tiles from the truth.
    # Something genuinely recognisable matches once — every sparkle, every warp
    # pad and every belt machine verified here matched in exactly one place — so
    # a crowd of candidates is the signal to stop, not to pick the closest.
    if len(hit) > MAX_HITS:
        return None
    dy, dx = hit[:, 0] + ys - y0, hit[:, 1] + xs - x0
    best = int(np.argmin(dy.astype(np.int64) ** 2 + dx.astype(np.int64) ** 2))
    iy, ix = hit[best]
    return int(xs + ix), int(ys + iy), float(share[iy, ix])


class Fixer:
    """Measures one (map, tile, sprite) at a time and keeps the tally."""

    def __init__(self, radius, only):
        self.radius, self.only = radius, only
        self.moved = Counter()
        self.measured = self.ruled = self.skipped = 0
        self.big, self.share = [], []

    def skip(self, map_id):
        """True when a map-id argument excludes this map.

        Naming maps has to mean "leave the others alone", not "recompute them
        from the rule" — that would quietly throw away every measurement the
        last full run made.
        """
        return bool(self.only) and map_id not in self.only

    def rect(self, map_id, key, tx, ty, what, prio=1):
        """The rectangle to record, or None when the sprite renders to nothing."""
        sheet, index, direction, pattern = _r28['parse_key'](key)
        rule = _r28['placed_rect'](sheet, index, direction, tx, ty, pattern, prio)
        if rule is None:
            self.skipped += 1
            return None
        rx, ry, w, h = rule
        out = {'x': rx, 'y': ry, 'w': w, 'h': h, 'artFit': 'rule'}
        png, spr = load_png(map_id), trimmed_frame(key)
        if png is None or spr is None:
            self.ruled += 1
            return out
        got = find(png, spr, rx, ry, self.radius)
        if got is None:
            self.ruled += 1
            return out
        x, y, share = got
        self.measured += 1
        self.share.append(share)
        self.moved[(x - rx, y - ry)] += 1
        if abs(x - rx) + abs(y - ry) >= 8:
            self.big.append((abs(x - rx) + abs(y - ry), f'map{map_id} {what} '
                             f'{key} moved ({x - rx:+d}, {y - ry:+d})'))
        out.update(x=x, y=y, artFit='measured')
        return out


def melon_sprite(map_id, ev_id, _cache={}):
    """(frame key, priority) for a watermelon — highlights.json records neither."""
    if map_id not in _cache:
        src = DECRYPTED / f'Map{int(map_id):03d}.json'
        _cache.clear()
        _cache[map_id] = {e['id']: e for e in
                          (json.loads(src.read_text()).get('events') or []) if e} \
            if src.exists() else {}
    ev = _cache[map_id].get(ev_id)
    if not ev:
        return None
    page = next((p for p in (ev.get('pages') or [])
                 if (p.get('image') or {}).get('characterName')
                 and p['image']['characterName'] != 'DEV_TEST'), None)
    if not page:
        return None
    img = page['image']
    return (f"{img['characterName']}|{img.get('characterIndex', 0)}|"
            f"{img.get('direction', 2)}|{img.get('pattern', 1)}",
            page.get('priorityType', 1))


def main():
    args = sys.argv[1:]
    radius = RADIUS
    if '--radius' in args:
        i = args.index('--radius')
        radius = int(args[i + 1])
        del args[i:i + 2]
    fix = Fixer(radius, set(args))

    points = ROOT / 'data' / 'collectibles.json'
    data = json.loads(points.read_text())
    # Map order keeps one PNG in memory at a time rather than 637.
    for p in sorted(data['points'], key=lambda p: int(p['mapId'])):
        if fix.skip(p['mapId']):
            continue
        if not p.get('sprite'):
            p.pop('art', None)
            continue
        r = fix.rect(p['mapId'], p['sprite'], p['x'], p['y'],
                     f'ev{p["evId"]} {p["evName"]}', p.get('prio', 1))
        if r:
            p['art'] = r
        else:
            p.pop('art', None)
    points.write_text(json.dumps(data, indent=1))
    print(f'  ✓ collectibles.json: {fix.measured} measured, {fix.ruled} left on the rule')

    before = fix.measured
    conv_path = ROOT / 'data' / 'conveyors.json'
    if conv_path.exists():
        conv = json.loads(conv_path.read_text())
        for map_id, d in sorted(conv.items(), key=lambda kv: int(kv[0])):
            if fix.skip(map_id):
                continue
            for g in d['groups']:
                for m in g['machines']:
                    if not m.get('art'):
                        continue
                    r = fix.rect(map_id, m['art']['sprite'], m['x'], m['y'], m['name'],
                                 m['art'].get('prio', 1))
                    if r:
                        m['art'] = {'sprite': m['art']['sprite'],
                                    'prio': m['art'].get('prio', 1), **r}
        conv_path.write_text(json.dumps(conv, indent=1))
        print(f'  ✓ conveyors.json: {fix.measured - before} machine(s) measured')

    before = fix.measured
    melon_path = ROOT / 'data' / 'melon_art.json'
    melons = json.loads(melon_path.read_text()) if melon_path.exists() else {}
    seen = set()
    every = [m for hl in sorted((ROOT / 'data').glob('*_highlights.json'))
             for m in json.loads(hl.read_text()).get('watermelons', [])]
    for m in sorted(every, key=lambda m: int(m['mapId'])):
        # A watermelon recorded without its event id cannot be looked up, and
        # the atlas keys its rectangles by one, so there is nothing to write.
        if m.get('evId') is None:
            continue
        map_id, tag = str(m['mapId']), f"{m['mapId']}:{m['evId']}"
        seen.add(tag)
        if fix.skip(map_id):
            continue
        got = melon_sprite(map_id, m['evId'])
        r = fix.rect(map_id, got[0], m['x'], m['y'], f'melon ev{m["evId"]}', got[1]) \
            if got else None
        melons[tag] = r if r else melons.pop(tag, None)
    # A melon that no longer exists should not keep a rectangle.
    melons = {k: v for k, v in melons.items() if v and k in seen}
    melon_path.write_text(json.dumps(melons, indent=1))
    print(f'  ✓ melon_art.json: {len(melons)} watermelon(s), '
          f'{fix.measured - before} measured')

    total = fix.measured + fix.ruled
    print(f'\n{fix.measured}/{total} sprite(s) found in the shipped art '
          f'({fix.measured * 100 // max(1, total)}%); {fix.skipped} render to nothing.')
    exact = fix.moved[(0, 0)]
    print(f'of those, {exact} were already right and {fix.measured - exact} moved.')
    if fix.share:
        whole = sum(1 for s in fix.share if s > 0.999)
        print(f'{whole} matched every solid pixel; the rest were partly covered '
              f'(worst {min(fix.share):.0%}).')
    print('\ncorrections (dx, dy) -> count:')
    for k, v in fix.moved.most_common(12):
        print(f'  {k}: {v}')
    if fix.big:
        print('\nfurthest moved:')
        for _, line in sorted(fix.big, reverse=True)[:12]:
            print(f'  {line}')


if __name__ == '__main__':
    main()
