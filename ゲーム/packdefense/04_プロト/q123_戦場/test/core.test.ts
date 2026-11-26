// 計算の芯の確かめ（node --test test/core.test.ts）。CSV は 03_仕様 のものをそのまま読む。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseCsv, buildParams } from '../src/core/params.ts';
import { Game } from '../src/core/game.ts';
import { csvKnobs as defaultKnobs, defaultKnobs as ownerKnobs, PRESSURE, applyOverrides } from '../src/core/proto.ts';
import type { FieldPack, Monster } from '../src/core/game.ts';
import { exportText } from '../src/core/log.ts';

const csv = readFileSync(new URL('../../../03_仕様/パラメータ表.csv', import.meta.url), 'utf8');
const { p, missing } = buildParams(parseCsv(csv));

/** いちばん塔に近い魔物へ指を向ける、素朴な指 */
function bot(g: Game, steps: number, on = true): void {
  for (let i = 0; i < steps && (g.scene === 'fight'); i++) {
    if (on) {
      let best = null as null | { x: number; y: number }, bd = 1e9;
      for (const m of g.monsters) { if (!g.visible(m)) continue; const d = Math.hypot(m.x - g.towerX, m.y - g.towerY); if (d < bd) { bd = d; best = m; } }
      const pk = g.packs.find(q => q.tele <= 0);
      const t = pk && (!best || bd > 120) ? pk : best;
      if (t) { if (!g.fingerOn) g.pointerDown(t.x, t.y + g.k.ringOffset); else g.pointerMove(t.x, t.y + g.k.ringOffset); }
      else if (g.fingerOn) g.pointerUp();
    }
    g.step();
  }
}

test('CSV の名前が全部見つかる', () => {
  assert.deepEqual(missing, []);
  assert.equal(p.ringOffsetDefault, 56);
  assert.deepEqual(p.ringOffsetOptions, [0, 40, 56, 72]);
  assert.equal(p.pack.novice.rarityWeights.length, 3);
});

test('輪は指の上 offset、下の端で止まる', () => {
  const k = defaultKnobs(p); const g = new Game(p, k, 844, 't');
  g.newRun(); g.pointerDown(200, 400);
  assert.equal(g.ringY, 344);
  g.pointerMove(200, 844); assert.equal(g.ringY, 788);
  assert.equal(g.reachBottom, 822);
  k.ringOffset = 72; g.pointerMove(200, 400); assert.equal(g.ringY, 328);
});

test('Q1：指で第1ウェーブを遊べて、記録が出る。同じシードで同じ', () => {
  const run = () => { const k = defaultKnobs(p); k.sameSeed = true; const g = new Game(p, k, 844, 'same'); g.newRun(); bot(g, 60 * 90); return g; };
  const a = run(), b = run();
  assert.equal(a.scene, 'cleared', a.scene + ' ' + a.towerHp);
  const s = a.logs[0];
  assert.ok(s.hitsMonster > 20, 'hits ' + s.hitsMonster);
  assert.ok(s.time >= 8 && s.time <= 45, 'time ' + s.time);
  assert.equal(s.dmg.auto, 0);
  assert.deepEqual(a.logs[0], b.logs[0]);
  console.log('  W1', s.time.toFixed(1), 's hits', s.hitsMonster, 'tower', s.towerHpEnd, JSON.stringify(s.towerDmg));
});

test('指なしだと第1ウェーブで塔が削られる。自動化を入れると自動の傷が出る', () => {
  const k = defaultKnobs(p); const g = new Game(p, k, 844, 'x'); g.newRun(); bot(g, 60 * 60, false);
  const hpNo = g.towerHp;
  const k2 = defaultKnobs(p); k2.auto = 1; const g2 = new Game(p, k2, 844, 'x'); g2.newRun(); bot(g2, 60 * 60, false);
  assert.ok(g2.stat.dmg.auto > 0 || g2.logs[0]?.dmg.auto > 0);
  console.log('  指なし 塔', Math.round(hpNo), ' 自動=中 塔', Math.round(g2.towerHp));
});

