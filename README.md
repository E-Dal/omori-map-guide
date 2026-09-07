# OMORI Map Guide

An interactive map atlas for OMORI — explore Faraway Town and Headspace, find watermelons, NPC rewards, and never get lost again.

## Goals

- Stitched outdoor world maps for FARAWAY TOWN and HEADSPACE
- Click-to-enter interiors (independent rooms shown side-by-side, not force-fit into the world map)
- Markers for collectibles (watermelons), NPC rewards, badge triggers
- Filterable by type / region / availability

## Status

WIP. All 11 regions have extracted data; stitched world maps exist for 4 of them.

| Region | Maps | Exits | 🍉 | Stitched |
|---|---:|---:|---:|:--:|
| `faraway` | 82 | 778 | 0 | day / sunset / night |
| `vast_forest` | 29 | 99 | 28 | — |
| `orange_oasis` | 29 | 90 | 52 | — |
| `otherworld` | 41 | 128 | 46 | — |
| `junkyard` | 15 | 50 | 24 | ✅ |
| `pyrefly_forest` | 25 | 96 | 16 | ✅ |
| `sweethearts_castle` | 55 | 139 | 75 | ✅ |
| `deep_well` | 24 | 49 | 21 | — |
| `deeper_well` | 30 | 126 | 51 | — |
| `humphrey` | 35 | 120 | 31 | — |
| `last_resort` | 15 | 69 | 13 | — |
| `forest_playground` | 1 | 1 | 0 | — |

Every map listed above has an image in `data/raw_pngs/` (360/360). Editor-only
folder nodes in the map tree (`-- PINWHEEL FOREST`, `-- MINIGAMES`, …) are
dropped during extraction — see `01_extract_adjacency.js`.

Some maps are *room atlases*: several unconnected rooms sharing one canvas,
with impassable filler between them. Those are sliced into per-room sub-maps
(`subMaps` in `01`, cut by `05`) under whichever region's door leads into each
room. Map453 CLUB SANDWICH also holds one room that nothing in the game can
reach, kept and flagged `[UNUSED]`.

Skills viewer covers vanilla + the Broken Dreams mod.

## Run locally

```bash
# 1. Extract map metadata + adjacency for a region (regenerate when game data changes)
node scripts/01_extract_adjacency.js <region>       # e.g. junkyard

# 2. Download that region's map PNGs from goats.dev (skips existing + 404s)
./scripts/02_download_goats_pngs.sh <region>

# 3. If the region has sliced rooms: cut them, then anchor their exits
python3 scripts/05_cut_submaps.py      <region>
python3 scripts/14_add_exit_anchors.py <region>   # re-run after any new slice

# 4. Markers: extract them, cut their sprites, then measure where those sprites
#    really are in the map art. 29 must follow 22/28 — it corrects what they
#    predict against the shipped PNGs.
python3 scripts/22_extract_conveyors.py
node    scripts/23_extract_collectibles.js
python3 scripts/28_extract_point_sprites.py
python3 scripts/29_measure_point_art.py
# 30 and 31 also write collectibles.json and 23 overwrites it, so the whole
# chain has to be re-run in order — stopping after 29 silently drops the five
# HANGMAN keys only 31 can place, and every "requires" note.
python3 scripts/30_extract_requirements.py
python3 scripts/31_blackletter_clues.py
# 5. The Chinese half of the interface. Reads the *installed* (Simplified
#    Chinese) build and pairs its names to the English dump's by row id.
python3 scripts/37_extract_zh_names.py

# 6. Serve the repo root (the web pages fetch ../data/*)
python3 -m http.server 8000
# then open http://localhost:8000/web/
```

Maps that goats.dev doesn't host can be rendered straight from a local Steam
install instead:

```bash
python3 scripts/13_render_tiled_map.py <map_id> [<map_id> ...]
```

`13` composites the map's parallax under the tile layers, and `16` can draw the
event sprites a render is missing — SOLAR SYSTEM is both: its tile layers hold
only white specks, its starfield is the parallax and its planets are events, so
a tiles-only render came out 95% black and looked like BLACKSPACE.

