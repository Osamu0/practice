// 規則の芯（Q1 のプロト。捨てる前提）。
// 03_仕様/tools/rules_sim.py の State を、Q1 で使う範囲だけ TypeScript に写したもの：
//   2-2 弾む、2-4 ずれる、2-5 落ちる（当たる・縮む・谷底・落ちて死ぬ・下敷き）、当主の手（入る・登る・押す・置く・拾う・待つ）
// 入れていないもの：燃える、引っぱる、水、杭、墓、敵、掟、癖（Q1 の範囲外）。
// Math.random・Date・DOM は使わない（規則の計算 8章）。照合は test/compare.test.ts。
import { P, PARTS, type PartId } from './params.ts';

export type Dir = 'up' | 'down' | 'east' | 'west';
export const DIRS: Record<Dir, [number, number]> = { up: [0, -1], down: [0, 1], east: [1, 0], west: [-1, 0] };
const OPP: Record<Dir, Dir> = { up: 'down', down: 'up', east: 'west', west: 'east' };

export interface Obj {
  kind: 'leader' | 'part';
  part?: PartId;
  x: number; y: number;
  wear: number;
  facing?: Dir;
  dist: number;
  byLeader: boolean;
  /** 試し場の人形（当主と同じ値。壊れても・落ちて「死んで」も手は止めない） */
  doll?: boolean;
}

/** 道具の1マス：[dx, dy, 部品, 向き, 傷み]（拾った部品は傷みを持ったまま道具になる） */
export type ToolCell = [number, number, PartId, Dir | null, number?];
export type Tool = ToolCell[];

export type Act =
  | { t: 'wait' }
  | { t: 'enter' | 'climb' | 'push'; d: -1 | 1 }
  | { t: 'place'; tool: number; ox: number; oy: number }
  | { t: 'pick'; ids: number[] };

export type Stage = '段1' | '2-2' | '2-4' | '2-5';
export interface Ev {
  stage: Stage;
  type: 'slid' | 'fell' | 'landed' | 'abyss' | 'compressed' | 'launched' | 'worn' | 'broken' | 'death' | 'doll';
  ids: number[];
  dir?: number;
  why?: string;
  /** ずれたときの重み（説明の帯に出す） */
  m?: number; r?: number;
}
export interface Snap { stage: Stage; objs: Map<number, { x: number; y: number; wear: number; facing?: Dir }> }

export class State {
  terrain: string[];
  W: number; H: number;
  objs = new Map<number, Obj>();
  links = new Set<string>(); // "a,b"（a < b）
  comp = new Map<number, [number, number, number, number, number]>(); // ばね → [G, sx, sy, gx, gy]
  nid = 0;
  inv: Tool[] = [];
  dead: string | null = null;
  goal: [number, number] | null = null;
  goalMustStop = false;
  moved = new Set<number>();
  events: Ev[] = [];
  snaps: Snap[] = [];
  private stage: Stage = '段1';

  constructor(terrain: string[]) {
    this.terrain = terrain;
    this.H = terrain.length;
    this.W = terrain[0].length;
  }

  copy(): State {
    const s = new State(this.terrain);
    for (const [k, o] of this.objs) s.objs.set(k, { ...o });
    s.links = new Set(this.links);
    s.comp = new Map(this.comp);
    s.nid = this.nid;
    s.inv = this.inv.map(t => t.map(c => [...c] as ToolCell));
    s.dead = this.dead;
    s.goal = this.goal;
    s.goalMustStop = this.goalMustStop;
    return s;
  }

  add(o: Omit<Obj, 'dist' | 'wear' | 'byLeader'> & Partial<Obj>): number {
    const i = this.nid++;
    this.objs.set(i, { dist: 0, wear: 0, byLeader: false, ...o } as Obj);
    return i;
  }

