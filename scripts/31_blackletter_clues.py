#!/usr/bin/env python3
"""Add the game's own HANGMAN clues, and the five keys the extractor cannot see.

Every blackletter item carries two notetags in Items:

    <Blackletter: A>
    <BlackLetterClue:在树桩旁边的草丛中>

so the game ships a one-line hint for where each of the 26 keys is. That text
is worth having on the map, and it is also the evidence that settles the five
letters nothing else could place.

**Read from the installed game, not from the decrypted dump.** The dump under
omori_data_decrypted is missing Doodads, Map513/514 and, crucially, is a build
whose item names differ — it has none of these notetags at all. Everything here
comes out of OMORI.app/…/data/Items.KEL.

## The five missing keys

23_extract_collectibles.js finds a key by the item it grants. Twenty-one turn
up that way. The other five are events named plain `BLACKLETTER` whose page
carries no sprite, no item and, in three cases, no commands at all — the pickup
is wired up elsewhere. Nothing in the event says which letter it is.

The clues say it, and each one names its map unmistakably. There are exactly
five such events on region maps and exactly five unaccounted-for letters, and
they pair off one to one:

| Letter | Clue | Event |
|---|---|---|
| A | 在树桩旁边的草丛中 — in the grass beside the stump | map89 ev7, STUMP ENTRANCE |
| B | 在一座若隐若现的老桥上 — on an old bridge that fades in and out | map101 ev3, EAST FOREST BRIDGE |
| D | 在废弃的容器附近 — near an abandoned container | map147 ev4, JUNKYARD (VI) |
| G | 在活板门底下 — under a trapdoor | map132 ev21, IGLOO INTERIOR |
| Y | 在白雪的原野中 — in a field of white snow | map134 ev16, FROZEN FOREST (I) |

G is the one worth checking rather than believing: map132 holds two events
named `Trap Door`, at (31,9) and (31,29). Map134 is 150×150 of snow.

The same method confirms itself on the letters that were already found — C is
在巨大的风车之间, "among the giant pinwheels", and C is on map100, the map with
eleven pinwheel poles on it.

Run after 23 and before 30 (which fills in `requires` for the new points).

    python3 scripts/31_blackletter_clues.py
    python3 scripts/31_blackletter_clues.py --dry-run
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _keys  # noqa: E402

from Crypto.Cipher import AES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
GAME = (Path.home() / 'Library/Application Support/Steam/steamapps/common/OMORI'
        / 'OMORI.app/Contents/Resources/app.nw')
KEY = _keys.aubrey_key()

# letter -> (map id, event id, event name). See the table in the docstring for
# why each one is what it is; the clue is checked against it at run time.
MISSING = {
    'A': ('89',  7,  'BLACKLETTER'),
    'B': ('101', 3,  'BLACKLETTER'),
    'D': ('147', 4,  'BLACKLETTER'),
    'G': ('132', 21, 'BLACKLETTER'),
    'Y': ('134', 16, 'BLACKLETTER'),
}


def decrypt_json(path):
    raw = path.read_bytes()
    cipher = AES.new(KEY, AES.MODE_CTR, initial_value=raw[:16], nonce=b'')
    return json.loads(cipher.decrypt(raw[16:]).decode('utf-8'))


def clues():
    """letter -> the game's hint text."""
    out = {}
    for item in decrypt_json(GAME / 'data/Items.KEL'):
        if not item:
            continue
        note = item.get('note') or ''
        letter = re.search(r'<Blackletter:\s*([A-Z])>', note)
        if not letter:
            continue
        clue = re.search(r'<BlackLetterClue:\s*(.*?)>', note)
        out[letter.group(1)] = (clue.group(1).strip() if clue else '')
    return out


def event_at(map_id, ev_id):
    m = decrypt_json(GAME / f'data/Map{int(map_id):03d}.KEL')
    return next((e for e in (m.get('events') or []) if e and e['id'] == ev_id), None)


def main():
    dry = '--dry-run' in sys.argv
    if not GAME.exists():
        print(f'❌ OMORI not found at {GAME}')
        sys.exit(1)

    hints = clues()
    print(f'  {len(hints)} blackletter clues read from the installed game')

    path = DATA / 'collectibles.json'
    col = json.loads(path.read_text())
    points = col['points']
    have = {p['letter'] for p in points if p['layer'] == 'hangman' and p.get('letter')}

    added = 0
    for letter, (map_id, ev_id, ev_name) in sorted(MISSING.items()):
        if letter in have:
            print(f'  · {letter} already placed — skipped')
            continue
        event = event_at(map_id, ev_id)
        if not event:
            print(f'  ⚠ {letter}: map{map_id} ev{ev_id} not found — skipped')
            continue
        if event['name'].strip().upper() != ev_name:
            print(f"  ⚠ {letter}: map{map_id} ev{ev_id} is {event['name']!r}, "
                  f'expected {ev_name!r} — skipped')
            continue
        page = event['pages'][0]
        image = page['image']
        points.append({
            'layer': 'hangman',
            'mapId': map_id,
            'x': event['x'],
            'y': event['y'],
            'evId': ev_id,
            'evName': event['name'],
            'letter': letter,
            # Kept even when it is DEV_TEST: the hangman layer draws its own
            # letter art, and 29 needs the key to know there is nothing to find.
            'sprite': f"{image['characterName']}|{image['characterIndex']}"
                      f"|{image['direction']}|{image['pattern']}",
            'prio': page['priorityType'],
            'items': [f'Blackletter {letter}'],
            # Placed from the event tile, not measured: these events draw
            # nothing, so there are no pixels in the PNG to match against.
            'placedFrom': 'clue',
        })
        added += 1
        print(f'  + {letter}: map{map_id} ev{ev_id} — {hints.get(letter, "(no clue)")}')

    # A letter can own more than one point — T is on four maps, and a sliced
    # sub-map carries a copy of its parent's — so count letters, not points.
    tagged = set()
    for p in points:
        if p['layer'] != 'hangman' or not p.get('letter'):
            continue
        clue = hints.get(p['letter'])
        if clue:
            p['clue'] = clue
            tagged.add(p['letter'])
        else:
            p.pop('clue', None)

    print(f'  {added} key(s) added; {len(tagged)} of {len(hints)} letters carry a clue')
    if dry:
        print('  (--dry-run: nothing written)')
        return
    path.write_text(json.dumps(col, indent=1))


if __name__ == '__main__':
    main()