```bash
python3 scripts/13_render_tiled_map.py 127
python3 scripts/16_render_event_sprites.py 127 --no-clip \
  --events 2,3,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30
```

Which events, exactly, matters. `31 EPILOGUE PLUTO` and `32 THE EARTH EPILOGUE`
are left out: Pluto's every drawn page is behind an epilogue switch, so the map
should show only the hole it left, and the epilogue Earth is a second copy of
the one already on the road. `--no-clip` is needed because the headroom
clipping the flag turns off is for two-tile warp pads — it took Jupiter down to
a single tile.

Both refresh `data/raw_pngs/manifest.json`, which is each PNG's mtime; the web
pages stamp it onto the image URLs so a re-rendered map is picked up without a
hard reload. Run `python3 scripts/35_png_manifest.py` by hand if you replace a
PNG some other way.

## Layout

```
data/
  <region>_maps.json        map id → name, width/height (tiles), parallax, bgm
  <region>_edges.json       { internal: [ {from:{mapId,evId,evName,x,y,page,hitbox}, to:{mapId,x,y}, kind} ] }
  <region>_highlights.json  { watermelons: [ {mapId,evId,name,x,y,color,prize} ] }
  skills_vanilla.json       skill tables for the skills viewer
  skills_brokendreams.json
  raw_pngs/                 per-map PNGs (gitignored, ~580 files)
  stitched/                 stitched world PNGs + layout JSON (gitignored)
scripts/                    extraction + rendering pipeline (numbered by run order)
web/                        static site — no build step
```

Coordinates are in **tiles** in the JSON, **pixels** (`tile × 32`) in the stitched
layouts. Leaflet uses `CRS.Simple` with the y-axis flipped (`lat = heightPx - y`).

## Scripts

| Script | What it does |
|---|---|
| `01_extract_adjacency.js <region>` | Walks the mapInfo parent/child tree from each region's roots and scans every event page for transfers — RPG Maker code 201, `reserveTransfer(...)`, and OMORI's `setValue(9=mapId, 10=x, 11=y)` fade pattern. Writes `<region>_maps.json` + `<region>_edges.json`. Region roots / exclusions / extra rooms are configured in the `REGIONS` table at the top. |
| `02_download_goats_pngs.sh <region>` | Pulls pre-rendered map PNGs from goats.dev into `data/raw_pngs/`. |
| `03_extract_skills.js` | Vanilla skill tables → `skills_vanilla.json`. |
| `04_extract_bd_skills.js` | Broken Dreams skill tables (incl. Energy cost) → `skills_brokendreams.json`. |
| `05_cut_submaps.py` | Cuts oversized source PNGs into sub-maps. |
| `06_restitch.py` | Rebuilds a stitched PNG from a layout JSON. |
| `07_patch_renders.py` | Patches individual map renders into an existing stitch. |
| `08_render_aubrey.py` | Renders maps from decrypted `.AUBREY` data. |
| `12_slice_houses.py` | Slices Faraway house interiors → `faraway_houses_sliced.json`. |
| `38_add_arrival_anchors.py [<region>…]` | Puts a snap anchor on a tile the game sends you *to* but never *from*. A room entered only by a transfer somewhere else has no FROM side of its own, so the stitcher has nothing there to snap a route to — SWEETHEART DUNGEON 1's top-left cell holds twelve `dressmole` events and not one transfer, yet map171 ev76 drops you at (7, 8) inside it. Hand-written list; each entry is checked against the edges and reported rather than placed if nothing actually arrives there. Re-running is safe. |
| `34_add_side_anchors.py <region> <mapId>…` | Adds one anchor on the left and right edge of a map, for open maps that run into their neighbours along a whole side with no door event anywhere near it — FROZEN FOREST (II) and (VII). The anchor's hitbox is vertical, which pins X and lets Y slide, so one point stands for the entire side. |
| `14_add_exit_anchors.py <region>` | Most sliced rooms leave through a narrow path stub at the bottom that carries no event, so the stitcher had nothing to snap a route to there. Measures each cut PNG and appends a synthetic anchor edge on the stub. Run after `01` and `05`. |
| `13_render_tiled_map.py <id>...` | Renders a map from a local Steam install: decrypts `.AUBREY` (AES-256-CTR) and `.rpgmvp` tilesets (header XOR), composites the visible Tiled layers. |
| `37_extract_zh_names.py` | Writes `data/names_zh.json`: every item, weapon and charm name in the installed Simplified Chinese build, keyed by the English dump's name for the same row id. The two builds number their rows identically, so the pairing is exact. `index.html` swaps names at render time — `collectibles.json` stays English. |
| `36_bake_deco_clusters.py` | Composites each contiguous run of decorations into one PNG under `web/assets/decorations/baked/`, plus `data/stitched/deco_clusters.json`. The trees bridge holes in the layout, so what is behind them is `#map`'s background; Leaflet rounds each of the 179 overlays separately and lets it through the hairline cracks as a black outline round every tree. One image cannot crack against itself. **Run after every layout import**, next to `33_recolor_close_routes.py`, with the same flag each time — `index.html` checks the manifest against the layout and falls back to per-sprite drawing when it is stale. `--all-below` puts every cluster under every map instead of honouring the layout's z-order, which makes each spatial cluster exactly one file and survives maps moving; this atlas uses it, because nearly every tree hangs over a hole and has no map to be in front of anyway. |

