// 比べるための描画（PixiJS 8、WebGL）。負荷の比べ（bench.html?r=pixi）でだけ使う。本番の候補 B。
import { Application, Container, Sprite, Texture, Rectangle } from 'pixi.js';
import { type World, W, H, TOWER_X, TOWER_Y } from './core/sim.ts';
import { makeAtlas, type Atlas } from './atlas.ts';
import { fmt } from './core/num.ts';
import type { Renderer } from './render2d.ts';

class SpritePool {
  readonly c = new Container();
  private list: Sprite[] = [];
  private inv: number;
  constructor(inv: number) { this.inv = inv; }
  begin(): number { return 0; }
  get(i: number, tex: Texture): Sprite {
    let s = this.list[i];
    if (!s) { s = new Sprite(tex); s.anchor.set(0.5); s.scale.set(this.inv); this.c.addChild(s); this.list[i] = s; }
    if (s.texture !== tex) s.texture = tex;
    s.visible = true;
    return s;
  }
  end(n: number): void { for (let i = n; i < this.list.length; i++) this.list[i].visible = false; }
}

export class PixiRenderer implements Renderer {
  readonly name = 'pixi';
  app = new Application();
  private atlas!: Atlas;
  private tex: Record<string, Texture> = {};
  private pools: SpritePool[] = [];
  private world = new Container();
  private css = 1; private ox = 0; private oy = 0;
  private canvas: HTMLCanvasElement;
  constructor(canvas: HTMLCanvasElement) { this.canvas = canvas; }
  async init(cssW: number, cssH: number, dpr: number): Promise<void> {
    await this.app.init({ canvas: this.canvas, width: cssW, height: cssH, resolution: dpr, autoDensity: true, antialias: false, background: '#1d2b1f', preference: 'webgl', autoStart: false, sharedTicker: false });
    this.app.ticker.stop();
    this.resize(cssW, cssH, dpr);
  }
  resize(cssW: number, cssH: number, dpr: number): void {
    this.css = Math.min(cssW / W, cssH / H);
    this.ox = (cssW - W * this.css) / 2; this.oy = (cssH - H * this.css) / 2;
    this.atlas = makeAtlas(this.css * dpr);
    const base = Texture.from(this.atlas.canvas);
    for (const [k, f] of Object.entries(this.atlas.frames)) this.tex[k] = new Texture({ source: base.source, frame: new Rectangle(f.x, f.y, f.w, f.h) });
    this.world.removeChildren();
    const ground = new Sprite(Texture.WHITE); ground.tint = 0x4b7f52; ground.width = W; ground.height = H; this.world.addChild(ground);
    this.pools = [];
    for (let i = 0; i < 7; i++) { const p = new SpritePool(1 / (this.css * dpr)); this.pools.push(p); this.world.addChild(p.c); }
    this.world.scale.set(this.css); this.world.position.set(this.ox, this.oy);
    this.app.stage.removeChildren(); this.app.stage.addChild(this.world);
  }
  toWorld(cx: number, cy: number) { return { x: (cx - this.ox) / this.css, y: (cy - this.oy) / this.css }; }
  draw(w: World): void {
    const [pT, pP, pE, pH, pB, pX, pF] = this.pools;
    const one = (pool: SpritePool, i: number, name: string, x: number, y: number) => { const s = pool.get(i, this.tex[name]); s.position.set(x, y); };
    one(pT, 0, 'tower', TOWER_X, TOWER_Y); let n = 1; if (w.ringOn) { one(pT, 1, 'ring', w.ringX, w.ringY); n = 2; } pT.end(n);
    const pk = w.pack; for (let i = 0; i < pk.n; i++) one(pP, i, 'pack' + pk.k[i], pk.x[i], pk.y[i]); pP.end(pk.n);
    const e = w.enemy; for (let i = 0; i < e.n; i++) one(pE, i, 'enemy' + e.k[i], e.x[i], e.y[i]); pE.end(e.n);
    const h = w.hero; for (let i = 0; i < h.n; i++) one(pH, i, 'hero' + h.k[i], h.x[i], h.y[i]); pH.end(h.n);
    const b = w.bullet; for (let i = 0; i < b.n; i++) one(pB, i, 'bullet', b.x[i], b.y[i]); pB.end(b.n);
    const p = w.particle; for (let i = 0; i < p.n; i++) one(pX, i, 'particle' + p.k[i], p.x[i], p.y[i]); pX.end(p.n);
    const f = w.float; let m = 0;
    for (let i = 0; i < f.n; i++) {
      const str = fmt(f.b[i]); let x = f.x[i] - str.length * 3;
      for (const ch of str) { const t = this.tex['g' + ch]; if (t) { const s = pF.get(m++, t); s.position.set(x, f.y[i]); x += 6; } }
    }
    pF.end(m);
    this.app.render();
  }
}
