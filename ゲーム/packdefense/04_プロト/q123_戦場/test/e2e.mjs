// ビルドしたものを iPhone のまね（Chromium）で動かして確かめる。npm run build && npm run e2e
// iPhone のまね＝画面の大きさ・画素比・タッチ・UA だけ。中身は Chromium（WebKit はこの環境に入らない。技術選定 5.5）。
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium, devices } = require(process.env.PLAYWRIGHT_PATH ?? '/opt/node-tools/node_modules/playwright');
const PORT = 4174, BASE = `http://localhost:${PORT}/`;
const SHOTS = fileURLToPath(new URL('../screenshots/', import.meta.url));
mkdirSync(SHOTS, { recursive: true }); mkdirSync('test-results', { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'OK  ' : 'NG  '} ${name}${detail ? '  — ' + detail : ''}`); };
const server = spawn('node_modules/.bin/vite', ['preview', '--port', String(PORT), '--strictPort'], { stdio: 'pipe' });
process.on('exit', () => server.kill());
await new Promise((res, rej) => { server.stdout.on('data', d => String(d).includes('Local') && res()); setTimeout(() => rej(new Error('server timeout')), 15000); });
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
console.log('browser', browser.version());
const sleep = ms => new Promise(r => setTimeout(r, ms));

const SIZES = [
  { tag: '390x844', dev: 'iPhone 13', viewport: { width: 390, height: 844 }, full: true },   // ホーム画面のアプリの大きさ
  { tag: '375x667', dev: 'iPhone SE (3rd gen)', viewport: { width: 375, height: 667 }, full: true },
  { tag: '390x664', dev: 'iPhone 13', viewport: { width: 390, height: 664 }, full: false },   // Safari のバーがあるとき（Playwright の既定）
];
const summary = {};

for (const S of SIZES) {
  console.log(`\n== ${S.tag}（${S.dev} のまね）`);
  const ctx = await browser.newContext({ ...devices[S.dev], viewport: S.viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [], external = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('request', r => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('blob:') && !u.startsWith('data:')) external.push(u); });
  await page.goto(BASE);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await page.waitForFunction(() => window.__pd);
  const cdp = await ctx.newCDPSession(page);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map((p, i) => ({ x: p.x, y: p.y, id: i })) });
  const scr = (x, y) => page.evaluate(([x, y]) => window.__pd.toScreen(x, y), [x, y]);
  const G = f => page.evaluate(f);
  const shot = async name => { const f = `${SHOTS}${S.tag}_${name}.png`; await page.screenshot({ path: f }); return f; };
  const clickAct = async (act, v) => { await page.locator(v ? `[data-act="${act}"][data-v="${v}"]:visible` : `[data-act="${act}"]:visible`).first().click(); await sleep(260); };
  const setKnobs = o => page.evaluate(o => Object.assign(window.__pd.g.k, o), o);
  const start = async () => { await page.evaluate(() => window.__pd.start()); await sleep(250); };
  /** 素朴な指：塔にいちばん近い魔物（近くにいなければ降ったパック）へ、輪が乗るように指を置く */
  let fingerDown = false;
  const botTick = async (opts = {}) => {
    const t = await page.evaluate(o => {
      const g = window.__pd.g; if (g.scene !== 'fight') return null;
      let best = null, bd = 1e9;
      for (const m of g.monsters) { if (!g.visible(m)) continue; const d = Math.hypot(m.x - g.towerX, m.y - g.towerY); if (d < bd) { bd = d; best = m; } }
      const pk = g.packs.find(q => q.tele <= 0);
      const tg = pk && !o.noPack && (!best || bd > 130) ? pk : best;
      if (!tg) return { none: true };
      return { x: tg.x, y: Math.min(window.__pd.H - 2, tg.y + g.k.ringOffset) };
    }, opts);
    if (!t || t.none) { if (fingerDown) { await touch('touchEnd', []); fingerDown = false; } return t; }
    const s = await scr(t.x, t.y);
    await touch(fingerDown ? 'touchMove' : 'touchStart', [s]); fingerDown = true;
    return t;
  };
  const release = async () => { if (fingerDown) { await touch('touchEnd', []); fingerDown = false; } };
  const playUntil = async (cond, maxMs, opts) => { const t0 = Date.now(); while (Date.now() - t0 < maxMs) { if (await G(cond)) break; await botTick(opts); await sleep(40); } await release(); };

  // --- 起動
  check(`[${S.tag}] 起動して「タップで始める」が出る`, await page.locator('#cover.on [data-act="start"]').isVisible());
  check(`[${S.tag}] CSV の名前がすべて読めた`, (await G(() => window.__pd.missing.length)) === 0);
  const noScroll = await G(() => document.documentElement.scrollWidth <= window.innerWidth && document.documentElement.scrollHeight <= window.innerHeight);
  check(`[${S.tag}] 横にも縦にもスクロールしない`, noScroll);
  if (S.tag === '390x844') await shot('01_title');
  await page.click('#cover [data-act="start"]'); await sleep(300);
  check(`[${S.tag}] タップで Q1 が始まる（場面 fight、音 running）`, (await G(() => window.__pd.g.scene)) === 'fight', await G(() => window.__pd.audioState()));
  const hud = await page.locator('#hud').boundingBox(), pause = await page.locator('#pause').boundingBox();
  check(`[${S.tag}] HUD が上の端、一時停止は 48×48`, hud.y < 60 && pause.width >= 48 && pause.height >= 48, `hud y=${hud.y} pause ${pause.width}x${pause.height}`);

  // --- 輪のずらし（つまみ）
  const ringAt = async (fy) => { const s = await scr(200, fy); await touch('touchStart', [s]); await sleep(80); const r = await G(() => ({ y: window.__pd.g.ringY, on: window.__pd.g.fingerOn })); await touch('touchEnd', []); await sleep(50); return r; };
  let r = await ringAt(500);
  check(`[${S.tag}] 輪が指の 56 上に出る（既定）`, r.on && Math.abs(r.y - 444) < 1.5, `ringY=${r.y.toFixed(1)}`);
  await page.click('#pause'); await sleep(250);
  await clickAct('knobsP'); await clickAct('knob', 'ringOffset=72');
  await page.locator('#sf [data-act="pause"]').click(); await sleep(250); await clickAct('resume');
  r = await ringAt(500);
  check(`[${S.tag}] つまみで 72 にすると輪が 72 上に`, Math.abs(r.y - 428) < 1.5, `ringY=${r.y.toFixed(1)}`);
  for (const off of [0, 40]) { await setKnobs({ ringOffset: off }); r = await ringAt(500); check(`[${S.tag}] ずらし ${off}`, Math.abs(r.y - (500 - off)) < 1.5, `ringY=${r.y.toFixed(1)}`); }
  await setKnobs({ ringOffset: 56 });
  const band = await G(() => ({ rb: window.__pd.g.reachBottom, H: window.__pd.H }));
  check(`[${S.tag}] 南の打てない帯の幅（ずらし56）`, Math.abs((band.H - band.rb) - 22) < 0.5, `${(band.H - band.rb).toFixed(1)}px`);

  // --- 塔の高さ
  await setKnobs({ towerY: 0.55 }); await start();
  const ty = await G(() => ({ y: window.__pd.g.towerY, H: window.__pd.H }));
  check(`[${S.tag}] 塔の高さ 55% が効く`, ty.y === Math.round(ty.H * 0.55), `towerY=${ty.y} H=${ty.H.toFixed(0)}`);
  await setKnobs({ towerY: 0.5 }); await start();

  // --- Q1：1ウェーブ遊ぶ（速さ3倍、素朴な指）
  await page.evaluate(() => window.__pd.setSpeed(3));
  await playUntil(() => window.__pd.g.waveT > 60 * 9 && window.__pd.g.fingerOn, 8000);
  if (S.tag !== '390x664') {
    // 輪が出ているところを撮る
    await botTick(); await page.evaluate(() => window.__pd.setSpeed(0)); await sleep(120); await shot('02_q1_playing'); await page.evaluate(() => window.__pd.setSpeed(3));
  }
  await playUntil(() => window.__pd.g.scene === 'q1end', 40000);
  const q1 = await G(() => { const g = window.__pd.g; return { scene: g.scene, log: g.logs[g.logs.length - 1], panel: window.__pd.panelKind() }; });
  check(`[${S.tag}] Q1：第1ウェーブが終わり、Q1 の結果の板が出る`, q1.scene === 'q1end' && q1.panel === 'end', `${q1.log?.result} ${q1.log?.time.toFixed(1)}秒 塔${q1.log?.towerHpEnd}`);
  check(`[${S.tag}] Q1：指の当たりが記録される`, q1.log?.hitsMonster > 0, `当たり${q1.log?.hitsMonster} 押さえ${q1.log?.presses} 当たらない押さえ${q1.log?.whiffPresses} 塔の傷${JSON.stringify(q1.log?.towerDmg)}`);
  summary[S.tag] = { q1: q1.log };
  if (S.tag !== '390x664') await shot('03_q1_end');

  // --- Q2：S2（置き場）→ 引いて使う
  await setKnobs({ mode: 'q2', spellMode: 'S2', forceSpell: true }); await start();
  await playUntil(() => window.__pd.g.slots.length > 0 || window.__pd.g.scene !== 'fight', 25000);
  const sl = await G(() => ({ n: window.__pd.g.slots.length, rects: window.__pd.g.slotRects, opened: window.__pd.g.stat.packsOpened }));
  check(`[${S.tag}] Q2 S2：開けた呪文が置き場に入る`, sl.n > 0, `置き場${sl.n} 開けた${sl.opened}`);
  if (sl.n > 0) {
    if (S.tag !== '390x664') { await page.evaluate(() => window.__pd.setSpeed(0)); await shot('04_q2_S2_slot'); }
    const casts0 = await G(() => window.__pd.g.stat.spellCasts);
    const r0 = sl.rects[0], a = await scr(r0.x + r0.w / 2, r0.y + r0.h / 2);
    const tgt = await G(() => { const g = window.__pd.g; const m = g.monsters.filter(m => g.visible(m))[0]; return m ? { x: m.x, y: m.y + g.k.ringOffset } : { x: g.towerX, y: g.towerY + 120 }; });
    const b = await scr(tgt.x, Math.min(tgt.y, r0.y - 30));
    await touch('touchStart', [a]); await sleep(60);
    for (let i = 1; i <= 6; i++) { await touch('touchMove', [{ x: a.x + (b.x - a.x) * i / 6, y: a.y + (b.y - a.y) * i / 6 }]); await sleep(30); }
    if (S.tag !== '390x664') await shot('05_q2_S2_drag');
    await touch('touchEnd', []); await page.evaluate(() => window.__pd.setSpeed(3)); await sleep(400);
    const casts1 = await G(() => window.__pd.g.stat.spellCasts + window.__pd.g.logs.filter(s => s.run === window.__pd.g.runIndex).reduce((a, s) => a + s.spellCasts, 0));
    check(`[${S.tag}] Q2 S2：置き場から戦場へ引いて離すと呪文が起きる`, casts1 > casts0, `呪文 ${casts0}→${casts1}`);
  }
  await playUntil(() => window.__pd.g.scene !== 'fight' && window.__pd.g.scene !== 'cleared', 30000);
  // S1
  await setKnobs({ mode: 'q2', spellMode: 'S1' }); await start();
  await playUntil(() => window.__pd.g.stat.spellCasts > 0 || window.__pd.g.scene !== 'fight', 25000);
  const s1 = await G(() => ({ casts: window.__pd.g.stat.spellCasts, slots: window.__pd.g.slots.length, opened: window.__pd.g.stat.packsOpened }));
  check(`[${S.tag}] Q2 S1：開けた瞬間に呪文が起き、置き場は無い`, s1.casts > 0 && s1.slots === 0, JSON.stringify(s1));
  if (S.tag === '390x844') { await page.evaluate(() => window.__pd.setSpeed(0)); await shot('06_q2_S1'); await page.evaluate(() => window.__pd.setSpeed(3)); }
  // Q2 を最後まで（第2〜4）。ショップは見習いを買えるだけ買う
  const q2t0 = Date.now();
  while (Date.now() - q2t0 < 90000) {
    const sc = await G(() => window.__pd.g.scene);
    if (sc === 'q2end') break;
    if (sc === 'shop') {
      if (S.tag === '390x844' && !summary.shopShot) { summary.shopShot = await shot('07_shop'); }
      while (await page.locator('[data-act="buy"][data-v="novice"]:not([disabled])').count()) await clickAct('buy', 'novice');
      await clickAct('next');
    } else { await botTick(); await sleep(40); }
  }
  await release();
  const q2 = await G(() => { const g = window.__pd.g; return { scene: g.scene, waves: g.logs.filter(s => s.run === g.runIndex) }; });
  check(`[${S.tag}] Q2：第2〜4ウェーブを通して遊べる（ショップを2回通る）`, q2.scene === 'q2end', q2.waves.map(s => `W${s.wave}:${s.result} 開けた${s.packsOpened} 開けるまで[${s.openDelays.map(x => x.toFixed(1))}] 呪文${s.spellCasts}`).join(' / '));
  summary[S.tag].q2 = q2.waves;
  if (S.tag === '390x844') await shot('08_q2_end');

  // --- Q3：自動化の3段（指を離したまま 20秒）
  const autoRes = {};
  for (const lv of [0, 1, 3]) {
    await setKnobs({ mode: 'q3', auto: lv, sameSeed: true }); await start();
    await page.evaluate(() => window.__pd.setSpeed(4));
    await page.waitForFunction(() => window.__pd.g.waveT >= 60 * 20 || window.__pd.g.scene !== 'fight', null, { timeout: 30000 });
    autoRes[lv] = await G(() => ({ auto: window.__pd.g.stat.dmg.auto, hp: window.__pd.g.towerHp, kills: window.__pd.g.stat.kills }));
    if (lv === 1 && S.tag === '390x844') { await page.evaluate(() => window.__pd.setSpeed(0)); await shot('09_q3_auto_mid'); }
  }
  check(`[${S.tag}] Q3：自動化なしは自動の傷 0`, autoRes[0].auto === 0, JSON.stringify(autoRes[0]));
  check(`[${S.tag}] Q3：自動化 中で自動の傷が出る`, autoRes[1].auto > 0, JSON.stringify(autoRes[1]));
  check(`[${S.tag}] Q3：強（指と同じ）は中より強い`, autoRes[3].auto > autoRes[1].auto, JSON.stringify(autoRes[3]));
  summary[S.tag].auto = autoRes;

  // --- Q3：1ランを最後まで（390x844 だけ。速さ8倍、素朴な指、自動=中）→ 結果 → 強化画面 → 次のラン
  if (S.tag === '390x844') {
    await setKnobs({ mode: 'q3', auto: 1, sameSeed: false }); await start();
    await page.evaluate(() => window.__pd.setSpeed(8));
    const t0 = Date.now();
    while (Date.now() - t0 < 240000) {
      const sc = await G(() => window.__pd.g.scene);
      if (sc === 'result') break;
      if (sc === 'shop') { while (await page.locator('[data-act="buy"][data-v="novice"]:not([disabled])').count()) await clickAct('buy', 'novice'); await clickAct('next'); }
      else { await botTick({ noPack: false }); await sleep(30); }
    }
    await release();
    const res = await G(() => ({ scene: window.__pd.g.scene, info: window.__pd.g.resultInfo, fame: window.__pd.g.meta.fame, logs: window.__pd.g.logs.filter(s => s.run === window.__pd.g.runIndex) }));
    check('[390x844] Q3：ランが終わり、結果の画面（名声）が出る', res.scene === 'result', `第${res.info.reached}まで ${(res.info.time / 60).toFixed(1)}分（ゲームの時間） 名声+${Math.floor(res.info.fame)}`);
    summary.q3run = { reached: res.info.reached, minutes: res.info.time / 60, fame: res.info.fame, waves: res.logs.map(s => ({ w: s.wave, t: +s.time.toFixed(1), dmg: s.dmg, hero: s.heroesEnd })) };
    await shot('10_q3_result');
    await clickAct('toUpgrade');
    await shot('11_upgrade');
    const f0 = await G(() => window.__pd.g.meta.fame);
    await clickAct('up', 'tapDmg');
    const f1 = await G(() => ({ fame: window.__pd.g.meta.fame, lv: window.__pd.g.meta.up.tapDmg }));
    check('[390x844] 強化画面で名声を払って強くできる', f1.fame < f0 && f1.lv === 2, `名声 ${Math.floor(f0)}→${Math.floor(f1.fame)} 段${f1.lv}`);
    await clickAct('start');
    check('[390x844] 「ランに出る」で第1ウェーブから', (await G(() => [window.__pd.g.scene, window.__pd.g.wave].join())) === 'fight,1');
  }

  // --- 記録を書き出す
  await page.evaluate(() => window.__pd.setSpeed(1));
  await page.click('#pause'); await sleep(250); await clickAct('export');
  const txt = await page.locator('#out').inputValue();
  check(`[${S.tag}] 記録が書き出せる（ウェーブの行・置き間違い・傷の割合・開けるまで）`, /W1 /.test(txt) && /置き間違い/.test(txt) && /傷の割合/.test(txt) && /開けるまで/.test(txt), `${txt.split('\n').length}行 ${txt.length}文字`);
  writeFileSync(`test-results/export_${S.tag}.txt`, txt);
  if (S.tag !== '390x664') await shot('12_export');
  await page.locator('#sf [data-act="pause"]').click(); await sleep(250); await clickAct('knobsP');
  if (S.tag === '390x844') await shot('13_knobs');
  const btns = await page.locator('#sheet button').evaluateAll(bs => bs.filter(b => b.offsetParent).map(b => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height)));
  check(`[${S.tag}] つまみの板のボタンが 48 以上`, btns.every(v => v >= 47.5), `最小 ${Math.min(...btns).toFixed(1)}`);

  // フレームの間隔（速さ1、Q1）
  await page.locator('#sf [data-act="start"]').click(); await sleep(300);
  await setKnobs({ mode: 'q1' });
  await sleep(2500);
  const fm = await G(() => window.__pd.frameMs().slice(-120));
  const avg = fm.reduce((a, b) => a + b, 0) / fm.length, over = fm.filter(x => x > 17.5).length;
  check(`[${S.tag}] フレームの間隔（この環境の参考）`, avg < 20, `平均 ${avg.toFixed(1)}ms、17.5ms 超 ${over}/${fm.length}`);
  check(`[${S.tag}] ページのエラーなし・外への通信なし`, errors.length === 0 && external.length === 0, [...errors, ...external].slice(0, 3).join(' | '));
  await ctx.close();
}
await browser.close();
const ng = results.filter(r => !r.ok).length;
console.log(`\n${results.length - ng}/${results.length} 通った`);
writeFileSync('test-results/e2e.json', JSON.stringify({ results, summary }, null, 1));
process.exit(ng ? 1 : 0);