`01` reads decrypted `Map*.json` from a path hardcoded at the top of the file;
`13` reads the Steam copy of OMORI directly.

## Web pages

- **`index.html`** — the viewer. Region picker, per-map mode (map image + clickable
  exit markers that jump to the destination) and stitched mode (world PNG + route
  overlay with dot/line size sliders). Watermelon markers with prize tooltips.
- **`stitcher_all.html`** — all-region stitcher: drag/snap maps, group by imported
  layout, z-order, undo/redo, marquee select, route drawing, export PNG + layout JSON.
- **`stitcher_<region>.html`** — the same tool scoped to one region.
- **`skills.html`** — skill table browser, switchable between vanilla and Broken Dreams.

## Stack

- Static HTML site, no build step
- [Leaflet](https://leafletjs.com/) for the map viewer (zoom + pan + markers)
- Map images courtesy of [goats.dev](https://goats.dev/omori/)
- Hosted on GitHub Pages

## Data sources

- Game event data: extracted from decrypted vanilla `Map*.json` files
- Map images: [goats.dev](https://goats.dev/omori/) pre-rendered PNGs, plus local
  renders from the game's own encrypted Tiled data

## Credits & permissions

- **OMORI** is © OMOCAT, LLC. This is a non-commercial fan project with no
  affiliation to, or endorsement by, OMOCAT. All original art, sprites, fonts
  and audio belong to them.
- **Map renders** are from [goats.dev](https://goats.dev/omori/), with a few
  rendered here from the game's own Tiled data where goats.dev has no image.
- **Chinese text** — region names, item names and the HANGMAN clues — is the
  game's own Simplified Chinese translation, read out of an installed copy
  rather than written by hand. See `scripts/37_extract_zh_names.py`.

## License

The **code** in this repository is released under the MIT License.

**The assets are not.** OMORI's map images and sprites belong to OMOCAT, LLC.
They are not covered by the code licence and may not be redistributed.

## Colophon

Most of the extraction scripts and most of the code in `web/index.html` were
written by [Claude](https://claude.ai/code), across a very long back-and-forth.

The world is not its work. Every one of the 253 maps was placed by hand in the
stitcher, along with 226 routes and 179 trees and pinwheels — and so was every
correction that made the data right. Claude had the HANGMAN V key on the wrong
tile until it was told the key is in the cage, and the sprite sheet then proved
it; it explained the black outline around the Vast Forest trees twice, wrongly,
before being told plainly that the stitcher does not have the problem, which is
what led to the real cause; and it would have shipped a HECTOR quest that does
not exist. Knowing the game is what fixed all three.
