// 戦場の計算・保存・数の表記を Node で確かめる（DOM なし）。node --test test/core.test.ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { World, ringFromFinger, TOP, STEP } from '../src/core/sim.ts';
import { seedFrom, nextU32 } from '../src/core/rng.ts';
import { exportText, importText, saveLocal, loadLocal, SAVE_KEY, PREV_KEY, type SaveData } from '../src/core/save.ts';
import { fmt } from '../src/core/num.ts';

function quiet(seed = 't'): World { const w = new World(seed); w.spawnPerSec = 0; return w; }
function placeEnemy(w: World, x: number, y: number, hp: number): number {
  const i = w.enemy.add(x, y); w.enemy.a[i] = hp; w.enemy.b[i] = hp; return i;
}
class Mem { m = new Map<string, string>(); full = false;
  getItem(k: string) { return this.m.get(k) ?? null; }
  setItem(k: string, v: string) { if (this.full) throw new Error('QuotaExceededError'); this.m.set(k, v); }
  removeItem(k: string) { this.m.delete(k); } }
const sample = (over: Partial<SaveData> = {}): SaveData => ({ v: 1, seed: 's', wave: 7, phase: 'shop', coins: 12, towerHp: 80, fame: 1.5e42, heroes: [[100, 200, 1]], packs: [0, 2], settings: { ringOffset: 48, sound: true }, savedAt: 1, ...over });

test('乱数：同じシードなら同じ列（yarikomi と同じ sfc32）', () => {
  const a = seedFrom('x'), b = seedFrom('x');
  for (let i = 0; i < 1000; i++) assert.equal(nextU32(a), nextU32(b));
});

test('同じシードなら、同じウェーブは同じ出方・同じ結果（ウェーブの始まりから戻れる前提）', () => {
  const run = () => { const w = new World('seed/w3'); w.spawnPerSec = 4; w.addHero(180, 300); w.addHero(180, 480);
    for (let i = 0; i < 60 * 20; i++) w.step(); return [w.kills, w.towerHp, w.enemy.n, w.bullet.n, w.enemy.x[0] ?? 0].join(','); };
  assert.equal(run(), run());
});

test('攻撃の輪は指の少し上。ずらし 0 も選べる。上の端より上には出ない', () => {
  assert.deepEqual(ringFromFinger(100, 300, 48), { x: 100, y: 252 });
  assert.deepEqual(ringFromFinger(100, 300, 0), { x: 100, y: 300 });
  assert.equal(ringFromFinger(100, TOP + 10, 48).y, TOP);
});

test('押さえ続けると 0.1秒ごとに攻撃。輪の中の魔物に当たり、指の真下の魔物には当たらない', () => {
  const w = quiet();
  const finger = { x: 120, y: 500 }, ring = ringFromFinger(finger.x, finger.y, 48);
  const inRing = placeEnemy(w, ring.x + 20, ring.y, 100);   // 輪の中心から 20（当たりの半径 34 の中）
  placeEnemy(w, finger.x, finger.y, 100);                   // 指の真下（輪から 48 離れている）
  w.ringOn = true; w.ringX = ring.x; w.ringY = ring.y;
  for (let i = 0; i < 60; i++) w.step();                    // 1秒
  assert.equal(w.enemy.a[inRing], 90, '1秒で10回当たる');
  assert.equal(w.enemy.a[1], 100, '指の真下は当たらない');
  w.ringOn = false; for (let i = 0; i < 60; i++) w.step();
  assert.equal(w.enemy.a[inRing], 90, '離したら止まる');
  assert.ok(Math.abs(60 * STEP - 1) < 1e-9);
});

test('当たりは見た目の輪（半径28）より少し大きい（34）', () => {
  const w = quiet(); w.ringOn = true; w.ringX = 200; w.ringY = 400;
  placeEnemy(w, 200 + 32, 400, 10); placeEnemy(w, 200 + 36, 400, 10);
  w.step();
  assert.equal(w.enemy.a[0], 9); assert.equal(w.enemy.a[1], 10);
});

