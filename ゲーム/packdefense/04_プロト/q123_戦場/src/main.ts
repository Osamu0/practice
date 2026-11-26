// 画面（描画・入力・板）。計算は core を呼ぶだけ。捨てる前提のプロト。
import csvText from '../../../03_仕様/パラメータ表.csv?raw';
import { parseCsv, buildParams, market } from './core/params.ts';
import { Game, W, STEP, newMeta, type Meta, type WaveStat, type Monster, type Hero, type FieldPack } from './core/game.ts';
import { defaultKnobs, autoLevels, KNOB_CHOICES, NAME, POOL, Q2_START, Q3_RUN_TARGET, PRESSURE, RULE_NAME, SPELL_NAME, type Knobs, type Mode, type PackType } from './core/proto.ts';
import { exportText, waveLine, type RunLog } from './core/log.ts';
import { fmt } from './core/num.ts';
import * as audio from './audio.ts';

const VERSION = 'q123-0.2';
const { p, missing } = buildParams(parseCsv(csvText));

// ---------- 保存（つまみ・名声・記録。端末の中だけ） ----------
const KEY = 'pd.proto.q123';
interface Saved { knobs: Knobs; meta: Meta; logs: WaveStat[]; runLogs: RunLog[]; note: string }
function load(): Saved {
  const d: Saved = { knobs: defaultKnobs(p), meta: newMeta(), logs: [], runLogs: [], note: '' };
  try { const s = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    if (s?.knobs) { if (s.knobs.spellMode === 'S1') s.knobs.spellMode = 'S1a'; if (![1, 2, 3].includes(s.knobs.hitsMul)) s.knobs.hitsMul = 1; } // 1回目の保存から
    if (s) return { ...d, ...s, knobs: { ...d.knobs, ...s.knobs }, meta: { ...d.meta, ...s.meta, up: { ...d.meta.up, ...s.meta?.up } } }; } catch { /* 読めなければ最初から */ }
  return d;
}
const saved = load();
function save(): void {
  try { localStorage.setItem(KEY, JSON.stringify({ knobs: g.k, meta: g.meta, logs: g.logs, runLogs: g.runLogs, note: saved.note })); } catch { toast('保存できません'); }
}

// ---------- 画面の大きさ（横幅に合わせる。アート 5.1） ----------
const cv = document.getElementById('field') as HTMLCanvasElement;
const ctx = cv.getContext('2d')!;
let scale = 1, H = 844, dpr = 1;
function resize(): void {
  const vw = window.innerWidth, vh = window.innerHeight;
  scale = vw / W; H = vh / scale; dpr = Math.min(2, window.devicePixelRatio || 1); // 画素の倍率の上限 2（技術選定 4.3）
  cv.width = Math.round(vw * dpr); cv.height = Math.round(vh * dpr);
  if (g) { g.H = H; if (g.scene === 'title') g.layout(); }
}
let g: Game;
resize();
g = new Game(p, saved.knobs, H, 'q' + Date.now().toString(36), saved.meta);
g.logs = saved.logs; g.runLogs = saved.runLogs;
audio.setEnabled(g.k.sound);
window.addEventListener('resize', resize);

// ---------- 入力（1本めの指だけ） ----------
let activeId: number | null = null;
const toWorld = (cx: number, cy: number) => ({ x: cx / scale, y: cy / scale });
cv.addEventListener('pointerdown', e => {
  audio.unlock();
  if (activeId !== null || paused) return;
  activeId = e.pointerId; try { cv.setPointerCapture(e.pointerId); } catch { /* */ }
  const w = toWorld(e.clientX, e.clientY); g.pointerDown(w.x, w.y);
});
cv.addEventListener('pointermove', e => { if (e.pointerId !== activeId) return; const w = toWorld(e.clientX, e.clientY); g.pointerMove(w.x, w.y); });
const release = (e: PointerEvent, cancel: boolean) => { if (e.pointerId !== activeId) return; activeId = null; g.pointerUp(cancel); };
cv.addEventListener('pointerup', e => release(e, false));
cv.addEventListener('pointercancel', e => release(e, true));
cv.addEventListener('lostpointercapture', e => release(e, true));
for (const ev of ['touchstart', 'touchmove', 'gesturestart', 'dblclick', 'contextmenu']) document.addEventListener(ev, e => { if ((e.target as HTMLElement)?.closest?.('#sheet .body, textarea')) return; e.preventDefault(); }, { passive: false });
document.addEventListener('touchend', () => audio.unlock(), { passive: true });

// ---------- 一時停止・裏に回る ----------
let paused = true;
const cover = document.getElementById('cover')!;
const panel = document.getElementById('panel')!;
function setPaused(v: boolean): void { paused = v; if (v) { if (activeId !== null) { activeId = null; g.pointerUp(true); } } }
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    audio.suspend();
    if (g.scene === 'fight' || g.scene === 'cleared') { setPaused(true); if (!panel.classList.contains('on')) showCover('resume'); }
  }
});
function showCover(kind: 'title' | 'resume'): void {
  cover.innerHTML = kind === 'title'
    ? `<h1>開けて守れ！</h1><p>プロト q123（問い1〜3）</p><p style="opacity:.85">いまの遊び方：<b>${modeName(g.k.mode)}</b></p>
       <div style="width:300px;margin-top:18px;display:flex;flex-direction:column;gap:10px">
       <button class="main" data-act="start">タップで始める</button><button class="sec" data-act="knobs">つまみ（設定）</button>
       <button class="sec" data-act="export">記録を書き出す</button></div>`
    : `<h1>タップで再開</h1>`;
  cover.dataset.kind = kind;
  cover.classList.add('on');
}
cover.addEventListener('click', e => {
  audio.unlock();
  const act = (e.target as HTMLElement).closest('[data-act]')?.getAttribute('data-act');
  if (cover.dataset.kind === 'resume') { cover.classList.remove('on'); setPaused(false); return; }
  if (act) doAct(act);
});
document.getElementById('pause')!.addEventListener('click', () => { audio.unlock(); if (g.scene === 'fight' || g.scene === 'cleared') { setPaused(true); openPause(); } });

