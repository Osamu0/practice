// 剣士 sword1 ラフ（段階1）。原点＝台座の中心。y は上がマイナス。単位＝論理px（ゲームの表示の大きさ）
const fs = require('fs');
const K = '#1B2233';
const ped = (sil) => `<ellipse cx="0" cy="0" rx="15" ry="6" fill="${sil ? '#D5D9E0' : '#FFFFFF'}" stroke="${sil ? '#8A93A6' : '#2F6FD6'}" stroke-width="2.5"/>`;
const ln = (x1, y1, x2, y2, w = 4) => `<path d="M${x1} ${y1} L${x2} ${y2}" stroke="${K}" stroke-width="${w}" stroke-linecap="round" fill="none"/>`;
const pth = (d) => `<path d="${d}" fill="${K}" stroke="${K}" stroke-width="2" stroke-linejoin="round"/>`;
const cir = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${K}" stroke="${K}" stroke-width="2"/>`;
const ell = (x, y, rx, ry, rot = 0) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${K}" stroke="${K}" stroke-width="2" transform="rotate(${rot} ${x} ${y})"/>`;
const sword = (x1, y1, x2, y2, w = 5) => {
  // 刃＋つば（つばは刃に直角、長さ7）
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L;
  const gx = x1 + ux * 3, gy = y1 + uy * 3, px = -uy * 3.5, py = ux * 3.5;
  return ln(x1, y1, x2, y2, w) + ln(gx - px, gy - py, gx + px, gy + py, 3);
};
const legs = (s = 0, w = 5, top = -9) => ln(-3, top, -3 - s, -1.5, w) + ln(3, top, 3 + s, -1.5, w);
const body = () => pth('M-8 -4 L-6 -19 L6 -19 L8 -4 Z');
const head = (y = -26, r = 8) => cir(0, y, r);
const dome = (y = -26, r = 9) => pth(`M${-r} ${y} A${r} ${r} 0 0 1 ${r} ${y} Z`);
const rarm = () => ln(5, -17, 8, -11, 4);

