#!/usr/bin/env node
/**
 * Scan all Faraway Town maps and build an adjacency graph.
 *
 * For each event page, collect transfers from any of these patterns:
 *   1. code 201 (standard Transfer Player command)
 *   2. code 355/655 with reserveTransfer(N, x, y, ...)
 *   3. code 355/655 with setValue(9, mapId) + setValue(10, x) + setValue(11, y)
 *      (OMORI's standard fade-transition pattern; Var[9]=mapId, [10]=x, [11]=y)
 *
 * Outputs:
 *   data/faraway_maps.json  — list of Faraway map IDs + names + dimensions
 *   data/faraway_edges.json — directed edges with coordinates
 */

const fs = require('fs');
const path = require('path');

const DECRYPTED = '/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted';
const OUT_DIR = path.join(__dirname, '..', 'data');

// Region configs: roots = top-level mapInfo IDs to walk via parent-child tree.
// excludeRoots = subtrees to subtract (e.g. otherworld minus junkyard).
// extraMaps = additional map IDs to pull in (reward rooms accessed via teleport
// from this region, e.g. Map433 ALCOVES I = pyrefly waterfall room).
const REGIONS = {
  faraway:             { roots: [12, 77],   prefix: 'faraway'             },
  junkyard:            { roots: [128, 142], prefix: 'junkyard'            },
  orange_oasis:        { roots: [106],      prefix: 'orange_oasis',
                         extraMaps: [437] },                                  // face wall reward
  pyrefly_forest:      { roots: [152],      prefix: 'pyrefly_forest',
                         extraMaps: [433] },                                  // waterfall + face wall reward
  sweethearts_castle:  { roots: [171],      prefix: 'sweethearts_castle',
                         extraMaps: [433, 437, 453] },                        // face walls + club sandwich
  vast_forest:         { roots: [93],       prefix: 'vast_forest',
                         excludeRoots: [106, 152, 171],
                         extraMaps: [343, 89, 92, 90] },                      // SUMMONING CIRCLE + STUMP ENTRANCE + FOREST PLAYGROUND + NORTH COAST
  otherworld:          { roots: [117],      prefix: 'otherworld',
                         // FROZEN FOREST ENTRANCE and everything under it, plus
                         // Map132's igloo rooms, are Snowglobe Mountain's.
                         excludeRoots: [128, 142, 133],
                         extraMaps: [433, 437] },                             // face walls (453 club sandwich
                                                                              // dropped: no otherworld door leads there)
  deep_well:           { roots: [188],      prefix: 'deep_well',
                         extraMaps: [
                           91, 330,                         // NORTH LAKE + ALT
                           199, 200, 203, 211,              // SEACOW FARM/BARN + UNDERWATER HIGHWAYS
                           493, 501, 502,                   // VIEW: DEEP WELL + LOST AT SEA I/II
                           // The rooms hanging off Map203 UNDERWATER HIGHWAY. None of
                           // them were collected, taking 19 watermelons with them.
                           204, 205, 206, 207, 260, 261,
                           430,                             // ENDLESS HIGHWAY — Map211 at this end,
                                                            // LAST RESORT Map191 at the other
                           433, 437,                        // face wall rewards
                         ] },
  deeper_well:         { roots: [215],      prefix: 'deeper_well',
                         extraMaps: [
                           // THE ABYSS — the descent below UNDERWATER HIGHWAY, reached
                           // from Map215 'HITCHHIKER'. Only its last room (258) had been
                           // collected; the six above it, and their 14 watermelons, hadn't.
                           201, 253, 254, 255, 256, 257, 258,
                           433, 437,                        // alcoves I (m495 face wall) + II (m495 side)
                           453,                             // club sandwich (Map215 'Face Wall' lands here)
                         ] }, // PATH TO TRENCH + DEEPERWELL FALLS/PATH + WHIRLPOOLS + TRENCH + HUMPHREY'S CAVE
  // Inside HUMPHREY. The whale himself is Deeper Well's — you meet him in
  // HUMPHREY'S CAVE (m216) and that is a place on the sea floor — but
  // everything past his uvula is a self-contained dungeon of 34 maps, three
  // named wings (MARINA, MEDUSA, MOLLY) with a boss each, and it dwarfed the
  // region it was filed under. It carries no room slices of its own.
  //
  // Listed by hand because the chain has no transfer events the walker can
  // follow: access from m216 is scripted, so the editor's map tree is the only
  // thing that relates them and it does not.
  humphrey:            { roots: [],         prefix: 'humphrey',
                         extraMaps: [
                           217, 218,                        // SLIME GIRL'S LAIR + HUMPHREY'S UVULA (the way in)
                           219, 220, 221, 222, 223, 224, 225, 226, 227,   // MARINA wing
                           228, 229, 230, 231, 232, 233, 234,             // MEDUSA wing
                           235, 236, 237, 238, 239, 240, 241, 243, 245, 247, 248,  // MOLLY wing
                           242, 244,                        // BOSS RUSH battle room + lobby
                           249,                             // HUMPHREY BOSS ROOM
                           250, 251,                        // MEDUSA MAZE 1 + 2
                           437,                             // alcoves II — m223 / m239 / m251 face walls
                         ] },
  // SNOWGLOBE MOUNTAIN. The game gives it no folder and no map of its own, so
  // where it starts is a judgement call the player made: the four igloo rooms
  // cut out of Map132 are the way in, and everything behind them is the
  // mountain. That "everything" needs no list — FROZEN FOREST ENTRANCE is the
  // parent of exactly FROZEN FOREST (I) through (IX) in the editor's own tree,
  // so one root covers all ten. Map132 is listed so its slices can be cut here;
  // the uncut parent is not in the world layout, so nothing is drawn twice.
  snowglobe_mountain:  { roots: [133],      prefix: 'snowglobe_mountain',
                         extraMaps: [132] },
  // WHITE SPACE and the NEIGHBOUR'S ROOM behind it. Rooted on the two maps
  // themselves, not on their folder: DREAM WORLD also parents STUMP ENTRANCE,
  // DEEP WELL and UNDERWATER HIGHWAY, so rooting there drags in the entire
  // dream world. MAP OF TRUTH's ev20 opens onto the Neighbour's Room, which is
  // how you reach this from the Deep Well route.
  white_space:         { roots: [87, 88],   prefix: 'white_space'         },
  forest_playground:   { roots: [92],       prefix: 'forest_playground'   }, // single map
  last_resort:         { roots: [191],      prefix: 'last_resort',
                         extraMaps: [298, 453] },                             // Faces of Omori + club sandwich
};

// Global dimFixes applied to ALL regions (deep_well/deeper_well/last_resort/otherworld)
const GLOBAL_DIM_FIXES = {
  118: { width: 24, height: 20 },
  126: { width: 38, height: 40 },
  132: { width: 44, height: 44 },
  133: { width: 30, height: 27 },
  189: { width: 21, height: 125 },
  195: { width: 25, height: 44 },
  // SEACOW BARN declares 28x28, but its .AUBREY and the shipped PNG are both
  // 32x32. Without this the atlas squeezed a 1024px image into an 896px box —
  // the barn came out 12.5% narrow and every tile coordinate on it, including
  // the snap point at its door, landed short of where it belongs.
  200: { width: 32, height: 32 },
  216: { width: 23, height: 48 },
  // Humphrey interior: PNG sizes differ from declared (goats.dev rendered at PNG dims).
  221: { width: 33, height: 38 },  // MARINA ROOM 1: PNG is 1 col wider
  222: { width: 40, height: 22 },  // MARINA ROOM 2: PNG is 2 cols narrower, 1 row taller
  223: { width: 51, height: 51 },  // MARINA ROOM 3: PNG is 1 row taller
  238: { width: 77, height: 36 },  // MOLLY ROOM RIGHT 2: PNG is 1 col wider
  368: { width: 24, height: 30 },
  437: { width: 62, height: 70 },
};