  // --- 盤面 ---
  ground(x: number, y: number) { return x >= 0 && x < this.W && y >= 0 && y < this.H && this.terrain[y][x] === '#'; }
  occ(): Map<string, number> {
    const m = new Map<string, number>();
    for (const [i, o] of this.objs) m.set(o.x + ',' + o.y, i);
    return m;
  }
  free(x: number, y: number, occ: Map<string, number>, ignore?: Set<number> | number[]) {
    if (!(x >= 0 && x < this.W && y >= 0 && y < this.H)) return false;
    if (this.terrain[y][x] === '#') return false;
    const j = occ.get(x + ',' + y);
    if (j === undefined) return true;
    if (!ignore) return false;
    return Array.isArray(ignore) ? ignore.includes(j) : ignore.has(j);
  }
  weight(i: number) {
    const o = this.objs.get(i)!;
    return o.kind === 'leader' ? P['leader.weight'] : PARTS[o.part!].weight;
  }
  hardness(i: number) {
    const o = this.objs.get(i)!;
    return o.kind === 'leader' ? P['leader.hardness'] : PARTS[o.part!].hardness;
  }
  isSpring(i: number) { const o = this.objs.get(i)!; return o.kind === 'part' && PARTS[o.part!].springPower !== undefined; }
  power(i: number) { return PARTS[this.objs.get(i)!.part!].springPower!; }

  groups(): number[][] {
    const parent = new Map<number, number>();
    for (const i of this.objs.keys()) parent.set(i, i);
    const f = (a: number): number => {
      while (parent.get(a) !== a) { parent.set(a, parent.get(parent.get(a)!)!); a = parent.get(a)!; }
      return a;
    };
    for (const l of this.links) {
      const [a, b] = l.split(',').map(Number);
      if (parent.has(a) && parent.has(b)) parent.set(f(a), f(b));
    }
    const g = new Map<number, number[]>();
    for (const i of this.objs.keys()) {
      const r = f(i);
      if (!g.has(r)) g.set(r, []);
      g.get(r)!.push(i);
    }
    return [...g.values()].map(v => v.sort((a, b) => a - b));
  }
  gweight(g: Iterable<number>) { let w = 0; for (const i of g) w += this.weight(i); return w; }

  supportedSet(gs: number[][]): [Set<number>, Map<number, number>] {
    const occ = this.occ();
    const gid = new Map<number, number>();
    gs.forEach((g, k) => g.forEach(i => gid.set(i, k)));
    const sup = new Set<number>();
    let changed = true;
    while (changed) {
      changed = false;
      for (let k = 0; k < gs.length; k++) {
        if (sup.has(k)) continue;
        for (const i of gs[k]) {
          const o = this.objs.get(i)!;
          const bx = o.x, by = o.y + 1;
          if (by >= this.H) continue;
          if (this.ground(bx, by)) { sup.add(k); changed = true; break; }
          const j = occ.get(bx + ',' + by);
          if (j !== undefined && gid.get(j) !== k && sup.has(gid.get(j)!)) { sup.add(k); changed = true; break; }
        }
      }
    }
    return [sup, gid];
  }

  order(gs: number[][]) {
    const key = (g: number[]) => [-Math.max(...g.map(i => this.objs.get(i)!.y)), Math.min(...g.map(i => this.objs.get(i)!.x)), Math.min(...g)];
    return [...gs].sort((a, b) => { const ka = key(a), kb = key(b); for (let t = 0; t < 3; t++) if (ka[t] !== kb[t]) return ka[t] - kb[t]; return 0; });
  }

  remove(i: number) {
    this.objs.delete(i);
    for (const l of [...this.links]) { const [a, b] = l.split(',').map(Number); if (a === i || b === i) this.links.delete(l); }
    for (const [s, v] of [...this.comp]) if (s === i || v[0] === i) this.comp.delete(s);
  }

  private ev(e: Omit<Ev, 'stage'>) { this.events.push({ stage: this.stage, ...e }); }

  /** 当主の死。人形なら手を止めない（作業台と設計図.md 10章：人形は壊れても何も起きない） */
  private kill(i: number, why: string) {
    const o = this.objs.get(i);
    if (o?.doll) { this.ev({ type: 'doll', ids: [i], why }); return; }
    this.dead = why;
    this.ev({ type: 'death', ids: [i], why });
  }

  breakObj(i: number, why: string) {
    const o = this.objs.get(i);
    if (!o) return;
    if (o.kind === 'leader') this.kill(i, why);
    else {
      o.wear += P['rule.impact.wearAdd'];
      if (o.wear > 2) { this.remove(i); this.ev({ type: 'broken', ids: [i], why }); }
      else this.ev({ type: 'worn', ids: [i], why });
    }
  }

  moveGroup(g: Iterable<number>, dx: number, dy: number) {
    for (const i of g) { const o = this.objs.get(i)!; o.x += dx; o.y += dy; }
  }

