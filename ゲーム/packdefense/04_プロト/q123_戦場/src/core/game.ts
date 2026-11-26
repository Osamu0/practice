// 戦場とランの計算（DOM・時間・Math.random を使わない。Node でも動く）。1歩は 1/60 秒。
// プロトなので物はふつうのオブジェクトの配列（数は多くて百ほど）。湧いたときだけ new し、毎歩は new しない。
import { type RngState, seedFrom, nextFloat, nextInt } from './rng.ts';
import { type Params, market, budget, spawnDuration, hpGrowth, famePerWave } from './params.ts';
import { type Knobs, type Role, type SpellId, type PackType, POOL, autoLevels, applyOverrides, overrideList, Q2_START, Q3_START_UPGRADES, Q3_RUN_TARGET, SPAWN_LATERAL, KNOCKBACK } from './proto.ts';

export const STEP = 1 / 60;
export const W = 390;
export type Dir = 'n' | 'e' | 's' | 'w';
export type MType = 'slime' | 'wolf' | 'swarm';
export type Source = 'finger' | 'auto' | 'hero' | 'spell';
export type Scene = 'title' | 'fight' | 'cleared' | 'shop' | 'destroyed' | 'result' | 'upgrade' | 'q1end' | 'q2end';

export interface Monster {
  id: number; type: MType; dir: Dir; x: number; y: number; hp: number; maxHp: number; size: number; speed: number;
  atk: number; atkInterval: number; atkCd: number; slowUntil: number; slowMul: number; flash: number; attacking: boolean; dead: boolean;
}
export interface Card { kind: 'hero' | 'spell'; id: Role | SpellId; rarity: number }
export interface PackDef { type: PackType; cards: Card[]; rarity: number; boughtWave: number }
export interface FieldPack { def: PackDef; x: number; y: number; tele: number; hits: number; need: number; landT: number; shake: number }
export interface Hero { role: Role; rarity: number; power: number; x: number; y: number; cd: number; born: number; stackFx: number; atkFx: number; aimX: number; aimY: number }
export interface SlotSpell { id: SpellId; power: number }
export interface PendingSpell { id: SpellId; x: number; y: number; t: number; power: number; auto: boolean }
export interface Proj { x: number; y: number; target: number; dmg: number; speed: number; life: number }
export interface Fx { kind: 'burst' | 'slash' | 'line' | 'spell' | 'open' | 'coin' | 'aura' | 'hurt'; x: number; y: number; x2: number; y2: number; t: number; life: number; r: number; c: number }
export interface Float { x: number; y: number; v: number; t: number }
export interface Warning { dir: Dir; x: number; y: number; until: number }
interface Entry { time: number; type: MType; dir: Dir; done: boolean; lat: number }

export interface WaveStat {
  run: number; mode: string; wave: number; seed: string; knobs: string; time: number; result: string;
  presses: number; holdTime: number; attacks: number; whiffAttacks: number; hitsMonster: number; whiffPresses: number; hitsPack: number;
  spellCasts: number; spellWhiff: number; spellCancel: number; spellOverflow: number;
  packsDropped: number; packsOpened: number; openDelays: number[]; packsCarried: number;
  kills: number; dmg: Record<Source, number>; towerDmg: Record<Dir, number>; towerHpEnd: number; coinsEnd: number; heroesEnd: number;
}

function newStat(run: number, mode: string, wave: number, seed: string, knobs: string): WaveStat {
  return { run, mode, wave, seed, knobs, time: 0, result: '', presses: 0, holdTime: 0, attacks: 0, whiffAttacks: 0, hitsMonster: 0,
    whiffPresses: 0, hitsPack: 0, spellCasts: 0, spellWhiff: 0, spellCancel: 0, spellOverflow: 0, packsDropped: 0, packsOpened: 0,
    openDelays: [], packsCarried: 0, kills: 0, dmg: { finger: 0, auto: 0, hero: 0, spell: 0 }, towerDmg: { n: 0, e: 0, s: 0, w: 0 },
    towerHpEnd: 0, coinsEnd: 0, heroesEnd: 0 };
}

export interface Meta { fame: number; record: number; runs: number; up: { tapDmg: number; heroDmg: number; towerHp: number } }
export const newMeta = (): Meta => ({ fame: 0, record: 0, runs: 0, up: { tapDmg: Q3_START_UPGRADES.tapDmg, heroDmg: Q3_START_UPGRADES.heroDmg, towerHp: Q3_START_UPGRADES.towerHp } });

const DIRS: Dir[] = ['n', 'e', 's', 'w'];

export class Game {
  p: Params;            // CSV ＋ つまみの上書き（ランの始めに作り直す）
  readonly base: Params; // CSV のまま
  k: Knobs;
  meta: Meta;
  H: number;
  towerX = W / 2; towerY = 422;
  scene: Scene = 'title';
  seedBase: string;
  seed = '';
  rng: RngState;
  t = 0;                 // 全体の歩
  sceneT = 0;            // いまの場面に入ってからの歩
  // ラン
  wave = 1; coins = 0; towerHp = 100; towerMax = 100; runSteps = 0; runFame = 0; runIndex = 0; spellGiven = false; tenMinTold = false;
  heroes: Hero[] = [];
  queued: PackDef[] = [];  // 次のウェーブに降る（買った・持ち越し）
  carried = 0;              // queued のうち先頭の何個が持ち越しか
  slots: SlotSpell[] = [];
  boughtThisShop: PackDef[] = [];
  lastShopResult: { fame: number; coins: number } = { fame: 0, coins: 0 };
  // ウェーブ
  monsters: Monster[] = [];
  packs: FieldPack[] = [];
  drops: { def: PackDef; time: number }[] = [];
  pending: PendingSpell[] = [];
  projs: Proj[] = [];
  fx: Fx[] = [];
  floats: Float[] = [];
  warnings: Warning[] = [];
  schedule: Entry[] = [];
  clock = 0; lastSpawnClock = -99; waveT = 0; killedCoins = 0; nextId = 1;
  // 指
  fingerOn = false; fx0 = 0; fy0 = 0; ringX = 0; ringY = 0; tapCd = 0; pressHit = false;
  drag: { slot: number; fx: number; fy: number } | null = null;
  lockPack: FieldPack | null = null;
  // 自動化
  autoX = W / 2; autoY = 422; autoCd = 0; autoTarget = -1; autoFlash = 0;
  // 記録
  stat: WaveStat;
  logs: WaveStat[] = [];
  events: string[] = [];   // 音と画面のきっかけ（main が読んで空にする）
  lastWaveSummary = '';

