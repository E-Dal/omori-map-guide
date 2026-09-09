#!/usr/bin/env node
/**
 * Build the quest layer: where each side quest starts, where its steps are.
 *
 * For a long time this looked impossible — nothing in the map data says "this
 * event belongs to that quest". Two things say it after all:
 *
 *   data/Quests.PLUTO   the game's own quest log. 35 named quests (plus 16
 *                       empty Quest36..Quest50 placeholders), each with an
 *                       English name and its stages.
 *   sidequest_*.HERO    every line of dialogue lives in a file named after the
 *                       quest it belongs to, and events cite it by key:
 *                       `ShowMessage sidequest_dreamworld_ghostgathering.message_10`.
 *
 * So the events of a quest are the events that quote its dialogue file, and
 * the message number they quote is the order the game says them in. That turns
 * out to be exactly the order you do the quest in:
 *
 *   msg  0   map198 TOPHATGHOST      GHOST PARTY      <- the one who asks
 *   msg 10   map106 BEARDGHOST       ORANGE OASIS
 *   msg 14   map144 GLASSESGHOST     JUNKYARD (III)
 *   msg 17   map193 MUSTACHEGHOST    HOTEL ROOMS
 *   …
 *
 * message_0 is the giver in every quest checked by hand: PotatoGirl for RAIN
 * TOWN, CRIS'S DAD for the remote, LEAFY for RABBIT KILLER, MARINA for her own.
 * So the atlas puts one pin per quest, on the giver, and the rest of the
 * locations are listed in its popup and drawn only when asked for — 35 pins
 * instead of 300, and the six scattered ghosts still one click away.
 *
 * Faraway repeats its maps by time of day, so the same NPC turns up on
 * PLAYER'S HOUSE (DAY) and (SUNSET). Those are kept: in per-map view you want
 * the pin on whichever copy you are looking at.
 *
 *     node scripts/39_extract_quests.js
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..');
const DECRYPTED = '/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted';
const GAME = path.join(process.env.HOME,
  'Library/Application Support/Steam/steamapps/common/OMORI',
  'OMORI.app/Contents/Resources/app.nw');
const OUT = path.join(ROOT, 'data', 'quests.json');

function aubreyKey() {
  if (process.env.OMORI_AUBREY_KEY) return process.env.OMORI_AUBREY_KEY;
  const local = path.join(__dirname, 'omori_keys.json');
  if (fs.existsSync(local)) {
    try { return JSON.parse(fs.readFileSync(local, 'utf8')).aubrey; } catch (e) { /* fall through */ }
  }
  console.error('No OMORI AES key — see scripts/_keys.py.');
  process.exit(1);
}
function decrypt(file) {
  const enc = fs.readFileSync(file);
  const d = crypto.createDecipheriv('aes-256-ctr', aubreyKey(), enc.slice(0, 16));
  return Buffer.concat([d.update(enc.slice(16)), d.final()]).toString('utf8');
}

// ── the quest log ──────────────────────────────────────────────────────────
// Quests.PLUTO is YAML, but only three fields deep and only two of them
// matter, so it is read with a line scanner rather than a parser dependency.
function questLog() {
  const txt = decrypt(path.join(GAME, 'data', 'Quests.PLUTO'));
  const out = {};
  let id = null;
  for (const line of txt.split(/\r?\n/)) {
    let m = /^ {2}(\w+):\s*$/.exec(line);
    if (m) { id = m[1]; out[id] = { id, name: null }; continue; }
    m = /^ {6}en:\s*(.+?)\s*$/.exec(line);
    if (m && id && !out[id].name) out[id].name = m[1];
  }
  // Quest36..Quest50 and Quest95 are unfilled rows in the editor.
  for (const k of Object.keys(out)) if (!out[k].name || /^Quest\d+$/.test(k)) delete out[k];
  return out;
}