const R = [
  { n: 0, name: 'いま（参考）', note: '02 の見本', a: false, ref: true,
    s: () => ln(-4, -6, -4, -1, 4) + ln(4, -6, 4, -1, 4) + sword(9, -10, 20, -34, 5) + pth('M-9 -4 L-6 -20 L6 -20 L9 -4 Z') + head(-28) + dome(-29, 8) + ln(0, -36, 0, -39, 3) },
  { n: 1, name: '小さな騎士', note: 'マント＋兜の房', a: true,
    s: () => pth('M-8 -20 L-12 -3 L10 -3 L8 -20 Z') + legs() + body() + rarm() + sword(8, -11, 18, -33) + head() + dome(-27) + ln(0, -36, 0, -40, 3) },
  { n: 2, name: 'どんぶり兜', note: '大きいお下がりの兜、がに股', a: false,
    s: () => legs(4, 5) + pth('M-7 -6 L-6 -19 L6 -19 L7 -6 Z') + `<path d="M-6 -17 L-11 -12 L-6 -9" stroke="${K}" stroke-width="4" fill="none" stroke-linejoin="round"/>` + rarm() + sword(8, -12, 21, -35) + head(-25, 7.5) +
      `<g transform="rotate(-8 0 -28)">${pth('M-10.5 -28 A10.5 10 0 0 1 10.5 -28 Z')}<rect x="-12.5" y="-29.5" width="25" height="3" rx="1.5" fill="${K}" stroke="${K}" stroke-width="2"/></g>` },
  { n: 3, name: '耳当て兜', note: '丸い耳当てが左右に下がる', a: false,
    s: () => legs(1) + body() + rarm() + sword(8, -11, 19, -33) + head(-25) + dome(-26) + ell(-9, -23, 3.5, 5) + ell(9, -23, 3.5, 5) + cir(0, -35.5, 2) },
  { n: 4, name: '両手で正眼', note: '体の前で両手に構える', a: true,
    s: () => legs(1) + body() + ln(-5, -17, 1, -12, 4) + ln(5, -17, 1, -12, 4) + sword(1, -12, 12, -38) + head() + dome(-27) },
  { n: 5, name: '高く掲げる', note: '勝ちどき。高さが44をこえる', a: true,
    s: () => legs(1) + body() + ln(5, -18, 10, -29, 4) + sword(10, -29, 19, -47) + head() + dome(-27) },
  { n: 6, name: '羽根の房', note: '兜から後ろへ大きな房', a: true,
    s: () => legs(1) + body() + rarm() + sword(8, -11, 18, -33) + head() + dome(-27) + pth('M0 -34 Q-6 -43 -15 -35 Q-8 -37 -2 -30 Z') },
  { n: 7, name: 'ずんぐり踏ん張り', note: '2頭身、横に広い、大股', a: false,
    s: () => ln(-4, -8, -9, -1.5, 6) + ln(4, -8, 9, -1.5, 6) + `<rect x="-10" y="-20" width="20" height="14" rx="5" fill="${K}" stroke="${K}" stroke-width="2"/>` + ln(8, -16, 11, -12, 5) + sword(11, -12, 22, -30) + head(-27) + pth('M-9 -27 A9 8 0 0 1 9 -27 Z') + `<rect x="-11" y="-28.5" width="22" height="2.5" rx="1.2" fill="${K}" stroke="${K}" stroke-width="1.5"/>` },
  { n: 8, name: '肩に担ぐ', note: '剣を肩にのせ、刃が頭の後ろ', a: false,
    s: () => legs(1) + body() + ln(5, -17, 6, -14, 4) + sword(6, -14, -13, -38) + head() + dome(-27) },
  { n: 9, name: 'A字の上着', note: '裾が台座まで広がる', a: false,
    s: () => legs(0, 4, -6) + pth('M-4 -20 L4 -20 L11 -4 L-11 -4 Z') + ln(4, -17, 8, -11, 4) + sword(8, -11, 18, -33) + head() + pth('M-8 -28 Q0 -37 8 -28 Z') },
  { n: 10, name: '道具袋を背負う', note: '石工の袋と小づち', a: false,
    s: () => cir(-9, -15, 6) + ln(-11, -20, -15, -31, 2.5) + `<rect x="-19" y="-34" width="8" height="4" rx="1" fill="${K}" transform="rotate(-25 -15 -32)"/>` + legs(1) + body() + rarm() + sword(8, -11, 18, -33) + head() + dome(-27) },
  { n: 11, name: '長いスカーフ', note: '首の布が風になびく', a: true,
    s: () => pth('M-3 -20 Q-12 -23 -19 -17 L-18 -13 Q-11 -17 -3 -16 Z') + legs(1) + body() + rarm() + sword(8, -11, 18, -33) + head() + dome(-27) },
  { n: 12, name: '兜を押し上げる', note: '左手でずれた兜を上げる', a: false,
    s: () => legs(3) + body() + `<path d="M-5 -18 L-12 -24 L-9 -31" stroke="${K}" stroke-width="4" fill="none" stroke-linejoin="round" stroke-linecap="round"/>` + rarm() + sword(8, -11, 20, -34) + head(-25, 7.5) +
      `<g transform="rotate(-14 0 -28)">${pth('M-10.5 -28 A10.5 10 0 0 1 10.5 -28 Z')}<rect x="-12.5" y="-29.5" width="25" height="3" rx="1.5" fill="${K}"/></g>` },
  { n: 13, name: '後ろにためる', note: '剣を後ろへ引いて払う前', a: false,
    s: () => legs(4) + pth('M-7 -4 L-5 -19 L6 -19 L8 -4 Z') + ln(5, -16, 11, -12, 4) + ln(-5, -16, -8, -11, 4) + sword(-8, -11, -19, -31) + head() + dome(-27) },
  { n: 14, name: '大きな籠手', note: 'お下がりの大きな手袋', a: false,
    s: () => legs(2) + body() + ln(-5, -17, -9, -11, 4) + ln(5, -17, 9, -12, 4) + cir(-9, -11, 3.5) + sword(9, -12, 20, -34) + cir(9, -12, 3.5) + head() + dome(-27) },
  { n: 15, name: '大剣を背負う', note: '決めを変える：剣が槍より長く見える', a: false, rule: true,
    s: () => sword(-10, -6, 13, -42, 6.5) + legs(1) + body() + head() + dome(-27) },
  { n: 16, name: '剣を地に突く', note: '決めを変える：待つときの姿。剣が下向き', a: false, rule: true,
    s: () => ln(0, -13, 0, -1, 5) + ln(-3.5, -12, 3.5, -12, 3) + legs(3) + body() + ln(-5, -17, 0, -15, 4) + ln(5, -17, 0, -15, 4) + head() + dome(-27) },
  { n: 17, name: '卵形の胸当て', note: '丸い胴、細い手足', a: false,
    s: () => legs(2, 3.5, -7) + ell(0, -13, 8.5, 8) + ln(7, -14, 10, -11, 3) + sword(10, -11, 20, -33) + head(-28, 7.5) + dome(-29, 8.5) },
  { n: 18, name: '片方だけの肩当て', note: '大きすぎる肩当てが左に1枚', a: false,
    s: () => legs(2) + body() + pth('M-12 -15 Q-13 -23 -4 -21 L-4 -16 Z') + rarm() + sword(8, -11, 19, -33) + head(-27) + dome(-28) },
];
module.exports = { R, ped, K };