const region = process.argv[2];
if (!region || !REGIONS[region]) {
  console.error('Usage: node 01_extract_adjacency.js <region>');
  console.error('  region: ' + Object.keys(REGIONS).join(' / '));
  process.exit(1);
}
const ROOTS = REGIONS[region].roots;
const EXCLUDE_ROOTS = REGIONS[region].excludeRoots || [];
const EXTRA_MAPS = REGIONS[region].extraMaps || [];
const PREFIX = REGIONS[region].prefix;

const mapInfos = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'MapInfos.json'), 'utf8'));

// ── Watermelon prize templates (Map 2 = "❀ > TREASURES" library) ──────────
// Each melonCopy event in the game uses YEP_EventCopier's <Copy Event: NAME>
// notetag to inherit behavior from a Map 2 event with that exact name. We
// scan Map 2 once and build a lookup: templateName → { kind, itemName }.
// kind ∈ {'Weapon','Armor','Item'} (charms are Armor in OMORI's data model).
const ITEMS   = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Items.json'),   'utf8'));
const WEAPONS = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Weapons.json'), 'utf8'));
const ARMORS  = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Armors.json'),  'utf8'));
const GAIN_TABLES = { Item: ITEMS, Weapon: WEAPONS, Armor: ARMORS };
// Find the first add-op gain command (op param[1]===0) in a list of pages.
function firstPrizeIn(pages) {
  const map = { 126: 'Item', 127: 'Weapon', 128: 'Armor' };
  for (const p of (pages || [])) {
    for (const c of (p.list || [])) {
      const kind = map[c.code]; if (!kind) continue;
      const pp = c.parameters || [];
      if (pp[1] !== 0) continue;  // skip removes
      const id = pp[0];
      const itemName = GAIN_TABLES[kind][id]?.name || '?';
      return { kind, itemName };
    }
  }
  return null;
}
// ── Watermelon prize templates (Map 2 = "❀ > TREASURES" library) ──────────
// Each melonCopy event in the game uses YEP_EventCopier's <Copy Event: NAME>
// notetag to inherit behavior from a Map 2 event with that exact name. We
// scan Map 2 once and build a lookup: lowercase(templateName) → {kind, itemName}.
// kind ∈ {'Weapon','Armor','Item'} (charms are Armor in OMORI's data model).
// Case-insensitive lookup because junkyard notes have inconsistent capitalization
// (e.g. "melonHotdog" vs Map 2's "melonHotDog").
const TEMPLATES = (() => {
  const m2 = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Map002.json'), 'utf8'));
  const out = {};
  for (const ev of (m2.events || [])) {
    if (!ev || !ev.name) continue;
    const prize = firstPrizeIn(ev.pages);
    if (prize) out[ev.name.toLowerCase()] = prize;
  }
  return out;
})();
console.log(`Loaded ${Object.keys(TEMPLATES).length} melon-prize templates from Map 2.`);