// A dialogue file and a quest-log row are named by different people. Most
// pair up once punctuation and the world prefix are dropped; these are the
// ones that do not, matched by reading the dialogue.
const NAME_OVERRIDES = {
  dreamworld_ghostgathering: 'GhostParty',
  dreamworld_rabbitkiller: 'Leafie',
  dreamworld_stoprain: 'Raintown',
  dreamworld_feedhumphrey: 'Humphrey',
  dreamworld_itch: 'Itchy',
  dreamworld_oragne: 'Orange',          // the game's typo, not mine
  dreamworld_flowerpuzzle: 'FlowerPuzzle',
  dreamworld_stolen: 'Mixtape',
  dreamworld_tentacle: 'StrangeRequest',
  dreamworld_bed: 'BED',
  dreamworld_poolnoodle: 'PoolNoodle',
  dreamworld_pinkbeard: 'Pinkbeard',
  dreamworld_squizzards: 'Squizzards',
  dreamworld_marina: 'Marina',
  dreamworld_medusa: 'Medusa',
  dreamworld_molly: 'Molly',
  dreamworld_hector: 'Hector',
  dreamworld_hectorjr: 'Hector',
  farawaytown_mypie: 'Sweaty',
};

// 48 of the 67 dialogue files have no row in the quest log — most of Faraway's
// errands are not tracked quests, they are just things people ask you to do.
// Their file names are the developers' own words run together, so these are a
// re-spacing, not a translation: `wherestheremote` -> WHERE'S THE REMOTE.
const DISPLAY = {
  anniversarychoco: "ANNIVERSARY CHOCOLATE", anniversarypizza: "ANNIVERSARY PIZZA",
  artist: "THE ARTIST", birthdaygift1: "BIRTHDAY GIFT (I)",
  birthdaygift2: "BIRTHDAY GIFT (II)", bringangel: "BRING THE ANGEL",
  brushteeth: "BRUSH YOUR TEETH", claus: "CLAUS", coffeemachine: "THE COFFEE MACHINE",
  cooking: "COOKING", crowfriends: "CROW FRIENDS", deliversprout: "SPROUT DELIVERY",
  demonboy: "DEMON BOY", fixarcademachine: "FIX THE ARCADE MACHINE",
  fixpipe: "FIX THE PIPE", fliphim: "FLIP HIM OVER", forgotmeat: "THE FORGOTTEN MEAT",
  fruitwaradrian: "FRUIT WAR — ADRIAN", fruitwarbrayden: "FRUIT WAR — BRAYDEN",
  ginohighscore: "GINO'S HIGH SCORE", ginojukebox: "GINO'S JUKEBOX",
  hobbeezhighscore: "HOBBEEZ HIGH SCORE", jackson: "JACKSON",
  lostlucas: "LOST LUCAS", lostrarebear: "THE LOST RARE BEAR", lostson: "THE LOST SON", medication: "THE MEDICATION",
  michaelslunch: "MICHAEL'S LUNCH", michaelthemusician: "MICHAEL THE MUSICIAN",
  mincy: "MINCY", missingshears: "THE MISSING SHEARS", oldhobo: "THE OLD HOBO",
  peanutjelly: "PEANUT AND JELLY", perfectwind: "THE PERFECT WIND",
  pickingpaint: "PICKING PAINT", pickupfurniture: "PICK UP THE FURNITURE",
  ringinthesink: "THE RING IN THE SINK", seasons: "THE SEASONS",
  seashells: "SEASHELLS", shutin: "THE SHUT-IN", smellyhobo: "THE SMELLY HOBO",
  sneakingoutbrent: "SNEAKING OUT — BRENT", sneakingoutjoy: "SNEAKING OUT — JOY",
  stargazing: "STARGAZING", toiletseat: "THE TOILET SEAT",
  trashpickup: "TRASH PICKUP", tutorbrent: "TUTORING BRENT", tutorjoy: "TUTORING JOY",
  wherestheremote: "WHERE'S THE REMOTE",
};
// Chinese quest names. The game has none — Quests.PLUTO carries only `en` and
// `jp`, and nothing in languages/sc names a quest — so unlike every other piece
// of Chinese in this atlas these are written here rather than lifted from the
// game. Character names follow the game's own (奥布里, 贝瑟尔, 凯, 甜心, 汉弗莱).
const ZH = {
  dreamworld_bed: 'B.E.D.',
  dreamworld_coffeemachine: '咖啡机',
  dreamworld_crowfriends: '乌鸦朋友',
  dreamworld_deliversprout: '树苗鼹鼠快递',
  dreamworld_demonboy: '恶魔男孩',
  dreamworld_feedhumphrey: '喂饱汉弗莱',
  dreamworld_fliphim: '把他翻过来',
  dreamworld_flowerpuzzle: '雏菊的难题',
  dreamworld_ghostgathering: '鬼魂聚会',
  dreamworld_hector: '赫克托',
  dreamworld_hectorjr: '小赫克托',
  dreamworld_itch: '好痒',
  dreamworld_lostrarebear: '走失的稀有小熊',
  dreamworld_lostson: '走失的儿子',
  dreamworld_marina: '玛丽娜的手术',
  dreamworld_medusa: '美杜莎的实验',
  dreamworld_molly: '莫莉的分析',
  dreamworld_oragne: '橙子乔的信念',
  dreamworld_peanutjelly: '花生和果酱',
  dreamworld_perfectwind: '完美的风',
  dreamworld_pinkbeard: '太空海盗之子',
  dreamworld_rabbitkiller: '兔子杀手',
  dreamworld_seasons: '四季',
  dreamworld_squizzards: '松鼠蜥',
  dreamworld_stargazing: '观星',
  dreamworld_stolen: '太空海盗船长',
  dreamworld_stoprain: '雨镇',
  dreamworld_tentacle: '奇怪的请求',
  farawaytown_anniversarychoco: '纪念日巧克力',
  farawaytown_anniversarypizza: '纪念日披萨',
  farawaytown_artist: '画家',
  farawaytown_birthdaygift1: '生日礼物（一）',
  farawaytown_birthdaygift2: '生日礼物（二）',
  farawaytown_bringangel: '把天使带来',
  farawaytown_brushteeth: '刷牙',
  farawaytown_claus: '克劳斯',
  farawaytown_cooking: '下厨',
  farawaytown_fixarcademachine: '修好街机',
  farawaytown_fixpipe: '修好水管',
  farawaytown_forgotmeat: '忘了买肉',
  farawaytown_fruitwaradrian: '水果之战 — 艾德里安',
  farawaytown_fruitwarbrayden: '水果之战 — 布雷登',
  farawaytown_ginohighscore: '吉诺的最高分',
  farawaytown_ginojukebox: '吉诺的点唱机',
  farawaytown_hobbeezhighscore: '蜂玩堂的最高分',
  farawaytown_jackson: '杰克逊',
  farawaytown_lostlucas: '走失的卢卡斯',
  farawaytown_medication: '取药',
  farawaytown_michaelslunch: '迈克尔的午餐',
  farawaytown_michaelthemusician: '音乐家迈克尔',
  farawaytown_mincy: '敏西',
  farawaytown_missingshears: '不见的园艺剪',
  farawaytown_mypie: '汗流浃背的点心',
  farawaytown_oldhobo: '老流浪汉',
  farawaytown_pickingpaint: '挑油漆',
  farawaytown_pickupfurniture: '搬家具',
  farawaytown_ringinthesink: '掉进水槽的戒指',
  farawaytown_seashells: '贝壳',
  farawaytown_shutin: '闭门不出的人',
  farawaytown_smellyhobo: '臭烘烘的流浪汉',
  farawaytown_sneakingoutbrent: '溜出门 — 布伦特',
  farawaytown_sneakingoutjoy: '溜出门 — 乔伊',
  farawaytown_toiletseat: '马桶圈',
  farawaytown_trashpickup: '捡垃圾',
  farawaytown_tutorbrent: '给布伦特补课',
  farawaytown_tutorjoy: '给乔伊补课',
  farawaytown_wherestheremote: '遥控器在哪儿',
};

