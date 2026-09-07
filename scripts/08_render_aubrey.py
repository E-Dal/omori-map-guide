#!/usr/bin/env python3
"""
Render an OMORI map from its .AUBREY (encrypted Tiled JSON) data.

Pipeline:
  1. Decrypt maps/map<id>.AUBREY → Tiled JSON (via Node helper)
  2. For each referenced tileset:
     - Decrypt maps/<name>.AUBREY → tileset JSON
     - Decrypt img/tilesets/<name>.rpgmvp → tileset PNG
  3. Composite every tile layer onto a transparent RGBA canvas

Skips collision/region "marker" tilesets (Tile_Collisions, Tile_Regions) —
they only carry passability info and would overlay debug arrows.

Usage:
  python3 scripts/08_render_aubrey.py <mapId> [<mapId> ...]
  python3 scripts/08_render_aubrey.py --all
"""
import json, os, sys, subprocess, tempfile, shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _keys  # noqa: E402
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
GAME = Path('/Users/vicky/Library/Application Support/Steam/steamapps/common/OMORI/OMORI.app/Contents/Resources/app.nw')
DEC_KEY_HEX = _keys.rpgmvp_key().hex()   # .rpgmvp XOR decrypt (System.json encryptionKey)
RAW_OUT = ROOT / 'data' / 'raw_pngs'
TILE = 32
CACHE = Path('/tmp/aubrey_cache')
CACHE.mkdir(exist_ok=True)
(CACHE / 'tilesets_img').mkdir(exist_ok=True)
(CACHE / 'tilesets_meta').mkdir(exist_ok=True)
(CACHE / 'maps').mkdir(exist_ok=True)

# ── Decryption helpers ──────────────────────────────────────────────────────
def decrypt_aubrey(src_path: Path, dst_path: Path):
    """Use Node helper to AES-256-CTR decrypt."""
    if dst_path.exists(): return
    subprocess.run(['node', str(SCRIPT_DIR / '_aubrey_decrypt.js'),
                    str(src_path), str(dst_path)],
                   check=True, capture_output=True)

def decrypt_rpgmvp(src_path: Path, dst_path: Path):
    """XOR-decrypt MV image format: drop 16-byte sig, XOR next 16 with key, append rest."""
    if dst_path.exists(): return
    kb = bytes.fromhex(DEC_KEY_HEX)
    data = src_path.read_bytes()
    enc_header = data[16:32]
    body = data[32:]
    dec = bytes(b ^ kb[i % len(kb)] for i, b in enumerate(enc_header))
    dst_path.write_bytes(dec + body)

# ── Tileset loading ─────────────────────────────────────────────────────────
SKIP_TILESETS = {'Tile_Collisions_32x32', 'Tile_Regions_32x32',
                 'Tile_Collisions', 'Tile_Regions'}

