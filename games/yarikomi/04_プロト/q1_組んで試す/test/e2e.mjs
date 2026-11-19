// ブラウザ（Chromium）で、最初から解くまでをタッチで操作して確かめる。前提：npm run build 済み。
// node test/e2e.mjs   スクリーンショットは screenshots/ に出す。
// 注意：これは「操作できるか」の確かめ。人が遊んだときの時間・置き間違いの数は測れない（プレイテストで測る）。
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require(process.env.PLAYWRIGHT_PATH ?? '/opt/node-tools/node_modules/playwright'); }
const { chromium, devices } = pw;
const PORT = 4179, BASE = `http://localhost:${PORT}/`;
const SHOT = fileURLToPath(new URL('../screenshots/', import.meta.url));
mkdirSync(SHOT, { recursive: true });

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok }); console.log(`${ok ? 'OK  ' : 'NG  '} ${name}${detail ? '  — ' + detail : ''}`); };

const server = spawn('node_modules/.bin/vite', ['preview', '--port', String(PORT), '--strictPort'], { stdio: 'pipe', cwd: fileURLToPath(new URL('..', import.meta.url)) });
process.on('exit', () => server.kill());
await new Promise((res, rej) => { server.stdout.on('data', d => String(d).includes('Local') && res()); setTimeout(() => rej(new Error('server timeout')), 15000); });
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
console.log('browser', browser.version());

