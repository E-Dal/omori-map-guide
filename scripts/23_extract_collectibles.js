#!/usr/bin/env node
/**
 * Pull the things worth marking on a map out of the event data.
 *
 * Watermelons already have their own pass in 01_extract_adjacency.js. This
 * covers the rest:
 *
 *   quest    key items. RPG Maker files these under itypeId 2, and that turns
 *            out to be exactly the category a player thinks of as a quest item
 *            — JOKE BOOK, TEDDY BEAR and WOODEN TRACK are all in it, while
 *            POETRY BOOK, which you can buy, is not. So the game's own
 *            classification is the definition; no keyword list to maintain.
 *   sparkle  the glints you press A on to receive something. Named
 *            "sparkle - item" and variants throughout.
 *   button   things you step on or press to open a way through.
 *
 * An event counts when one of its pages runs Change Items (code 126) as a
 * gain. Pages are searched, not just page 0, because a pickup usually lives on
 * a later page behind the switch that armed it.
 *
 * Maps 1, 2 and 4 are skipped along with every other map that has no PNG:
 * they are the editor's template libraries, where a single event holds dozens
 * of item grants that exist nowhere in the world.
 *
 * Coordinates are propagated into sub-maps the same way watermelons are, so a
 * pickup inside a sliced alcove lands on the slice as well as the parent.
 *
 *   node scripts/23_extract_collectibles.js
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DECRYPTED = '/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted';
const OUT = path.join(ROOT, 'data', 'collectibles.json');

// Only a legend for whoever reads collectibles.json directly — index.html
// keeps its own bilingual copy in MARKER_LAYERS. Keep the two in step
// anyway; a file that names a layer one thing and shows another is a trap.
const LAYERS = [
  { key: 'hangman',   label: 'HANGMAN keys', icon: '⌨️' },
  { key: 'npc',       label: 'NPC (quest)',  icon: '🧑' },
  { key: 'quest',     label: 'Quest items',  icon: '🎒' },
  { key: 'charm',     label: 'Charms',       icon: '🧿' },
  { key: 'weapon',    label: 'Weapons',      icon: '🔪' },
  { key: 'collect',   label: 'Collectibles', icon: '🗑️' },
  { key: 'sparkle',   label: 'Sparkles',     icon: '✨' },
  { key: 'picnic',    label: 'Picnic (save)', icon: '🧺' },
  { key: 'music',     label: 'Sheet music',  icon: '🎼' },
  { key: 'telescope', label: 'Telescopes',   icon: '🔭' },
  { key: 'clubsandwich', label: 'Club Sandwich', icon: '🥪' },
  { key: 'giver',     label: 'NPC (item)',   icon: '🥤' },
  { key: 'clams',     label: 'CLAMS',        icon: '🐚' },
  { key: 'cooler',    label: 'Coolers',      icon: '🧊' },
  { key: 'mirror',    label: 'Mirrors',      icon: '🪞' },
  { key: 'mechanism', label: 'Mechanisms',   icon: '⚙️' },
];

// Two things worth finding that no rule here could ever have caught: their
// events carry no commands at all — not an item, not a switch, not a line of
// script. Every page is a graphic behind a condition, and whatever counts them
// lives elsewhere. They are named, though, and the names are exact.
//
//   Cooler   19 of them, one beside most of Mari's picnics. Opened once.
//   MIRROR   the Headspace mirrors; in Faraway the same event is named
//            `Mirror` and wears DEV_TEST, an invisible trigger standing on a
//            mirror that is painted into the map art — so mirrors are exempt
//            from the has-a-graphic test below, exactly as HANGMAN keys are.
//
// `MIRROR_EFFECT` and `Mirror View` are the machinery that drives them and are
// deliberately not matched; nor are the `dw_mirror_*` in MINIGAMES, which is a
// gallery rather than a place.
const IS_COOLER = /^cooler$/i;
const IS_MIRROR = /^mirror$/i;

// Mari's picnic blanket is where Headspace is saved: her event warps you to
// WHITE SPACE (Map87) and back. One per map, 21 maps — the single most useful
// thing in here, and it was landing in 'mechanism' along with every cutscene
// trigger merely because it flips other events' switches on the way out.
// Named Mari or Picnic *and* running the routine every picnic runs. The name
// alone is not enough: NORTH COAST, NEIGHBOUR'S ROOM and PLAYER'S HOME all hold
// an event called `Mari` that is a cutscene — followers, camera work, a page
// wearing DW_KEL — and four maps hold `Picnic` events that are the blanket
// itself. Of the 41 events named either way, the 22 real save points are
// exactly the ones calling common event 68, one per map, one in every region.
const IS_PICNIC = /^(mari|picnic)$/i;
const PICNIC_COMMON_EVENT = 68;   // "Mari check leader"

// SHEET MUSIC is a key item, so it was already being found — filed under quest
// items with 44 others. It gets its own layer because on the HIKIKOMORI route
// it is the collection that matters, and three pickups in one corner of
// DEEPERWELL FALLS are not something to go hunting for behind a shared toggle.
const IS_MUSIC = /^sheet music$/i;

// The telescopes you can look through, which is an achievement. Named exactly
// `Telescope`; `Telescope Activate` is the trigger that swaps you to the view,
// and the `-- VIEW: …` maps are that view rather than a place to stand, so
// neither is a telescope to go and find. Several of them are painted into the
// map art with only an invisible event on top, so like the mirrors they are
// exempt from the has-a-graphic test.
const IS_TELESCOPE = /^telescope$/i;

// CLUB SANDWICH is one bar reached from four places, and finding all four is
// the point of it — the game keeps a switch per entrance, named "Last Resort
// CS", "Orange Oasis CS", "Otherworld CS" and "Pyrefly CS". Every one of those
// doors runs the same common event, which is what identifies them: the door
// itself hands over nothing and its event is called simply "Club Sandwich", so
// neither the name nor a gain would find it.
const CLUB_SANDWICH_COMMON_EVENT = 412;

// Someone who gives you something for talking to them. NPCs handing over a KEY
// item are already covered — they end up in 'npc' below — but the great
// majority hand over food and drink, which is itypeId 1, and nothing was
// keeping those: Reuben behind the CLUB SANDWICH bar pours four GRAPE SODAs
// over a playthrough and the guide had never heard of him.
//
// The test is the sheet, the same one that separates people from props
// everywhere else here, so a chest that yields a PIE is not mistaken for a
// person who offers you one.
const GIVES_A_TREAT = (gainedIds, sheet, isShopEvent) =>
  gainedIds.size > 0 && !isShopEvent && isPerson(sheet);

// Clams for interacting with something. RPG Maker's Change Gold is code 125,
// [operation (0 = increase), operandType (0 = a number, 1 = a variable), value],
// and only pages you set off with the action button count — trigger 0. That
// keeps out the cutscene payouts (the Faraway delivery jobs, the allowance in
// NEIGHBOUR'S ROOM) which are not somewhere you can go and get clams.
//
// This covers two things a player asks the same question about. The 30 events
// named plain CLAM are the shells lying around Last Resort and the Deep Well,
// one clam each; the rest are people — Hoagie behind the CLUB SANDWICH bar is
// worth 5000, and exactly one of the 23 Mari picnics, the one in PATH TO
// TRENCH, hands over 500.
//
// Unlike every other layer here this one does not claim the event: it is an
// extra point on top of whatever the event already was, because Mari being a
// save point and Mari being 500 clams are both true and a player toggling
// "CLAMS" wants to see her.
const clamsFrom = pages => {
  const amounts = new Set();
  let variable = false;
  for (const p of pages || []) {
    if (p.trigger !== 0) continue;                       // 0 = action button
    for (const c of p.list || []) {
      if (c.code !== 125 || c.parameters[0] !== 0) continue;
      if (c.parameters[1] === 0) amounts.add(c.parameters[2]);
      else variable = true;
    }
  }
  return { amounts: [...amounts].sort((a, b) => a - b), variable };
};

// 'mechanism' means "flips another event's self-switch", which is also what
// every cutscene trigger in the game does — 206 points, two thirds of them
// people. Bass, KEL TAG and aubreyPots are machinery; HERO, Recycultist2 and
// EV077 are a scene starting. No property of the event tells the two apart:
// the sheet name puts `vent` and `Trap Door` on the person side (DW_TrapDoor)
// and `KEL TAG` on the object side, so it cannot be the test either.
//
// So the layer is a list, grouped by what the thing does to the world. Add to
// it rather than loosening it — a rule wide enough to catch the next lever
// catches forty cutscenes with it.
const MECHANISMS = [
  // ways through that open
  /^trap ?door$/i, /^vent$/i, /^elevator( full)?$/i, /^mine cart$/i,
  /^mushroom rise$/i, /^snake gate$/i, /^rope$/i, /^closet door$/i,
  /^player home \(night\)$/i, /^fear of heights$/i,
  // switches you press
  /^candle\d*$/i, /^aubreypots$/i, /^hide-(rug|curtain)$/i, /^switch [a-z]/i,
  /^statue$/i, /^sbfstatue$/i, /^finalspike$/i, /^console$/i, /^puzzle\d+$/i,
  /^bombpuzzle\d+$/i, /^spidercat\d+$/i, /^humphreytarget\d+$/i, /^kel tag/i,
  // teleports and resets inside a puzzle
  /^back to /i, /^correct teleport$/i, /^to main room$/i, /^teleport$/i,
  // things you break
  /^(aubrey)?smash$/i, /^bridge smash/i,
  // props that do something when used
  /^fountain$/i, /^bass$/i, /^laptop$/i, /^camera$/i, /^bed \(/i,
  /^cards -- base$/i, /^tree$/i, /^tube$/i, /^chimera$/i, /^case$/i, /^cheese$/i,
];

// A repeated pickup is a collection quest, not a story beat. TRASH turns up in
// 65 places and SEASHELL in 11 because the JUNKYARD wants a pile of them;
// TEDDY BEAR and WOODEN TRACK turn up once or three times because they are the
// point of a particular errand. Splitting on how many places an item is found
// separates the two without a hand-written list to keep in sync.
const COLLECTION_MIN = 5;

const items = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Items.json'), 'utf8'));
const weapons = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Weapons.json'), 'utf8'));
const armors = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Armors.json'), 'utf8'));
// Watermelons have their own layer already, out of the region highlight files,
// and their marker names the prize in its own tooltip. Twelve of the 21 charms
// and two of the 14 weapons were the *same event* as a melon — `melonGLAD`,
// `melonROSE`, `WATERMELON - ITEM` — so the map carried two pins on one tile,
// the melon and the thing inside it. Keyed by event, not by tile, so a charm
// that merely happens to lie beside a melon is left alone.
const melonEvents = new Set();
for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
  if (!f.endsWith('_highlights.json')) continue;
  try {
    const h = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', f), 'utf8'));
    for (const w of (h.watermelons || [])) melonEvents.add(`${w.mapId}:${w.evId}`);
  } catch { /* a region without highlights is not an error */ }
}

