#!/usr/bin/env python3
"""
Patch goats.dev's map renders for events it got wrong.

Per-event patches: erase an area (horizontal-nearest inpaint) and optionally
stamp the correct sprite from the decrypted character sheet.

Run: python3 scripts/07_patch_renders.py
Backs up originals as map<id>_orig.png on first run.
"""
import json, os, shutil
from pathlib import Path
from PIL import Image
import numpy as np

ROOT     = Path(__file__).resolve().parent.parent
RAW      = ROOT / 'data' / 'raw_pngs'
SPRITES  = Path('/tmp/decrypted_sprites')   # decrypted character sheets live here
T        = 32

# ── Cell extraction ─────────────────────────────────────────────────────────
def extract_cell(sheet_path, index, dollar_prefix=False):
    """Return the down-idle frame as RGBA. For non-$ sheets, layout is
    4 sets × 2 rows of 3×4 frame grids. For $ sheets, the whole sheet IS
    one character with 3 cols × 4 rows of frames."""
    im = Image.open(sheet_path).convert('RGBA')
    W, H = im.size
    if dollar_prefix:
        cw, ch = W // 3, H // 4
        x, y = cw, 0                       # middle col, top row = down idle
        return im.crop((x, y, x + cw, y + ch))
    sw, sh = W // 4, H // 2
    cw, ch = sw // 3, sh // 4
    cs, rs = index % 4, index // 4
    x = cs * sw + cw                       # middle col of the set
    y = rs * sh                            # top row (down)
    return im.crop((x, y, x + cw, y + ch))

# ── Inpainting (horizontal nearest neighbor) ────────────────────────────────
def inpaint_region(arr, mask):
    """Fill RGB of arr where mask=True by copying from nearest unmasked pixel
    in the same row (left or right). Alpha is also copied from that source.
    Returns nothing — modifies arr in place."""
    H, W = mask.shape
    for y in range(H):
        rm = mask[y]
        if not rm.any(): continue
        valid = np.where(~rm)[0]
        if len(valid) == 0: continue
        targets = np.where(rm)[0]
        idx = np.searchsorted(valid, targets)
        for tx, ii in zip(targets, idx):
            cands = []
            if ii > 0: cands.append(valid[ii-1])
            if ii < len(valid): cands.append(valid[ii])
            sx = min(cands, key=lambda c: abs(c - tx))
            arr[y, tx] = arr[y, sx]

# ── Patch helpers ───────────────────────────────────────────────────────────
def ensure_backup(map_id):
    src = RAW / f'map{map_id}.png'
    bk  = RAW / f'map{map_id}_orig.png'
    if not bk.exists() and src.exists():
        shutil.copy(src, bk)
        print(f"  backed up → {bk.name}")

def color_mask_in_region(arr, region, target_rgb, tol=8):
    """Within region (x0,y0,x1,y1), True where pixel is close to target_rgb."""
    x0, y0, x1, y1 = region
    sub = arr[y0:y1, x0:x1, :3]
    d = np.abs(sub.astype(int) - np.array(target_rgb)[None, None, :]).sum(axis=2)
    mask = np.zeros(arr.shape[:2], dtype=bool)
    mask[y0:y1, x0:x1] = d <= tol
    return mask

def patch_event(map_id, sprite_path, sprite_index, tile_x, tile_y,
                erase_box=None, erase_color=None, dollar=False, sprite_offset=(0, 0)):
    """One-shot event patch.
      - erase_box: (left, top, right, bottom) in pixel coords to inpaint over.
                   If None, derived from sprite cell size centered on the tile.
      - erase_color: if given, only erase pixels matching this RGB inside the box.
                     Otherwise erase the entire box.
      - sprite_offset: (dx, dy) tweak for sprite placement relative to anchor.
    Sprite is stamped with bottom-center at tile bottom-center."""
    ensure_backup(map_id)
    src = RAW / f'map{map_id}.png'
    im = Image.open(src).convert('RGBA')
    arr = np.array(im)

    # Sprite cell
    sprite = extract_cell(sprite_path, sprite_index, dollar_prefix=dollar) if sprite_path else None
    sw, sh = (sprite.size if sprite else (T, T))

    # Anchor: tile bottom-center → sprite bottom-center
    anchor_x = tile_x * T + T // 2
    anchor_y = (tile_y + 1) * T
    sx_left = anchor_x - sw // 2 + sprite_offset[0]
    sy_top  = anchor_y - sh + sprite_offset[1]

    # Erase box default = a bit larger than where the goats render's sprite was
    if erase_box is None:
        # Default: 1 tile wide × 2 tiles tall centered on the event tile, biased upward.
        ebw, ebh = T, T * 2
        ex0 = tile_x * T + (T - ebw) // 2
        ey0 = (tile_y + 1) * T - ebh
        erase_box = (ex0, ey0, ex0 + ebw, ey0 + ebh)
    ex0, ey0, ex1, ey1 = erase_box
    ex0 = max(0, ex0); ey0 = max(0, ey0)
    ex1 = min(arr.shape[1], ex1); ey1 = min(arr.shape[0], ey1)

    if erase_color is not None:
        mask = color_mask_in_region(arr, (ex0, ey0, ex1, ey1), erase_color, tol=20)
    else:
        mask = np.zeros(arr.shape[:2], dtype=bool)
        mask[ey0:ey1, ex0:ex1] = True
    if mask.any():
        inpaint_region(arr, mask)
        print(f"    erased {mask.sum()} px in {(ex0,ey0,ex1,ey1)}")

    out = Image.fromarray(arr)
    if sprite is not None:
        out.paste(sprite, (sx_left, sy_top), sprite)
        print(f"    stamped sprite at ({sx_left},{sy_top}) size {sw}×{sh}")
    out.save(src)
    print(f"  wrote {src.name}")

