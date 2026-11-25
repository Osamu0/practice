// 負荷の確かめ：物の数を決めて動かし、1フレームの計算・描画の時間と、フレームの間隔を測る。
// bench.html?r=2d|pixi&e=魔物&h=英雄&b=弾&p=粒&f=数字&k=パック&dpr=画素比&frames=測るフレーム数&flush=1
import { World } from './core/sim.ts';
import { Canvas2DRenderer, type Renderer } from './render2d.ts';

const q = new URLSearchParams(location.search);
const num = (k: string, d: number) => (q.has(k) ? Number(q.get(k)) : d);
const kind = q.get('r') ?? '2d';
const dpr = Math.min(num('dpr', devicePixelRatio), devicePixelRatio);
const frames = num('frames', 180), warm = 60, flush = q.get('flush') === '1';
const canvas = document.getElementById('c') as HTMLCanvasElement;
const world = new World('bench');
world.setStress({ enemy: num('e', 500), hero: num('h', 32), bullet: num('b', 500), particle: num('p', 500), float: num('f', 40), pack: num('k', 6) });
world.ringOn = true; world.ringX = 180; world.ringY = 300;

let r: Renderer;
if (kind === 'pixi') {
  const { PixiRenderer } = await import('./renderPixi.ts');
  const pr = new PixiRenderer(canvas); await pr.init(innerWidth, innerHeight, dpr); r = pr;
} else { const c2 = new Canvas2DRenderer(canvas); c2.hudInCanvas = true; c2.resize(innerWidth, innerHeight, dpr); r = c2; }

function glInfo(): string {
  const c = document.createElement('canvas'); const gl = c.getContext('webgl2') || c.getContext('webgl');
  if (!gl) return 'no webgl';
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER));
}
const g2d = kind === '2d' ? canvas.getContext('2d') : null;
const gl = kind === 'pixi' ? ((r as any).app.renderer.gl as WebGL2RenderingContext) : null;
const px = new Uint8Array(4);

const step: number[] = [], draw: number[] = [], fl: number[] = [], gap: number[] = [];
let i = 0, last = 0;
function frame(now: number) {
  if (i > 0) gap.push(now - last);
  last = now;
  const t0 = performance.now(); world.step();
  const t1 = performance.now(); r.draw(world);
  const t2 = performance.now();
  if (flush) { if (g2d) g2d.getImageData(0, 0, 1, 1); if (gl) gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); }
  const t3 = performance.now();
  if (i >= warm) { step.push(t1 - t0); draw.push(t2 - t1); fl.push(t3 - t2); }
  i++;
  if (i < warm + frames) requestAnimationFrame(frame);
  else done();
}
const pct = (a: number[], p: number) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const avg = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
function done() {
  const total = step.map((s, k) => s + draw[k] + fl[k]);
  const g = gap.slice(warm);
  (window as any).__bench = {
    renderer: r.name, dpr, canvas: [canvas.width, canvas.height], objects: world.total(),
    counts: { enemy: world.enemy.n, hero: world.hero.n, bullet: world.bullet.n, particle: world.particle.n, float: world.float.n, pack: world.pack.n },
    stepAvg: avg(step), drawAvg: avg(draw), flushAvg: avg(fl), totalAvg: avg(total), totalP95: pct(total, 0.95),
    gapAvg: avg(g), gapP95: pct(g, 0.95), over17: g.filter(x => x > 17.5).length / g.length, gl: glInfo(),
  };
  // 実機で読めるように、結果を画面に出す（04 で、オーナーの iPhone で見る）
  const b = (window as any).__bench, d = document.createElement('pre');
  d.style.cssText = 'position:fixed;left:8px;right:8px;top:40%;margin:0;padding:10px;background:rgba(0,0,0,.85);color:#fff;font:14px/1.5 monospace;white-space:pre-wrap;';
  d.textContent = `${b.renderer} 画素比${b.dpr} 物${b.objects}\n合計 平均 ${b.totalAvg.toFixed(1)}ms / 95% ${b.totalP95.toFixed(1)}ms\n間隔 平均 ${b.gapAvg.toFixed(1)}ms / 95% ${b.gapP95.toFixed(1)}ms\n17.5ms超 ${(b.over17 * 100).toFixed(0)}%\n${b.gl}`;
  document.body.appendChild(d);
}
requestAnimationFrame(frame);