function descendants(rootId) {
  const result = new Set([rootId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (let i = 0; i < mapInfos.length; i++) {
      if (mapInfos[i] && result.has(mapInfos[i].parentId) && !result.has(i)) {
        result.add(i);
        changed = true;
      }
    }
  }
  return [...result].sort((a, b) => a - b);
}

function loadMap(mapId) {
  const fp = path.join(DECRYPTED, `Map${String(mapId).padStart(3, '0')}.json`);
  if (!fs.existsSync(fp)) return null;
  return JSON.parse(fs.readFileSync(fp, 'utf8'));
}

function scriptStr(cmd) {
  if (cmd.code !== 355 && cmd.code !== 655) return null;
  return cmd.parameters?.[0] || '';
}

/**
 * Walk through a page's list of commands and collect transfers.
 * Returns array of { kind, dstMap, dstX, dstY }.
 *
 * For the setValue(9/10/11, ...) pattern: scan linearly, accumulate the most
 * recent values for each var, and emit a transfer when we see all three set
 * within the same page (treat any subsequent setValue(9) as a new transfer).
 */
function collectTransfers(pageList) {
  const transfers = [];
  let curMap = null, curX = null, curY = null;
  for (const cmd of (pageList || [])) {
    // pattern 1: code 201
    if (cmd.code === 201 && cmd.parameters?.[0] === 0) {
      transfers.push({
        kind: 'code201',
        dstMap: cmd.parameters[1],
        dstX: cmd.parameters[2],
        dstY: cmd.parameters[3],
      });
      continue;
    }
    const s = scriptStr(cmd);
    if (!s) continue;
    // pattern 2: reserveTransfer(N, x, y, ...)
    const rt = s.match(/reserveTransfer\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (rt) {
      transfers.push({
        kind: 'reserveTransfer',
        dstMap: parseInt(rt[1]),
        dstX: parseInt(rt[2]),
        dstY: parseInt(rt[3]),
      });
      continue;
    }
    // pattern 3: setValue(9, mapId) / setValue(10, x) / setValue(11, y)
    const m9 = s.match(/setValue\(\s*9\s*,\s*(\d+)\s*\)/);
    const m10 = s.match(/setValue\(\s*10\s*,\s*(\d+)\s*\)/);
    const m11 = s.match(/setValue\(\s*11\s*,\s*(\d+)\s*\)/);
    if (m9) {
      // start new transfer (in case there were multiple in one page list)
      if (curMap !== null) {
        transfers.push({
          kind: 'setValue',
          dstMap: curMap,
          dstX: curX,
          dstY: curY,
        });
      }
      curMap = parseInt(m9[1]); curX = null; curY = null;
    }
    if (m10 && curMap !== null) curX = parseInt(m10[1]);
    if (m11 && curMap !== null) curY = parseInt(m11[1]);
  }
  if (curMap !== null) {
    transfers.push({
      kind: 'setValue',
      dstMap: curMap,
      dstX: curX,
      dstY: curY,
    });
  }
  return transfers;
}

// ----- Main -----
const excludeSet = new Set(EXCLUDE_ROOTS.flatMap(descendants));
const regionIds = [...new Set([...ROOTS.flatMap(descendants), ...EXTRA_MAPS])].filter(id => !excludeSet.has(id)).sort((a,b)=>a-b);
const regionSet = new Set(regionIds);
console.log(`${region} maps: ${regionIds.length} (root ids ${ROOTS.join(',')})`);

const mapMeta = {};
const allEdges = [];
const highlights = { watermelons: [] };  // events of special interest (e.g. melons)

for (const mapId of regionIds) {
  const map = loadMap(mapId);
  if (!map) {
    console.warn(`  Map${mapId}: file not found, skipping`);
    continue;
  }
  mapMeta[mapId] = {
    id: mapId,
    name: (mapInfos[mapId].name || '').trim(),
    width: map.width,
    height: map.height,
    parallaxName: map.parallaxName || null,
    bgm: map.bgm?.name || null,
  };
  for (const ev of (map.events || [])) {
    if (!ev) continue;
    // Collect watermelons (melon events). Color logic:
    //   1. start from sprite-sheet (DW_IMPORTANTOBJ → green, DW_IMPORTANTOBJ_2 → blue)
    //   2. read the <Copy Event: NAME> notetag (YEP_EventCopier) — at runtime the
    //      event clones a template from Map 2 ("❀ > TREASURES"). If the template
    //      gives a real prize, upgrade color to 'blue' and stash prize info.
    const evImg = ev.pages?.[0]?.image;
    if (evImg && /melon/i.test(ev.name || '')) {
      let color = (evImg.characterName === 'DW_IMPORTANTOBJ_2') ? 'blue'
                : (evImg.characterName === 'DW_IMPORTANTOBJ')   ? 'green' : null;
      if (color) {
        let prize = null;
        // 1) Look up Copy Event notetag → Map 2 template (case-insensitive).
        const m = (ev.note || '').match(/<Copy Event:\s*([A-Za-z0-9_]+)\s*>/i);
        if (m) {
          const tpl = m[1];
          const t = TEMPLATES[tpl.toLowerCase()];
          if (t) prize = { template: tpl, ...t };
        }
        // 2) Fallback: event is self-contained (no notetag, or template unknown) —
        // scan its own pages for a gain command. Catches melonPoetryBook (M147)
        // and melonCheapGoldWatch (M142), which give items directly.
        if (!prize) {
          const self = firstPrizeIn(ev.pages);
          if (self) prize = { template: null, ...self };
        }
        // Color rule: blue ONLY for weapon/charm (Armor) prizes — the real "good
        // stuff". Item prizes (consumables, rubber band, soda…) are decoys → green.
        if (prize && (prize.kind === 'Weapon' || prize.kind === 'Armor')) color = 'blue';
        highlights.watermelons.push({
          mapId, evId: ev.id, name: ev.name, x: ev.x, y: ev.y, color,
          ...(prize ? { prize } : {}),
        });
      }
    }
    // Parse <Hitbox L/R/T/B: N> from event note — extends trigger zone
    const hb = { L: 0, R: 0, T: 0, B: 0 };
    const note = ev.note || '';
    let m;
    if (m = note.match(/<Hitbox Left:\s*(\d+)>/i))   hb.L = +m[1];
    if (m = note.match(/<Hitbox Right:\s*(\d+)>/i))  hb.R = +m[1];
    if (m = note.match(/<Hitbox Top:\s*(\d+)>/i))    hb.T = +m[1];
    if (m = note.match(/<Hitbox Bottom:\s*(\d+)>/i)) hb.B = +m[1];
    for (let pi = 0; pi < (ev.pages || []).length; pi++) {
      const transfers = collectTransfers(ev.pages[pi].list);
      for (const t of transfers) {
        allEdges.push({
          from: { mapId, evId: ev.id, evName: ev.name, x: ev.x, y: ev.y, page: pi, hitbox: hb },
          to: { mapId: t.dstMap, x: t.dstX, y: t.dstY },
          kind: t.kind,
        });
      }
    }
  }
}

const internal = allEdges.filter(e => regionSet.has(e.to.mapId));
const external = allEdges.filter(e => !regionSet.has(e.to.mapId));

console.log(`\nEdges:  total=${allEdges.length}  internal=${internal.length}  external=${external.length}`);

// Group by source for inspection
const bySource = {};
for (const e of internal) (bySource[e.from.mapId] = bySource[e.from.mapId] || []).push(e);

console.log(`\nInternal edges per map:`);
for (const id of regionIds.slice(0, 20)) {
  const exits = bySource[id] || [];
  const m = mapMeta[id];
  if (!m) continue;
  console.log(`  Map${id} "${m.name}" (${m.width}×${m.height}): ${exits.length} exits`);
  for (const e of exits.slice(0, 3)) {
    const dn = (mapMeta[e.to.mapId]?.name || '?').trim();
    console.log(`    [${e.kind}] (${e.from.x},${e.from.y}) "${e.from.evName}" → Map${e.to.mapId} "${dn}" (${e.to.x},${e.to.y})`);
  }
  if (exits.length > 3) console.log(`    ... +${exits.length - 3} more`);
}

// Patches: dim fixes (Tiled format differs from RPG MV format for some maps)
// + per-region "vanilla render" aliases used to compare goats.dev vs our render.
const PATCHES = {
  faraway: {
    dimFixes: {
      40:  { height: 32 },  // Church DAY (PNG matches Tiled, not RPG MV)
      43:  { height: 32 },  // Church SUNSET
      85:  { height: 32 },  // Church NIGHT
      54:  { width: 31, height: 44 }, // PARK + THAT PLACE
      59:  { height: 42 },  // FIXIT DAY
      69:  { height: 42 },  // FIXIT SUNSET
      64:  { height: 44 },  // Lake DAY
      74:  { height: 44 },  // Lake SUNSET
      67:  { width: 21 },   // GINOS SUNSET
      368: { width: 24, height: 30 }, // DELIVERY 3-1
    },
    vanillaAliases: { 1031: 31, 1040: 40 },  // {fakeId: realId}
    // Map341 RECYCULTIST HQ — a multi-level cave laid out as six unconnected
    // rooms on one 80x80 canvas. Level names come from the transfer events
    // linking them (TO TOP / MID / MID 2 / LOWER / LOWER LEVEL 2).
    //
    // Those transfers, and the ladder events that stand in for the climbs,
    // sit just *outside* each room's own tiles — the four LADDER events are at
    // (21,50-53), above the west lower room — so the polygons reach past the
    // floor to take them in. Without that the rooms slice out with no snap
    // points and nothing to connect a route to.
    subMaps: {
      3411: { src: 341, name: '[upper west — hammer wall]', polygon: [[14,13],[25,13],[25,29],[14,29]] },
      3412: { src: 341, name: '[boss chamber]',             polygon: [[55,22],[64,22],[64,36],[55,36]] },
      3413: { src: 341, name: '[mid — congregation]',       polygon: [[31,28],[42,28],[42,42],[31,42]] },
      3414: { src: 341, name: '[lower west — kel throw]',   polygon: [[14,50],[26,50],[26,68],[14,68]] },
      3415: { src: 341, name: '[lower centre]',             polygon: [[37,54],[51,54],[51,68],[37,68]] },
      3416: { src: 341, name: '[entrance from park]',       polygon: [[60,54],[71,54],[71,68],[60,68]] },
    },
  },
  orange_oasis: {
    // Manual route anchor — center of the Summoning Circle on Map343.
    // The real teleport events sit at (15,11) and (15,15); add a snap point
    // at the visual circle center so routes can attach.
    syntheticEdges: [
      { from: { mapId: 343, evId: 900, evName: 'Summoning Circle (center)', x: 15, y: 13, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 343, x: 15, y: 13 }, kind: 'manual' },
      // Flour-pile landing spots (where the team falls from previous map). These act as
      // snap targets on the destination side so routes can terminate at the visible pile.
      // Pantry 1 (3441): team falls from map342 (rolling stone) at (14,16) parent → (3,5) local.
      { from: { mapId: 3441, evId: 901, evName: 'Flour Pile (team landing)', x: 3, y: 5, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 3441, x: 3, y: 5 }, kind: 'manual' },
      // Pantry 2/3 also have flour-pile decorations even though only Pantry 1 is the actual landing.
      // Add snap points for visual route planning convenience.
      { from: { mapId: 3442, evId: 902, evName: 'Flour Pile', x: 3, y: 5, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 3442, x: 3, y: 5 }, kind: 'manual' },
      { from: { mapId: 3443, evId: 903, evName: 'Flour Pile', x: 3, y: 5, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 3443, x: 3, y: 5 }, kind: 'manual' },
      // Pantry north exits (door to Baking Room). These are sub-map snap targets at local (3, 0).
      { from: { mapId: 3441, evId: 910, evName: 'Exit to Baking Room', x: 3, y: 0, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 345, x: 10, y: 55 }, kind: 'manual' },
      { from: { mapId: 3442, evId: 910, evName: 'Exit to Baking Room', x: 3, y: 0, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 345, x: 14, y: 55 }, kind: 'manual' },
      { from: { mapId: 3443, evId: 910, evName: 'Exit to Baking Room', x: 3, y: 0, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 345, x: 18, y: 55 }, kind: 'manual' },
      // Map116 (Arrow Cave) bottom destination — Map106 ev8 lands here but no `from`-side snap existed.
      { from: { mapId: 116, evId: 901, evName: 'Arrow Cave Bottom Landing', x: 53, y: 145, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 116, x: 53, y: 145 }, kind: 'manual' },
      // Map343 (Summoning Circle) bottom flour pile (dough mound) — player falls in from above
      { from: { mapId: 343, evId: 920, evName: 'Flour Pile (bottom)', x: 15, y: 47, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 343, x: 15, y: 47 }, kind: 'manual' },
      // Map333 (Train Station) interior train terminal door
      { from: { mapId: 333, evId: 920, evName: 'Train Terminal', x: 18, y: 11, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 333, x: 18, y: 11 }, kind: 'manual' },
    ],
    // Map344 PANTRY is 3 disconnected pantry rooms — slice into sub-maps.
    // Map112 OASIS INTERIORS is 4 disconnected rooms — slice the same way.
    subMaps: {
      // ALCOVES II alcove 1 — reached from Map106 (ORANGE OASIS) "Face Wall".
      4371: { src: 437, name: '[alcove 1]', polygon: [[3,4],[12,4],[12,16],[3,16]] },
      3441: { src: 344, name: '[pantry 1]', polygon: [[11,11],[18,11],[18,20],[11,20]] },
      3442: { src: 344, name: '[pantry 2]', polygon: [[31,11],[38,11],[38,20],[31,20]] },
      3443: { src: 344, name: '[pantry 3]', polygon: [[50,11],[57,11],[57,20],[50,20]] },
      // Map112 OASIS INTERIORS — 4 rooms (top-L Mina, top-R Donut shop, bot-L+R orange interiors)
      // Polygons extend 1 row below visible content to include doorway exit tiles.
      1121: { src: 112, name: '[top-L Mina]',    polygon: [[11,11],[22,11],[22,21],[11,21]] },
      1122: { src: 112, name: '[top-R Donut]',   polygon: [[42,10],[54,10],[54,22],[42,22]] },
      1123: { src: 112, name: '[bot-L orange]',  polygon: [[13,43],[20,43],[20,55],[13,55]] },
      1124: { src: 112, name: '[bot-R orange]',  polygon: [[44,43],[51,43],[51,55],[44,55]] },
    },
    // Manual watermelons NOT detected by the melonCopy scan (e.g. Tomb Prize uses a different event template).
    manualWatermelons: [
      { mapId: 334, x: 13, y: 18, name: 'Tomb Prize (blue)', color: 'blue' },
    ],
    dimFixes: {
      113: { width: 29 },
      116: { width: 88, height: 150 },
      344: { width: 72, height: 32 },
      345: { width: 29, height: 62 },
      437: { width: 62, height: 70 },
    },
    vanillaAliases: {},
  },
  deeper_well: {
    syntheticEdges: [
      // Map259 (MAP OF TRUTH) — the red water starts right under the rock wall
      // that caps the map, and that waterline is the only thing up there to
      // line a route up against. (11,6) is the first water tile: (11,5) is
      // still wall.
      { from: { mapId: 259, evId: 905, evName: 'Red water — under the north wall', x: 11, y: 6, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 259, x: 11, y: 6 }, kind: 'manual' },
      // Map229 (Medusa River 4) inbound landings — no FROM-side events exist at these tiles
      // (player arrives via setValue-style scripts from m231 and m233).
      { from: { mapId: 229, evId: 900, evName: 'From River 3 (landing)', x: 1, y: 16, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 229, x: 1, y: 16 }, kind: 'manual' },
      { from: { mapId: 229, evId: 901, evName: 'From River 2 (landing)', x: 8, y: 34, hitbox: {L:0,R:0,T:1,B:0} },
        to:   { mapId: 229, x: 8, y: 34 }, kind: 'manual' },
      // Map215's two exits down the right-hand side both leave the region —
      // to BROKEN BRIDGE and UNDERWATER HIGHWAY, which live in deep_well — so
      // they land in `external` and left that whole edge with no snap target.
      // The nearest one was the Face Wall at (18,26), a dozen tiles too high.
      { from: { mapId: 215, evId: 904, evName: 'To Broken Bridge', x: 19, y: 38, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 215, x: 19, y: 38 }, kind: 'manual' },
      { from: { mapId: 215, evId: 905, evName: 'To Underwater Highway', x: 19, y: 48, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 215, x: 19, y: 48 }, kind: 'manual' },
      { from: { mapId: 215, evId: 906, evName: 'To Underwater Highway (west)', x: 0, y: 49, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 215, x: 0, y: 49 }, kind: 'manual' },
      // The beach at the top of WHIRLPOOLS 2 (tiles x 31-41, y 7-10) is left
      // by interacting with the branch coral rather than by walking into an
      // exit, so nothing there registers as a transfer and the whole island had
      // no snap target. Anchor its centre — which is the coral's own tile.
      // Also placed on the [main path] slice: sub-map propagation runs before
      // synthetic edges are added, so an anchor on the parent never reaches it.
      { from: { mapId: 447, evId: 908, evName: 'Branch Coral (to Vast Forest)', x: 36, y: 8, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 447, x: 36, y: 8 }, kind: 'manual' },
      { from: { mapId: 4473, evId: 908, evName: 'Branch Coral (to Vast Forest)', x: 32, y: 8, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 4473, x: 32, y: 8 }, kind: 'manual' },
      // BOSS RUSH BATTLE ROOM had no snap points at all. Its two warp pads are
      // named 'To Molly Boss Room' but carry no transfer command — the teleport
      // is driven from elsewhere — so extraction found nothing to hang an edge
      // on. Anchor the pads themselves. Nothing sits on the room's right: the
      // floor stops at x=18 and the last two columns are solid wall.
      { from: { mapId: 242, evId: 909, evName: 'Warp pad (north)', x: 10, y: 12, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 242, x: 10, y: 12 }, kind: 'manual' },
      { from: { mapId: 242, evId: 910, evName: 'Warp pad (south)', x: 10, y: 30, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 242, x: 10, y: 30 }, kind: 'manual' },
    ],
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // ALCOVES I keeps one map per alcove but runs it as two rooms. The
      // watermelon is a single event with self-switch A for one approach and
      // B for the other, gated on switch 1499, so taking it on one route
      // leaves it sitting there on the other — the game hands out a reward
      // per route. Switch 1499 also decides which way back exists, and the
      // Sweetheart's Castle door carries a cake sprite, which is how the two
      // versions tell themselves apart on screen. So: one slice per route.
      4336: { src: 433, name: '[ocean alcove — via deeper well]', polygon: [[54,32],[60,32],[60,44],[54,44]] },

      // ALCOVES II — the three alcoves whose face walls are in this region:
      // Map239 -> 4373, Map251 (MEDUSA MAZE 2) -> 4376, Map223 -> 4379.
      4373: { src: 437, name: '[alcove 3]', polygon: [[48,3],[58,3],[58,15],[48,15]] },
      4376: { src: 437, name: '[alcove 6]', polygon: [[48,25],[58,25],[58,37],[48,37]] },
      4379: { src: 437, name: '[alcove 10]', polygon: [[48,47],[58,47],[58,59],[48,59]] },
      // Map453 CLUB SANDWICH is a room atlas: 5 isolated rooms on one 66x50
      // canvas, separated by fully collision-blocked black background. Each
      // room is sliced out under whichever region's door leads into it.
      // This one is reached from Map215 'Face Wall'.
      4532: { src: 453, name: '[bounce shroom room]', polygon: [[29,3],[38,3],[38,15],[29,15]] },
      // Whirlpool destinations. Map495 DEEPERWELL FALLS is the hub holding all
      // 13 'Pool X' entrances; jumping in lands in one of these seabed rooms,
      // which are parked as separate islands on two 75x75 canvases. Room names
      // are the pool letters that open onto them.
      2101: { src: 210, name: '[pool C-D room]', polygon: [[2,0],[29,0],[29,23],[2,23]] },
      2102: { src: 210, name: '[pool E-Q room]', polygon: [[46,0],[68,0],[68,28],[46,28]] },
      2103: { src: 210, name: '[pool H-I-L room]', polygon: [[6,37],[33,37],[33,70],[6,70]] },
      2104: { src: 210, name: '[pool A-B room]', polygon: [[53,36],[71,36],[71,61],[53,61]] },
      4471: { src: 447, name: '[pool S-T room]', polygon: [[57,5],[70,5],[70,33],[57,33]] },
      4472: { src: 447, name: '[branch coral room]', polygon: [[40,50],[49,50],[49,66],[40,66]] },
      // The long route between the pools. Upper half spans the full width, then
      // it narrows to a winding descent — a bounding rectangle would swallow the
      // branch coral room sitting off to the right at y 50-65, so the polygon
      // steps in to follow the path's own shape.
      4473: { src: 447, name: '[main path — pools F & G]', polygon: [
        [4,0],[48,0],[48,35],[24,35],[24,73],[14,73],[14,35],[4,35],
      ]},
    },
  },
  deep_well: {
    syntheticEdges: [
      // Map339 MAIN CURRENTS is 55 wide and full to both edges on every one of
      // its 100 rows, so "somewhere along the left side" is the whole side.
      // A vertical hitbox makes these slide snaps: X is pinned to the edge and
      // Y is free, so one anchor covers the entire edge — 200 point anchors
      // would say the same thing and bury the map in dots.
      { from: { mapId: 339, evId: 906, evName: 'Left edge (slides)', x: 0, y: 49, hitbox: {L:0,R:0,T:1,B:0} },
        to:   { mapId: 339, x: 0, y: 49 }, kind: 'manual' },
      { from: { mapId: 339, evId: 907, evName: 'Right edge (slides)', x: 54, y: 49, hitbox: {L:0,R:0,T:1,B:0} },
        to:   { mapId: 339, x: 54, y: 49 }, kind: 'manual' },
      // Map359 (Abandoned House Interior) — only event is ev1 Teleport at (18,19), not extracted
      { from: { mapId: 359, evId: 920, evName: 'Teleport', x: 18, y: 19, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 359, x: 18, y: 19 }, kind: 'manual' },
      // Map206's west exit goes to PATH TO TRENCH over in deeper_well, so it
      // was an external edge and the left edge had no snap target at all.
      { from: { mapId: 206, evId: 907, evName: 'To Path to Trench', x: 0, y: 19, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 206, x: 0, y: 19 }, kind: 'manual' },
    ],
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // Map421 LIGHTHOUSE — 2 disconnected rooms
      4211: { src: 421, name: '[top room]',    polygon: [[10,4],[16,4],[16,12],[10,12]] },
      4212: { src: 421, name: '[main room]',   polygon: [[8,25],[19,25],[19,39],[8,39]] },
    },
  },
  pyrefly_forest: {
    syntheticEdges: [
      // Map336 top — castle entrance cutscene (no real event, but visually a transition point)
      { from: { mapId: 336, evId: 900, evName: 'Castle Entrance (cutscene)', x: 20, y: 5, hitbox: {L:0,R:2,T:0,B:0} },
        to:   { mapId: 336, x: 20, y: 5 }, kind: 'manual' },
      // Map165 top-left door — visible door at upper-left, not in event data
      { from: { mapId: 165, evId: 900, evName: 'Top-Left Door', x: 7, y: 5, hitbox: {L:1,R:1,T:0,B:0} },
        to:   { mapId: 165, x: 7, y: 5 }, kind: 'manual' },
    ],
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // ALCOVES I alcove 4 — reached from Map160 (PYREFLY V) "Pyrefly Forest".
      4334: { src: 433, name: '[alcove 4]', polygon: [[11,32],[18,32],[18,45],[11,45]] },
    },
  },
  vast_forest: {
    syntheticEdges: [
      // Map327 ev2 (interior train door, choice-based teleport not captured by extractor)
      { from: { mapId: 327, evId: 902, evName: 'Train Door (other dest)', x: 19, y: 10, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 327, x: 19, y: 10 }, kind: 'manual' },
      // Map326 VAST FOREST PIER — the ladder near the top is ev2 'Teleport',
      // which leaves the region for Map197 CONSTRUCTION (last_resort). Being
      // cross-region it lands in `external`, so the pier had no snap target
      // there at all — only the 'Bridge' at the very bottom.
      { from: { mapId: 326, evId: 903, evName: 'Ladder (to Construction)', x: 19, y: 11, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 326, x: 19, y: 11 }, kind: 'manual' },
      // Map90 (NORTH COAST) ↔ Map91 (NORTH LAKE) — m90 ev3 "To North Lake" at (3,0) and m91 ev1 "To North Coast"
      // are NOT auto-extracted (no transferEvent codes). Add manual snaps.
      // m90: dock at top, player walks up to enter lake.
      { from: { mapId: 90, evId: 900, evName: 'To North Lake', x: 3, y: 0, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 91, x: 15, y: 19 }, kind: 'manual' },
      // m91: bottom edge, returns to North Coast.
      { from: { mapId: 91, evId: 900, evName: 'To North Coast', x: 15, y: 19, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 90, x: 8, y: 56 }, kind: 'manual' },
      // m90 south exit "MAP TELEPORT" at (8, 56) — goes back to vast forest. Snap target on south edge.
      { from: { mapId: 90, evId: 901, evName: 'To Vast Forest (south)', x: 8, y: 56, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 90, x: 8, y: 56 }, kind: 'manual' },
      // Map98 OLD SHOE INTERIOR sub-maps — door exits at bottom of each shoe (no real events).
      // Local coords: 981 has cropX=6 cropY=0 → door at global (10,14) = local (4,14)
      //               982 has cropX=28 cropY=4 → door at global (30,14) = local (2,10)
      { from: { mapId: 981, evId: 900, evName: 'Door (south)', x: 4, y: 13, hitbox: {L:0,R:0,T:0,B:1} },
        to:   { mapId: 981, x: 4, y: 13 }, kind: 'manual' },
      { from: { mapId: 982, evId: 900, evName: 'Door (south)', x: 2, y: 9, hitbox: {L:0,R:0,T:0,B:1} },
        to:   { mapId: 982, x: 2, y: 9 }, kind: 'manual' },
      // Map426 FOREST ALCOVES stem doorways are handled by 14_add_exit_anchors.py,
      // which measures them off the cut PNGs. Hand-written coords were wrong for
      // alcoves TL/TR (stem sits at local x=1, not x=3).
    ],
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // Map98 OLD SHOE INTERIOR — 2 disconnected rooms (extended +1 row for south door)
      981: { src: 98, name: '[main shoe]',    polygon: [[6,0],[15,0],[15,14],[6,14]] },
      982: { src: 98, name: '[side shoe]',    polygon: [[28,4],[33,4],[33,14],[28,14]] },
      // Map426 FOREST ALCOVES — 4 alcoves
      4261: { src: 426, name: '[alcove TL]',  polygon: [[5,3],[12,3],[12,16],[5,16]] },
      4262: { src: 426, name: '[alcove TR]',  polygon: [[27,3],[34,3],[34,16],[27,16]] },
      4263: { src: 426, name: '[alcove BR]',  polygon: [[27,25],[34,25],[34,44],[27,44]] },
      4264: { src: 426, name: '[alcove BL]',  polygon: [[5,30],[12,30],[12,43],[5,43]] },
    },
  },
  otherworld: {
    syntheticEdges: [
      // Map126 (SB House) top — door entrance into the planet chamber (visual door TBD)
      { from: { mapId: 126, evId: 900, evName: 'Planet Chamber Entrance', x: 19, y: 15, hitbox: {L:0,R:1,T:0,B:0} },
        to:   { mapId: 126, x: 19, y: 15 }, kind: 'manual' },
      // Map127 (SOLAR SYSTEM) — only existing snap is west-edge teleport (0,10). Add east-end snap
      // at SBF pirates location so route can connect from path end to the SBF house.
      { from: { mapId: 127, evId: 900, evName: 'Solar System East End (SBF)', x: 48, y: 10, hitbox: {L:1,R:0,T:0,B:0} },
        to:   { mapId: 127, x: 48, y: 10 }, kind: 'manual' },
      // (moved to snowglobe_mountain along with Map347)
      // Map347 (FROZEN FOREST IX) [side branch] sub-map (3472) — no teleport events inside.
      // Anchor near the north edge where it meets the main corridor.
      // 3472 cropX=20 cropY=31 → anchor at global (23,32) = local (3,1)
      { from: { mapId: 3472, evId: 900, evName: 'Side branch entry', x: 3, y: 1, hitbox: {L:1,R:0,T:0,B:0} },
        to:   { mapId: 3472, x: 3, y: 1 }, kind: 'manual' },
    ],
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // ALCOVES I keeps one map per alcove but runs it as two rooms. The
      // watermelon is a single event with self-switch A for one approach and
      // B for the other, gated on switch 1499, so taking it on one route
      // leaves it sitting there on the other — the game hands out a reward
      // per route. Switch 1499 also decides which way back exists, and the
      // Sweetheart's Castle door carries a cake sprite, which is how the two
      // versions tell themselves apart on screen. So: one slice per route.
      4333: { src: 433, name: '[junk alcove — via outskirts]', polygon: [[55,11],[60,11],[60,22],[55,22]] },

      // ALCOVES II alcove 4 — reached from Map136 (FROZEN FOREST III) "Face Wall".
      4374: { src: 437, name: '[alcove 4]', polygon: [[5,25],[12,25],[12,38],[5,38]] },
      // Map125 OTHERWORLD INTERIORS — 4 disconnected rooms.
      // Polygons extended by 1 row to include south-edge TELEPORT events:
      // ev1@(14,21)→1251, ev2@(35,19)→1252, ev3@(36,41)→1254, ev4@(13,42)→1253
      1251: { src: 125, name: '[top-L]', polygon: [[9,8],[17,8],[17,22],[9,22]] },
      1252: { src: 125, name: '[top-R]', polygon: [[31,10],[42,10],[42,20],[31,20]] },
      1253: { src: 125, name: '[bot-L]', polygon: [[10,31],[17,31],[17,43],[10,43]] },
      1254: { src: 125, name: '[bot-R]', polygon: [[33,31],[40,31],[40,42],[33,42]] },
      // Map132 IGLOO INTERIOR's four rooms now live under snowglobe_mountain.
      // Map347 FROZEN FOREST IX's two rooms moved to snowglobe_mountain.
    },
  },
  snowglobe_mountain: {
    dimFixes: {
      132: { width: 44, height: 44 },
    },
    syntheticEdges: [
      // Map141 FROZEN FOREST (VIII) has only two doors, both near its corners,
      // leaving the long sides with nothing to line a route up against. Points
      // rather than slides: the ask was for the middle of each side.
      { from: { mapId: 141, evId: 906, evName: 'Left side (middle)', x: 0, y: 44, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 141, x: 0, y: 44 }, kind: 'manual' },
      { from: { mapId: 141, evId: 907, evName: 'Right side (middle)', x: 39, y: 44, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 141, x: 39, y: 44 }, kind: 'manual' },
      // Map347 [side branch] has no teleport events inside it, so the slice had
      // nothing to snap to. 3472 cropX=20 cropY=31 → global (23,32) = local (3,1).
      { from: { mapId: 3472, evId: 900, evName: 'Side branch entry', x: 3, y: 1, hitbox: {L:1,R:0,T:0,B:0} },
        to:   { mapId: 3472, x: 3, y: 1 }, kind: 'manual' },
    ],
    subMaps: {
      // Map347 FROZEN FOREST IX — 2 rooms (main vertical corridor + side branch)
      3471: { src: 347, name: '[main corridor]', polygon: [[6,6],[18,6],[18,70],[6,70]] },
      3472: { src: 347, name: '[side branch]',   polygon: [[20,31],[26,31],[26,47],[20,47]] },
      // Map132 IGLOO INTERIOR — 4 rooms, and the way into Snowglobe Mountain.
      1321: { src: 132, name: '[top-L]', polygon: [[8,4],[15,4],[15,16],[8,16]] },
      1322: { src: 132, name: '[top-R]', polygon: [[28,7],[35,7],[35,16],[28,16]] },
      1323: { src: 132, name: '[bot-L]', polygon: [[8,26],[15,26],[15,36],[8,36]] },
      1324: { src: 132, name: '[bot-R]', polygon: [[28,26],[35,26],[35,36],[28,36]] },
    },
  },
  sweethearts_castle: {
    // Manual route anchor points — virtual events that exist only for stitcher snapping.
    // Use these for visual features (light pillars, etc.) that aren't real game events.
    syntheticEdges: [
      { from: { mapId: 187, evId: 901, evName: 'Light Pillar', x: 15, y: 10, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 187, x: 15, y: 10 }, kind: 'manual' },
      { from: { mapId: 169, evId: 902, evName: 'Garden Center Trapdoor', x: 25, y: 36, hitbox: {L:0,R:0,T:0,B:0} },
        to:   { mapId: 169, x: 25, y: 36 }, kind: 'manual' },
    ],
    dimFixes: {
      170: { width: 23, height: 43 },
      173: { width: 60, height: 35 },
      176: { width: 25, height: 50 },
      178: { width: 25, height: 43 },
      181: { width: 23, height: 46 },
      182: { width: 47, height: 40 },
      183: { width: 47, height: 45 },
      186: { width: 28, height: 35 },
      437: { width: 62, height: 70 },
    },
    vanillaAliases: {},
    // Alcoves cut from larger sweetheart rooms (bboxes in tile coords from connected-component scan).
    // Polygons = rectangles around each visible room cluster on AUBREY render.
    subMaps: {
      // The same two alcoves again, entered from this side: these carry the
      // cake that marks the way back to the castle. 16_render_event_sprites.py
      // draws it on — the shipped render only has the cake-less page.
      4338: { src: 433, name: '[ocean alcove — via ballroom]', polygon: [[54,32],[60,32],[60,44],[54,44]] },
      4339: { src: 433, name: '[junk alcove — via servant\'s quarter]', polygon: [[55,11],[60,11],[60,22],[55,22]] },

      // Map171 SWEETHEART'S CASTLE STAGE — 2 alcoves (left + right thrones)
      1711: { src: 171, name: '[stage left]',  polygon: [[7,1],[22,1],[22,33],[7,33]] },
      1712: { src: 171, name: '[stage right]', polygon: [[48,1],[63,1],[63,33],[48,33]] },
      // Map433 ALCOVES I — 7 alcoves (3x2 grid + 1 bottom)
      4331: { src: 433, name: '[alcove 1]', polygon: [[11,10],[18,10],[18,23],[11,23]] },
      4332: { src: 433, name: '[alcove 2]', polygon: [[33,10],[40,10],[40,22],[33,22]] },
      4335: { src: 433, name: '[alcove 5]', polygon: [[33,32],[40,32],[40,45],[33,45]] },
      4337: { src: 433, name: '[alcove 7]', polygon: [[11,55],[18,55],[18,68],[11,68]] },
      // Map435 SWEETHEART DUNGEON 2 — 3 alcoves
      4351: { src: 435, name: '[dungeon main]', polygon: [[10,4],[45,4],[45,62],[10,62]] },
      4352: { src: 435, name: '[right corridor]', polygon: [[64,11],[71,11],[71,33],[64,33]] },
      4353: { src: 435, name: '[bottom small]',   polygon: [[37,38],[46,38],[46,49],[37,49]] },
      // Map437 ALCOVES II — 9 main alcoves (skip noise alcove 7)
      4372: { src: 437, name: '[alcove 2]', polygon: [[26,3],[34,3],[34,16],[26,16]] },
      4375: { src: 437, name: '[alcove 5]', polygon: [[27,25],[34,25],[34,38],[27,38]] },
      4377: { src: 437, name: '[alcove 8]', polygon: [[5,48],[12,48],[12,61],[5,61]] },
      4378: { src: 437, name: '[alcove 9]', polygon: [[27,48],[34,48],[34,61],[27,61]] },
      // Map438 SWEETHEART DUNGEON 3 — 1 main room
      4381: { src: 438, name: '[main room]', polygon: [[7,6],[30,6],[30,17],[7,17]] },
      // Map453 CLUB SANDWICH room atlas — this room is reached from Map175 'Face Wall'.
      4535: { src: 453, name: '[jam packets room]', polygon: [[30,31],[37,31],[37,41],[30,41]] },
    },
  },
  last_resort: {
    // Map202 LAST RESORT ELEVATOR keeps only its real snap point, the 'Door'
    // event at (15,15) that all twelve exits share. A centre anchor was tried
    // and removed: a route attaching to the middle of the car rather than to
    // its door reads as ambiguous.
    anchorNudges: {
      // Map195 MANAGER/CONCIERGE 'To Floor 1'. The event stands at (11,41),
      // one row past the end of the carpet — row 40 is the last tile the map
      // draws, and the arrival tile coming the other way (Map193's Door, and
      // Map1932's) is (12,40). Standing on the event triggers it from the
      // tile above, so the file position is right for the game and one row
      // low for a snap point.
      '195:6': { y: 40 },
    },
    dimFixes: {},
    vanillaAliases: {},
    subMaps: {
      // Map196 JAWSUM OFFICE AND BREAK — two rooms with 14 tiles of nothing
      // between them. Bounds are the map's own alpha, flood-filled: exactly two
      // connected components, 296 and 309 tiles. The break room and the office
      // to its right are one component, joined by the corridor along their top.
      1961: { src: 196, name: "[jawsum's office]", polygon: [[7,4],[25,4],[25,23],[7,23]] },
      1962: { src: 196, name: '[break room]',      polygon: [[39,5],[66,5],[66,18],[39,18]] },
      // Map453 CLUB SANDWICH room atlas (see deeper_well above). Three of the
      // five rooms belong here: the bar itself, reached from the
      // '★ CLUB SANDWICH' common event, and the room behind Map196
      // 'Pluto Smash'.
      4531: { src: 453, name: '[bar]',         polygon: [[4,1],[15,1],[15,14],[4,14]] },
      4534: { src: 453, name: '[pluto room]',  polygon: [[7,30],[14,30],[14,42],[7,42]] },
      // Cut content: fully built (floor, walls and collision are all authored)
      // but no event and no transfer anywhere in the game points at it — a
      // full scan of every Map*.json plus CommonEvents.json finds zero ways in,
      // and the black gap between rooms is 100% impassable. Kept for the atlas,
      // flagged so it can't be mistaken for a reachable room.
      4533: { src: 453, name: '[nine holes room] [UNUSED]',
              polygon: [[52,3],[61,3],[61,16],[52,16]] },

      // Map192 HALLWAY — five hotel floors on one canvas, each its own island
      // with a pair of elevator doors. Floor numbers are off the signs hanging
      // in each corridor; 4F's sign has fallen over, which suits it.
      1921: { src: 192, name: '[B1 — break room]',  polygon: [[15,8],[29,8],[29,16],[15,16]] },
      1922: { src: 192, name: '[2F — guest rooms]', polygon: [[48,7],[78,7],[78,19],[48,19]] },
      1923: { src: 192, name: '[4F — broken down]', polygon: [[17,34],[47,34],[47,42],[17,42]] },
      1924: { src: 192, name: '[3F — guest rooms]', polygon: [[15,53],[45,53],[45,62],[15,62]] },
      1925: { src: 192, name: '[portrait hall]',    polygon: [[9,80],[51,80],[51,88],[9,88]] },

      // Map193 HOTEL ROOMS — nine rooms in a 3x3 grid. Each room's door event
      // sits a row or two below the room's own tiles, so the polygons run past
      // the floor; without that the doors never propagate onto the slice and
      // the rooms come out with nothing to snap a route to.
      1931: { src: 193, name: '[guest room — life jam guy]', polygon: [[12,13],[19,13],[19,22],[12,22]] },
      1932: { src: 193, name: '[entry hall]',                polygon: [[33,10],[36,10],[36,18],[33,18]] },
      1933: { src: 193, name: '[guest room — lamb & wolf]',  polygon: [[49,13],[56,13],[56,22],[49,22]] },
      1934: { src: 193, name: '[ball pit room]',             polygon: [[12,29],[19,29],[19,38],[12,38]] },
      1935: { src: 193, name: '[bathroom, upper]',           polygon: [[31,29],[38,29],[38,38],[31,38]] },
      1936: { src: 193, name: '[guest room — middle right]',  polygon: [[49,32],[56,32],[56,41],[49,41]] },
      1937: { src: 193, name: '[ghost party room]',          polygon: [[12,47],[19,47],[19,56],[12,56]] },
      1938: { src: 193, name: '[bathroom, lower]',           polygon: [[31,48],[38,48],[38,56],[31,56]] },
      1939: { src: 193, name: '[guest room — doll]',         polygon: [[49,49],[56,49],[56,58],[49,58]] },
    },
  },
  junkyard: {
    dimFixes: {},
    vanillaAliases: {},
    // M428 split into 3 zones via polygon clip (list of [col, row] vertices).
    // The PNG crop step (scripts/cut_submaps.py) masks outside-polygon → transparent
    // and crops to the polygon's bounding box. cropX/cropY = bbox top-left.
    subMaps: {
      4281: { src: 428, name: '[part 1 / L w/ bump]', polygon: [
        [4,0],[37,0],[37,14],[31,14],[31,10],[11,10],[11,30],[4,30],
      ]},
      4282: { src: 428, name: '[part 2 / bottom island]', polygon: [
        [18,15],[27,15],[27,30],[18,30],
      ]},
      4283: { src: 428, name: '[part 3 / right vertical]', polygon: [
        [48,0],[55,0],[55,22],[48,22],
      ]},
    },
  },
};
const patches = PATCHES[region] || { dimFixes: {}, vanillaAliases: {} };