  constructor(p: Params, k: Knobs, H: number, seedBase: string, meta?: Meta) {
    this.base = p; this.p = applyOverrides(p, k); this.k = k; this.H = H; this.seedBase = seedBase; this.meta = meta ?? newMeta();
    this.rng = seedFrom(seedBase);
    this.stat = newStat(0, k.mode, 1, seedBase, '');
    this.layout();
  }

  // ---------- 画面の形 ----------
  layout(): void { this.towerY = Math.round(this.H * this.k.towerY); }
  get slotRects(): { x: number; y: number; w: number; h: number }[] {
    const w = 68, h = 90, gap = 16, bottom = this.H - 62; // 下のふちは下の安全域(34)の 28 上（アート 7.2）
    const x0 = W / 2 - gap / 2 - w;
    return [0, 1].slice(0, this.p.slotCount).map(i => ({ x: x0 + i * (w + gap), y: bottom - h, w, h }));
  }
  /** 呪文の置き場の帯（S2 のときだけ）。上下に少し余白 */
  get slotBand(): [number, number] { const r = this.slotRects[0]; return [r.y - 12, r.y + r.h + 8]; }
  inSlotBand(y: number): boolean { if (this.k.spellMode !== 'S2') return false; const [a, b] = this.slotBand; return y >= a && y <= b; }
  /** 指の輪が届く、いちばん下の y（これより下の魔物は指で打てない） */
  get reachBottom(): number { return this.H - this.k.ringOffset + this.p.ringHit; }
  visible(m: { x: number; y: number }): boolean { return m.x >= 0 && m.x <= W && m.y >= this.p.ringTop && m.y <= this.H; }
  ringFromFinger(fx: number, fy: number): { x: number; y: number } {
    return { x: Math.max(0, Math.min(W, fx)), y: Math.max(this.p.ringTop, Math.min(this.H - this.k.ringOffset, fy - this.k.ringOffset)) };
  }

  // ---------- 強さ ----------
  fingerDmg(): number { return this.p.tapDamage * market(this.p, this.wave) * this.p.up.tapDmg.effect ** this.meta.up.tapDmg; }
  autoLevel() { return autoLevels(this.p)[this.k.auto] ?? autoLevels(this.p)[0]; }
  upCost(id: 'tapDmg' | 'heroDmg' | 'towerHp' | 'tapAuto'): number {
    const u = this.p.up[id], lv = id === 'tapAuto' ? this.k.auto : this.meta.up[id];
    return Math.round(u.costBase * u.costGrowth ** lv);
  }
  heroDmg(h: Hero): number { return this.p.hero[h.role].dmg * (this.p.rarityPower[h.rarity] ?? 1) * h.power * this.p.up.heroDmg.effect ** this.meta.up.heroDmg; }
  packPrice(t: PackType): number { return this.p.pack[t].price * market(this.p, this.wave); }

  // ---------- ラン ----------
  /** つまみの遊び方で、新しいランを始める */
  newRun(): void {
    this.runIndex++;
    this.p = applyOverrides(this.base, this.k);
    this.seed = this.k.sameSeed ? 'fixed' : `${this.seedBase}/r${this.runIndex}`;
    this.rng = seedFrom(this.seed);
    this.layout();
    this.heroes = []; this.queued = []; this.carried = 0; this.slots = []; this.runSteps = 0; this.runFame = 0;
    this.spellGiven = false; this.tenMinTold = false;
    this.towerMax = this.p.towerHp * (this.k.mode === 'q3' ? this.p.up.towerHp.effect ** this.meta.up.towerHp : 1);
    this.towerHp = this.towerMax;
    if (this.k.mode === 'q2') {
      this.wave = Q2_START.wave; this.coins = Q2_START.coins;
      const r = seedFrom(this.seed + '/start');
      Q2_START.packs.forEach((t, i) => this.queued.push(this.rollPack(t, 1, r, i === 0)));
    } else {
      this.wave = 1; this.coins = this.p.coinStart;
    }
    this.startWave();
  }

  /** パックの中身を買ったときに決める */
  rollPack(type: PackType, boughtWave: number, r: RngState, firstOfShop: boolean): PackDef {
    const pp = this.p.pack[type], pool = POOL[type], cards: Card[] = [];
    const wsum = pp.rarityWeights.reduce((s, x) => s + x, 0);
    const forceSpell = firstOfShop && (this.k.forceSpell && this.k.mode === 'q2'
      || (!this.spellGiven && boughtWave >= this.p.firstSpellWave - 1));
    for (let i = 0; i < pp.cards; i++) {
      let x = nextFloat(r) * wsum, rar = 0;
      for (; rar < pp.rarityWeights.length - 1; rar++) { x -= pp.rarityWeights[rar]; if (x < 0) break; }
      const spell = i === 0 ? pp.firstCard === 'spell' : (forceSpell && i === 1) || nextFloat(r) < pp.spellShare;
      if (spell) {
        const ws = pool.spells.reduce((s, q) => s + q.w, 0); let y = nextFloat(r) * ws, id: SpellId = pool.spells[0].id;
        for (const q of pool.spells) { y -= q.w; if (y < 0) { id = q.id; break; } }
        cards.push({ kind: 'spell', id, rarity: rar });
      } else cards.push({ kind: 'hero', id: pool.heroes[nextInt(r, pool.heroes.length)], rarity: rar });
    }
    if (cards.some(c => c.kind === 'spell')) this.spellGiven = true;
    return { type, cards, rarity: Math.max(...cards.map(c => c.rarity)), boughtWave };
  }

