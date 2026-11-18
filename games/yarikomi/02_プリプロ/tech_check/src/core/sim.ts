// 盤面の規則。描画・DOM に依存しない（Node でもブラウザでも同じコードが動く）。
// 整数だけ・決まった順番だけで計算する。
import { seedFrom, nextInt, fnv1a, type RngState } from './rng.ts';

export type Kind = '.' | 'P' | 'W' | 'S' | 'F'; // 空き、板、重り、ばね、火
export const KIND_NAME: Record<Kind, string> = { '.': '空き', P: '板', W: '重り', S: 'ばね', F: '火' };
export const PLACEABLE: Exclude<Kind, '.'>[] = ['P', 'W', 'S', 'F'];
export type Law = 'none' | 'wind' | 'rain';
export const LAW_NAME: Record<Law, string> = { none: '掟なし', wind: '大風（落ちる物が東へ流れる）', rain: '長雨（火が燃え移らない）' };

export interface Cell { k: Kind; a: number } // a：火の経過ターン
export type Action = { t: 'place'; x: number; y: number; k: Exclude<Kind, '.'> } | { t: 'remove'; x: number; y: number } | { t: 'step' };

export interface State {
  v: 1;
  seed: string;
  w: number;
  h: number;
  law: Law;
  turn: number;
  cells: Cell[];
  shelf: Record<Exclude<Kind, '.'>, number>;
  log: Action[]; // シードとこの記録から、いつでも同じ盤面を作り直せる
}

export function newGame(seed: string, w = 5, h = 5): State {
  const r: RngState = seedFrom(seed);
  const laws: Law[] = ['none', 'wind', 'rain'];
  const law = laws[nextInt(r, laws.length)];
  const shelf = { P: 2 + nextInt(r, 3), W: 1 + nextInt(r, 3), S: 1 + nextInt(r, 2), F: 1 + nextInt(r, 2) };
  const cells: Cell[] = Array.from({ length: w * h }, () => ({ k: '.' as Kind, a: 0 }));
  return { v: 1, seed, w, h, law, turn: 0, cells, shelf, log: [] };
}

export function clone(s: State): State {
  return { ...s, cells: s.cells.map(c => ({ ...c })), shelf: { ...s.shelf }, log: s.log.slice() };
}

const at = (s: State, x: number, y: number) => s.cells[y * s.w + x];
const inside = (s: State, x: number, y: number) => x >= 0 && y >= 0 && x < s.w && y < s.h;
const empty = (s: State, x: number, y: number) => inside(s, x, y) && at(s, x, y).k === '.';

/** 部品を置く。置けなければ理由を返す */
export function apply(s: State, act: Action): { ok: boolean; events: string[] } {
  if (act.t === 'place') {
    if (!inside(s, act.x, act.y)) return { ok: false, events: ['盤の外'] };
    if (at(s, act.x, act.y).k !== '.') return { ok: false, events: ['もう何かある'] };
    if (s.shelf[act.k] <= 0) return { ok: false, events: [`${KIND_NAME[act.k]}がもうない`] };
    s.shelf[act.k]--;
    s.cells[act.y * s.w + act.x] = { k: act.k, a: 0 };
    s.log.push(act);
    return { ok: true, events: [`${KIND_NAME[act.k]}を(${act.x},${act.y})に置いた`] };
  }
  if (act.t === 'remove') {
    if (!inside(s, act.x, act.y)) return { ok: false, events: ['盤の外'] };
    const c = at(s, act.x, act.y);
    if (c.k === '.') return { ok: false, events: ['何もない'] };
    const k = c.k;
    s.shelf[k]++;
    s.cells[act.y * s.w + act.x] = { k: '.', a: 0 };
    s.log.push(act);
    return { ok: true, events: [`${KIND_NAME[k]}を棚に戻した`] };
  }
  const events = step(s);
  s.log.push(act);
  return { ok: true, events };
}

/** 1手ぶん規則を進める。順番：①火（同時に判定）②重り（下の段から、左から） */
function step(s: State): string[] {
  const ev: string[] = [];
  s.turn++;
  // ① 火：前の盤面を見て、燃え移りを同時に決める
  const before = s.cells.map(c => ({ ...c }));
  const b = (x: number, y: number) => before[y * s.w + x];
  for (let y = 0; y < s.h; y++) for (let x = 0; x < s.w; x++) {
    const c = at(s, x, y);
    if (b(x, y).k === 'F') {
      c.a++;
      if (c.a >= 2) { s.cells[y * s.w + x] = { k: '.', a: 0 }; ev.push(`(${x},${y})の火が消えた`); }
    } else if (b(x, y).k === 'P' && s.law !== 'rain') {
      const near = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => inside(s, x + dx, y + dy) && b(x + dx, y + dy).k === 'F');
      if (near) { s.cells[y * s.w + x] = { k: 'F', a: 0 }; ev.push(`(${x},${y})の板に火が移った`); }
    }
  }
  // ② 重り：下の段から順に。1手で動くのは1回だけ
  const moved = new Set<number>();
  for (let y = s.h - 1; y >= 0; y--) for (let x = 0; x < s.w; x++) {
    const i = y * s.w + x;
    if (s.cells[i].k !== 'W' || moved.has(i)) continue;
    let nx = x, ny = y;
    if (inside(s, x, y + 1) && at(s, x, y + 1).k === 'S') {
      // ばねの上：上へ2マスまで跳ねる
      let up = 0;
      while (up < 2 && empty(s, nx, ny - 1)) { ny--; up++; }
      if (up > 0) ev.push(`(${x},${y})の重りがばねで${up}マス跳ねた`);
    } else if (empty(s, x, y + 1)) {
      ny = y + 1;
      ev.push(`(${x},${y})の重りが落ちた`);
      if (s.law === 'wind' && empty(s, nx + 1, ny)) { nx++; ev.push('大風で東へ流れた'); }
    }
    if (nx !== x || ny !== y) {
      s.cells[ny * s.w + nx] = s.cells[i];
      s.cells[i] = { k: '.', a: 0 };
      moved.add(ny * s.w + nx);
    }
  }
  if (ev.length === 0) ev.push('何も動かなかった');
  return ev;
}

/** 次の1手で変わるマス（盤面の印に使う） */
export function preview(s: State): number[] {
  const t = clone(s);
  apply(t, { t: 'step' });
  const out: number[] = [];
  for (let i = 0; i < s.cells.length; i++) if (s.cells[i].k !== t.cells[i].k) out.push(i);
  return out;
}

/** 盤面の指紋。記録（log）は含めない */
export function fingerprint(s: State): string {
  const board = s.cells.map(c => c.k + c.a).join('');
  return fnv1a([s.v, s.seed, s.w, s.h, s.law, s.turn, board, PLACEABLE.map(k => s.shelf[k]).join(',')].join('|'));
}

/** シードと記録だけから作り直す */
export function replay(seed: string, log: Action[]): State {
  const s = newGame(seed);
  for (const a of log) apply(s, a);
  return s;
}