// ---------- 板 ----------
const sh = document.getElementById('sh')!, sb = document.getElementById('sb')!, sf = document.getElementById('sf')!;
let panelKind = '';
function openPanel(kind: string, head: string, body: string, foot: string): void {
  panelKind = kind; sh.innerHTML = head; sb.innerHTML = body; sf.innerHTML = foot; sb.scrollTop = 0; panel.classList.add('on'); cover.classList.remove('on');
}
function closePanel(): void { panel.classList.remove('on'); panelKind = ''; }
let lastPress = 0;
panel.addEventListener('click', e => {
  audio.unlock();
  const el = (e.target as HTMLElement).closest('[data-act]'); if (!el) return;
  const now = performance.now(); if (now - lastPress < 200) return; lastPress = now; // ui.press.guard 0.2秒
  doAct(el.getAttribute('data-act')!, el.getAttribute('data-v') ?? '');
});

const modeName = (m: Mode) => m === 'q1' ? 'Q1 第1ウェーブだけ' : m === 'q2' ? 'Q2 第2〜4ウェーブ' : 'Q3 10分のラン';
const seg = (key: string, opts: [string, string][], cur: string) =>
  `<div class="seg">${opts.map(([v, l]) => `<button data-act="knob" data-v="${key}=${v}" class="${v === cur ? 'on' : ''}">${l}</button>`).join('')}</div>`;