  // --- 2-2 弾む ---
  stepBounce() {
    this.stage = '2-2';
    for (const s of [...this.comp.keys()].sort((a, b) => a - b)) {
      if (!this.comp.has(s)) continue;
      const [gi, sx, sy, gx, gy] = this.comp.get(s)!;
      this.comp.delete(s);
      if (!this.objs.has(s) || !this.objs.has(gi)) continue;
      const so = this.objs.get(s)!, go = this.objs.get(gi)!;
      if (so.x !== sx || so.y !== sy || go.x !== gx || go.y !== gy) continue;
      const g = this.groups().find(x => x.includes(gi))!;
      if (g.some(i => this.moved.has(i))) continue;
      const d = Math.max(0, this.power(s) - this.gweight(g));
      const [dx, dy] = DIRS[so.facing!];
      let moved = 0;
      for (let n = 0; n < d; n++) {
        const occ = this.occ();
        let block: number | null = null;
        let ok = true;
        for (const i of g) {
          const o = this.objs.get(i)!;
          const nx = o.x + dx, ny = o.y + dy;
          if (!(nx >= 0 && nx < this.W && ny >= 0 && ny < this.H) || this.ground(nx, ny)) { ok = false; continue; }
          const j = occ.get(nx + ',' + ny);
          if (j !== undefined && !g.includes(j)) { ok = false; block = j; }
        }
        if (!ok) {
          if (moved >= 1 && block !== null) {
            const bo = this.objs.get(block)!;
            if (this.isSpring(block) && bo.facing === OPP[so.facing!]) {
              this.comp.set(block, [gi, bo.x, bo.y, this.objs.get(gi)!.x, this.objs.get(gi)!.y]);
              this.ev({ type: 'compressed', ids: [block] });
            } else if (this.gweight(g) >= this.hardness(block)) this.breakObj(block, '投げ当て');
          }
          break;
        }
        this.moveGroup(g, dx, dy);
        moved++;
      }
      for (const i of g) if (this.objs.has(i)) { this.objs.get(i)!.dist = 0; this.moved.add(i); }
      if (moved) this.ev({ type: 'launched', ids: g, dir: dy === 0 ? dx : 0 });
      if (this.dead) return;
    }
  }

  // --- 2-4 ずれる ---
  stepSlide() {
    this.stage = '2-4';
    const gs = this.groups();
    const [sup, gid] = this.supportedSet(gs);
    let occ = this.occ();
    for (const g of this.order(gs)) {
      if (g.some(i => this.moved.has(i) || !this.objs.has(i))) continue;
      if (g.length < 2) continue;
      const k = gid.get(g[0])!;
      if (!sup.has(k)) continue;
      const gset = new Set(g);
      const cols: number[] = [];
      for (const i of g) {
        const o = this.objs.get(i)!;
        const by = o.y + 1;
        if (by < this.H) {
          const j = occ.get(o.x + ',' + by);
          if (this.ground(o.x, by) || (j !== undefined && !gset.has(j) && sup.has(gid.get(j)!))) cols.push(o.x);
        }
      }
      if (!cols.length) continue;
      const xW = Math.min(...cols), xE = Math.max(...cols);
      const load = new Map<number, number>();
      const stack = new Set<number>();
      for (const x of new Set(g.map(i => this.objs.get(i)!.x))) {
        const top = Math.min(...g.filter(i => this.objs.get(i)!.x === x).map(i => this.objs.get(i)!.y));
        let l = g.filter(i => this.objs.get(i)!.x === x).reduce((a, i) => a + this.weight(i), 0);
        let y = top - 1;
        while (y >= 0 && occ.get(x + ',' + y) !== undefined && !gset.has(occ.get(x + ',' + y)!)) {
          const j = occ.get(x + ',' + y)!;
          l += this.weight(j);
          stack.add(j);
          y--;
        }
        load.set(x, l);
      }
      let mE = 0, rE = 0, mW = 0, rW = 0;
      for (const [x, l] of load) {
        if (x > xE) mE += l * (x - xE);
        if (x < xE) rE += l * (xE - x);
        if (x < xW) mW += l * (xW - x);
        if (x > xW) rW += l * (x - xW);
      }
      const east = mE > rE, west = mW > rW;
      if (east === west) continue;
      const dx = east ? 1 : -1;
      const mv = new Set(g);
      for (const j of stack) for (const i of gs.find(x => x.includes(j))!) mv.add(i);
      if ([...mv].every(i => this.free(this.objs.get(i)!.x + dx, this.objs.get(i)!.y, occ, mv))) {
        this.moveGroup(mv, dx, 0);
        for (const i of mv) this.moved.add(i);
        occ = this.occ();
        this.ev({ type: 'slid', ids: [...mv], dir: dx, m: east ? mE : mW, r: east ? rE : rW });
      }
    }
  }

