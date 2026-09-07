# Field notes

Things that cost real time to work out, written down so they only cost it once.
Every number here was measured against the game's own data or the shipped
renders — where a rule was guessed and turned out wrong, that is recorded too,
because the wrong guess is usually the tempting one.

---

## 1. Where the data actually lives

`data/Map*.json` (the decrypted RPG Maker files) carry the **events**. Their
`data` array — the tile grid — is **always empty**. Tiles live somewhere else:

| What | Where | Encryption |
|---|---|---|
| Tile layers | `OMORI.app/…/maps/map<id>.AUBREY` | AES-256-CTR, first 16 bytes are the IV |
| Tilesets | `img/tilesets/<name>.rpgmvp` | 16-byte RPGMV header, next 16 bytes XORed |
| Tileset metadata | `maps/<name>.AUBREY` | same as maps |

`13_render_tiled_map.py` handles all of it. A few maps **inline** their tileset
instead of referencing one by `source`; reading only the referenced form killed
six maps with `KeyError: 'source'`. Image filenames inside inline blocks are not
always cased like the file on disk (`DW_HiddenLIbrary`), so match
case-insensitively.

**Template libraries.** Maps 1, 2, 4, 5, 6 and 346 are the editor's scratch
space: single events holding dozens of item grants, all 26 HANGMAN letters, one
of everything. They have no PNG. Filter on "is there a PNG for this map" and
they disappear on their own — no need for a blocklist.

---

## 2. Events

### The sprite is usually not on page 0

A pickup or a warp pad normally lives on a **later page**, behind the switch
that arms it, with an invisible `DEV_TEST` placeholder on page 0. Scanning only
page 0 reported MOLLY ROOM LEFT 2 as having no portals when it has six.

Always search all pages for the first one carrying a real graphic. `DEV_TEST`
is the editor's stand-in — a flat labelled square — and nothing wearing it is
meant to be seen. Filtering it out is what stopped an `INIT` box being stamped
onto MOLLY ROOM LEFT 1.

### Sprite sheets

A normal sheet is 4×2 characters, each 3 animation frames across and 4 facings
down, so 12×8 cells. Prefixes matter:

- `$name` — one character, the whole image is a 3×4 grid
- `!name` — an *object* character (doors, props). RPG Maker's own marker.
- neither — the 4×2 grid

A sheet whose dimensions do not divide evenly is **one frame and nothing else**.
`[SF]SW_Cake` is 32×37; slicing it as 12×8 yields a 2×4 pixel "frame" that
composites as nothing at all, which is why the cake appeared to render
successfully while changing zero pixels.

### Transfers

Three patterns, all in use:

1. code `201` — the standard Transfer Player command
2. `reserveTransfer(N, x, y, …)` in a script call
3. OMORI's fade pattern: `setValue(9, mapId)` + `setValue(10, x)` + `setValue(11, y)`

Miss the third and most of Headspace looks disconnected.

---

## 3. Sprite anchoring — the one that keeps biting

**The rule: the whole frame is anchored bottom-centre on the tile.** The drawn
pixels sit wherever they sit inside that frame.

The tempting wrong version is to anchor the *trimmed* pixels. That is off by
exactly the number of blank rows beneath the art — 8px for the singing Bass, 1px
for `DW_MARI`, 0 for a sprite drawn flush to the bottom. Markers placed that way
sit low by a varying amount, which reads as "randomly misaligned" rather than as
one systematic error.

How this was settled: template-match sprites that are already baked into the
shipped PNGs and measure where they really are. 18 of 29 confirmed the offset is
exactly the blank-row count. Switching the rule took full alignment from
**21% → 79%** across every marker in the atlas.

**Exceptions are real and must be measured, not assumed.** `DW_PuzzleObjects_2`
(the conveyor machines) is anchored by the **frame's top-left corner** instead.
That came from JUNKYARD (III), which already has four of these machines painted
into its render: all four agree exactly, +17px right and −3px up from where the
bottom-centre rule puts them.

A sweep across ten maps found the conventions genuinely disagree between sheets,
so `16_render_event_sprites.py` keeps `ANCHOR_FRAME_TOPLEFT` as a table of
*measured* sheets rather than trying for one universal rule. Do not "fix" the
default to match a new sheet — it will move the warp pads, which are correct.

### The missing six pixels

