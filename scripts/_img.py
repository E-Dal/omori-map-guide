"""How a render gets written, in one place.

Pillow picks the format from the suffix, and for `.webp` its default is *lossy*.
On pixel art that is both wrong and, absurdly, bigger: a map render saved at
q90 comes out three to seven times the size of the PNG, with every hard edge
smeared. Lossless is smaller *and* exact — 87 MB of raw_pngs becomes about 22.

Lossless WebP also drops the RGB under fully transparent pixels by default,
because nothing can see it and throwing it away compresses better. That is
exactly the thing 32_bleed_deco_edges.py spends its time setting, so `exact`
turns it off. It costs nothing measurable — the same 45-file sample came out
within 0.0% either way.

No script writes a render with im.save() directly; they come through here.

    from _img import save
    save(canvas, out_path)
"""
from pathlib import Path

# method 6 is the slowest search and about 3% smaller than method 4. These
# files are written once and served forever, so the encoder gets the time.
WEBP = {'lossless': True, 'quality': 100, 'method': 6, 'exact': True}


def save(im, path, **kw):
    """Write `im` to `path`, with the right options for whatever it ends in."""
    path = Path(path)
    opts = {**WEBP, **kw} if path.suffix.lower() == '.webp' else kw
    im.save(path, **opts)
    return path
