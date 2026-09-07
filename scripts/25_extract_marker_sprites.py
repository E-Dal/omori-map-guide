#!/usr/bin/env python3
"""Cut the atlas's marker icons out of the game's own sprite sheets.

Watermelons have always been drawn with their real sprite; emoji stand-ins for
everything else read as annotations sitting on top of the map rather than as
the thing they point at. These two are worth the same treatment:

  hangman  DW_BLACKLETTERS is a keyboard, one key per letter. Its frames are
           laid out as the usual four-across, two-down characters, three
           animation frames wide and four facings tall, and each facing is a
           different letter:

               char 0: A B C L      char 4: M T D G
               char 1: E K P O      char 5: S W F H
               char 2: I N R V      char 6: Y
               char 3: J Q U X      char 7: Z

           That reading is checked against the game rather than trusted: all 18
           BLACKLETTER_<X> events that carry a sprite agree with it, none
           disagree. The five that carry no sprite — I, M, N, O, R, which only
           appear once their room is solved — are why the table is needed at
           all.

  machine  the conveyor machine from DW_PuzzleObjects_2, the same frame
           16_render_event_sprites.py composites onto the maps.

Written to web/assets/, which is where the watermelon icons already live.

    python3 scripts/25_extract_marker_sprites.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'web' / 'assets'

_r13 = {'__name__': 'imported', '__file__': str(ROOT / 'scripts/13_render_tiled_map.py')}
exec(compile((ROOT / 'scripts/13_render_tiled_map.py').read_text(), 'r13', 'exec'), _r13)

LETTER_GRID = [
    ['A', 'B', 'C', 'L'], ['E', 'K', 'P', 'O'], ['I', 'N', 'R', 'V'], ['J', 'Q', 'U', 'X'],
    ['M', 'T', 'D', 'G'], ['S', 'W', 'F', 'H'], ['Y', '', '', ''], ['Z', '', '', ''],
]


def sheet(name):
    return _r13['load_rpgmvp_png'](_r13['GAME_ROOT'] / 'img/characters' / f'{name}.rpgmvp')


def frame(sh, index, row, col=1):
    """One frame of a normal 4x2-character, 3x4-cell sheet."""
    fw, fh = sh.width // 12, sh.height // 8
    bx, by = (index % 4) * (sh.width // 4), (index // 4) * (sh.height // 2)
    return sh.crop((bx + col * fw, by + row * fh, bx + (col + 1) * fw, by + (row + 1) * fh))


def trim(img):
    a = np.array(img)
    ys, xs = np.where(a[:, :, 3] > 0)
    if not len(ys):
        return img
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def main():
    out = ASSETS / 'hangman'
    out.mkdir(parents=True, exist_ok=True)
    keys = sheet('DW_BLACKLETTERS')
    n = 0
    for index, letters in enumerate(LETTER_GRID):
        for row, letter in enumerate(letters):
            if not letter:
                continue
            trim(frame(keys, index, row)).save(out / f'{letter}.png')
            n += 1
    print(f'  ✓ web/assets/hangman/: {n} letter key(s)')

    machine = trim(frame(sheet('DW_PuzzleObjects_2'), 0, 1))
    machine.save(ASSETS / 'machine.png')
    print(f'  ✓ web/assets/machine.png: {machine.width}x{machine.height}')


if __name__ == '__main__':
    main()