const row = (lab: string, inner: string, sub = '') => `<div class="row"><div class="lab">${lab}</div>${inner}${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
const onoff = (key: string, v: boolean) => seg(key, [['1', '入'], ['0', '切']], v ? '1' : '0');

function knobsBody(): string {
  const k = g.k;
  return row('遊び方', seg('mode', [['q1', 'Q1 第1W'], ['q2', 'Q2 第2〜4W'], ['q3', 'Q3 ラン']], k.mode), '変えたら「この設定で始める」')
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">Q1 序盤の圧（CSV を上書き。次のランから）</div>'
    + row('プリセット', `<div class="seg">${PRESSURE.map((pr, i) => `<button data-act="preset" data-v="${i}" class="${(Object.keys(pr.v) as (keyof typeof pr.v)[]).every(key => k[key] === pr.v[key]) ? 'on' : ''}">${pr.name}</button>`).join('')}</div>`,
      'やや強い＝遅い自動の指が第1ウェーブで少し傷を受ける目安（README）。下の4つをまとめて変える')
    + row('湧きの量 wave.budget.base', seg('budgetBase', KNOB_CHOICES.budgetBase.map(v => [String(v), v ? String(v) : `CSV(${p.budgetBase})`]), String(k.budgetBase)), 'すべてのウェーブの頭が変わる（第n は 頭＋3×(n−1)）')
    + row('同時に湧く組 spawn.packet.base', seg('packetBase', KNOB_CHOICES.packetBase.map(v => [String(v), v ? String(v) : `CSV(${p.packetBase})`]), String(k.packetBase)))
    + row('slime の耐久', seg('slimeHpMul', KNOB_CHOICES.slimeHpMul.map(v => [String(v), '×' + v]), String(k.slimeHpMul)), `CSV ${p.monster.slime.hp}`)
    + row('前倒し（spawn.pullForward）', onoff('pullForward', k.pullForward), '魔物が0のとき次の組がすぐ来る')
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">Q1 指と画面</div>'
    + row('輪のずらし（tap.ring.offset）', seg('ringOffset', KNOB_CHOICES.ringOffset.map(v => [String(v), String(v)]), String(k.ringOffset)), 'すぐ効く')
    + row('塔の高さ（field.tower.yRatio）', seg('towerY', KNOB_CHOICES.towerY.map(v => [String(v), Math.round(v * 100) + '%']), String(k.towerY)), '次のランから')
    + row('指で打てない帯を見せる', onoff('showBand', k.showBand), '南の下の端の、輪が届かない帯を赤く塗る')
    + row('第1ウェーブの方向', seg('introDirs', [['1', 'はじめの順（東→東西→四方）'], ['0', '四方']], k.introDirs ? '1' : '0'))
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">Q2 パックと呪文</div>'
    + row('輪がパックに当たる決め', seg('packRule', (['A', 'B', 'C'] as const).map(v => [v, RULE_NAME[v]]), k.packRule), 'A 輪の中の魔物とパックの両方／B 輪の中に魔物がいない時だけパック／C 押さえ始めに輪の中にあったパックだけ。すぐ効く')
    + row('開けるのに要る回数', seg('hitsMul', KNOB_CHOICES.hitsMul.map(v => [String(v), '×' + v]), String(k.hitsMul)), `CSV：コモン${p.hitsToOpen[0]}・レア${p.hitsToOpen[1]}・エピック${p.hitsToOpen[2]}回。次に降るパックから`)
    + row('降る時刻を湧きの山に合わせる', onoff('dropSync', k.dropSync), '切＝CSV（半分は始まり、残りは湧きの4割の時）。入＝組の湧く時刻に散らす。次のウェーブから')
    + row('呪文の形', seg('spellMode', (['S1a', 'S1b', 'S2'] as const).map(v => [v, SPELL_NAME[v]]), k.spellMode), 'S1b＝呪文の輪にいちばん多く魔物が入る所で起きる。次のランから')
    + row('群れの出始め monster.swarm.fromWave', seg('swarmFrom', KNOB_CHOICES.swarmFrom.map(v => [String(v), v ? '第' + v : `CSV(第${p.monster.swarm.fromWave})`]), String(k.swarmFrom)), '次のランから')
    + row('落ち方：英雄の少ない方向の優先（pack.drop.dirBias）', seg('dropBias', KNOB_CHOICES.dropBias.map(v => [String(v), String(v)]), String(k.dropBias)))
    + row('Q2 で呪文を必ずまぜる', onoff('forceSpell', k.forceSpell), '各ショップの最初のパックの2枚めを呪文に')
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">ショップ（次のランから）</div>'
    + row('最初のコイン coin.start', seg('startCoin', KNOB_CHOICES.startCoin.map(v => [String(v), v ? String(v) : `CSV(${p.coinStart})`]), String(k.startCoin)))
    + row('パックの値段の倍率', seg('priceMul', KNOB_CHOICES.priceMul.map(v => [String(v), '×' + v]), String(k.priceMul)), `CSV 見習い${p.pack.novice.price}・鉄壁${p.pack.iron.price}（×相場）`)
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">Q3 自動化</div>'
    + row('タップ攻撃の自動化', seg('auto', autoLevels(p).map((a, i) => [String(i), a.name]), String(k.auto)),
      autoLevels(p).map(a => `${a.name}：${a.ratio ? `威力×${a.ratio}・${a.interval}秒ごと` : '切'}`).join('／') + '。強＝指と同じ（比べるためだけ）。すぐ効く')
    + '<div class="lab" style="margin-top:14px;color:#2F6FD6">そのほか</div>'
    + row('音', onoff('sound', k.sound)) + row('シード', seg('sameSeed', [['0', '毎回かえる'], ['1', '毎回同じ']], k.sameSeed ? '1' : '0'))
    + row('名声と強化（Q3）', `<button class="sec" data-act="resetMeta">名声・記録・強化を最初に戻す</button>`, `いま：名声${fmt(g.meta.fame)} 記録 第${g.meta.record} 強化 指${g.meta.up.tapDmg}・英雄${g.meta.up.heroDmg}・塔${g.meta.up.towerHp}`)
    + (missing.length ? `<div class="sub" style="color:#c00">CSV に無い名前：${missing.join('、')}</div>` : `<div class="sub">値は 03_仕様/パラメータ表.csv から読んだ（${VERSION}）</div>`);
}
function openKnobs(back: string): void {
  openPanel('knobs', 'つまみ', knobsBody(), `<button class="main" data-act="start">この設定で始める</button><button class="sec" data-act="${back}">閉じる</button>`);
}
function openPause(): void {
  const t = g.runSteps / 60;
  openPanel('pause', '一時停止', `<div class="sub">${modeName(g.k.mode)}　第${g.wave}ウェーブ　ランの時間 ${Math.floor(t / 60)}分${Math.floor(t % 60)}秒</div><div class="sub">${g.knobText()}</div>`,
    `<button class="main" data-act="resume">再開</button><div class="two"><button class="sec" data-act="knobsP">つまみ</button><button class="sec" data-act="export">記録</button></div>
     <div class="two"><button class="sec" data-act="restart">はじめからやり直す</button><button class="sec" data-act="quit">ランをやめる</button></div>`);
}
const pctStr = (a: number, t: number) => t > 0 ? Math.round(a / t * 100) + '%' : '-';
function statTable(s: WaveStat[]): string {
  const sum = (f: (x: WaveStat) => number) => s.reduce((a, x) => a + f(x), 0);
  const tot = sum(x => x.dmg.finger + x.dmg.auto + x.dmg.hero + x.dmg.spell);
  const delays = s.flatMap(x => x.openDelays);
  const rows: [string, string][] = [
    ['時間', sum(x => x.time).toFixed(1) + '秒'], ['指の当たり', String(sum(x => x.hitsMonster))],
    ['当たらなかった押さえ', `${sum(x => x.whiffPresses)} / ${sum(x => x.presses)}`],
    ['塔の傷 北・東・南・西', ['n', 'e', 's', 'w'].map(d => Math.round(sum(x => x.towerDmg[d as 'n']))).join('・')],
    ['開けたパック', `${sum(x => x.packsOpened)}（開けるまで平均 ${delays.length ? (delays.reduce((a, b) => a + b, 0) / delays.length).toFixed(1) : '-'}秒）`],
    ['呪文 使った・空振り・あふれ', `${sum(x => x.spellCasts)}・${sum(x => x.spellWhiff)}・${sum(x => x.spellOverflow)}`],
    ['傷の割合 指・自動・英雄・呪文', [sum(x => x.dmg.finger), sum(x => x.dmg.auto), sum(x => x.dmg.hero), sum(x => x.dmg.spell)].map(v => pctStr(v, tot)).join('・')],
  ];
  return `<table class="st">${rows.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join('')}</table>`;
}
function openShop(): void {
  const buys = (Object.keys(POOL) as PackType[]).map(t => {
    const pp = p.pack[t], ws = pp.rarityWeights, tot = ws.reduce((a, b) => a + b, 0);
    const price = g.packPrice(t);
    return `<div class="card"><div class="t">${NAME.pack[t]}　● ${fmt(price)}</div>
      <div class="s">${pp.cards}枚。英雄：${POOL[t].heroes.map(h => NAME.role[h]).join('・')}／呪文：${POOL[t].spells.map(s => NAME.spell[s.id]).join('・')}（2枚め以降の呪文 ${Math.round(pp.spellShare * 100)}%）<br>
      ${ws.map((w, i) => `${NAME.rarity[i]} ${Math.round(w / tot * 100)}%`).join('　')}</div>
      <button class="main" data-act="buy" data-v="${t}" ${g.canBuy(t) ? '' : 'disabled style="opacity:.4"'}>買う</button></div>`;
  }).join('');
  const r = g.lastShopResult;
  openPanel('shop', `ショップ　<span style="font-size:15px">● ${fmt(g.coins)}</span>`,
    `<div class="sub">第${g.wave}ウェーブを生き延びた（生き延びたコイン +${fmt(r.coins)}${g.k.mode === 'q3' ? `、名声 +${fmt(r.fame)}` : ''}）。買ったパックは次のウェーブで降ってくる。</div>
     <div class="sub">買った ${g.boughtThisShop.length} / ${p.shopBuyMax}${g.carried ? `　持ち越し ${g.carried}` : ''}　（中身は戦場で開けるまでわからない）</div>${buys}`,
    `<button class="main" data-act="next">次のウェーブへ</button>`);
}
function openEnd(): void {
  const mine = g.logs.filter(s => s.run === g.runIndex);
  if (g.scene === 'q1end') {
    const s = mine[mine.length - 1];
    openPanel('end', 'Q1：第1ウェーブ', `<div class="big">${s?.result ?? ''}　塔 ${s?.towerHpEnd ?? 0}</div><div class="sub">${g.knobText()}</div>${statTable(mine)}
      <div class="sub">見ること：上下左右に持ち替えずに届いたか／見落として削られたのが「自分のせい」か／40秒で指が疲れないか</div>`,
      `<button class="main" data-act="start">もう一度</button><div class="two"><button class="sec" data-act="knobs">つまみ</button><button class="sec" data-act="export">記録</button></div>`);
  } else {
    const last = mine[mine.length - 1];
    openPanel('end', `Q2：第${Q2_START.wave}〜${Q2_START.lastWave}ウェーブ`, `<div class="big">${last?.result === '生き延びた' ? '生き延びた' : `第${last?.wave}で塔が壊れた`}</div><div class="sub">${g.knobText()}</div>${statTable(mine)}
      <div class="sub">見ること：30秒に1回「開けて得をした」か／無視し続けると損か／「ここで使ってよかった」はS1とS2のどちらが多いか</div>`,
      `<button class="main" data-act="start">もう一度</button><div class="two"><button class="sec" data-act="knobs">つまみ</button><button class="sec" data-act="export">記録</button></div>`);
  }
}
function openResult(): void {
  const r = g.resultInfo;
  const line = r.reached > r.prevRecord ? '記録を更新！' : r.reached === r.prevRecord ? '記録に並んだ' : `前の記録まで あと ${r.prevRecord - r.reached} ウェーブ`;
  const mine = g.logs.filter(s => s.run === g.runIndex);
  openPanel('result', '結果', `<div class="big">第${r.reached}ウェーブまで生き延びた</div><div class="t" style="font-weight:800">${line}</div>
    <div class="row">このランの名声 +${fmt(r.fame)}　持っている名声 ${fmt(g.meta.fame)}</div><div class="sub">ランの時間 ${(r.time / 60).toFixed(1)}分　自動化：${g.autoLevel().name}</div>${statTable(mine)}`,
    `<button class="main" data-act="toUpgrade">強化画面へ</button>`);
}
function openUpgrade(): void {
  const items: [ 'tapDmg' | 'heroDmg' | 'towerHp' | 'tapAuto', string, string, string][] = [
    ['tapAuto', 'タップ攻撃の自動化', autoLevels(p)[g.k.auto].name, autoLevels(p)[g.k.auto + 1]?.name ?? '最大'],
    ['tapDmg', 'タップ攻撃の威力', '段' + g.meta.up.tapDmg, `×${(p.up.tapDmg.effect ** g.meta.up.tapDmg).toFixed(2)} → ×${(p.up.tapDmg.effect ** (g.meta.up.tapDmg + 1)).toFixed(2)}`],
    ['heroDmg', '英雄の威力', '段' + g.meta.up.heroDmg, `×${(p.up.heroDmg.effect ** g.meta.up.heroDmg).toFixed(2)} → ×${(p.up.heroDmg.effect ** (g.meta.up.heroDmg + 1)).toFixed(2)}`],
    ['towerHp', '塔の耐久', '段' + g.meta.up.towerHp, `${Math.round(p.towerHp * p.up.towerHp.effect ** g.meta.up.towerHp)} → ${Math.round(p.towerHp * p.up.towerHp.effect ** (g.meta.up.towerHp + 1))}`],
  ];
  const body = items.map(([id, name, now, next]) => {
    const maxed = id === 'tapAuto' && g.k.auto >= autoLevels(p).length - 1;
    const c = g.upCost(id), ok = !maxed && g.meta.fame >= c;
    return `<div class="card"><div class="t">${name}　<span style="font-size:13px">${now}</span></div><div class="s">${maxed ? '最大' : '次：' + next}</div>
      <button class="main" data-act="up" data-v="${id}" ${ok ? '' : 'disabled style="opacity:.4"'}>${maxed ? '最大' : `強くする　名声 ${fmt(c)}`}</button></div>`;
  }).join('');
  openPanel('upgrade', `強化画面　<span style="font-size:15px">名声 ${fmt(g.meta.fame)}　記録 第${g.meta.record}</span>`, body,
    `<button class="main" data-act="start">ランに出る</button><div class="two"><button class="sec" data-act="knobsU">つまみ</button><button class="sec" data-act="export">記録</button></div>`);
}
function exportString(): string {
  const head = [`${new Date().toISOString().slice(0, 16)} ${VERSION}`, `画面 ${window.innerWidth}x${window.innerHeight} 倍率${window.devicePixelRatio} 論理 390x${Math.round(H)}`,
    navigator.userAgent.replace(/\s+/g, ' ').slice(0, 140), missing.length ? 'CSV に無い：' + missing.join(',') : 'CSV ok'];
  return exportText(head, g.logs, g.runLogs, saved.note);
}
let exportBack = '';
function openExport(back: string): void {
  exportBack = back;
  openPanel('export', '記録を書き出す', `<div class="sub">${g.logs.length}ウェーブぶん。コピーして貼ってください。</div>
    <div class="row"><div class="lab">ひとこと（感じたこと。記録に入る）</div><textarea id="note" rows="3">${saved.note.replace(/</g, '&lt;')}</textarea></div>
    <textarea id="out" rows="12" readonly>${exportString().replace(/</g, '&lt;')}</textarea>`,
    `<div class="two"><button class="main" data-act="copy">コピー</button><button class="sec" data-act="download">ファイル</button></div>
     <div class="two"><button class="sec" data-act="clearLog">記録を消す</button><button class="sec" data-act="${back}">閉じる</button></div>`);
  const note = document.getElementById('note') as HTMLTextAreaElement;
  note.addEventListener('input', () => { saved.note = note.value; (document.getElementById('out') as HTMLTextAreaElement).value = exportString(); save(); });
}

function backTo(where: string): void {
  if (where === 'title') { closePanel(); showCover('title'); }
  else if (where === 'pause') openPause();
  else if (where === 'end') openEnd();
  else if (where === 'upgrade') openUpgrade();
  else if (where === 'result') openResult();
  else if (where === 'shop') openShop();
  else { closePanel(); showCover('title'); }
}
function currentBack(): string {
  if (g.scene === 'title') return 'title';
  if (g.scene === 'fight' || g.scene === 'cleared' || g.scene === 'destroyed') return 'pause';
  if (g.scene === 'q1end' || g.scene === 'q2end') return 'end';
  return g.scene;
}

function doAct(act: string, v = ''): void {
  switch (act) {
    case 'start': closePanel(); cover.classList.remove('on'); g.H = H; g.newRun(); setPaused(false); save(); break;
    case 'knobs': openKnobs(currentBack()); break;
    case 'knobsP': openKnobs('pause'); break;
    case 'knobsU': openKnobs('upgrade'); break;
    case 'title': case 'pause': case 'end': case 'upgrade': case 'result': case 'shop': backTo(act); break;
    case 'knob': {
      const [key, val] = v.split('='); const k = g.k as unknown as Record<string, unknown>;
      const cur = k[key];
      k[key] = typeof cur === 'boolean' ? val === '1' : typeof cur === 'number' ? Number(val) : val;
      if (key === 'sound') audio.setEnabled(g.k.sound);
      save(); const st = sb.scrollTop; const back = sf.querySelector('[data-act]:not([data-act=start])')?.getAttribute('data-act') ?? 'title';
      openKnobs(back); sb.scrollTop = st; break;
    }
    case 'preset': { Object.assign(g.k, PRESSURE[Number(v)].v); save(); const st = sb.scrollTop; openKnobs(sf.querySelector('[data-act]:not([data-act=start])')?.getAttribute('data-act') ?? 'title'); sb.scrollTop = st; break; }
    case 'resetMeta': g.meta = newMeta(); g.k.auto = 0; g.runLogs = []; save(); openKnobs(sf.querySelector('[data-act]:not([data-act=start])')?.getAttribute('data-act') ?? 'title'); break;
    case 'resume': closePanel(); setPaused(false); break;
    case 'restart': closePanel(); g.newRun(); setPaused(false); break;
    case 'quit': closePanel(); setPaused(false); g.endRun(); save(); break;
    case 'export': openExport(currentBack() === 'title' && cover.classList.contains('on') ? 'title' : panelKind === 'pause' ? 'pause' : currentBack()); break;
    case 'copy': {
      const ta = document.getElementById('out') as HTMLTextAreaElement; const txt = ta.value;
      const fallback = () => { ta.removeAttribute('readonly'); ta.focus(); ta.select(); ta.setSelectionRange(0, txt.length); const ok = document.execCommand('copy'); ta.setAttribute('readonly', ''); toast(ok ? 'コピーした' : '選んで長押しでコピーしてください'); };
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(txt).then(() => toast('コピーした'), fallback); else fallback();
      break;
    }
    case 'download': {
      const blob = new Blob([exportString()], { type: 'text/plain' });
      const file = new File([blob], 'packdefense_proto_log.txt', { type: 'text/plain' });
      const nav = navigator as Navigator & { canShare?: (d: unknown) => boolean };
      if (nav.canShare?.({ files: [file] })) { nav.share({ files: [file] }).catch(() => { /* 取りやめ */ }); }
      else { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = file.name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
      break;
    }
    case 'clearLog': g.logs = []; g.runLogs = []; saved.note = ''; save(); openExport(exportBack); break;
    case 'buy': if (g.buy(v as PackType)) { audio.play('buy'); const st = sb.scrollTop; openShop(); sb.scrollTop = st; } break;
    case 'next': closePanel(); g.nextWave(); save(); break;
    case 'toUpgrade': g.toUpgrade(); openUpgrade(); break;
    case 'up': if (g.buyUpgrade(v as 'tapDmg')) { audio.play('buy'); save(); openUpgrade(); } break;
  }
}

// ---------- 知らせ ----------
const toastEl = document.getElementById('toast')!;
let toastTimer = 0;
function toast(s: string): void { toastEl.textContent = s; toastEl.style.display = 'block'; clearTimeout(toastTimer); toastTimer = window.setTimeout(() => { toastEl.style.display = 'none'; }, 2500); }

// ---------- 描画 ----------
const RAR = ['#F2EFE8', '#4FA3FF', '#8A3FE0'];
const RAR_EDGE = ['#9A968C', '#1B2F5E', '#3B1670'];
let bg: HTMLCanvasElement | null = null, bgKey = '';
function background(): HTMLCanvasElement {
  const key = `${cv.width}x${cv.height}:${g.towerY}`;
  if (bg && bgKey === key) return bg;
  bg = document.createElement('canvas'); bg.width = cv.width; bg.height = cv.height; bgKey = key;
  const b = bg.getContext('2d')!; b.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0);
  b.fillStyle = '#A9CB8C'; b.fillRect(0, 0, W, H + 2);
  b.fillStyle = '#A2C585';
  for (let y = 0; y < H; y += 32) for (let x = (y / 32) % 2 ? 32 : 0; x < W; x += 64) b.fillRect(x, y, 32, 32);
  b.fillStyle = '#DCCBA4';
  b.fillRect(g.towerX - 22, 0, 44, H + 2); b.fillRect(0, g.towerY - 22, W, 44);
  b.fillStyle = '#8DB06F'; b.beginPath(); b.ellipse(g.towerX, g.towerY + 8, 54, 34, 0, 0, Math.PI * 2); b.fill();
  return bg;
}
function rr(x: number, y: number, w: number, h: number, r: number): void { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); }

function drawTower(): void {
  const x = g.towerX, y = g.towerY, hurt = g.fx.some(f => f.kind === 'hurt');
  ctx.lineWidth = 3; ctx.strokeStyle = '#3A3530';
  ctx.fillStyle = '#C9C4B8'; rr(x - 28, y - 66, 56, 96, 6); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#A8A397'; ctx.fillRect(x + 8, y - 64, 18, 92);
  ctx.fillStyle = '#5A4632'; rr(x - 10, y + 6, 20, 24, 8); ctx.fill();
  ctx.fillStyle = '#3A3530'; ctx.fillRect(x - 6, y - 46, 12, 14);
  ctx.strokeStyle = '#3A3530'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x, y - 66); ctx.lineTo(x, y - 96); ctx.stroke();
  ctx.fillStyle = '#2F6FD6'; ctx.beginPath(); ctx.moveTo(x, y - 96); ctx.lineTo(x + 22, y - 89); ctx.lineTo(x, y - 82); ctx.fill();
  if (hurt) { ctx.strokeStyle = 'rgba(229,72,77,.8)'; ctx.lineWidth = 5; ctx.beginPath(); ctx.arc(x, y, p.towerHitR + 10, 0, Math.PI * 2); ctx.stroke(); }
}
function drawMonster(m: Monster): void {
  const s = m.size, white = m.flash > 0;
  ctx.lineWidth = m.type === 'swarm' ? 1.5 : 2; ctx.strokeStyle = '#2A1E2E';
  ctx.fillStyle = white ? '#fff' : m.type === 'slime' ? '#A8323E' : m.type === 'wolf' ? '#5E5A66' : '#7A5A8C';
  if (m.type === 'slime') { ctx.beginPath(); ctx.ellipse(m.x, m.y, 16, 14, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
  else if (m.type === 'wolf') {
    ctx.beginPath(); ctx.ellipse(m.x, m.y, 16, 11, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(m.x - 9, m.y - 8); ctx.lineTo(m.x - 5, m.y - 18); ctx.lineTo(m.x - 1, m.y - 9); ctx.moveTo(m.x + 1, m.y - 9); ctx.lineTo(m.x + 5, m.y - 18); ctx.lineTo(m.x + 9, m.y - 8); ctx.fill(); ctx.stroke();
  } else { ctx.beginPath(); ctx.arc(m.x, m.y, s, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
  ctx.fillStyle = '#FFE14D';
  const e = m.type === 'swarm' ? 2 : 3;
  ctx.beginPath(); ctx.arc(m.x - s * 0.35, m.y - 2, e, 0, Math.PI * 2); ctx.arc(m.x + s * 0.35, m.y - 2, e, 0, Math.PI * 2); ctx.fill();
  if (m.slowUntil > g.t) { ctx.strokeStyle = '#7FD3FF'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(m.x, m.y, s + 4, 0, Math.PI * 2); ctx.stroke(); }
  if (m.hp < m.maxHp) { ctx.fillStyle = '#2A1E2E'; ctx.fillRect(m.x - 12, m.y - s - 8, 24, 4); ctx.fillStyle = '#E5484D'; ctx.fillRect(m.x - 12, m.y - s - 8, 24 * Math.max(0, m.hp / m.maxHp), 4); }
}
function drawHero(h: Hero): void {
  const age = (g.t - h.born) / 60, drop = age < p.heroSpawnFx ? (1 - age / p.heroSpawnFx) * 30 : 0;
  const x = h.x, y = h.y - drop, bob = Math.sin(g.t / 30 + x) > 0 ? 1 : 0;
  ctx.lineWidth = 2; ctx.strokeStyle = '#1B2233';
  ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.ellipse(x, y, 15, 6, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = RAR_EDGE[h.rarity] === '#9A968C' ? '#2F6FD6' : RAR[h.rarity]; ctx.lineWidth = 2.5; ctx.stroke();
  ctx.strokeStyle = '#1B2233'; ctx.lineWidth = 2;
  const body = h.role === 'sword' ? '#2F6FD6' : h.role === 'archer' ? '#3E8A55' : h.role === 'shield' ? '#E6E9EF' : '#C9873A';
  ctx.fillStyle = body; rr(x - 9, y - 28 - bob, 18, 24, 5); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#F3D2B3'; ctx.beginPath(); ctx.arc(x, y - 36 - bob, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#E8B730'; ctx.fillRect(x - 9, y - 18 - bob, 18, 3);
  // 役の印
  const a = h.atkFx > 0 ? Math.atan2(h.aimY - y, h.aimX - x) : -Math.PI / 3;
  ctx.lineWidth = 2.5;
  if (h.role === 'sword') { ctx.strokeStyle = '#D9DEE6'; ctx.beginPath(); ctx.moveTo(x + 9, y - 20); ctx.lineTo(x + 9 + Math.cos(a) * 16, y - 20 + Math.sin(a) * 16); ctx.stroke(); }
  if (h.role === 'archer') { ctx.strokeStyle = '#5A4632'; ctx.beginPath(); ctx.arc(x + 11, y - 20, 9, -1.2, 1.2); ctx.stroke(); }
  if (h.role === 'shield') { ctx.fillStyle = '#2F6FD6'; ctx.strokeStyle = '#1B2233'; ctx.lineWidth = 1.5; rr(x - 17, y - 26, 12, 16, 3); ctx.fill(); ctx.stroke(); }
  if (h.role === 'spear') { ctx.strokeStyle = '#5A4632'; ctx.beginPath(); ctx.moveTo(x + 10, y - 4); ctx.lineTo(x + 10 + Math.cos(a) * 26, y - 20 + Math.sin(a) * 26); ctx.stroke(); }
  if (h.stackFx > 0) { ctx.fillStyle = '#E8B730'; ctx.beginPath(); ctx.moveTo(x, y - 58); ctx.lineTo(x - 6, y - 50); ctx.lineTo(x + 6, y - 50); ctx.fill(); }
}
function drawPack(pk: FieldPack): void {
  const r = pk.def.rarity;
  if (pk.tele > 0) {
    const k = pk.tele / p.dropTele;
    ctx.fillStyle = `rgba(255,255,230,${0.35 + 0.25 * (1 - k)})`; ctx.fillRect(pk.x - 15, 0, 30, pk.y);
    ctx.fillStyle = RAR[r]; ctx.globalAlpha = 0.7; ctx.beginPath(); ctx.ellipse(pk.x, pk.y + 18, 30, 10, 0, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
    return;
  }
  const sh = pk.shake > 0 ? Math.sin(g.t * 2.5) * 2 : 0, x = pk.x + sh, y = pk.y;
  ctx.fillStyle = 'rgba(0,0,0,.18)'; ctx.beginPath(); ctx.ellipse(pk.x, y + 20, 16, 5, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#FBF8F1'; ctx.strokeStyle = '#1B2233'; ctx.lineWidth = 2; rr(x - 13, y - 19, 26, 38, 4); ctx.fill(); ctx.stroke();
  ctx.strokeStyle = RAR[r] === '#F2EFE8' ? '#9A968C' : RAR[r]; ctx.lineWidth = 3.5; rr(x - 10, y - 16, 20, 32, 3); ctx.stroke();
  if (r >= 2) { ctx.lineWidth = 1.5; rr(x - 7, y - 13, 14, 26, 2); ctx.stroke(); }
  ctx.fillStyle = pk.def.type === 'iron' ? '#5E5A66' : '#E8B730'; ctx.fillRect(x - 10, y - 3, 20, 6);
  // ひび
  const k = pk.hits / pk.need; ctx.strokeStyle = '#1B2233'; ctx.lineWidth = 1.5;
  for (let i = 0; i < Math.floor(k * 5); i++) { ctx.beginPath(); ctx.moveTo(x - 8 + i * 4, y - 16 + (i % 2) * 6); ctx.lineTo(x - 2 + i * 3, y - 4 + (i % 3) * 4); ctx.lineTo(x + 4 - i, y + 8 + i); ctx.stroke(); }
}
function diamond(x: number, y: number, c: string): void {
  ctx.fillStyle = c; ctx.strokeStyle = '#1B2233'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); ctx.fill(); ctx.stroke();
}
function ring(x: number, y: number, r: number, color = '#fff', w = 2.5): void {
  ctx.strokeStyle = 'rgba(27,34,51,.55)'; ctx.lineWidth = w + 4.5; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke();
  ctx.strokeStyle = color; ctx.lineWidth = w; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.stroke();
}
function spellIcon(id: string, x: number, y: number, s: number): void {
  ctx.fillStyle = id === 'fire1' ? '#F07A2B' : '#7FD3FF'; ctx.beginPath(); ctx.arc(x, y, s, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#1B2233'; ctx.font = `bold ${Math.round(s * 1.1)}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(id === 'fire1' ? '火' : '氷', x, y + 1);
}