  startWave(): void {
    const p = this.p, n = this.wave;
    this.scene = 'fight'; this.sceneT = 0; this.waveT = 0; this.clock = 0; this.lastSpawnClock = -99; this.killedCoins = 0;
    this.monsters = []; this.packs = []; this.pending = []; this.projs = []; this.warnings = []; this.drops = [];
    this.fingerOn = false; this.drag = null; this.autoTarget = -1;
    this.stat = newStat(this.runIndex, this.k.mode, n, this.seed, this.knobText());
    const r = seedFrom(`${this.seed}/w${n}`);
    this.rng = r;
    this.buildSchedule(r);
    // パックの降る時刻：持ち越しは 0、買ったぶんは前の半分が 0、残りが湧きの長さ × 2つめ
    const bought = this.queued.length - this.carried, firstHalf = Math.ceil(bought / 2), dur = spawnDuration(p, n);
    // 湧きの山に合わせる（つまみ）：組の湧く時刻のうち、ウェーブの中ほどに散らした時刻に降らせる（魔物と同時に来る）
    const peaks = [...new Set(this.schedule.map(e => e.time))];
    const k = this.queued.length;
    this.queued.forEach((def, i) => {
      const j = i - this.carried;
      if (this.k.dropSync && peaks.length) this.drops.push({ def, time: peaks[Math.min(peaks.length - 1, Math.floor((i + 1) * peaks.length / (k + 1)))] });
      else this.drops.push({ def, time: j < firstHalf ? 0 : dur * (p.dropTimes[1] ?? 0.4) });
    });
    this.queued = []; this.carried = 0;
    this.events.push('wave');
  }

  knobText(): string {
    const k = this.k;
    const ov = overrideList(this.base, k);
    return `ずらし${k.ringOffset} 塔${k.towerY.toFixed(2)} 呪文${k.spellMode} 輪とパック${k.packRule} 自動=${this.autoLevel().name}` +
      (ov.length ? ` 上書き[${ov.join(' ')}]` : ' 上書きなし') +
      ` 前倒し=${k.pullForward ? '入' : '切'}${k.mode === 'q1' ? ` 方向=${k.introDirs ? 'はじめの順' : '四方'}` : ''}${k.mode === 'q2' ? ` 呪文まぜ=${k.forceSpell ? '入' : '切'}` : ''}`;
  }

  private buildSchedule(r: RngState): void {
    const p = this.p, n = this.wave;
    let pts = budget(p, n);
    const types = (Object.keys(p.monster) as MType[]).filter(t => p.monster[t].fromWave <= n);
    const list: MType[] = [];
    let guard = 0;
    while (guard++ < 1000) {
      const ok = types.filter(t => p.monster[t].cost <= pts);
      if (!ok.length) break;
      const ws = ok.reduce((s, t) => s + p.typeWeight[t], 0); let x = nextFloat(r) * ws, pick = ok[0];
      for (const t of ok) { x -= p.typeWeight[t]; if (x < 0) { pick = t; break; } }
      list.push(pick); pts -= p.monster[pick].cost;
    }
    if (!list.length) list.push('slime');
    const k = Math.min(p.packetCap, p.packetBase + Math.floor((n - 1) / p.packetPerWaves));
    const G = Math.ceil(list.length / k), dur = spawnDuration(p, n);
    const intro = n === 1 && this.k.introDirs && (this.k.mode === 'q1' || (this.k.mode === 'q3' && this.meta.runs === 0));
    const out: Entry[] = [];
    let lastSwarm = -99;
    for (let g = 0; g < G; g++) {
      const used: Dir[] = [];
      for (let j = 0; j < k && g * k + j < list.length; j++) {
        const idx = g * k + j, type = list[idx];
        let dir: Dir;
        if (intro && idx < list.length / 4) dir = 'e';
        else if (intro && idx < list.length / 2) dir = idx % 2 === 0 ? 'e' : 'w';
        else {
          const cand = DIRS.filter(d => !used.includes(d));
          const wts = cand.map(d => intro ? 1 : p.dirWeight[d]);
          let x = nextFloat(r) * wts.reduce((s, v) => s + v, 0); dir = cand[0];
          for (let q = 0; q < cand.length; q++) { x -= wts[q]; if (x < 0) { dir = cand[q]; break; } }
        }
        used.push(dir);
        let time = dur * (g + 0.5) / G;
        if (type === 'swarm') { if (time - lastSwarm < p.groupGap) time = lastSwarm + p.groupGap; lastSwarm = time; }
        out.push({ time, type, dir, done: false, lat: (nextFloat(r) * 2 - 1) * SPAWN_LATERAL });
      }
    }
    out.sort((a, b) => a.time - b.time);
    this.schedule = out;
  }

  private entryPos(dir: Dir, lat: number): { x: number; y: number } {
    const m = this.p.entryMargin;
    if (dir === 'n') return { x: this.towerX + lat, y: this.p.ringTop - m };
    if (dir === 's') return { x: this.towerX + lat, y: this.H + m };
    if (dir === 'e') return { x: W + m, y: this.towerY + lat };
    return { x: -m, y: this.towerY + lat };
  }

