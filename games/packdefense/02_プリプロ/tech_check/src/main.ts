// 最小の「動く」：四方から魔物、押さえ続けると指の少し上の輪で攻撃、パックを開けると英雄、
// ウェーブの始まりとショップで保存、裏に回ったら一時停止、書き出し・読み込み、合成の音。
import { World, TOWER_X, TOWER_Y, ringFromFinger } from './core/sim.ts';
import { type SaveData, saveLocal, loadLocal, exportText, importText, SAVE_KEY } from './core/save.ts';
import { fmt } from './core/num.ts';
import { Canvas2DRenderer } from './render2d.ts';
import { Loop } from './loop.ts';
import * as audio from './audio.ts';

const q = new URLSearchParams(location.search);
const DPR_CAP = Number(q.get('dpr') ?? 2); // 画素比の上限（技術選定 6章：3 だと描く画素が 2.25倍）
const WAVE_STEPS = Number(q.get('wave') ?? 20) * 60; // 確認版は1ウェーブ20秒
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $('c') as HTMLCanvasElement;
const renderer = new Canvas2DRenderer(canvas);

let data: SaveData;
let world: World;
let waveStep = 0;
let phase: 'wave' | 'shop' = 'wave';
let paused = true;
let lastSaveOk = true;
let activeId: number | null = null;

function freshRun(seed: string): SaveData {
  return { v: 1, seed, wave: 1, phase: 'wave', coins: 0, towerHp: 100, fame: 0, heroes: [], packs: [], settings: { ringOffset: 48, sound: true }, savedAt: 0 };
}

/** 保存の中身から、そのウェーブの始まり（またはショップ）の戦場を作る */
function enter(d: SaveData): void {
  data = d;
  world = new World(`${d.seed}/w${d.wave}`); // ウェーブごとに別の乱数の流れ（やり直しても同じ出方）
  world.coins = d.coins; world.towerHp = d.towerHp;
  world.spawnPerSec = 1 + d.wave * 0.5;
  for (const [x, y, k] of d.heroes) world.addHero(x, y, k);
  phase = d.phase; waveStep = 0;
  if (phase === 'wave') {
    // 買ったパックが塔のまわりに降る
    d.packs.forEach((r, i) => {
      const a = (i / Math.max(1, d.packs.length)) * Math.PI * 2 + 0.4;
      world.addPack(TOWER_X + Math.cos(a) * 90, TOWER_Y + Math.sin(a) * 120, r);
    });
  }
  $('shop').classList.toggle('on', phase === 'shop');
  hud();
}

function heroesNow(): [number, number, number][] {
  return Array.from({ length: world.hero.n }, (_, i) => [Math.round(world.hero.x[i]), Math.round(world.hero.y[i]), world.hero.k[i]] as [number, number, number]);
}
function persist(d: SaveData): void { data = d; lastSaveOk = saveLocal(localStorage, d); hud(); }

/** ウェーブの始まりで保存。買ったパックも入れておく（裏で落ちたら、同じパックがまた降る） */
function startWave(): void {
  const d: SaveData = { ...data, phase: 'wave', coins: world.coins, towerHp: world.towerHp, heroes: heroesNow(), savedAt: Date.now() };
  persist(d);
  enter(d);
}
/** ショップが開いたら保存 */
function openShop(): void {
  const wave = data.wave + 1;
  const fame = data.fame + 10 ** Math.min(wave, 400); // 名声（桁の伸びの試し。仮の式。wave 309 で Infinity になる）
  const d: SaveData = { ...data, phase: 'shop', wave, fame, coins: world.coins, towerHp: world.towerHp, heroes: heroesNow(), packs: [], savedAt: Date.now() };
  phase = 'shop'; world.ringOn = false; activeId = null;
  persist(d);
  $('shop').classList.add('on');
}

function hud(): void {
  $('hud').textContent = `ウェーブ ${data.wave}　塔 ${fmt(world.towerHp)}　コイン ${fmt(world.coins)}　名声 ${fmt(data.fame)}${lastSaveOk ? '' : '　保存できません'}`;
}

// ---- ループ
let frameMs: number[] = [];
const loop = new Loop({
  step() {
    if (paused || phase !== 'wave') return;
    world.step();
    waveStep++;
    if (world.towerHp <= 0) { const d = { ...freshRun(data.seed + '+'), fame: data.fame }; persist(d); enter(d); return; }
    if (waveStep >= WAVE_STEPS) openShop();
  },
  draw() {
    renderer.draw(world);
    if (data.settings.sound) for (const ev of world.events) audio.play(ev === 1 ? 'hit' : ev === 2 ? 'kill' : 'open');
    world.events.length = 0;
    if (world.t % 15 === 0) hud();
  },
  onFrame(dt) { frameMs.push(dt); if (frameMs.length > 600) frameMs.shift(); },
});

function resize(): void { renderer.resize(innerWidth, innerHeight, Math.min(devicePixelRatio, DPR_CAP)); }
addEventListener('resize', resize);