  // --- 2-5 落ちる ---
  stepFall() {
    this.stage = '2-5';
    const gs0 = this.groups();
    const [sup0] = this.supportedSet(gs0);
    let active: Set<number>[] = gs0.map(g => new Set(g)).filter((g, k) => !sup0.has(k) && ![...g].some(i => this.moved.has(i)));
    const fell = new Map<number, number>();
    let prevMoved = new Set<number>();
    const startPos = new Map<number, number>();
    for (const g of active) for (const i of g) startPos.set(i, this.objs.get(i)!.y);
    for (let n = 0; n < P['rule.fall.cellsPerTurn']; n++) {
      if (!active.length) break;
      const occ = this.occ();
      const moving = [...active];
      let changed = true;
      while (changed) {
        changed = false;
        const mids = new Set<number>();
        for (const g of moving) for (const i of g) mids.add(i);
        for (const g of [...moving]) {
          let blocked = false;
          for (const i of g) {
            const o = this.objs.get(i)!;
            const ny = o.y + 1;
            if (ny >= this.H) continue;
            if (this.ground(o.x, ny)) { blocked = true; break; }
            const j = occ.get(o.x + ',' + ny);
            if (j !== undefined && !mids.has(j)) { blocked = true; break; }
          }
          if (blocked) { moving.splice(moving.indexOf(g), 1); changed = true; }
        }
      }
      const stopped = active.filter(g => !moving.includes(g));
      const movedNow = new Set<number>();
      for (const g of moving) {
        this.moveGroup(g, 0, 1);
        for (const i of g) { fell.set(i, (fell.get(i) ?? 0) + 1); this.objs.get(i)!.dist += 1; movedNow.add(i); }
      }
      for (const g of [...moving]) {
        if ([...g].some(i => this.objs.get(i)!.y >= this.H)) {
          const ids = [...g];
          for (const i of g) {
            if (this.objs.get(i)!.kind === 'leader') this.kill(i, '谷底へ落ちる');
            this.remove(i);
          }
          this.ev({ type: 'abyss', ids });
          moving.splice(moving.indexOf(g), 1);
        }
      }
      if (this.dead) return;
      const gs = this.groups();
      const [sup, gid] = this.supportedSet(gs);
      const nowLanded: Set<number>[] = [], still: Set<number>[] = [];
      for (const g of moving) (sup.has(gid.get(g.values().next().value!)!) ? nowLanded : still).push(g);
      this.land(nowLanded, movedNow);
      if (this.dead) return;
      this.land(stopped.filter(g => [...g].some(i => fell.get(i))), prevMoved);
      if (this.dead) return;
      for (const g of stopped) for (const i of g) if (this.objs.has(i)) this.moved.add(i);
      active = still.filter(g => [...g].every(i => this.objs.has(i)));
      prevMoved = movedNow;
    }
    for (const g of active) for (const i of g) if (this.objs.has(i)) this.moved.add(i);
    const fellIds = [...fell.keys()].filter(i => this.objs.has(i));
    if (fellIds.length) this.ev({ type: 'fell', ids: fellIds });
    const gs = this.groups();
    const [sup] = this.supportedSet(gs);
    gs.forEach((g, k) => { if (sup.has(k)) for (const i of g) this.objs.get(i)!.dist = 0; });
  }

