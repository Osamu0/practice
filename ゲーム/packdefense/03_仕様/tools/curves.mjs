// パラメータ表.csv の式から、ウェーブごとの表と強化の値段の表を出す（game-spec-balance、2026-11-25）
// 使い方：node curves.mjs [--set 名前=値 ...]   出力は Markdown の表（パラメータ表.md に貼る）
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const text = fs.readFileSync(path.join(here, '..', 'パラメータ表.csv'), 'utf8');
const T = new Map();
for (const line of text.split('\n').slice(1)) {
  const cells = []; let f = '', q = false;
  for (let i = 0; i < line.length; i++) { const c = line[i]; if (q) { if (c === '"') { if (line[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; } else if (c === '"') q = true; else if (c === ',') { cells.push(f); f = ''; } else f += c; }
  cells.push(f); if (cells[1]) T.set(cells[1], cells[2]);
}
const a = process.argv.slice(2); for (let i = 0; i < a.length; i++) if (a[i] === '--set') { const [k, v] = a[++i].split('='); T.set(k, v); }
const n = k => Number(T.get(k));
const market = w => Math.pow(n('econ.marketGrowth'), w - 1);
const hp = w => Math.pow(n('monster.hp.growthRate'), w - 1);
const budget = w => Math.min(n('wave.budget.cap'), n('wave.budget.base') + n('wave.budget.perWave') * (w - 1));
const dur = w => Math.min(n('wave.spawn.cap'), n('wave.spawn.first') + n('wave.spawn.perWave') * (w - 1));
const fame = w => n('fame.perWaveBase') * Math.pow(n('fame.growth'), w - 1);
const pk = w => Math.min(n('spawn.packet.cap'), n('spawn.packet.base') + Math.floor((w - 1) / n('spawn.packet.perWaves')));
const f = x => x < 1e4 ? (x < 10 ? x.toFixed(2) : x.toFixed(0)) : x.toExponential(2);
const slimeHits = w => n('monster.slime.hp') * hp(w) / (n('tap.damage') * market(w));
let cum = 0;
console.log('| ウェーブ n | 湧きの点 | 湧きの長さ（秒） | いっぺんに来る数 | 相場 | 耐久の伸び | slime の耐久 | slime をタップ何回（強化なし） | 1ウェーブのコイン（全部倒す＋生き延びた） | 見習いのパックが何個 | 生き延びた名声（記録の先は×2） | 名声の合計（第1から全部、記録の先） |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|');
for (const w of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 300, 500, 1000]) {
  const coin = n('wave.coin.base') * market(w) * (1 + n('wave.clear.coinRatio'));
  cum = 0; for (let k = 1; k <= w; k++) cum += fame(k) * (1 + n('fame.killShare')) * n('fame.beyondRecordMul');
  console.log(`| ${w} | ${f(budget(w))} | ${f(dur(w))} | ${pk(w)} | ${f(market(w))} | ${f(hp(w))} | ${f(n('monster.slime.hp') * hp(w))} | ${f(slimeHits(w))} | ${f(coin)} | ${(coin / (n('pack.novice.price') * market(w))).toFixed(2)} | ${f(fame(w))} | ${f(cum)} |`);
}
console.log('\n| 項目 | 段1 | 段2 | 段3 | 段5 | 段10 | 段20 | 段30 | 段50 | 段100 |');
console.log('|---|---|---|---|---|---|---|---|---|---|');
for (const id of ['tapDmg', 'heroDmg', 'spellPower', 'towerHp', 'tapAuto', 'packHits', 'tapInterval', 'heroRole.<role>', 'towerRegen', 'startCoin', 'coinGain', 'packCards', 'packSlots', 'headStart']) {
  const b = n(`upgrade.${id}.costBase`), g = n(`upgrade.${id}.costGrowth`), mx = T.get(`upgrade.${id}.maxLevel`);
  const max = mx === 'なし' ? Infinity : Number(mx);
  const cells = [1, 2, 3, 5, 10, 20, 30, 50, 100].map(L => L > max ? '—' : f(b * Math.pow(g, L - 1)));
  console.log(`| ${id}（${mx === 'なし' ? '上限なし' : '最大' + mx}） | ${cells.join(' | ')} |`);
}
const k = Math.log(n('fame.growth')) / Math.log(n('upgrade.tapDmg.costGrowth')) * Math.log(n('upgrade.tapDmg.effect')) / Math.log(n('monster.hp.growthRate') / n('econ.marketGrowth'));
console.log(`\nk ＝ ln(fame.growth)/ln(costGrowth) × ln(effect)/ln(monster.hp.growthRate/econ.marketGrowth) ＝ ${k.toFixed(3)}`);
let W = 1; while (fame(W) * 10 < 1e300 && W < 5000) W++; console.log(`名声（1ウェーブ）が 1e300 に届くウェーブ：第${W}`);
let W2 = 1; while (n('monster.boss.hp') * hp(W2) < 1e300 && W2 < 5000) W2++; console.log(`大物の耐久が 1e300 に届くウェーブ：第${W2}`);