test('パックは輪で5回攻撃すると開き、その場に英雄が立つ', () => {
  const w = quiet(); w.addPack(150, 300, 2);
  w.ringOn = true; w.ringX = 150; w.ringY = 300;
  for (let i = 0; i < 60; i++) w.step();
  assert.equal(w.pack.n, 0); assert.equal(w.opened, 1); assert.equal(w.hero.n, 1);
  assert.equal(w.hero.k[0], 2); assert.ok(w.events.includes(3));
});

test('保存：書き出し→読み込みで同じ。Infinity（1e308 をこえた数）もこわれない', () => {
  const s = sample({ fame: Infinity });
  const back = importText(exportText(s));
  assert.deepEqual(back, s);
  assert.equal(back.fame, Infinity);
  assert.equal(JSON.parse(JSON.stringify({ a: Infinity })).a, null, '（ふつうの JSON だと null になる、の確かめ）');
});

test('保存：1文字変えた・途中で切れた・違う版の書き出しは断る', () => {
  const t = exportText(sample());
  const mid = Math.floor(t.length / 2);
  const bad = t.slice(0, mid) + (t[mid] === 'A' ? 'B' : 'A') + t.slice(mid + 1);
  assert.throws(() => importText(bad));
  assert.throws(() => importText(t.slice(0, t.length - 5)));
  assert.throws(() => importText(t.replace(/^PD1/, 'PD9')));
});

test('保存：端末内。前の保存も残し、今のが壊れていたら前のを読む。容量オーバーは false を返す', () => {
  const m = new Mem();
  assert.ok(saveLocal(m, sample({ wave: 1 })));
  assert.ok(saveLocal(m, sample({ wave: 2 })));
  assert.equal(loadLocal(m)!.wave, 2);
  m.m.set(SAVE_KEY, 'こわれた');
  assert.equal(loadLocal(m)!.wave, 1);
  m.m.delete(PREV_KEY); assert.equal(loadLocal(m), null);
  m.full = true; assert.equal(saveLocal(m, sample()), false);
});

test('保存の大きさ：英雄 60人・パック 8 でも 3KB 未満', () => {
  const s = sample({ heroes: Array.from({ length: 60 }, (_, i) => [i * 5, i * 7, i % 4] as [number, number, number]), packs: [0, 1, 2, 3, 0, 1, 2, 3] });
  const n = exportText(s).length;
  console.log(`  保存の文字数：${n}`);
  assert.ok(n < 3000);
});

test('数の表記：1 から 1e308 まで、7文字以内。Infinity は ∞', () => {
  const ex: [number, string][] = [[0, '0'], [9999, '9999'], [12345, '1.23万'], [99999999, '9999万'], [1e8, '1億'], [3.4e12, '3.4兆'], [5.6e16, '5.6京'], [1.234e20, '1.2e20'], [1.79e308, '2e308'], [Infinity, '∞']];
  for (const [n, s] of ex) assert.equal(fmt(n), s, String(n));
  let worst = '';
  for (let e = 0; e <= 308; e += 0.01) { const s = fmt(10 ** e); if (s.length > worst.length) worst = s; }
  console.log(`  いちばん長い表記：${worst}（${worst.length}文字）`);
  assert.ok(worst.length <= 7);
});

test('計算の速さ（Node）：物の数ごとの1歩の時間（目安）', () => {
  for (const n of [250, 500, 1000, 2000, 4000]) {
    const w = new World('bench');
    w.setStress({ enemy: n, hero: Math.min(96, n / 10), bullet: n, particle: n, float: 60, pack: 6 });
    w.ringOn = true; w.ringX = 180; w.ringY = 300;
    for (let i = 0; i < 60; i++) w.step();
    const t0 = performance.now(); for (let i = 0; i < 300; i++) w.step(); const ms = (performance.now() - t0) / 300;
    console.log(`  魔物${n}・弾${w.bullet.n}・粒${w.particle.n}・英雄${w.hero.n}（計 ${w.total()}）：1歩 ${ms.toFixed(3)} ms`);
  }
});