// ---- 入力：1本の指だけ。押さえているあいだ攻撃し続ける。輪は指の少し上
function setRing(e: PointerEvent): void {
  const p = renderer.toWorld(e.clientX, e.clientY);
  const r = ringFromFinger(p.x, p.y, data.settings.ringOffset);
  world.ringX = r.x; world.ringY = r.y;
}
canvas.addEventListener('pointerdown', e => {
  audio.unlock();
  if (activeId !== null || paused || phase !== 'wave') return;
  activeId = e.pointerId; canvas.setPointerCapture(e.pointerId);
  setRing(e); world.ringOn = true;
});
canvas.addEventListener('pointermove', e => { if (e.pointerId === activeId) setRing(e); });
const up = (e: PointerEvent) => { if (e.pointerId === activeId) { activeId = null; world.ringOn = false; } };
canvas.addEventListener('pointerup', up);
canvas.addEventListener('pointercancel', up);
canvas.addEventListener('lostpointercapture', up);
// iOS：拡大・ダブルタップ・長押しのメニューを止める
for (const t of ['touchstart', 'touchmove', 'gesturestart', 'dblclick', 'contextmenu']) canvas.addEventListener(t, e => e.preventDefault(), { passive: false });
addEventListener('touchend', () => audio.unlock(), { passive: true }); // iOS は touchend の中でも音を起こせる

// ---- 裏に回ったら一時停止（保存はしない。戻るのはウェーブの始まりから）
function pause(): void {
  paused = true; activeId = null; world.ringOn = false;
  audio.suspendForBackground();
  $('cover').textContent = 'タップで再開'; $('cover').classList.remove('off');
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') pause(); });
addEventListener('pagehide', pause);
$('cover').addEventListener('pointerdown', () => {
  audio.unlock(); // 再開のタップで、音も起こしなおす
  paused = false; $('cover').classList.add('off');
  if (navigator.storage?.persist) navigator.storage.persist().then(v => { (window as any).__pd.persisted = v; });
});

// ---- ショップ
$('buy').addEventListener('click', () => {
  if (world.coins < 3) return;
  world.coins -= 3; data.coins = world.coins;
  persist({ ...data, coins: world.coins, packs: [...data.packs, data.packs.length % 4] }); // レア度（中身は買ったときに決める前提）
});
$('next').addEventListener('click', () => { $('shop').classList.remove('on'); startWave(); });

// ---- 書き出し・読み込み
const msg = (s: string) => { $('msg').textContent = s; };
$('menu').addEventListener('click', () => { pause(); ($('txt') as HTMLTextAreaElement).value = localStorage.getItem(SAVE_KEY) ?? exportText(data); $('save').classList.add('on'); });
$('close').addEventListener('click', () => $('save').classList.remove('on'));
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(($('txt') as HTMLTextAreaElement).value); msg('コピーしました'); } catch { ($('txt') as HTMLTextAreaElement).select(); msg('選んだ文字を長押しでコピーしてください'); }
});
$('file').addEventListener('click', async () => {
  const text = ($('txt') as HTMLTextAreaElement).value;
  const name = `packdefense-save-w${data.wave}.txt`; // 英数字だけ（yarikomi の確認で、日本語の名前が download になった）
  const file = new File([text], name, { type: 'text/plain' });
  // iOS は「共有」から「ファイルに保存」できる（Web Share の files。iOS 15 以降とされる。実機未確認）
  if (navigator.canShare?.({ files: [file] })) { try { await navigator.share({ files: [file] }); msg('共有しました'); return; } catch { /* 取り消し → ダウンロードへ */ } }
  const a = document.createElement('a'); a.href = URL.createObjectURL(file); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  msg('ダウンロードしました');
});
function loadText(t: string): void {
  try { const d = importText(t); persist(d); enter(d); msg(`読み込みました（ウェーブ ${d.wave}）`); }
  catch (err) { msg('読み込めません：' + (err as Error).message); }
}
$('load').addEventListener('click', () => loadText(($('txt') as HTMLTextAreaElement).value));
$('pick').addEventListener('click', () => $('fin').click());
$('fin').addEventListener('change', async () => { const f = ($('fin') as HTMLInputElement).files?.[0]; if (f) loadText(await f.text()); });

// ---- はじめ
const saved = loadLocal(localStorage);
const first = saved ?? freshRun('run-' + Math.floor(Math.random() * 1e9).toString(36)); // シードを決めるときだけ Math.random
if (!saved) persist(first);
enter(first);
resize();
loop.start();

// テスト用の口
(window as any).__pd = {
  get world() { return world; }, get data() { return data; }, get phase() { return phase; }, get paused() { return paused; },
  get waveStep() { return waveStep; }, frameMs: () => frameMs, toWorld: (x: number, y: number) => renderer.toWorld(x, y),
  audio, openShop, startWave, persisted: null as boolean | null, setOffset: (v: number) => { data.settings.ringOffset = v; },
};

// オフライン（https か localhost のときだけ動く）
if ('serviceWorker' in navigator && q.get('sw') !== '0') navigator.serviceWorker.register('./sw.js').catch(() => {});
