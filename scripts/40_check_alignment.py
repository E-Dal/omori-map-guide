#!/usr/bin/env python3
"""Find maps that do not line up with the neighbours the game says they touch.

A transfer whose departure tile sits on one map's edge and whose arrival tile
sits on the opposite edge of another is a statement about geometry: those two
maps abut, and the shared axis has to match exactly. The layout is arranged by
hand, so a map can be a few tiles out and look almost right — which is how the
same regions kept coming back "offset" with no way to tell which map was wrong.

Every such pair is checked here and the offset reported in pixels. A map's other
edges are listed too: when they are all satisfied and one is not, that one map
is what to move, and by how much. When two maps in a chain each have a satisfied
edge of their own, the chain does not close and moving either breaks something
else — those are called out separately, since they need a decision rather than a
nudge.

Transfers that jump rather than abut show up as huge offsets; anything past
--max-gap is treated as one of those and skipped.

    python3 scripts/40_check_alignment.py
    python3 scripts/40_check_alignment.py --region pyrefly_forest
    python3 scripts/40_check_alignment.py --max-gap 2000
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TILE = 32
OPP = {'L': 'R', 'R': 'L', 'T': 'B', 'B': 'T'}


# Gaps that are meant to be there, keyed "<a>:<b>:<side>" with the offset in
# pixels. A map's edge can carry two doors, and only one of the two maps behind
# them can abut it — the other is set a little apart and reached by a drawn
# route instead. That is a layout decision, not a mistake, and re-closing one
# undoes deliberate work. Recorded so the checker stays quiet about them and
# still speaks up the moment an offset changes or a new one appears.
KNOWN_GAPS = {
    '92:99:R':    192,   # FOREST PLAYGROUND ↔ PINWHEEL FOREST EAST
    '131:331:L': -224,   # FROZEN LAKE ↔ PATH TO FROZEN LAKE
    '172:177:R':  800,   # FOYER ↔ RIGHT HALL
    '160:336:T':  -64,   # PYREFLY V ↔ PYREFLY TO SWEETHEART
    '153:154:T': -160,   # PYREFLY I ↔ PYREFLY II
}


def gap_key(ai, bi, side):
    return f'{ai}:{bi}:{side}'


def load():
    lay = json.loads((ROOT / 'data/stitched/all_regions_layout.json').read_text())['layout']
    meta, owner = {}, {}
    for f in sorted(glob.glob(str(ROOT / 'data/*_maps.json'))):
        reg = os.path.basename(f)[:-len('_maps.json')]
        for mid, m in json.loads(Path(f).read_text()).items():
            meta.setdefault(mid, m)
            owner.setdefault(mid, reg)
    edges = []
    for f in sorted(glob.glob(str(ROOT / 'data/*_edges.json'))):
        d = json.loads(Path(f).read_text())
        for kind in ('internal', 'external'):
            edges.extend(d.get(kind, []))
    return lay, meta, owner, edges


def sides(meta, mid, x, y):
    m = meta.get(mid)
    if not m or x is None or y is None:
        return []
    w, h, out = m['width'], m['height'], []
    if x <= 0: out.append('L')
    if x >= w - 1: out.append('R')
    if y <= 0: out.append('T')
    if y >= h - 1: out.append('B')
    return out


def constraints(lay, meta, edges, max_gap):
    """mapId -> [(neighbour, which side of me it is on, axis, px I must move)]."""
    cons, seen, skipped, accepted = defaultdict(list), set(), 0, []
    for e in edges:
        a, b = e['from'], e['to']
        ai, bi = str(a.get('mapId')), str(b.get('mapId'))
        if ai not in lay or bi not in lay or ai == bi:
            continue
        touch = [s for s in sides(meta, ai, a.get('x'), a.get('y'))
                 if OPP[s] in sides(meta, bi, b.get('x'), b.get('y'))]
        if not touch:
            continue
        side = touch[0]
        if (ai, bi, side) in seen:
            continue
        seen.add((ai, bi, side))
        A, B, ma, mb = lay[ai], lay[bi], meta[ai], meta[bi]
        if side == 'R':   off, axis = B['x'] - (A['x'] + ma['width'] * TILE), 'x'
        elif side == 'L': off, axis = B['x'] - (A['x'] - mb['width'] * TILE), 'x'
        elif side == 'B': off, axis = B['y'] - (A['y'] + ma['height'] * TILE), 'y'
        else:             off, axis = B['y'] - (A['y'] - mb['height'] * TILE), 'y'
        if abs(off) > max_gap:
            skipped += 1
            continue
        # An accepted gap is treated as though it closed: the pair is checked
        # against the number that was signed off, so a change still shows.
        for key in (gap_key(ai, bi, side), gap_key(bi, ai, OPP[side])):
            if key in KNOWN_GAPS:
                if off == KNOWN_GAPS[key] or -off == KNOWN_GAPS[key]:
                    off = 0
                    accepted.append(key)
                break
        cons[bi].append((ai, side, axis, off))
        cons[ai].append((bi, OPP[side], axis, -off))
    return cons, len(seen), skipped, accepted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region')
    ap.add_argument('--max-gap', type=int, default=1000)
    args = ap.parse_args()

    lay, meta, owner, edges = load()
    cons, pairs, skipped, accepted = constraints(lay, meta, edges, args.max_gap)
    name = lambda m: (meta[m].get('name') or '').replace('-- ', '')[:26]

    broken = {m for m, cs in cons.items() if any(c[3] for c in cs)}
    if args.region:
        broken = {m for m in broken if owner.get(m) == args.region}
    print(f'{pairs} abutting pair(s) checked, {skipped} skipped as jumps '
          f'(> {args.max_gap}px apart), {len(set(accepted))} deliberate gap(s) accepted')
    if not broken:
        print('every map lines up with the neighbours it touches')
        return

    # A map whose every other edge is satisfied can simply be moved; two maps
    # that each have a satisfied edge of their own cannot both be right.
    simple, tangled = [], []
    for m in sorted(broken, key=int):
        bad = [c for c in cons[m] if c[3]]
        good_same_axis = [c for c in cons[m] if not c[3] and c[2] == bad[0][2]]
        (tangled if good_same_axis else simple).append((m, bad, good_same_axis))

    if simple:
        print(f'\n{len(simple)} map(s) can be moved on their own:')
        for m, bad, _ in simple:
            nb, side, axis, off = bad[0]
            print(f'  map{m} "{name(m)}" [{owner.get(m)}] at ({lay[m]["x"]},{lay[m]["y"]})')
            # off is how far out it currently is; the move is the other way.
            print(f'      move {axis} by {-off:+}px  — its {side} side meets '
                  f'map{nb} "{name(nb)}", and it has no other edge to break')
    if tangled:
        print(f'\n{len(tangled)} map(s) are in a chain that does not close:')
        for m, bad, good in tangled:
            print(f'  map{m} "{name(m)}" [{owner.get(m)}] at ({lay[m]["x"]},{lay[m]["y"]})')
            for nb, side, axis, off in bad:
                print(f'      {side} meets map{nb} "{name(nb)}" — off by {off:+}px')
            for nb, side, axis, off in good:
                print(f'      {side} meets map{nb} "{name(nb)}" — already aligned, '
                      f'moving would break it')


if __name__ == '__main__':
    main()