The bottom-centre rule above is the whole frame's *anchor*, and it is not the
whole story: the engine then lifts the sprite. From the game's own
`rpg_objects.js`:

```js
Game_CharacterBase.prototype.shiftY = function() {
    return this.isObjectCharacter() ? 0 : 6;
};
```

`ImageManager.isObjectCharacter` is true exactly when the sheet name starts with
`!`. So a door or a shelf sits flush on its tile and **everything else is drawn
six pixels higher** — every sparkle, every NPC, every loose object on a plain
sheet. None of the game's 172 plugins overrides either function.

There is a second condition, and it is the renderer's rather than the engine's:
an event set to **"below characters" (`priorityType` 0) gets no lift**, because
it is painted with the ground. JUNKYARD (III)'s 96 conveyor belts are that case
— plain sheet, priority 0 — and all 14 sampled sit exactly on their tiles in the
untouched download, while the sparkles beside them are priority 1 and all 16 sit
exactly six pixels above theirs. So the lift needs the *page*, not just the
sheet name; 34 collectible points are on the ground side of that line.

This is what made the sparkle markers look "randomly" low.

### `pattern` belongs in the frame key

A page's `image.pattern` is which of the three animation columns it shows, and
**122 of 501 points are not on column 1** — the microwave is on 2, the first aid
kit on 0, every conveyor machine on 0. A key of `sheet|index|direction` throws
that away, so 28 drew whatever happened to sit on column 1 (a different object
on the same sheet) and then measured *that* frame's outline to place the marker.
Keys are `sheet|index|direction|pattern`; keys without the fourth field are read
as column 1, which is what they were rendered as.

### Sprites you find in the art may not be sprites

Template matching answers "are these pixels here", not "is this an event". The
bed on `FA_TV` and Mari on her picnic blanket both match their character frames
pixel-for-pixel in the shipped PNG *and* appear in a tiles-only re-render: the
artist reused the same art in the tileset. Taken at face value they read as two
sprites disobeying the six-pixel rule, which is enough to talk you out of a rule
that is right. Re-render the map with `13_render_tiled_map.py` and check whether
the pixels are already there before believing a counter-example.

### Rules place; measurement corrects

`29_measure_point_art.py` looks for each point's frame in the map's own PNG
within a tile of where the rule puts it, and records where it actually is. That
is the only thing that gets the leftovers right, and they are all real:

| Case | Correction |
|---|---|
| Sprites this project composited (16 anchors the *trimmed* frame, no lift) | +6 to +26px |
| JUNKYARD TUNNELS 1's own render offset — nine sparkles, all identical | (+1, −2)px |
| Sheets that follow no rule (`DW_PuzzleObjects_2`) | confirmed, not guessed |

One guard earns its place: **a sprite that is one flat colour agrees with any
flat wall.** `!FA_PLAYERHOUSE_OBJ`'s beige panel matched 585 positions in a
single search window and was duly "found" three tiles from the truth. Everything
genuinely recognisable — every sparkle, warp pad and belt machine checked here —
matches in exactly one place, so more than a handful of candidates means stop,
not pick the nearest.

Each rectangle carries `artFit: measured` or `artFit: rule` so the two kinds of
answer stay apart. Only about one point in eight can be measured — most pickups
are on a page the shipped render never drew, and watermelons are not drawn at
all — so both halves have to be right.

### A point that is not there yet

117 of 501 points and 14 watermelons sit on a page behind a switch: the item is
not in the world until something has happened. Three of them are the whole
reason this got written down — THINGAMABOB, DOOHICKEY and WHATCHAMACALLIT are
sparkles that look exactly like the other 33, and none of the three exists
until you have taken the TV girl's list (`Q- Coffee Machine (Start)`). Map100's
SPAGHETTI watermelon is the same: it only drops out of the pinwheel once KEL
has been tagged into throwing at it (`Q- Pinwheel Kite(Throw)`).

**The condition is on the page the marker came from, not page 0.** A pickup
normally lives on a later page behind the switch that arms it, with an
invisible `DEV_TEST` placeholder on page 0. Reading page 0 finds no condition
and reports the point as always available, which is backwards — 117 gated
points become 103. `30_extract_requirements.py` matches the page by the sprite
key the extractor recorded, `sheet|index|direction|pattern`, the same key 28
and 29 use.

