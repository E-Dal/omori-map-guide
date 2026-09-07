#!/usr/bin/env python3
"""Give routes that run close together different colours.

The stitcher hands each new route the next colour off a 10-entry wheel
(`ROUTE_COLORS[routes.length % 10]`), so a route's colour says nothing about
what it is — it exists only to tell one dashed line apart from the one beside
it. Draw enough of them and the wheel comes round to a route that happens to
sit right next to one already wearing that colour, and the two read as one.

So: build the graph of routes that pass within --min-gap of each other, and
colour it. A route keeps the colour it has whenever that colour is still free,
which keeps the change small and the file's diff readable.

Ten colours cannot always win — a route with more than nine close neighbours
has no free colour left by definition. Those are reported rather than papered
over, and get the colour whose nearest same-coloured neighbour is furthest
away, which is the least bad answer available.

  python3 scripts/33_recolor_close_routes.py [layout.json] [--min-gap PX] [--dry-run]
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path

# Must stay in step with ROUTE_COLORS in web/stitcher_all.html, so a file that
# has been through here still looks native when it is imported back.
ROUTE_COLORS = ['#ff66d9', '#33ccff', '#66ff66', '#ffcc33', '#ff7733',
                '#bb88ff', '#ff5566', '#22eebb', '#eeaa44', '#88ddff']

DEFAULT_LAYOUT = Path(__file__).resolve().parent.parent / 'data' / 'stitched' / 'all_regions_layout.json'


def _lab(hex_colour):
    """sRGB hex → CIE L*a*b*, so 'looks the same' can be measured rather than guessed."""
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    t = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116
    fx, fy, fz = t(x), t(y), t(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


LAB = {c: _lab(c) for c in ROUTE_COLORS}


def looks_same(a, b, min_de):
    """Identical always counts; beyond that it is a question of degree."""
    return a == b or delta_e(a, b) < min_de


def delta_e(a, b):
    """CIE76. Crude next to CIEDE2000 and quite good enough to separate ten
    colours: it puts the two blues 14 apart and the two yellows 22, which is
    exactly the pair of complaints the eye makes about this palette."""
    la, lb = LAB.get(a), LAB.get(b)
    if la is None or lb is None:
        return math.inf if a != b else 0.0
    return math.dist(la, lb)


def snap_ids(route):
    """The transfer events a route's ends are pinned to. Two routes hanging off
    the same door read as one line through it however far apart their far ends
    are, so sharing one counts as touching even when the geometry does not."""
    out = set()
    for p in route['pts']:
        s = p.get('snap')
        if s and s.get('mapId') is not None:
            out.add(f"{s['mapId']}:{s.get('evId')}")
    return out


def _point_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _crosses(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = side(c, d, a), side(c, d, b)
    d3, d4 = side(a, b, c), side(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def seg_distance(r1, r2):
    """Closest approach of two route segments, in world pixels."""
    a = (r1['pts'][0]['x'], r1['pts'][0]['y'])
    b = (r1['pts'][1]['x'], r1['pts'][1]['y'])
    c = (r2['pts'][0]['x'], r2['pts'][0]['y'])
    d = (r2['pts'][1]['x'], r2['pts'][1]['y'])
    if _crosses(a, b, c, d):
        return 0.0
    # No crossing, so the closest approach is at one of the four endpoints.
    return min(_point_seg(*a, *c, *d), _point_seg(*b, *c, *d),
               _point_seg(*c, *a, *b), _point_seg(*d, *a, *b))


def label(routes, i):
    r = routes[i]
    names = [p.get('snap', {}).get('evName') for p in r['pts'] if p.get('snap')]
    where = ' → '.join(n for n in names if n) or f"({r['pts'][0]['x']}, {r['pts'][0]['y']})"
    return f'#{i} {where}'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('layout', nargs='?', type=Path, default=DEFAULT_LAYOUT)
    ap.add_argument('--min-gap', type=float, default=500.0,
                    help='routes closer than this (world px) must not share a colour '
                         '(default: 500, about 16 tiles)')
    ap.add_argument('--min-de', type=float, default=50.0,
                    help='colours closer than this in CIE76 count as the same colour '
                         '(default: 50, which catches green/teal, the two blues and '
                         'the two yellows; 0 compares colours exactly)')
    ap.add_argument('--dry-run', action='store_true', help='report, change nothing')
    args = ap.parse_args(argv)

    data = json.loads(args.layout.read_text())
    routes = data.get('routes') or []
    if not routes:
        sys.exit(f'{args.layout} has no routes')
    n = len(routes)

    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist[i][j] = dist[j][i] = seg_distance(routes[i], routes[j])
    snaps = [snap_ids(r) for r in routes]
    close = [[j for j in range(n) if j != i and
              (dist[i][j] < args.min_gap or (snaps[i] & snaps[j]))] for i in range(n)]
    shared_only = sum(1 for i in range(n) for j in close[i]
                      if i < j and dist[i][j] >= args.min_gap)

    # Two routes that meet at exactly the same point and already wear the same
    # colour are one journey drawn in two hops — Elevator → Door → Elevator
    # through the castle. Their shared colour is the whole point of them, so
    # they are coloured as a single unit rather than pulled apart.
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    ends = [{(p['x'], p['y']) for p in r['pts']} for r in routes]
    for i in range(n):
        for j in range(i + 1, n):
            if routes[i]['color'] == routes[j]['color'] and ends[i] & ends[j]:  # exact: a chain was drawn one colour
                union(i, j)
    chains = {}
    for i in range(n):
        chains.setdefault(find(i), []).append(i)
    linked = {i: set(g) for g in chains.values() for i in g}
    if any(len(g) > 1 for g in chains.values()):
        print('chains kept whole (same colour, meeting at a point):')
        for g in chains.values():
            if len(g) > 1:
                print(f'    {routes[g[0]]["color"]}  ' + '  ·  '.join(label(routes, i) for i in g))

    for i in range(n):
        close[i] = [j for j in close[i] if j not in linked[i]]

    before = [(i, j) for i in range(n) for j in close[i]
              if i < j and looks_same(routes[i]['color'], routes[j]['color'], args.min_de)]
    print(f'{n} routes · {sum(len(c) for c in close) // 2} adjacent pairs '
          f'({args.min_gap:.0f}px apart or closer, or pinned to the same transfer; '
          f'{shared_only} of them only because they share one) '
          f'· {len(before)} of those wear colours within ΔE {args.min_de:.0f} of each other')
    for i, j in before:
        print(f'    {dist[i][j]:6.0f}px  {routes[i]["color"]}  {label(routes, i)}  ×  {label(routes, j)}')

    # Not every conflict is equally bad, and in the tangle of eleven "To Abyss"
    # routes inside ABYSS LOWER 4 every colour conflicts with something — eight
    # of the ten are already in use within 500px, so counting conflicts alone
    # leaves every choice tied and the route keeps whatever it had. What made
    # the yellow and the orange there unreadable was not that they conflicted
    # but that they conflicted *badly*: 10px apart at ΔE 22. Swapping one to
    # #ff7733 still conflicts, with a route 119px away at ΔE 37, and that is a
    # picture you can read.
    #
    # So rank a colour by its worst conflict rather than by how many it has:
    # fewest conflicts first, then the furthest away, then the least alike.
    def severity(head, near, c, colour_of):
        conflicts = [(dist[head][j], delta_e(colour_of(j), c)) for j in near
                     if colour_of(j) and looks_same(colour_of(j), c, args.min_de)]
        worst = min(conflicts, default=(math.inf, math.inf))
        return (len(conflicts), -worst[0], -worst[1])

    # Welsh-Powell: hardest routes (most close neighbours) choose first, so the
    # crowded corners are settled while the palette is still wide open.
    groups = list(chains.values())
    nbrs = {g[0]: sorted({j for i in g for j in close[i]}) for g in groups}
    order = sorted(groups, key=lambda g: -len(nbrs[g[0]]))
    original = [r['color'] for r in routes]
    assigned = [None] * n
    for g in order:
        head, near = g[0], nbrs[g[0]]
        taken = {assigned[j] for j in near if assigned[j] is not None}
        clashes = lambda c: any(looks_same(c, t, args.min_de) for t in taken)
        if not clashes(original[head]):
            pick = original[head]
        else:
            free = [c for c in ROUTE_COLORS if not clashes(c)]
            if free:
                # Among the free colours prefer the one already furthest away, so
                # a recoloured route is not merely legal but visibly separated.
                pick = max(free, key=lambda c: min(
                    [dist[head][j] for j in near if
                     (assigned[j] or original[j]) == c] or [math.inf]))
            else:
                pick = min(ROUTE_COLORS, key=lambda c: severity(head, near, c,
                                                                lambda j: assigned[j] or original[j]))
        for i in g:
            assigned[i] = pick

    # Welsh-Powell settles most of it but is not optimal: it can paint itself
    # into a corner where a later route has no free colour even though a proper
    # colouring existed. Six routes fan out of one door in Sweethearts Castle
    # and all touch at that point, which is exactly the shape that traps it.
    # A few min-conflicts passes repair that — each route in conflict takes the
    # colour with the fewest conflicts, ties going to the furthest separation.
    for _ in range(200):
        bad = [i for i in range(n)
               if any(looks_same(assigned[j], assigned[i], args.min_de) for j in close[i])]
        if not bad:
            break
        moved = False
        for head in {find(i) for i in bad}:
            g, near = chains[head], nbrs[head]
            def cost(c):
                # keeping the original colour breaks ties, so the diff stays small
                return severity(head, near, c, lambda j: assigned[j]) + (c != original[head],)
            best = min(ROUTE_COLORS, key=cost)
            if cost(best) < cost(assigned[head]):
                for i in g:
                    assigned[i] = best
                moved = True
        if not moved:
            break

    changed = [i for i in range(n) if assigned[i] != original[i]]
    after = [(i, j) for i in range(n) for j in close[i]
             if i < j and looks_same(assigned[i], assigned[j], args.min_de)]

    print(f'\nrecoloured {len(changed)} route(s); '
          f'same-colour close pairs {len(before)} -> {len(after)}')
    for i in changed:
        print(f'    {label(routes, i)}: {original[i]} -> {assigned[i]}')
    if after:
        print(f'\n{len(after)} pair(s) could not be separated — a route with more than '
              f'{len(ROUTE_COLORS) - 1} close neighbours has no free colour left:')
    for i, j in after:
        print(f'    still sharing: {dist[i][j]:6.0f}px  {assigned[i]}  '
              f'{label(routes, i)}  ×  {label(routes, j)}')

    if args.dry_run:
        print('\n--dry-run: nothing written')
        return
    if not changed:
        print('\nnothing to change')
        return

    backup = args.layout.with_suffix('.json.bak-recolor')
    shutil.copy2(args.layout, backup)
    for i in range(n):
        routes[i]['color'] = assigned[i]
    # indent=2 / ensure_ascii=False reproduces the stitcher's own
    # JSON.stringify(data, null, 2) byte for byte, so only colours move.
    args.layout.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    print(f'\nwrote {args.layout}  (backup: {backup.name})')


if __name__ == '__main__':
    main()
