// ブラウザ（Chromium）で、ビルドしたものを動かして確かめる。node test/e2e.mjs
// 前提：npm run build 済み。Playwright はこの環境の全体に入っているもの（/opt/node-tools）を使う。
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { replay, fingerprint } from '../src/core/sim.ts';

const require = createRequire(import.meta.url);
const pwPath = process.env.PLAYWRIGHT_PATH ?? '/opt/node-tools/node_modules/playwright';
const { chromium, devices } = require(pwPath);
const PORT = 4173, BASE = `http://localhost:${PORT}/`;
mkdirSync('test-results', { recursive: true });

const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok, detail }); console.log(`${ok ? 'OK  ' : 'NG  '} ${name}${detail ? '  — ' + detail : ''}`); };

const server = spawn('node_modules/.bin/vite', ['preview', '--port', String(PORT), '--strictPort'], { stdio: 'pipe' });
await new Promise((res, rej) => { server.stdout.on('data', d => String(d).includes('Local') && res()); setTimeout(() => rej(new Error('server timeout')), 15000); });

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
console.log('browser', browser.version());

const profiles = [
  { name: 'Pixel 7（Chromium・タッチ）', opts: devices['Pixel 7'], touch: true },
  { name: '390x844 縦（iPhone相当の画面の大きさだけ。WebKitではない）', opts: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, userAgent: devices['iPhone 13'].userAgent }, touch: true },
  { name: '360x640 縦（小さめのAndroid）', opts: { viewport: { width: 360, height: 640 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, touch: true },
  { name: 'PC 1280x800（マウス）', opts: { viewport: { width: 1280, height: 800 } }, touch: false },
];

for (const p of profiles) {
  console.log(`\n== ${p.name}`);
  const ctx = await browser.newContext({ ...p.opts, acceptDownloads: true });
  const page = await ctx.newPage();
  const external = [];
  page.on('request', r => { if (!r.url().startsWith(BASE) && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) external.push(r.url()); });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE);
  await page.waitForSelector('.cell');
  const tag = p.name.split('（')[0].replace(/\s/g, '');

  // 画面：5×5が全部見え、操作が下半分にあり、指で押せる大きさか
  const vp = page.viewportSize();
  const cells = await page.$$eval('.cell', els => els.map(e => e.getBoundingClientRect().toJSON()));
  const step = await page.$eval('#step', e => e.getBoundingClientRect().toJSON());
  const shelf = await page.$eval('#shelf', e => e.getBoundingClientRect().toJSON());
  const allIn = cells.every(c => c.top >= 0 && c.bottom <= vp.height && c.left >= 0 && c.right <= vp.width);
  check('5×5 のマスが画面に収まる', cells.length === 25 && allIn, `マス ${cells[0].width.toFixed(0)}px角`);
  check('マスが 44px 以上', cells[0].width >= 44, `${cells[0].width.toFixed(1)}px`);
  if (p.touch) check('棚と「1手進める」が画面の下半分', shelf.top > vp.height / 2 && step.top > vp.height / 2, `棚 y=${shelf.top.toFixed(0)}／ボタン y=${step.top.toFixed(0)}／高さ ${vp.height}`);
  check('ページの横スクロールがない', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  // 入力①：棚をタップ→マスをタップで置く
  const tapOrClick = async sel => p.touch ? page.tap(sel) : page.click(sel);
  await tapOrClick('.part[data-k="W"]');
  await tapOrClick('.cell[data-i="2"]');
  let st = await page.evaluate(() => window.__tc.state);
  check('タップで重りを (2,0) に置ける', st.cells[2].k === 'W');

  // 入力②：棚からマスへドラッグ（タッチは CDP で指の動きを送る。PC はマウス）
  const from = await page.$eval('.part[data-k="P"]', e => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  const to = await page.$eval('.cell[data-i="17"]', e => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  if (p.touch) {
    const cdp = await ctx.newCDPSession(page);
    const touch = (type, pt) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pt ? [{ x: pt.x, y: pt.y }] : [] });
    await touch('touchStart', from);
    for (let i = 1; i <= 10; i++) await touch('touchMove', { x: from.x + (to.x - from.x) * i / 10, y: from.y + (to.y - from.y) * i / 10 });
    await touch('touchEnd');
  } else {
    await page.mouse.move(from.x, from.y); await page.mouse.down();
    await page.mouse.move(to.x, to.y, { steps: 10 }); await page.mouse.up();
  }
  st = await page.evaluate(() => window.__tc.state);
  check('ドラッグで板を (2,3) に置ける', st.cells[17].k === 'P');

  // 次の1手の印
  check('次の1手で変わるマスに印が出る', await page.$eval('.cell[data-i="2"]', e => e.classList.contains('next')));

  // 1手進める：重りが落ち、板の上で止まる
  await page.evaluate(() => { window.__clicks = 0; document.getElementById('step').addEventListener('click', () => window.__clicks++); });
  for (let i = 0; i < 4; i++) await tapOrClick('#step');
  st = await page.evaluate(() => window.__tc.state);
  check('1手ずつ規則で動く（重りが板の上で止まる）', st.cells[12].k === 'W' && st.turn === 4, `turn=${st.turn} click=${await page.evaluate(() => window.__clicks)} 盤=${st.cells.map(c => c.k).join('')}`);
  await page.screenshot({ path: `test-results/${tag}-play.png` });

  // 決定性：ブラウザの盤面の指紋 ＝ 同じ記録を Node で再生した指紋
  const fpBrowser = await page.evaluate(() => window.__tc.fingerprint());
  const fpNode = fingerprint(replay(st.seed, st.log));
  check('ブラウザと Node で同じ指紋（同じ記録→同じ盤面）', fpBrowser === fpNode, `${fpBrowser} / ${fpNode}`);
  const golden = await page.evaluate(() => {
    const t = window.__tc, r = t.seedFrom('入力'), first = t.nextU32(t.seedFrom('谷-0001')).toString(16);
    const s = t.newGame('谷-0042'), kinds = ['P', 'W', 'S', 'F'];
    for (let i = 0; i < 10000; i++) { const n = t.nextU32(r) % 10, x = t.nextU32(r) % 5, y = t.nextU32(r) % 5;
      t.apply(s, n < 4 ? { t: 'place', x, y, k: kinds[n] } : n < 6 ? { t: 'remove', x, y } : { t: 'step' }); }
    return { first, fp: t.fp(s) };
  });
  check('乱数と1万手の指紋が Node の固定値と同じ', golden.first === '529f9503' && golden.fp === '120aa3a5', JSON.stringify(golden));

  // 音：最初のタップで AudioContext が起き、置く・進めるで音を作った
  const audio = await page.evaluate(() => ({ state: window.__tc.audioState(), n: window.__tc.audioLog.length }));
  check('音：AudioContext が running、音を鳴らす呼び出しがあった', audio.state === 'running' && audio.n >= 5, JSON.stringify(audio));
  const peak = await page.evaluate(async () => {
    const oc = new OfflineAudioContext(1, 44100 * 0.2, 44100);
    window.__tc.blip(440, oc);
    const buf = await oc.startRendering();
    return Math.max(...buf.getChannelData(0).map(Math.abs));
  });
  check('音：合成した波形が無音でない（OfflineAudioContext）', peak > 0.05, `peak=${peak.toFixed(3)}`);

  // 端末内保存：読み込み直しても続きから
  await page.reload(); await page.waitForSelector('.cell');
  check('再読み込みで続きから（localStorage）', await page.evaluate(() => window.__tc.fingerprint()) === fpBrowser);

  // 書き出し（文字・ファイル）と読み込み
  await tapOrClick('#io-btn');
  await tapOrClick('#exp');
  const text = await page.$eval('#io-text', e => e.value);
  const [dl] = await Promise.all([page.waitForEvent('download'), tapOrClick('#dl')]);
  const dlPath = `test-results/${tag}-${dl.suggestedFilename()}`;
  await dl.saveAs(dlPath);
  check('ファイルに保存（ダウンロード）が文字の書き出しと同じ', readFileSync(dlPath, 'utf8') === text, dl.suggestedFilename());
  await page.evaluate(k => localStorage.removeItem(k), await page.evaluate(() => window.__tc.SAVE_KEY));
  await page.reload(); await page.waitForSelector('.cell');
  const fresh = await page.evaluate(() => window.__tc.fingerprint());
  await tapOrClick('#io-btn');
  await page.fill('#io-text', text);
  await tapOrClick('#imp');
  check('保存を消したあと、文字から読み込んで元どおり', fresh !== fpBrowser && await page.evaluate(() => window.__tc.fingerprint()) === fpBrowser);
  await page.evaluate(k => localStorage.removeItem(k), await page.evaluate(() => window.__tc.SAVE_KEY));
  await page.reload(); await page.waitForSelector('.cell');
  await page.setInputFiles('#file', dlPath);
  await page.waitForFunction(fp => window.__tc.fingerprint() === fp, fpBrowser, { timeout: 3000 }).catch(() => {});
  check('ファイルから読み込んで元どおり', await page.evaluate(() => window.__tc.fingerprint()) === fpBrowser, (await page.textContent('#log')).slice(0, 80));
  await tapOrClick('#io-btn');
  await page.fill('#io-text', text.slice(0, -1) + (text.endsWith('0') ? '1' : '0'));
  await tapOrClick('#imp');
  check('書き換えた文字は読み込みを断る', (await page.textContent('#log')).includes('読み込めなかった') && await page.evaluate(() => window.__tc.fingerprint()) === fpBrowser);

  // オフライン：Service Worker が付いたあと、ネットを切って開き直す
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload(); await page.waitForSelector('.cell');
  const controlled = await page.evaluate(() => !!navigator.serviceWorker.controller);
  await ctx.setOffline(true);
  let offlineOk = false;
  try { await page.reload(); await page.waitForSelector('.cell', { timeout: 5000 }); offlineOk = await page.evaluate(() => window.__tc.fingerprint()) === fpBrowser; } catch (e) { offlineOk = false; }
  await ctx.setOffline(false);
  check('オフラインで開き直しても遊べる（Service Worker）', controlled && offlineOk, `controlled=${controlled}`);
  check('外部への通信がない（CDN なし）', external.length === 0, external.join(', '));
  check('ページのエラーがない', errors.length === 0, errors.join(' | '));

  // 性能の目安：CPU を 4倍・6倍遅くして、1手ぶん（規則＋印の計算＋描画）の時間を見る
  if (p.touch) {
    const cdp = await ctx.newCDPSession(page);
    for (const rate of [4, 6]) {
      await cdp.send('Emulation.setCPUThrottlingRate', { rate });
      const ms = await page.evaluate(async () => {
        const t = [];
        for (let i = 0; i < 30; i++) { const t0 = performance.now(); document.getElementById('step').click(); await new Promise(r => requestAnimationFrame(() => r())); t.push(performance.now() - t0); }
        t.sort((a, b) => a - b); return { median: t[15], max: t[29] };
      });
      check(`CPU ${rate}倍遅い：1手の時間（次の描画まで）`, ms.max < 100, `中央 ${ms.median.toFixed(1)}ms／最大 ${ms.max.toFixed(1)}ms`);
    }
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  }
  await ctx.close();
}

await browser.close();
server.kill();
writeFileSync('test-results/e2e.json', JSON.stringify(results, null, 2));
const ng = results.filter(r => !r.ok);
console.log(`\n${results.length - ng.length}/${results.length} OK`);
process.exit(ng.length ? 1 : 0);