  private spawn(e: Entry): void {
    const p = this.p, mp = p.monster[e.type], n = this.wave;
    const count = e.type === 'swarm' ? p.swarmGroup : 1;
    const base = this.entryPos(e.dir, e.lat);
    for (let i = 0; i < count; i++) {
      if (this.monsters.length >= p.limitMonster) break;
      const ang = nextFloat(this.rng) * Math.PI * 2, rr = count > 1 ? nextFloat(this.rng) * p.swarmSpread : 0;
      const hp = mp.hp * hpGrowth(p, n);
      this.monsters.push({ id: this.nextId++, type: e.type, dir: e.dir, x: base.x + Math.cos(ang) * rr, y: base.y + Math.sin(ang) * rr,
        hp, maxHp: hp, size: mp.size, speed: mp.speed, atk: mp.atk, atkInterval: mp.atkInterval, atkCd: 0, slowUntil: 0, slowMul: 1,
        flash: 0, attacking: false, dead: false });
    }
    this.lastSpawnClock = this.clock;
  }

  // ---------- 入力（論理 px の指の位置） ----------
  pointerDown(fx: number, fy: number): void {
    if (this.scene !== 'fight' && this.scene !== 'cleared') return;
    if (this.k.spellMode === 'S2') {
      const i = this.slotRects.findIndex(r => fx >= r.x && fx <= r.x + r.w && fy >= r.y && fy <= r.y + r.h);
      if (i >= 0 && this.slots[i]) { this.drag = { slot: i, fx, fy }; this.fingerOn = false; return; }
    }
    this.fingerOn = true; this.pressHit = false; this.stat.presses++;
    this.fx0 = fx; this.fy0 = fy; const r = this.ringFromFinger(fx, fy); this.ringX = r.x; this.ringY = r.y;
    // 決め C：押さえ始めに輪の中にあったパック（いちばん近い1つ）だけを、この押さえで狙う
    this.lockPack = null; let bd = this.p.ringHit;
    for (const pk of this.packs) { if (pk.tele > 0) continue; const d = Math.hypot(pk.x - r.x, pk.y - r.y); if (d <= bd) { bd = d; this.lockPack = pk; } }
  }
  pointerMove(fx: number, fy: number): void {
    if (this.drag) { this.drag.fx = fx; this.drag.fy = fy; return; }
    if (!this.fingerOn) return;
    this.fx0 = fx; this.fy0 = fy; const r = this.ringFromFinger(fx, fy); this.ringX = r.x; this.ringY = r.y;
  }
  pointerUp(cancel = false): void {
    if (this.drag) {
      const d = this.drag; this.drag = null;
      const s = this.slots[d.slot];
      if (!s) return;
      if (cancel || this.inSlotBand(d.fy) || (this.scene !== 'fight' && this.scene !== 'cleared')) { this.stat.spellCancel++; return; }
      const r = this.ringFromFinger(d.fx, d.fy);
      this.slots.splice(d.slot, 1);
      this.pending.push({ id: s.id, x: r.x, y: r.y, t: this.p.spellPreview, power: s.power, auto: false });
      return;
    }
    if (this.fingerOn && !this.pressHit) this.stat.whiffPresses++;
    this.fingerOn = false;
  }

  /** 指の下や近くにあって、輪の当たりの外のパック（近い順、tap.hiddenMark.max まで） */
  hiddenMarks(): FieldPack[] {
    if (!this.fingerOn) return [];
    const out = this.packs.filter(pk => pk.tele <= 0 && Math.hypot(pk.x - this.fx0, pk.y - this.fy0) <= this.p.hiddenR
      && Math.hypot(pk.x - this.ringX, pk.y - this.ringY) > this.p.ringHit);
    out.sort((a, b) => Math.hypot(a.x - this.fx0, a.y - this.fy0) - Math.hypot(b.x - this.fx0, b.y - this.fy0));
    return out.slice(0, this.p.hiddenMax);
  }

