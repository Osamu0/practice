// Q1 のプロトの画面（捨てる前提）。見る → 工房（組む ⇄ 試す）→ 挑む。
import { KNOBS, PARTS, PART_ORDER, P, type PartId } from './params.ts';
import { State, trialMap, benchToTool, type Act, type Dir, type Tool, type Obj, type Ev } from './core.ts';
import { partSVG, leaderSVG, goalSVG, toolSVG } from './art.ts';
import { CHALLENGE } from './challenge.ts';
import { startSession, session, log, now, summarize, fmtMs, loadAll, clearAll, save } from './log.ts';

// ---------- つまみを端末に覚える ----------
const KNOB_KEY = 'q1.knobs';
try { Object.assign(KNOBS, JSON.parse(localStorage.getItem(KNOB_KEY) ?? '{}')); } catch { /* なし */ }
const saveKnobs = () => { try { localStorage.setItem(KNOB_KEY, JSON.stringify({ DRAG_TARGET: KNOBS.DRAG_TARGET, DRAG_LIFT_PX: KNOBS.DRAG_LIFT_PX, GOAL_MUST_STOP: KNOBS.GOAL_MUST_STOP, EXPLAIN_SLIDE_WITH_DOTS: KNOBS.EXPLAIN_SLIDE_WITH_DOTS, TRIAL_CLIFF_COLUMN: KNOBS.TRIAL_CLIFF_COLUMN, STEP_MS: KNOBS.STEP_MS, TRIAL_SHOW_CHALLENGE_TERRAIN: KNOBS.TRIAL_SHOW_CHALLENGE_TERRAIN })); } catch { /* なし */ } };

const $ = (id: string) => document.getElementById(id)!;
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
const N = () => KNOBS.BENCH_SIZE;
const CELL = 48;

type Screen = 'title' | 'look' | 'bench' | 'trial' | 'ch';
interface BenchPart { part: PartId; facing?: Dir; placedAt: number }
type Bench = Map<number, BenchPart>;

type TKind = 'flat' | 'cliff' | 'gap' | 'challenge';
interface Trial { msg?: string; msgL2?: string; kind: TKind; ox: number; base: State; cur: State; turn: number; adds: { type: 'doll' | 'weight'; x: number }[]; armed: 'doll' | 'weight' | null; running: boolean; stop: boolean }
interface Ch { msg?: { html: string; danger: boolean; l2: string }; lost?: string; s: State; card: 'move' | 'place' | 'pick' | null; cands: Act[]; idx: number; act: Act | null; turn: number; tool: Tool | null; over: 'dead' | 'solved' | null }

const app = {
  screen: 'title' as Screen,
  bench: new Map() as Bench,
  hist: [] as { bench: Bench; op: string; cell: number; t: number }[],
  sel: null as number | null,
  armed: null as PartId | null,
  tool: null as Tool | null,
  toolBench: null as Bench | null,
  trial: null as Trial | null,
  ch: null as Ch | null,
  busy: false,
  skip: false,
};
(window as any).__q1 = { app, summary: () => session() && summarize(session()!), KNOBS };

function go(to: Screen) {
  app.screen = to;
  log('screen', { to });
  render();
}

