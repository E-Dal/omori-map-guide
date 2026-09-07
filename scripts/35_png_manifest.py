#!/usr/bin/env python3
"""Record each map PNG's modification time, so the pages can version their URLs.

`python3 -m http.server` sends no Cache-Control, so a browser holds on to a map
render for as long as its own heuristics say — and these files are rewritten
often. SOLAR SYSTEM went from a wrong black-and-white render to the right one
and the stitcher kept drawing the old bytes; the server had the new file all
along.

`?fresh` in the page URL already forces every image to reload, but that is
something to remember, and it dumps the entire ~580-file cache to pick up one
changed render. Versioning each URL by its own mtime fixes both ends: an
unchanged PNG keeps being served from cache, and a changed one has a different
URL the moment it changes, so it cannot be stale.

Written after any script that renders a PNG; run it by hand after replacing one
some other way.

    python3 scripts/35_png_manifest.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PNG_DIR = ROOT / 'data' / 'raw_pngs'
OUT = PNG_DIR / 'manifest.json'


def rebuild():
    """{filename: mtime as whole seconds}. Seconds are plenty — nothing here
    changes twice in one second, and it keeps the file small."""
    if not PNG_DIR.is_dir():
        return {}
    entries = {p.name: int(p.stat().st_mtime)
               for p in sorted(PNG_DIR.glob('*.png'))}
    OUT.write_text(json.dumps(entries, separators=(',', ':'), sort_keys=True))
    return entries


if __name__ == '__main__':
    e = rebuild()
    print(f'{len(e)} PNG(s) → {OUT.relative_to(ROOT)}')
