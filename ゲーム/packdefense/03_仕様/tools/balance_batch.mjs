// balance_sim.mjs をシード 1〜N で動かし、最初のランと記録の伸びをまとめる（game-spec-balance、2026-11-25）
// 使い方：node balance_batch.mjs [シードの数=8] [時間=1] [balance_sim に渡す引数 ...]
//   例：node balance_batch.mjs 8 1 --skill weak
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const [nS = '8', hrs = '1', ...rest] = process.argv.slice(2);
const res = [];
for (let s = 1; s <= Number(nS); s++) {
  const out = execFileSync('node', [path.join(here, 'balance_sim.mjs'), hrs, String(s), ...rest], { encoding: 'utf8' });
  const first = [...out.match(/最初のラン：(.*)/)[1].matchAll(/第(\d+)\(([\d.]+)分\)/g)].map(m => [Number(m[1]), Number(m[2])]);
  const rec = Number(out.match(/記録 第(\d+)、記録が伸びない/)[1]);
  const stuck = Number(out.match(/最長の連続 (\d+) 回/)[1]);
  const share = out.match(/与えた傷の割合（全部のラン）：(.*)/)[1];
  const lim = out.match(/画面の魔物の最多 (\d+).*弾の最多 (\d+).*いちばん長いウェーブ (\d+)秒/);
  const marks = [...out.matchAll(/^\s*([\d.]+)時間：ラン(\d+)回、記録 第(\d+)/gm)].map(m => `${m[1]}h:第${m[3]}`);
  res.push({ s, first, rec, stuck, share, mon: Number(lim[1]), proj: Number(lim[2]), wmax: Number(lim[3]), marks });
}
const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
const f1 = res.map(r => r.first[0]);
console.log(`引数：${rest.join(' ') || '（なし）'}、シード ${nS}、${hrs}時間`);
for (const r of res) console.log(`シード${r.s}：最初 第${r.first[0][0]}(${r.first[0][1]}分) 2回め 第${r.first[1]?.[0]} 3回め 第${r.first[2]?.[0]} 5回め 第${r.first[4]?.[0]} | ${r.marks.join(' ')} | 記録 第${r.rec} 止まり最長${r.stuck} | ${r.share} | 魔物${r.mon} 弾${r.proj} 最長${r.wmax}秒`);
console.log(`最初のラン：第${Math.min(...f1.map(x => x[0]))}〜${Math.max(...f1.map(x => x[0]))}（平均 ${avg(f1.map(x => x[0])).toFixed(1)}）、${Math.min(...f1.map(x => x[1]))}〜${Math.max(...f1.map(x => x[1]))}分（平均 ${avg(f1.map(x => x[1])).toFixed(1)}）`);
console.log(`記録：第${Math.min(...res.map(r => r.rec))}〜${Math.max(...res.map(r => r.rec))}（平均 ${avg(res.map(r => r.rec)).toFixed(1)}）、記録が伸びないランの最長 ${Math.max(...res.map(r => r.stuck))} 回`);
console.log(`画面の魔物の最多 ${Math.max(...res.map(r => r.mon))}、弾の最多 ${Math.max(...res.map(r => r.proj))}、いちばん長いウェーブ ${Math.max(...res.map(r => r.wmax))}秒`);
