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
const FARAWAY_ROOT = 12;

const mapInfos = JSON.parse(fs.readFileSync(path.join(DECRYPTED, 'MapInfos.json'), 'utf8'));

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
const farawayIds = descendants(FARAWAY_ROOT);
const farawaySet = new Set(farawayIds);
console.log(`Faraway maps: ${farawayIds.length} (root id ${FARAWAY_ROOT})`);

const mapMeta = {};
const allEdges = [];

for (const mapId of farawayIds) {
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
    for (let pi = 0; pi < (ev.pages || []).length; pi++) {
      const transfers = collectTransfers(ev.pages[pi].list);
      for (const t of transfers) {
        allEdges.push({
          from: { mapId, evId: ev.id, evName: ev.name, x: ev.x, y: ev.y, page: pi },
          to: { mapId: t.dstMap, x: t.dstX, y: t.dstY },
          kind: t.kind,
        });
      }
    }
  }
}

const internal = allEdges.filter(e => farawaySet.has(e.to.mapId));
const external = allEdges.filter(e => !farawaySet.has(e.to.mapId));

console.log(`\nEdges:  total=${allEdges.length}  internal=${internal.length}  external=${external.length}`);

// Group by source for inspection
const bySource = {};
for (const e of internal) (bySource[e.from.mapId] = bySource[e.from.mapId] || []).push(e);

console.log(`\nInternal edges per map:`);
for (const id of farawayIds.slice(0, 20)) {
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

// Write outputs
fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'faraway_maps.json'), JSON.stringify(mapMeta, null, 2));
fs.writeFileSync(path.join(OUT_DIR, 'faraway_edges.json'), JSON.stringify({ internal, external }, null, 2));
console.log(`\nWrote: data/faraway_maps.json, data/faraway_edges.json`);