async function newPage(opts) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [], external = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => { if (!r.url().startsWith(BASE) && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) external.push(r.url()); });
  await page.goto(BASE);
  return { ctx, page, errors, external };
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ===================== iPhone 相当（390×844、タッチ） =====================
{
  const { ctx, page, errors, external } = await newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, userAgent: devices['iPhone 13'].userAgent });
  const cdp = await ctx.newCDPSession(page);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y]) => ({ x, y })) });
  async function drag([x0, y0], [x1, y1], { hold } = {}) {
    await touch('touchStart', [[x0, y0]]);
    for (let i = 1; i <= 12; i++) { await touch('touchMove', [[x0 + (x1 - x0) * i / 12, y0 + (y1 - y0) * i / 12]]); await sleep(8); }
    if (hold) await hold();
    await touch('touchEnd', []);
    await sleep(60);
  }
  const tap = async sel => { await page.tap(sel); await sleep(80); };
  const tapAt = async (x, y) => { await page.touchscreen.tap(x, y); await sleep(80); };
  const center = async sel => { const b = await page.locator(sel).first().boundingBox(); return [b.x + b.width / 2, b.y + b.height / 2]; };
  const lift = 56;
  async function benchCell(x, y) {
    const b = await page.locator('#stage .bench').boundingBox();
    const c = b.width / 4;
    return [b.x + (x + .5) * c, b.y + (y + .5) * c];
  }
  // 浮かせた部品の下のマスに置く（指は 56px 下）
  async function dragPart(part, x, y, opts) {
    const from = await center(`.tile[data-part="${part}"]`);
    const [cx, cy] = await benchCell(x, y);
    await drag(from, [cx, cy + lift], opts);
  }
  async function boardCell(x, y) {
    const b = await page.locator('#stage .board').first().boundingBox();
    return [b.x + (x + .5) * 48, b.y + (y + .5) * 48];
  }
  const st = () => page.evaluate(() => ({ screen: window.__q1.app.screen, bench: [...window.__q1.app.bench].map(([k, v]) => [k, v.part, v.facing ?? null]), sum: window.__q1.summary() }));
  const waitIdle = async () => { await page.waitForFunction(() => !window.__q1.app.busy && !(window.__q1.app.trial?.running)); await sleep(50); };

  await page.screenshot({ path: SHOT + '01_タイトル.png' });
  // 画面：ボタンの大きさと置き場所
  await tap('[data-a="start"]');
  check('はじめる → 見る', (await st()).screen === 'look');
  await page.screenshot({ path: SHOT + '02_見る.png' });

  await tap('[data-a="toBench"]');
  check('工房（組む）に入る', (await st()).screen === 'bench');
  const vp = page.viewportSize();
  const btns = await page.$$eval('#hand button, #thumb button, .tile', els => els.map(e => ({ t: e.textContent.trim(), ...e.getBoundingClientRect().toJSON() })));
  check('組む画面のボタン・棚の札が 48×48px 以上', btns.every(b => b.width >= 48 && b.height >= 48), btns.filter(b => b.width < 48 || b.height < 48).map(b => b.t).join(',') || `${btns.length} 個`);
  check('ボタン・棚が画面の下（基準の y392 に、縦の増えた分を足した線より下）', btns.every(b => b.y >= vp.height - 640 + 392 - 1), `いちばん上 y=${Math.min(...btns.map(b => b.y)).toFixed(0)}`);
  const main = await page.locator('[data-a="build"]').boundingBox();
  check('主ボタン（組み上げる）が 高さ64・幅160 以上', main.height >= 64 && main.width >= 160, `${main.width.toFixed(0)}×${main.height.toFixed(0)}`);
  const bb = await page.locator('#stage .bench').boundingBox();
  check('作業台 4×4 のマスが 72px', Math.abs(bb.width / 4 - 72) < .5, `${(bb.width / 4).toFixed(1)}px`);
  check('ページの横スクロールがない', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  // 組む：板3（ドラッグ2つ、タップ→タップ1つ）。下の段に並べる
  await dragPart('plank', 0, 3);
  await dragPart('plank', 1, 3, { hold: async () => { await page.screenshot({ path: SHOT + '03_組む_ドラッグ中.png' }); } });
  await tap('.tile[data-part="plank"]');
  await tapAt(...await benchCell(2, 3));
  let s = await st();
  check('板3つが作業台の下の段に置かれる（ドラッグ2・タップ1）', JSON.stringify(s.bench.map(b => b[0]).sort()) === '[12,13,14]' && s.bench.every(b => b[1] === 'plank'), JSON.stringify(s.bench));
  // 置けない：部品があるマスへドラッグ
  await dragPart('pebble', 1, 3);
  s = await st();
  check('部品のあるマスには置けず、置けなかった回数に数える', s.bench.length === 3 && s.sum.dropMiss === 1, `dropMiss=${s.sum.dropMiss}`);
  check('説明の帯に置けない理由', (await page.textContent('#band')).includes('置けない'));
  await page.screenshot({ path: SHOT + '04_組む_板3.png' });

  // 試す：崖。人形を東の端に → 送る → ずれる → 落ちる
  await tap('[data-a="toTrial"]');
  check('試し場（崖）に切り替わる', (await st()).screen === 'trial');
  await tap('[data-a="tDoll"]');
  await tapAt(...await boardCell(3, 2));
  await sleep(100);
  const band1 = await page.textContent('#band');
  check('人形を置くと「次：…ずれる」が説明の帯に出る（次の1手の印）', band1.includes('ずれる'), band1);
  await page.screenshot({ path: SHOT + '05_試す_次の1手の印.png' });
  await tap('[data-a="tStep"]'); await waitIdle();
  const band15 = await page.textContent('#band');
  check('1手目：人形を乗せた道具が東へずれた（帯に結果が残る）', band15.includes('1手目') && band15.includes('ずれた'), band15);
  await tap('[data-a="tStep"]'); await waitIdle();
  await tap('[data-a="tStep"]'); await waitIdle();
  const band2 = await page.textContent('#band');
  check('3手目で道具と人形が谷底へ落ちる', band2.includes('3手目') && band2.includes('谷底へ落ちた'), band2);
  await page.screenshot({ path: SHOT + '06_試す_外れた.png' });

  // 直さずに挑む → 外れる（死ぬ）
  await tap('[data-a="toBench2"]');
  await tap('[data-a="build"]');
  check('組み上げると見るへ戻り、道具を持つ', (await page.textContent('#hand')).includes('持っている道具'));
  await tap('[data-a="challenge"]');
  check('挑むに入る', (await st()).screen === 'ch');
  async function confirmCard(card, candLabel) {
    await tap(`[data-a="card"][data-k="${card}"]`);
    if (candLabel) await tap(`[data-a="cand"]:has-text("${candLabel}")`);
    await tap('[data-a="confirm"]');
    await waitIdle();
  }
  await confirmCard('place');
  await confirmCard('move', '→ 入る');
  await confirmCard('move', '→ 入る');
  await confirmCard('move', '→ 入る'); // 印へ。板がずれて運ばれる
  let ch = await page.evaluate(() => ({ over: window.__q1.app.ch.over, band: document.querySelector('#band').textContent }));
  check('重りなしの板3：印へ入ると東へずれて運ばれ、解けない', ch.over === null && ch.band.includes('ずれた'), ch.band);
  let dangerBtn = '';
  for (let i = 0; i < 3; i++) {
    await tap('[data-a="wait"]');
    dangerBtn = await page.locator('[data-a="confirm"]').getAttribute('class');
    if (dangerBtn.includes('danger')) break;
    await tap('[data-a="confirm"]'); await waitIdle();
  }
  await page.screenshot({ path: SHOT + '07_挑む_危険な手.png' });
  check('次の手で死ぬとき、確定が危険の形（朱）になる', dangerBtn.includes('danger'), dangerBtn);
  await tap('[data-a="confirm"]'); await waitIdle();
  ch = await page.evaluate(() => ({ over: window.__q1.app.ch.over, dead: window.__q1.app.ch.s.dead }));
  check('当主が谷底へ落ちて、外れの画面', ch.over === 'dead', JSON.stringify(ch));
  await page.screenshot({ path: SHOT + '08_挑む_外れ.png' });

  // 直す：見る → 工房（道具がばらされて作業台に戻る）→ 板の西の端の上に石 → 試す → 止まる
  await tap('[data-a="backLook"]');
  await tap('[data-a="toBench"]');
  s = await st();
  check('工房に戻ると、組んだ道具が作業台に戻る', s.bench.length === 3);
  await dragPart('stoneWeight', 0, 2);
  s = await st();
  check('石の重りを板の西の端の上に置ける', s.bench.some(b => b[0] === 8 && b[1] === 'stoneWeight'));
  await page.screenshot({ path: SHOT + '09_組む_石で押さえる.png' });
  await tap('[data-a="toTrial"]');
  await tap('[data-a="tDoll"]');
  await tapAt(...await boardCell(3, 2));
  await tap('[data-a="tRun"]'); await waitIdle();
  const band3 = await page.textContent('#band');
  check('石で押さえると、人形を乗せても止まったまま', band3.includes('止まった'), band3);
  await page.screenshot({ path: SHOT + '10_試す_止まる.png' });

  // 挑む → 解く（盤面のマスのタップでも選ぶ）
  await tap('[data-a="toBench2"]');
  await tap('[data-a="build"]');
  await tap('[data-a="challenge"]');
  await tap('[data-a="card"][data-k="place"]');
  await page.screenshot({ path: SHOT + '11_挑む_置く.png' });
  await tap('[data-a="confirm"]'); await waitIdle();
  await tapAt(...await boardCell(1, 2)); // 盤面のマスで「→ 入る」
  const sel = await page.evaluate(() => window.__q1.app.ch.act);
  check('盤面のマスをタップして手を選べる', sel && sel.t === 'enter', JSON.stringify(sel));
  await tap('[data-a="confirm"]'); await waitIdle();
  await confirmCard('move', '→ 入る');
  await tap('[data-a="card"][data-k="move"]');
  await tap('[data-a="cand"]:has-text("→ 入る")');
  const band4 = await page.textContent('#band');
  check('印へ入る手を選ぶと「この手で解ける」', band4.includes('解ける'), band4);
  await tap('[data-a="confirm"]'); await waitIdle();
  ch = await page.evaluate(() => window.__q1.app.ch.over);
  check('解けた', ch === 'solved');
  await page.screenshot({ path: SHOT + '12_解けた.png' });

  // 記録
  const sum = (await st()).sum;
  console.log('記録の要約', JSON.stringify(sum));
  check('記録：解けた・時間がある', sum.solved && sum.solveMs > 0, `${sum.solveMs}ms（自動の操作なので人の時間ではない）`);
  check('記録：置いた 4・置けなかった 1・予行を開いた 2・挑んだ 2・死んだ 1', sum.placements === 4 && sum.dropMiss === 1 && sum.trialsEntered === 2 && sum.challengeStarts === 2 && sum.deaths === 1, JSON.stringify({ p: sum.placements, d: sum.dropMiss, t: sum.trialsEntered, c: sum.challengeStarts, x: sum.deaths }));
  check('記録：予行の送る 3・続けて 1', sum.trialSteps === 3 && sum.trialRuns === 1);
  await tap('[data-a="showLog"]');
  await page.screenshot({ path: SHOT + '13_記録.png' });
  await tap('[data-m="copy"]');
  const exported = JSON.parse(await page.inputValue('#logtext'));
  check('記録を文字で書き出せる（JSON）', exported.sessions.length >= 1 && exported.sessions.at(-1).summary.solved === true);
  await page.reload();
  const kept = await page.evaluate(() => JSON.parse(localStorage.getItem('q1.sessions') ?? '[]').length);
  check('読み込み直しても記録が端末に残る', kept >= 1, `${kept} 件`);
  check('ページのエラーがない', errors.length === 0, errors.join(' / '));
  check('外への通信がない', external.length === 0, external.join(' '));
  await ctx.close();
}

