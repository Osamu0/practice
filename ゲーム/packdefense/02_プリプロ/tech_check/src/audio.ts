// 音：外部ファイルなしで Web Audio の合成音を鳴らす。
// iOS の手当て（市場調査 5、技術選定 R4）：
//  1. AudioContext は人の操作（pointerdown と touchend の両方）の中で作り、resume する。最初に無音を1つ鳴らす
//  2. 裏から戻ったら、次の操作で resume しなおす（state が 'interrupted' / 'suspended' のとき）
//  3. resume が返ってこない・running にならないとき（iOS 26 のホーム画面アプリで報告。WebKit bug 291892）は、
//     古い AudioContext を閉じて作り直す
//  4. 同時に鳴る音の数と、同じ音の間隔に上限を置く（後半に当たりの音が何百も重ならないように）
let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let voices = 0;
const lastAt: Record<string, number> = {};
export const MAX_VOICES = 12;
export const audioLog: string[] = [];
export let recreated = 0;

function make(): void {
  const AC: typeof AudioContext = (window as any).AudioContext ?? (window as any).webkitAudioContext;
  ctx = new AC();
  master = ctx.createGain(); master.gain.value = 0.5; master.connect(ctx.destination);
  // 無音を1つ鳴らして、iOS の音の出口を開く
  const b = ctx.createBuffer(1, 1, 22050); const s = ctx.createBufferSource(); s.buffer = b; s.connect(ctx.destination); s.start();
}

/** 操作のたびに呼ぶ（安い）。必要なときだけ作る・起こす */
export function unlock(): void {
  if (!ctx) { make(); audioLog.push('create'); }
  const c = ctx!;
  if (c.state !== 'running') {
    const before = c.state;
    let done = false;
    c.resume().then(() => { done = true; audioLog.push(`resume ${before}->${c.state}`); }, () => { done = true; });
    // 0.6秒たっても running にならなければ作り直す（次の操作で、新しいほうを resume する）
    setTimeout(() => {
      if (ctx === c && (!done || c.state !== 'running')) {
        audioLog.push(`recreate (state=${c.state}, resolved=${done})`);
        recreated++;
        try { void c.close(); } catch { /* 閉じられなくても捨てる */ }
        ctx = null; master = null; voices = 0;
      }
    }, 600);
  }
}
export function audioState(): string { return ctx ? ctx.state : 'none'; }

type Sfx = 'hit' | 'kill' | 'open';

/** 合成の効果音。c を渡せば OfflineAudioContext でも同じ音を作れる（テスト用） */
export function play(name: Sfx, c: BaseAudioContext | null = ctx, out: AudioNode | null = master): boolean {
  if (!c || !out) return false;
  const now = c.currentTime;
  const minGap = name === 'hit' ? 0.05 : name === 'kill' ? 0.03 : 0;
  if (c === ctx) {
    if (voices >= MAX_VOICES) return false;
    if (lastAt[name] !== undefined && now - lastAt[name] < minGap) return false;
    lastAt[name] = now;
  }
  const g = c.createGain(); g.connect(out);
  const notes = name === 'open' ? [523, 659, 784, 1047] : name === 'kill' ? [220] : [880];
  const len = name === 'open' ? 0.09 : 0.07;
  notes.forEach((f, k) => {
    const o = c.createOscillator();
    o.type = name === 'kill' ? 'square' : 'triangle';
    const t = now + k * len;
    o.frequency.setValueAtTime(f, t);
    if (name === 'kill') o.frequency.exponentialRampToValueAtTime(80, t + len);
    o.connect(g); o.start(t); o.stop(t + len + 0.02);
  });
  const end = now + notes.length * len + 0.02;
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(0.35, now + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, end);
  if (c === ctx) { voices++; setTimeout(() => { voices--; }, (end - now) * 1000 + 30); }
  audioLog.push(name);
  return true;
}

/** 裏に回ったら止めて電池を守る。戻ったら、次の操作の unlock() で起こす */
export function suspendForBackground(): void { if (ctx && ctx.state === 'running') void ctx.suspend(); }
