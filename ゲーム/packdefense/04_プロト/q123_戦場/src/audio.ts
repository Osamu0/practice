// 仮の合成音（ファイルなし）。iOS の手当ては確認版（02_プリプロ/tech_check/src/audio.ts）と同じ考え方を短くしたもの。
let ctx: AudioContext | null = null, master: GainNode | null = null, voices = 0;
const lastAt: Record<string, number> = {};
export let enabled = true;
export function setEnabled(v: boolean): void { enabled = v; }
export function unlock(): void {
  try {
    if (!ctx) {
      const AC: typeof AudioContext = (window as any).AudioContext ?? (window as any).webkitAudioContext;
      ctx = new AC(); master = ctx.createGain(); master.gain.value = 0.45; master.connect(ctx.destination);
      const b = ctx.createBuffer(1, 1, 22050), s = ctx.createBufferSource(); s.buffer = b; s.connect(ctx.destination); s.start();
    }
    if (ctx.state !== 'running') {
      const c = ctx; let done = false;
      c.resume().then(() => { done = true; }, () => { done = true; });
      setTimeout(() => { if (ctx === c && (!done || c.state !== 'running')) { try { void c.close(); } catch { /* */ } ctx = null; master = null; voices = 0; } }, 600);
    }
  } catch { /* 音が出なくても遊べる */ }
}
export function suspend(): void { if (ctx && ctx.state === 'running') void ctx.suspend(); }
export function audioState(): string { return ctx ? ctx.state : 'none'; }

type Tone = { f: number[]; len: number; type: OscillatorType; vol: number; gap: number; slide?: number };
const SFX: Record<string, Tone> = {
  hit: { f: [880], len: 0.05, type: 'triangle', vol: 0.25, gap: 0.05 },
  whiff: { f: [660], len: 0.03, type: 'triangle', vol: 0.06, gap: 0.09 },
  packHit: { f: [1320], len: 0.04, type: 'square', vol: 0.12, gap: 0.05 },
  kill: { f: [220], len: 0.07, type: 'square', vol: 0.2, gap: 0.03, slide: 80 },
  auto: { f: [990], len: 0.03, type: 'sine', vol: 0.08, gap: 0.08 },
  open0: { f: [523, 659, 784], len: 0.06, type: 'triangle', vol: 0.3, gap: 0 },
  open1: { f: [523, 659, 784, 1047, 1319], len: 0.07, type: 'triangle', vol: 0.35, gap: 0 },
  open2: { f: [392, 523, 659, 784, 1047, 1319, 1568], len: 0.08, type: 'triangle', vol: 0.4, gap: 0 },
  spell: { f: [196, 147], len: 0.12, type: 'sawtooth', vol: 0.22, gap: 0.1 },
  towerHit: { f: [90], len: 0.12, type: 'sine', vol: 0.35, gap: 0.5 },
  wave: { f: [392, 523], len: 0.15, type: 'square', vol: 0.15, gap: 0 },
  warn: { f: [740, 740], len: 0.06, type: 'square', vol: 0.12, gap: 0.3 },
  cleared: { f: [659, 784, 1047], len: 0.09, type: 'triangle', vol: 0.3, gap: 0 },
  destroyed: { f: [330, 262, 196], len: 0.18, type: 'triangle', vol: 0.3, gap: 0 },
  buy: { f: [784, 1047], len: 0.05, type: 'triangle', vol: 0.25, gap: 0 },
  slot: { f: [1047, 1568], len: 0.05, type: 'sine', vol: 0.2, gap: 0 },
  land: { f: [300], len: 0.06, type: 'sine', vol: 0.2, gap: 0.05 },
};
export function play(name: string): void {
  const s = SFX[name]; if (!s || !enabled || !ctx || !master || ctx.state !== 'running' || voices >= 12) return;
  const now = ctx.currentTime;
  if (lastAt[name] !== undefined && now - lastAt[name] < s.gap) return;
  lastAt[name] = now;
  const g = ctx.createGain(); g.connect(master);
  s.f.forEach((f, k) => {
    const o = ctx!.createOscillator(); o.type = s.type; const t = now + k * s.len;
    o.frequency.setValueAtTime(f * (name === 'hit' ? 0.95 + Math.random() * 0.1 : 1), t);
    if (s.slide) o.frequency.exponentialRampToValueAtTime(s.slide, t + s.len);
    o.connect(g); o.start(t); o.stop(t + s.len + 0.02);
  });
  const end = now + s.f.length * s.len + 0.02;
  g.gain.setValueAtTime(0.0001, now); g.gain.exponentialRampToValueAtTime(s.vol, now + 0.006); g.gain.exponentialRampToValueAtTime(0.0001, end);
  voices++; setTimeout(() => { voices--; }, (end - now) * 1000 + 30);
}
