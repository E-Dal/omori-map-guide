#!/usr/bin/env python3
"""Record what has to be true before a point exists, so the guide can say so.

Roughly one marker in five is on an event page that is gated: the item is not
in the world until a switch is on. The TV girl's coffee-machine errand is the
clearest case — THINGAMABOB, DOOHICKEY and WHATCHAMACALLIT are three sparkles
that look exactly like the other 33, and none of the three is there until
you have taken her list. Map100's SPAGHETTI watermelon is the same: it drops
out of the pinwheel only once KEL has been tagged into throwing at it.

Without this, a marker over bare ground reads as the guide being wrong.

The condition that matters is on the page the marker was extracted from, not
on page 0. A pickup normally lives on a later page behind the switch that arms
it, with an invisible DEV_TEST placeholder on page 0 — reading page 0 finds no
condition and reports the point as always available, which is backwards. The
page is matched by the sprite the extractor recorded, `sheet|index|dir|pattern`,
the same key 28/29 use.

Self-switches are deliberately ignored. A self-switch condition means "after
you have already dealt with this event", which is the *taken* page of a pickup,
not a requirement for finding it.

Switch names are the game's own labels and are kept verbatim: 'Q- Coffee
Machine (Start)' says more, and says it more honestly, than anything worth
paraphrasing.

Writes `requires` back into data/collectibles.json and into the watermelons in
each data/<region>_highlights.json. Run after 23 (and after 01, which writes
the highlights).

    python3 scripts/30_extract_requirements.py
    python3 scripts/30_extract_requirements.py --dry-run
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DECRYPTED = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')

_maps = {}
_system = None


def system():
    global _system
    if _system is None:
        _system = json.loads((DECRYPTED / 'System.json').read_text())
    return _system


def map_data(map_id):
    """Events for a map id, following sliced sub-maps back to their parent.

    05_cut_submaps.py names a slice by appending a part number — 98 becomes
    981 and 982, 428 becomes 4281 — so a slice has no map file of its own and
    carries its parent's events. Dropping trailing digits until a file turns up
    handles both that and plain ids, and is the only rule that gets 981 (map
    98, part 1) and 1932 (map 193, part 2) both right.
    """
    key = str(map_id)
    if key in _maps:
        return _maps[key]
    probe = key
    while probe:
        path = DECRYPTED / f'Map{int(probe):03d}.json'
        if path.exists():
            _maps[key] = json.loads(path.read_text())
            return _maps[key]
        probe = probe[:-1]
    _maps[key] = None
    return None


def event_of(map_id, ev_id):
    m = map_data(map_id)
    if not m:
        return None
    return next((e for e in (m.get('events') or []) if e and e['id'] == ev_id), None)


def page_of(event, sprite):
    """The page this marker was drawn from, found by its recorded sprite."""
    parts = (sprite or '').split('|')
    if len(parts) == 4:
        sheet, index, direction, pattern = parts
        for page in event['pages']:
            im = page['image']
            if (im['characterName'] == sheet
                    and str(im['characterIndex']) == index
                    and str(im['direction']) == direction
                    and str(im['pattern']) == pattern):
                return page
    return event['pages'][0] if event['pages'] else None


def requirements(page):
    sysd = system()
    switches, variables = sysd['switches'], sysd['variables']
    cond = page['conditions']
    out = []
    if cond.get('switch1Valid'):
        out.append(switches[cond['switch1Id']])
    if cond.get('switch2Valid'):
        out.append(switches[cond['switch2Id']])
    if cond.get('variableValid'):
        out.append(f"{variables[cond['variableId']]} ≥ {cond['variableValue']}")
    # A switch with no name is a switch nobody bothered to label; naming it
    # 'Switch 412' in the guide would be worse than saying nothing.
    return [s.strip() for s in out if s and s.strip()]


def annotate(map_id, ev_id, sprite):
    """None when the event cannot be found, [] when it is ungated."""
    event = event_of(map_id, ev_id)
    if not event or not event['pages']:
        return None
    page = page_of(event, sprite)
    return requirements(page) if page else None


def main():
    dry = '--dry-run' in sys.argv
    if not DECRYPTED.exists():
        print(f'❌ decrypted map data not found at {DECRYPTED}')
        sys.exit(1)

    # ---- collectibles.json ----
    path = DATA / 'collectibles.json'
    col = json.loads(path.read_text())
    gated = missing = 0
    for p in col['points']:
        req = annotate(p['mapId'], p['evId'], p.get('sprite'))
        if req is None:
            missing += 1
            p.pop('requires', None)
            continue
        if req:
            gated += 1
            p['requires'] = req
        else:
            p.pop('requires', None)
    print(f'  collectibles.json: {gated} of {len(col["points"])} points gated'
          + (f', {missing} event(s) not found' if missing else ''))
    if not dry:
        path.write_text(json.dumps(col, indent=1))

    # ---- watermelons in each region's highlights ----
    total = 0
    for path in sorted(DATA.glob('*_highlights.json')):
        h = json.loads(path.read_text())
        melons = h.get('watermelons') or []
        if not melons:
            continue
        n = 0
        for w in melons:
            # Orange Oasis's Tomb Prize is placed by hand rather than lifted
            # from an event, so there is no page to read a condition off.
            if 'evId' not in w:
                w.pop('requires', None)
                continue
            req = annotate(w['mapId'], w['evId'], w.get('sprite'))
            if req:
                w['requires'] = req
                n += 1
            else:
                w.pop('requires', None)
        total += n
        if n:
            print(f'  {path.name}: {n} of {len(melons)} watermelons gated')
        if not dry:
            path.write_text(json.dumps(h, indent=1))
    print(f'  watermelons gated in total: {total}')
    if dry:
        print('  (--dry-run: nothing written)')


if __name__ == '__main__':
    main()