  // ---------- 1歩 ----------
  step(): void {
    this.t++; this.sceneT++;
    if (this.events.length > 256) this.events.length = 0; // 読む人がいないとき（Node）にふくらまない
    const dt = STEP;
    this.updateFx(dt);
    if (this.scene === 'cleared') {
      if (this.sceneT >= this.p.clearFx * 60) this.afterClear();
      return;
    }
    if (this.scene === 'destroyed') {
      if (this.sceneT >= this.p.towerDestroyFx * 60) this.afterDestroy();
      return;
    }
    if (this.scene !== 'fight') return;
    const p = this.p;
    this.waveT++; this.runSteps++;
    this.stat.time = this.waveT / 60;
    if (this.fingerOn) this.stat.holdTime += dt;
    if (this.k.mode === 'q3' && !this.tenMinTold && this.runSteps >= Q3_RUN_TARGET * 60) { this.tenMinTold = true; this.events.push('tenMin'); }

    // 湧きの時計と前倒し
    this.clock += dt;
    const left = this.schedule.filter(e => !e.done);
    if (this.k.pullForward && left.length && this.monsters.length === 0 && this.clock - this.lastSpawnClock >= p.pullGap) {
      const nx = left[0].time - (left[0].type === 'swarm' ? p.telegraph : 0);
      if (nx > this.clock) this.clock = nx; // 予定の時計ごと進める（途中のパックも早く降る。パック.md）
    }
    for (const e of this.schedule) {
      if (e.done) continue;
      if (e.type === 'swarm' && this.clock >= e.time - p.telegraph && !this.warnings.some(w => w.until === e.time)) {
        const pos = this.entryPos(e.dir, e.lat);
        this.warnings.push({ dir: e.dir, x: Math.max(14, Math.min(W - 14, pos.x)), y: Math.max(p.ringTop + 16, Math.min(this.H - 20, pos.y)), until: e.time });
        this.events.push('warn');
      }
      if (this.clock >= e.time && this.monsters.length < p.limitMonster) { e.done = true; this.spawn(e); }
    }
    this.warnings = this.warnings.filter(w => w.until > this.clock);
    const spawnDone = this.schedule.every(e => e.done);

    // パックが降る
    for (let i = this.drops.length - 1; i >= 0; i--) {
      const d = this.drops[i];
      if (this.clock >= d.time || spawnDone) {
        if (this.packs.length >= p.limitPack) continue;
        this.drops.splice(i, 1); this.dropPack(d.def);
      }
    }
    for (const pk of this.packs) {
      if (pk.tele > 0) { pk.tele -= dt; if (pk.tele <= 0) { pk.landT = this.waveT; this.stat.packsDropped++; this.events.push('land'); } }
      if (pk.shake > 0) pk.shake -= dt;
    }

    const rush = this.waveT / 60 > p.durMax;
    const rushOver = rush ? this.waveT / 60 - p.durMax : 0;

    // 魔物が動く・塔を攻める
    for (const m of this.monsters) {
      if (m.flash > 0) m.flash--;
      const dx = this.towerX - m.x, dy = this.towerY - m.y, d = Math.hypot(dx, dy) || 1;
      const stop = p.towerHitR + m.size + p.attackRange;
      const slow = m.slowUntil > this.t ? m.slowMul : 1;
      if (m.slowUntil <= this.t) m.slowMul = 1;
      if (d > stop) {
        m.attacking = false;
        const sp = m.speed * slow * (rush ? p.rushSpeed : 1) * dt;
        const mv = Math.min(sp, d - stop); m.x += dx / d * mv; m.y += dy / d * mv;
      } else {
        if (!m.attacking) { m.attacking = true; m.atkCd = 0; }
        m.atkCd -= dt * (rush ? p.rushAtk * 2 ** Math.floor(rushOver / p.rushDouble) : 1);
        if (m.atkCd <= 0) {
          m.atkCd += m.atkInterval;
          const a = rush ? Math.max(m.atk, this.towerMax * p.rushHitRatio) : m.atk;
          this.towerHp -= a; this.stat.towerDmg[m.dir] += a;
          this.events.push('towerHit');
          this.fx.push({ kind: 'hurt', x: this.towerX, y: this.towerY, x2: 0, y2: 0, t: 0, life: 0.25, r: 0, c: 0 });
        }
      }
    }

    // 指のタップ攻撃
    if (this.tapCd > 0) this.tapCd--;
    if (this.fingerOn && this.tapCd <= 0) {
      this.tapCd = Math.round(p.tapInterval * 60);
      this.stat.attacks++;
      const dmg = this.fingerDmg(); let n = 0;
      for (const m of this.monsters) {
        if (m.dead || !this.visible(m)) continue;
        if (Math.hypot(m.x - this.ringX, m.y - this.ringY) <= p.ringHit) { this.hurt(m, dmg, 'finger', this.ringX, this.ringY); n++; }
      }
      let pkHit = 0;
      const rule = this.k.packRule;
      for (const pk of this.packs) {
        if (pk.tele > 0) continue;
        if (rule === 'B' && n > 0) continue;              // B：輪の中に魔物がいれば、パックには当たらない
        if (rule === 'C' && pk !== this.lockPack) continue; // C：押さえ始めのパックだけ
        if (Math.hypot(pk.x - this.ringX, pk.y - this.ringY) <= p.ringHit) { pk.hits++; pk.shake = 0.1; pkHit++; this.stat.hitsPack++; }
      }
      if (n > 0) { this.stat.hitsMonster += n; this.pressHit = true; this.popNumber(this.ringX, this.ringY - 12, dmg * n); this.events.push('hit'); }
      if (pkHit > 0) { this.pressHit = true; this.events.push('packHit'); }
      if (n === 0 && pkHit === 0) { this.stat.whiffAttacks++; this.events.push('whiff'); }
      for (let i = this.packs.length - 1; i >= 0; i--) if (this.packs[i].hits >= this.packs[i].need) this.openPack(i);
    }

    // 自動化
    const al = this.autoLevel();
    if (this.autoFlash > 0) this.autoFlash -= dt;
    if (al.ratio > 0) {
      if (this.autoCd > 0) this.autoCd--;
      let tgt = this.monsters.find(m => m.id === this.autoTarget && !m.dead);
      if (!tgt || this.autoCd <= 0) {
        let best: Monster | undefined, bd = p.autoRange;
        for (const m of this.monsters) {
          if (m.dead || !this.visible(m)) continue;
          const d = Math.hypot(m.x - this.towerX, m.y - this.towerY);
          if (d <= bd && (d < bd || !best || m.id < best.id)) { bd = d; best = m; }
        }
        tgt = best; this.autoTarget = tgt ? tgt.id : -1;
      }
      if (tgt) {
        const dx = tgt.x - this.autoX, dy = tgt.y - this.autoY, d = Math.hypot(dx, dy);
        const mv = p.autoMove * dt;
        if (d > mv) { this.autoX += dx / d * mv; this.autoY += dy / d * mv; } else { this.autoX = tgt.x; this.autoY = tgt.y; }
        if (this.autoCd <= 0 && Math.hypot(tgt.x - this.autoX, tgt.y - this.autoY) <= p.autoRingR) {
          this.autoCd = Math.round(al.interval * 60);
          const dmg = this.fingerDmg() * al.ratio;
          for (const m of this.monsters) if (!m.dead && this.visible(m) && Math.hypot(m.x - this.autoX, m.y - this.autoY) <= p.autoRingR) this.hurt(m, dmg, 'auto', this.autoX, this.autoY);
          this.autoFlash = 0.12; this.events.push('auto');
        }
      }
    }

    // 英雄
    for (const h of this.heroes) {
      if (h.stackFx > 0) h.stackFx -= dt;
      if (h.atkFx > 0) h.atkFx -= dt;
      if (this.t - h.born < p.heroSpawnFx * 60) continue;
      h.cd -= dt;
      if (h.cd > 0) continue;
      const hp = p.hero[h.role];
      const inRange = this.monsters.filter(m => !m.dead && this.visible(m) && Math.hypot(m.x - h.x, m.y - h.y) <= hp.range);
      if (!inRange.length) { h.cd = 0; continue; }
      h.cd = hp.interval;
      inRange.sort((a, b) => Math.hypot(a.x - this.towerX, a.y - this.towerY) - Math.hypot(b.x - this.towerX, b.y - this.towerY) || a.id - b.id);
      const tg = inRange[0], dmg = this.heroDmg(h);
      h.atkFx = 0.3; h.aimX = tg.x; h.aimY = tg.y;
      if (h.role === 'sword') { this.hurt(tg, dmg, 'hero', h.x, h.y); this.fx.push({ kind: 'slash', x: tg.x, y: tg.y, x2: h.x, y2: h.y, t: 0, life: 0.15, r: 14, c: 0 }); }
      else if (h.role === 'archer') this.projs.push({ x: h.x, y: h.y - 20, target: tg.id, dmg, speed: hp.projSpeed, life: 2 });
      else if (h.role === 'shield') {
        for (const m of inRange) { this.hurt(m, dmg, 'hero', h.x, h.y); m.slowUntil = this.t + hp.slowTime * 60; m.slowMul = Math.min(m.slowMul, hp.slow); }
        this.fx.push({ kind: 'aura', x: h.x, y: h.y, x2: 0, y2: 0, t: 0, life: 0.3, r: hp.range, c: 0 });
      } else if (h.role === 'spear') {
        const dx = tg.x - h.x, dy = tg.y - h.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d;
        for (const m of inRange) {
          const ax = m.x - h.x, ay = m.y - h.y, along = ax * ux + ay * uy, side = Math.abs(ax * uy - ay * ux);
          if (along >= 0 && along <= hp.range && side <= hp.lineWidth / 2) this.hurt(m, dmg, 'hero', h.x, h.y);
        }
        this.fx.push({ kind: 'line', x: h.x, y: h.y, x2: h.x + ux * hp.range, y2: h.y + uy * hp.range, t: 0, life: 0.15, r: hp.lineWidth, c: 0 });
      }
    }
    for (let i = this.projs.length - 1; i >= 0; i--) {
      const b = this.projs[i], tg = this.monsters.find(m => m.id === b.target && !m.dead);
      b.life -= dt;
      if (!tg || b.life <= 0) { this.projs.splice(i, 1); continue; }
      const dx = tg.x - b.x, dy = tg.y - b.y, d = Math.hypot(dx, dy), mv = b.speed * dt;
      if (d <= mv + tg.size * 0.5) { this.hurt(tg, b.dmg, 'hero', b.x, b.y); this.projs.splice(i, 1); }
      else { b.x += dx / d * mv; b.y += dy / d * mv; }
    }

    // 呪文の予告→効く
    for (let i = this.pending.length - 1; i >= 0; i--) {
      const s = this.pending[i]; s.t -= dt;
      if (s.t > 0) continue;
      this.pending.splice(i, 1); this.castSpell(s);
    }

    // 倒れた魔物
    for (let i = this.monsters.length - 1; i >= 0; i--) {
      const m = this.monsters[i];
      if (m.hp > 0) continue;
      m.dead = true; this.monsters.splice(i, 1);
      const mp = p.monster[m.type], n = this.wave, b = budget(p, n);
      const coin = p.coinBase * market(p, n) * mp.coin / b;
      const cost = m.type === 'swarm' ? mp.cost / p.swarmGroup : mp.cost;
      const fame = famePerWave(p, n) * p.fameKillShare * cost / b * (n > this.meta.record ? p.fameBeyond : 1);
      this.coins += coin; this.killedCoins += coin; this.stat.kills++;
      if (this.k.mode === 'q3') this.runFame += fame;
      this.fx.push({ kind: 'burst', x: m.x, y: m.y, x2: 0, y2: 0, t: 0, life: 0.3, r: m.size, c: 0 });
      this.fx.push({ kind: 'coin', x: m.x, y: m.y, x2: 0, y2: 0, t: 0, life: p.coinFly, r: 5, c: 0 });
      this.events.push('kill');
    }

    // 終わりの判定（塔が先）
    if (this.towerHp <= 0) {
      this.towerHp = 0; this.scene = 'destroyed'; this.sceneT = 0; this.fingerOn = false; this.drag = null;
      this.finishStat('塔が壊れた'); this.events.push('destroyed');
      return;
    }
    if (spawnDone && this.monsters.length === 0) this.clearWave();
  }

