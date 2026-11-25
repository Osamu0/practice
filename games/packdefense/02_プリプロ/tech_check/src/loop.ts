// 固定の1歩（1/60秒）で計算し、描くのは画面の更新ごと（requestAnimationFrame）。
// 低電力モードで 30fps に落ちても（WebKit bug 215745）、ゲームの速さは変わらない（1回の描画で2歩進む）。
import { STEP } from './core/sim.ts';

export interface LoopHooks { step(): void; draw(): void; onFrame?(dtMs: number, steps: number): void }

export class Loop {
  running = false;
  private acc = 0; private last = 0; private raf = 0;
  private h: LoopHooks;
  constructor(h: LoopHooks) { this.h = h; }
  start(): void {
    if (this.running) return;
    this.running = true; this.acc = 0; this.last = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }
  stop(): void { this.running = false; cancelAnimationFrame(this.raf); }
  private frame = (now: number): void => {
    if (!this.running) return;
    let dt = (now - this.last) / 1000; this.last = now;
    if (dt > 0.25) dt = 0.25; // 長く止まっていたら、まとめて進めすぎない
    this.acc += dt;
    let n = 0;
    while (this.acc >= STEP && n < 5) { this.h.step(); this.acc -= STEP; n++; }
    if (n === 5) this.acc = 0; // 計算が間に合わないときは、遅れを捨てる（ゲームがゆっくりになる）
    this.h.draw();
    this.h.onFrame?.(dt * 1000, n);
    this.raf = requestAnimationFrame(this.frame);
  };
}
