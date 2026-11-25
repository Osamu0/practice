// 描画（Canvas 2D）。選んだ形。戦場の論理の大きさ（360×720）を、画面に合わせて拡大して描く。
import { type World, W, H, TOWER_X, TOWER_Y, TOP } from './core/sim.ts';
import { makeAtlas, type Atlas } from './atlas.ts';
import { fmt } from './core/num.ts';

export interface Renderer {
  readonly name: string;
  resize(cssW: number, cssH: number, dpr: number): void;
  draw(w: World): void;
  /** 画面の点（CSS px）→ 戦場の論理の点 */
  toWorld(cx: number, cy: number): { x: number; y: number };
}

export class Canvas2DRenderer implements Renderer {
  readonly name = 'canvas2d';
  hudInCanvas = false; // 負荷の確かめのときだけ true（ゲームの画面は DOM の HUD）
  private g: CanvasRenderingContext2D;
  private atlas!: Atlas;
  private bg!: HTMLCanvasElement;
  private s = 1;   // 論理px → 端末の画素
  private ox = 0; private oy = 0; // 余白（端末の画素）
  private css = 1; private dpr = 1;
  private canvas: HTMLCanvasElement;
  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.g = canvas.getContext('2d', { alpha: false })!;
  }
  resize(cssW: number, cssH: number, dpr: number): void {
    this.dpr = dpr;
    this.canvas.style.width = cssW + 'px'; this.canvas.style.height = cssH + 'px';
    this.canvas.width = Math.round(cssW * dpr); this.canvas.height = Math.round(cssH * dpr);
    this.css = Math.min(cssW / W, cssH / H);
    this.s = this.css * dpr;
    this.ox = Math.round((this.canvas.width - W * this.s) / 2); this.oy = Math.round((this.canvas.height - H * this.s) / 2);
    this.atlas = makeAtlas(this.s);
    // 背景は1枚の絵にしておき、毎フレーム1回貼るだけ
    this.bg = document.createElement('canvas'); this.bg.width = this.canvas.width; this.bg.height = this.canvas.height;
    const b = this.bg.getContext('2d')!;
    b.fillStyle = '#1d2b1f'; b.fillRect(0, 0, this.bg.width, this.bg.height);
    b.fillStyle = '#4b7f52'; b.fillRect(this.ox, this.oy, W * this.s, H * this.s);
    b.fillStyle = '#8d7b5a';
    b.fillRect(this.ox + (TOWER_X - 10) * this.s, this.oy + TOP * this.s, 20 * this.s, (H - TOP) * this.s);
    b.fillRect(this.ox, this.oy + (TOWER_Y - 10) * this.s, W * this.s, 20 * this.s);
    b.fillStyle = 'rgba(0,0,0,0.35)'; b.fillRect(this.ox, this.oy, W * this.s, TOP * this.s);
  }
  toWorld(cx: number, cy: number) {
    return { x: (cx * this.dpr - this.ox) / this.s, y: (cy * this.dpr - this.oy) / this.s };
  }
  private spr(name: string, x: number, y: number): void {
    const f = this.atlas.frames[name];
    this.g.drawImage(this.atlas.canvas, f.x, f.y, f.w, f.h, Math.round(this.ox + x * this.s - f.w / 2), Math.round(this.oy + y * this.s - f.h / 2), f.w, f.h);
  }
  private text(str: string, x: number, y: number): void {
    // 字の絵を並べる（真ん中ぞろえ）
    let total = 0; for (const ch of str) total += this.atlas.frames['g' + ch]?.w ?? 0;
    let px = Math.round(this.ox + x * this.s - total / 2); const py = Math.round(this.oy + y * this.s);
    for (const ch of str) {
      const f = this.atlas.frames['g' + ch]; if (!f) continue;
      this.g.drawImage(this.atlas.canvas, f.x, f.y, f.w, f.h, px, py, f.w, f.h); px += f.w * 0.62;
    }
  }
  draw(w: World): void {
    const g = this.g;
    g.drawImage(this.bg, 0, 0);
    this.spr('tower', TOWER_X, TOWER_Y);
    const pk = w.pack; for (let i = 0; i < pk.n; i++) this.spr('pack' + pk.k[i], pk.x[i], pk.y[i]);
    const e = w.enemy; for (let i = 0; i < e.n; i++) this.spr('enemy' + e.k[i], e.x[i], e.y[i]);
    const h = w.hero; for (let i = 0; i < h.n; i++) this.spr('hero' + h.k[i], h.x[i], h.y[i]);
    const b = w.bullet; for (let i = 0; i < b.n; i++) this.spr('bullet', b.x[i], b.y[i]);
    const p = w.particle; for (let i = 0; i < p.n; i++) this.spr('particle' + p.k[i], p.x[i], p.y[i]);
    const f = w.float; for (let i = 0; i < f.n; i++) this.text(fmt(f.b[i]), f.x[i], f.y[i]);
    if (w.ringOn) this.spr('ring', w.ringX, w.ringY);
    // 上の端の数字（塔の耐久・コイン）
    if (this.hudInCanvas) { this.text(fmt(w.towerHp), 60, 18); this.text(fmt(w.coins), 300, 18); }
  }
}