  private hurt(m: Monster, dmg: number, src: Source, fromX: number, fromY: number): void {
    if (m.dead || m.hp <= 0) return;
    this.stat.dmg[src] += Math.min(dmg, m.hp);
    m.hp -= dmg; m.flash = 3;
    const dx = m.x - fromX, dy = m.y - fromY, d = Math.hypot(dx, dy);
    if (d > 0.5 && src !== 'spell') { m.x += dx / d * KNOCKBACK * 0.3; m.y += dy / d * KNOCKBACK * 0.3; }
  }

  private popNumber(x: number, y: number, v: number): void {
    // 同じ場所の数はまとめる（ui.damageText.mergeRadius 24。合計の数を1つ）
    const near = this.floats.find(f => f.t < 0.3 && Math.hypot(f.x - x, f.y - y) <= 24);
    if (near) { near.v += v; near.t = 0; return; }
    if (this.floats.length >= this.p.damageTextMax) this.floats.shift();
    this.floats.push({ x, y, v, t: 0 });
  }

  private updateFx(dt: number): void {
    for (let i = this.fx.length - 1; i >= 0; i--) { const f = this.fx[i]; f.t += dt; if (f.t >= f.life) this.fx.splice(i, 1); }
    for (let i = this.floats.length - 1; i >= 0; i--) { const f = this.floats[i]; f.t += dt; f.y -= 40 * dt; if (f.t >= this.p.damageTextTime) this.floats.splice(i, 1); }
  }

