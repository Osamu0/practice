// ブラウザ（Chromium）で、ビルドしたものを iPhone 相当の画面で動かして確かめる。node test/e2e.mjs
// iPhone 相当 = 画面の大きさ・画素比・タッチ・UA だけ。中身は Chromium（WebKit はこの環境に入らなかった）。
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium, devices } = require(process.env.PLAYWRIGHT_PATH ?? '/opt/node-tools/node_modules/playwright');
const PORT = 4173, BASE = `http://localhost:${PORT}/`;
mkdirSync('test-results', { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok, detail }); console.log(`${ok ? 'OK  ' : 'NG  '} ${name}${detail ? '  — ' + detail : ''}`); };
const server = spawn('node_modules/.bin/vite', ['preview', '--port', String(PORT), '--strictPort'], { stdio: 'pipe' });
process.on('exit', () => server.kill());
await new Promise((res, rej) => { server.stdout.on('data', d => String(d).includes('Local') && res()); setTimeout(() => rej(new Error('server timeout')), 15000); });
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
console.log('browser', browser.version());
const sleep = ms => new Promise(r => setTimeout(r, ms));

for (const devName of ['iPhone 17', 'iPhone SE (3rd gen)']) {
  console.log(`\n== ${devName}（${JSON.stringify(devices[devName].viewport)} ×${devices[devName].deviceScaleFactor}）`);
  const ctx = await browser.newContext({ ...devices[devName], acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [], external = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith('blob:') && !u.startsWith('data:')) external.push(u); });
  await page.goto(BASE);
  await page.waitForFunction(() => window.__pd);
  const cdp = await ctx.newCDPSession(page);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map((p, i) => ({ x: p.x, y: p.y, id: i })) });
  // 戦場の論理の点 → 画面の点（CSS px）
  const toScreen = async (x, y) => page.evaluate(([x, y]) => {
    const a = window.__pd.toWorld(0, 0), b = window.__pd.toWorld(100, 100);
    const sx = 100 / (b.x - a.x), sy = 100 / (b.y - a.y);
    return { x: (x - a.x) * sx, y: (y - a.y) * sy };
  }, [x, y]);

  // --- 始める：最初のタップで一時停止がとけ、音が起きる
  check('はじめは止まっていて「タップで始める」', await page.evaluate(() => window.__pd.paused));
  await page.tap('#cover');
  await sleep(200);
  check('タップで始まる', !(await page.evaluate(() => window.__pd.paused)));
  check('音：最初のタップで AudioContext が running', (await page.evaluate(() => window.__pd.audio.audioState())) === 'running');

  // --- 画面：上の端の数字が見え、横にはみ出さない
  const vp = page.viewportSize();
  const hud = await page.$eval('#hud', e => e.getBoundingClientRect().toJSON());
  check('数字（HUD）が画面の上の端にある', hud.top >= 0 && hud.bottom < vp.height * 0.12, `y=${hud.top.toFixed(0)}〜${hud.bottom.toFixed(0)}`);
  check('横スクロールがない', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  // --- タッチ：押さえ続け、ずらした輪の当たり
  await page.evaluate(() => { const w = window.__pd.world; w.spawnPerSec = 0; w.enemy.n = 0; w.pack.n = 0;
    const add = (x, y) => { const i = w.enemy.add(x, y); w.enemy.a[i] = 1000; w.enemy.b[i] = 1000; return i; };
    add(180, 250); add(180, 298); });
  const off = await page.evaluate(() => window.__pd.data.settings.ringOffset);
  const finger = await toScreen(180, 250 + off);
  await touch('touchStart', [finger]);
  await sleep(100);
  const st0 = await page.evaluate(() => { const w = window.__pd.world; return { on: w.ringOn, x: w.ringX, y: w.ringY, t: w.t, hp: [w.enemy.a[0], w.enemy.a[1]] }; });
  check('押さえると、輪が指の少し上に出る', st0.on && Math.abs(st0.x - 180) < 1.5 && Math.abs(st0.y - 250) < 1.5, `指 y=${(250 + off)} → 輪 (${st0.x.toFixed(1)}, ${st0.y.toFixed(1)})、ずらし ${off}（論理px）`);
  await sleep(1000);
  const st1 = await page.evaluate(() => { const w = window.__pd.world; return { t: w.t, hp: [w.enemy.a[0], w.enemy.a[1]] }; });
  const hits = st0.hp[0] - st1.hp[0] + 0, steps = st1.t - st0.t;
  const expect = Math.floor(steps / 6);
  check('押さえ続けると攻撃し続ける（0.1秒ごと）', Math.abs(hits - expect) <= 1 && hits >= 7, `${steps}歩（${(steps / 60).toFixed(2)}秒）で ${hits}回`);
  check('指の真下の魔物には当たらない', st1.hp[1] === 1000);
  check('ページが拡大・スクロールされていない', await page.evaluate(() => (visualViewport?.scale ?? 1) === 1 && scrollY === 0));
  // 2本めの指は無視する
  await touch('touchMove', [finger, { x: finger.x + 120, y: finger.y + 120 }]);
  await sleep(50);
  const st2 = await page.evaluate(() => ({ x: window.__pd.world.ringX }));
  check('2本めの指では輪が動かない', Math.abs(st2.x - 180) < 1.5);
  const moved = { x: finger.x + 60, y: finger.y };
  await touch('touchMove', [moved]);
  await sleep(50);
  const st3 = await page.evaluate(() => ({ x: window.__pd.world.ringX }));
  check('指を動かすと輪がついてくる', st3.x > 200, `輪 x=${st3.x.toFixed(1)}`);
  await touch('touchEnd', []);
  await sleep(50);
  const hp2 = await page.evaluate(() => window.__pd.world.enemy.a[0]);
  await sleep(400);
  check('離すと攻撃が止まる', !(await page.evaluate(() => window.__pd.world.ringOn)) && (await page.evaluate(() => window.__pd.world.enemy.a[0])) === hp2);

  // --- パックを押さえて開ける → 英雄、開封の音
  await page.evaluate(() => { const w = window.__pd.world; w.enemy.n = 0; w.addPack(100, 560, 3); });
  const pf = await toScreen(100, 560 + off);
  await touch('touchStart', [pf]); await sleep(900); await touch('touchEnd', []);
  const op = await page.evaluate(() => ({ opened: window.__pd.world.opened, heroes: window.__pd.world.hero.n, log: window.__pd.audio.audioLog.slice(-30) }));
  check('パックを押さえると開き、英雄が立つ', op.opened === 1 && op.heroes >= 1);
  check('開封の音を鳴らす呼び出しがある', op.log.includes('open'));

  // --- 音：OfflineAudioContext で同じ合成音を作り、無音でない
  const peak = await page.evaluate(async () => {
    const oc = new OfflineAudioContext(1, 44100 * 0.5, 44100);
    window.__pd.audio.play('open', oc, oc.destination);
    const buf = await oc.startRendering(); let m = 0; for (const v of buf.getChannelData(0)) m = Math.max(m, Math.abs(v)); return m;
  });
  check('合成音の波形が無音でない', peak > 0.05, `最大 ${peak.toFixed(2)}`);
  // --- 音：resume が返ってこないとき、作り直す（iOS 26 のホーム画面アプリの報告への手当ての、筋道だけの確かめ）
  const rec = await page.evaluate(async () => {
    const a = window.__pd.audio; const orig = AudioContext.prototype.resume;
    await new Promise(r => { a.suspendForBackground(); setTimeout(r, 100); });
    AudioContext.prototype.resume = () => new Promise(() => {});
    a.unlock(); await new Promise(r => setTimeout(r, 800));
    AudioContext.prototype.resume = orig;
    const after1 = a.audioState(); a.unlock(); await new Promise(r => setTimeout(r, 200));
    return { recreated: a.recreated, after1, after2: a.audioState() };
  });
  check('resume が返らないと AudioContext を作り直し、次のタップで鳴る', rec.recreated === 1 && rec.after1 === 'none' && rec.after2 === 'running', JSON.stringify(rec));

  // --- 裏に回ったら一時停止
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
  const t0 = await page.evaluate(() => window.__pd.world.t); await sleep(500); const t1 = await page.evaluate(() => window.__pd.world.t);
  check('裏に回ったら一時停止（時間が進まない）', t0 === t1 && await page.evaluate(() => window.__pd.paused));
  check('裏に回ったら音を止める', (await page.evaluate(() => window.__pd.audio.audioState())) === 'suspended');
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
  check('戻ったら「タップで再開」が出ている', await page.$eval('#cover', e => !e.classList.contains('off') && e.textContent.includes('再開')));
  await page.tap('#cover'); await sleep(300);
  check('再開のタップで動き出し、音も running', !(await page.evaluate(() => window.__pd.paused)) && (await page.evaluate(() => window.__pd.audio.audioState())) === 'running');

  // --- 保存：ショップが開いたら保存 → パックを買う → ウェーブの始まりで保存 → 再読み込みで同じ形
  await page.evaluate(() => { window.__pd.world.coins = 10; window.__pd.openShop(); });
  let saved = await page.evaluate(() => JSON.parse(atob(localStorage.getItem('packdefense.techcheck.v1').split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))));
  check('ショップが開いた瞬間に保存', saved.phase === 'shop' && saved.wave === 2);
  const btn = await page.$eval('#buy', e => e.getBoundingClientRect().toJSON());
  check('ショップのボタンが 44px 以上', btn.height >= 44, `${btn.height.toFixed(0)}px`);
  await page.tap('#buy'); await page.tap('#buy'); await page.tap('#next');
  saved = await page.evaluate(() => JSON.parse(atob(localStorage.getItem('packdefense.techcheck.v1').split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))));
  check('ウェーブの始まりで保存（買ったパック2つ、コイン 4）', saved.phase === 'wave' && saved.packs.length === 2 && saved.coins === 4, `packs=${saved.packs} coins=${saved.coins}`);
  const before = await page.evaluate(() => ({ wave: window.__pd.data.wave, packs: window.__pd.world.pack.n, heroes: window.__pd.world.hero.n }));
  await sleep(1500);
  await page.reload(); await page.waitForFunction(() => window.__pd);
  const after = await page.evaluate(() => ({ wave: window.__pd.data.wave, packs: window.__pd.world.pack.n, heroes: window.__pd.world.hero.n, phase: window.__pd.phase, t: window.__pd.world.t }));
  check('再読み込みで、そのウェーブの始まりから（パック・英雄も同じ）', after.wave === before.wave && after.packs === before.packs && after.heroes === before.heroes && after.phase === 'wave', JSON.stringify({ before, after }));
  await page.tap('#cover');

  // --- 書き出し・読み込み
  await page.tap('#menu');
  const text = await page.$eval('#txt', e => e.value);
  check('書き出しの文字が出る（PD1. で始まる）', text.startsWith('PD1.'), `${text.length}文字`);
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 5000 }).catch(() => null), page.tap('#file')]);
  if (dl) { const p = await dl.path(); const body = (await import('node:fs')).readFileSync(p, 'utf8'); check('ファイルの書き出しの中身 ＝ 文字の書き出し（共有の使えないとき）', body === text, dl.suggestedFilename()); }
  else check('ファイルの書き出し', false, 'ダウンロードが起きなかった');
  await page.evaluate(() => localStorage.clear());
  await page.fill('#txt', text.slice(0, 30) + 'X' + text.slice(31));
  await page.tap('#load');
  check('1文字変えた文字は読み込みを断る', (await page.textContent('#msg')).includes('読み込めません'));
  await page.fill('#txt', text); await page.tap('#load');
  check('保存を消したあと、文字から読み込んで元どおり', (await page.evaluate(() => window.__pd.data.wave)) === before.wave && (await page.textContent('#msg')).includes('読み込みました'));
  await page.evaluate(() => localStorage.clear());
  await page.setInputFiles('#fin', { name: 'save.txt', mimeType: 'text/plain', buffer: Buffer.from(text) });
  await sleep(200);
  check('ファイルから読み込んで元どおり', (await page.evaluate(() => window.__pd.data.wave)) === before.wave && !!(await page.evaluate(() => localStorage.getItem('packdefense.techcheck.v1'))));
  await page.tap('#close');

  // --- 1e308 をこえた名声が保存・表示でこわれない
  await page.evaluate(() => { window.__pd.data.wave = 309; window.__pd.openShop(); });
  await page.reload(); await page.waitForFunction(() => window.__pd);
  const fame = await page.evaluate(() => ({ v: window.__pd.data.fame, hud: document.getElementById('hud').textContent }));
  check('名声が 1e308 をこえても（Infinity）保存・読み込み・表示がこわれない', fame.v === Infinity && fame.hud.includes('∞'), fame.hud);

  // --- オフライン
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload(); await page.waitForFunction(() => window.__pd);
  await ctx.setOffline(true);
  let offOk = true; try { await page.reload(); await page.waitForFunction(() => window.__pd, null, { timeout: 5000 }); } catch { offOk = false; }
  check('オフライン：Service Worker が付いたあと、ネットを切って開き直しても動く', offOk);
  await ctx.setOffline(false);
  check('storage.persist() の結果（記録）', true, String(await page.evaluate(() => navigator.storage.persist())));

  // --- 遊んでいる画面のフレームの間隔（ふつうのウェーブ、CPU そのまま）
  await page.evaluate(() => { localStorage.clear(); });
  await page.reload(); await page.waitForFunction(() => window.__pd); await page.tap('#cover');
  await page.evaluate(() => { const w = window.__pd.world; w.spawnPerSec = 8; for (let i = 0; i < 12; i++) w.addHero(180 + Math.cos(i) * 90, 390 + Math.sin(i) * 110, i % 4); w.addPack(80, 300, 3); w.addPack(280, 520, 1); });
  const ff = await toScreen(240, 330 + off);
  await touch('touchStart', [ff]);
  await sleep(3000);
  const fm = await page.evaluate(() => window.__pd.frameMs().slice(-150));
  const avg = fm.reduce((a, b) => a + b, 0) / fm.length, over = fm.filter(x => x > 17.5).length;
  check('遊ぶ画面（ふつうのウェーブ＋英雄12・パック2）でフレームの間隔', avg < 18, `平均 ${avg.toFixed(1)} ms、17.5ms 超 ${over}/${fm.length}、物 ${await page.evaluate(() => window.__pd.world.total())}`);
  const shot = devName === 'iPhone 17' ? 'screenshot_iphone17.png' : `test-results/screenshot_${devName.replace(/\W+/g, '_')}.png`;
  await page.screenshot({ path: shot });
  await touch('touchEnd', []);

  check('ページのエラーがない', errors.length === 0, errors.join(' / '));
  check('外への通信がない', external.length === 0, external.join(' '));
  await ctx.close();
}
await browser.close();
const ng = results.filter(r => !r.ok);
console.log(`\n${results.length - ng.length}/${results.length} 通った`);
writeFileSync('test-results/e2e.json', JSON.stringify(results, null, 1));
process.exit(ng.length ? 1 : 0);
