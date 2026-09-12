#!/usr/bin/env python3
"""Make the two decoration tables agree with the PNGs on disk.

Scenery lives in four places that have to say the same thing: the file in
web/assets/decorations, DECORATIONS in the stitcher (which fills its dropdown),
DECO_ART in the atlas (which draws it) and a third copy in 36, which bakes the
clusters. The sizes in the two tables are the
PNG's own pixel size, and index.html's comment is blunt about why — a wrong
number there stretches every scaled copy on the map. Keeping three things in
step by hand is what this replaces: drop a PNG in the folder, run this, and the
tables are rewritten from what the files actually are.

Labels already in the stitcher are kept; a new file gets one from its name, and
you can edit it afterwards without this overwriting it next run.

    python3 scripts/41_sync_decorations.py
    python3 scripts/41_sync_decorations.py --dry-run
"""
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECO_DIR = ROOT / 'web' / 'assets' / 'decorations'
STITCHER = ROOT / 'web' / 'stitcher_all.html'
ATLAS = ROOT / 'web' / 'index.html'
BAKER = ROOT / 'scripts' / '36_bake_deco_clusters.py'


def png_size(path):
    """(w, h) straight out of the IHDR — no decode, no dependency."""
    head = path.read_bytes()[:26]
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


def existing(src):
    """[(key, label)] in the order the table already has them.

    Order is the dropdown's order, so it is the author's and not alphabet's:
    the trees come first because they are what gets used. Files already listed
    keep their place and their label; anything new lands at the end, where it
    can be moved by hand once and stay there.
    """
    m = re.search(r'const DECORATIONS = \[(.*?)\n\];', src, re.S)
    if not m:
        return []
    return re.findall(r"key: '([^']+)',\s*label: '([^']*)'", m.group(1))


def nice(key):
    """A first label for a new file: tree_part_2 -> Tree part 2."""
    return key.replace('_', ' ').capitalize()


def main():
    dry = '--dry-run' in sys.argv[1:]
    if not DECO_DIR.is_dir():
        sys.exit(f'no {DECO_DIR}')

    pngs = sorted(p for p in DECO_DIR.glob('*.png') if p.is_file())
    if not pngs:
        sys.exit(f'no PNGs in {DECO_DIR}')

    st_src = STITCHER.read_text()
    known = existing(st_src)
    labels = dict(known)
    order = [k for k, _ in known]

    by_key = {}
    for p in pngs:
        size = png_size(p)
        if not size:
            print(f'  ⚠ {p.name}: not a PNG — skipped')
            continue
        by_key[p.stem] = (f'assets/decorations/{p.name}', *size)

    gone = [k for k in order if k not in by_key]
    for k in gone:
        print(f'  ⚠ {k}: listed in the table but no PNG on disk — dropped')
    keys = [k for k in order if k in by_key] + sorted(k for k in by_key if k not in order)
    rows = [(k, labels.get(k) or nice(k), *by_key[k]) for k in keys]

    q = lambda v: f"'{v}',"
    wk = max(len(q(r[0])) for r in rows)
    wl = max(len(q(r[1])) for r in rows)
    ws = max(len(q(r[2])) for r in rows)
    deco = '\n'.join(
        f"  {{ key: {q(k):<{wk}} label: {q(l):<{wl}} src: {q(s):<{ws}} w: {w}, h: {h} }},"
        for k, l, s, w, h in rows)
    wkey = max(len(k) + 1 for k, *_ in rows)
    art = '\n'.join(
        f"  {k + ':':<{wkey}} {{ src: {q(s):<{ws}} w: {w}, h: {h} }},"
        for k, _, s, w, h in rows)

    new_st = re.sub(r'const DECORATIONS = \[\n.*?\n\];',
                    f'const DECORATIONS = [\n{deco}\n];', st_src, flags=re.S)
    at_src = ATLAS.read_text()
    new_at = re.sub(r'const DECO_ART = \{\n.*?\n\};',
                    f'const DECO_ART = {{\n{art}\n}};', at_src, flags=re.S)

    # 36 keeps its own copy, as a Python dict of (file, w, h).
    wpy = max(len(f"'{k}':") for k, *_ in rows)
    wfile = max(len(f"'{Path(s).name}',") for _, _, s, _, _ in rows)
    baked = '\n'.join(
        f"    {k + ':':<{wpy}} ({f:<{wfile}} {w}, {h}),"
        for k, f, w, h in ((f"'{k}'", f"'{Path(s).name}',", w, h)
                           for k, _, s, w, h in rows))
    bk_src = BAKER.read_text()
    new_bk = re.sub(r'DECO_ART = \{\n.*?\n\}',
                    f'DECO_ART = {{\n{baked}\n}}', bk_src, flags=re.S, count=1)

    print(f'  {len(rows)} decoration(s) in {DECO_DIR.relative_to(ROOT)}:')
    for k, l, s, w, h in rows:
        mark = '' if k in labels else '   ← new'
        print(f'    {k:<14} {w}x{h:<5} "{l}"{mark}')

    changed = (new_st != st_src) + (new_at != at_src) + (new_bk != bk_src)
    if not changed:
        print('  all three tables already match the files')
        return
    if dry:
        print(f'  [dry run] would rewrite {changed} file(s)')
        return
    if new_st != st_src:
        STITCHER.write_text(new_st)
        print(f'  wrote DECORATIONS in {STITCHER.relative_to(ROOT)}')
    if new_at != at_src:
        ATLAS.write_text(new_at)
        print(f'  wrote DECO_ART in {ATLAS.relative_to(ROOT)}')
    if new_bk != bk_src:
        BAKER.write_text(new_bk)
        print(f'  wrote DECO_ART in {BAKER.relative_to(ROOT)}')
    print('  now re-bake:  python3 scripts/36_bake_deco_clusters.py --all-below')


if __name__ == '__main__':
    main()
