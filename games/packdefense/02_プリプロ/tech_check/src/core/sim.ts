// 戦場の計算（DOM・時間・Math.random を使わない。Node でも動く）。
// 物はすべて「型付き配列の列（SoA）」で持ち、毎フレーム new しない（ガベージコレクションで止まらないように）。
// 1歩は固定の 1/60 秒。描画の速さ（30fps・60fps・120fps）が違っても、ゲームの速さは同じ。
import { type RngState, seedFrom, nextFloat, nextInt } from './rng.ts';

export const W = 360, H = 720;            // 戦場の論理の大きさ（縦長）。画面にはこれを拡大して出す
export const TOWER_X = 180, TOWER_Y = 390; // 塔の位置（少し下寄り。上の端は数字の場所）
export const TOP = 56;                     // 上の端の数字の帯。魔物はこの下から出る
export const STEP = 1 / 60;

export const CAP = { enemy: 4096, hero: 128, bullet: 4096, particle: 4096, pack: 32, float: 128 } as const;

class Pool {
  n = 0;
  readonly x: Float32Array; readonly y: Float32Array;
  readonly vx: Float32Array; readonly vy: Float32Array;
  readonly a: Float32Array;   // 用途ごと：魔物=耐久、弾=威力、粒=残り時間、パック=耐久、英雄=次に撃つまで、数字=残り時間
  readonly b: Float32Array;   // 用途ごと：魔物=最大耐久、数字=値、パック=レア度、英雄=射程
  readonly k: Uint8Array;     // 種類
  readonly cap: number;
  constructor(cap: number) {
    this.cap = cap;
    this.x = new Float32Array(cap); this.y = new Float32Array(cap);
    this.vx = new Float32Array(cap); this.vy = new Float32Array(cap);
    this.a = new Float32Array(cap); this.b = new Float32Array(cap);
    this.k = new Uint8Array(cap);
  }
  add(x: number, y: number): number {
    if (this.n >= this.cap) return -1;
    const i = this.n++;
    this.x[i] = x; this.y[i] = y; this.vx[i] = 0; this.vy[i] = 0; this.a[i] = 0; this.b[i] = 0; this.k[i] = 0;
    return i;
  }
  /** 末尾と入れ替えて消す（順番は変わるが、配列は詰まったまま） */
  remove(i: number): void {
    const j = --this.n;
    if (i === j) return;
    this.x[i] = this.x[j]; this.y[i] = this.y[j]; this.vx[i] = this.vx[j]; this.vy[i] = this.vy[j];
    this.a[i] = this.a[j]; this.b[i] = this.b[j]; this.k[i] = this.k[j];
  }
}

// 当たり判定の升目（魔物だけを入れる）。升目ごとのつなぎの列で、毎歩作り直す
const CELL = 40, GW = Math.ceil(W / CELL), GH = Math.ceil(H / CELL);

export interface Stress { enemy: number; hero: number; bullet: number; particle: number; float: number; pack: number }

export class World {
  readonly enemy = new Pool(CAP.enemy);
  readonly hero = new Pool(CAP.hero);
  readonly bullet = new Pool(CAP.bullet);
  readonly particle = new Pool(CAP.particle);
  readonly pack = new Pool(CAP.pack);
  readonly float = new Pool(CAP.float);
  private readonly head = new Int32Array(GW * GH);
  private readonly next = new Int32Array(CAP.enemy);
  rng: RngState;
  t = 0;              // 経過（歩の数）
  towerHp = 100;
  coins = 0;
  kills = 0;
  hits = 0;           // タップ攻撃が当たった回数（テスト用）
  opened = 0;         // 開けたパックの数
  events: number[] = []; // 音のきっかけ（1=当たり 2=倒した 3=開封）。描画側が読んで空にする
  // タップ攻撃（指の少し上の輪）
  ringOn = false; ringX = 0; ringY = 0;
  ringR = 34;         // 当たりの半径（見た目の輪 28 より少し大きい）
  tapEvery = 6;       // 何歩ごとに攻撃するか（6歩=0.1秒）
  tapDmg = 1;
  private tapCd = 0;
  spawnPerSec = 1.5;  // ふつうのウェーブの出現の速さ
  private spawnAcc = 0;
  stress: Stress | null = null;

  constructor(seed: string) { this.rng = seedFrom(seed); }

  spawnEnemy(): number {
    const r = this.rng, side = nextInt(r, 4);
    let x = 0, y = 0;
    if (side === 0) { x = nextFloat(r) * W; y = TOP; }
    else if (side === 1) { x = nextFloat(r) * W; y = H; }
    else if (side === 2) { x = 0; y = TOP + nextFloat(r) * (H - TOP); }
    else { x = W; y = TOP + nextFloat(r) * (H - TOP); }
    const i = this.enemy.add(x, y);
    if (i < 0) return -1;
    const dx = TOWER_X - x, dy = TOWER_Y - y, d = Math.hypot(dx, dy) || 1;
    const sp = 18 + nextFloat(r) * 14; // 1秒あたりの論理px
    this.enemy.vx[i] = dx / d * sp; this.enemy.vy[i] = dy / d * sp;
    const hp = this.stress ? 1e9 : 3;
    this.enemy.a[i] = hp; this.enemy.b[i] = hp; this.enemy.k[i] = nextInt(r, 4);
    return i;
  }