const prettify = (file) => {
  const bare = file.replace(/^(dreamworld|farawaytown)_/, '');
  return DISPLAY[bare] || bare.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/_/g, ' ').toUpperCase();
};

function main() {
  const log = questLog();
  const byNorm = {};
  for (const q of Object.values(log)) byNorm[q.id.toLowerCase()] = q;

  const mapMeta = {};
  for (const f of fs.readdirSync(path.join(ROOT, 'data'))) {
    if (f.endsWith('_maps.json')) {
      Object.assign(mapMeta, JSON.parse(fs.readFileSync(path.join(ROOT, 'data', f), 'utf8')));
    }
  }
  const drawn = id => fs.existsSync(path.join(ROOT, 'data', 'raw_pngs', `map${id}.png`));

  // Sliced rooms carry cropX/cropY and a name extending their parent's, the
  // same shape 23 uses. HOTEL ROOMS is the case that made this necessary: the
  // parent map is not placed in the world at all, only its nine rooms are, so
  // GHOST PARTY's MUSTACHEGHOST — who is in the slice literally called
  // "[ghost party room]" — had nowhere to be drawn.
  const subsOf = {};
  for (const [id, m] of Object.entries(mapMeta)) {
    if (m.cropX === undefined) continue;
    for (const [pid, pm] of Object.entries(mapMeta)) {
      if (pid !== id && pm.cropX === undefined && m.name && pm.name &&
          m.name.startsWith(pm.name + ' ')) { (subsOf[pid] ||= []).push({ id, m }); break; }
    }
  }
  const locateSubs = (mapId, x, y) => (subsOf[mapId] || []).filter(({ m }) =>
    x >= m.cropX && x < m.cropX + m.width && y >= m.cropY && y < m.cropY + m.height);
  const withSlices = list => list.flatMap(e => [e, ...locateSubs(e.mapId, e.x, e.y)
    .map(sub => ({ ...e, mapId: sub.id, x: e.x - sub.m.cropX, y: e.y - sub.m.cropY }))]);

  const items = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Items.json'), 'utf8'));
  const weapons = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Weapons.json'), 'utf8'));
  const armors = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'Armors.json'), 'utf8'));

  const quests = {};   // file -> { events: [], rewards: Set }
  for (const f of fs.readdirSync(DECRYPTED)) {
    const mm = /^Map(\d+)\.json$/.exec(f);
    if (!mm) continue;
    const mapId = String(+mm[1]);
    if (!mapMeta[mapId] || !drawn(mapId)) continue;
    const raw = fs.readFileSync(path.join(DECRYPTED, f), 'utf8');
    if (!raw.includes('sidequest_')) continue;
    let data;
    try { data = JSON.parse(raw); } catch { continue; }

    for (const ev of (data.events || [])) {
      if (!ev) continue;
      const blob = JSON.stringify(ev.pages || []);
      // What gates this event's pages. Two steps of one quest with identical
      // gates are alternatives, not a sequence — see `ordered` below.
      const gate = (ev.pages || []).map(p => {
        const c = p.conditions || {};
        return [c.switch1Valid && 's' + c.switch1Id, c.switch2Valid && 's' + c.switch2Id,
                c.variableValid && 'v' + c.variableId, c.selfSwitchValid && 'S']
          .filter(Boolean).join('+') || '-';
      }).join('|');
      const cites = {};
      for (const m of blob.matchAll(/sidequest_([a-z0-9_]+)\.message_(\d+)/g)) {
        cites[m[1]] = Math.min(cites[m[1]] ?? Infinity, +m[2]);
      }
      if (!Object.keys(cites).length) continue;

      // What this event hands over, if anything. Read once per event and
      // attributed to every quest it speaks for — an event that belongs to two
      // quests is rare enough not to be worth splitting.
      const gains = [];
      for (const p of ev.pages || []) {
        for (const c of p.list || []) {
          if (c.code === 126 && c.parameters[1] === 0 && items[c.parameters[0]]) gains.push(items[c.parameters[0]].name);
          if (c.code === 127 && c.parameters[1] === 0 && weapons[c.parameters[0]]) gains.push(weapons[c.parameters[0]].name);
          if (c.code === 128 && c.parameters[1] === 0 && armors[c.parameters[0]]) gains.push(armors[c.parameters[0]].name);
        }
      }
      // The frame the event shows, so the pin can be its own sprite.
      const page = (ev.pages || []).find(p =>
        (p.image || {}).characterName && p.image.characterName !== 'DEV_TEST');
      const img = page && page.image;

      for (const [file, msg] of Object.entries(cites)) {
        (quests[file] ||= { events: [], rewards: new Set() });
        quests[file].events.push({
          mapId, evId: ev.id, evName: ev.name || '', x: ev.x, y: ev.y, msg, gate,
          sprite: img ? `${img.characterName}|${img.characterIndex || 0}|` +
                        `${img.direction || 2}|${img.pattern === undefined ? 1 : img.pattern}`
                      : undefined,
          prio: page ? (page.priorityType === undefined ? 1 : page.priorityType) : undefined,
        });
        for (const g of gains) quests[file].rewards.add(g);
      }
    }
  }

  const out = [];
  const unmatched = [];
  for (const [file, q] of Object.entries(quests).sort()) {
    q.events.sort((a, b) => a.msg - b.msg || +a.mapId - +b.mapId);
    const id = NAME_OVERRIDES[file] ||
      Object.keys(log).find(k => k.toLowerCase() === file.replace(/^(dreamworld|farawaytown)_/, ''));
    const row = log[id];
    if (!row) unmatched.push(file);
    // Everything at the lowest message number is a giver — Faraway repeats the
    // same NPC across its day/sunset/night copies of a map, and each copy wants
    // its own pin.
    const lowest = q.events[0].msg;
    const givers = q.events.filter(e => e.msg === lowest);
    // GHOST PARTY's six ghosts appear twice: once where you find them, and
    // again back at the party as BEARDGHOST2, GLASSESGHOST2 and so on, once
    // they have gathered. The second set is the result, not a place to go, and
    // drawing it put six pins on top of the ghost who sent you. An event whose
    // name is another event's name with a digit stuck on the end is a later
    // state of the same character, so only the first is kept. Faraway's
    // day/sunset copies share a name exactly rather than by suffix, so they are
    // untouched — you want the pin on whichever map you are looking at.
    const base = new Set(q.events.map(e => e.evName));
    const steps = q.events.filter(e => e.msg !== lowest)
      .filter(e => !/\d$/.test(e.evName) || !base.has(e.evName.replace(/\d+$/, '')));
    // Is there an order to do these in? The game says so by how it gates them.
    // GHOST PARTY's six ghosts all sit behind switch 193, each flipping only its
    // own self-switch and bumping a shared counter — find them in any order.
    // RAIN TOWN's sixteen do not share one gate; the quest moves through stages
    // and the steps come with it. Eight of the 34 multi-step quests are sets,
    // and they are exactly the "collect N of these" ones: the ghosts, the four
    // SEASHELLS, the three SEASONS, GINO'S JUKEBOX.
    //
    // A heuristic on page conditions, not a flag in the data — but it puts the
    // right eight in the right bucket, and it is what decides whether the step
    // pins are numbered.
    const ordered = new Set(steps.map(e => e.gate)).size > 1;
    for (const e of [...givers, ...steps]) delete e.gate;
    out.push({
      file,
      name: { en: row ? row.name : prettify(file), zh: ZH[file] || null },
      named: !!row,
      ordered,
      givers: withSlices(givers),
      steps: withSlices(steps),
      rewards: [...q.rewards],
    });
  }

  fs.writeFileSync(OUT, JSON.stringify({ quests: out }, null, 1));
  const located = out.filter(q => q.givers.length).length;
  const multi = out.filter(q => q.steps.length > 1);
  console.log(`${multi.filter(q => q.ordered).length} of ${multi.length} multi-step quest(s) ` +
              `are a sequence; the rest are a set you can do in any order`);
  console.log(`${Object.keys(log).length} quest(s) in the game's log`);
  console.log(`${out.length} side quest(s) found on drawn maps, ${located} with a giver`);
  console.log(`${out.filter(q => q.named).length} matched to a quest-log name; ` +
              `${unmatched.length} named from their dialogue file`);
  const rough = out.filter(q => !q.named &&
    !DISPLAY[q.file.replace(/^(dreamworld|farawaytown)_/, '')]);
  if (rough.length) console.log('  no display name yet: ' + rough.map(q => q.file).join(', '));
  const noZh = out.filter(q => !q.name.zh);
  if (noZh.length) console.log('  no Chinese name yet: ' + noZh.map(q => q.file).join(', '));
  console.log(`\n→ data/quests.json`);
}

main();
