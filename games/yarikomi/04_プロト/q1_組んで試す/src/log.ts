// Q1 で見るもの（かかった時間、置き間違いの回数、予行の回数）を端末内に記録する。外へは送らない。
// 保存先：localStorage 'q1.sessions'。メニューの「記録」から見る・書き出す。
import { KNOBS } from './params.ts';

export interface LogEv { t: number; type: string; [k: string]: unknown }
export interface Session {
  id: string; startedAt: string; device: { w: number; h: number; touch: boolean; ua: string };
  knobs: Record<string, unknown>; events: LogEv[]; solvedAt?: number;
}

const KEY = 'q1.sessions';
let cur: Session | null = null;
let t0 = 0;
let saveTimer: number | undefined;

export function now() { return Math.round(performance.now() - t0); }

export function startSession(): Session {
  t0 = performance.now();
  cur = {
    id: new Date().toISOString().replace(/[:.]/g, '-'),
    startedAt: new Date().toISOString(),
    device: { w: innerWidth, h: innerHeight, touch: matchMedia('(pointer: coarse)').matches, ua: navigator.userAgent.slice(0, 120) },
    knobs: { ...KNOBS, SHELF: { ...KNOBS.SHELF } },
    events: [],
  };
  log('start');
  return cur;
}
export function session() { return cur; }

export function log(type: string, data: Record<string, unknown> = {}) {
  if (!cur) return;
  cur.events.push({ t: now(), type, ...data });
  if (type === 'solved' && cur.solvedAt === undefined) cur.solvedAt = now();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 300) as unknown as number;
}

export function save() {
  if (!cur) return;
  try {
    const all = loadAll().filter(s => s.id !== cur!.id);
    all.push(cur);
    localStorage.setItem(KEY, JSON.stringify(all.slice(-30)));
  } catch { /* 保存できない端末ではメモリだけ */ }
}
export function loadAll(): Session[] {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '[]'); } catch { return []; }
}
export function clearAll() { localStorage.removeItem(KEY); }

export interface Summary {
  solved: boolean; solveMs: number | null; totalMs: number;
  msByScreen: Record<string, number>;
  placements: number; mistakes: number; mistakeUndo: number; mistakeMove: number; mistakeRemove: number; dropMiss: number;
  /** ドラッグで、指の下とは違うマス（＝浮かせた部品の下の枠）に置いた回数。決まりどおりなので間違いではない（参考） */
  liftShifted: number;
  trialsEntered: number; trialSteps: number; trialRuns: number; trialResets: number;
  builds: number; challengeStarts: number; confirms: number; deaths: number; retreats: number; losts: number; clears: number;
}

export function summarize(s: Session): Summary {
  const ev = s.events;
  const c = (type: string, f?: (e: LogEv) => boolean) => ev.filter(e => e.type === type && (!f || f(e))).length;
  const msByScreen: Record<string, number> = {};
  let last: { t: number; to: string } | null = null;
  const end = s.solvedAt ?? (ev.length ? ev[ev.length - 1].t : 0);
  for (const e of ev) {
    if (e.type !== 'screen') continue;
    if (e.t > end) break;
    if (last) msByScreen[last.to] = (msByScreen[last.to] ?? 0) + e.t - last.t;
    last = { t: e.t, to: String(e.to) };
  }
  if (last) msByScreen[last.to] = (msByScreen[last.to] ?? 0) + end - last.t;
  const mistakeUndo = c('undo', e => !!e.mistake), mistakeMove = c('move', e => !!e.mistake), mistakeRemove = c('remove', e => !!e.mistake);
  const dropMiss = c('drop-miss');
  return {
    solved: s.solvedAt !== undefined, solveMs: s.solvedAt ?? null, totalMs: ev.length ? ev[ev.length - 1].t : 0, msByScreen,
    placements: c('place'), mistakes: mistakeUndo + mistakeMove + mistakeRemove, mistakeUndo, mistakeMove, mistakeRemove, dropMiss,
    liftShifted: c('place', e => e.via === 'drag' && e.fingerCell !== e.cell),
    trialsEntered: c('screen', e => e.to === 'trial'), trialSteps: c('trial-step'), trialRuns: c('trial-run'), trialResets: c('trial-reset'),
    builds: c('build'), challengeStarts: c('ch-start'), confirms: c('ch-confirm'), deaths: c('ch-death'), retreats: c('ch-retreat'), losts: c('ch-lost'), clears: c('bench-clear'),
  };
}

export function fmtMs(ms: number | null) {
  if (ms === null) return '—';
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}分${String(s % 60).padStart(2, '0')}秒`;
}