// Belt machines have their own layer already, out of conveyors.json.
let beltMachines = new Set();
try {
  const conv = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'conveyors.json'), 'utf8'));
  for (const [mapId, d] of Object.entries(conv))
    for (const g of d.groups) for (const m of g.machines) beltMachines.add(`${mapId}:${m.evId}`);
} catch { /* not extracted yet */ }
const KEY_ITEM = new Set(items.map((it, i) => (it && it.itypeId === 2 ? i : -1)).filter(i => i >= 0));
const itemName = id => (items[id] && items[id].name) || `#${id}`;

// Maps the atlas actually draws, plus their sub-map slices.
const mapMeta = {};
for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
  if (f.endsWith('_maps.json')) Object.assign(mapMeta, JSON.parse(fs.readFileSync(path.join(ROOT, 'data', f), 'utf8')));
}
const drawn = id => fs.existsSync(path.join(ROOT, 'data', 'raw_pngs', `map${id}.png`));

// Sub-maps carry cropX/cropY and a name extending their parent's, so a point on
// the parent can be rebased onto whichever slice contains it.
const subsOf = {};
for (const [id, m] of Object.entries(mapMeta)) {
  if (m.cropX === undefined) continue;
  for (const [pid, pm] of Object.entries(mapMeta)) {
    if (pid !== id && pm.cropX === undefined && m.name && pm.name && m.name.startsWith(pm.name + ' ')) {
      (subsOf[pid] ||= []).push({ id, m });
      break;
    }
  }
}
const locateSub = (mapId, x, y) => (subsOf[mapId] || []).find(({ m }) =>
  x >= m.cropX && x < m.cropX + m.width && y >= m.cropY && y < m.cropY + m.height);