  private land(groups: Set<number>[], movedNow: Set<number>) {
    if (!groups.length) return;
    const gset = groups;
    const pos = new Map<string, number>();
    gset.forEach((g, k) => { for (const i of g) { const o = this.objs.get(i)!; pos.set(o.x + ',' + o.y, k); } });
    const par = gset.map((_, k) => k);
    const f = (a: number) => { while (par[a] !== a) a = par[a]; return a; };
    for (const [p, k] of pos) {
      const [x, y] = p.split(',').map(Number);
      const k2 = pos.get(x + ',' + (y + 1));
      if (k2 !== undefined && k2 !== k) par[f(k)] = f(k2);
    }
    const clusters = new Map<number, number[]>();
    for (let k = 0; k < gset.length; k++) { const r = f(k); if (!clusters.has(r)) clusters.set(r, []); clusters.get(r)!.push(k); }
    const aboveWeight = (k: number, cl: Set<number>) => {
      const seen = new Set([k]), q = [k];
      while (q.length) {
        const a = q.pop()!;
        for (const i of gset[a]) {
          const o = this.objs.get(i)!;
          const k2 = pos.get(o.x + ',' + (o.y - 1));
          if (k2 !== undefined && cl.has(k2) && !seen.has(k2)) { seen.add(k2); q.push(k2); }
        }
      }
      let w = 0; for (const a of seen) w += this.gweight(gset[a]); return w;
    };
    for (const cl of clusters.values()) {
      const cellIds = new Set<number>();
      for (const k of cl) for (const i of gset[k]) cellIds.add(i);
      for (const i of cellIds) this.moved.add(i);
      this.ev({ type: 'landed', ids: [...cellIds] });
      const occ = this.occ();
      let broke = false;
      for (const k of cl) {
        const g = gset[k];
        const gd = Math.max(...[...g].map(i => this.objs.get(i)!.dist));
        const below: number[] = [];
        for (const i of g) {
          const o = this.objs.get(i)!;
          const j = occ.get(o.x + ',' + (o.y + 1));
          if (j !== undefined && !cellIds.has(j) && !below.includes(j)) below.push(j);
        }
        below.sort((a, b) => a - b);
        let comp = false;
        for (const j of below) {
          const bo = this.objs.get(j)!;
          if (this.isSpring(j) && bo.facing === 'up') {
            const gi = Math.min(...[...g].filter(i => this.objs.get(i)!.x === bo.x));
            this.comp.set(j, [gi, bo.x, bo.y, this.objs.get(gi)!.x, this.objs.get(gi)!.y]);
            this.ev({ type: 'compressed', ids: [j] });
            comp = true;
            break;
          }
        }
        if (comp) { for (const i of g) this.objs.get(i)!.dist = 0; continue; }
        if (gd >= P['rule.impact.minFall']) {
          const w = aboveWeight(k, new Set(cl));
          for (const j of below) {
            if (!this.objs.has(j) || movedNow.has(j)) continue;
            if (w >= this.hardness(j)) {
              this.breakObj(j, '下敷き');
              broke = true;
              if (this.dead) return;
            }
          }
        }
        const li = [...g].find(i => this.objs.get(i)!.kind === 'leader');
        if (li !== undefined && gd >= P['leader.fallDeathHeight']) {
          this.kill(li, '落ちて死ぬ');
          if (this.dead) return;
        }
      }
      if (broke) {
        const gs = this.groups();
        const [sup] = this.supportedSet(gs);
        gs.forEach((g2, k2) => { if (!sup.has(k2)) for (const i of g2) this.moved.add(i); });
      }
    }
  }