// ---------- 盤面の描き方 ----------
class BoardView {
  el: HTMLDivElement; layer: HTMLDivElement; objs = new Map<number, HTMLDivElement>(); meta = new Map<number, Obj>();
  cols: number; rows: number; cell: number;
  constructor(cols: number, rows: number, cell: number, cls = 'board') {
    this.cols = cols; this.rows = rows; this.cell = cell;
    this.el = document.createElement('div');
    this.el.className = cls;
    this.el.style.width = cols * cell + 'px';
    this.el.style.height = rows * cell + 'px';
    this.layer = document.createElement('div');
    this.layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:3';
  }
  terrain(t: string[] | null) {
    let h = '';
    for (let y = 0; y < this.rows; y++) for (let x = 0; x < this.cols; x++) {
      const g = t && t[y][x] === '#';
      const top = g && (y === 0 || t![y - 1][x] !== '#');
      h += `<div class="cell ${g ? 'ground' : (x + y) % 2 ? 'alt' : ''} ${top ? 'top' : ''}" style="left:${x * this.cell}px;top:${y * this.cell}px;width:${this.cell}px;height:${this.cell}px"></div>`;
    }
    if (t) for (let x = 0; x < this.cols; x++) if (t[this.rows - 1][x] !== '#') h += `<div class="abyss" style="left:${x * this.cell}px;width:${this.cell}px">▼</div>`;
    this.el.innerHTML = h;
    this.el.appendChild(this.layer);
    this.objs.clear();
  }
  svgFor(o: Obj, wear: number, facing?: Dir) {
    return o.kind === 'leader' ? leaderSVG(this.cell, !!o.doll) : partSVG(o.part!, this.cell, facing, wear);
  }
  /** 物を描く。pos がなければ state の位置。ms > 0 なら動かして見せる */
  draw(state: State, pos?: Map<number, { x: number; y: number; wear: number; facing?: Dir }>, ms = 0, ease = 'ease-out') {
    for (const [i, o] of state.objs) this.meta.set(i, { ...o });
    const p = pos ?? new Map([...state.objs].map(([i, o]) => [i, { x: o.x, y: o.y, wear: o.wear, facing: o.facing }]));
    for (const [i, q] of p) {
      const m = this.meta.get(i)!;
      let el = this.objs.get(i);
      const key = `${q.wear}|${q.facing}`;
      if (!el) {
        el = document.createElement('div');
        el.className = 'obj';
        el.dataset.id = String(i);
        el.style.zIndex = m.kind === 'leader' ? '2' : '1';
        this.el.insertBefore(el, this.layer);
        this.objs.set(i, el);
        el.style.transform = `translate(${q.x * this.cell}px,${q.y * this.cell}px)`;
      }
      if (el.dataset.k !== key) { el.innerHTML = this.svgFor(m, q.wear, q.facing); el.dataset.k = key; }
      el.style.transition = ms ? `transform ${ms}ms ${ease}` : 'none';
      el.style.transform = `translate(${q.x * this.cell}px,${q.y * this.cell}px)`;
    }
    for (const [i, el] of [...this.objs]) {
      if (p.has(i)) continue;
      this.objs.delete(i);
      if (ms) {
        el.style.transition = `transform ${ms}ms ease-in, opacity ${ms}ms`;
        const m = /translate\(([-\d.]+)px/.exec(el.style.transform);
        el.style.transform = `translate(${m ? m[1] : 0}px,${(this.rows + 1) * this.cell}px)`;
        el.classList.add('gone');
        setTimeout(() => el.remove(), ms);
      } else el.remove();
    }
  }
  overlay(html: string) { this.layer.innerHTML = html; }
  cellAt(cx: number, cy: number): [number, number] | null {
    const r = this.el.getBoundingClientRect();
    const x = Math.floor((cx - r.left) / this.cell), y = Math.floor((cy - r.top) / this.cell);
    return x >= 0 && y >= 0 && x < this.cols && y < this.rows ? [x, y] : null;
  }
  box(x: number, y: number, cls: string, extra = '') {
    return `<div class="${cls}" style="left:${x * this.cell}px;top:${y * this.cell}px;width:${this.cell}px;height:${this.cell}px;${extra}"></div>`;
  }
}

let view: BoardView | null = null;
let viewFor = '';

async function playStep(v: BoardView, next: State) {
  app.busy = true; app.skip = false;
  for (let k = 1; k < next.snaps.length; k++) {
    if (app.skip) break;
    const st = next.snaps[k].stage;
    v.draw(next, next.snaps[k].objs, KNOBS.STEP_MS, st === '2-5' ? 'ease-in' : st === '2-2' ? 'cubic-bezier(.3,.6,.4,1)' : 'linear');
    if (st === '2-4') {
      const ev = next.events.find(e => e.type === 'slid');
      if (ev) v.overlay(ev.ids.filter(i => next.objs.get(i)?.kind === 'part').map(i => { const o = next.objs.get(i)!; return `<div class="slidemark" style="left:${o.x * v.cell}px;top:${(o.y + 1) * v.cell - 16}px;width:${v.cell}px">${ev.dir! > 0 ? '≫' : '≪'}</div>`; }).join(''));
    }
    await sleep(KNOBS.STEP_MS + KNOBS.GAP_MS);
  }
  v.draw(next);
  app.busy = false;
}

// ---------- 説明の帯 ----------
function dotsTxt(n: number) {
  if (n <= 0) return 'なし';
  const k = Math.min(n, 12);
  let s = '';
  for (let i = 0; i < k; i++) s += (i && i % 3 === 0 ? ' ' : '') + '●';
  return `<span class="dots">${s}${n > 12 ? '+' : ''}</span>`;
}
/** 説明の帯（2行まで）。l2 は2行目（力の比べ・部品の働きなど） */
function band(html: string, danger = false, l2 = '') {
  const b = $('band');
  b.className = danger ? 'danger' : '';
  b.innerHTML = `<div>${danger ? '<span class="tri">▲</span>' : ''}${html}</div>${l2 ? `<div class="l2">${l2}</div>` : ''}`;
}
/** 力の比べ（2行目）。ずれたならその力、ずれないなら当主・人形の乗った組（なければ張り出した組）の余裕 */
function balanceLine(s: State, slid?: Ev): string {
  if (!KNOBS.EXPLAIN_SLIDE_WITH_DOTS) return '';
  const dir = (d: number) => (d > 0 ? '東' : '西');
  if (slid) return `${dir(slid.dir!)}へ倒す ${dotsTxt(slid.m!)} ＞ 戻す ${dotsTxt(slid.r!)}　→ずれる`;
  const bs = s.balances();
  if (!bs.length) return '';
  const riders = [...s.objs].filter(([, o]) => o.kind === 'leader').map(([i]) => i);
  const b = bs.find(b => b.ids.some(i => riders.includes(i))) ?? bs.reduce((a, c) => (c.m > a.m ? c : a));
  if (b.m === b.r) return `${dir(b.dir)}へ倒す ${dotsTxt(b.m)} ＝ 戻す ${dotsTxt(b.r)}　つり合い（あと少しでずれる）`;
  if (b.m < b.r) return `${dir(b.dir)}へ倒す ${dotsTxt(b.m)} ＜ 戻す ${dotsTxt(b.r)}　余裕 ${dotsTxt(b.r - b.m)}`;
  // この手で落ちて止まった組は、この手ではずれない（規則の計算 5.1 決まり2）。次の手でずれる
  if (b.ids.some(i => s.moved.has(i))) return `${dir(b.dir)}へ倒す ${dotsTxt(b.m)} ＞ 戻す ${dotsTxt(b.r)}　次の手でずれる`;
  return `${dir(b.dir)}へ倒す ${dotsTxt(b.m)} ＞ 戻す ${dotsTxt(b.r)}　ふさがれてずれない`;
}
const nameOf = (s: State, ids: number[]) => {
  const ps = ids.map(i => s.objs.get(i) ?? view?.meta.get(i)).filter(Boolean) as Obj[];
  if (ps.some(o => o.kind === 'leader' && !o.doll)) return ps.length > 1 ? '当主を乗せた道具' : '当主';
  if (ps.some(o => o.doll)) return ps.length > 1 ? '人形を乗せた道具' : '人形';
  if (ps.length > 1) return '道具';
  return ps[0] ? PARTS[ps[0].part!].name : '物';
};
function describe(s: State, prev: State, future: boolean): { txt: string; danger: boolean; l2: string } {
  const w = (a: string, b: string) => (future ? b : a);
  const dead = s.events.find(e => e.type === 'death');
  const slid = s.events.find(e => e.type === 'slid');
  if (dead) return { txt: `${future ? 'この手で' : ''}当主が${dead.why}`, danger: true, l2: slid ? balanceLine(s, slid) : '' };
  const abyss = s.events.find(e => e.type === 'abyss');
  const parts: string[] = [];
  if (slid) {
    parts.push(`${nameOf(prev, slid.ids)}が${slid.dir! > 0 ? '東' : '西'}へ${w('ずれた', 'ずれる')}`);
  }
  if (abyss) parts.push(`${nameOf(prev, abyss.ids)}が谷底へ${w('落ちた', '落ちる')}`);
  const doll = s.events.find(e => e.type === 'doll');
  if (doll && !abyss) parts.push(`人形が${doll.why}`);
  const worn = s.events.filter(e => e.type === 'worn' || e.type === 'broken');
  if (worn.length) parts.push(`${nameOf(prev, worn.flatMap(e => e.ids))}が${worn.some(e => e.type === 'broken') ? w('壊れた', '壊れる') : w('傷んだ', '傷む')}`);
  if (s.events.some(e => e.type === 'compressed')) parts.push(`ばねが${w('縮んだ', '縮む')}`);
  if (s.events.some(e => e.type === 'launched')) parts.push(`ばねが${w('打ち出した', '打ち出す')}`);
  if (!parts.length && s.events.some(e => e.type === 'fell')) parts.push(w('落ちて止まった', '落ちて止まる'));
  return { txt: parts.join('　') || w('何も動かない', '何も動かない'), danger: false, l2: balanceLine(s, slid) };
}

// ---------- 上の帯 ----------
function miniChallenge() {
  const c = 5;
  let h = `<div style="position:relative;width:${7 * c}px;height:${7 * c}px;border:1px solid var(--kei)">`;
  CHALLENGE.map.forEach((r, y) => [...r].forEach((ch, x) => { if (ch === '#') h += `<div style="position:absolute;left:${x * c}px;top:${y * c}px;width:${c}px;height:${c}px;background:var(--shizu)"></div>`; }));
  h += `<div style="position:absolute;left:${CHALLENGE.goal[0] * c}px;top:${CHALLENGE.goal[1] * c}px;width:${c}px;height:${c}px;background:var(--taikou)"></div>`;
  h += `<div style="position:absolute;left:${CHALLENGE.leader[0] * c}px;top:${CHALLENGE.leader[1] * c}px;width:${c}px;height:${c}px;background:var(--yamabuki)"></div></div>`;
  return h;
}
function renderTop() {
  const label = { title: 'Q1 プロト', look: '見る', bench: '工房：組む', trial: '工房：試す', ch: '挑む' }[app.screen];
  $('top').innerHTML = `<span class="mode">${label}</span><span>課題「${CHALLENGE.name}」</span><span class="mini">${app.screen === 'bench' || app.screen === 'trial' ? miniChallenge() : ''}</span>`;
}

// ---------- 描く（画面ごと） ----------
function render() {
  renderTop();
  const s = app.screen;
  if (s === 'title') return renderTitle();
  if (s === 'look') return renderLook();
  if (s === 'bench') return renderBench();
  if (s === 'trial') return renderTrial();
  if (s === 'ch') return renderCh();
}

function setView(key: string, mk: () => BoardView) {
  if (viewFor !== key || !view) { view = mk(); viewFor = key; }
  const stage = $('stage');
  if (view.el.parentElement !== stage) { stage.innerHTML = ''; stage.appendChild(view.el); }
  stage.querySelectorAll('.overlay').forEach(e => e.remove());
  return view;
}

function thumb(html: string) { $('thumb').innerHTML = html; }
function hand(html: string) { $('hand').innerHTML = html; }

function renderTitle() {
  viewFor = ''; view = null;
  $('stage').innerHTML = `<div class="title"><h1>組んで試す（Q1 プロト）</h1>
    <p>崖の先の印まで行こう。<br>工房で道具を組み、試してから挑む。<br>親指だけで遊べます。</p>
    <p class="hint">捨てる前提の試作。絵と音は仮です</p></div>`;
  band('「はじめる」で記録を始めます（端末の中だけ）');
  hand(`<div class="hint">記録は メニュー（≡）→「記録」で見られます</div>`);
  thumb(`<button class="menu" data-a="menu">≡</button><button class="main" data-a="start">はじめる</button>`);
}

// 見る
function challengeState(): State {
  const s = new State(CHALLENGE.map);
  s.add({ kind: 'leader', x: CHALLENGE.leader[0], y: CHALLENGE.leader[1] });
  s.goal = [...CHALLENGE.goal];
  s.goalMustStop = KNOBS.GOAL_MUST_STOP;
  return s;
}
function goalHTML(v: BoardView) { return `<div class="goal" style="left:${CHALLENGE.goal[0] * v.cell}px;top:${CHALLENGE.goal[1] * v.cell}px">${goalSVG(v.cell)}</div>`; }
function renderLook() {
  const v = setView('look', () => { const b = new BoardView(7, 7, CELL); b.terrain(CHALLENGE.map); return b; });
  v.draw(challengeState());
  v.overlay(goalHTML(v));
  band(KNOBS.GOAL_MUST_STOP ? '崖の先の印に立って、止まれたら解ける' : '崖の先の印に立てば解ける');
  hand(app.tool
    ? `<div class="row" style="align-items:center"><div style="flex:0 0 auto">持っている道具：</div><div style="flex:1 1 auto;display:flex;justify-content:center">${toolSVG(app.tool as any, 22)}</div></div><div class="hint">「工房へ」で道具をばらして組み直せる</div>`
    : `<div class="hint">道具を持っていない。「工房へ」で組む</div>`);
  thumb(`<button data-a="toBench">工房へ</button><button class="main" data-a="challenge">挑む</button><button class="menu" data-a="menu">≡</button>`);
}

// 工房：組む
function shelfLeft(p: PartId) {
  let used = 0;
  for (const b of app.bench.values()) if (b.part === p) used++;
  return KNOBS.SHELF[p] - used;
}
function benchHTML(v: BoardView) {
  let h = '';
  const n = N();
  for (const [c, b] of app.bench) {
    const x = c % n, y = Math.floor(c / n);
    if (app.sel === c) h += v.box(x, y, 'selbox');
    h += `<div class="obj" style="transform:translate(${x * v.cell}px,${y * v.cell}px)">${partSVG(b.part, v.cell, b.facing)}</div>`;
  }
  // 結び目：隣どうしで、向かい合う辺の両方につなぎ点があるとき（core の conn と同じ決め）
  const tool = benchCells();
  const s = new State(Array(n).fill('.'.repeat(n)));
  s.placeTool(benchToTool(tool), 0, 0);
  const mx = Math.min(...tool.map(t => t.x)), my = Math.min(...tool.map(t => t.y));
  for (const l of s.links) {
    const [a, b] = l.split(',').map(Number);
    const oa = s.objs.get(a)!, ob = s.objs.get(b)!;
    const cx = ((oa.x + ob.x) / 2 + mx + .5) * v.cell, cy = ((oa.y + ob.y) / 2 + my + .5) * v.cell;
    h += `<div class="knot" style="left:${cx}px;top:${cy}px"></div>`;
  }
  return h;
}
function benchCells() {
  const n = N();
  return [...app.bench].map(([c, b]) => ({ x: c % n, y: Math.floor(c / n), part: b.part, facing: b.facing }));
}
function renderBench() {
  const n = N();
  const v = setView('bench' + n, () => { const b = new BoardView(n, n, KNOBS.BENCH_FRAME_PX / n, 'board bench'); b.terrain(null); return b; });
  v.overlay(benchHTML(v));
  if (app.sel !== null && app.bench.has(app.sel)) {
    const b = app.bench.get(app.sel)!, d = PARTS[b.part];
    band(`${d.name}（${d.family}・${d.material}）重さ${dotsTxt(d.weight)}${d.springPower ? '　もう一度タップで向き' : ''}`, false, d.does);
  } else if (app.armed) band(`${PARTS[app.armed].name}を置くマスをタップ`, false, PARTS[app.armed].does);
  else band('棚の部品を作業台へ（ドラッグかタップ）');
  hand(`<div class="shelf">${PART_ORDER.map(p => {
    const left = shelfLeft(p);
    return `<div class="tile ${left <= 0 ? 'zero' : ''} ${app.armed === p ? 'sel' : ''}" data-part="${p}">${partSVG(p, 36, 'up')}<span class="nm">${PARTS[p].name}<small>×${left}</small></span></div>`;
  }).join('')}</div>`);
  const empty = app.bench.size === 0;
  thumb(`<button data-a="undo" ${app.hist.length ? '' : 'disabled'}>ひとつ戻す</button><button data-a="toTrial" ${empty ? 'disabled' : ''}>試す</button><button class="main" data-a="build" ${empty ? 'disabled' : ''}>組み上げる</button><button class="menu" data-a="menu">≡</button>`);
}

// 工房：試す
function benchTool(): Tool { return benchToTool(benchCells()); }
function trialTerrain(kind: TKind) { return kind === 'challenge' ? CHALLENGE.map : trialMap(kind, KNOBS.TRIAL_CLIFF_COLUMN); }
/** 道具を ox の列で、上からおろして止まる高さ（入らなければ null） */
function restY(s: State, tool: Tool, ox: number): number | null {
  const occ = s.occ();
  const fits = (oy: number) => tool.every(([dx, dy]) => s.free(ox + dx, oy + dy, occ));
  if (!fits(0)) return null;
  let oy = 0;
  while (fits(oy + 1)) oy++;
  return oy;
}
function trialBase(kind: TKind, ox: number, adds: Trial['adds']): State {
  const s = new State(trialTerrain(kind));
  const tool = benchTool();
  s.placeTool(tool, ox, restY(s, tool, ox) ?? 0, false);
  for (const a of adds) addTrialThing(s, a.type, a.x);
  return s;
}
function addTrialThing(s: State, type: 'doll' | 'weight', x: number): boolean {
  const occ = s.occ();
  if (type === 'weight') {
    if (!s.free(x, 0, occ)) return false;
    s.add({ kind: 'part', part: 'stoneWeight', x, y: 0 });
    return true;
  }
  let y = 0;
  while (y < s.H && s.free(x, y, occ)) y++;
  const ty = y >= s.H ? 0 : y - 1;
  if (ty < 0 || !s.free(x, ty, occ)) return false;
  s.add({ kind: 'leader', x, y: ty, doll: true });
  return true;
}
function startTrial() {
  let kind: TKind = app.trial?.kind ?? KNOBS.TRIAL_START_TERRAIN;
  if (kind === 'challenge' && !KNOBS.TRIAL_SHOW_CHALLENGE_TERRAIN) kind = 'cliff';
  const tool = benchTool();
  const w = Math.max(...tool.map(c => c[0])) + 1;
  let ox = Math.min(P['trial.startColumn'], 7 - w);
  const probe = new State(trialTerrain(kind));
  while (ox > 0 && restY(probe, tool, ox) === null) ox--;
  const base = trialBase(kind, ox, []);
  app.trial = { kind, ox, base, cur: base.copy(), turn: 0, adds: [], armed: null, running: false, stop: false };
  viewFor = '';
}
function trialPreview(t: Trial, v: BoardView) {
  const n = t.cur.do({ t: 'wait' })!;
  let h = '';
  for (const [i, o] of n.objs) {
    const p = t.cur.objs.get(i)!;
    if (p.x !== o.x || p.y !== o.y) h += `<div class="ghost" style="transform:translate(${o.x * v.cell}px,${o.y * v.cell}px)">${v.svgFor(o, o.wear, o.facing)}</div>`;
  }
  return { h, n };
}
function renderTrial() {
  const t = app.trial!;
  const v = setView('trial' + t.kind + KNOBS.TRIAL_CLIFF_COLUMN, () => { const b = new BoardView(7, 7, CELL); b.terrain(t.base.terrain); return b; });
  v.draw(t.cur);
  const pv = trialPreview(t, v);
  v.overlay(pv.h);
  const hasSpring = [...t.cur.objs.values()].some(o => o.kind === 'part' && PARTS[o.part!].springPower);
  if (t.armed === 'doll') band('人形を置く列をタップ（その列のいちばん上に立つ）', false, '人形は当主と同じ重さ');
  else if (t.armed === 'weight') band('重りを落とす列をタップ（上から落ちる）', false, hasSpring ? 'ばねの真上の列に落とすと、ばねが縮んで次の手で打ち出す' : '石の重りと同じ重さ');
  else if (!t.running) {
    const d = describe(pv.n, t.cur, true);
    if (t.msg) band(t.msg, false, t.msgL2 ?? '');
    else if (t.turn === 0 && !t.adds.length) band('人形を乗せる・重りを落として「送る」で1手ずつ', false, hasSpring ? 'ばねは上から物が落ちると縮む。「重り落とし」で試せる' : d.l2);
    else band(`次：${d.txt}`, d.danger, d.l2);
  }
  const t0 = t.turn === 0;
  hand(`<div class="row"><button data-a="tDoll" class="${t.armed === 'doll' ? 'sel' : ''}">人形</button><button data-a="tWeight" class="${t.armed === 'weight' ? 'sel' : ''}">重り落とし</button>
      <button data-a="tLeft" ${t0 ? '' : 'disabled'} aria-label="道具を西へ">◀ 道具</button><button data-a="tRight" ${t0 ? '' : 'disabled'} aria-label="道具を東へ">道具 ▶</button></div>
    <div class="chips">${(['flat', 'cliff', 'gap', 'challenge'] as const).filter(k => k !== 'challenge' || KNOBS.TRIAL_SHOW_CHALLENGE_TERRAIN).map(k => `<button data-a="tTerrain" data-k="${k}" class="${t.kind === k ? 'sel' : ''}" ${t0 ? '' : 'disabled'}>${{ flat: '平ら', cliff: '崖', gap: '割れ目', challenge: '課題の形' }[k]}</button>`).join('')}</div>`);
  thumb(`<button data-a="toBench2">組む</button><button data-a="tReset" ${t0 && !t.adds.length ? 'disabled' : ''}>最初へ</button><button class="main" data-a="tStep">送る</button><button data-a="tRun">続けて</button>`);
}

// 挑む
function startCh() {
  const s = challengeState();
  if (app.tool) s.inv = [app.tool.map(c => [...c] as any)];
  app.ch = { s, card: null, cands: [], idx: 0, act: null, turn: 0, tool: app.tool, over: null };
  app.tool = null;
  viewFor = '';
  log('ch-start', { tool: s.inv[0] ?? null });
  go('ch');
}
function actTargets(s: State, a: Act): [number, number][] {
  const L = s.leader() !== null ? s.objs.get(s.leader()!)! : null;
  if (!L) return [];
  if (a.t === 'enter' || a.t === 'push') return [[L.x + a.d, L.y]];
  if (a.t === 'climb') { const d = s.climbDest(a.d); return d ? [d] : []; }
  if (a.t === 'place') return s.inv[a.tool].map(([dx, dy]) => [a.ox + dx, a.oy + dy] as [number, number]);
  if (a.t === 'pick') return a.ids.map(i => [s.objs.get(i)!.x, s.objs.get(i)!.y] as [number, number]);
  return [[L.x, L.y]];
}
const actName = (a: Act) => a.t === 'wait' ? '待つ' : a.t === 'place' ? '置く' : a.t === 'pick' ? '拾う' : `${a.d > 0 ? '→' : '←'} ${{ enter: '入る', climb: '登る', push: '押す' }[a.t]}`;
function renderCh() {
  const c = app.ch!;
  const v = setView('ch', () => { const b = new BoardView(7, 7, CELL); b.terrain(CHALLENGE.map); return b; });
  if (!app.busy) v.draw(c.s);
  const act: Act = c.act ?? { t: 'wait' };
  let danger = false;
  let ov = goalHTML(v);
  if (!c.over && !app.busy) {
    const n = c.s.do(act);
    if (n) {
      const placing = c.act?.t === 'place' ? c.act : null;
      if (placing) for (const [dx, dy, part, f] of c.s.inv[placing.tool]) ov += `<div class="placing" style="transform:translate(${(placing.ox + dx) * v.cell}px,${(placing.oy + dy) * v.cell}px)">${partSVG(part, v.cell, f ?? undefined)}</div>`;
      for (const [i, o] of n.objs) {
        const p = c.s.objs.get(i);
        if (placing && !p) { ov += `<div class="landing" style="transform:translate(${o.x * v.cell}px,${o.y * v.cell}px)">${v.svgFor(o, o.wear, o.facing)}</div>`; continue; }
        if (!p || p.x !== o.x || p.y !== o.y) {
          if (o.kind === 'leader') ov += `<div class="ring" style="left:${o.x * v.cell + 4}px;top:${o.y * v.cell + 4}px;width:${v.cell - 8}px;height:${v.cell - 8}px"></div>`;
          ov += `<div class="ghost" style="transform:translate(${o.x * v.cell}px,${o.y * v.cell}px)">${v.svgFor(o, o.wear, o.facing)}</div>`;
        }
      }
      const li = c.s.leader()!;
      if (n.dead) { danger = true; const L = c.s.objs.get(li)!; const e = n.snaps[n.snaps.length - 1].objs.get(li); ov += v.box(e?.x ?? L.x, Math.min(e?.y ?? L.y, 6), 'dangerc'); }
      for (const e of n.events.filter(e => e.type === 'worn' || e.type === 'broken')) for (const i of e.ids) { const o = c.s.objs.get(i); if (o) ov += v.box(o.x, o.y, 'dangerc'); }
      // 置く・拾うの候補は、選んでいる1つだけを描く（重なって読めないため。ほかは「前・次」で送る）
      if (c.card === 'move') for (const a of c.cands) for (const [x, y] of actTargets(c.s, a)) ov += v.box(x, y, 'cand', a === c.act ? 'border-style:solid' : 'border-style:dotted;opacity:.7');
      if (c.card === 'pick' && c.act) for (const [x, y] of actTargets(c.s, c.act)) ov += v.box(x, y, 'cand');
      const d = describe(n, c.s, true);
      const solved = n.solved();
      if (c.lost && !c.act) band(`外れた：${c.lost}`, true, '「引き返して組み直す」で工房へ（何も失わない）');
      else if (!c.act && c.msg) band(c.msg.html, c.msg.danger, c.msg.l2);
      else band(c.act ? `${actName(c.act)}：${solved ? 'この手で解ける' : d.txt}` : `待つなら：${d.txt}`, d.danger, d.l2);
    }
  }
  v.overlay(ov);
  if (c.over) {
    const sm = summarize(session()!);
    const o = document.createElement('div');
    o.className = 'overlay';
    o.innerHTML = c.over === 'solved'
      ? `<h2>解けた</h2><p>はじめてから ${fmtMs(sm.solveMs)}</p><p class="hint">試した回数 ${sm.trialsEntered}・置き間違い ${sm.mistakes}・挑んだ回数 ${sm.challengeStarts}</p>`
      : `<h2>当主が${c.s.dead}</h2><p>見るへ戻って組み直せる（プロトでは何も失わない）</p>`;
    $('stage').appendChild(o);
    band(c.over === 'solved' ? 'よし！' : '外れた。どこがずれたかを工房で試そう', c.over === 'dead');
    hand(`<div class="hint">${c.over === 'solved' ? '記録はメニュー（≡）→「記録」' : ''}</div>`);
    thumb(c.over === 'solved'
      ? `<button data-a="showLog">記録を見る</button><button class="main" data-a="again">もう一度（新しい記録）</button><button class="menu" data-a="menu">≡</button>`
      : `<button class="main" data-a="backLook">見るへ戻る</button><button class="menu" data-a="menu">≡</button>`);
    return;
  }
  const L = c.s.leader();
  const acts = c.s.actions();
  const has = (t: string) => acts.some(a => (t === 'move' ? ['enter', 'climb', 'push'].includes(a.t) : a.t === t));
  let row2 = c.lost
    ? `<div class="row"><button class="sel" data-a="retreat">引き返して組み直す</button></div>`
    : `<div class="row" style="align-items:center"><div class="hint" style="flex:1 1 auto">手を選ぶ（盤面のマスでもよい）</div><button data-a="retreat" style="flex:0 0 auto">引き返す</button></div>`;
  if (c.card === 'move') row2 = `<div class="row">${c.cands.map((a, k) => `<button data-a="cand" data-k="${k}" class="${a === c.act ? 'sel' : ''}">${actName(a)}</button>`).join('')}</div>`;
  else if (c.card === 'place' || c.card === 'pick') row2 = `<div class="row"><button data-a="candPrev">◀ 前</button><button class="sel" style="flex:0 0 64px">${c.idx + 1}/${c.cands.length}</button><button data-a="candNext">次 ▶</button></div>`;
  hand(`<div class="row">${(['move', 'place', 'pick'] as const).map(k => `<button data-a="card" data-k="${k}" class="${c.card === k ? 'sel' : ''}" ${L !== null && has(k === 'move' ? 'move' : k) ? '' : 'disabled'}>${{ move: '進む', place: '置く', pick: '拾う' }[k]}</button>`).join('')}<button data-a="wait" class="${c.act?.t === 'wait' ? 'sel' : ''}">待つ</button></div>${row2}`);
  thumb(`<button data-a="reselect" ${c.act ? '' : 'disabled'}>選び直す</button><button class="main ${danger ? 'danger' : ''}" data-a="confirm" ${c.act && !app.busy ? '' : 'disabled'}>${danger ? '！確定' : '確定'}</button><button class="menu" data-a="menu">≡</button>`);
}

// ---------- 操作 ----------
function pushHist(op: string, cell: number) {
  app.hist.push({ bench: new Map([...app.bench].map(([k, v]) => [k, { ...v }])), op, cell, t: now() });
}
function placeOnBench(part: PartId, cell: number, via: string, fingerCell: number) {
  if (shelfLeft(part) <= 0) { band(`${PARTS[part].name}は棚にもうない`); log('drop-miss', { reason: 'none-left', part }); return; }
  if (app.bench.has(cell)) { band('そこには置けない（部品がある）'); log('drop-miss', { reason: 'occupied', part, cell, via }); return; }
  pushHist('place', cell);
  app.bench.set(cell, { part, facing: PARTS[part].springPower ? 'up' : undefined, placedAt: now() });
  app.sel = cell;
  log('place', { part, cell, fingerCell, via });
  if (shelfLeft(part) <= 0 && app.armed === part) app.armed = null;
  render();
}
function quick(b: BenchPart) { return now() - b.placedAt < KNOBS.MISTAKE_WINDOW_MS; }
function moveOnBench(from: number, to: number, fingerCell: number) {
  if (from === to) { render(); return; }
  if (app.bench.has(to)) { band('そこには置けない（部品がある）'); log('drop-miss', { reason: 'occupied', cell: to, via: 'move' }); render(); return; }
  const b = app.bench.get(from)!;
  pushHist('move', from);
  log('move', { part: b.part, from, to, fingerCell, mistake: quick(b) });
  app.bench.delete(from);
  app.bench.set(to, { ...b, placedAt: now() });
  app.sel = to;
  render();
}
function removeFromBench(cell: number) {
  const b = app.bench.get(cell)!;
  pushHist('remove', cell);
  log('remove', { part: b.part, cell, mistake: quick(b) });
  app.bench.delete(cell);
  app.sel = null;
  render();
}
function tapBench(cell: number) {
  const b = app.bench.get(cell);
  if (app.armed) {
    if (b) { band('そこには置けない（部品がある）'); log('drop-miss', { reason: 'occupied', cell, via: 'tap' }); return; }
    placeOnBench(app.armed, cell, 'tap', cell);
    return;
  }
  if (!b) { app.sel = null; render(); return; }
  if (app.sel === cell && PARTS[b.part].springPower) {
    pushHist('rotate', cell);
    const order: Dir[] = ['up', 'east', 'down', 'west'];
    b.facing = order[(order.indexOf(b.facing ?? 'up') + 1) % 4];
    log('rotate', { cell, facing: b.facing });
  } else { app.sel = cell; log('select', { cell }); }
  render();
}

async function trialStep(t: Trial, v: BoardView) {
  const n = t.cur.do({ t: 'wait' })!;
  t.armed = null;
  const prev = t.cur;
  t.cur = n; t.turn++;
  t.running = true;
  const d = describe(n, prev, false);
  t.msg = `${t.turn}手目：${d.txt}`;
  t.msgL2 = d.l2;
  band(t.msg, false, t.msgL2);
  await playStep(v, n);
  t.running = false;
  return n.events.length > 0;
}

const handlers: Record<string, (el: HTMLElement) => void | Promise<void>> = {
  start() { startSession(); app.bench.clear(); app.hist = []; app.tool = null; app.toolBench = null; app.sel = null; app.armed = null; app.trial = null; go('look'); },
  menu() { openMenu(); },
  toBench() {
    if (app.tool && app.toolBench) { app.bench = app.toolBench; app.tool = null; app.toolBench = null; app.hist = []; log('disassemble'); }
    go('bench');
  },
  challenge() { startCh(); },
  undo() {
    const h = app.hist.pop();
    if (!h) return;
    const placed = app.bench.get(h.cell);
    log('undo', { op: h.op, mistake: h.op === 'place' && now() - h.t < KNOBS.MISTAKE_WINDOW_MS, part: placed?.part });
    app.bench = h.bench; app.sel = null;
    render();
  },
  toTrial() { app.armed = null; app.sel = null; startTrial(); go('trial'); },
  build() {
    app.tool = benchTool(); app.toolBench = app.bench; app.bench = new Map(); app.hist = []; app.sel = null; app.armed = null;
    log('build', { tool: app.tool });
    go('look');
  },
  toBench2() { if (app.trial?.running) { app.trial.stop = true; app.skip = true; } go('bench'); },
  tDoll() { const t = app.trial!; t.armed = t.armed === 'doll' ? null : 'doll'; render(); },
  tWeight() { const t = app.trial!; t.armed = t.armed === 'weight' ? null : 'weight'; render(); },
  tLeft() { shiftTrial(-1); },
  tRight() { shiftTrial(1); },
  tTerrain(el) { const t = app.trial!; t.msg = undefined; t.kind = el.dataset.k as Trial['kind']; t.base = trialBase(t.kind, t.ox, t.adds); t.cur = t.base.copy(); log('trial-terrain', { kind: t.kind }); render(); },
  tReset() { const t = app.trial!; t.msg = undefined; if (t.running) { t.stop = true; app.skip = true; } t.adds = t.turn === 0 ? [] : t.adds; t.base = trialBase(t.kind, t.ox, t.adds); t.cur = t.base.copy(); t.turn = 0; log('trial-reset'); render(); },
  async tStep() {
    const t = app.trial!;
    if (t.running || app.busy) return;
    log('trial-step', { turn: t.turn + 1 });
    await trialStep(t, view!);
    render();
  },
  async tRun() {
    const t = app.trial!;
    if (t.running || app.busy) return;
    log('trial-run', { from: t.turn });
    t.stop = false;
    while (!t.stop && t.turn < P['trial.maxTurns'] && app.screen === 'trial') {
      const moved = await trialStep(t, view!);
      if (!moved) { t.msg = `${t.turn}手目で止まった（何も動かない）`; break; }
    }
    if (app.screen === 'trial') render();
  },
  card(el) {
    const c = app.ch!;
    const k = el.dataset.k as Ch['card'];
    const acts = c.s.actions();
    c.card = k;
    c.cands = acts.filter(a => k === 'move' ? ['enter', 'climb', 'push'].includes(a.t) : a.t === k);
    c.idx = 0;
    c.act = c.cands.length && k !== 'move' ? c.cands[0] : (c.cands.length === 1 ? c.cands[0] : null);
    render();
  },
  cand(el) { const c = app.ch!; c.act = c.cands[Number(el.dataset.k)]; render(); },
  candPrev() { const c = app.ch!; c.idx = (c.idx + c.cands.length - 1) % c.cands.length; c.act = c.cands[c.idx]; render(); },
  candNext() { const c = app.ch!; c.idx = (c.idx + 1) % c.cands.length; c.act = c.cands[c.idx]; render(); },
  wait() { const c = app.ch!; c.card = null; c.cands = []; c.act = { t: 'wait' }; render(); },
  reselect() { const c = app.ch!; c.card = null; c.cands = []; c.act = null; render(); },
  async confirm() {
    const c = app.ch!;
    if (!c.act || app.busy) return;
    const n = c.s.do(c.act);
    if (!n) return;
    c.turn++;
    log('ch-confirm', { turn: c.turn, act: c.act.t, d: (c.act as any).d, dead: n.dead, solved: n.solved() });
    const d = describe(n, c.s, false);
    c.s = n; c.act = null; c.card = null; c.cands = [];
    c.msg = { html: `${c.turn}手目：${n.dead ? '当主が' + n.dead : d.txt}`, danger: !!n.dead, l2: d.l2 };
    band(c.msg.html, c.msg.danger, c.msg.l2);
    thumb(`<button disabled>選び直す</button><button class="main" disabled>確定</button><button class="menu" disabled>≡</button>`);
    view!.overlay(goalHTML(view!));
    await playStep(view!, n);
    if (n.dead) { c.over = 'dead'; log('ch-death', { why: n.dead, turn: c.turn }); }
    else if (n.solved()) { c.over = 'solved'; log('solved', { turn: c.turn }); save(); }
    else if (!c.lost) {
      // 外れた：道具の部品が谷底へ落ちた、または待つしかできない。そのうえで、この先 8 手で解ける手が見つからないとき
      const fellAway = n.events.some(e => e.type === 'abyss');
      const stuck = n.actions().every(a => a.t === 'wait');
      if (fellAway || stuck) {
        const r = n.canStillSolve();
        if (r !== 'yes') { c.lost = fellAway ? '道具が谷底へ落ちた。もう解けない' : 'もう動けない'; log('ch-lost', { why: c.lost, turn: c.turn, search: r }); }
      }
    }
    render();
  },
  backLook() { const c = app.ch!; app.tool = c.tool; app.ch = null; go('look'); },
  retreat() {
    const c = app.ch!;
    log('ch-retreat', { turn: c.turn, lost: !!c.lost });
    app.tool = c.tool; app.ch = null;
    handlers.toBench(document.body); // 道具をばらして作業台へ（組み直す）
  },
  again() { handlers.start(document.body); },
  showLog() { openLog(); },
};

function shiftTrial(dx: number) {
  const t = app.trial!;
  t.msg = undefined;
  const tool = benchTool();
  const w = Math.max(...tool.map(c => c[0])) + 1;
  const nx = t.ox + dx;
  if (nx < 0 || nx + w > 7) return;
  t.ox = nx;
  t.base = trialBase(t.kind, t.ox, t.adds);
  t.cur = t.base.copy();
  log('trial-shift', { ox: t.ox });
  render();
}

// ---------- メニュー・記録・つまみ ----------
function sheet(html: string) {
  const s = $('sheet');
  // 見出しと「閉じる」は上に固定（長い記録でも画面の中にある）
  const h = html.replace(/<h2>(.*?)<\/h2>/, '<div class="head"><h2>$1</h2><button data-m="close">閉じる</button></div>');
  s.innerHTML = `<div class="panel">${h}</div>`;
  s.hidden = false;
}
function closeSheet() { $('sheet').hidden = true; }
function openMenu() {
  const scr = app.screen;
  sheet(`<h2>メニュー</h2>
    ${scr === 'bench' || scr === 'trial' ? '<button data-m="look">課題を見る</button>' : ''}
    ${scr === 'bench' && app.bench.size ? '<button data-m="clear-bench">作業台をまっさらにする（ひとつ戻すで戻せる）</button>' : ''}
    ${scr === 'ch' && app.ch && !app.ch.over ? '<button data-m="retreat">引き返して組み直す</button>' : ''}
    <button data-m="log">記録（かかった時間・置き間違い・予行の回数）</button>
    <button data-m="knobs">つまみ（プレイテスト用）</button>
    <button data-m="restart">はじめから（新しい記録）</button>
    <button data-m="close" class="main">閉じる</button>`);
}
function row(k: string, v: string | number) { return `<tr><td>${k}</td><td>${v}</td></tr>`; }
function openLog() {
  const s = session();
  const all = loadAll();
  const sm = s ? summarize(s) : null;
  const scr = sm ? sm.msByScreen : {};
  sheet(`<h2>記録（端末の中だけ）</h2>
    ${sm ? `<table>
      ${row('解けたか', sm.solved ? 'はい' : 'まだ')}${row('はじめてから解けるまで', fmtMs(sm.solveMs))}${row('今の記録の長さ', fmtMs(sm.totalMs))}
      ${row('　見る', fmtMs(scr.look ?? 0))}${row('　組む', fmtMs(scr.bench ?? 0))}${row('　試す', fmtMs(scr.trial ?? 0))}${row('　挑む', fmtMs(scr.ch ?? 0))}
      ${row('置いた回数', sm.placements)}${row('置き間違い（合計）', sm.mistakes)}
      ${row('　置いてすぐ「ひとつ戻す」', sm.mistakeUndo)}${row('　置いてすぐ動かした', sm.mistakeMove)}${row('　置いてすぐ棚に戻した', sm.mistakeRemove)}
      ${row('置けなかった（部品のあるマス・外で離した）', sm.dropMiss)}${row('作業台をまっさらにした', sm.clears)}
      ${row('予行：試し場を開いた', sm.trialsEntered)}${row('予行：送る（1手）', sm.trialSteps)}${row('予行：続けて動かす', sm.trialRuns)}${row('予行：最初に戻す', sm.trialResets)}
      ${row('組み上げた', sm.builds)}${row('挑んだ', sm.challengeStarts)}${row('確定した手', sm.confirms)}${row('当主が死んだ', sm.deaths)}${row('外れた（もう解けない）', sm.losts)}${row('引き返した', sm.retreats)}
    </table>` : '<p>まだ記録がない（タイトルの「はじめる」から）</p>'}
    <p class="small">置き間違い＝置いてから ${KNOBS.MISTAKE_WINDOW_MS / 1000} 秒以内に「ひとつ戻す」・動かす・棚に戻した回数（目安）。置く先は、ドラッグなら枠が出たマス（今の決まり：${KNOBS.DRAG_TARGET === 'ghost' ? '指の上' : '指の下'}）、タップなら指の下。枠どおりに置けたものは数えない。この端末の記録：${all.length} 件</p>
    <div class="row"><button data-m="copy">書き出す（文字）</button><button data-m="dl">ファイルに保存</button></div>
    <textarea id="logtext" readonly></textarea>
    <div class="row"><button data-m="clear">この端末の記録を消す</button><button data-m="close" class="main">閉じる</button></div>`);
}
function exportText() {
  const all = loadAll();
  return JSON.stringify({ app: 'yarikomi-q1-proto', exportedAt: new Date().toISOString(), sessions: all.map(s => ({ ...s, summary: summarize(s) })) }, null, 1);
}
const KNOB_UI: [keyof typeof KNOBS, string, (string | number | boolean)[]][] = [
  ['DRAG_TARGET', 'ドラッグで置くマス', ['ghost', 'finger']],
  ['TRIAL_SHOW_CHALLENGE_TERRAIN', '試し場に「課題の形」を出す', [true, false]],
  ['DRAG_LIFT_PX', '指の上に浮かせる（px）', [0, 40, 56, 72]],
  ['GOAL_MUST_STOP', '印の上で止まるまで求める', [true, false]],
  ['EXPLAIN_SLIDE_WITH_DOTS', 'ずれたときに力の丸を出す', [true, false]],
  ['TRIAL_CLIFF_COLUMN', '試し場の崖の縁の列', [2, 3, 4]],
  ['STEP_MS', '1段の再生（ms）', [100, 200, 300, 500]],
];
function openKnobs() {
  const show = (v: unknown) => v === true ? 'する' : v === false ? 'しない' : v === 'ghost' ? '指の上' : v === 'finger' ? '指の下' : String(v);
  sheet(`<h2>つまみ</h2><p class="small">タップで値が変わる。変えると記録に残る。値は src/params.ts の KNOBS</p>
    ${KNOB_UI.map(([k, label]) => `<label>${label}<button data-m="knob" data-k="${k}" style="min-width:96px">${show(KNOBS[k])}</button></label>`).join('')}
    <button data-m="close" class="main">閉じる</button>`);
}
function setKnob(k: keyof typeof KNOBS) {
  const vals = KNOB_UI.find(u => u[0] === k)![2];
  const v = vals[(vals.findIndex(x => String(x) === String(KNOBS[k])) + 1) % vals.length];
  (KNOBS as any)[k] = v;
  saveKnobs();
  log('knob', { k, v });
  if (app.ch) app.ch.s.goalMustStop = KNOBS.GOAL_MUST_STOP;
  if (app.trial && k === 'TRIAL_CLIFF_COLUMN') { app.trial.base = trialBase(app.trial.kind, app.trial.ox, app.trial.adds); app.trial.cur = app.trial.base.copy(); app.trial.turn = 0; }
  render();
  openKnobs();
}
function sheetTap(target: HTMLElement) {
  const b = target.closest('[data-m]') as HTMLElement | null;
  if (!b) { if (target === $('sheet')) closeSheet(); return; }
  const m = b.dataset.m;
  if (m === 'close') closeSheet();
  else if (m === 'log') openLog();
  else if (m === 'knobs') openKnobs();
  else if (m === 'knob') setKnob(b.dataset.k as keyof typeof KNOBS);
  else if (m === 'look') { closeSheet(); go('look'); }
  else if (m === 'clear-bench') { closeSheet(); pushHist('clear', -1); log('bench-clear', { n: app.bench.size }); app.bench = new Map(); app.sel = null; app.armed = null; render(); }
  else if (m === 'retreat') { closeSheet(); handlers.retreat(document.body); }
  else if (m === 'restart') { closeSheet(); save(); handlers.start(document.body); }
  else if (m === 'copy') { save(); const ta = $('logtext') as HTMLTextAreaElement; ta.value = exportText(); ta.select(); navigator.clipboard?.writeText(ta.value).catch(() => { }); }
  else if (m === 'dl') {
    save();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([exportText()], { type: 'application/json' }));
    a.download = `q1_記録_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`;
    a.click();
  } else if (m === 'clear') { clearAll(); openLog(); }
}