const IS_SPARKLE = /sparkl/i;
// The keys HANGMAN wants. Each hiding place is an event named for its letter —
// BLACKLETTER_V sits in MOLLY ROOM LEFT 2, BLACKLETTER_X in the EXCAVATION
// SITE. ENTRANCE TO ABYSS also holds all 26 as "Blackletter A" … "Blackletter
// Z", but those are the board you spell the answer on, not places to search;
// the underscore is what tells the two apart.
const IS_HANGMAN = /^BLACKLETTER_([A-Z])\b/i;
// A mechanism is a thing that operates other things: its script reaches into
// another event's self-switch. That is the same shape as the conveyor machines
// — one object, a block of objects that answer to it — and it separates a
// lever from an NPC who merely sets a conversation flag.
//
// It does not catch scenery you interact with that changes nothing itself: the
// Vast Forest pinwheel has no state-changing command at all, its pages just
// switch on a global someone else sets. Those need naming by hand.
const SETS_OTHER_SELFSWITCH = /gameSelfSwitches\.setValue\(\s*\[/;
const SETS_OWN_SELFSWITCH = /this\._eventId/;

// A person who hands you something is not a thing you found, and mixing the
// two made the quest-item layer mostly townsfolk. They are told apart by the
// sheet the event wears, which OMORI names consistently:
//
//   objects   a leading '!' (RPG Maker's own marker for object characters, used
//             for doors and props), or a name saying what it is — OBJECTS,
//             IMPORTANTOBJ, PuzzleObjects, objects_pf_minecart, [SF]Teddy, FA_TV
//   people    everything else — FA_tucker, DW_NPC_12, $fa_old_lady, DW_SPRM_1
//
// directionFix was the obvious candidate and is not reliable: an NPC posed to
// face one way has it set too, which put SMELLYHOBO, KimsMom and JOYSDAD on the
// object side.
const OBJECT_SHEET = /^!|obj|prop|puzzle|track|minecart|^\[SF\]|_TV$|NEIGHBOURSROOM/i;
const isPerson = sheet => !!sheet && !OBJECT_SHEET.test(sheet);

const points = [];
for (const f of fs.readdirSync(DECRYPTED)) {
  const mm = /^Map(\d+)\.json$/.exec(f);
  if (!mm) continue;
  const mapId = String(+mm[1]);
  if (!mapMeta[mapId] || !drawn(mapId)) continue;
  let data;
  try { data = JSON.parse(fs.readFileSync(path.join(DECRYPTED, f), 'utf8')); } catch { continue; }

  // Where an event *ends up*, not where the editor parked it. Sixteen of these
  // points are put in place at run time by a Set Event Location somewhere else
  // on the map (code 203), and nine of them are HANGMAN keys: BLACKLETTER_V
  // lives at (15, 6) in the file and is moved into the cage at (16, 6) by an
  // event called `Placement`; BLACKLETTER_E sits at (9, 0), off in the corner,
  // and is moved to (19, 14). Reading the file position alone put those markers
  // on bare floor, or on the map's edge.
  //
  // Only unambiguous moves are followed. Six events are sent to more than one
  // place — `Smash`, `chimera`, DAISY — because they genuinely travel; there is
  // no single answer for those, so they keep the position the file gives them.
  const movedTo = {};
  for (const ev of (data.events || []).filter(Boolean)) {
    for (const pg of (ev.pages || [])) {
      for (const c of (pg.list || [])) {
        if (c.code !== 203 || c.parameters[1] !== 0) continue;  // 0 = a literal x/y
        const target = c.parameters[0] || ev.id;                // 0 means "this event"
        (movedTo[target] ||= new Set()).add(`${c.parameters[2]},${c.parameters[3]}`);
      }
    }
  }
  const placedAt = id => {
    const d = movedTo[id];
    if (!d || d.size !== 1) return null;
    const [x, y] = [...d][0].split(',').map(Number);
    return { x, y };
  };

  for (const ev of (data.events || []).filter(Boolean)) {
    const name = ev.name || '';
    const gained = new Set(), gotWeapons = [], gotCharms = [];
    let isShop = false, operates = false;
    for (const p of ev.pages || []) {
      // A page that hands over a weapon or charm and then equips it onto more
      // than one party member is the game kitting the party out, not loot you
      // found. Exactly one page in the game does that: HERO (2) in NEIGHBOUR'S
      // ROOM, whose unconditional first page gains RUBBER BALL, SPATULA and
      // HECTOR, equips them onto three different actors, and then runs
      // `$gamePlayer.locate(15, 19)` and a Recover All. It is the new-game
      // bootstrap, and it had been sitting on the map as a Quest NPC offering
      // you HECTOR.
      //
      // "Gains and equips" alone is not enough — 22 pages do that, and most are
      // real: TENTACLE really does hand you the RED KNIFE, and the STEAK KNIFE
      // in PLAYER'S HOME is a thing you pick up. Every one of those equips a
      // single actor. Counting actors is what separates them.
      //
      // Items (126) are untouched: 319 only equips weapons and armour.
      const outfits = new Set((p.list || [])
        .filter(c => c.code === 319).map(c => c.parameters[0])).size > 1;
      for (const c of p.list || []) {
        // [itemId, operation(0 = gain), operandType, operand]
        if (c.code === 126 && c.parameters[1] === 0) gained.add(c.parameters[0]);
        if (c.code === 127 && c.parameters[1] === 0 && weapons[c.parameters[0]] && !outfits)
          gotWeapons.push(weapons[c.parameters[0]].name);
        if (c.code === 128 && c.parameters[1] === 0 && armors[c.parameters[0]] && !outfits)
          gotCharms.push(armors[c.parameters[0]].name);
        // Shop stock is not treasure lying around.
        if (c.code === 302 || c.code === 605) isShop = true;
      }
      const src = (p.list || []).map(c =>
        (c.code === 355 || c.code === 655) ? c.parameters[0] : '').join('\n');
      if (SETS_OTHER_SELFSWITCH.test(src) && !SETS_OWN_SELFSWITCH.test(src)) operates = true;
    }
    const letter = IS_HANGMAN.exec(name);
    const commonEvents = new Set((ev.pages || []).flatMap(pg =>
      (pg.list || []).filter(c => c.code === 117).map(c => c.parameters[0])));
    // Something you can find has to be something you can see. Plenty of events
    // hand over a key item from behind an invisible trigger — CLAUS2D in the
    // Faraway house has five pages and no graphic on any of them — and marking
    // those puts a pickup on bare floor. An event with art on some page is a
    // drawer, a minecart, a teddy bear: a place worth pointing at. HANGMAN keys
    // are exempt: half of them only appear once the room has been solved, so
    // they carry no graphic on any page and are still exactly where you look.
    const visible = (ev.pages || []).some(p =>
      (p.image || {}).characterName && p.image.characterName !== 'DEV_TEST');
    const isView = /^--\s*VIEW:/i.test((mapMeta[mapId] || {}).name || '');
    if (!visible && !letter && !IS_MIRROR.test(name) &&
        !(IS_TELESCOPE.test(name) && !isView)) continue;
    const keyItems = [...gained].filter(id => KEY_ITEM.has(id)).map(itemName);
    // The frame this event shows, so the atlas can draw the thing itself rather
    // than a stand-in. Deduped across the game by 28_extract_point_sprites.py —
    // 500-odd points share about 194 distinct frames. Resolved before the layer
    // chain because 'giver' asks whether the sheet is a person.
    const page = (ev.pages || [])
      .find(p => (p.image || {}).characterName && p.image.characterName !== 'DEV_TEST');
    const img = page && page.image;
    let layer = null;
    if (letter) layer = 'hangman';
    else if (IS_PICNIC.test(name) && commonEvents.has(PICNIC_COMMON_EVENT)) layer = 'picnic';
    else if (keyItems.some(n => IS_MUSIC.test(n))) layer = 'music';
    else if (IS_COOLER.test(name)) layer = 'cooler';
    else if (IS_MIRROR.test(name)) layer = 'mirror';
    else if (IS_TELESCOPE.test(name) && !isView) layer = 'telescope';
    else if (commonEvents.has(CLUB_SANDWICH_COMMON_EVENT)) layer = 'clubsandwich';
    // A sparkle that hands over nothing is scenery: the ambient glitter in
    // STUMP ENTRANCE is named "SPARKLES (11)" and the one in NEIGHBOUR'S ROOM
    // "Break Time Sparkle", and matching the name alone put both on the map as
    // things to go and collect. The 34 real ones all hand over something —
    // seven of them a weapon or a charm rather than an item, so all three
    // kinds of gain have to count.
    else if (IS_SPARKLE.test(name))
      layer = (gained.size || gotWeapons.length || gotCharms.length) ? 'sparkle' : null;
    else if (keyItems.length) layer = 'quest';   // may become 'collect' below
    else if (gotCharms.length) layer = 'charm';
    else if (gotWeapons.length) layer = 'weapon';
    else if (operates && !beltMachines.has(`${mapId}:${ev.id}`) &&
             MECHANISMS.some(re => re.test(name))) layer = 'mechanism';
    else if (GIVES_A_TREAT(gained, img && img.characterName, isShop)) layer = 'giver';

    // Emitted before the layer chain's verdict is acted on, so a CLAM shell
    // (which claims no layer of its own) and Mari (who is already a picnic)
    // both get one.
    const clams = isShop ? { amounts: [], variable: false } : clamsFrom(ev.pages);
    if (clams.amounts.length || clams.variable) {
      const at = placedAt(ev.id) || { x: ev.x, y: ev.y };
      points.push({
        layer: 'clams', mapId, x: at.x, y: at.y, evId: ev.id, evName: name,
        sprite: img ? `${img.characterName}|${img.characterIndex || 0}|` +
                      `${img.direction || 2}|${img.pattern === undefined ? 1 : img.pattern}`
                    : undefined,
        prio: page ? (page.priorityType === undefined ? 1 : page.priorityType) : undefined,
        // The casino machine pays 100, 500, 1000 or 2000 depending on the roll,
        // so all of them are listed rather than a single misleading number.
        items: [(clams.amounts.length ? clams.amounts.join(' / ') : '?') + ' CLAMS'],
      });
    }

    if (!layer || isShop) continue;
    if (melonEvents.has(`${mapId}:${ev.id}`)) continue;   // the melon marks it already

    // Anything handed over by a person goes to its own layer whatever it was.
    // Mari is a person and her picnic is still not an NPC errand, so 'picnic'
    // stays out of this — it is a save point wearing her sprite.
    if (['quest', 'collect', 'charm', 'weapon'].includes(layer) &&
        isPerson(img && img.characterName)) layer = 'npc';
    const spot = placedAt(ev.id) || { x: ev.x, y: ev.y };
    points.push({
      layer, mapId, x: spot.x, y: spot.y, evId: ev.id, evName: name,
      letter: letter ? letter[1].toUpperCase() : undefined,
      // The pattern belongs in the key. It is the animation column the page
      // actually shows, and a quarter of these points are not on column 1: the
      // microwave is on 2, the first aid kit on 0. Leaving it out let 28 draw
      // whatever sat on column 1 — a different object on the same sheet — and
      // measure that frame's outline to place the marker.
      sprite: img ? `${img.characterName}|${img.characterIndex || 0}|` +
                    `${img.direction || 2}|${img.pattern === undefined ? 1 : img.pattern}` : undefined,
      // "Below characters" (0) means the renderer paints it with the ground and
      // it gets no six-pixel lift; anything on the character layer does. 34 of
      // these points are on the ground side, so the layer has to travel with
      // the point — the sheet name alone does not say which it is.
      prio: page ? (page.priorityType === undefined ? 1 : page.priorityType) : undefined,
      items: gotCharms.length ? gotCharms
           : gotWeapons.length ? gotWeapons
           : keyItems.length ? keyItems : [...gained].map(itemName),
    });
  }
}

// Second pass: an item found in many places is a collection quest. This needs
// the whole game counted first, so it cannot be decided while scanning.
const found = {};
for (const p of points) {
  if (p.layer !== 'quest') continue;
  for (const it of p.items) found[it] = (found[it] || 0) + 1;
}
for (const p of points) {
  if (p.layer === 'quest' && p.items.some(it => found[it] >= COLLECTION_MIN)) p.layer = 'collect';
}

// Slices inherit their parent's pickups, rebased to slice-local coordinates.
for (const p of points.slice()) {
  const sub = locateSub(p.mapId, p.x, p.y);
  if (sub) points.push({ ...p, mapId: sub.id, x: p.x - sub.m.cropX, y: p.y - sub.m.cropY });
}

fs.writeFileSync(OUT, JSON.stringify({ layers: LAYERS, points }, null, 1));
const per = {};
for (const p of points) per[p.layer] = (per[p.layer] || 0) + 1;
console.log(LAYERS.map(l => `${l.icon} ${l.label}: ${per[l.key] || 0}`).join('\n'));
const letters = new Set(points.filter(p => p.letter).map(p => p.letter));
console.log(`HANGMAN letters covered: ${[...letters].sort().join('')} ` +
            `(missing ${[...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].filter(c => !letters.has(c)).join('') || 'none'})`);
console.log(`\n${points.length} point(s) across ${new Set(points.map(p => p.mapId)).size} map(s) → data/collectibles.json`);
