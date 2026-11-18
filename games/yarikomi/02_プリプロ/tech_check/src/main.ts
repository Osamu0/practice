import { newGame, apply, preview, fingerprint, replay, KIND_NAME, LAW_NAME, PLACEABLE, type State, type Kind, type Action } from './core/sim.ts';
import { exportText, importText, saveLocal, loadLocal, SAVE_KEY } from './core/save.ts';
import { unlock, blip, audioState, audioLog } from './audio.ts';
import { seedFrom, nextU32 } from './core/rng.ts';

const ICON: Record<Kind, string> = { '.': '', P: '▬', W: '●', S: '≋', F: '火' };
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

let s: State = loadLocal(localStorage) ?? newGame('谷-0001');
let selected: Exclude<Kind, '.'> | null = null;
const logLines: string[] = [];

function say(lines: string[]) {
  logLines.unshift(...lines.map(l => `[${s.turn}] ${l}`));
  logLines.length = Math.min(logLines.length, 30);
}

function render() {
  $('info').textContent = `シード ${s.seed}／${LAW_NAME[s.law]}／${s.turn}手目／指紋 ${fingerprint(s)}`;
  const next = new Set(preview(s));
  const board = $('board');
  board.replaceChildren(...s.cells.map((c, i) => {
    const d = document.createElement('div');
    d.className = 'cell' + (next.has(i) ? ' next' : '');
    d.dataset.i = String(i);
    d.textContent = ICON[c.k];
    d.setAttribute('role', 'button');
    d.setAttribute('aria-label', `${i % s.w},${Math.floor(i / s.w)} ${KIND_NAME[c.k]}`);
    return d;
  }));
  $('shelf').replaceChildren(...PLACEABLE.map(k => {
    const b = document.createElement('button');
    b.className = 'part' + (selected === k ? ' sel' : '');
    b.dataset.k = k;
    b.innerHTML = `${ICON[k]}<small>${KIND_NAME[k]}×${s.shelf[k]}</small>`;
    return b;
  }));
  $('log').innerHTML = logLines.map(l => `<div>${l}</div>`).join('');
}

function act(a: Action) {
  const r = apply(s, a);
  say(r.events);
  if (r.ok) { saveLocal(localStorage, s); blip(a.t === 'step' ? 330 : 660); }
  render();
}

function cellIndexAt(x: number, y: number): number | null {
  const el = document.elementFromPoint(x, y) as HTMLElement | null;
  const c = el?.closest<HTMLElement>('.cell');
  return c ? Number(c.dataset.i) : null;
}

// 入力：Pointer Events だけで、タッチとマウスを同じに扱う
// ①棚をタップして選ぶ → 盤をタップして置く ②棚から盤へドラッグして置く ③置いた部品をタップで棚へ戻す
let drag: { k: Exclude<Kind, '.'>; sx: number; sy: number; moved: boolean } | null = null;
const ghost = $('ghost');
document.addEventListener('pointerdown', () => unlock(), { capture: true });

$('shelf').addEventListener('pointerdown', e => {
  const b = (e.target as HTMLElement).closest<HTMLElement>('.part');
  if (!b) return;
  drag = { k: b.dataset.k as Exclude<Kind, '.'>, sx: e.clientX, sy: e.clientY, moved: false };
  (e.target as HTMLElement).releasePointerCapture?.(e.pointerId); // タッチの暗黙のキャプチャを外す
});
document.addEventListener('pointermove', e => {
  if (!drag) return;
  if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) > 8) drag.moved = true;
  if (drag.moved) { ghost.style.display = 'block'; ghost.textContent = ICON[drag.k]; ghost.style.left = e.clientX + 'px'; ghost.style.top = e.clientY + 'px'; }
});
document.addEventListener('pointerup', e => {
  if (!drag) return;
  const d = drag; drag = null; ghost.style.display = 'none';
  if (d.moved) {
    const i = cellIndexAt(e.clientX, e.clientY);
    if (i !== null) act({ t: 'place', x: i % s.w, y: Math.floor(i / s.w), k: d.k });
  } else { selected = selected === d.k ? null : d.k; render(); }
});
document.addEventListener('pointercancel', () => { drag = null; ghost.style.display = 'none'; });

$('board').addEventListener('click', e => {
  const c = (e.target as HTMLElement).closest<HTMLElement>('.cell');
  if (!c) return;
  const i = Number(c.dataset.i), x = i % s.w, y = Math.floor(i / s.w);
  if (s.cells[i].k !== '.') act({ t: 'remove', x, y });
  else if (selected) act({ t: 'place', x, y, k: selected });
});
$('step').addEventListener('click', () => act({ t: 'step' }));
$('new').addEventListener('click', () => { s = newGame('谷-' + String(Date.now() % 10000).padStart(4, '0')); logLines.length = 0; saveLocal(localStorage, s); render(); });
$('io-btn').addEventListener('click', () => $('io').classList.toggle('open'));
$('exp').addEventListener('click', () => { ($('io-text') as HTMLTextAreaElement).value = exportText(s); });
$('imp').addEventListener('click', () => load(($('io-text') as HTMLTextAreaElement).value));
$('dl').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([exportText(s)], { type: 'text/plain' }));
  const a = document.createElement('a'); a.href = url; a.download = `yarikomi-save-${s.seed}-t${s.turn}.txt`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('file').addEventListener('change', async e => {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (f) load(await f.text());
});
function load(text: string) {
  try { s = importText(text); saveLocal(localStorage, s); say(['読み込んだ']); }
  catch (err) { say([`読み込めなかった：${(err as Error).message}`]); }
  render();
}

// 端末内保存を消されにくくする（効くかはブラウザしだい）
navigator.storage?.persist?.().then(p => { $('persist').textContent = `storage.persist: ${p}`; }).catch(() => {});
if ('serviceWorker' in navigator && location.protocol !== 'file:') navigator.serviceWorker.register('./sw.js').catch(() => {});

// テスト用の窓口（本番では外す）
Object.assign(window, { __tc: { get state() { return s; }, fingerprint: () => fingerprint(s), fp: fingerprint, replay, newGame, apply, seedFrom, nextU32, audioState, audioLog, blip, SAVE_KEY } });
render();