  /** 方向ごとの英雄の数（塔から見た向き） */
  heroDirCount(): Record<Dir, number> {
    const c: Record<Dir, number> = { n: 0, e: 0, s: 0, w: 0 };
    for (const h of this.heroes) c[this.dirOf(h.x, h.y)]++;
    return c;
  }
  dirOf(x: number, y: number): Dir {
    const dx = x - this.towerX, dy = y - this.towerY;
    return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'e' : 'w') : (dy > 0 ? 's' : 'n');
  }

  private placeOk(x: number, y: number, gap: number): boolean {
    const p = this.p, r = 19;
    if (y - r < p.ringTop || y + r > this.H - 34 || x - 13 < 0 || x + 13 > W) return false;
    if (this.inSlotBand(y - r) || this.inSlotBand(y + r) || (this.k.spellMode === 'S2' && y - r < this.slotBand[0] && y + r > this.slotBand[1])) return false;
    if (Math.hypot(x - this.towerX, y - this.towerY) < p.towerHitR + 30) return false;
    for (const o of this.packs) if (Math.hypot(o.x - x, o.y - y) < gap) return false;
    for (const o of this.heroes) if (Math.hypot(o.x - x, o.y - y) < gap) return false;
    return true;
  }

  private dropPack(def: PackDef): void {
    const p = this.p, r = this.rng, cnt = this.heroDirCount(), mx = Math.max(...DIRS.map(d => cnt[d]));
    const wts = DIRS.map(d => 1 + this.k.dropBias * (mx - cnt[d]));
    const ang0: Record<Dir, number> = { e: 0, s: Math.PI / 2, w: Math.PI, n: -Math.PI / 2 };
    let pos: { x: number; y: number } | null = null;
    for (const gap of [p.dropMinGap, p.dropMinGap / 2]) {
      for (let tries = 0; tries < 40 && !pos; tries++) {
        let x = nextFloat(r) * wts.reduce((s, v) => s + v, 0), dir: Dir = 'n';
        for (let i = 0; i < 4; i++) { x -= wts[i]; if (x < 0) { dir = DIRS[i]; break; } }
        const a = ang0[dir] + (nextFloat(r) * 2 - 1) * p.dropAngle * Math.PI / 180;
        const rr = p.dropRingMin + nextFloat(r) * (p.dropRingMax - p.dropRingMin);
        const cx = this.towerX + Math.cos(a) * rr, cy = this.towerY + Math.sin(a) * rr;
        if (this.placeOk(cx, cy, gap)) pos = { x: cx, y: cy };
      }
      if (pos) break;
    }
    if (!pos) pos = { x: this.towerX + p.dropRingMin, y: this.towerY };
    const need = Math.max(1, Math.ceil(p.hitsToOpen[def.rarity] * this.k.hitsMul));
    this.packs.push({ def, x: pos.x, y: pos.y, tele: p.dropTele, hits: 0, need, landT: 0, shake: 0 });
  }

  private openPack(i: number): void {
    const p = this.p, pk = this.packs[i];
    this.packs.splice(i, 1);
    this.stat.packsOpened++; this.stat.openDelays.push((this.waveT - pk.landT) / 60);
    this.fx.push({ kind: 'open', x: pk.x, y: pk.y, x2: 0, y2: 0, t: 0, life: p.openFx[pk.def.rarity] ?? 0.3, r: 40 + 40 * pk.def.rarity, c: pk.def.rarity });
    this.events.push('open' + pk.def.rarity);
    const power = market(p, pk.def.boughtWave);
    const heroCards = pk.def.cards.filter(c => c.kind === 'hero');
    heroCards.forEach((c, j) => {
      const off = heroCards.length > 1 ? (j - (heroCards.length - 1) / 2) * p.placeMinGap : 0;
      this.addHero(c.id as Role, c.rarity, power, pk.x + off, pk.y);
    });
    for (const c of pk.def.cards) {
      if (c.kind !== 'spell') continue;
      const sp = { id: c.id as SpellId, power: this.spellPower(c.id as SpellId, pk.def.boughtWave) };
      if (this.k.spellMode !== 'S2') {
        const at = this.k.spellMode === 'S1b' ? this.crowdPoint(sp.id === 'fire1' ? p.fire1.radius : p.ice1.radius) ?? pk : pk;
        this.pending.push({ ...sp, x: at.x, y: at.y, t: p.spellPreview, auto: false });
      }
      else {
        if (this.slots.length >= p.slotCount) {
          const old = this.slots.shift()!; this.stat.spellOverflow++;
          this.pending.push({ ...old, x: this.towerX, y: this.towerY, t: p.spellPreview, auto: true });
        }
        this.slots.push(sp); this.events.push('slot');
      }
    }
  }

  /** S1b：呪文の輪にいちばん多く魔物が入る所（魔物の位置を中心の候補にする）。いなければ null */
  crowdPoint(radius: number): { x: number; y: number } | null {
    let best: Monster | null = null, bn = 0;
    for (const c of this.monsters) {
      if (c.dead || !this.visible(c)) continue;
      let n = 0; for (const m of this.monsters) if (!m.dead && Math.hypot(m.x - c.x, m.y - c.y) <= radius) n++;
      const closer = best && Math.hypot(c.x - this.towerX, c.y - this.towerY) < Math.hypot(best.x - this.towerX, best.y - this.towerY);
      if (n > bn || (n === bn && closer)) { bn = n; best = c; }
    }
    return best ? { x: best.x, y: best.y } : null;
  }

  spellPower(id: SpellId, boughtWave: number): number { return id === 'fire1' ? this.p.fire1.power * market(this.p, boughtWave) : 0; }

  private addHero(role: Role, rarity: number, power: number, x: number, y: number): void {
    const p = this.p;
    const same = this.heroes.filter(h => h.role === role && h.rarity === rarity);
    if (same.length < p.sameMax && this.heroes.length < p.fieldMax) {
      this.heroes.push({ role, rarity, power, x, y, cd: 0, born: this.t, stackFx: 0, atkFx: 0, aimX: x, aimY: y - 10 });
      return;
    }
    const pool = same.length ? same : this.heroes;
    pool.sort((a, b) => same.length ? Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y) : a.power - b.power);
    const h = pool[0]; if (!h) return;
    h.power += power * p.stackMul; h.stackFx = 0.5;
  }

  private castSpell(s: PendingSpell): void {
    const p = this.p; let n = 0;
    if (s.id === 'fire1') {
      for (const m of this.monsters) if (!m.dead && Math.hypot(m.x - s.x, m.y - s.y) <= p.fire1.radius) { this.hurt(m, s.power, 'spell', s.x, s.y); n++; }
      this.fx.push({ kind: 'spell', x: s.x, y: s.y, x2: 0, y2: 0, t: 0, life: 0.5, r: p.fire1.radius, c: 0 });
    } else {
      for (const m of this.monsters) if (!m.dead && Math.hypot(m.x - s.x, m.y - s.y) <= p.ice1.radius) { m.slowUntil = this.t + p.ice1.duration * 60; m.slowMul = Math.min(m.slowMul, p.ice1.slow); n++; }
      this.fx.push({ kind: 'spell', x: s.x, y: s.y, x2: 0, y2: 0, t: 0, life: 0.6, r: p.ice1.radius, c: 1 });
    }
    this.stat.spellCasts++; if (n === 0) this.stat.spellWhiff++;
    this.events.push('spell');
  }

  private finishStat(result: string): void {
    const s = this.stat;
    s.result = result; s.towerHpEnd = Math.ceil(this.towerHp); s.coinsEnd = Math.floor(this.coins); s.heroesEnd = this.heroes.length;
    s.packsCarried = this.packs.length + this.drops.length;
    if (this.fingerOn && !this.pressHit) s.whiffPresses++;
    this.logs.push(s);
  }

  private clearWave(): void {
    const p = this.p, n = this.wave;
    this.fingerOn = false; this.drag = null;
    // 生き延びたときの確定：予告中の呪文は捨てる、開けていないパックは持ち越し
    this.pending = [];
    this.queued = [...this.packs.map(pk => pk.def), ...this.drops.map(d => d.def)];
    this.carried = this.queued.length;
    const clearCoin = p.clearCoinRatio * this.killedCoins;
    this.coins += clearCoin;
    if (n === 1 && this.coins < p.firstShopCoinMin) this.coins = p.firstShopCoinMin;
    let fame = 0;
    if (this.k.mode === 'q3') { fame = famePerWave(p, n) * (n > this.meta.record ? p.fameBeyond : 1); this.runFame += fame; }
    this.lastShopResult = { fame, coins: clearCoin };
    this.towerHp = Math.min(this.towerMax, this.towerHp + this.towerMax * p.towerRegen);
    this.finishStat('生き延びた');
    this.scene = 'cleared'; this.sceneT = 0; this.events.push('cleared');
  }

  private afterClear(): void {
    if (this.k.mode === 'q1') { this.scene = 'q1end'; this.events.push('end'); return; }
    if (this.k.mode === 'q2' && this.wave >= Q2_START.lastWave) { this.scene = 'q2end'; this.events.push('end'); return; }
    this.scene = 'shop'; this.sceneT = 0; this.boughtThisShop = []; this.events.push('shop');
  }

  private afterDestroy(): void {
    if (this.k.mode === 'q1') { this.scene = 'q1end'; this.events.push('end'); return; }
    if (this.k.mode === 'q2') { this.scene = 'q2end'; this.events.push('end'); return; }
    this.endRun();
  }

  /** ランを終える（塔が壊れた／やめた）。Q3 だけ名声と記録 */
  endRun(): void {
    if (this.scene === 'fight') { this.finishStat('やめた'); }
    if (this.k.mode !== 'q3') { this.scene = this.k.mode === 'q1' ? 'q1end' : 'q2end'; return; }
    const reached = this.scene === 'fight' || this.scene === 'destroyed' ? this.wave - 1 : this.wave;
    this.resultInfo = { reached, prevRecord: this.meta.record, fame: this.runFame, time: this.runSteps / 60 };
    this.meta.fame += this.runFame; this.meta.runs++;
    if (reached > this.meta.record) this.meta.record = reached;
    this.runLogs.push({ run: this.runIndex, reached, prevRecord: this.resultInfo.prevRecord, fame: this.runFame, time: this.runSteps / 60, knobs: this.knobText() });
    this.scene = 'result'; this.sceneT = 0; this.events.push('result');
  }
  resultInfo = { reached: 0, prevRecord: 0, fame: 0, time: 0 };
  runLogs: { run: number; reached: number; prevRecord: number; fame: number; time: number; knobs: string }[] = [];

  // ---------- ショップ ----------
  canBuy(t: PackType): boolean {
    return this.scene === 'shop' && this.boughtThisShop.length < this.p.shopBuyMax
      && this.queued.length < this.p.limitPack && this.coins >= this.packPrice(t);
  }
  buy(t: PackType): boolean {
    if (!this.canBuy(t)) return false;
    this.coins -= this.packPrice(t);
    const r = seedFrom(`${this.seed}/shop${this.wave}/${this.boughtThisShop.length}`);
    const def = this.rollPack(t, this.wave, r, this.boughtThisShop.length === 0);
    this.boughtThisShop.push(def); this.queued.push(def);
    this.events.push('buy');
    return true;
  }
  nextWave(): void { if (this.scene !== 'shop') return; this.wave++; this.startWave(); }

  // ---------- 強化画面 ----------
  toUpgrade(): void { if (this.scene === 'result') this.scene = 'upgrade'; }
  buyUpgrade(id: 'tapDmg' | 'heroDmg' | 'towerHp' | 'tapAuto'): boolean {
    if (this.scene !== 'upgrade') return false;
    if (id === 'tapAuto' && this.k.auto >= autoLevels(this.p).length - 1) return false;
    const c = this.upCost(id);
    if (this.meta.fame < c) return false;
    this.meta.fame -= c;
    if (id === 'tapAuto') this.k.auto++; else this.meta.up[id]++;
    this.events.push('upgrade');
    return true;
  }
}