  // --- 当主 ---
  leader(): number | null {
    for (const [i, o] of this.objs) if (o.kind === 'leader' && !o.doll) return i;
    return null;
  }
  private climbSolid(x: number, y: number, occ: Map<string, number>, sup: Set<number>, gid: Map<number, number>) {
    if (!(x >= 0 && x < this.W && y >= 0 && y < this.H)) return false;
    if (this.ground(x, y)) return true;
    const j = occ.get(x + ',' + y);
    if (j === undefined || this.objs.get(j)!.kind === 'leader') return false;
    return sup.has(gid.get(j)!);
  }
  climbDest(d: number): [number, number] | null {
    const L = this.objs.get(this.leader()!)!;
    const tx = L.x + d;
    if (!(tx >= 0 && tx < this.W)) return null;
    const occ = this.occ();
    const [sup, gid] = this.supportedSet(this.groups());
    if (!this.climbSolid(tx, L.y, occ, sup, gid)) return null;
    for (let k = 1; k <= P['leader.climbHeight']; k++) {
      const ty = L.y - k;
      if (ty < 0) return null;
      if (!this.free(L.x, ty, occ)) return null;
      if (this.free(tx, ty, occ)) return [tx, ty];
      if (!this.climbSolid(tx, ty, occ, sup, gid)) return null;
    }
    return null;
  }
  pushOk(d: number) {
    const L = this.objs.get(this.leader()!)!;
    const tx = L.x + d;
    if (!(tx >= 0 && tx < this.W)) return false;
    const occ = this.occ();
    const j = occ.get(tx + ',' + L.y);
    if (j === undefined) return false;
    const g = this.groups().find(x => x.includes(j))!;
    if (g.some(i => this.objs.get(i)!.kind === 'leader')) return false;
    if (this.gweight(g) > P['leader.pushWeight']) return false;
    return g.every(i => this.free(this.objs.get(i)!.x + d, this.objs.get(i)!.y, occ, g));
  }
  enterOk(d: number) {
    const L = this.objs.get(this.leader()!)!;
    return this.free(L.x + d, L.y, this.occ());
  }
  pickable(g: number[]) {
    if (!g.every(i => this.objs.get(i)!.kind === 'part')) return false;
    return g.length === 1 || g.every(i => this.objs.get(i)!.byLeader);
  }
  /** 置く位置の候補（rules_sim.py の actions() と同じ順） */
  placeCandidates(ti: number): [number, number][] {
    const L = this.objs.get(this.leader()!)!;
    const occ = this.occ();
    const tool = this.inv[ti];
    const seen = new Set<string>();
    const out: [number, number][] = [];
    for (const [ax, ay] of [[L.x + 1, L.y], [L.x - 1, L.y], [L.x, L.y - 1], [L.x, L.y + 1]]) {
      for (const [dx, dy] of tool) {
        const ox = ax - dx, oy = ay - dy;
        if (seen.has(ox + ',' + oy)) continue;
        seen.add(ox + ',' + oy);
        if (tool.every(([tx, ty]) => this.free(ox + tx, oy + ty, occ))) out.push([ox, oy]);
      }
    }
    return out;
  }
  actions(): Act[] {
    const acts: Act[] = [{ t: 'wait' }];
    const li = this.leader();
    if (li === null) return acts;
    const L = this.objs.get(li)!;
    for (const d of [-1, 1] as const) {
      if (this.enterOk(d)) acts.push({ t: 'enter', d });
      if (this.climbDest(d)) acts.push({ t: 'climb', d });
      if (this.pushOk(d)) acts.push({ t: 'push', d });
    }
    this.inv.forEach((_, ti) => { for (const [ox, oy] of this.placeCandidates(ti)) acts.push({ t: 'place', tool: ti, ox, oy }); });
    if (this.inv.length < P['leader.carryTools']) {
      for (const g of this.groups()) {
        if (!this.pickable(g)) continue;
        if (g.some(i => Math.abs(this.objs.get(i)!.x - L.x) + Math.abs(this.objs.get(i)!.y - L.y) === 1)) acts.push({ t: 'pick', ids: g });
      }
    }
    return acts;
  }

  conn(o: Obj, side: Dir) {
    const def = PARTS[o.part!];
    if (def.springPower !== undefined) return side !== o.facing;
    if (def.noConn === side) return false;
    return true;
  }

  /** 道具を (ox, oy) に盤面の物として置く。置いた部品の番号を返す */
  placeTool(tool: Tool, ox: number, oy: number, byLeader = true): number[] {
    const ids = tool.map(([dx, dy, part, facing, wear]) => this.add({ kind: 'part', part, x: ox + dx, y: oy + dy, facing: facing ?? undefined, byLeader, wear: wear ?? 0 }));
    const pos = new Map(ids.map(i => [this.objs.get(i)!.x + ',' + this.objs.get(i)!.y, i]));
    for (const i of ids) {
      const o = this.objs.get(i)!;
      for (const [dx, dy, side, oside] of [[1, 0, 'east', 'west'], [0, 1, 'down', 'up']] as [number, number, Dir, Dir][]) {
        const j = pos.get((o.x + dx) + ',' + (o.y + dy));
        if (j === undefined) continue;
        if (this.conn(o, side) && this.conn(this.objs.get(j)!, oside)) this.links.add(Math.min(i, j) + ',' + Math.max(i, j));
      }
    }
    return ids;
  }

  snap() {
    const m = new Map<number, { x: number; y: number; wear: number; facing?: Dir }>();
    for (const [i, o] of this.objs) m.set(i, { x: o.x, y: o.y, wear: o.wear, facing: o.facing });
    this.snaps.push({ stage: this.stage, objs: m });
  }