# ── Bulk-remove tiles by repeating color signature ───────────────────────────
def remove_tile_color(map_id, signature_rgb, tol=10):
    """Find ALL pixels in the map that match the signature color and inpaint
    them (horizontal nearest). Useful for nuking the green '28' debug blocks
    that goats.dev sprinkled across Map333."""
    ensure_backup(map_id)
    src = RAW / f'map{map_id}.png'
    im = Image.open(src).convert('RGBA')
    arr = np.array(im)
    # Mask = pixels close to signature_rgb (and inside the green block — extend
    # to neighboring darker text pixels via a small dilation by treating any
    # pixel whose 4-neighbours majority are green as also green-block).
    d = np.abs(arr[:,:,:3].astype(int) - np.array(signature_rgb)[None,None,:]).sum(axis=2)
    bg_mask = d <= tol
    # Dilate by 3 px (manual numpy) to catch the dark "28" text pixels inside green tiles
    dilated = bg_mask.copy()
    for _ in range(3):
        d2 = np.zeros_like(dilated)
        d2[1:, :]  |= dilated[:-1, :]
        d2[:-1, :] |= dilated[1:, :]
        d2[:, 1:]  |= dilated[:, :-1]
        d2[:, :-1] |= dilated[:, 1:]
        dilated |= d2
    mask = bg_mask | (dilated & ~bg_mask)
    if not mask.any():
        print(f"  no pixels matching {signature_rgb}±{tol} in map{map_id}")
        return
    print(f"  removing {mask.sum()} px matching {signature_rgb}")
    inpaint_region(arr, mask)
    Image.fromarray(arr).save(src)
    print(f"  wrote {src.name}")

# ── Patches ─────────────────────────────────────────────────────────────────
def main():
    print("[1/4] Map106 — replace '1' placeholder with DW_MIRROR sprite at (42, 19)")
    # Mirror tall sprite — erase a generous 2×3-tile area to cover the placeholder + its text
    patch_event(106, SPRITES/'DW_MIRROR.png', 0, 42, 19,
                erase_box=(41*T, 17*T, 44*T, 21*T))

    print("\n[2/4] Map185 — stamp JASH SHOP (DW_ASH_1[1] = tofu) at (23, 29)")
    patch_event(185, SPRITES/'DW_ASH_1.png', 1, 23, 29,
                erase_box=(22*T+8, 28*T+4, 25*T-8, 30*T))

    print("\n[3/4] Map144 — replace Life Jam Guy small crate with $DW_Lifejam_Guy[0] at (25, 33)")
    patch_event(144, SPRITES/'$DW_Lifejam_Guy.png', 0, 25, 33,
                erase_box=(24*T, 31*T, 27*T, 35*T), dollar=True)

    print("\n[4/4] Map333 — remove green '28' debug placeholders")
    # Sample a known '28' block to get its background green color, then nuke
    im333 = Image.open(RAW/'map333.png').convert('RGBA')
    a333 = np.array(im333)
    # Sample tile at row 7 cols 5-22 — these are the visible '28' row in user's view
    # Pick a pixel that is clearly green-block bg
    sig = a333[7*T + 16, 14*T + 16, :3].tolist()
    print(f"  sampling at ({14*T+16}, {7*T+16}): {sig}")
    if sig[1] > sig[0] and sig[1] > sig[2]:  # G is dominant — green
        remove_tile_color(333, sig, tol=20)
    else:
        print(f"  sampled color isn't green ({sig}); will need manual coords")

if __name__ == '__main__':
    main()
