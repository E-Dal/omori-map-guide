#!/usr/bin/env python3
"""Render an OMORI map (encrypted Tiled format) to PNG.

OMORI ships maps as .AUBREY (AES-256-CTR encrypted Tiled JSON) in OMORI.app/.../maps/
and tileset images as .rpgmvp (header-XOR encrypted PNG) in img/tilesets/.

For each map:
  1. Decrypt map<id>.AUBREY → Tiled JSON with layers + tileset refs
  2. Resolve each tileset:
       - <name>.AUBREY → tileset JSON (image filename, columns, tilecount)
       - img/tilesets/<image>.rpgmvp → PNG
  3. Composite all visible tile layers in order

Pass --drop-void to leave void filler (tiles that are nothing but opaque
black) transparent, so a map does not paint over its neighbours in the stitch.
Off by default: 18_trim_black_bg.py already clears backdrop black from a
finished PNG, and it does it by flood fill from the border, which also catches
black that came from somewhere other than a filler tile.

Usage: python3 scripts/13_render_tiled_map.py [--drop-void] <map_id> [<map_id> ...]
"""
import sys, os, json, struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _keys  # noqa: E402
from PIL import Image

GAME_ROOT = Path.home() / 'Library/Application Support/Steam/steamapps/common/OMORI/OMORI.app/Contents/Resources/app.nw'
MAPS_DIR = GAME_ROOT / 'maps'
TILESETS_DIR = GAME_ROOT / 'img/tilesets'
OUT_DIR = Path(__file__).resolve().parent.parent / 'data' / 'raw_pngs'
PARALLAX_DIR = GAME_ROOT / 'img/parallaxes'
MAP_META_DIR = Path(__file__).resolve().parent.parent / 'data'

# AES-256-CTR key (32 ASCII bytes)
AUBREY_KEY = _keys.aubrey_key()
# rpgmvp XOR key (16 bytes hex, total 16 bytes after parsing)
RPGMVP_KEY = _keys.rpgmvp_key()

TILE = 32


def aes_decrypt(path: Path) -> bytes:
    """Decrypt AES-256-CTR file. First 16 bytes are IV; rest is ciphertext.
    Implement CTR manually (no cryptography lib dep)."""
    data = path.read_bytes()
    iv = bytearray(data[:16])
    ct = data[16:]
    # Use Python's built-in AES via subprocess to openssl? Better: use a tiny CTR impl.
    # We'll use PyCryptodome if available, else fall back to subprocess.
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(bytes(AUBREY_KEY), AES.MODE_CTR,
                         initial_value=bytes(iv), nonce=b'')
        return cipher.decrypt(ct)
    except ImportError:
        # Use openssl as fallback
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(delete=False) as t:
            t.write(ct); tpath = t.name
        out = subprocess.run(
            ['openssl', 'enc', '-d', '-aes-256-ctr',
             '-K', AUBREY_KEY.hex(), '-iv', iv.hex(),
             '-in', tpath],
            capture_output=True, check=True
        ).stdout
        os.unlink(tpath)
        return out


def load_aubrey_json(path: Path):
    return json.loads(aes_decrypt(path).decode('utf-8'))


def load_rpgmvp_png(path: Path) -> Image.Image:
    """Decrypt rpgmvp → PNG."""
    data = path.read_bytes()
    # Skip 16-byte RPGMV header, XOR next 16 bytes with key
    body = bytearray(data[16:])
    for i in range(16):
        body[i] ^= RPGMVP_KEY[i]
    import io
    return Image.open(io.BytesIO(bytes(body))).convert('RGBA')


_tileset_cache = {}

def load_tileset(source_name: str):
    """Load a tileset by its source name (e.g., 'TerrainTiles.json').
    Returns: dict with keys: image (PIL Image), columns, tilecount, tilewidth, tileheight."""
    if source_name in _tileset_cache:
        return _tileset_cache[source_name]
    # Source name has .json extension; corresponding encrypted is .AUBREY
    base = source_name.rsplit('.', 1)[0]
    aubrey_path = MAPS_DIR / f'{base}.AUBREY'
    if not aubrey_path.exists():
        print(f'  ⚠ tileset {base}.AUBREY not found')
        _tileset_cache[source_name] = None
        return None
    meta = load_aubrey_json(aubrey_path)
    img_filename = meta.get('image', '')  # e.g., '../img/tilesets/TerrainTiles.png'
    img_base = os.path.basename(img_filename).rsplit('.', 1)[0]
    rpgmvp_path = TILESETS_DIR / f'{img_base}.rpgmvp'
    image = None
    if rpgmvp_path.exists():
        image = load_rpgmvp_png(rpgmvp_path)
    else:
        # Some tilesets are pure-data (collision/region maps) with no image
        print(f'  · {img_base}.rpgmvp not found (data-only tileset)')
    info = {
        'image': image,
        'columns': meta.get('columns', 1),
        'tilecount': meta.get('tilecount', 0),
        'tilewidth': meta.get('tilewidth', TILE),
        'tileheight': meta.get('tileheight', TILE),
    }
    _tileset_cache[source_name] = info
    return info


