// 剣士 sword1 色の案（段階3）。原点＝台座の中心。単位＝論理px
const fs = require('fs');
const K = '#1B2233';
let uid = 0;
const C0 = { skin: '#F3D2B3', skinS: '#E2B996', blue: '#2F6FD6', blueS: '#2459B0', metal: '#E6E9EF', metalS: '#AEB6C4',
  gold: '#E8B730', goldS: '#B98E1C', ped: '#FFFFFF', pedR: '#2F6FD6' };
// 案ごとの色の組（新しく足す色は 絞り込み.md の表に載せる）
const S = {
  s1: { label: '1 王国の青', pants: '#2B3A5C', pantsS: '#1F2A44', boot: '#6A4A34', hair: '#5A3A26', belt: '#E8B730', brim: 'metal', patch: '#EFE4CC', sleeve: null, glove: '#8C6A48', gloveS: '#6A4E34', jacket: 'blue' },
  s2: { label: '2 生成りのそで', pants: '#B89466', pantsS: '#977650', boot: '#5A3E2C', hair: '#3E2A1E', belt: '#6A4A34', brim: 'metal', patch: '#D8C39C', sleeve: '#EFE4CC', sleeveS: '#D6C7A8', glove: '#EFE4CC', gloveS: '#D6C7A8', jacket: 'blue' },
  s3: { label: '3 金のつば', pants: '#EFE4CC', pantsS: '#D6C7A8', boot: '#2B3A5C', hair: '#6B4A2E', belt: '#2B3A5C', brim: 'gold', patch: '#B89466', sleeve: null, glove: '#2B3A5C', gloveS: '#1F2A44', jacket: 'blue' },
  s4: { label: '4 真鍮の兜（決め変え）', pants: '#2B3A5C', pantsS: '#1F2A44', boot: '#6A4A34', hair: '#5A3A26', belt: '#6A4A34', brim: 'brass', patch: '#EFE4CC', sleeve: null, glove: '#8C6A48', gloveS: '#6A4E34', jacket: 'blue', brass: '#D4A94A', brassS: '#A9822E' },
};
// 2段の面：shape(fill, stroke, sw) を返す関数 f。light は左上から当たる明るい部分の要素
function two(f, base, shade, lightEl) {
  const id = 'c' + (uid++);
  return `<clipPath id="${id}">${f('#000', 'none', 0)}</clipPath>${f(shade, 'none', 0)}<g clip-path="url(#${id})" fill="${base}">${lightEl}</g>${f('none', K, 2)}`;
}
const stroke2 = (d, col, w) => `<path d="${d}" stroke="${K}" stroke-width="${w + 2.5}" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="${d}" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`;
const ped = () => `<ellipse cx="0" cy="0" rx="15" ry="6" fill="#FFFFFF" stroke="#2F6FD6" stroke-width="2.5"/><ellipse cx="0" cy="1.2" rx="11" ry="3.2" fill="#E4E9F2"/>`;
function sword(x1, y1, x2, y2, c) {
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L, px = -uy, py = ux;
  const g = [x1 + ux * 3, y1 + uy * 3];
  const b0 = [g[0] + ux * 1, g[1] + uy * 1];
  return `<path d="M${x1 - ux * 2} ${y1 - uy * 2} L${g[0]} ${g[1]}" stroke="${K}" stroke-width="4.5" stroke-linecap="round"/>` +
    `<path d="M${b0[0]} ${b0[1]} L${x2} ${y2}" stroke="${K}" stroke-width="5.5" stroke-linecap="round"/>` +
    `<path d="M${b0[0]} ${b0[1]} L${x2} ${y2}" stroke="${C0.metalS}" stroke-width="3" stroke-linecap="round"/>` +
    `<path d="M${b0[0] + px * -0.6} ${b0[1] + py * -0.6} L${x2 + px * -0.6} ${y2 + py * -0.6}" stroke="${C0.metal}" stroke-width="1.4" stroke-linecap="round"/>` +
    stroke2(`M${g[0] - px * 4} ${g[1] - py * 4} L${g[0] + px * 4} ${g[1] + py * 4}`, C0.gold, 2);
}
const eyes = (y, dx = 2.6) => `<circle cx="${-dx}" cy="${y}" r="1.25" fill="${K}"/><circle cx="${dx}" cy="${y}" r="1.25" fill="${K}"/><path d="M-1.2 ${y + 3} Q0 ${y + 3.9} 1.2 ${y + 3}" stroke="${K}" stroke-width="0.9" fill="none" stroke-linecap="round"/>`;
const headC = (cx, cy, r) => two((f, s, w) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${f}" stroke="${s}" stroke-width="${w}"/>`, C0.skin, C0.skinS, `<circle cx="${cx - 2}" cy="${cy - 2}" r="${r}"/>`);
function helmetCols(s) {
  if (s.brim === 'brass') return [s.brass, s.brassS, s.brass, s.brassS];
  if (s.brim === 'gold') return [C0.metal, C0.metalS, C0.gold, C0.goldS];
  return [C0.metal, C0.metalS, C0.metal, C0.metalS];
}
const leg = (x1, y1, x2, y2, s, w) => stroke2(`M${x1} ${y1} L${x2} ${y2}`, s.pants, w);
const boot = (x, y, s, rx = 3.2) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="2.1" fill="${s.boot}" stroke="${K}" stroke-width="1.6"/>`;
const arm = (d, s, w = 3) => stroke2(d, s.sleeve || C0.blue, w);
const fist = (x, y, col, r = 1.9) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${col}" stroke="${K}" stroke-width="1.5"/>`;
const hairTuft = (s, pts) => pts.map(([x, y, rx, ry]) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${s.hair}" stroke="${K}" stroke-width="1.4"/>`).join('');

const D = {
  A: { name: 'A どんぶり兜（ラフ2）', draw: (s) => {
    const [hm, hmS, br, brS] = helmetCols(s);
    let o = '';
    o += leg(-3, -9, -7, -2.5, s, 3.5) + leg(3, -9, 7, -2.5, s, 3.5) + boot(-7.6, -2, s) + boot(7.6, -2, s);
    o += arm('M-5.5 -17 L-10.5 -12.5 L-6.5 -9.5', s);
    o += two((f, st, w) => `<path d="M-7 -6 L-6.5 -19 L6.5 -19 L7 -6 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, C0.blue, C0.blueS, `<rect x="-9" y="-21" width="11" height="16"/>`);
    o += `<path d="M-6.8 -9.5 H6.8" stroke="${s.belt}" stroke-width="2"/><rect x="-5.2" y="-16.6" width="3" height="3" fill="${s.patch}" stroke="${K}" stroke-width="0.8"/>`;
    o += arm('M5 -17 L8 -12.5', s) + sword(8, -12, 21, -35, s) + fist(8, -12, C0.skin);
    o += headC(0, -25, 7.5) + hairTuft(s, [[-6.4, -23.5, 2, 3], [6.6, -23, 1.8, 2.6]]) + eyes(-24.2);
    o += `<g transform="rotate(-8 0 -28)">` + two((f, st, w) => `<path d="M-10.5 -28 A10.5 10 0 0 1 10.5 -28 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, hm, hmS, `<circle cx="-3" cy="-33" r="10"/>`) +
      two((f, st, w) => `<rect x="-12.5" y="-29.5" width="25" height="3.2" rx="1.6" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, br, brS, `<rect x="-13" y="-30" width="18" height="2"/>`) + `</g>`;
    return o; } },
  B: { name: 'B ずんぐり＋大きな籠手（ラフ7＋14）', draw: (s) => {
    const [hm, hmS, br, brS] = helmetCols(s);
    let o = '';
    o += leg(-4, -8, -9, -2.5, s, 4.5) + leg(4, -8, 9, -2.5, s, 4.5) + boot(-9.5, -2, s, 3.6) + boot(9.5, -2, s, 3.6);
    o += arm('M-8 -16 L-11.5 -11.5', s, 3.4);
    o += two((f, st, w) => `<rect x="-10" y="-20" width="20" height="14" rx="5" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, C0.blue, C0.blueS, `<rect x="-11" y="-21" width="15" height="16"/>`);
    o += `<path d="M-9.6 -10 H9.6" stroke="${s.belt}" stroke-width="2"/><rect x="-7" y="-17.5" width="3" height="3" fill="${s.patch}" stroke="${K}" stroke-width="0.8"/>`;
    o += two((f, st, w) => `<circle cx="-11.5" cy="-11" r="3.6" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, s.glove, s.gloveS, `<circle cx="-12.5" cy="-12" r="3.4"/>`);
    o += arm('M8 -16 L11 -12.5', s, 3.4) + sword(11, -12, 22, -30, s);
    o += two((f, st, w) => `<circle cx="11" cy="-12" r="3.6" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, s.glove, s.gloveS, `<circle cx="10" cy="-13" r="3.4"/>`);
    o += headC(0, -27, 8) + hairTuft(s, [[-7, -25, 1.8, 2.6], [7, -25, 1.8, 2.6]]) + eyes(-25.5);
    o += two((f, st, w) => `<path d="M-9 -27 A9 8 0 0 1 9 -27 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, hm, hmS, `<circle cx="-3" cy="-32" r="8.5"/>`);
    o += two((f, st, w) => `<rect x="-11" y="-28.6" width="22" height="2.8" rx="1.4" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, br, brS, `<rect x="-12" y="-29" width="16" height="1.8"/>`);
    return o; } },
  C: { name: 'C 後ろにためる＋肩当て（ラフ13＋18）', draw: (s) => {
    const [hm, hmS, br, brS] = helmetCols(s);
    let o = '';
    o += leg(-3, -9, -7, -2.5, s, 3.5) + leg(3, -9, 7, -2.5, s, 3.5) + boot(-7.6, -2, s) + boot(7.6, -2, s);
    o += arm('M-5 -16 L-8 -11.5', s) + sword(-8, -11, -19, -31, s) + fist(-8, -11, C0.skin);
    o += two((f, st, w) => `<path d="M-7 -4.5 L-5 -19 L6 -19 L8 -4.5 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, C0.blue, C0.blueS, `<rect x="-9" y="-21" width="11" height="18"/>`);
    o += `<path d="M-6.4 -8.5 H7.4" stroke="${s.belt}" stroke-width="2"/><rect x="-4.6" y="-15.6" width="3" height="3" fill="${s.patch}" stroke="${K}" stroke-width="0.8"/>`;
    o += arm('M5 -16 L11 -12.5', s) + fist(11, -12.5, C0.skin);
    o += two((f, st, w) => `<path d="M3 -21 Q13 -23 12.5 -14 L5 -15 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, s.brim === 'brass' ? s.brass : C0.metal, s.brim === 'brass' ? s.brassS : C0.metalS, `<circle cx="5" cy="-23" r="7"/>`);
    o += headC(0, -26, 8) + hairTuft(s, [[-7, -24, 1.8, 2.6], [7, -24, 1.8, 2.6]]) + eyes(-24.6);
    o += two((f, st, w) => `<path d="M-9 -26.5 A9 9 0 0 1 9 -26.5 Z" fill="${f}" stroke="${st}" stroke-width="${w}" stroke-linejoin="round"/>`, hm, hmS, `<circle cx="-3" cy="-32" r="9"/>`);
    o += two((f, st, w) => `<rect x="-10" y="-27.8" width="20" height="2.6" rx="1.3" fill="${f}" stroke="${st}" stroke-width="${w}"/>`, br, brS, `<rect x="-11" y="-28.5" width="14" height="1.8"/>`);
    return o; } },
};
module.exports = { D, S, ped, C0 };

if (require.main === module) {
  const out = process.argv[2];
  const bfPath = process.argv[3];
  const bf = fs.readFileSync(bfPath, 'utf8');
  const inner = bf.replace(/^[\s\S]*?<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
  const W = 1530;
  let s = '';
  const sets = { A: ['s1', 's2', 's3', 's4'], B: ['s1', 's2', 's3'], C: ['s1', 's2', 's3'] };
  const cellW = 170, cellH = 230, sc = 4;
  let y = 100;
  s += `<text x="24" y="40" font-size="24" font-weight="700" fill="${K}">剣士 sword1 色の案（段階3）：3案 × 色3つ以上、左＝色、右＝白黒</text>`;
  s += `<text x="24" y="66" font-size="14" fill="#444">game-art-concept 2026-11-27。各マスの上＝4倍、下の小窓＝1倍（実寸）を草地と道の上に。白黒は彩度0（スタイル見本の白黒と同じ）。</text>`;
  s += `<text x="24" y="86" font-size="14" fill="#444">上着の青 #2F6FD6・台座・縁 #1B2233・金属・金・肌は決めのまま。ズボン・靴・髪・当て布・籠手の色は新しく足す提案（絞り込み.md の表）。</text>`;
  const gs = `<filter id="gs"><feColorMatrix type="saturate" values="0"/></filter>`;
  s += `<defs>${gs}</defs>`;
  for (const k of ['A', 'B', 'C']) {
    s += `<text x="24" y="${y + 22}" font-size="18" font-weight="700" fill="${K}">${D[k].name}</text>`;
    const yy = y + 34;
    sets[k].forEach((sk, i) => {
      for (const g of [0, 1]) {
        const x = 24 + i * (cellW + 8) + g * 760;
        s += `<g ${g ? 'filter="url(#gs)"' : ''}>`;
        s += `<rect x="${x}" y="${yy}" width="${cellW}" height="${cellH}" rx="8" fill="#FFFFFF" stroke="#CCC"/>`;
        s += `<g transform="translate(${x + cellW / 2 - 12} ${yy + 172}) scale(${sc})">${ped()}${D[k].draw(S[sk])}</g>`;
        // 1倍の小窓（草地・道）
        s += `<rect x="${x + 8}" y="${yy + 180}" width="74" height="44" fill="#A9CB8C"/><rect x="${x + 88}" y="${yy + 180}" width="74" height="44" fill="#DCCBA4"/>`;
        s += `<g transform="translate(${x + 45} ${yy + 216})">${ped()}${D[k].draw(S[sk])}</g>`;
        s += `<g transform="translate(${x + 125} ${yy + 216})">${ped()}${D[k].draw(S[sk])}</g>`;
        s += `</g>`;
        s += `<text x="${x + 8}" y="${yy + 18}" font-size="13" font-weight="700" fill="${K}">${S[sk].label}${g ? '（白黒）' : ''}</text>`;
      }
    });
    y = yy + cellH + 16;
  }
  // 戦場の見本の上に置く（左が新しい案、右下がいまの英雄）
  s += `<text x="24" y="${y + 22}" font-size="18" font-weight="700" fill="${K}">スタイル見本の戦場に置いたもの（色の案1、塔の左の道の下。右の小さい英雄＝いまの見本）。左＝2倍に拡大、右＝白黒の1倍</text>`;
  const yy = y + 34;
  ['A', 'B', 'C'].forEach((k, i) => {
    const x = 24 + i * 490;
    const vb = '110 330 200 170';
    const hero = `<g transform="translate(150 480)">${ped()}${D[k].draw(S.s1)}</g>`;
    s += `<svg x="${x}" y="${yy}" width="400" height="340" viewBox="${vb}" >${inner.replace(/id="/g, `id="${k}_`).replace(/url\(#/g, `url(#${k}_`)}${hero}</svg>`;
    s += `<g filter="url(#gs)"><svg x="${x + 404}" y="${yy}" width="60" height="60" viewBox="120 432 60 60">${inner.replace(/id="/g, `id="g${k}_`).replace(/url\(#/g, `url(#g${k}_`)}${hero}</svg></g>`;
    s += `<svg x="${x + 404}" y="${yy + 66}" width="60" height="60" viewBox="120 432 60 60">${inner.replace(/id="/g, `id="h${k}_`).replace(/url\(#/g, `url(#h${k}_`)}${hero}</svg>`;
    s += `<text x="${x + 404}" y="${yy + 142}" font-size="12" fill="#444">上：白黒1倍</text><text x="${x + 404}" y="${yy + 158}" font-size="12" fill="#444">下：色1倍</text>`;
    s += `<text x="${x}" y="${yy + 360}" font-size="15" font-weight="700" fill="${K}">${k}</text>`;
  });
  const H = yy + 380;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="IPAGothic, 'IPAゴシック', 'Hiragino Sans', sans-serif">\n<!-- 剣士 sword1 色の案。game-art-concept 2026-11-27。下の戦場は 02_プリプロ/スタイル見本/戦場_色.svg の中身をそのまま入れたもの -->\n<rect width="${W}" height="${H}" fill="#F4F2EC"/>\n${s}\n</svg>\n`;
  fs.writeFileSync(out, svg);
}
