// 規則の芯を Node で確かめる（DOM なし）。node --test test/core.test.ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { newGame, apply, replay, fingerprint, type State, type Action } from '../src/core/sim.ts';
import { seedFrom, nextU32 } from '../src/core/rng.ts';
import { exportText, importText } from '../src/core/save.ts';

const k = (s: State, x: number, y: number) => s.cells[y * s.w + x].k;
function withLaw(law: State['law']): State {
  const s = newGame('t'); s.law = law; s.shelf = { P: 9, W: 9, S: 9, F: 9 }; return s;
}

test('乱数：同じシードなら同じ列、違うシードなら違う列', () => {
  const a = seedFrom('谷-0001'), b = seedFrom('谷-0001'), c = seedFrom('谷-0002');
  const ra = Array.from({ length: 1000 }, () => nextU32(a));
  const rb = Array.from({ length: 1000 }, () => nextU32(b));
  const rc = Array.from({ length: 1000 }, () => nextU32(c));
  assert.deepEqual(ra, rb);
  assert.notDeepEqual(ra, rc);
  // 決まった値（規則やエンジンが変わったら気づく。ブラウザ側でも同じ値か E2E で比べる）
  assert.equal(nextU32(seedFrom('谷-0001')).toString(16), GOLDEN_FIRST);
});

test('シードから掟と棚が決まり、シードを変えると散らばる', () => {
  assert.deepEqual(newGame('谷-0001'), newGame('谷-0001'));
  const laws = new Set<string>();
  for (let i = 0; i < 200; i++) laws.add(newGame('谷-' + i).law);
  assert.equal(laws.size, 3);
});

test('重りは落ち、床で止まる', () => {
  const s = withLaw('none');
  apply(s, { t: 'place', x: 2, y: 0, k: 'W' });
  for (let i = 0; i < 10; i++) apply(s, { t: 'step' });
  assert.equal(k(s, 2, 4), 'W');
});

test('板の上で止まり、ばねの上で2マス跳ねる', () => {
  const s = withLaw('none');
  apply(s, { t: 'place', x: 1, y: 2, k: 'P' });
  apply(s, { t: 'place', x: 1, y: 0, k: 'W' });
  apply(s, { t: 'place', x: 3, y: 4, k: 'S' });
  apply(s, { t: 'place', x: 3, y: 3, k: 'W' });
  apply(s, { t: 'step' });
  assert.equal(k(s, 1, 1), 'W');
  assert.equal(k(s, 3, 1), 'W'); // 3→1 へ2マス
});

test('火は隣の板に移り、2手で消える。長雨では移らない', () => {
  const s = withLaw('none');
  apply(s, { t: 'place', x: 0, y: 4, k: 'F' });
  apply(s, { t: 'place', x: 1, y: 4, k: 'P' });
  apply(s, { t: 'place', x: 2, y: 4, k: 'P' });
  apply(s, { t: 'step' });
  assert.deepEqual([k(s, 0, 4), k(s, 1, 4), k(s, 2, 4)], ['F', 'F', 'P']); // 同時判定：1手で1マスずつ
  apply(s, { t: 'step' });
  assert.deepEqual([k(s, 0, 4), k(s, 1, 4), k(s, 2, 4)], ['.', 'F', 'F']);
  const r = withLaw('rain');
  apply(r, { t: 'place', x: 0, y: 4, k: 'F' });
  apply(r, { t: 'place', x: 1, y: 4, k: 'P' });
  apply(r, { t: 'step' });
  assert.equal(k(r, 1, 4), 'P');
});

test('大風：落ちた重りが東へ流れる', () => {
  const s = withLaw('wind');
  apply(s, { t: 'place', x: 0, y: 0, k: 'W' });
  apply(s, { t: 'step' });
  assert.equal(k(s, 1, 1), 'W');
});

test('記録の再生で同じ指紋になる（1万手のでたらめな入力）', () => {
  const r = seedFrom('入力');
  const s = newGame('谷-0042');
  for (let i = 0; i < 10000; i++) {
    const n = nextU32(r) % 10;
    const x = nextU32(r) % 5, y = nextU32(r) % 5;
    const kinds = ['P', 'W', 'S', 'F'] as const;
    const a: Action = n < 4 ? { t: 'place', x, y, k: kinds[n] } : n < 6 ? { t: 'remove', x, y } : { t: 'step' };
    apply(s, a);
  }
  assert.equal(fingerprint(replay(s.seed, s.log)), fingerprint(s));
  assert.equal(fingerprint(s), GOLDEN_10K);
});

test('書き出し→読み込みで同じ。1文字でも変えたら弾く', () => {
  const s = newGame('谷-0007');
  apply(s, { t: 'place', x: 2, y: 0, k: 'W' });
  apply(s, { t: 'step' });
  const text = exportText(s);
  assert.equal(fingerprint(importText(text)), fingerprint(s));
  const bad = text.slice(0, 20) + (text[20] === 'A' ? 'B' : 'A') + text.slice(21);
  assert.throws(() => importText(bad));
  assert.throws(() => importText('YK2.xxx.yyy'));
});

test('速さの目安：5×5で10万手', () => {
  const s = newGame('谷-0001'); s.shelf = { P: 99, W: 99, S: 99, F: 99 };
  for (let x = 0; x < 5; x++) apply(s, { t: 'place', x, y: 0, k: 'W' });
  const t0 = performance.now();
  for (let i = 0; i < 100000; i++) apply(s, { t: 'step' });
  const ms = performance.now() - t0;
  console.log(`  10万手: ${ms.toFixed(0)}ms（1手 ${(ms / 100000 * 1000).toFixed(1)}µs）`);
});

// 初回の実行で出た値を固定した（規則の版を変えたら、ここも変わるのが正しい）
const GOLDEN_FIRST = '529f9503';
const GOLDEN_10K = '120aa3a5';
