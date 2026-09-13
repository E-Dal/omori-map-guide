#!/usr/bin/env python3
"""Re-encode the map renders as lossless WebP and drop the PNGs.

The renders are the whole download. One World view of Vast Forest pulls 2.7 MB
of them; the folder is 87 MB. Lossless WebP takes that to about 22, and because
it is lossless the picture is the same picture — every file here is decoded
back and compared pixel for pixel before its PNG is removed, and anything that
does not match is left alone and reported.

Lossy would be the wrong tool twice over: pixel art is all hard edges, so it
both smears and *grows* — the same map at q90 is three to seven times the size
of its PNG.

Idempotent. A PNG whose .webp already exists and matches is just cleaned up.

    python3 scripts/44_png_to_webp.py --dry-run
    python3 scripts/44_png_to_webp.py
    python3 scripts/44_png_to_webp.py --keep      # convert, leave the PNGs
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _img import save  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'data' / 'raw_pngs'


def main(argv):
    dry = '--dry-run' in argv
    keep = '--keep' in argv
    files = sorted(TARGET.rglob('*.png'))
    if not files:
        sys.exit(f'no PNGs under {TARGET}')

    png_bytes = webp_bytes = 0
    converted = skipped = failed = 0
    for i, src in enumerate(files, 1):
        dst = src.with_suffix('.webp')
        im = Image.open(src).convert('RGBA')
        png_bytes += src.stat().st_size
        if dry:
            print(f'  [{i}/{len(files)}] would write {dst.relative_to(TARGET)}')
            continue
        save(im, dst)
        # The point of lossless is that this holds. Check it rather than
        # believe it: a silent colour shift across 871 renders would be found
        # weeks later, by eye, on one map.
        back = Image.open(dst).convert('RGBA')
        if not np.array_equal(np.asarray(im), np.asarray(back)):
            print(f'  ⚠ {src.name}: round-trip differs — PNG kept', file=sys.stderr)
            dst.unlink(missing_ok=True)
            failed += 1
            continue
        webp_bytes += dst.stat().st_size
        converted += 1
        if not keep:
            src.unlink()
        if i % 50 == 0 or i == len(files):
            print(f'  [{i}/{len(files)}] {webp_bytes / 1048576:.1f} MB written', flush=True)

    if dry:
        print(f'\n[dry run] {len(files)} file(s), {png_bytes / 1048576:.1f} MB of PNG')
        return
    print(f'\n{converted} converted, {failed} left as PNG, {skipped} skipped')
    if webp_bytes:
        print(f'{png_bytes / 1048576:.1f} MB → {webp_bytes / 1048576:.1f} MB '
              f'({100 - webp_bytes / png_bytes * 100:.0f}% smaller)')


if __name__ == '__main__':
    main(sys.argv[1:])
