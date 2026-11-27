// 剣士 sword1（決定の方向：A どんぶり兜 × A-1 王国の青）。監修_段階2.md の直しを入れた版。
// 原点＝台座の中心（配置の座標）。y は上がマイナス。単位＝論理px（ゲームの表示の大きさ）。
// 図形は円・楕円・角丸の四角・直線・2次曲線・円弧だけ（Canvas の arc / ellipse / quadraticCurveTo / roundRect で描ける）。
const K = '#1B2233'; // 味方の縁
// パレット（監修_段階2.md「パレットに足す色」のとおり）
const P = {
  outline: K,
  pedestal: '#FFFFFF', pedestalRim: '#2F6FD6',
  jacket: '#2F6FD6', jacketS: '#2459B0',
  skin: '#F3D2B3', skinS: '#E2B996',
  metal: '#E6E9EF', metalS: '#AEB6C8',
  gold: '#E8B730', goldS: '#B98E1C',
  pants: '#2B3A5C', pantsS: '#1F2A44',
  boot: '#6A4A34', belt: '#6A4A34', hair: '#5A3A26',
  patch: '#EFE4CC', // 大きな絵だけ
};
let uid = 0;
const two = (f, base, shade, lightEl) => {
  const id = 'sw' + (uid++);
  return `<clipPath id="${id}">${f('#000', 'none', 0)}</clipPath>${f(shade, 'none', 0)}<g clip-path="url(#${id})" fill="${base}">${lightEl}</g>${f('none', K, 2)}`;
};
const stroke2 = (d, col, w) => `<path d="${d}" stroke="${K}" stroke-width="${w + 2.5}" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="${d}" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`;
// 指摘1：台座の中の灰の楕円を消した。台座は白 #FFFFFF＋青いふち 2.5 だけ
const ped = () => `<ellipse cx="0" cy="0" rx="15" ry="6" fill="${P.pedestal}" stroke="${P.pedestalRim}" stroke-width="2.5"/>`;
function sword(x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L, px = -uy, py = ux;
  const g = [x1 + ux * 3, y1 + uy * 3], b0 = [g[0] + ux, g[1] + uy];
  return `<path d="M${x1 - ux * 2} ${y1 - uy * 2} L${g[0]} ${g[1]}" stroke="${K}" stroke-width="4.5" stroke-linecap="round"/>` +
    `<path d="M${b0[0]} ${b0[1]} L${x2} ${y2}" stroke="${K}" stroke-width="5.5" stroke-linecap="round"/>` +
    `<path d="M${b0[0]} ${b0[1]} L${x2} ${y2}" stroke="${P.metalS}" stroke-width="3" stroke-linecap="round"/>` +
    `<path d="M${b0[0] - px * 0.6} ${b0[1] - py * 0.6} L${x2 - px * 0.6} ${y2 - py * 0.6}" stroke="${P.metal}" stroke-width="1.4" stroke-linecap="round"/>` +
    stroke2(`M${g[0] - px * 4} ${g[1] - py * 4} L${g[0] + px * 4} ${g[1] + py * 4}`, P.gold, 2);
}
const swordAt = (hx, hy, deg, len = 26) => { const r = deg * Math.PI / 180; return sword(hx, hy, hx + Math.cos(r) * len, hy - Math.sin(r) * len); };
const fist = (x, y) => `<circle cx="${x}" cy="${y}" r="1.9" fill="${P.skin}" stroke="${K}" stroke-width="1.5"/>`;
// 指摘2：兜（鉢を深く A10.5 11、つばを中央が持ち上がる弧で両端を下げる、厚さ 3.8、縦の筋1本。傾き -8 は残す）
function helmet(angle = -8, big = false) {
  let h = `<g transform="rotate(${angle} 0 -28)">`;
  h += two((f, s, w) => `<path d="M-10.5 -28 A10.5 11 0 0 1 10.5 -28 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.metal, P.metalS, `<circle cx="-3" cy="-34" r="10"/>`);
  h += `<path d="M0.5 -38.2 Q1.5 -33 1.5 -28.5" stroke="${K}" stroke-width="1.3" fill="none" stroke-linecap="round"/>`;
  h += two((f, s, w) => `<path d="M-12.6 -28 Q0 -30.6 12.6 -28 L12.6 -24.2 Q0 -26.8 -12.6 -24.2 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.metal, P.metalS, `<rect x="-13" y="-31" width="17" height="3.4"/>`);
  if (big) for (const x of [-9.5, -4.8, 0, 4.8, 9.5]) { const y = -25.6 - 1.25 * (1 - (x / 12.6) ** 2) + 0.6; h += `<circle cx="${x}" cy="${y}" r="0.55" fill="${K}"/>`; }
  return h + '</g>';
}
// 顔と髪（指摘3：髪の房は右だけ1つ）
const face = (dy = 0) => `<circle cx="-2.6" cy="${-23.2 + dy}" r="1.25" fill="${K}"/><circle cx="2.6" cy="${-23.2 + dy}" r="1.25" fill="${K}"/><path d="M-1.2 ${-20.4 + dy} Q0 ${-19.5 + dy} 1.2 ${-20.4 + dy}" stroke="${K}" stroke-width="0.9" fill="none" stroke-linecap="round"/>`;
const head = () => two((f, s, w) => `<circle cx="0" cy="-25" r="7.5" fill="${f}" stroke="${s}" stroke-width="${w}"/>`, P.skin, P.skinS, `<circle cx="-2" cy="-27" r="7.5"/>`);
const hair = () => `<ellipse cx="6.9" cy="-22.8" rx="1.5" ry="2.1" fill="${P.hair}" stroke="${K}" stroke-width="1.2"/>`;

/* ポーズ（コマ）。
   pose: idle0 / idle1 / windup / hit / recover / spawnEnd(P2) / stack(P3) / stackHigh(P3 の別案)
   opt: { belt: 'brown'|'gold', big: 大きな絵の注記つき }  */
function parts(pose = 'idle0', opt = {}) {
  const belt = opt.belt === 'gold' ? P.gold : P.belt;
  const by = pose === 'idle1' ? 1 : 0;          // 胴から上の下がり（待つの2コマめ）
  const hy = pose === 'idle1' ? 0.5 : 0;        // 兜は遅れて半分だけ下がる
  const L = [];
  // 足と靴（がに股：残すもの）。足の付け根だけ胴といっしょに下がる
  L.push(['足・靴', stroke2(`M-3 ${-9 + by} L-7 -2.5`, P.pants, 3.5) + stroke2(`M3 ${-9 + by} L7 -2.5`, P.pants, 3.5) +
    `<ellipse cx="-7.6" cy="-2" rx="3.2" ry="2.1" fill="${P.boot}" stroke="${K}" stroke-width="1.6"/><ellipse cx="7.6" cy="-2" rx="3.2" ry="2.1" fill="${P.boot}" stroke="${K}" stroke-width="1.6"/>`, 0]);
  // 左腕（腰に手：残すもの。立つの最後のコマでは兜を押し上げる）
  let la;
  if (pose === 'spawnEnd') la = stroke2('M-5.5 -17 L-11.5 -23 L-9.5 -29', P.jacket, 3) + fist(-9.5, -29.5);
  else if (pose === 'hit') la = stroke2('M-5.5 -17 L-9.5 -13.5', P.jacket, 3);
  else la = stroke2('M-5.5 -17 L-10.5 -12.5 L-6.5 -9.5', P.jacket, 3);
  L.push(['左腕', la, by]);
  let b = two((f, s, w) => `<path d="M-7 -6 L-6.5 -19 L6.5 -19 L7 -6 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.jacket, P.jacketS, `<rect x="-9" y="-21" width="11" height="16"/>`);
  b += `<path d="M-6.8 -9.5 H6.8" stroke="${belt}" stroke-width="2"/>`;
  if (opt.big) { // 大きな絵だけ：当て布・腰の道具袋（ノミの柄）
    b += `<rect x="-5.2" y="-16.6" width="3" height="3" fill="${P.patch}" stroke="${K}" stroke-width="0.6" stroke-dasharray="0.8 0.5"/>`;
    b += `<path d="M-7.6 -10.3 L-8.6 -13.4" stroke="#8C7A66" stroke-width="1" stroke-linecap="round"/><rect x="-9.6" y="-10.2" width="3.6" height="4.4" rx="1.2" fill="${P.patch}" stroke="${K}" stroke-width="0.8"/>`;
  }
  L.push(['胴・帯', b, by]);
  const S = {
    idle0: [[5, -17], [8, -12.5], 60], idle1: [[5, -17], [8, -12.5], 60], recover: [[5, -17], [8.5, -12.5], 50],
    windup: [[5, -17], [10, -15], 25], hit: [[5, -17], [-3, -12], 172], spawnEnd: [[5, -17], [8, -12.5], 60],
    stack: [[5, -17], [8.5, -18], 67],        // P3：剣の先 高さ48 まで（監修の仮置き）
    stackHigh: [[5, -17], [9, -21], 74],     // P3 の別案：剣の先 高さ52（槍の先 58 より低い）
  }[pose];
  const [sh, hd, deg] = S;
  const arm = stroke2(`M${sh[0]} ${sh[1]} L${hd[0]} ${hd[1]}`, P.jacket, 3);
  let sw = swordAt(hd[0], hd[1], deg);
  if (pose === 'hit') { const r = deg * Math.PI / 180; const tx = hd[0] + Math.cos(r) * 26, ty = hd[1] - Math.sin(r) * 26; sw += `<path d="M${tx - 3.5} ${ty} L${tx + 3.5} ${ty} M${tx} ${ty - 3.5} L${tx} ${ty + 3.5} M${tx - 2.4} ${ty - 2.4} L${tx + 2.4} ${ty + 2.4} M${tx - 2.4} ${ty + 2.4} L${tx + 2.4} ${ty - 2.4}" stroke="#FFFFFF" stroke-width="1.4" stroke-linecap="round"/>`; }
  L.push(['右腕・剣', pose === 'hit' ? sw + fist(hd[0], hd[1]) + arm : arm + sw + fist(hd[0], hd[1]), by]);
  L.push(['頭・髪・顔', head() + hair() + face(), by]);
  L.push(['兜', helmet(pose === 'spawnEnd' ? -14 : -8, opt.big), by + hy]);
  return L;
}
function draw(pose = 'idle0', opt = {}) {
  return parts(pose, opt).map(([n, svg, dy]) => dy ? `<g transform="translate(0 ${dy})">${svg}</g>` : svg).join('');
}
// 横（右向き）。設定画用
function side(opt = {}) {
  let o = '';
  o += stroke2('M-1 -9 L-4 -2.5', P.pantsS, 3.5) + `<ellipse cx="-3.4" cy="-2" rx="3.2" ry="2.1" fill="${P.boot}" stroke="${K}" stroke-width="1.6"/>`;
  o += stroke2('M1 -9 L4.5 -2.5', P.pants, 3.5) + `<ellipse cx="5.6" cy="-2" rx="3.4" ry="2.1" fill="${P.boot}" stroke="${K}" stroke-width="1.6"/>`;
  o += stroke2('M-2 -17 L-6 -12 L-3 -9.5', P.jacketS, 3); // 奥の腕：腰に手（ひじが後ろへ）
  o += two((f, s, w) => `<path d="M-4.5 -6 L-4 -19 L4 -19 L5 -6 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.jacket, P.jacketS, `<rect x="-6" y="-21" width="6" height="16"/>`);
  o += `<path d="M-4.4 -9.5 H4.8" stroke="${opt.belt === 'gold' ? P.gold : P.belt}" stroke-width="2"/>`;
  o += swordAt(6, -12.5, 60) + stroke2('M1.5 -17 L6 -12.5', P.jacket, 3) + fist(6, -12.5);
  o += two((f, s, w) => `<circle cx="0" cy="-25" r="7.5" fill="${f}" stroke="${s}" stroke-width="${w}"/>`, P.skin, P.skinS, `<circle cx="1" cy="-27" r="7.5"/>`);
  o += `<path d="M-7.2 -26 Q-8.6 -21 -5 -19.6 Q-3.2 -21.5 -3.6 -25 Z" fill="${P.hair}" stroke="${K}" stroke-width="1.2" stroke-linejoin="round"/>`; // 後ろ髪（兜からはみ出た短い髪）
  o += `<circle cx="4.4" cy="-23.4" r="1.2" fill="${K}"/><path d="M7.1 -23.2 Q8.7 -22.2 7.3 -21.3" stroke="${K}" stroke-width="1" fill="${P.skin}" stroke-linecap="round"/><path d="M4.8 -20.2 L6.4 -20.4" stroke="${K}" stroke-width="0.9" stroke-linecap="round"/>`;
  // 兜：横から。前にやや傾く（つばが目の上）。つばの弧は前後で同じ
  o += `<g transform="rotate(6 0 -28)">` + two((f, s, w) => `<path d="M-10.5 -28 A10.5 11 0 0 1 10.5 -28 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.metal, P.metalS, `<circle cx="-3" cy="-34" r="10"/>`) +
    two((f, s, w) => `<path d="M-12.6 -28 Q0 -30.6 12.6 -28 L12.6 -24.2 Q0 -26.8 -12.6 -24.2 Z" fill="${f}" stroke="${s}" stroke-width="${w}" stroke-linejoin="round"/>`, P.metal, P.metalS, `<rect x="-13" y="-31" width="17" height="3.4"/>`) + `</g>`;
  return o;
}
module.exports = { P, K, ped, draw, parts, side, helmet, stroke2, two };