def load_tileset(source_name):
    """source_name like 'DW_VastForest.json' or 'general_use.json'.
    Returns dict with: {name, firstgid (set by caller), columns, tilecount,
                        image (PIL Image), tilewidth, tileheight}
    Returns (None, reason) tuple if cannot load."""
    base = source_name.replace('.json', '')
    if base in SKIP_TILESETS: return (None, 'marker')

    # 1) tileset metadata
    aubrey = GAME / 'maps' / f'{base}.AUBREY'
    if not aubrey.exists():
        return (None, 'no metadata')
    meta_path = CACHE / 'tilesets_meta' / f'{base}.json'
    decrypt_aubrey(aubrey, meta_path)
    meta = json.loads(meta_path.read_text())

    # 2) tileset image — read 'image' field from metadata (NOT same as tileset name!).
    # e.g. DW_DeepReef.AUBREY → image='../img/tilesets/DW_DeepWell.png'
    img_ref = meta.get('image', '')
    if not img_ref:
        return (None, 'no image field')
    img_basename = Path(img_ref).stem   # e.g. 'DW_DeepWell'
    img_rpgmvp = GAME / 'img' / 'tilesets' / f'{img_basename}.rpgmvp'
    img_path = CACHE / 'tilesets_img' / f'{img_basename}.png'
    if not img_rpgmvp.exists():
        return (None, f'image rpgmvp missing: {img_basename}')
    decrypt_rpgmvp(img_rpgmvp, img_path)
    img = Image.open(img_path).convert('RGBA')

    return ({
        'name': base, 'image_name': img_basename,
        'image': img,
        'tilewidth':  meta.get('tilewidth',  TILE),
        'tileheight': meta.get('tileheight', TILE),
        'columns':    meta.get('columns', img.width // TILE),
        'tilecount':  meta.get('tilecount', (img.width // TILE) * (img.height // TILE)),
    }, 'ok')

# ── Renderer ────────────────────────────────────────────────────────────────
def render_map(map_id):
    aubrey = GAME / 'maps' / f'map{map_id}.AUBREY'
    if not aubrey.exists():
        print(f"  Map{map_id}: no .AUBREY"); return False
    tiled_path = CACHE / 'maps' / f'map{map_id}.json'
    decrypt_aubrey(aubrey, tiled_path)
    tiled = json.loads(tiled_path.read_text())

    w_tiles = tiled['width']; h_tiles = tiled['height']
    tw = tiled.get('tilewidth', TILE); th = tiled.get('tileheight', TILE)
    print(f"  Map{map_id}: {w_tiles}×{h_tiles} tiles ({w_tiles*tw}×{h_tiles*th} px)")
    print(f"    {len(tiled.get('layers',[]))} layers, {len(tiled.get('tilesets',[]))} tilesets")

    # Load all tilesets (handles BOTH external source= refs AND embedded inline tilesets)
    tilesets = []
    for ts in tiled.get('tilesets', []):
        source = ts.get('source', '')
        if source:
            loaded, reason = load_tileset(source)
            label = source
        else:
            # Embedded tileset — image + columns/tilecount inline
            img_ref = ts.get('image', '')
            name = ts.get('name', '?')
            label = f"<embedded {name}>"
            if not img_ref:
                loaded, reason = None, 'embedded with no image'
            else:
                img_basename = Path(img_ref).stem
                img_rpgmvp = GAME / 'img' / 'tilesets' / f'{img_basename}.rpgmvp'
                img_path = CACHE / 'tilesets_img' / f'{img_basename}.png'
                if not img_rpgmvp.exists():
                    loaded, reason = None, f'image rpgmvp missing: {img_basename}'
                else:
                    decrypt_rpgmvp(img_rpgmvp, img_path)
                    img = Image.open(img_path).convert('RGBA')
                    loaded = {
                        'name': name, 'image_name': img_basename, 'image': img,
                        'tilewidth':  ts.get('tilewidth',  TILE),
                        'tileheight': ts.get('tileheight', TILE),
                        'columns':    ts.get('columns', img.width // TILE),
                        'tilecount':  ts.get('tilecount', (img.width // TILE) * (img.height // TILE)),
                    }
                    reason = 'ok'
        if loaded:
            tilesets.append((ts['firstgid'], loaded))
            print(f"    + {loaded['name']:30s} → img {loaded['image_name']:25s} firstgid={ts['firstgid']:5d}")
        else:
            tilesets.append((ts['firstgid'], None))
            print(f"    - {label:30s} skipped: {reason}")

    # Canvas
    canvas = Image.new('RGBA', (w_tiles * tw, h_tiles * th), (0, 0, 0, 0))

    # Sort ALL tilesets by firstgid (preserve None markers in order).
    # A GID belongs to the tileset with the highest firstgid <= GID — i.e. neighbors
    # define the upper bound, not arbitrary tilecount estimates.
    all_sorted = sorted(tilesets, key=lambda x: x[0])

    def find_tileset(gid):
        chosen = None
        for fg, ts in all_sorted:
            if fg <= gid: chosen = (fg, ts)
            else: break
        if chosen is None or chosen[1] is None: return None, 0
        return chosen[1], gid - chosen[0]

    # Render layers in order
    for li, layer in enumerate(tiled.get('layers', [])):
        if layer.get('type') != 'tilelayer': continue
        if layer.get('visible') is False: continue
        # Skip layers that are clearly debug/passability overlays
        lname = (layer.get('name') or '').upper()
        if any(kw in lname for kw in ['COLLISION', 'REGION', 'PASSABILITY', 'FLAGS']):
            continue
        data = layer.get('data', [])
        for i, gid in enumerate(data):
            if gid == 0: continue
            # Flip flags occupy top 3 bits; mask them off
            actual_gid = gid & 0x1FFFFFFF
            ts, tile_idx = find_tileset(actual_gid)
            if ts is None: continue
            cols = ts['columns']
            sx = (tile_idx % cols) * tw
            sy = (tile_idx // cols) * th
            if sy + th > ts['image'].height or sx + tw > ts['image'].width:
                continue
            src_tile = ts['image'].crop((sx, sy, sx + tw, sy + th))
            dx = (i % w_tiles) * tw
            dy = (i // w_tiles) * th
            canvas.alpha_composite(src_tile, (dx, dy))

    out_path = RAW_OUT / f'map{map_id}.png'
    # Backup _orig if not already
    bk = RAW_OUT / f'map{map_id}_orig.png'
    if not bk.exists() and out_path.exists():
        shutil.copy(out_path, bk)
    canvas.save(out_path)
    print(f"    ✓ wrote {out_path.name} ({canvas.size})")
    return True

def main(argv):
    if len(argv) < 2:
        print(__doc__); sys.exit(1)
    if argv[1] == '--all':
        # Find all .AUBREY map files
        map_ids = []
        for f in sorted((GAME / 'maps').glob('map*.AUBREY')):
            stem = f.stem  # e.g. map101
            if stem.startswith('map') and stem[3:].isdigit():
                map_ids.append(int(stem[3:]))
        print(f"Found {len(map_ids)} .AUBREY map files")
    else:
        map_ids = [int(x) for x in argv[1:]]
    ok = 0
    for mid in map_ids:
        if render_map(mid): ok += 1
    print(f"\nRendered {ok}/{len(map_ids)} maps.")

if __name__ == '__main__':
    main(sys.argv)