// Snap points come straight off the event's tile, which is where the game
// wants the trigger, not always where the doorway is. `anchorNudges` moves the
// handful that land a tile out, keyed "<mapId>:<evId>". Applied here, before
// the sub-map derivation below rebases anything into slice-local coordinates.
for (const key in (patches.anchorNudges || {})) {
  const [mapId, evId] = key.split(':').map(Number);
  const move = patches.anchorNudges[key];
  const hit = allEdges.filter(e => e.from.mapId === mapId && e.from.evId === evId);
  if (!hit.length) {
    console.warn(`  ⚠ anchorNudges ${key}: no edge leaves that event — stale entry?`);
    continue;
  }
  for (const e of hit) Object.assign(e.from, move);
  console.log(`  · nudged ${key} (${hit[0].from.evName}) -> ` +
              `(${hit[0].from.x}, ${hit[0].from.y})`);
}

// Merge GLOBAL_DIM_FIXES first (region-specific can override)
const allDimFixes = { ...GLOBAL_DIM_FIXES, ...patches.dimFixes };
for (const id in allDimFixes) {
  if (mapMeta[id]) Object.assign(mapMeta[id], allDimFixes[id]);
}
for (const fakeId in patches.vanillaAliases) {
  const realId = patches.vanillaAliases[fakeId];
  if (mapMeta[realId]) {
    mapMeta[fakeId] = { ...mapMeta[realId], id: +fakeId,
                       name: mapMeta[realId].name + ' [VANILLA RENDER]' };
  }
}
// Sub-map crops. Supports either rectangle (x/y/width/height) or polygon
// (list of [col, row] vertices — bbox is computed from the polygon).
for (const fakeId in (patches.subMaps || {})) {
  const sm = patches.subMaps[fakeId];
  if (!mapMeta[sm.src]) continue;
  let cropX, cropY, width, height, polygon = null;
  if (sm.polygon) {
    polygon = sm.polygon;
    const xs = polygon.map(p => p[0]);
    const ys = polygon.map(p => p[1]);
    cropX = Math.min(...xs); cropY = Math.min(...ys);
    width = Math.max(...xs) - cropX;
    height = Math.max(...ys) - cropY;
  } else {
    cropX = sm.x ?? 0; cropY = sm.y ?? 0;
    width = sm.width; height = sm.height ?? mapMeta[sm.src].height;
  }
  mapMeta[fakeId] = { ...mapMeta[sm.src], id: +fakeId,
                     width, height, cropX, cropY,
                     ...(polygon ? { polygon } : {}),
                     name: mapMeta[sm.src].name + ' ' + sm.name };
}