// ---------- 入力（タッチ・マウス共通。pointer イベント） ----------
interface Drag { src: 'shelf' | 'bench'; part: PartId; facing?: Dir; from?: number; sx: number; sy: number; started: boolean; id: number }
let drag: Drag | null = null;
const ghost = $('ghost');

function dropTarget(x: number, y: number) {
  const tx = x, ty = KNOBS.DRAG_TARGET === 'ghost' ? y - KNOBS.DRAG_LIFT_PX : y;
  const c = view?.cellAt(tx, ty) ?? null;
  const f = view?.cellAt(x, y) ?? null;
  return { cell: c ? c[1] * N() + c[0] : null, finger: f ? f[1] * N() + f[0] : null };
}
function overShelf(x: number, y: number) {
  const r = $('hand').getBoundingClientRect();
  return y >= r.top && y <= r.bottom && x >= r.left && x <= r.right;
}

document.addEventListener('pointerdown', e => {
  if (!$('sheet').hidden) return;
  const tgt = e.target as HTMLElement;
  if (app.screen === 'bench') {
    const tile = tgt.closest('.tile') as HTMLElement | null;
    if (tile) {
      const p = tile.dataset.part as PartId;
      drag = { src: 'shelf', part: p, facing: PARTS[p].springPower ? 'up' : undefined, sx: e.clientX, sy: e.clientY, started: false, id: e.pointerId };
      return;
    }
    if (view && view.el.contains(tgt)) {
      const c = view.cellAt(e.clientX, e.clientY);
      if (c) {
        const cell = c[1] * N() + c[0];
        const b = app.bench.get(cell);
        drag = { src: 'bench', part: b?.part as PartId, facing: b?.facing, from: cell, sx: e.clientX, sy: e.clientY, started: false, id: e.pointerId };
      }
    }
  }
});
document.addEventListener('pointermove', e => {
  if (!drag || e.pointerId !== drag.id) return;
  if (!drag.started) {
    if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < KNOBS.DRAG_START_PX) return;
    if (drag.src === 'bench' && !app.bench.has(drag.from!)) { drag = null; return; }
    if (drag.src === 'shelf' && shelfLeft(drag.part) <= 0) { band(`${PARTS[drag.part].name}は棚にもうない`); drag = null; return; }
    drag.started = true;
    const sz = view ? view.cell : 64;
    ghost.innerHTML = partSVG(drag.part, sz, drag.facing);
    ghost.hidden = false;
    ghost.style.width = sz + 'px';
  }
  const sz = view ? view.cell : 64;
  const lift = KNOBS.DRAG_TARGET === 'ghost' ? KNOBS.DRAG_LIFT_PX : 0;
  ghost.style.transform = `translate(${e.clientX - sz / 2}px,${e.clientY - lift - sz / 2}px)`;
  const { cell } = dropTarget(e.clientX, e.clientY);
  if (view) {
    let h = benchHTML(view);
    if (cell !== null) {
      const bad = app.bench.has(cell) && cell !== drag.from;
      h += view.box(cell % N(), Math.floor(cell / N()), 'target' + (bad ? ' bad' : ''));
      band(bad ? 'そこには置けない（部品がある）' : `${PARTS[drag.part].name}を枠のマスに置く`, false, PARTS[drag.part].does);
    } else band(drag.src === 'bench' && overShelf(e.clientX, e.clientY) ? '離すと棚に戻す' : '作業台のマスの上で離す');
    view.overlay(h);
  }
});
function endDrag(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  const d = drag;
  drag = null;
  ghost.hidden = true;
  if (!d.started) {
    if (d.src === 'shelf') {
      if (shelfLeft(d.part) <= 0) { band(`${PARTS[d.part].name}は棚にもうない`); return; }
      app.armed = app.armed === d.part ? null : d.part; app.sel = null;
      log('arm', { part: app.armed });
      render();
    } else tapBench(d.from!);
    return;
  }
  const { cell, finger } = dropTarget(e.clientX, e.clientY);
  if (d.src === 'shelf') {
    if (cell === null) { log('drop-miss', { reason: 'outside', part: d.part, via: 'drag' }); render(); return; }
    placeOnBench(d.part, cell, 'drag', finger ?? -1);
  } else {
    if (cell !== null) moveOnBench(d.from!, cell, finger ?? -1);
    else if (overShelf(e.clientX, e.clientY)) removeFromBench(d.from!);
    else { log('drop-miss', { reason: 'outside', part: d.part, via: 'move' }); render(); }
  }
}
// タップ：pointerdown と pointerup が同じ所なら、そこでタップとして扱う（click は使わない：タッチのドラッグのあとに click が来ない端末がある）
let press: { el: HTMLElement; x: number; y: number; id: number } | null = null;
document.addEventListener('pointerdown', e => { press = { el: e.target as HTMLElement, x: e.clientX, y: e.clientY, id: e.pointerId }; }, true);
document.addEventListener('pointerup', e => {
  const wasDrag = !!drag;
  endDrag(e);
  const p = press;
  press = null;
  if (!p || p.id !== e.pointerId || Math.hypot(e.clientX - p.x, e.clientY - p.y) > 12) return;
  if (!$('sheet').hidden) { sheetTap(p.el); return; }
  if (wasDrag && app.screen === 'bench' && !(p.el.closest('[data-a]'))) return; // 作業台・棚のタップは endDrag で済んだ
  void onTap(p.el, e.clientX, e.clientY);
});
document.addEventListener('pointercancel', e => { if (drag && e.pointerId === drag.id) { drag = null; ghost.hidden = true; render(); } });

