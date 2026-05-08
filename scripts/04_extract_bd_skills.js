#!/usr/bin/env node
/**
 * Extract Broken Dreams skill data.
 *
 * Loads vanilla Skills/States/Classes/Actors JSON, applies BD's .jsond
 * patches, then identifies BD's playable actors and dumps their skill kits.
 *
 * Output: data/skills_brokendreams.json (same shape as skills_vanilla.json
 * but with BD-merged data and BD-specific actors).
 */

const fs = require('fs');
const path = require('path');

const VANILLA = '/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted';
const BD = '/Users/vicky/Library/Application Support/Steam/steamapps/common/OMORI/OMORI.app/Contents/Resources/app.nw/mods/brokendreams/data';
const OUT = path.join(__dirname, '..', 'data', 'skills_brokendreams.json');

// Minimal RFC 6902 JSON Patch applier (add / replace / remove only).
function applyPatch(doc, ops) {
  for (const op of ops) {
    const segs = op.path.split('/').slice(1).map(s => s.replace(/~1/g, '/').replace(/~0/g, '~'));
    let target = doc;
    for (let i = 0; i < segs.length - 1; i++) {
      const k = /^\d+$/.test(segs[i]) ? +segs[i] : segs[i];
      if (target[k] == null) target[k] = /^\d+$/.test(segs[i + 1]) ? [] : {};
      target = target[k];
    }
    const last = segs[segs.length - 1];
    const k = /^\d+$/.test(last) ? +last : last;
    if (op.op === 'replace' || op.op === 'add') target[k] = op.value;
    else if (op.op === 'remove') {
      if (Array.isArray(target)) target.splice(k, 1);
      else delete target[k];
    }
  }
  return doc;
}

function loadMerged(name) {
  const vanillaFile = name === 'Actors' ? 'Actors.json' : `${name}.json`;
  const v = JSON.parse(fs.readFileSync(path.join(VANILLA, vanillaFile), 'utf8'));
  const patchPath = path.join(BD, `${name}.jsond`);
  if (fs.existsSync(patchPath)) {
    const ops = JSON.parse(fs.readFileSync(patchPath, 'utf8'));
    applyPatch(v, ops);
  }
  return v;
}

const skills = loadMerged('Skills');
const states = loadMerged('States');
const classes = loadMerged('Classes');
const actors = loadMerged('Actors');

const DAMAGE_TYPE = { 0:'none', 1:'HP damage', 2:'MP damage', 3:'HP recover', 4:'MP recover', 5:'HP drain', 6:'MP drain' };
const SCOPE = { 0:'none', 1:'one enemy', 2:'all enemies', 3:'1 random enemy', 4:'2 random enemies', 5:'3 random enemies',
                6:'4 random enemies', 7:'one ally', 8:'all allies', 9:'one dead ally', 10:'all dead allies', 11:'self',
                12:'one ally (any)', 13:'all allies (any)', 14:'all everyone' };

function resolveEffect(e) {
  if (e.code === 21) return { kind: 'add_state', stateId: e.dataId, stateName: states[e.dataId]?.name || `state${e.dataId}`, chance: e.value1 };
  if (e.code === 22) return { kind: 'remove_state', stateId: e.dataId, stateName: states[e.dataId]?.name || `state${e.dataId}`, chance: e.value1 };
  if (e.code === 11) return { kind: 'recover_hp', percent: e.value1, flat: e.value2 };
  if (e.code === 12) return { kind: 'recover_mp', percent: e.value1, flat: e.value2 };
  if (e.code === 13) return { kind: 'gain_tp', amount: e.value1 };
  if (e.code === 31) return { kind: 'buff_param', paramId: e.dataId, turns: e.value1 };
  if (e.code === 32) return { kind: 'debuff_param', paramId: e.dataId, turns: e.value1 };
  if (e.code === 33) return { kind: 'remove_buff', paramId: e.dataId };
  if (e.code === 34) return { kind: 'remove_debuff', paramId: e.dataId };
  if (e.code === 41) return { kind: 'special_escape' };
  if (e.code === 44) return { kind: 'common_event', ceId: e.dataId };
  return { kind: `code${e.code}`, raw: e };
}

function parseEnergyCost(note) {
  // BD stores energy cost as <EnergyCost: N> in skill notes
  const m = (note || '').match(/<EnergyCost:\s*(\d+)\s*>/i);
  return m ? parseInt(m[1]) : 0;
}

