// シード付き乱数（sfc32）。yarikomi の確認版から流用。Math.random は使わない。
export type RngState = [number, number, number, number];

export function seedFrom(text: string): RngState {
  // 文字列から4つの32bit値を作る（cyrb128 と同じ考え方の、FNV 混ぜ）
  let h1 = 0x811c9dc5, h2 = 0x01000193, h3 = 0x9e3779b9, h4 = 0x85ebca6b;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ c, 0x85ebca6b) >>> 0;
    h3 = Math.imul(h3 ^ c, 0xc2b2ae35) >>> 0;
    h4 = Math.imul(h4 ^ c, 0x27d4eb2f) >>> 0;
  }
  const s: RngState = [h1, h2, h3, h4];
  for (let i = 0; i < 12; i++) nextU32(s); // 最初の数回は捨てる
  return s;
}

export function nextU32(s: RngState): number {
  let [a, b, c, d] = s;
  const t = (((a + b) >>> 0) + d) >>> 0;
  d = (d + 1) >>> 0;
  a = b ^ (b >>> 9);
  b = (c + (c << 3)) >>> 0;
  c = ((c << 21) | (c >>> 11)) >>> 0;
  c = (c + t) >>> 0;
  s[0] = a >>> 0; s[1] = b; s[2] = c; s[3] = d;
  return t;
}

/** 0 以上 n 未満の整数（小数を使わない。剰余の偏りは n が小さいので許す） */
export function nextInt(s: RngState, n: number): number {
  return nextU32(s) % n;
}

/** FNV-1a 32bit。状態の指紋に使う */
export function fnv1a(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0;
  return h.toString(16).padStart(8, '0');
}

/** 0 以上 1 未満 */
export function nextFloat(s: RngState): number {
  return nextU32(s) / 4294967296;
}
