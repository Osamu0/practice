// 負荷の確かめ：iPhone 17 相当（画面の大きさ・画素比・タッチ・UA だけ。中身は Chromium）で、物の数を変えてフレームの時間を測る。
// 前提：npm run build 済み。node test/perf.mjs [--quick]
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium, devices } = require(process.env.PLAYWRIGHT_PATH ?? '/opt/node-tools/node_modules/playwright');
const PORT = 4174, BASE = `http://localhost:${PORT}/`;
mkdirSync('test-results', { recursive: true });
const server = spawn('node_modules/.bin/vite', ['preview', '--port', String(PORT), '--strictPort'], { stdio: 'pipe' });
process.on('exit', () => server.kill());
await new Promise((res, rej) => { server.stdout.on('data', d => String(d).includes('Local') && res()); setTimeout(() => rej(new Error('server timeout')), 15000); });

const quick = process.argv.includes('--quick');
const LOADS = [
  { name: 'L1', e: 100, h: 16, b: 100, p: 100, f: 20, k: 4 },
  { name: 'L2', e: 250, h: 32, b: 250, p: 250, f: 30, k: 6 },
  { name: 'L3', e: 500, h: 48, b: 500, p: 500, f: 40, k: 8 },
  { name: 'L4', e: 1000, h: 64, b: 1000, p: 1000, f: 60, k: 8 },
  { name: 'L5', e: 2000, h: 96, b: 2000, p: 2000, f: 80, k: 8 },
];
const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'chrome' });
console.log('browser', browser.version());
const rows = [];
for (const r of ['2d', 'pixi']) for (const dpr of [3, 2]) for (const cpu of [1, 4]) for (const L of (quick ? LOADS.slice(1, 4) : LOADS)) {
  const ctx = await browser.newContext({ ...devices['iPhone 17'] });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
  const url = `${BASE}bench.html?r=${r}&dpr=${dpr}&e=${L.e}&h=${L.h}&b=${L.b}&p=${L.p}&f=${L.f}&k=${L.k}&frames=180&flush=1`;
  await page.goto(url);
  await page.waitForFunction(() => window.__bench, null, { timeout: 120000 });
  const res = await page.evaluate(() => window.__bench);
  if (r === '2d' && dpr === 3 && cpu === 1 && L.name === 'L3') await page.screenshot({ path: 'test-results/bench_L3.png' });
  rows.push({ r, dpr, cpu, load: L.name, ...res });
  console.log(`${r.padEnd(4)} dpr${dpr} cpu×${cpu} ${L.name} 物${String(res.objects).padStart(5)}  計算 ${res.stepAvg.toFixed(2)}  描く(JS) ${res.drawAvg.toFixed(2)}  画素に落とす ${res.flushAvg.toFixed(2)}  合計 平均 ${res.totalAvg.toFixed(2)} / 95% ${res.totalP95.toFixed(2)} ms  間隔 平均 ${res.gapAvg.toFixed(1)} 95% ${res.gapP95.toFixed(1)} ms  17.5ms超 ${(res.over17 * 100).toFixed(0)}%`);
  await ctx.close();
}
console.log('GPU:', rows[0]?.gl, ' canvas:', rows[0]?.canvas);
writeFileSync('test-results/perf.json', JSON.stringify(rows, null, 1));
await browser.close();
process.exit(0);
