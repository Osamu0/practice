// 大きな数の短い表記（縦の画面の上の端に収まるように）。案：万・億・兆・京 まで漢字、その先は「1.23e20」。
// どこから e 表記にするか、単位の字は 03（game-design-ux・game-spec-balance）で決める。ここでは長さの確かめだけ。
const UNITS: [number, string][] = [[1e16, '京'], [1e12, '兆'], [1e8, '億'], [1e4, '万']];

function mant(v: number): string {
  // 有効数字3けた程度。整数部が4けたまで
  if (v < 10) return trim(v.toFixed(2));
  if (v < 100) return trim(v.toFixed(1));
  return Math.floor(v).toString();
}
function trim(s: string): string { return s.replace(/\.?0+$/, ''); }

export function fmt(n: number): string {
  if (Number.isNaN(n)) return '?';
  if (n < 0) return '-' + fmt(-n);
  if (n === Infinity) return '∞';
  if (n < 1e4) return Math.floor(n).toString();
  if (n < 1e20) {
    for (const [u, s] of UNITS) if (n >= u) {
      const m = mant(n / u);
      if (Number(m) >= 10000 && u < 1e16) continue; // 繰り上がり（9999.99万 → 1億）は上の単位で
      return m + s;
    }
  }
  // e 表記：仮数は1けたの小数。指数が3けたなら仮数は整数
  const e = Math.floor(Math.log10(n));
  let m = n / 10 ** e;
  if (m >= 9.95) { m = 1; return (e + 1 >= 100 ? '1' : '1.0') + 'e' + (e + 1); }
  return (e >= 100 ? Math.round(m).toString() : m.toFixed(1)) + 'e' + e;
}