function cleanSkill(s) {
  if (!s || !s.name) return null;
  const dmg = s.damage || {};
  return {
    id: s.id,
    name: s.name,
    description: (s.description || '').replace(/\r/g, '').trim(),
    mpCost: s.mpCost,
    tpCost: s.tpCost,
    energyCost: parseEnergyCost(s.note),
    scope: s.scope,
    scopeName: SCOPE[s.scope] || `scope${s.scope}`,
    damage: {
      type: dmg.type, typeName: DAMAGE_TYPE[dmg.type] || `type${dmg.type}`,
      formula: dmg.formula, variance: dmg.variance, critical: dmg.critical, elementId: dmg.elementId,
    },
    effects: (s.effects || []).map(resolveEffect),
  };
}

// Identify BD playable actors. Heuristic: actor with non-empty name AND non-vanilla characterName
// (vanilla actors keep their portraits, BD adds new ones with custom portraits).
console.log('=== All actors with names (post-merge) ===');
const candidateActors = [];
for (let i = 1; i < actors.length; i++) {
  const a = actors[i];
  if (!a || !a.name) continue;
  const cls = classes[a.classId];
  const className = cls?.name || '';
  const learnings = (cls?.learnings || []).filter(l => skills[l.skillId] && skills[l.skillId].name);
  if (learnings.length > 0 || /sunny|stranger|dreamer|aubrey|kel|hero|omori|mari|basil|player/i.test(a.name)) {
    candidateActors.push({
      id: i, name: a.name, classId: a.classId, className,
      learningCount: learnings.length,
      faceName: a.faceName, characterName: a.characterName,
    });
  }
}
console.log(`Found ${candidateActors.length} candidate actors:`);
for (const a of candidateActors) {
  console.log(`  Actor ${a.id} "${a.name}"  class=${a.classId} "${a.className}"  skills=${a.learningCount}  face=${a.faceName}`);
}

// Pull the actors that have skills
const out = { actors: [], skills: {}, states: {} };

const PARTY = candidateActors.filter(a => a.learningCount > 0);
console.log(`\n=== ${PARTY.length} party-eligible actors (with skills) ===`);

for (const ca of PARTY) {
  const a = actors[ca.id];
  const cls = classes[a.classId];
  const learnings = (cls.learnings || []).filter(l => skills[l.skillId] && skills[l.skillId].name);
  out.actors.push({
    id: ca.id, name: a.name, label: `${a.name} (Actor ${ca.id})`,
    classId: a.classId, className: cls.name,
    learnings: learnings.map(l => ({ level: l.level, skillId: l.skillId, skillName: skills[l.skillId].name })),
  });
  for (const l of learnings) {
    if (!out.skills[l.skillId]) out.skills[l.skillId] = cleanSkill(skills[l.skillId]);
  }
}

// Resolve referenced states
const refStates = new Set();
for (const sk of Object.values(out.skills)) {
  if (!sk) continue;
  for (const e of sk.effects) if (e.stateId) refStates.add(e.stateId);
}
for (const id of refStates) {
  const st = states[id];
  if (!st) continue;
  out.states[id] = {
    id, name: st.name,
    note: (st.note || '').slice(0, 200),
    autoRemoval: st.autoRemovalTiming === 1 ? 'after action' : st.autoRemovalTiming === 2 ? 'turn end' : 'manual',
    minTurns: st.minTurns, maxTurns: st.maxTurns,
    removeAtBattleEnd: st.removeAtBattleEnd,
  };
}

fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
console.log(`\nWrote ${OUT}`);
console.log(`  Actors: ${out.actors.length}`);
console.log(`  Skills: ${Object.keys(out.skills).length}`);
console.log(`  States: ${Object.keys(out.states).length}`);

// Quick summary print
console.log('\n=== BD Party Skills ===');
for (const a of out.actors) {
  console.log(`\n${a.label} [class ${a.classId}: ${a.className}]:`);
  for (const l of a.learnings) {
    const sk = out.skills[l.skillId];
    if (!sk) continue;
    const eff = sk.effects.map(e => {
      if (e.kind === 'add_state') return `→${e.stateName}`;
      if (e.kind === 'remove_state') return `-${e.stateName}`;
      if (e.kind === 'recover_hp') return `+HP ${e.percent}%${e.flat?'+'+e.flat:''}`;
      if (e.kind === 'recover_mp') return `+MP ${e.percent}%${e.flat?'+'+e.flat:''}`;
      if (e.kind === 'common_event') return `[CE ${e.ceId}]`;
      return e.kind;
    }).join(' ');
    console.log(`  Lv${String(l.level).padStart(2)} ${sk.name.padEnd(22)} ${(sk.mpCost+'MP/'+sk.tpCost+'TP').padEnd(10)} ${(sk.damage.formula||'-').slice(0,55).padEnd(57)}  ${eff}`);
  }
}