if (require.main === module) {
  const out = process.argv[2];
  const W = 1360;
  let s = '';
  const font = `font-family="IPAGothic, 'IPAゴシック', 'Hiragino Sans', sans-serif"`;
  s += `<rect width="${W}" height="1380" fill="#F4F2EC"/>`;
  s += `<text x="24" y="40" font-size="24" font-weight="700" fill="${K}">剣士 sword1 ラフ一覧（段階1・シルエット）</text>`;
  s += `<text x="24" y="66" font-size="14" fill="#444">game-art-concept 2026-11-27。上の段：ゲームの表示の大きさ（1倍＝論理px。高さ約44）を草地の上に。下の2段：同じ図形を4倍にしたもの。</text>`;
  s += `<text x="24" y="86" font-size="14" fill="#444">台座は決め（形を比べる対象ではない）なので薄い灰で描いた。赤い札＝ありがち（担当の感触）。紫の札＝決めを変える案。0 は いまの見本（比べる用）。</text>`;
  // 1x row
  const y1 = 110, cw = 69;
  s += `<rect x="16" y="${y1}" width="${W - 32}" height="110" rx="8" fill="#A9CB8C"/>`;
  s += `<text x="28" y="${y1 + 20}" font-size="13" font-weight="700" fill="${K}">1倍（実寸）</text>`;
  R.forEach((r, i) => {
    const cx = 50 + i * cw + 20, cy = y1 + 78;
    s += `<g transform="translate(${cx} ${cy})">${ped(true)}${r.s()}</g>`;
    s += `<text x="${cx}" y="${y1 + 102}" font-size="12" text-anchor="middle" fill="${K}" font-weight="700">${r.n}</text>`;
  });
  // 4x rows
  const rows = [R.slice(0, 7), R.slice(7, 14), R.slice(14)];
  rows.forEach((row, ri) => {
    const yy = 250 + ri * 370;
    row.forEach((r, i) => {
      const cx = 112 + i * 190, cy = yy + 250;
      s += `<rect x="${cx - 92}" y="${yy}" width="184" height="350" rx="8" fill="${r.ref ? '#E6E3DA' : '#FFFFFF'}" stroke="#CCC"/>`;
      s += `<g transform="translate(${cx} ${cy}) scale(4)">${ped(true)}${r.s()}</g>`;
      s += `<text x="${cx - 84}" y="${yy + 24}" font-size="20" font-weight="700" fill="${K}">${r.n}</text>`;
      s += `<text x="${cx - 58}" y="${yy + 22}" font-size="13" font-weight="700" fill="${K}">${r.name}</text>`;
      if (r.a) s += `<rect x="${cx - 84}" y="${yy + 34}" width="60" height="18" rx="4" fill="#D9413A"/><text x="${cx - 54}" y="${yy + 47}" font-size="12" fill="#FFF" text-anchor="middle" font-weight="700">ありがち</text>`;
      if (r.rule) s += `<rect x="${cx - 84}" y="${yy + 34}" width="86" height="18" rx="4" fill="#7A4FB0"/><text x="${cx - 41}" y="${yy + 47}" font-size="12" fill="#FFF" text-anchor="middle" font-weight="700">決めを変える</text>`;
      const words = r.note.match(/.{1,13}/g);
      words.forEach((w, k) => s += `<text x="${cx}" y="${yy + 300 + k * 16}" font-size="12" text-anchor="middle" fill="#333">${w}</text>`);
      // 44px の高さの目安線
      s += `<path d="M${cx - 88} ${cy - 44 * 4 + 24} H${cx + 88}" stroke="#4FA3FF" stroke-dasharray="4 4" stroke-width="1"/>`;
    });
  });
  s += `<text x="24" y="1370" font-size="12" fill="#666">青い点線＝台座の下の端から高さ44の線。</text>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="1380" viewBox="0 0 ${W} 1380" ${font}>\n<!-- 剣士 sword1 ラフ一覧。game-art-concept 2026-11-27。図形は円・楕円・四角・直線・2次曲線・円弧だけ（Canvas に移せる） -->\n${s}\n</svg>\n`;
  fs.writeFileSync(out, svg);
}