// Propagate events to sub-maps so the stitcher can snap routes on them.
// For each sub-map with a polygon, copy every edge whose source event tile
// center lies inside the polygon; rewrite from.mapId/x/y to the sub-map's
// frame. Destination side is left as the original map id (the game still
// teleports to the real map). Edges where to.mapId is in-region also get
// a translated to.mapId/x/y if the landing tile is inside a sub polygon —
// so routes ending on the sub-map render at the right local position.
function pointInPolygon(px, py, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (((yi > py) !== (yj > py)) &&
        (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
const subBySrc = {};
for (const fakeId in (patches.subMaps || {})) {
  const sm = patches.subMaps[fakeId];
  if (!sm.polygon || !mapMeta[fakeId]) continue;
  (subBySrc[sm.src] = subBySrc[sm.src] || []).push({ id: +fakeId, sm, meta: mapMeta[fakeId] });
}
function locateSub(srcMapId, x, y) {
  const subs = subBySrc[srcMapId]; if (!subs) return null;
  for (const s of subs) {
    if (pointInPolygon(x + 0.5, y + 0.5, s.sm.polygon)) return s;
  }
  return null;
}
const derived = [];
for (const e of internal) {
  const fromSub = locateSub(e.from.mapId, e.from.x, e.from.y);
  const toSub   = locateSub(e.to.mapId,   e.to.x,   e.to.y);
  if (!fromSub && !toSub) continue;
  derived.push({
    ...e,
    from: fromSub ? { ...e.from, mapId: fromSub.id,
                      x: e.from.x - fromSub.meta.cropX,
                      y: e.from.y - fromSub.meta.cropY }
                  : e.from,
    to:   toSub   ? { ...e.to,   mapId: toSub.id,
                      x: e.to.x   - toSub.meta.cropX,
                      y: e.to.y   - toSub.meta.cropY }
                  : e.to,
  });
}
for (const e of derived) internal.push(e);

// Synthetic edges (manual route anchors for stitcher snapping)
for (const se of (patches.syntheticEdges || [])) {
  internal.push(se);
  console.log(`  synthetic anchor: Map${se.from.mapId} (${se.from.x},${se.from.y}) '${se.from.evName}'`);
}
const propCounts = {};
for (const e of derived) propCounts[e.from.mapId] = (propCounts[e.from.mapId] || 0) + 1;
for (const id of Object.keys(propCounts).sort())
  console.log(`  Sub-map ${id}: ${propCounts[id]} events propagated`);

// ── Drop non-renderable maps (RPG Maker folder / organizer nodes) ──────────
// The map tree contains grouping nodes that exist only in the editor's sidebar:
// Map12 "-- FARAWAY TOWN (DAY + SUNSET)", Map93 "-- PINWHEEL FOREST",
// Map361 "-- MINIGAMES" and friends. Left in, they clutter the stitcher
// thumbnail list and index.html's dropdown with entries that can never load.
//
// They can't be detected from the decrypted dump alone: OMORI keeps tile data
// in maps/*.AUBREY (Tiled), so every Map*.json has an empty `data` array —
// even for real rooms. And "0 events" is wrong in both directions (Map355
// HALLUCINATION HOUSE is a real 100x90 map with no events; Map3 ENCOUNTERS is
// a folder with 94). The reliable signal is whether the game ships an .AUBREY.
//
// Synthetic ids invented above (sliced sub-maps, [VANILLA RENDER] aliases)
// have no .AUBREY either, and a newly declared sub-map has no PNG yet — its
// image is cut afterwards by 05_cut_submaps.py. So exempt every id this script
// minted, and keep anything with a PNG already on disk.
const SYNTHETIC_IDS = new Set([
  ...Object.keys(patches.vanillaAliases || {}),
  ...Object.keys(patches.subMaps || {}),
]);
const AUBREY_MAPS_DIR = path.join(
  process.env.HOME,
  'Library/Application Support/Steam/steamapps/common/OMORI',
  'OMORI.app/Contents/Resources/app.nw/maps'
);
if (fs.existsSync(AUBREY_MAPS_DIR)) {
  const aubrey = new Set(fs.readdirSync(AUBREY_MAPS_DIR).map(f => f.toLowerCase()));
  const dropped = [];
  for (const id of Object.keys(mapMeta)) {
    if (SYNTHETIC_IDS.has(id)) continue;
    if (aubrey.has(`map${id}.aubrey`)) continue;
    if (fs.existsSync(path.join(OUT_DIR, 'raw_pngs', mapMeta[id].image || `map${id}.png`))) continue;
    dropped.push(`${id} "${mapMeta[id].name}"`);
    delete mapMeta[id];
  }
  if (dropped.length) {
    console.log(`Dropped ${dropped.length} non-renderable map(s): ${dropped.join(', ')}`);
  }
} else {
  console.warn(`No Steam install at ${AUBREY_MAPS_DIR} — keeping folder nodes.`);
}

// Write outputs
fs.mkdirSync(OUT_DIR, { recursive: true });
const mapsFile = `${PREFIX}_maps.json`;
const edgesFile = `${PREFIX}_edges.json`;
const highlightsFile = `${PREFIX}_highlights.json`;
fs.writeFileSync(path.join(OUT_DIR, mapsFile),  JSON.stringify(mapMeta, null, 2));
fs.writeFileSync(path.join(OUT_DIR, edgesFile), JSON.stringify({ internal, external }, null, 2));
// Propagate watermelons on parent maps into their alcove sub-maps, so the
// stitcher's pulse overlay shows up on placed sub-maps too. Coords get
// rebased to sub-map local using cropX/cropY (set during sub-map creation).
const subDerivedMelons = [];
for (const m of highlights.watermelons.slice()) {
  const sub = locateSub(+m.mapId, m.x, m.y);
  if (!sub) continue;
  subDerivedMelons.push({
    ...m,
    mapId: sub.id,
    x: m.x - sub.meta.cropX,
    y: m.y - sub.meta.cropY,
  });
}
highlights.watermelons.push(...subDerivedMelons);
if (subDerivedMelons.length) console.log(`Propagated ${subDerivedMelons.length} watermelons to sub-maps`);

// Inject any manualWatermelons declared in the region config (events the
// melonCopy scan can't auto-detect, e.g. one-off Tomb Prize / quest items).
const manualMelons = (patches.manualWatermelons) || [];
for (const m of manualMelons) highlights.watermelons.push(m);
fs.writeFileSync(path.join(OUT_DIR, highlightsFile), JSON.stringify(highlights, null, 2));
console.log(`Watermelons found: ${highlights.watermelons.length} (${manualMelons.length} manual)`);
console.log(`\nWrote: data/${mapsFile}, data/${edgesFile}`);
