// TS の規則の写し（src/core.ts）が、rules_sim.py（03_仕様/tools）と同じ結果になるかを照らす。
// 先に python3 tools/make_cases.py で test/cases.json を作る。node --test test/compare.test.ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { State, type Act, type Dir, type Tool, type ToolCell } from '../src/core.ts';
import type { PartId } from '../src/params.ts';

interface Dump {
  terrain: string[]; nid: number; goal: [number, number] | null;
  objs: { id: number; kind: 'leader' | 'part'; part: PartId | null; x: number; y: number; wear: number; facing: Dir | null; dist: number; byLeader: boolean }[];
  links: [number, number][]; comp: [number, number, number, number, number, number][]; inv: [number, number, PartId, Dir | null, number][][];
}
interface Case { name: string; start: Dump; steps: { act: any; key: any }[] }

const cases: Case[] = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));

function load(d: Dump): State {
  const s = new State(d.terrain);
  for (const o of d.objs) s.objs.set(o.id, { kind: o.kind, part: o.part ?? undefined, x: o.x, y: o.y, wear: o.wear, facing: o.facing ?? undefined, dist: o.dist, byLeader: o.byLeader });
  s.nid = d.nid;
  for (const [a, b] of d.links) s.links.add(Math.min(a, b) + ',' + Math.max(a, b));
  for (const [k, gi, sx, sy, gx, gy] of d.comp) s.comp.set(k, [gi, sx, sy, gx, gy]);
  s.inv = d.inv.map(t => t.map(c => [c[0], c[1], c[2], c[3], c[4]] as ToolCell));
  s.goal = d.goal ? [d.goal[0], d.goal[1]] : null;
  s.goalMustStop = true;
  return s;
}

const toolSig = (t: Tool) => JSON.stringify([...t].map(c => [c[0], c[1], c[2], c[3], c[4] ?? 0]).sort());

function decode(s: State, a: any): Act {
  if (a.t === 'place') {
    const sig = toolSig(a.cells);
    const ti = s.inv.findIndex(t => toolSig(t) === sig);
    assert.ok(ti >= 0, '置く道具が持ち物にない');
    return { t: 'place', tool: ti, ox: a.ox, oy: a.oy };
  }
  if (a.t === 'pick') {
    const occ = s.occ();
    return { t: 'pick', ids: a.cells.map(([x, y]: [number, number]) => occ.get(x + ',' + y)!) };
  }
  return a as Act;
}

function keyOf(s: State) {
  const k = s.key();
  return { objs: k.objs, links: k.links, comp: k.comp, dead: k.dead, inv: k.inv, solved: s.solved() };
}

const groups = new Map<string, Case[]>();
for (const c of cases) { const g = c.name.split(' ')[0]; if (!groups.has(g)) groups.set(g, []); groups.get(g)!.push(c); }

for (const [g, cs] of groups) {
  test(`${g}：${cs.length} ケース、${cs.reduce((a, c) => a + c.steps.length, 0)} 手が rules_sim.py と同じ`, () => {
    for (const c of cs) {
      let s = load(c.start);
      c.steps.forEach((st, n) => {
        const t = s.do(decode(s, st.act));
        assert.ok(t, `${c.name}：${n + 1}手目 ${JSON.stringify(st.act)} が TS ではできない手`);
        assert.deepEqual(keyOf(t!), st.key, `${c.name}：${n + 1}手目 ${JSON.stringify(st.act)} のあとが違う`);
        s = t!;
      });
    }
  });
}

test('次の1手の印（写しの盤面で1手進める）と、確定したあとの盤面が同じ（R-26 の小さな版）', () => {
  for (const c of cases.filter(c => c.name.startsWith('B'))) {
    let s = load(c.start);
    for (const st of c.steps) {
      const act = decode(s, st.act);
      const preview = s.copy().do(act)!;
      const real = s.do(act)!;
      assert.deepEqual(preview.key(), real.key());
      s = real;
    }
  }
});

test('A の「解く」は解け、「運ばれる手順」は印で止まらないので解けない', () => {
  for (const c of cases.filter(c => c.name.startsWith('A'))) {
    const last = c.steps[c.steps.length - 1].key;
    const any = c.steps.some(s => s.key.solved);
    if (c.name.includes('解く')) assert.ok(last.solved, c.name);
    else assert.ok(!any, c.name);
  }
});

test('まだ解けるか（外れたの判定）と、つり合いの余裕', () => {
  const map = ['.......', '.......', '.......', '#......', '#......', '###....', '###....'];
  const mk = (tool: Tool) => { const s = new State(map); s.add({ kind: 'leader', x: 0, y: 2 }); s.goal = [3, 3]; s.goalMustStop = true; s.inv = [tool]; return s; };
  assert.equal(mk([[0, 0, 'stoneWeight', null], [0, 1, 'plank', null], [1, 1, 'plank', null], [2, 1, 'plank', null]]).canStillSolve(), 'yes');
  assert.equal(mk([[0, 0, 'plank', null], [1, 0, 'plank', null], [2, 0, 'plank', null]]).canStillSolve(), 'no');
  // 板3（西の端に石）が崖に置かれ、東の端に当主：倒す 4 ＝ 戻す 4
  const s = new State(map);
  const ids = [1, 2, 3].map(x => s.add({ kind: 'part', part: 'plank', x, y: 4 }));
  s.links.add(ids[0] + ',' + ids[1]); s.links.add(ids[1] + ',' + ids[2]);
  const st = s.add({ kind: 'part', part: 'stoneWeight', x: 1, y: 3 }); s.links.add(ids[0] + ',' + st);
  s.add({ kind: 'leader', x: 3, y: 3 });
  const b = s.balances()[0];
  assert.deepEqual([b.dir, b.m, b.r], [1, 4, 4]);
});