Self-switches are not requirements. A self-switch condition means "after you
have already dealt with this event" — the *taken* page of a pickup.

### A key that grants nothing is still a key

`map89` (STUMP ENTRANCE) has an event called `BLACKLETTER` with one page, a
`DEV_TEST` sprite, no commands at all and no item grant. It looks exactly like
the editor's leftovers, and reading it as one was wrong: **it is the A.** The
pickup is wired up somewhere other than the event, so "does this event actually
grant its item" — the rule that correctly keeps out the alphabets sitting on
maps 5, 6, 346 and 457 — silently loses five real keys with it.

What settles it is in Items, not in the maps. Every blackletter carries its own
hint as a notetag:

```
<Blackletter: A>
<BlackLetterClue:在树桩旁边的草丛中>      in the grass beside the stump
```

Five letters were unaccounted for, five letterless `BLACKLETTER` events sit on
region maps, and the clues pair them off one to one: A → map89 STUMP ENTRANCE,
B → map101 EAST FOREST BRIDGE (*an old bridge that fades in and out*),
D → map147 JUNKYARD VI (*near an abandoned container*), G → map132 IGLOO
INTERIOR (*under a trapdoor* — the map holds two events named `Trap Door`),
Y → map134 FROZEN FOREST I (*a field of white snow*, 150×150 of it). The method
checks out on the letters already known: C's clue is *among the giant
pinwheels*, and C is on map100, the map with eleven pinwheel poles.

`31_blackletter_clues.py` reads all 26 and adds the five. All of it comes out
of the **installed game**, not `omori_data_decrypted`: that dump is a different
build whose items carry none of these notetags, and it is also missing
`Doodads`, `Map513` and `Map514`. Check the install before concluding the data
does not say something.

---

## 4. Editor overlays baked into the shipped renders

The goats.dev PNGs have RPG Maker's authoring marks drawn into them: numbered
region squares, sometimes collision tint. Our own renderer skips any layer whose
name contains `REGION` or `COLLISION`; theirs did not.

Two traps:

- **Layer names are not uniform**: `REGION - 20`, `REGION 28`, `Region L0`,
  `region 90`, `REGIONS`, `Region -28`. Match the substring, case-insensitively.
- **`visible: false` does not mean it was not rendered.** 36 maps carry marks on
  hidden layers. Skipping those on the strength of the flag left a `90` running
  down OTHERWORLD LADDER II's rungs, which is what the squares were covering.

The squares come from `Tile_Regions_32x32`, where **the tile's index is the
region number** — so the exact bitmap is available and a candidate tile can be
tested by fitting `shipped = (1-a)·tiles + a·square`. That guard matters: many
marked tiles differ from a clean render simply because real art sits on them,
and repainting those would erase it.

`24_strip_region_overlay.py` erased 248 squares across 15 maps. `map325`
(OTHERWORLD LADDER II) alone had 119, one per rung, hiding a magenta ladder.

---

## 5. Machines and belts

Every machine's script runs the same loop:

```js
var len = 66;
for (var i = 63; i <= len; i++) {
  var key = [mapid, i, 'A'];
  $gameSelfSwitches.setValue(key, trigger);
}
```

So a machine owns a **contiguous block of event ids ending at itself**. Parsing
the bounds gives the grouping for free; guessing from adjacency merges belt runs
that only look like one.

Two machines can drive the same block (JUNKYARD's BlueBot 1-1 and 1-2, one at
each end of the floor) — collapse by range, keep both buttons.

The same idiom drives plenty of things that are **not** belts: a traffic cone in
OUTSKIRTS, a pushable box in FROZEN FOREST, a collapsing bridge in MARINA MAZE,
a row of teleport pads in MOLLY ROOM RIGHT 2. Filter on the event name.

### The baked state is not always the default state

MOLLY ROOM LEFT 2 ships with its belts in the unconditional state. **JUNKYARD
(III) ships with all 99 of its belts already in the self-switch-A state.**
Writing the A-state overlay for it produced an image identical to what was
underneath: clicking the machine worked perfectly and changed *two pixels*.

Measure which state is on the map (compare each belt against both sprites,
majority wins) and draw the other one.

### MOLLY ROOM LEFT 1 has no machine

Its 14 belts have self-switch pages, but nothing in the game ever sets them —
`CE401 ★ CONVEYOR START` only moves the player. There is nothing to click there.

