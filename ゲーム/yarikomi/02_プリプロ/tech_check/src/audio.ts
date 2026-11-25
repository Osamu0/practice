// 音：外部ファイルなしで Web Audio の合成音を鳴らす。最初のタップで AudioContext を起こす（スマホの自動再生の制限のため）。
let ctx: AudioContext | null = null;
export const audioLog: string[] = [];

export function unlock(): void {
  if (!ctx) ctx = new AudioContext();
  if (ctx.state === 'suspended') void ctx.resume();
}
export function audioState(): string { return ctx ? ctx.state : 'none'; }

/** 短い音を鳴らす。dest を渡せば OfflineAudioContext でも同じ音を作れる（テスト用） */
export function blip(freq: number, c: BaseAudioContext | null = ctx, at = 0): void {
  if (!c) return;
  const t = (c.currentTime || 0) + at;
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = 'triangle';
  o.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.3, t + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
  o.connect(g).connect(c.destination);
  o.start(t); o.stop(t + 0.13);
  audioLog.push(`${freq}@${c.constructor.name}`);
}