def tileset_from_inline(ts_ref: dict):
    """Build tileset info from a tileset embedded in the map itself.

    Most maps reference their tilesets by file — {"firstgid": N, "source":
    "TerrainTiles.json"} — but a handful inline one instead, carrying image,
    columns and tilecount directly and no `source` key at all. Reading only the
    referenced form meant six maps (HIDDEN LIBRARY, HUMPHREY'S CAVE, ALCOVES I,
    MOLLY ENTRANCE and two Sweetheart's Castle rooms) died on a KeyError.

    Image names in these blocks are not always cased like the file on disk —
    map187 asks for DW_HiddenLIbrary — so match the filename case-insensitively.
    """
    img_base = os.path.basename(ts_ref.get('image', '')).rsplit('.', 1)[0]
    image = None
    if img_base:
        path = TILESETS_DIR / f'{img_base}.rpgmvp'
        if not path.exists():
            wanted = f'{img_base}.rpgmvp'.lower()
            path = next((p for p in TILESETS_DIR.iterdir() if p.name.lower() == wanted), None)
        if path and path.exists():
            image = load_rpgmvp_png(path)
        else:
            print(f'  · {img_base}.rpgmvp not found (inline tileset)')
    return {
        'image': image,
        'columns': ts_ref.get('columns', 1),
        'tilecount': ts_ref.get('tilecount', 0),
        'tilewidth': ts_ref.get('tilewidth', TILE),
        'tileheight': ts_ref.get('tileheight', TILE),
    }


# A tile that is nothing but opaque black is void filler, not scenery: OMORI
# pads a map out to its rectangle with it, and the goats.dev renders leave those
# squares transparent — 266 of them on GINO'S DINER alone, every one the same
# tile. Drawing them is what made our renders worse than theirs for stitching: a
# map's filler paints over whatever neighbour lies under it, which is where the
# black edges around FOREST PLAYGROUND came from.
#
# The test is per tile and asks for *every* pixel: art that merely contains
# black — every outline in the game — is untouched. Results are cached because
# the same handful of filler tiles is used tens of thousands of times.
_all_black_cache = {}


def is_void_tile(image, box):
    """True when this tile is entirely opaque, pure black."""
    key = (id(image), box)
    hit = _all_black_cache.get(key)
    if hit is None:
        tile = image.crop(box)
        colours = tile.getcolors(maxcolors=8)      # None once there are many
        hit = colours is not None and all(
            c == (0, 0, 0, 255) for _, c in colours)
        _all_black_cache[key] = hit
    return hit


# Tiled flip bits
FLIP_H = 0x80000000
FLIP_V = 0x40000000
FLIP_D = 0x20000000  # diagonal (rotate 90)
ID_MASK = 0x1FFFFFFF


def load_rpgmv_as_tiled(map_id: int, sibling_for_tilesets: int = None):
    """For maps without .AUBREY source, build a pseudo-Tiled dict from RPG MV
    data/Map{id}.json. Use sibling_for_tilesets's .AUBREY tileset list."""
    import json as J
    rpgmv = J.load(open(f'/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted/Map{map_id:03d}.json'))
    W, H = rpgmv['width'], rpgmv['height']
    raw = rpgmv['data']
    # RPG MV layout: data is flat [layer * W*H + row*W + col], 6 layers (4 visual + shadow + region)
    # Build per-layer 2D arrays
    layers = []
    for layer_i in range(4):  # 4 visual tilemap layers
        layer_data = raw[layer_i * W*H : (layer_i + 1) * W*H]
        layers.append({'type': 'tilelayer', 'visible': True, 'data': layer_data})
    # Get tilesets from sibling
    sib_path = MAPS_DIR / f'map{sibling_for_tilesets}.AUBREY'
    sib = load_aubrey_json(sib_path)
    return {
        'width': W, 'height': H,
        'tilewidth': TILE, 'tileheight': TILE,
        'tilesets': sib['tilesets'],
        'layers': layers,
    }


def map_parallax(map_id: int):
    """The parallax this map declares, out of whichever region file knows it."""
    for f in sorted(MAP_META_DIR.glob('*_maps.json')):
        try:
            meta = json.load(open(f))
        except Exception:
            continue
        m = meta.get(str(map_id))
        if m and m.get('parallaxName'):
            return m['parallaxName']
    return None