  /** 1手。できない手なら null。返す盤面の events / snaps に、起きたことと小段ごとの写しが入る */
  do(act: Act): State | null {
    const s = this.copy();
    s.stage = '段1';
    s.snap();
    const li = s.leader();
    if (act.t !== 'wait' && li === null) return null;
    const L = li !== null ? s.objs.get(li)! : null;
    if (act.t === 'enter') {
      if (!s.enterOk(act.d)) return null;
      L!.x += act.d;
    } else if (act.t === 'climb') {
      const dest = s.climbDest(act.d);
      if (!dest) return null;
      [L!.x, L!.y] = dest;
    } else if (act.t === 'push') {
      if (!s.pushOk(act.d)) return null;
      const j = s.occ().get((L!.x + act.d) + ',' + L!.y)!;
      const g = s.groups().find(x => x.includes(j))!;
      s.moveGroup(g, act.d, 0);
      L!.x += act.d;
    } else if (act.t === 'place') {
      const tool = s.inv[act.tool];
      if (!tool) return null;
      const occ = s.occ();
      if (!tool.every(([tx, ty]) => s.free(act.ox + tx, act.oy + ty, occ))) return null;
      s.placeTool(tool, act.ox, act.oy);
      s.inv.splice(act.tool, 1);
    } else if (act.t === 'pick') {
      if (s.inv.length >= P['leader.carryTools']) return null;
      const g = act.ids;
      if (!g.every(i => s.objs.has(i))) return null;
      const mx = Math.min(...g.map(i => s.objs.get(i)!.x)), my = Math.min(...g.map(i => s.objs.get(i)!.y));
      const tool: Tool = g.map(i => { const o = s.objs.get(i)!; return [o.x - mx, o.y - my, o.part!, o.facing ?? null, o.wear] as ToolCell; });
      for (const i of g) s.remove(i);
      s.inv.push(tool);
    }
    s.snap();
    s.stepRules();
    return s;
  }

  stepRules() {
    this.moved = new Set();
    this.events = this.events.filter(e => e.stage === '段1');
    for (const f of [() => this.stepBounce(), () => this.stepSlide(), () => this.stepFall()]) {
      const n = this.events.length;
      f();
      if (this.events.length > n) this.snap();
      if (this.dead) return;
    }
  }

  solved() {
    if (this.dead || !this.goal) return false;
    const li = this.leader();
    if (li === null) return false;
    const o = this.objs.get(li)!;
    if (o.x !== this.goal[0] || o.y !== this.goal[1]) return false;
    return !this.goalMustStop || !this.moved.has(li);
  }

  /** 照合用の写し（rules_sim.py の key() に近い形） */
  key() {
    const objs = [...this.objs.values()].filter(o => !o.doll)
      .map(o => [o.kind, o.part ?? null, o.x, o.y, o.wear, o.facing ?? null, Math.min(o.dist, 9)] as const)
      .map(a => JSON.stringify(a)).sort();
    const links = [...this.links].map(l => { const [a, b] = l.split(',').map(Number); const pa = this.objs.get(a)!, pb = this.objs.get(b)!; return JSON.stringify([[pa.x, pa.y], [pb.x, pb.y]].sort((p, q) => p[0] - q[0] || p[1] - q[1])); }).sort();
    const comp = [...this.comp.entries()].filter(([s]) => this.objs.has(s)).map(([s, v]) => { const o = this.objs.get(s)!; return JSON.stringify([[o.x, o.y], [v[3], v[4]]]); }).sort();
    return { objs, links, comp, dead: this.dead, inv: this.inv.length };
  }
}

// ===== 地形 =====
export function trialMap(kind: 'flat' | 'cliff' | 'gap', cliffColumn: number): string[] {
  const n = P['trial.size'];
  const c = cliffColumn, w = P['trial.gapWidth'];
  let row = '';
  for (let x = 0; x < n; x++) {
    if (kind === 'cliff') row += x <= c ? '#' : '.';
    else if (kind === 'gap') row += (c < x && x <= c + w) ? '.' : '#';
    else row += '#';
  }
  return [...Array(n - 1).fill('.'.repeat(n)), row];
}

/** 作業台の中身 → 道具（左上をそろえる） */
export function benchToTool(cells: { x: number; y: number; part: PartId; facing?: Dir }[]): Tool {
  if (!cells.length) return [];
  const mx = Math.min(...cells.map(c => c.x)), my = Math.min(...cells.map(c => c.y));
  return cells.map(c => [c.x - mx, c.y - my, c.part, c.facing ?? null] as ToolCell);
}