---

## 6. Classifying things

| Question | Reliable answer | What does *not* work |
|---|---|---|
| Is this a quest item? | `itypeId === 2` in Items.json | keyword lists — the game's own classification already contains JOKE BOOK, TEDDY BEAR, WOODEN TRACK and excludes POETRY BOOK |
| Person or object? | the sheet name: `!` prefix, or `OBJECTS`/`IMPORTANTOBJ`/`PuzzleObjects`/`minecart`/`[SF]`/`_TV` | `directionFix` — an NPC posed to face one way has it set too, which filed SMELLYHOBO, KimsMom and JOYSDAD as furniture |
| Is it a mechanism? | its script sets a self-switch on *another* event | "does it change any state" — 1183 hits, every NPC that sets a conversation variable |
| Which letter is this HANGMAN key? | `BLACKLETTER_<X>` in the event name | the 26 `Blackletter A`…`Z` in ENTRANCE TO ABYSS are the board you spell on, not hiding places — the underscore tells them apart |

**Item icons are unusable.** Every `iconIndex` in Items/Weapons/Armors is 0;
OMORI does not use RPG Maker's icon system. Use each event's own sprite frame.

Only 21 of the 26 HANGMAN letters are placed in the shipped world. A, B, D, G
and Y exist only in the template maps.

---

## 7. Regions come from the editor's folder tree

`01_extract_adjacency.js` walks `MapInfos.json` parent/child links, not the
transfer graph. Consequences:

- **Folder nodes have no map.** `86 DREAM WORLD` is a folder — but it also
  parents STUMP ENTRANCE, DEEP WELL and UNDERWATER HIGHWAY, so rooting a region
  there dragged in the entire dream world (202 watermelons). Root on the maps
  themselves when the folder is not what you mean.
- **Sometimes the tree is exactly right.** `133 FROZEN FOREST ENTRANCE` parents
  precisely FROZEN FOREST (I)–(IX), so `roots: [133]` defines Snowglobe Mountain
  in one line.
- **Connectivity cannot substitute.** A flood fill from FROZEN FOREST (I)
  reaches 286 maps: the frozen forest loops back into Otherworld, and from there
  into everything. There is no graph cut. Region boundaries are a judgement
  call.

### Declared dimensions can be wrong

`Map200.json` says SEACOW BARN is 28×28. Its `.AUBREY` and its PNG are both
32×32. The atlas squeezed a 1024px image into an 896px box — the barn came out
12.5% narrow and every tile coordinate on it, including its door's snap point,
landed short. `GLOBAL_DIM_FIXES` exists for this; map200 was the only one left
when the whole atlas was swept.

---

## 8. Leaflet

### `{pane: undefined}` is not "use the default"

`L.Util.setOptions` copies own properties over the defaults, so passing
`{pane: undefined}` **replaces** `'overlayPane'` with undefined. `getPane()`
then returns nothing and `appendChild` throws. Pass the key or don't:

```js
const pane = f.pane(mapId);
L.imageOverlay(url, bounds, pane ? { pane } : {})
```

This is why clicking a belt machine in Per-Map view did nothing at all — the
throw aborted the whole render, so neither the overlay nor the rebuilt markers
appeared.

### Do not re-render from inside a click handler

Tearing down the marker that is still dispatching its own click leaves Leaflet
finishing the dispatch against a removed icon. `setTimeout(render, 0)` — one
tick later the dispatch is over.

### Marker icons do not scale with the map

`divIcon` sizes are screen pixels. A 20px icon over a 7px sparkle looks wrong at
every zoom and differently wrong at each one. Size from the sprite's real height
times `2^zoom`, floored so it stays findable when zoomed out, and re-render on
`zoomend`.

### Never index `svg.children[i]` by logical index

That only held while each route owned exactly one node. The moment one-way
routes gained an arrowhead, every index past them was wrong and dragging a dot
moved someone else's line. Hold references to the nodes you create.

### The browser will serve you a stale image

Hard refresh does not reliably reach images Leaflet puts in an `<img>`. Both
pages accept `?fresh` in the URL, which stamps a timestamp onto every map image.
Reach for it before believing a render is unchanged.

---

## 9. Performance

Measured on the 234-map layout (326 route dots, 358 watermelon overlays):

