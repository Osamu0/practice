// 序盤の圧と開封のコストの目安（node test/calib.ts）。自動の指で、つまみの組み合わせごとに数を出す。
// 人の目安ではない。「遅い指」が第1ウェーブで少し傷を受けるあたり、を探すための物差し。
import { readFileSync } from 'node:fs';
import { parseCsv, buildParams } from '../src/core/params.ts';
import { Game } from '../src/core/game.ts';
import { defaultKnobs, PRESSURE, type Knobs } from '../src/core/proto.ts';
import { slowBot, fastBot, runWave } from './bots.ts';

const { p } = buildParams(parseCsv(readFileSync(new URL('../../../03_仕様/パラメータ表.csv', import.meta.url), 'utf8')));
const SEEDS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const avg = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length;
const mk = (o: Partial<Knobs>, seed: string) => { const k = { ...defaultKnobs(p), ...o }; const g = new Game(p, k, 844, seed); g.newRun(); return g; };

console.log('## Q1 第1ウェーブ（8シードの平均。塔の傷・秒・同時の魔物の最大）');
for (const pr of PRESSURE) for (const [bn, bf] of [['遅い指', () => slowBot(false)], ['速い指', () => fastBot(false)], ['指なし', null]] as const) {
  const dmg: number[] = [], time: number[] = [], peak: number[] = [], hurt: number[] = [];
  for (const s of SEEDS) {
    const g = mk({ mode: 'q1', ...pr.v }, s); const bot = bf ? (bf as () => ReturnType<typeof slowBot>)() : null; let pk = 0;
    for (let i = 0; i < 60 * 200 && g.scene === 'fight'; i++) { bot?.tick(g); g.step(); pk = Math.max(pk, g.monsters.filter(m => g.visible(m)).length); }
    const st = g.logs[g.logs.length - 1]; const d = st.towerDmg.n + st.towerDmg.e + st.towerDmg.s + st.towerDmg.w;
    dmg.push(d); time.push(st.time); peak.push(pk); hurt.push(d > 0 ? 1 : 0);
  }
  console.log(`${pr.name.padEnd(6)} ${bn}: 塔の傷 平均${avg(dmg).toFixed(1)}（最小${Math.min(...dmg)}〜最大${Math.max(...dmg)}、傷を受けた${hurt.reduce((a, b) => a + b, 0)}/${SEEDS.length}） 秒${avg(time).toFixed(1)} 同時の最大${avg(peak).toFixed(1)}`);
}

console.log('\n## Q2 第2〜4ウェーブ（遅い指、8シード。開けるまでの秒・開けた数・塔の傷・呪文。「無視」はパックを狙わない遅い指）');
const q2 = (label: string, o: Partial<Knobs>, packs = true) => {
  const del: number[] = [], dmg: number[] = [], opened: number[] = [], casts: number[] = [], whiff: number[] = [], lost: number[] = [];
  for (const s of SEEDS) {
    const g = mk({ mode: 'q2', spellMode: 'S1a', ...o }, s); const bot = slowBot(packs);
    while (g.scene !== 'q2end') {
      if (g.scene === 'fight') runWave(g, bot);
      else if (g.scene === 'shop') { while (g.buy('novice')); g.nextWave(); }
      else break;
    }
    const L = g.logs; del.push(...L.flatMap(x => x.openDelays)); opened.push(L.reduce((a, x) => a + x.packsOpened, 0));
    dmg.push(L.reduce((a, x) => a + x.towerDmg.n + x.towerDmg.e + x.towerDmg.s + x.towerDmg.w, 0));
    casts.push(L.reduce((a, x) => a + x.spellCasts, 0)); whiff.push(L.reduce((a, x) => a + x.spellWhiff, 0));
    lost.push(L.some(x => x.result === '塔が壊れた') ? 1 : 0);
  }
  console.log(`${label}: 開けるまで平均${del.length ? avg(del).toFixed(1) : '-'}秒 開けた${avg(opened).toFixed(1)} 塔の傷${avg(dmg).toFixed(1)}（壊れた${lost.reduce((a, b) => a + b, 0)}/8） 呪文${avg(casts).toFixed(1)}（空振り${avg(whiff).toFixed(1)}）`);
};
q2('CSV・A・×1・山切・S1a        ', {});
q2('CSV・A・×1・山切・S1a 無視    ', {}, false);
q2('CSV・A・×2・山切・S1a        ', { hitsMul: 2 });
q2('CSV・A・×2・山入・S1a        ', { hitsMul: 2, dropSync: true });
q2('CSV・A・×3・山入・S1a        ', { hitsMul: 3, dropSync: true });
q2('CSV・B・×2・山入・S1a        ', { hitsMul: 2, dropSync: true, packRule: 'B' });
q2('CSV・C・×2・山入・S1a        ', { hitsMul: 2, dropSync: true, packRule: 'C' });
q2('CSV・B・×2・山入・S1b        ', { hitsMul: 2, dropSync: true, packRule: 'B', spellMode: 'S1b' });
q2('CSV・B・×2・山入・S1a 群れ第2', { hitsMul: 2, dropSync: true, packRule: 'B', swarmFrom: 2 });
q2('CSV・B・×2・山入・S1b 群れ第2', { hitsMul: 2, dropSync: true, packRule: 'B', spellMode: 'S1b', swarmFrom: 2 });
q2('CSV・B・×2・山入・S1b 群れ第2 無視', { hitsMul: 2, dropSync: true, packRule: 'B', spellMode: 'S1b', swarmFrom: 2 }, false);
q2('やや強い・B・×2・山入・S1b 群れ第2', { ...PRESSURE[1].v, hitsMul: 2, dropSync: true, packRule: 'B', spellMode: 'S1b', swarmFrom: 2 });
q2('やや強い・B・×2・山入・S1b 群れ第2 無視', { ...PRESSURE[1].v, hitsMul: 2, dropSync: true, packRule: 'B', spellMode: 'S1b', swarmFrom: 2 }, false);
q2('やや強い・B・×3・山入・S1b 群れ第2', { ...PRESSURE[1].v, hitsMul: 3, dropSync: true, packRule: 'B', spellMode: 'S1b', swarmFrom: 2 });
q2('やや強い・A・×1・山切・S1a（群れ第4）', { ...PRESSURE[1].v });

console.log('\n## ショップ：第1〜4のショップで買えた数（遅い指、Q3 の1ラン目の第1〜5、圧は CSV）');
for (const [label, o] of [['CSV のまま', {}], ['最初15・値段×0.7', { startCoin: 15, priceMul: 0.7 }], ['最初25・値段×0.5', { startCoin: 25, priceMul: 0.5 }]] as const) {
  const per: number[][] = [];
  for (const s of SEEDS) {
    const g = mk({ mode: 'q3', ...o }, s); const bot = slowBot(true); const got: number[] = [];
    while (g.wave <= 4 && g.scene !== 'result') {
      if (g.scene === 'fight') runWave(g, bot);
      else if (g.scene === 'shop') { let n = 0; while (g.buy('novice')) n++; got.push(n); g.nextWave(); }
      else if (g.scene === 'q1end' || g.scene === 'q2end') break; else g.step();
    }
    per.push(got);
  }
  const cols = [0, 1, 2, 3].map(i => avg(per.map(x => x[i] ?? 0)).toFixed(1));
  console.log(`${label}: 見習いを買えた数（第1〜4のショップ、上限${p.shopBuyMax}） ${cols.join(' / ')}`);
}
