// 大きな数の速さを比べる：JS の number／break_infinity.js 2.2.0／break_eternity.js 2.2.2（どちらも MIT）。
// 1回の「当たり」で、耐久 -= 攻撃×倍率、倒れたか比べる、コイン += 報酬、の3つの演算をする想定。node test/bench-num.ts
import BI from 'break_infinity.js';
import BE from 'break_eternity.js';

const N = 200_000;
function time(name: string, fn: () => unknown): number {
  fn(); // ならし
  const t0 = performance.now(); const r = fn(); const ms = performance.now() - t0;
  console.log(`${name.padEnd(22)} ${N.toLocaleString()}回 ${ms.toFixed(1).padStart(7)} ms  1回 ${(ms / N * 1e6).toFixed(0).padStart(5)} ns  (${String(r).slice(0, 14)})`);
  return ms;
}
const a = time('number', () => { let hp = 1e200, coin = 0; const atk = 3.5e190, mul = 1.7, rew = 2e150;
  for (let i = 0; i < N; i++) { hp -= atk * mul; if (hp <= 0) hp = 1e200; coin += rew; } return coin; });
const b = time('break_infinity.js', () => { let hp = new BI(1e200), coin = new BI(0); const atk = new BI(3.5e190), mul = new BI(1.7), rew = new BI(2e150), z = new BI(0);
  for (let i = 0; i < N; i++) { hp = hp.sub(atk.mul(mul)); if (hp.lte(z)) hp = new BI(1e200); coin = coin.add(rew); } return coin.toString(); });
const c = time('break_eternity.js', () => { let hp = new BE(1e200), coin = new BE(0); const atk = new BE(3.5e190), mul = new BE(1.7), rew = new BE(2e150), z = new BE(0);
  for (let i = 0; i < N; i++) { hp = hp.sub(atk.mul(mul)); if (hp.lte(z)) hp = new BE(1e200); coin = coin.add(rew); } return coin.toString(); });
console.log(`倍率：break_infinity ${(b / a).toFixed(0)}倍、break_eternity ${(c / a).toFixed(0)}倍（number を1として）`);
console.log(`1フレームに 2,000 回の当たりを計算すると：number ${(a / N * 2000).toFixed(3)} ms、break_infinity ${(b / N * 2000).toFixed(3)} ms、break_eternity ${(c / N * 2000).toFixed(3)} ms`);
console.log('1e308 をこえる：', new BI('1e1000').mul(new BI('1e5')).toString(), '／', new BE('1e1000').mul(new BE('1e5')).toString(), '／ number:', 1e300 * 1e10);