function draw(): void {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(background(), 0, 0);
  ctx.setTransform(scale * dpr, 0, 0, scale * dpr, 0, 0);
  const inField = g.scene === 'fight' || g.scene === 'cleared' || g.scene === 'destroyed' || g.scene === 'shop';
  // 指で打てない帯（南）と、輪の上の限界
  if (g.k.showBand) {
    const yb = g.reachBottom;
    ctx.fillStyle = 'rgba(229,72,77,.16)'; ctx.fillRect(0, yb, W, H - yb);
    ctx.setLineDash([6, 5]); ctx.strokeStyle = 'rgba(229,72,77,.8)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(0, yb); ctx.lineTo(W, yb); ctx.stroke();
    ctx.strokeStyle = 'rgba(27,34,51,.35)'; ctx.beginPath(); ctx.moveTo(0, p.ringTop); ctx.lineTo(W, p.ringTop); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(160,30,40,.9)'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
    ctx.fillText(`指で打てない ${Math.max(0, Math.round(H - yb))}px（ずらし${g.k.ringOffset}）`, 6, yb - 2);
  }
  drawTower();
  if (!inField) return;
  if (g.k.spellMode === 'S2' && g.k.mode !== 'q1') {
    g.slotRects.forEach((r, i) => {
      ctx.globalAlpha = 0.8; ctx.fillStyle = 'rgba(251,248,241,.35)'; ctx.strokeStyle = g.slots[i] ? '#E8B730' : 'rgba(27,34,51,.6)'; ctx.lineWidth = g.slots[i] ? 3 : 1.5;
      rr(r.x, r.y, r.w, r.h, 10); ctx.fill(); ctx.stroke();
      const s = g.slots[i];
      if (s && !(g.drag && g.drag.slot === i)) { ctx.fillStyle = 'rgba(255,255,255,.75)'; rr(r.x + 6, r.y + 6, r.w - 12, r.h - 12, 8); ctx.fill(); spellIcon(s.id, r.x + r.w / 2, r.y + r.h / 2 - 6, 18);
        ctx.fillStyle = '#1B2233'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(NAME.spell[s.id], r.x + r.w / 2, r.y + r.h - 14); }
      ctx.globalAlpha = 1;
    });
  }
  for (const pk of g.packs) drawPack(pk);
  const heroes = [...g.heroes].sort((a, b) => a.y - b.y);
  for (const h of heroes) drawHero(h);
  for (const m of g.monsters) drawMonster(m);
  ctx.fillStyle = '#5A4632';
  for (const b of g.projs) { ctx.beginPath(); ctx.arc(b.x, b.y, 2.5, 0, Math.PI * 2); ctx.fill(); }
  for (const s of g.pending) { ctx.setLineDash([4, 4]); ring(s.x, s.y, s.id === 'fire1' ? p.fire1.radius : p.ice1.radius, s.id === 'fire1' ? '#F07A2B' : '#7FD3FF', 2); ctx.setLineDash([]); }
  for (const f of g.fx) {
    const k = f.t / f.life;
    if (f.kind === 'burst') { ctx.strokeStyle = `rgba(255,255,255,${1 - k})`; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(f.x, f.y, f.r * (0.6 + k), 0, Math.PI * 2); ctx.stroke(); }
    else if (f.kind === 'slash') { ctx.strokeStyle = `rgba(255,255,255,${1 - k})`; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(f.x, f.y, f.r, -0.9, 0.9); ctx.stroke(); }
    else if (f.kind === 'line') { ctx.strokeStyle = `rgba(255,240,200,${0.8 * (1 - k)})`; ctx.lineWidth = f.r * 0.5; ctx.beginPath(); ctx.moveTo(f.x, f.y - 16); ctx.lineTo(f.x2, f.y2 - 16); ctx.stroke(); }
    else if (f.kind === 'aura') { ctx.strokeStyle = `rgba(47,111,214,${0.5 * (1 - k)})`; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(f.x, f.y, f.r * (0.7 + 0.3 * k), 0, Math.PI * 2); ctx.stroke(); }
    else if (f.kind === 'spell') { ctx.fillStyle = f.c ? `rgba(127,211,255,${0.5 * (1 - k)})` : `rgba(240,122,43,${0.6 * (1 - k)})`; ctx.beginPath(); ctx.arc(f.x, f.y, f.r * (0.5 + 0.5 * Math.min(1, k * 3)), 0, Math.PI * 2); ctx.fill(); }
    else if (f.kind === 'open') {
      ctx.strokeStyle = RAR[f.c]; ctx.globalAlpha = 1 - k; ctx.lineWidth = 3 + f.c * 2;
      for (let i = 0; i < 10 + f.c * 6; i++) { const a = i / (10 + f.c * 6) * Math.PI * 2; ctx.beginPath(); ctx.moveTo(f.x + Math.cos(a) * 10, f.y + Math.sin(a) * 10); ctx.lineTo(f.x + Math.cos(a) * f.r * (0.4 + k), f.y + Math.sin(a) * f.r * (0.4 + k)); ctx.stroke(); }
      ctx.globalAlpha = 1;
    } else if (f.kind === 'coin') { const tx = 160, ty = 30; ctx.fillStyle = '#E8B730'; ctx.strokeStyle = '#5A4632'; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(f.x + (tx - f.x) * k * k, f.y + (ty - f.y) * k * k, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
  }
  // 危険の三角（群れ）
  for (const w of g.warnings) {
    if (Math.floor(g.t / 8) % 2) continue;
    const a = Math.atan2(g.towerY - w.y, g.towerX - w.x);
    ctx.save(); ctx.translate(w.x, w.y); ctx.rotate(a + Math.PI / 2);
    ctx.fillStyle = '#E5484D'; ctx.strokeStyle = '#2A1E2E'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, -13); ctx.lineTo(9, 13); ctx.lineTo(-9, 13); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.rotate(-(a + Math.PI / 2)); ctx.fillStyle = '#fff'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', 0, 2); ctx.restore();
  }
  // 自動の輪
  if (g.autoLevel().ratio > 0 && g.autoTarget >= 0) {
    ctx.strokeStyle = g.autoFlash > 0 ? '#FFE14D' : 'rgba(232,183,48,.85)'; ctx.lineWidth = 2; ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.arc(g.autoX, g.autoY, p.autoRingR, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
  }
  // 指の輪と隠れたパックの印
  if (g.fingerOn) {
    if (g.k.packRule === 'C' && g.lockPack && g.packs.includes(g.lockPack)) { ctx.strokeStyle = '#FFE14D'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(g.lockPack.x, g.lockPack.y, 26, 0, Math.PI * 2); ctx.stroke(); }
    ring(g.ringX, g.ringY, p.ringVis);
    ctx.fillStyle = 'rgba(255,255,255,.25)'; ctx.beginPath(); ctx.arc(g.fx0, g.fy0, 10, 0, Math.PI * 2); ctx.fill();
    for (const pk of g.hiddenMarks()) {
      const a = Math.atan2(pk.y - g.ringY, pk.x - g.ringX);
      diamond(g.ringX + Math.cos(a) * (p.ringVis + 2), g.ringY + Math.sin(a) * (p.ringVis + 2), RAR[pk.def.rarity]);
    }
  }
  // 呪文を引いている
  if (g.drag) {
    const s = g.slots[g.drag.slot], r = g.ringFromFinger(g.drag.fx, g.drag.fy);
    if (s) {
      const cancel = g.inSlotBand(g.drag.fy);
      ring(r.x, r.y, s.id === 'fire1' ? p.fire1.radius : p.ice1.radius, cancel ? 'rgba(255,255,255,.4)' : s.id === 'fire1' ? '#F07A2B' : '#7FD3FF');
      spellIcon(s.id, g.drag.fx, g.drag.fy, 16);
      if (cancel) { ctx.fillStyle = '#1B2233'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('取りやめ', g.drag.fx, g.drag.fy - 26); }
    }
  }
  // ダメージの数
  ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineWidth = 3; ctx.strokeStyle = '#1B2233';
  for (const f of g.floats) { ctx.globalAlpha = 1 - f.t / p.damageTextTime; const s = fmt(f.v); ctx.strokeText(s, f.x, f.y); ctx.fillStyle = '#fff'; ctx.fillText(s, f.x, f.y); }
  ctx.globalAlpha = 1;
  // 告知
  if (g.scene === 'fight' && g.waveT < p.announce * 60) {
    ctx.font = 'bold 26px sans-serif'; ctx.lineWidth = 5; ctx.strokeText(`第${g.wave} ウェーブ`, W / 2, H / 4); ctx.fillStyle = '#fff'; ctx.fillText(`第${g.wave} ウェーブ`, W / 2, H / 4);
    if (g.wave === 1 && g.k.mode !== 'q2') { ctx.font = 'bold 15px sans-serif'; ctx.lineWidth = 4; ctx.strokeText('押さえると攻撃', W / 2, H / 4 + 30); ctx.fillText('押さえると攻撃', W / 2, H / 4 + 30); }
  }
  if (g.scene === 'cleared') { ctx.font = 'bold 26px sans-serif'; ctx.lineWidth = 5; ctx.strokeText('生き延びた！', W / 2, H / 4); ctx.fillStyle = '#FFE14D'; ctx.fillText('生き延びた！', W / 2, H / 4); }
  if (g.scene === 'destroyed') { ctx.fillStyle = 'rgba(27,34,51,.3)'; ctx.fillRect(0, 0, W, H); ctx.font = 'bold 26px sans-serif'; ctx.lineWidth = 5; ctx.strokeText('塔が壊された', W / 2, H / 4); ctx.fillStyle = '#fff'; ctx.fillText('塔が壊された', W / 2, H / 4); }
}

// ---------- HUD ----------
const hpEl = document.getElementById('hp')!, hpFill = document.getElementById('hpfill')!, waveEl = document.getElementById('wave')!, coinsEl = document.getElementById('coins')!, timerEl = document.getElementById('timer')!;
function hud(): void {
  hpEl.textContent = String(Math.ceil(Math.max(0, g.towerHp)));
  const r = g.towerHp / g.towerMax; hpFill.style.width = Math.max(0, r * 100) + '%'; hpFill.classList.toggle('danger', r < p.towerDanger);
  waveEl.textContent = `第${g.wave}`; coinsEl.textContent = `● ${fmt(g.coins)}`;
  const t = g.runSteps / 60;
  timerEl.textContent = g.k.mode === 'q3' ? `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}` : g.k.mode.toUpperCase();
}

// ---------- ループ（固定の1歩。テストのために速さを変えられる） ----------
let speed = 1, last = performance.now(), acc = 0, lastScene = '';
const frameMs: number[] = [];
function frame(now: number): void {
  let dt = (now - last) / 1000; last = now; if (dt > 0.25) dt = 0.25;
  frameMs.push(dt * 1000); if (frameMs.length > 300) frameMs.shift();
  if (!paused) {
    acc += dt * speed; let n = 0;
    while (acc >= STEP && n < 5 * speed) { g.step(); acc -= STEP; n++; }
    if (n >= 5 * speed) acc = 0;
  } else acc = 0;
  for (const e of g.events) {
    if (g.k.sound) audio.play(e);
    if (e === 'tenMin') toast(`${Q3_RUN_TARGET / 60}分たちました（止めません）`);
  }
  g.events.length = 0;
  if (g.scene !== lastScene) {
    lastScene = g.scene;
    if (g.scene === 'shop') { save(); openShop(); }
    else if (g.scene === 'q1end' || g.scene === 'q2end') { save(); openEnd(); }
    else if (g.scene === 'result') { save(); openResult(); }
  }
  draw(); hud();
  requestAnimationFrame(frame);
}
showCover('title');
requestAnimationFrame(frame);

// ---------- テスト用の口（Playwright が読む） ----------
(window as unknown as Record<string, unknown>).__pd = {
  get g() { return g; }, p, missing, get paused() { return paused; }, get scale() { return scale; }, get H() { return H; },
  setSpeed(v: number) { speed = v; }, start: () => doAct('start'), toScreen: (x: number, y: number) => ({ x: x * scale, y: y * scale }),
  exportString, waveLine, market: (n: number) => market(p, n), frameMs: () => frameMs.slice(), audioState: audio.audioState, panelKind: () => panelKind,
};