// ===================== 360×640（基準の大きさ） =====================
{
  const { ctx, page, errors } = await newPage({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await page.tap('[data-a="start"]');
  await page.tap('[data-a="toBench"]');
  const r = await page.evaluate(() => {
    const els = [...document.querySelectorAll('#top, #stage, #band, #hand, #thumb')].map(e => e.getBoundingClientRect().toJSON());
    const btn = [...document.querySelectorAll('#hand button, #thumb button, .tile')].map(e => e.getBoundingClientRect().toJSON());
    return { els, btn, sw: document.documentElement.scrollWidth };
  });
  check('360×640：全部の帯が画面に入る', r.els.every(e => e.top >= 0 && e.bottom <= 640), r.els.map(e => `${e.top.toFixed(0)}-${e.bottom.toFixed(0)}`).join(' '));
  check('360×640：ボタン・棚の札が 48px 以上で y392 より下', r.btn.every(b => b.width >= 48 && b.height >= 48 && b.y >= 391), `いちばん上 y=${Math.min(...r.btn.map(b => b.y)).toFixed(0)}`);
  check('360×640：横スクロールなし', r.sw <= 360, `scrollWidth=${r.sw}`);
  const tb = await page.$$eval('#thumb button, #hand button', els => els.map(e => ({ t: e.textContent.trim(), sw: e.scrollWidth, cw: e.clientWidth, w: e.getBoundingClientRect().width })));
  check('360×640：ボタンの字がはみ出さない', tb.every(b => b.sw <= b.cw + 1), tb.map(b => `${b.t}:${b.w.toFixed(0)}`).join(' '));
  await page.screenshot({ path: SHOT + '14_360x640_組む.png' });
  check('360×640：エラーなし', errors.length === 0, errors.join(' / '));
  await ctx.close();
}

// ===================== PC（マウス） =====================
{
  const { ctx, page, errors } = await newPage({ viewport: { width: 1280, height: 800 } });
  await page.click('[data-a="start"]');
  await page.click('[data-a="toBench"]');
  const t = await page.locator('.tile[data-part="ironWeight"]').boundingBox();
  const b = await page.locator('#stage .bench').boundingBox();
  await page.mouse.move(t.x + t.width / 2, t.y + t.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + 36, b.y + 36 + 56, { steps: 10 });
  await page.mouse.up();
  const bench = await page.evaluate(() => [...window.__q1.app.bench].map(([k, v]) => [k, v.part]));
  check('PC：マウスのドラッグで置ける', bench.length === 1 && bench[0][0] === 0 && bench[0][1] === 'ironWeight', JSON.stringify(bench));
  check('PC：エラーなし', errors.length === 0, errors.join(' / '));
  await ctx.close();
}

await browser.close();
server.kill();
const ng = results.filter(r => !r.ok);
console.log(`\n${results.length - ng.length}/${results.length} OK`);
process.exit(ng.length ? 1 : 0);