async function onTap(tgt: HTMLElement, cx: number, cy: number) {
  const b = tgt.closest('[data-a]') as HTMLElement | null;
  if (b && !(b as HTMLButtonElement).disabled) { await handlers[b.dataset.a!]?.(b); return; }
  // 盤面のタップ
  if (!view || !view.el.contains(tgt) && !$('stage').contains(tgt)) return;
  if (app.busy) { app.skip = true; return; }
  const c = view.cellAt(cx, cy);
  if (app.screen === 'trial' && app.trial) {
    const t = app.trial;
    if (t.running) { t.stop = true; return; }
    if (t.armed && c) {
      const ok = addTrialThing(t.cur, t.armed, c[0]);
      if (ok) {
        if (t.turn === 0) { t.adds.push({ type: t.armed, x: c[0] }); t.base = trialBase(t.kind, t.ox, t.adds); t.cur = t.base.copy(); }
        log(t.armed === 'doll' ? 'trial-doll' : 'trial-weight', { x: c[0], turn: t.turn });
        t.msg = undefined;
      } else band('その列には置けない');
      t.armed = null;
      if (ok) render();
    }
    return;
  }
  if (app.screen === 'ch' && app.ch && !app.ch.over && c) {
    const ch = app.ch;
    const acts = ch.s.actions().filter(a => a.t !== 'wait');
    const hit = acts.filter(a => actTargets(ch.s, a).some(([x, y]) => x === c[0] && y === c[1]));
    if (!hit.length) return;
    const curIdx = ch.act ? hit.findIndex(a => JSON.stringify(a) === JSON.stringify(ch.act)) : -1;
    const pick = hit[(curIdx + 1) % hit.length] ?? hit[0];
    const card = ['enter', 'climb', 'push'].includes(pick.t) ? 'move' : pick.t as 'place' | 'pick';
    ch.card = card;
    ch.cands = acts.filter(a => card === 'move' ? ['enter', 'climb', 'push'].includes(a.t) : a.t === card);
    ch.act = ch.cands.find(a => JSON.stringify(a) === JSON.stringify(pick)) ?? pick;
    ch.idx = Math.max(0, ch.cands.indexOf(ch.act));
    log('board-tap', { x: c[0], y: c[1], act: pick.t });
    render();
  }
}

window.addEventListener('pagehide', save);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') save(); });
render();
