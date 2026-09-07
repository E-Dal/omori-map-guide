#!/usr/bin/env python3
"""Pull the game's own Chinese names for every item, weapon and charm.

The atlas reads its item names out of `omori_data_decrypted`, which is an
English build, so `collectibles.json` says GRAPE SODA and HECTOR. The clues on
the HANGMAN keys come from somewhere else entirely — 31_blackletter_clues.py
reads the *installed* copy, which is the Simplified Chinese build, so they say
在树桩旁边的草丛中. One bubble, two languages, and neither switchable.

This closes that. The two builds number their rows identically: 346 item ids
carry a name on both sides, 49 weapons and 110 armors, and every one of them
lines up (id 2 is COLD STEAK and 冷冻牛排, id 50 is HECTOR and 赫克托). So the
Chinese name can be keyed by the English one and index.html can swap them at
render time without collectibles.json having to change at all.

Everything here is the game's own translation, not mine.

    python3 scripts/37_extract_zh_names.py
    python3 scripts/37_extract_zh_names.py --dry-run
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
OUT = DATA / 'names_zh.json'
DUMP = Path('/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted')
GAME = (Path.home() / 'Library/Application Support/Steam/steamapps/common/OMORI'
        / 'OMORI.app/Contents/Resources/app.nw')
KEY = _keys.aubrey_key()

TABLES = [('Items', 'Items.KEL', 'Items.json'),
          ('Weapons', 'Weapons.KEL', 'Weapons.json'),
          ('Armors', 'Armors.KEL', 'Armors.json')]

HAS_HAN = re.compile(r'[一-鿿]')


def decrypt_json(path):
    raw = path.read_bytes()
    cipher = AES.new(KEY, AES.MODE_CTR, initial_value=raw[:16], nonce=b'')
    return json.loads(cipher.decrypt(raw[16:]).decode('utf-8'))


def main():
    dry = '--dry-run' in sys.argv[1:]
    if not GAME.exists():
        sys.exit(f'No installed OMORI at {GAME} — this needs the Chinese build.')

    names, clashes, skipped = {}, {}, 0
    for label, kel, dump in TABLES:
        zh = decrypt_json(GAME / 'data' / kel)
        en = json.loads((DUMP / dump).read_text())   # the dump is already plain
        paired = 0
        for i in range(min(len(zh), len(en))):
            a, b = zh[i], en[i]
            if not a or not b:
                continue
            zh_name, en_name = (a.get('name') or '').strip(), (b.get('name') or '').strip()
            if not zh_name or not en_name or not HAS_HAN.search(zh_name):
                continue
            paired += 1
            # Two ids can share an English name — usually a real duplicate row.
            # Keep the first and only complain when the translations disagree.
            if en_name in names and names[en_name] != zh_name:
                clashes.setdefault(en_name, {names[en_name]}).add(zh_name)
                continue
            names[en_name] = zh_name
        print(f'  {label:<8} {paired} name(s) with a Chinese counterpart')
        skipped += paired

    for en_name, zh_set in sorted(clashes.items()):
        print(f'  ⚠ {en_name}: the build gives it more than one Chinese name '
              f'({", ".join(sorted(zh_set))}) — kept {names[en_name]}')

    payload = {
        'note': 'English name -> the Simplified Chinese build\'s name for the same '
                'row id. Written by scripts/37_extract_zh_names.py; this is the '
                "game's own translation.",
        'names': dict(sorted(names.items())),
    }
    if not dry:
        OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))

    # The names that actually reach the atlas are the ones collectibles.json
    # hands to a popup, so report the coverage that matters rather than the
    # total, which counts hundreds of items no marker ever mentions.
    col = DATA / 'collectibles.json'
    if col.exists():
        used = {n for p in json.loads(col.read_text())['points'] for n in (p.get('items') or [])}
        used = {n for n in used if not n.endswith(' CLAMS')}   # 'CLAMS' is a layer, not an item
        missing = sorted(n for n in used if n not in names)
        print(f'\n{len(names)} name(s) written'
              f'\ncollectibles.json names {len(used)} distinct item(s); '
              f'{len(used) - len(missing)} have a Chinese name')
        if missing:
            print('  no translation for: ' + ', '.join(missing[:20])
                  + (f' … and {len(missing) - 20} more' if len(missing) > 20 else ''))
    if not dry:
        print(f'wrote {OUT.relative_to(ROOT)}')
    else:
        print('[dry run]')


if __name__ == '__main__':
    main()