test('Q2：S1 は開けるとすぐ効き、S2 は置き場に入る', () => {
  for (const mode of ['S1a', 'S2'] as const) {
    const k = defaultKnobs(p); k.mode = 'q2'; k.spellMode = mode; const g = new Game(p, k, 844, 'q2');
    g.newRun();
    assert.equal(g.wave, 2);
    assert.ok(g.drops.some(d => d.def.cards.some(c => c.kind === 'spell')), '呪文が混ざる');
    bot(g, 60 * 80);
    const s = g.logs[0] ?? g.stat;
    assert.ok(s.packsOpened >= 1, 'opened ' + s.packsOpened);
    if (mode === 'S1a') assert.ok(s.spellCasts >= 1); else assert.ok(g.slots.length + s.spellCasts >= 1);
    console.log(' ', mode, 'opened', s.packsOpened, 'delays', s.openDelays.map(x => x.toFixed(1)).join(','), 'slots', g.slots.length, 'casts', s.spellCasts);
  }
});

test('Q3：ランが終わり、名声で強化でき、次のランに出られる', () => {
  const k = defaultKnobs(p); k.mode = 'q3'; k.auto = 1; const g = new Game(p, k, 844, 'q3');
  g.newRun();
  let guard = 0;
  while (g.scene !== 'result' && guard++ < 60 * 60 * 30) {
    if (g.scene === 'shop') { while (g.buy('novice')); g.nextWave(); }
    else if (g.scene === 'fight') bot(g, 30); else g.step();
  }
  assert.equal(g.scene, 'result');
  console.log('  Q3 bot: reached', g.resultInfo.reached, 'time', (g.resultInfo.time / 60).toFixed(1), 'min fame', Math.floor(g.resultInfo.fame));
  g.toUpgrade();
  const before = g.meta.fame; const ok = g.buyUpgrade('tapDmg');
  assert.ok(!ok || g.meta.fame < before);
  g.newRun(); assert.equal(g.scene, 'fight'); assert.equal(g.wave, 1);
  const txt = exportText(['test'], g.logs, g.runLogs, 'メモ');
  assert.match(txt, /傷の割合/); assert.match(txt, /Q3 のラン/);
});

// ---- 2回目に足したつまみ ----
function setup(o: Record<string, unknown>): Game {
  const k = { ...defaultKnobs(p), mode: 'q2' as const, ...o }; const g = new Game(p, k, 844, 'r2'); g.newRun();
  g.drops = []; g.packs = []; g.monsters = []; g.schedule = [{ time: 999, type: 'slime', dir: 'n', done: false, lat: 0 } as never];
  return g;
}
const putPack = (g: Game, x: number, y: number): FieldPack => { const pk = { def: { type: 'novice', cards: [{ kind: 'hero', id: 'sword', rarity: 0 }], rarity: 0, boughtWave: 1 }, x, y, tele: 0, hits: 0, need: 99, landT: 0, shake: 0 } as FieldPack; g.packs.push(pk); return pk; };
const putMon = (g: Game, x: number, y: number): Monster => { const m = { id: 900 + g.monsters.length, type: 'slime', dir: 'n', x, y, hp: 1e9, maxHp: 1e9, size: 15, speed: 0, atk: 0, atkInterval: 1, atkCd: 0, slowUntil: 0, slowMul: 1, flash: 0, attacking: false, dead: false } as Monster; g.monsters.push(m); return m; };