| Suspect | Reality |
|---|---|
| Rebuilding 2069 snap targets per mousemove | **0.14 ms** — not the problem, despite looking like it |
| `renderRoutes()` per mousemove while dragging a map | **the problem** — destroys and recreates 326 dot divs, rebinds a drag handler to each, rebuilds every SVG node, then `applyLayers()` walks 591 elements toggling three classes each |
| `querySelector` per map inside the marquee loop | 234 DOM searches per mousemove |

Fixes: update only the routes actually affected, in place; build an id→element
index once per marquee move; cache the snap targets anyway since it is free.

The lesson is the ordinary one — the loop that *looks* expensive was 1% of the
cost, and the innocuous-looking helper call was 99%. Measure first.

---

## 10. How to find things out

**Measure against the shipped art.** Nearly every rule in this file came from
template-matching a sprite against the PNGs and reading off the offset, not from
reasoning about RPG Maker. When a rule and the pixels disagree, the pixels win.

**Run the page's real code without a browser.** Extract the `<script>` from the
HTML, stub `L` and `document`, and call the real functions on the real data. It
catches most logic errors, and it caught none of the Leaflet-specific ones —
which is itself useful to know.

**When the browser is the only witness, make it testify.** `web/belt_test.html`
loads the same data, performs the same steps, and prints each result *on the
page*. It turned "点了没用" into "the overlay changes 2 pixels" in one screenshot.
Reach for this instead of a fourth round of guessing.

**Check what is being served, not what is on disk.** A file can be correct, the
server can be correct, and the page can still show last week's — cache, or a
server started in a different directory. Open the asset URL directly.

**Beware patch scripts that assert before writing.** A failed assertion in the
middle of a batch of edits leaves the file untouched while the earlier edits
*look* applied. Verify after every batch, not at the end of several.

**Idempotence is the cheap test.** Every generator here produces byte-identical
output on a second run. When it does not, something is reading its own output.

**Back up before mutating PNGs.** `17_erase_party_sprites.py` once painted 35
maps with black silhouettes because it had no presence check and the tile
renderer fills the void with opaque black. Restoring from the backup was a
non-event; without one it would have been a re-download.

---

## 11. Pipeline order

Later steps read what earlier ones wrote.

```
01_extract_adjacency.js  <region>     maps.json + edges.json + highlights.json
05_cut_submaps.py        <region>     slice PNGs for sub-maps declared in 01
13_render_tiled_map.py   <ids>        tiles-only render (no events, no overlays)
16_render_event_sprites.py            composite missing event sprites onto PNGs
18_trim_black_bg.py      <ids>        clear opaque black backdrops
24_strip_region_overlay.py            erase baked region squares
22_extract_conveyors.py               belt groups + reversed-state overlays
23_extract_collectibles.js            collectibles.json  (all layers)
28_extract_point_sprites.py           point sprites + writes `art` rects back
                                      into collectibles.json — run after 23
29_measure_point_art.py               finds each sprite in the map's own PNG and
                                      corrects its rect — run after 22 and 28,
                                      and again whenever either is re-run
26_slice_world_stitch.py              per-region stitched images from the
                                      all-regions layout — run after 01
31_blackletter_clues.py               the 5 clue-placed HANGMAN keys + all 26
                                      clues — run after 23, before 30
30_extract_requirements.py            `requires` on gated points + watermelons
                                      — run after 23, 31 and 01
```

**Never re-run 29 after erasing baked sprites.** It locates each point by
template-matching the map's own PNG. Paint a sprite out and it can no longer be
found, so the 59 rects that read `artFit: measured` would quietly fall back to
`rule`. Measure first, erase after, and do not go back.

Adding a region touches more than the extractor: `ALL_REGIONS`,
`REGION_DEFAULTS`, `STITCHED_VARIANTS`, `REGION_ROUTES` and the dropdown in
`web/index.html`; `REGIONS` in `web/stitcher_all.html`; `REGIONS` in
`26_slice_world_stitch.py`.

**That list is not optional.** Splitting Snowglobe Mountain out of Otherworld
without updating the stitcher's hardcoded `REGIONS` removed five maps from its
metadata; `renderPlaced` dereferenced `mapMeta[id].width` unguarded, threw at
map 142 of 234, and took 92 maps and all 163 routes down with it. The loop now
skips unknown maps and says so in the console.