def render_map(map_id: int, fallback_sibling: int = None, drop_void: bool = False):
    src = MAPS_DIR / f'map{map_id}.AUBREY'
    if src.exists():
        print(f'\nRendering map{map_id} (from Tiled .AUBREY)…')
        tiled = load_aubrey_json(src)
    elif fallback_sibling:
        print(f'\nRendering map{map_id} (RPG MV data + sibling map{fallback_sibling} tilesets)…')
        tiled = load_rpgmv_as_tiled(map_id, fallback_sibling)
    else:
        print(f'❌ map{map_id}.AUBREY not found and no fallback sibling given')
        return
    W, H = tiled['width'], tiled['height']
    TW, TH = tiled.get('tilewidth', TILE), tiled.get('tileheight', TILE)

    # Resolve tilesets: list of {firstgid, image, columns, tilewidth, tileheight}.
    # Include image-less tilesets too (so we can correctly identify their gid range
    # and SKIP those tiles rather than mis-render with a different tileset).
    tilesets = []
    for ts_ref in tiled.get('tilesets', []):
        info = (load_tileset(ts_ref['source']) if 'source' in ts_ref
                else tileset_from_inline(ts_ref))
        if info is None:
            continue
        tilesets.append({**info, 'firstgid': ts_ref['firstgid']})
    tilesets.sort(key=lambda t: t['firstgid'])

    def find_tileset(gid):
        # Find the tileset whose firstgid is the largest <= gid (regardless of image).
        # Caller must check ts['image'] before rendering.
        owner = None
        for ts in tilesets:
            if ts['firstgid'] <= gid:
                owner = ts
            else:
                break
        return owner

    out = Image.new('RGBA', (W * TW, H * TH), (0, 0, 0, 0))

    # The parallax goes under the tiles. SOLAR SYSTEM's tile layers hold only
    # the white specks — its pink road and its starfield are the parallax, so a
    # tiles-only render came out 95% black and read as BLACKSPACE. RPG Maker
    # repeats a parallax whose name has no leading '!', which is every one we
    # want here, so it is tiled from the top-left to fill the map.
    par = map_parallax(map_id)
    if par:
        path = PARALLAX_DIR / f'{par}.rpgmvp'
        if path.exists():
            bg = load_rpgmvp_png(path).convert('RGBA')
            for y in range(0, out.height, bg.height):
                for x in range(0, out.width, bg.width):
                    out.alpha_composite(bg, dest=(x, y))
            print(f'  · parallax {par} ({bg.width}x{bg.height}) tiled underneath')
        else:
            print(f'  · parallax {par} named but {path.name} not found')
    n_drawn = 0
    n_skipped = 0
    n_void = 0
    for layer in tiled.get('layers', []):
        if layer.get('type') != 'tilelayer': continue
        if not layer.get('visible', True): continue
        # Skip collision/region overlay layers (editor-only, not visible in game).
        lname = (layer.get('name') or '').upper()
        if 'COLLISION' in lname or 'REGION' in lname: continue
        data = layer.get('data', [])
        for i, raw in enumerate(data):
            if raw == 0: continue
            gid = raw & ID_MASK
            ts = find_tileset(gid)
            if ts is None or ts['image'] is None: n_skipped += 1; continue
            local = gid - ts['firstgid']
            cols = ts['columns']
            if cols < 1: continue
            sx = (local % cols) * ts['tilewidth']
            sy = (local // cols) * ts['tileheight']
            box = (sx, sy, sx + ts['tilewidth'], sy + ts['tileheight'])
            if drop_void and is_void_tile(ts['image'], box):
                n_void += 1
                continue
            try:
                tile = ts['image'].crop(box)
            except: n_skipped += 1; continue
            # Apply flip flags
            if raw & FLIP_H: tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
            if raw & FLIP_V: tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
            if raw & FLIP_D: tile = tile.transpose(Image.TRANSPOSE)
            x = (i % W) * TW
            y = (i // W) * TH
            out.alpha_composite(tile, dest=(x, y))
            n_drawn += 1
    out_path = OUT_DIR / f'map{map_id}.png'
    out.save(out_path)
    print(f'  ✓ {out_path.name}: drew {n_drawn} tiles '
          f'({n_skipped} skipped, no tileset'
          + (f'; {n_void} void tiles left transparent' if n_void else '') + ')')


FALLBACK_SIBLINGS = {
    188: 189,  # NORTH LAKE → DEEP WELL uses same tilesets as DEEP WELL LADDER
}

def main():
    args = sys.argv[1:]
    drop_void = '--drop-void' in args
    if drop_void:
        args.remove('--drop-void')
    if not args:
        print(__doc__); sys.exit(1)
    for arg in args:
        mid = int(arg)
        render_map(mid, FALLBACK_SIBLINGS.get(mid), drop_void=drop_void)



def _refresh_png_manifest():
    """Stamp the manifest so the pages pick the new render up without a
    hard reload — see scripts/35_png_manifest.py."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'png_manifest', Path(__file__).resolve().parent / '35_png_manifest.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.rebuild()
    except Exception as exc:            # a stale manifest is not worth failing a render over
        print(f'  · could not refresh the PNG manifest: {exc}')


if __name__ == '__main__':
    main()
    _refresh_png_manifest()
