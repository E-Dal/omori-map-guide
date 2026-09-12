#!/usr/bin/env python3
"""Cut one image to the shape of another's transparency.

Cutting a sprite out of a map render is slow and fiddly, and Faraway Town ships
the same street three times — day, sunset, night. The shape is identical in all
three; only the colours differ. So cut it once, and let the other two be cut to
match: this reads where the first image is opaque and erases everything outside
that shape in the others, pixel for pixel.

    python3 scripts/42_cut_like.py tree_day.png tree_sunset.png tree_night.png
        writes tree_sunset.cut.png and tree_night.cut.png beside their inputs

    python3 scripts/42_cut_like.py mask.png a.png --inplace     overwrite a.png
    python3 scripts/42_cut_like.py mask.png a.png --trim        crop to the shape
    python3 scripts/42_cut_like.py mask.png a.png -o out/       choose a folder
    python3 scripts/42_cut_like.py mask.png --show              just describe the mask

Images must be the same size; --offset X,Y shifts the mask first, for a target
that is the same art in a different place. --threshold sets how opaque a pixel
has to be to count as kept (default 1: anything not fully transparent).
"""
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit('needs Pillow:  python3 -m pip install pillow')


def describe(mask, name):
    w, h = mask.size
    kept = sum(1 for v in mask.getdata() if v)
    box = mask.getbbox()
    pct = kept / (w * h) * 100 if w * h else 0
    print(f'  {name}: {w}x{h}, {kept:,} px kept ({pct:.1f}%)'
          + (f', shape spans {box[2]-box[0]}x{box[3]-box[1]} at ({box[0]},{box[1]})'
             if box else ', nothing opaque'))
    return box


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mask', type=Path, help='the image whose shape to copy')
    ap.add_argument('targets', type=Path, nargs='*', help='images to cut')
    ap.add_argument('-o', '--out-dir', type=Path)
    ap.add_argument('--inplace', action='store_true')
    ap.add_argument('--trim', action='store_true', help='crop the result to the shape')
    ap.add_argument('--offset', default='0,0', help='shift the mask by X,Y first')
    ap.add_argument('--threshold', type=int, default=1)
    ap.add_argument('--show', action='store_true', help='describe the mask and stop')
    args = ap.parse_args()

    src = Image.open(args.mask).convert('RGBA')
    mask = src.split()[3].point(lambda v: 255 if v >= args.threshold else 0)
    dx, dy = (int(v) for v in args.offset.split(','))
    if (dx, dy) != (0, 0):
        shifted = Image.new('L', mask.size, 0)
        shifted.paste(mask, (dx, dy))
        mask = shifted
    box = describe(mask, args.mask.name)
    if args.show or not args.targets:
        return
    if not box:
        sys.exit('  the mask is fully transparent — nothing would be kept')

    for t in args.targets:
        img = Image.open(t).convert('RGBA')
        if img.size != mask.size:
            print(f'  ⚠ {t.name}: {img.size[0]}x{img.size[1]} against the mask\'s '
                  f'{mask.size[0]}x{mask.size[1]} — skipped (use --offset, or resize first)')
            continue
        # Keep the target's own alpha where it is already softer than the mask,
        # so an anti-aliased edge is not squared off by a hard cut.
        a = Image.frombytes('L', img.size,
                            bytes(min(p, m) for p, m in zip(img.split()[3].getdata(),
                                                            mask.getdata())))
        out = img.copy()
        out.putalpha(a)
        if args.trim:
            b = out.getbbox()
            if b:
                out = out.crop(b)
        dest = (t if args.inplace
                else (args.out_dir or t.parent) / f'{t.stem}.cut{t.suffix}')
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.save(dest)
        kept = sum(1 for v in out.split()[3].getdata() if v)
        print(f'  {t.name} -> {dest.name}   {out.size[0]}x{out.size[1]}, {kept:,} px kept')


if __name__ == '__main__':
    main()