  addHero(x: number, y: number, kind = 0): number {
    const i = this.hero.add(x, y);
    if (i >= 0) { this.hero.k[i] = kind; this.hero.b[i] = 110; this.hero.a[i] = nextInt(this.rng, 30); }
    return i;
  }

  addPack(x: number, y: number, rarity = 0): number {
    const i = this.pack.add(x, y);
    if (i >= 0) { this.pack.a[i] = 5; this.pack.b[i] = rarity; this.pack.k[i] = rarity; }
    return i;
  }

  private buildGrid(): void {
    this.head.fill(-1);
    const e = this.enemy;
    for (let i = 0; i < e.n; i++) {
      const cx = Math.min(GW - 1, Math.max(0, (e.x[i] / CELL) | 0));
      const cy = Math.min(GH - 1, Math.max(0, (e.y[i] / CELL) | 0));
      const c = cy * GW + cx;
      this.next[i] = this.head[c]; this.head[c] = i;
    }
  }

  /** (x,y) から半径 r の中で、いちばん近い魔物。いなければ -1 */
  nearestEnemy(x: number, y: number, r: number): number {
    const e = this.enemy;
    const x0 = Math.max(0, ((x - r) / CELL) | 0), x1 = Math.min(GW - 1, ((x + r) / CELL) | 0);
    const y0 = Math.max(0, ((y - r) / CELL) | 0), y1 = Math.min(GH - 1, ((y + r) / CELL) | 0);
    let best = -1, bd = r * r;
    for (let cy = y0; cy <= y1; cy++) for (let cx = x0; cx <= x1; cx++) {
      for (let i = this.head[cy * GW + cx]; i >= 0; i = this.next[i]) {
        const dx = e.x[i] - x, dy = e.y[i] - y, d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
    }
    return best;
  }

  /** (x,y) から半径 r の中の魔物すべてに cb。数を返す */
  forEnemiesIn(x: number, y: number, r: number, cb: (i: number) => void): number {
    const e = this.enemy;
    const x0 = Math.max(0, ((x - r) / CELL) | 0), x1 = Math.min(GW - 1, ((x + r) / CELL) | 0);
    const y0 = Math.max(0, ((y - r) / CELL) | 0), y1 = Math.min(GH - 1, ((y + r) / CELL) | 0);
    let n = 0; const r2 = r * r;
    for (let cy = y0; cy <= y1; cy++) for (let cx = x0; cx <= x1; cx++) {
      for (let i = this.head[cy * GW + cx]; i >= 0; i = this.next[i]) {
        const dx = e.x[i] - x, dy = e.y[i] - y;
        if (dx * dx + dy * dy <= r2) { cb(i); n++; }
      }
    }
    return n;
  }

  private damage(i: number, dmg: number): void {
    this.enemy.a[i] -= dmg;
  }

  private burst(x: number, y: number, n: number): void {
    const p = this.particle;
    for (let j = 0; j < n; j++) {
      const i = p.add(x, y); if (i < 0) return;
      const ang = nextFloat(this.rng) * Math.PI * 2, sp = 30 + nextFloat(this.rng) * 60;
      p.vx[i] = Math.cos(ang) * sp; p.vy[i] = Math.sin(ang) * sp; p.a[i] = 0.4 + nextFloat(this.rng) * 0.3; p.k[i] = nextInt(this.rng, 3);
    }
  }

  private popNumber(x: number, y: number, v: number): void {
    const f = this.float;
    let i = f.add(x, y);
    if (i < 0) { i = nextInt(this.rng, f.n); f.x[i] = x; f.y[i] = y; } // 上限なら古いのを使い回す
    f.vy[i] = -40; f.a[i] = 0.6; f.b[i] = v;
  }

  /** 1歩（1/60秒）進める */
  step(): void {
    const dt = STEP;
    this.t++;
    const e = this.enemy, b = this.bullet, p = this.particle, h = this.hero, f = this.float;

    // 出現
    if (this.stress) {
      while (e.n < this.stress.enemy) if (this.spawnEnemy() < 0) break;
    } else {
      this.spawnAcc += this.spawnPerSec * dt;
      while (this.spawnAcc >= 1) { this.spawnAcc -= 1; this.spawnEnemy(); }
    }

    // 魔物が動く。塔に着いたら塔を削って消える
    for (let i = e.n - 1; i >= 0; i--) {
      e.x[i] += e.vx[i] * dt; e.y[i] += e.vy[i] * dt;
      const dx = e.x[i] - TOWER_X, dy = e.y[i] - TOWER_Y;
      if (dx * dx + dy * dy < 24 * 24) { if (!this.stress) this.towerHp -= 1; e.remove(i); }
    }
    this.buildGrid();

    // タップ攻撃：押さえているあいだ、一定の間隔で輪の中の魔物とパックを攻撃
    if (this.ringOn) {
      if (this.tapCd <= 0) {
        this.tapCd = this.tapEvery;
        const n = this.forEnemiesIn(this.ringX, this.ringY, this.ringR, i => this.damage(i, this.tapDmg));
        if (n > 0) { this.hits += n; this.events.push(1); this.popNumber(this.ringX, this.ringY - 10, this.tapDmg * n); }
        const pk = this.pack;
        for (let i = pk.n - 1; i >= 0; i--) {
          const dx = pk.x[i] - this.ringX, dy = pk.y[i] - this.ringY;
          if (dx * dx + dy * dy <= (this.ringR + 14) ** 2) {
            pk.a[i] -= 1; this.events.push(1);
            if (pk.a[i] <= 0) { this.addHero(pk.x[i], pk.y[i], pk.k[i]); this.burst(pk.x[i], pk.y[i], 24); this.opened++; this.events.push(3); pk.remove(i); }
          }
        }
      }
      this.tapCd--;
    } else if (this.tapCd > 0) this.tapCd--;

    // 英雄：射程の中のいちばん近い魔物へ弾を撃つ
    const wantB = this.stress ? this.stress.bullet : CAP.bullet;
    for (let i = 0; i < h.n; i++) {
      h.a[i] -= 1;
      if (h.a[i] > 0 && !(this.stress && b.n < wantB)) continue;
      if (b.n >= wantB) continue;
      const t = this.nearestEnemy(h.x[i], h.y[i], this.stress ? 400 : h.b[i]);
      if (t < 0) continue;
      h.a[i] = 30;
      const j = b.add(h.x[i], h.y[i]); if (j < 0) break;
      const dx = e.x[t] - h.x[i], dy = e.y[t] - h.y[i], d = Math.hypot(dx, dy) || 1;
      b.vx[j] = dx / d * 240; b.vy[j] = dy / d * 240; b.a[j] = 1; b.b[j] = 1.5;
    }

    // 弾：動いて、近くの升目の魔物に当たる
    for (let i = b.n - 1; i >= 0; i--) {
      b.x[i] += b.vx[i] * dt; b.y[i] += b.vy[i] * dt; b.b[i] -= dt;
      if (b.b[i] <= 0 || b.x[i] < 0 || b.x[i] > W || b.y[i] < 0 || b.y[i] > H) { b.remove(i); continue; }
      const t = this.nearestEnemy(b.x[i], b.y[i], 10);
      if (t >= 0) { this.damage(t, b.a[i]); b.remove(i); }
    }

    // 倒れた魔物
    for (let i = e.n - 1; i >= 0; i--) {
      if (e.a[i] <= 0) {
        this.kills++; this.coins += 1; this.events.push(2);
        this.burst(e.x[i], e.y[i], 6); this.popNumber(e.x[i], e.y[i], 1);
        e.remove(i);
      }
    }

    // 粒と数字
    if (this.stress) while (p.n < this.stress.particle) { const n0 = p.n; this.burst(nextFloat(this.rng) * W, TOP + nextFloat(this.rng) * (H - TOP), 8); if (p.n === n0) break; }
    for (let i = p.n - 1; i >= 0; i--) {
      p.a[i] -= dt; if (p.a[i] <= 0) { p.remove(i); continue; }
      p.x[i] += p.vx[i] * dt; p.y[i] += p.vy[i] * dt; p.vx[i] *= 0.96; p.vy[i] *= 0.96;
    }
    if (this.stress) while (f.n < this.stress.float) this.popNumber(nextFloat(this.rng) * W, TOP + nextFloat(this.rng) * (H - TOP), 1 + nextInt(this.rng, 1e6));
    for (let i = f.n - 1; i >= 0; i--) {
      f.a[i] -= dt; if (f.a[i] <= 0) { f.remove(i); continue; }
      f.y[i] += f.vy[i] * dt;
    }
  }

  /** 負荷試験：物の数を目標に保つ。英雄とパックはここで並べる */
  setStress(s: Stress): void {
    this.stress = s;
    this.hero.n = 0; this.pack.n = 0;
    for (let i = 0; i < s.hero; i++) {
      const ang = (i / Math.max(1, s.hero)) * Math.PI * 2, rr = 60 + (i % 3) * 30;
      this.addHero(TOWER_X + Math.cos(ang) * rr, TOWER_Y + Math.sin(ang) * rr, i % 4);
    }
    for (let i = 0; i < s.pack; i++) this.addPack(40 + (i * 53) % 280, 120 + ((i * 97) % 520), i % 4);
  }

  total(): number { return this.enemy.n + this.hero.n + this.bullet.n + this.particle.n + this.pack.n + this.float.n; }
}

/** 指の位置（論理px）から、攻撃の輪の中心。offset は指の上に何pxずらすか（0 でずらさない） */
export function ringFromFinger(fx: number, fy: number, offset: number): { x: number; y: number } {
  return { x: fx, y: Math.max(TOP, fy - offset) };
}