test('輪とパックの決め A／B／C', () => {
  for (const rule of ['A', 'B', 'C'] as const) {
    // 魔物を狙った輪のそばにパックがある（両方が輪の中）
    const g = setup({ packRule: rule }); const pk = putPack(g, 200, 300); putMon(g, 210, 300);
    g.pointerDown(205, 356); for (let i = 0; i < 30; i++) g.step(); g.pointerUp();
    const near = pk.hits;
    // 魔物がいないところでパックを押さえ始める
    const g2 = setup({ packRule: rule }); const pk2 = putPack(g2, 200, 300);
    g2.pointerDown(200, 356); for (let i = 0; i < 30; i++) g2.step(); g2.pointerUp();
    // 何もない所で押さえ始めて、パックへ指を動かす
    const g3 = setup({ packRule: rule }); const pk3 = putPack(g3, 200, 300);
    g3.pointerDown(60, 600); g3.step(); g3.pointerMove(200, 356); for (let i = 0; i < 30; i++) g3.step(); g3.pointerUp();
    console.log(`  ${rule}: 魔物のそば ${near}回 / パックを押さえ始め ${pk2.hits}回 / なぞって入る ${pk3.hits}回`);
    if (rule === 'A') { assert.ok(near > 0); assert.ok(pk2.hits > 0); assert.ok(pk3.hits > 0); }
    if (rule === 'B') { assert.equal(near, 0); assert.ok(pk2.hits > 0); assert.ok(pk3.hits > 0); }
    if (rule === 'C') { assert.ok(near > 0); assert.ok(pk2.hits > 0); assert.equal(pk3.hits, 0); }
  }
});

test('S1b は呪文の輪にいちばん多く魔物が入る所で起きる', () => {
  const g = setup({ spellMode: 'S1b' });
  putMon(g, 100, 300); for (let i = 0; i < 4; i++) putMon(g, 300 + i * 5, 600);
  assert.deepEqual(g.crowdPoint(60), { x: 300, y: 600 });
  const g2 = setup({ spellMode: 'S1b' }); assert.equal(g2.crowdPoint(60), null);
});

test('降る時刻を湧きの山に合わせる', () => {
  const k = { ...defaultKnobs(p), mode: 'q2' as const, dropSync: true }; const g = new Game(p, k, 844, 'sync'); g.newRun();
  const peaks = new Set(g.schedule.map(e => e.time));
  assert.ok(g.drops.length === 2 && g.drops.every(d => peaks.has(d.time) && d.time > 0), JSON.stringify(g.drops.map(d => d.time)));
});

test('上書きは CSV を変えず、記録の行に出る', () => {
  const k = { ...defaultKnobs(p), ...PRESSURE[1].v, hitsMul: 2, startCoin: 15, priceMul: 0.7, swarmFrom: 2 };
  const q = applyOverrides(p, k);
  assert.equal(q.budgetBase, 28); assert.equal(q.monster.slime.hp, 90); assert.equal(q.monster.swarm.fromWave, 2); assert.equal(q.coinStart, 15);
  assert.equal(p.budgetBase, 16); assert.equal(p.monster.slime.hp, 60);
  const g = new Game(p, { ...k, mode: 'q3' }, 844, 'ov'); g.newRun();
  assert.equal(g.coins, 15);
  const t = g.knobText();
  for (const w of ['wave.budget.base=28', 'spawn.packet.base=3', 'monster.slime.hp=90', 'spawn.pullForward=切', 'coin.start=15', 'pack.price×0.7', 'pack.hitsToOpen×2', 'monster.swarm.fromWave=2']) assert.ok(t.includes(w), w + ' / ' + t);
  assert.ok(new Game(p, defaultKnobs(p), 844, 'x').knobText().includes('上書きなし'));
});

test('既定（オーナーが初めて開いたとき）', () => {
  const k = ownerKnobs(p);
  assert.deepEqual([k.budgetBase, k.packetBase, k.slimeHpMul, k.pullForward, k.packRule, k.hitsMul, k.dropSync, k.spellMode, k.swarmFrom, k.startCoin, k.priceMul],
    [28, 3, 1.5, false, 'B', 2, true, 'S1b', 2, 15, 0.7]);
});
