#!/usr/bin/env node
/**
 * Extract OMORI vanilla skill data for the 4 main party members.
 *
 * Joins Skills.json + States.json + Classes.json + Actors.json into a single
 * clean JSON the website can render.
 *
 * Output: data/skills_vanilla.json
 *   {
 *     "actors": [{id, name, classId, skills: [{level, skillId, ...}]}, ...],
 *     "skills": {<id>: {name, description, damage, effects (resolved), ...}},
 *     "states": {<id>: {name, autoRemoval, ...}}
 *   }
 */

const fs = require('fs');
const path = require('path');

const SRC = '/Users/vicky/Documents/scripts/OMORI/omori_data_decrypted';
const OUT = path.join(__dirname, '..', 'data', 'skills_vanilla.json');

const skills = JSON.parse(fs.readFileSync(path.join(SRC, 'Skills.json'), 'utf8'));
const states = JSON.parse(fs.readFileSync(path.join(SRC, 'States.json'), 'utf8'));
const classes = JSON.parse(fs.readFileSync(path.join(SRC, 'Classes.json'), 'utf8'));
const actors = JSON.parse(fs.readFileSync(path.join(SRC, 'Actors.json'), 'utf8'));

// Damage type mapping
const DAMAGE_TYPE = {
  0: 'none', 1: 'HP damage', 2: 'MP damage',
  3: 'HP recover', 4: 'MP recover',
  5: 'HP drain', 6: 'MP drain',
};
const SCOPE = {
  0: 'none', 1: 'one enemy', 2: 'all enemies',
  3: '1 random enemy', 4: '2 random enemies', 5: '3 random enemies',
  6: '4 random enemies', 7: 'one ally', 8: 'all allies',
  9: 'one dead ally', 10: 'all dead allies', 11: 'self', 12: 'one ally (any)',
  13: 'all allies (any)', 14: 'all everyone',
};

function resolveEffect(e) {
  // RPG MV effect codes: 11 hp recover, 12 mp recover, 13 tp gain, 21 add state,
  // 22 remove state, 31-34 buffs, 41 special, 42 grow, 43 learn skill, 44 common event
  if (e.code === 21) {
    return { kind: 'add_state', stateId: e.dataId, stateName: states[e.dataId]?.name || `state${e.dataId}`, chance: e.value1 };
  }
  if (e.code === 22) {
    return { kind: 'remove_state', stateId: e.dataId, stateName: states[e.dataId]?.name || `state${e.dataId}`, chance: e.value1 };
  }
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

function cleanSkill(s) {
  if (!s) return null;
  const dmg = s.damage || {};
  return {
    id: s.id,
    name: s.name,
    description: (s.description || '').replace(/\r/g, '').trim(),
    mpCost: s.mpCost,
    tpCost: s.tpCost,
    scope: s.scope,
    scopeName: SCOPE[s.scope] || `scope${s.scope}`,
    damage: {
      type: dmg.type,
      typeName: DAMAGE_TYPE[dmg.type] || `type${dmg.type}`,
      formula: dmg.formula,
      variance: dmg.variance,
      critical: dmg.critical,
      elementId: dmg.elementId,
    },
    effects: (s.effects || []).map(resolveEffect),
  };
}

// 4 main HEADSPACE party members + Faraway variants
const MAIN_ACTORS = [
  { actorId: 1, label: 'OMORI (Headspace)' },
  { actorId: 2, label: 'AUBREY (Headspace)' },
  { actorId: 3, label: 'KEL (Headspace)' },
  { actorId: 4, label: 'HERO (Headspace)' },
  { actorId: 8, label: 'PLAYER / SUNNY (Faraway)' },
  { actorId: 9, label: 'AUBREY (Faraway)' },
  { actorId: 10, label: 'KEL (Faraway)' },
  { actorId: 11, label: 'HERO (Faraway)' },
];

const out = {
  actors: [],
  skills: {},
  states: {},
};

for (const { actorId, label } of MAIN_ACTORS) {
  const a = actors[actorId];
  if (!a) continue;
  const cls = classes[a.classId];
  const learnings = (cls?.learnings || []).filter(l => skills[l.skillId]);
  out.actors.push({
    id: actorId,
    name: a.name || label,
    label,
    classId: a.classId,
    className: cls?.name || '?',
    learnings: learnings.map(l => ({ level: l.level, skillId: l.skillId, skillName: skills[l.skillId].name })),
  });
  for (const l of learnings) {
    out.skills[l.skillId] = cleanSkill(skills[l.skillId]);
  }
}

// Resolve all referenced state IDs
const referencedStates = new Set();
for (const sk of Object.values(out.skills)) {
  for (const e of sk.effects) {
    if (e.stateId) referencedStates.add(e.stateId);
  }
}
for (const id of referencedStates) {
  const st = states[id];
  if (!st) continue;
  out.states[id] = {
    id,
    name: st.name,
    note: (st.note || '').slice(0, 200),
    autoRemoval: st.autoRemovalTiming === 1 ? 'after action' : st.autoRemovalTiming === 2 ? 'turn end' : 'manual',
    minTurns: st.minTurns,
    maxTurns: st.maxTurns,
    removeAtBattleEnd: st.removeAtBattleEnd,
  };
}

fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
console.log(`Wrote ${OUT}`);
console.log(`  Actors: ${out.actors.length}`);
console.log(`  Skills: ${Object.keys(out.skills).length}`);
console.log(`  States referenced: ${Object.keys(out.states).length}`);

// Print a quick summary
console.log('\n=== Summary ===');
for (const a of out.actors) {
  console.log(`\n${a.label}:`);
  for (const l of a.learnings) {
    const sk = out.skills[l.skillId];
    const eff = sk.effects.map(e => {
      if (e.kind === 'add_state') return `→${e.stateName}`;
      if (e.kind === 'recover_hp') return `+HP ${e.percent}%${e.flat?'+'+e.flat:''}`;
      if (e.kind === 'common_event') return `[CE ${e.ceId}]`;
      return e.kind;
    }).join(' ');
    console.log(`  Lv${String(l.level).padStart(2)} ${sk.name.padEnd(20)} cost=${sk.mpCost}MP/${sk.tpCost}TP  ${sk.damage.formula || '-'}  ${eff}`);
  }
}
