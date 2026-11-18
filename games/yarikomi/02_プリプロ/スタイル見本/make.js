// スタイル見本の生成スクリプト（game-art-concept, 2026-11-18）
// 使い方: node make.js            … HTML（自己完結・外部CDN/フォントなし）を書き出す
//         node make.js --png      … HTML に加えて PNG（カラー・グレースケール）も書き出す（playwright）
// 色コード・数値は 02_プリプロ/アートディレクション.md の 3.1／3.3／4.2／4.3／5 から。
// ガイドに無い値は「仮」として THEME の中にコメントで書いた。

const fs = require('fs');
const path = require('path');
const OUT = __dirname;

// ---------------------------------------------------------------- 色
const THEME = {
  A: {
    id: 'A', name: 'A 帳面の谷',
    bg: '#F2EADB', panel: '#E3D7C1', grid: '#CBBEA6', ink: '#2B2622', bgline: '#8C8378',
    lord: '#2F4E8C', lordLight: '#C9D6EA', enemyFill: '#2B2622', enemyEdge: null, enemyMark: '#6A3F6E',
    danger: '#B8321A', rule: '#3F7F6E', water: '#5FA3B0', ancestor: '#8A6A45',
    select: '#D9A441', selectBorder: '#2B2622', button: '#FBF7EF', eyes: '#F2EADB',
    shadow: '#2B2622', shadowOpacity: 0.18,
    destFill: '#C9D6EA',
    mode: 'fill',
  },
  B: {
    id: 'B', name: 'B 青焼きの工房',
    bg: '#1E3A5C', panel: '#284A70', grid: '#3E6388', ink: '#EAF0F2', bgline: '#7F9BB3',
    lord: '#F2B544',
    lordLight: '#EAF0F2',        // 仮：B に当主の明るい面の指定なし。主線色で代用
    enemyFill: '#0E1A28', enemyEdge: '#EAF0F2',
    enemyMark: '#EAF0F2',        // 仮：B に敵の差し色の指定なし。主線色＋形（破線の爪あと）で分ける
    danger: '#FF6B4A', rule: '#6FC2A8',
    water: '#5FA3B0',            // 仮：B に水の指定なし。A の浅葱をそのまま
    ancestor: '#C9A86A',
    select: '#3E6388',           // 仮：B に選択の下塗りの指定なし。黄土は当主の山吹とぶつかるのでマス目色で代用
    selectBorder: '#EAF0F2',
    button: '#284A70',           // 仮：B にボタンの地の指定なし。パネル色で代用
    eyes: '#EAF0F2',
    shadow: '#0E1A28', shadowOpacity: 0.35, // 仮：墨 18% は藍の地で見えないので、敵の色 35% に
    destFill: '#284A70',         // 仮：当主の行き先のマスの下塗り
    mode: 'blueprint',
  },
};
const MAT = {
  wood: ['#B98A55', '#9C7246'], rope: ['#C9B48A', '#AD9A74'], brass: ['#B8923A', '#987830'],
  stone: ['#7D7F80', '#66686A'], iron: ['#5E6670', '#4C535B'], flint: ['#4A4440', '#3A3532'],
};
const SKIN = '#F3D9BF', HAIR = '#4A3426';

// ---------------------------------------------------------------- 道具
function rng(seed) { let s = (seed * 2654435761) >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return (s % 100000) / 100000; }; }
const f = (n) => Math.round(n * 100) / 100;
// 点の列をわずかに揺らして path にする（揺らぎは種で決まる。毎回同じ）
function wob(pts, r, amp = 0.5, closed = true) {
  const p = pts.map(([x, y]) => [x + (r() * 2 - 1) * amp, y + (r() * 2 - 1) * amp]);
  return 'M' + p.map(([x, y]) => f(x) + ' ' + f(y)).join(' L') + (closed ? ' Z' : '');
}
function circ(cx, cy, rad, n = 20) { const a = []; for (let i = 0; i < n; i++) { const t = (i / n) * Math.PI * 2; a.push([cx + Math.cos(t) * rad, cy + Math.sin(t) * rad]); } return a; }
// 主線の太さ：基準 × (1 ± 15%)。物ごとに種で決める
const lw = (r, base) => f(base * (1 + (r() * 2 - 1) * 0.15));
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function rgbToHex([r, g, b]) { return '#' + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join(''); }
function desat(h, amt) { // 彩度を amt（0〜1）だけ落とす（輝度は保つ）
  const [r, g, b] = hexToRgb(h); const L = 0.299 * r + 0.587 * g + 0.114 * b;
  return rgbToHex([r + (L - r) * amt, g + (L - g) * amt, b + (L - b) * amt]);
}
const darken = (h, a = 0.12) => rgbToHex(hexToRgb(h).map((v) => v * (1 - a)));

// ---------------------------------------------------------------- 部品（48 の枠、中身は 4〜44）
// size: 表示の大きさ（px）。48 → 主線 2px、24 → 1.5px で内線なし、56 → 2px・つなぎ点 6px
function partFrame(size) {
  const s = size / 48; const small = size <= 24;
  return { s, small, line: (small ? 1.5 : 2) / s, inner: 1 / s, joint: (size >= 56 ? 6 : 4) / 2 / s };
}
function matColors(T, mat, age) {
  const sat = [0, 0.25, 0.5][age || 0];
  return [desat(MAT[mat][0], sat), desat(MAT[mat][1], sat)];
}
function cracks(T, fr, n, r) {
  let o = '';
  const sets = [[[14, 8], [19, 16], [16, 22], [22, 30]], [[34, 26], [30, 32], [34, 38], [29, 43]]];
  for (let i = 0; i < n; i++) o += `<path d="${wob(sets[i], r, 0.4, false)}" fill="none" stroke="${T.ink}" stroke-width="${f(1.2 / fr.s)}" stroke-linecap="round"/>`;
  return o;
}
function joints(T, fr, list) {
  return list.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="${f(fr.joint)}" fill="${T.ink}"/>`).join('');
}

function partSpring(T, size, opt = {}) {
  const fr = partFrame(size); const r = rng(11 + (opt.seed || 0)); const L = lw(r, fr.line);
  const [c, sh] = matColors(T, 'brass', opt.age);
  const bp = T.mode === 'blueprint';
  const plateFill = c, plate2 = bp ? c : sh;
  let o = '';
  // コイル：墨の太い線の上に真鍮の細い線 → 縁取りされた針金
  const zz = [[11, 24]]; for (let i = 0; i < 6; i++) zz.push([14 + i * 4 + 2, i % 2 ? 33 : 15]); zz.push([37, 24]);
  const zd = wob(zz, r, 0.3, false);
  o += `<path d="${zd}" fill="none" stroke="${T.ink}" stroke-width="${f(L + 3.2 / fr.s)}" stroke-linejoin="round" stroke-linecap="round"/>`;
  o += `<path d="${zd}" fill="none" stroke="${bp ? T.bg : c}" stroke-width="${f(3.2 / fr.s)}" stroke-linejoin="round" stroke-linecap="round"/>`;
  // 左右の板
  o += `<path d="${wob([[5, 9], [11, 9], [11, 39], [5, 39]], r, 0.3)}" fill="${plateFill}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  o += `<path d="${wob([[37, 9], [43, 9], [43, 39], [37, 39]], r, 0.3)}" fill="${plate2}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  if (!fr.small && !bp) o += `<path d="M7.5 12 L7.5 22" stroke="${T.bg}" stroke-width="${f(fr.inner)}" stroke-linecap="round"/>`; // 真鍮の照り1本
  if (!fr.small) o += cracks(T, fr, opt.age || 0, r);
  o += joints(T, fr, opt.joints || [[4, 24], [44, 24]]);
  return o;
}
function partGear(T, size, opt = {}) {
  const fr = partFrame(size); const r = rng(23 + (opt.seed || 0)); const L = lw(r, fr.line);
  const [c, sh] = matColors(T, 'brass', opt.age);
  const bp = T.mode === 'blueprint';
  const pts = []; const N = 8;
  for (let i = 0; i < N; i++) {
    const a0 = (i / N) * Math.PI * 2; const d = (Math.PI * 2) / N;
    [[a0 - d * 0.18, 18], [a0 - d * 0.12, 18.5], [a0 + d * 0.12, 18.5], [a0 + d * 0.18, 18], [a0 + d * 0.32, 13.5], [a0 + d * 0.68, 13.5]]
      .forEach(([a, rr]) => pts.push([24 + Math.cos(a) * rr, 24 + Math.sin(a) * rr]));
  }
  let o = `<path d="${wob(pts, r, 0.25)}" fill="${bp ? T.bg : c}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  // 影色：軸のまわりの輪（右下に光が当たらない面）
  o += `<path d="${wob(circ(24, 24, 7.5, 16), r, 0.2)}" fill="${bp ? c : sh}" stroke="${T.ink}" stroke-width="${f(L * 0.8)}"/>`;
  o += `<circle cx="24" cy="24" r="${f(2.6)}" fill="${T.bg}" stroke="${T.ink}" stroke-width="${f(L * 0.7)}"/>`;
  if (!fr.small && !bp) o += `<path d="M14.5 17 A11 11 0 0 1 19 12.6" fill="none" stroke="${T.bg}" stroke-width="${f(fr.inner)}" stroke-linecap="round"/>`; // 照り1本
  if (!fr.small) o += cracks(T, fr, opt.age || 0, r);
  if (opt.weight) o += weightDots(T, fr, opt.weight);
  o += joints(T, fr, opt.joints || [[4, 24], [24, 4], [44, 24], [24, 44]]);
  return o;
}
function partArm(T, size, opt = {}) {
  const fr = partFrame(size); const r = rng(37 + (opt.seed || 0)); const L = lw(r, fr.line);
  const [c, sh] = matColors(T, 'wood', opt.age);
  const bp = T.mode === 'blueprint';
  let o = '';
  // 腕：軸（下の中）から左上へのびる板。先に受け皿（上が開いた椀）
  const P0 = [24, 40], P1 = [13, 17]; const dx = P1[0] - P0[0], dy = P1[1] - P0[1]; const len = Math.hypot(dx, dy);
  const nx = -dy / len * 4.2, ny = dx / len * 4.2;
  const ax = [[P0[0] + nx, P0[1] + ny], [P0[0] - nx, P0[1] - ny], [P1[0] - nx, P1[1] - ny], [P1[0] + nx, P1[1] + ny]];
  o += `<path d="${wob(ax, r, 0.3)}" fill="${bp ? T.bg : c}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  const cup = [[3.5, 9]]; for (let i = 0; i <= 8; i++) { const t = Math.PI * (i / 8); cup.push([11 - Math.cos(t) * 8, 9 + Math.sin(t) * 8]); } cup.push([18.5, 9], [16, 9]);
  for (let i = 8; i >= 0; i--) { const t = Math.PI * (i / 8); cup.push([11 - Math.cos(t) * 5, 9 + Math.sin(t) * 5]); } cup.push([6, 9]);
  o += `<path d="${wob(cup, r, 0.15)}" fill="${bp ? c : sh}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  // 軸の止め
  o += `<circle cx="24" cy="40" r="2.6" fill="${bp ? c : sh}" stroke="${T.ink}" stroke-width="${f(L * 0.8)}"/>`;
  if (!fr.small && !bp) o += `<path d="M23 34 L16 19.5" stroke="${sh}" stroke-width="${f(fr.inner)}" stroke-linecap="round"/>`; // 木目1本
  if (!fr.small && bp) o += `<path d="M23 34 L16 19.5" stroke="${T.bgline}" stroke-width="${f(fr.inner)}" stroke-linecap="round"/>`;
  if (!fr.small) o += cracks(T, fr, opt.age || 0, r);
  if (opt.wet) o += wetBadge(T, fr);
  o += joints(T, fr, opt.joints || [[24, 44]]);
  return o;
}
// 小印 12px（部品の右下・右上）
function weightDots(T, fr, n) { // 右下：黒丸 1〜3
  let o = ''; for (let i = 0; i < n; i++) o += `<circle cx="${f(43 - i * 4.2)}" cy="43" r="1.7" fill="${T.ink}"/>`; return o;
}
function wetBadge(T, fr) { // 右上：波線
  return `<g transform="translate(34 2)"><path d="M1 4 q2.5 -2.5 5 0 t5 0 M1 8.5 q2.5 -2.5 5 0 t5 0" fill="none" stroke="${T.water}" stroke-width="1.6" stroke-linecap="round"/></g>`;
}
const PARTS = { spring: partSpring, gear: partGear, arm: partArm };
function part(T, kind, x, y, size, opt = {}) {
  return `<g transform="translate(${x} ${y}) scale(${f(size / 48)})">${PARTS[kind](T, size, opt)}</g>`;
}

// ---------------------------------------------------------------- 当主・敵・墓（48 のマス、物は 40×44）
function lord(T, x, y) {
  const r = rng(101); const L = lw(r, 2);
  const bodyC = T.lord, light = T.lordLight;
  let o = `<g transform="translate(${x} ${y})">`;
  // 脚（足はマスの下 4px＝ y44）
  o += `<path d="${wob([[17, 36], [22, 36], [22, 44], [16, 44]], r, 0.2)}" fill="${T.mode === 'blueprint' ? T.bg : T.ink}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  o += `<path d="${wob([[25, 36], [30, 36], [32, 44], [26, 44]], r, 0.2)}" fill="${T.mode === 'blueprint' ? T.bg : T.ink}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  // 胴（丸みのある縦長）
  o += `<path d="${wob([[16, 21], [32, 21], [35, 28], [35, 38], [13, 38], [13, 28]], r, 0.3)}" fill="${bodyC}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  // 前掛け（明るい面）
  o += `<path d="${wob([[24, 24], [33, 24], [33, 37], [24, 37]], r, 0.3)}" fill="${light}" stroke="${T.ink}" stroke-width="${f(L * 0.75)}" stroke-linejoin="round"/>`;
  // 前に出した腕（右向き）
  o += `<path d="M30 27 L39 30" stroke="${T.ink}" stroke-width="${f(L + 3.4)}" stroke-linecap="round"/>`;
  o += `<path d="M30 27 L39 30" stroke="${bodyC}" stroke-width="3.4" stroke-linecap="round"/>`;
  // 頭（大きめ、2頭身半）
  o += `<path d="${wob(circ(24, 12, 10.5, 22), r, 0.25)}" fill="${SKIN}" stroke="${T.ink}" stroke-width="${L}"/>`;
  // 髪（後ろ）と布の帽子
  o += `<path d="${wob([[14, 14], [13.6, 9], [17, 4.5], [22, 3], [19, 8], [18, 15], [16, 17]], r, 0.2)}" fill="${HAIR}" stroke="${T.ink}" stroke-width="${f(L * 0.8)}" stroke-linejoin="round"/>`;
  o += `<path d="${wob([[15, 6.5], [20, 1.2], [29, 1], [34.5, 6], [30, 6.4], [22, 6]], r, 0.2)}" fill="${light}" stroke="${T.ink}" stroke-width="${f(L * 0.8)}" stroke-linejoin="round"/>`;
  // 顔の向き：目と鼻（右向き）
  o += `<circle cx="29.2" cy="11.5" r="1.5" fill="${T.mode === 'blueprint' ? '#0E1A28' : T.ink}"/>`;
  o += `<path d="M34 13 L35.6 15.2 L33.4 16" fill="none" stroke="${T.mode === 'blueprint' ? '#0E1A28' : T.ink}" stroke-width="1.2" stroke-linejoin="round"/>`;
  return o + '</g>';
}
function enemy(T, x, y) {
  const r = rng(202);
  let o = `<g transform="translate(${x} ${y})">`;
  // 左右非対称のにじみ（左の肩が高い・右に垂れる）
  const pts = [[8, 18], [11, 9], [17, 4], [23, 7], [27, 3], [33, 9], [37, 17], [41, 27], [40, 36], [43, 44], [35, 42], [30, 44], [22, 42], [15, 44], [9, 41], [5, 33], [6, 25]];
  const d = wob(pts, r, 0.8);
  o += `<g filter="url(#bleed${T.id})"><path d="${d}" fill="${T.enemyFill}" ${T.enemyEdge ? `stroke="${T.enemyEdge}" stroke-width="2"` : ''}/>`;
  o += `<circle cx="44" cy="30" r="1.4" fill="${T.enemyFill}" ${T.enemyEdge ? `stroke="${T.enemyEdge}" stroke-width="1"` : ''}/><circle cx="3" cy="40" r="1.1" fill="${T.enemyFill}"/></g>`;
  // 目は紙の色で2つ（大きさをわざと変える）。左を向く
  o += `<ellipse cx="14" cy="17" rx="3.4" ry="4.2" fill="${T.eyes}"/><ellipse cx="23" cy="16" rx="2.4" ry="3.2" fill="${T.eyes}"/>`;
  o += `<circle cx="13" cy="18" r="1.4" fill="${T.enemyFill}"/><circle cx="22.2" cy="17" r="1" fill="${T.enemyFill}"/>`;
  return o + '</g>';
}
function grave(T, x, y, crest) {
  const r = rng(303); const L = lw(r, 2);
  const c = T.ancestor, sh = darken(T.ancestor);
  const bp = T.mode === 'blueprint';
  let o = `<g transform="translate(${x} ${y})">`;
  o += `<path d="${wob([[3, 37], [45, 37], [44, 44], [4, 44]], r, 0.3)}" fill="${bp ? T.bg : sh}" stroke="${T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  o += `<path d="${wob([[10, 37], [10, 24], [14, 19], [34, 19], [38, 24], [38, 37]], r, 0.35)}" fill="${bp ? T.bg : c}" stroke="${bp ? c : T.ink}" stroke-width="${L}" stroke-linejoin="round"/>`;
  // 家の印：丸の枠に線3本まで（コードで作る。実在の紋ではない）
  o += `<circle cx="24" cy="28" r="5.8" fill="none" stroke="${bp ? c : T.ink}" stroke-width="1.2"/>`;
  o += `<path d="M24 23.2 L24 32.8 M20 30 L28 30" stroke="${bp ? c : T.ink}" stroke-width="1.2"/>`;
  // ひび1本（傷みの段）
  o += `<path d="${wob([[33, 19.5], [30.5, 23.5], [32.5, 26], [30, 30]], r, 0.2, false)}" fill="none" stroke="${T.ink}" stroke-width="1"/>`;
  return o + '</g>';
}
function stone(T, cx, cy, op = 1) {
  const r = rng(404); const [c] = MAT.stone;
  return `<path d="${wob(circ(cx, cy, 5.5, 12), r, 0.6)}" fill="${T.mode === 'blueprint' ? T.bg : c}" stroke="${T.ink}" stroke-width="2" opacity="${op}"/>`;
}

// ---------------------------------------------------------------- 共通の定義（影・にじみ・紙の繊維）
function defs(T) {
  return `<defs>
  <filter id="ds${T.id}" x="-20%" y="-20%" width="140%" height="140%">
    <feOffset in="SourceAlpha" dx="2" dy="2" result="o"/>
    <feFlood flood-color="${T.shadow}" flood-opacity="${T.shadowOpacity}"/><feComposite in2="o" operator="in" result="s"/>
    <feMerge><feMergeNode in="s"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="bleed${T.id}" x="-15%" y="-15%" width="130%" height="130%">
    <feTurbulence type="fractalNoise" baseFrequency="0.35" numOctaves="2" seed="7" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
  <filter id="paper${T.id}" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3"/>
    <feColorMatrix type="matrix" values="0 0 0 0 ${T.mode === 'blueprint' ? 1 : 0}  0 0 0 0 ${T.mode === 'blueprint' ? 1 : 0}  0 0 0 0 ${T.mode === 'blueprint' ? 1 : 0}  0.16 0 0 0 -0.05"/>
  </filter>
  <pattern id="hatch${T.id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <line x1="0" y1="0" x2="0" y2="6" stroke="${T.bgline}" stroke-width="1.5"/>
  </pattern>
</defs>`;
}
// 紙の繊維：盤面の上には出さない（evenodd で盤面をくりぬく）
function paperNoise(T, w, h, hole) {
  const clip = hole ? `<clipPath id="nb${T.id}"><path clip-rule="evenodd" d="M0 0 H${w} V${h} H0 Z M${hole[0]} ${hole[1]} V${hole[1] + hole[3]} H${hole[0] + hole[2]} V${hole[1]} Z"/></clipPath>` : '';
  return `${clip}<rect x="0" y="0" width="${w}" height="${h}" filter="url(#paper${T.id})" ${hole ? `clip-path="url(#nb${T.id})"` : ''}/>`;
}

const FONT_G = `'IPAGothic','IPAPGothic','Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif`;
const FONT_M = `'IPAMincho','Noto Serif JP','Hiragino Mincho ProN','Yu Mincho',serif`;
const txt = (T, x, y, s, size, o = {}) => `<text x="${x}" y="${y}" font-size="${size}" fill="${o.fill || T.ink}" font-family="${o.mincho ? FONT_M : FONT_G}" ${o.anchor ? `text-anchor="${o.anchor}"` : ''} ${o.bold ? 'font-weight="bold"' : ''} ${o.ls ? `letter-spacing="${o.ls}"` : ''}>${s}</text>`;
function card(T, x, y, w, h, opt = {}) { // 札・ボタン：角丸 4px、縁 2px、右下に落ち影
  const fill = opt.fill || T.button;
  return `<g ${opt.noShadow ? '' : `filter="url(#ds${T.id})"`}><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${fill}" stroke="${opt.stroke || T.ink}" stroke-width="${opt.sw || 2}"/></g>`
    + (opt.hatch ? `<rect x="${x + 1}" y="${y + 1}" width="${w - 2}" height="${h - 2}" rx="3" fill="url(#hatch${T.id})"/>` : '');
}

// ---------------------------------------------------------------- 挑む画面（360×640）
const BX = 12, BY = 52, C = 48;
const cx = (c) => BX + c * C, cy = (r) => BY + r * C;

function challengeScreen(T) {
  const W = 360, H = 640;
  let o = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${defs(T)}`;
  o += `<rect width="${W}" height="${H}" fill="${T.bg}"/>`;

  // 上の帯 0〜44：代・年・掟の札（見るだけ）
  o += `<rect x="0" y="0" width="${W}" height="44" fill="${T.panel}"/><line x1="0" y1="44" x2="${W}" y2="44" stroke="${T.grid}" stroke-width="1"/>`;
  o += grave(T, 6, -4, true).replace('<g transform="translate(6 -4)">', '<g transform="translate(8 6) scale(0.66)">');
  o += txt(T, 44, 28, '三代目　谷暦四十一年', 16, { mincho: true });
  o += card(T, 264, 8, 86, 28, { fill: T.button, stroke: T.rule, noShadow: true });
  o += `<g transform="translate(272 14)"><path d="M2 2 L0 9 M7 1 L5 8 M12 2 L10 9" stroke="${T.rule}" stroke-width="1.6" stroke-linecap="round"/><path d="M0 13 q2 -2 4 0 t4 0 t4 0" fill="none" stroke="${T.rule}" stroke-width="1.6"/></g>`;
  o += txt(T, 292, 28, '掟：長雨', 14, { mincho: true });

  // 盤面 52〜388：7×7（48px）
  for (let r = 0; r < 7; r++) for (let c = 0; c < 7; c++)
    o += `<rect x="${cx(c)}" y="${cy(r)}" width="${C}" height="${C}" fill="${(r + c) % 2 ? T.panel : T.bg}"/>`;
  // 遠景（薄墨の線）
  const rr = rng(505);
  o += `<path d="${wob([[12, 150], [40, 128], [62, 136], [96, 104], [128, 126], [150, 118], [190, 92], [232, 124], [262, 112], [300, 84], [348, 108]], rr, 1, false)}" fill="none" stroke="${T.bgline}" stroke-width="1"/>`;
  o += `<path d="${wob([[72, 136], [96, 116], [118, 128]], rr, 0.6, false)}" fill="none" stroke="${T.bgline}" stroke-width="1"/>`;
  o += `<path d="${wob([[200, 104], [216, 114], [236, 106]], rr, 0.6, false)}" fill="none" stroke="${T.bgline}" stroke-width="1"/>`;
  // 掟の効果（長雨の線）不透明度 25%
  let rain = ''; const rnr = rng(606);
  for (let i = 0; i < 26; i++) { const x = 14 + rnr() * 330, y = 54 + rnr() * 180; rain += `M${f(x)} ${f(y)} l-3 10 `; }
  o += `<path d="${rain}" stroke="${T.water}" stroke-width="1.5" stroke-linecap="round" opacity="0.25"/>`;
  // 地形：地面（左は 5 段目から、右の崖の上は 4 段目から）
  const groundY = cy(5), cliffX = cx(5), cliffY = cy(4);
  o += `<path d="${wob([[12, groundY], [80, groundY + 0.5], [160, groundY - 0.5], [cliffX, groundY]], rr, 0.4, false)} L${cliffX} ${cliffY} L348 ${cliffY}" fill="none" stroke="${T.bgline}" stroke-width="2" stroke-linejoin="round"/>`;
  let strata = '';
  [12, 26, 44, 66].forEach((dy, i) => { const y = groundY + dy; for (let x = 14 + (i % 2) * 14; x < cliffX - 6; x += 40) strata += wob([[x, y], [Math.min(x + 26 - i * 3, cliffX - 4), y + (rr() - 0.5)]], rr, 0.3, false) + ' '; });
  [14, 30, 52, 74, 100, 124].forEach((dy, i) => { const y = cliffY + dy; for (let x = cliffX + 10 + (i % 2) * 12; x < 344; x += 34) strata += wob([[x, y], [Math.min(x + 22, 346), y]], rr, 0.3, false) + ' '; });
  o += `<path d="${strata}" fill="none" stroke="${T.bgline}" stroke-width="1" stroke-linecap="round"/>`;
  let kasure = ''; for (let i = 0; i < 9; i++) { const y = cliffY + 6 + i * 15; kasure += `M${cliffX + 3 + (i % 3) * 2} ${y} l0.5 ${8 + (i % 2) * 4} `; }
  o += `<path d="${kasure}" stroke="${T.bgline}" stroke-width="1" stroke-linecap="round"/>`;
  // マス目の線（罫）
  let grid = ''; for (let i = 0; i <= 7; i++) grid += `M${cx(i)} ${BY} V${BY + 336} M${BX} ${cy(i)} H${BX + 336} `;
  o += `<path d="${grid}" stroke="${T.grid}" stroke-width="1"/>`;

  // 当主の次の1手：行き先のマスの下塗り＋丸＋足あと（実線 2px）
  o += `<rect x="${cx(2) + 1}" y="${cy(4) + 1}" width="${C - 2}" height="${C - 2}" fill="${T.destFill}"/>`;
  o += `<circle cx="${cx(2) + 24}" cy="${cy(4) + 26}" r="15" fill="none" stroke="${T.lord}" stroke-width="2"/>`;
  const foot = (x, y, a) => `<ellipse cx="${x}" cy="${y}" rx="2.6" ry="4.2" transform="rotate(${a} ${x} ${y})" fill="${T.lord}"/>`;
  o += foot(cx(2) + 18, cy(4) + 30, 75) + foot(cx(2) + 29, cy(4) + 24, 75);

  // 先祖の墓（0,4）
  o += `<g filter="url(#ds${T.id})">${grave(T, cx(0), cy(4))}</g>`;
  // 当主（1,4）
  o += `<g filter="url(#ds${T.id})">${lord(T, cx(1) + 4 - 4, cy(4))}</g>`;
  // 発明品：ばね（3,4）＋歯車（4,4）＋投石の腕（4,3）。部品の絵をそのまま組む
  o += `<g filter="url(#ds${T.id})">`;
  o += part(T, 'spring', cx(3), cy(4), 48, { joints: [[44, 24]] });
  o += part(T, 'gear', cx(4), cy(4), 48, { joints: [[4, 24], [24, 4]], weight: 2 });
  o += part(T, 'arm', cx(4), cy(3), 48, { joints: [[24, 44]], wet: true });
  o += stone(T, cx(4) + 11, cy(3) + 9);
  o += `</g>`;
  // 敵（6,3）：崖の上
  o += `<g filter="url(#ds${T.id})">${enemy(T, cx(6) + 2, cy(3))}</g>`;

  // 道具の次の動き：石の影（40%）＋点線の弧 2px（4/4）＋矢
  const sx = cx(4) + 12, sy = cy(3) + 2, ex = cx(5) + 24, ey = cy(2) + 22;
  o += `<path d="M${sx} ${sy} Q${cx(4) + 34} ${cy(1) - 4} ${ex - 3} ${ey - 9}" fill="none" stroke="${T.ink}" stroke-width="2" stroke-dasharray="4 4"/>`;
  o += `<path d="M${ex - 9} ${ey - 13} L${ex - 1} ${ey - 6} L${ex - 10} ${ey - 4}" fill="none" stroke="${T.ink}" stroke-width="2" stroke-linejoin="round"/>`;
  o += stone(T, ex, ey, 0.4);
  // 敵の次の手：行き先（5,3）に「く」の字の爪あと（破線 2px 8/4）
  const kx = cx(5), ky = cy(3);
  o += `<path d="M${kx + 30} ${ky + 8} L${kx + 14} ${ky + 22} L${kx + 30} ${ky + 38} M${kx + 40} ${ky + 8} L${kx + 24} ${ky + 22} L${kx + 40} ${ky + 38}" fill="none" stroke="${T.enemyMark}" stroke-width="2" stroke-dasharray="8 4" stroke-linecap="round" stroke-linejoin="round"/>`;

  // 説明の帯 392〜436（1行、20字まで）
  o += card(T, 8, 392, 344, 44, { fill: T.panel, stroke: T.grid, sw: 1, noShadow: true });
  o += `<circle cx="28" cy="414" r="8" fill="none" stroke="${T.lord}" stroke-width="2"/>` + foot(26, 416, 75).replace(/rx="2.6" ry="4.2"/, 'rx="1.8" ry="3"');
  o += txt(T, 44, 420, '一歩進む。ばねが押され、石が崖へ', 16);

  // 手の棚 440〜560
  o += `<rect x="0" y="440" width="${W}" height="120" fill="${T.panel}"/>`;
  const items = [['進む', 'walk', 'sel'], ['使う', 'use'], ['待つ', 'wait'], ['拾う', 'pick', 'off'], ['帳面', 'book']];
  items.forEach(([label, ic, st], i) => {
    const x = 14 + i * 68, y = 452, w = 60, h = 96;
    if (st === 'sel') {
      o += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${T.select}"/>`;
      o += `<rect x="${x - 0.5}" y="${y - 0.5}" width="${w + 1}" height="${h + 1}" rx="4" fill="none" stroke="${T.selectBorder}" stroke-width="3"/>`;
    } else o += card(T, x, y, w, h, { hatch: st === 'off', stroke: st === 'off' ? T.bgline : T.ink });
    const col = st === 'off' ? T.bgline : T.ink;
    o += icon(T, ic, x + 30, y + 34, col);
    o += txt(T, x + 30, y + 80, label, 14, { anchor: 'middle', fill: col });
  });

  // 親指の帯 568〜632：取り消し・1手送り・確定（大）・メニュー
  o += card(T, 11, 568, 56, 64); o += icon(T, 'undo', 39, 590, T.ink); o += txt(T, 39, 622, '戻す', 14, { anchor: 'middle' });
  o += card(T, 73, 568, 56, 64); o += icon(T, 'step', 101, 590, T.ink); o += txt(T, 101, 622, '送る', 14, { anchor: 'middle' });
  o += card(T, 135, 568, 160, 64); o += txt(T, 215, 608, '確　定', 20, { anchor: 'middle', bold: true });
  o += card(T, 301, 568, 48, 64); o += `<path d="M315 590 H335 M315 600 H335 M315 610 H335" stroke="${T.ink}" stroke-width="2" stroke-linecap="round"/>`;

  o += paperNoise(T, W, H, [BX, BY, 336, 336]);
  return o + '</svg>';
}

function icon(T, k, x, y, col) { // 手の棚・ボタンの小さな絵（24px 前後）
  const s = `stroke="${col}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"`;
  switch (k) {
    case 'walk': return `<g transform="translate(${x} ${y})"><ellipse cx="-6" cy="5" rx="3.4" ry="5.6" transform="rotate(75 -6 5)" fill="${col}"/><ellipse cx="7" cy="-3" rx="3.4" ry="5.6" transform="rotate(75 7 -3)" fill="${col}"/><path d="M-12 12 H12" ${s} stroke-dasharray="3 3"/></g>`;
    case 'use': return `<g transform="translate(${x} ${y})"><path d="M-10 6 L4 -8 M0 -12 L8 -4 L4 0 L-4 -8 Z" ${s}/><path d="M-12 12 H12" ${s}/></g>`;
    case 'wait': return `<g transform="translate(${x} ${y})"><path d="M-8 -12 H8 M-8 12 H8 M-6 -12 C-6 -3 6 3 6 12 M6 -12 C6 -3 -6 3 -6 12" ${s}/></g>`;
    case 'pick': return `<g transform="translate(${x} ${y})"><path d="M-10 -2 H10 L8 12 H-8 Z M-5 -2 C-5 -10 5 -10 5 -2" ${s}/></g>`;
    case 'book': return `<g transform="translate(${x} ${y})"><path d="M0 -8 C-4 -11 -9 -11 -12 -9 V10 C-9 8 -4 8 0 11 C4 8 9 8 12 10 V-9 C9 -11 4 -11 0 -8 Z M0 -8 V11" ${s}/></g>`;
    case 'undo': return `<g transform="translate(${x} ${y})"><path d="M-6 -6 L-11 -1 L-6 4 M-11 -1 H4 C9 -1 11 3 11 6 C11 10 8 12 4 12" ${s}/></g>`;
    case 'step': return `<g transform="translate(${x} ${y})"><path d="M-8 -9 L4 0 L-8 9 Z" ${s} fill="${col}"/><path d="M9 -9 V9" ${s}/></g>`;
  }
  return '';
}

// ---------------------------------------------------------------- 部品の見本（360×640、上 A・下 B）
function partsSheet() {
  const W = 360, H = 640;
  let o = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${defs(THEME.A)}${defs(THEME.B)}`;
  const half = (T, y0, h) => {
    let s = `<rect x="0" y="${y0}" width="${W}" height="${h}" fill="${T.bg}"/>`;
    s += txt(T, 12, y0 + 22, T.name + '　部品3点', 16, { mincho: true });
    const cols = [118, 210, 302];
    const kinds = [['spring', 'ばね（真鍮）'], ['gear', '歯車（真鍮）'], ['arm', '投石の腕（木）']];
    const label = (y, a, b) => txt(T, 12, y, a, 14) + txt(T, 12, y + 17, b, 14, { fill: T.ink });
    // 作業台 56
    let y = y0 + 36;
    s += label(y + 24, '作業台', '56px');
    kinds.forEach(([k, n], i) => {
      s += `<rect x="${cols[i] - 28}" y="${y}" width="56" height="56" fill="${T.panel}" stroke="${T.grid}" stroke-width="1"/>`;
      s += `<g filter="url(#ds${T.id})">${part(T, k, cols[i] - 28, y, 56, k === 'gear' ? { weight: 2 } : k === 'arm' ? { wet: true } : {})}</g>`;
      s += txt(T, cols[i], y + 74, n, 14, { anchor: 'middle' });
    });
    // 盤面 48
    y += 86;
    s += label(y + 20, '盤面', '48px');
    kinds.forEach(([k], i) => { s += `<rect x="${cols[i] - 24}" y="${y}" width="48" height="48" fill="${T.panel}" stroke="${T.grid}" stroke-width="1"/>`; s += `<g filter="url(#ds${T.id})">${part(T, k, cols[i] - 24, y, 48)}</g>`; });
    // 帳面・図鑑 24（内線なし、主線 1.5px）＋ 墨一色の影絵
    y += 58;
    s += label(y + 10, '帳面', '24px');
    kinds.forEach(([k], i) => {
      s += part(T, k, cols[i] - 34, y, 24, {});
      s += `<g transform="translate(${cols[i] + 10} ${y}) scale(0.5)">${PARTS[k](T, 24, {}).replace(/fill="#[0-9A-Fa-f]{6}"/g, `fill="${T.ink}"`).replace(/stroke="#[0-9A-Fa-f]{6}"/g, `stroke="${T.ink}"`)}</g>`;
    });
    s += txt(T, 348, y + 40, '左：24px　右：影絵', 12, { anchor: 'end', fill: T.ink });
    // 古びの段：新しい／傷み／壊れかけ（ひび 0/1/2、彩度 −0/−25/−50%）
    y += 50;
    s += label(y + 20, '古び', '48px');
    ['新しい', '傷み', '壊れかけ'].forEach((n, i) => {
      s += `<rect x="${cols[i] - 24}" y="${y}" width="48" height="48" fill="${T.panel}" stroke="${T.grid}" stroke-width="1"/>`;
      s += `<g filter="url(#ds${T.id})">${part(T, 'gear', cols[i] - 24, y, 48, { age: i })}</g>`;
      s += txt(T, cols[i], y + 64, n, 14, { anchor: 'middle' });
    });
    s += paperNoise(T, W, H, null).replace('<rect x="0" y="0"', `<rect x="0" y="${y0}"`).replace(`height="${H}"`, `height="${h}"`);
    return s;
  };
  o += half(THEME.A, 0, 320);
  o += half(THEME.B, 320, 320);
  return o + '</svg>';
}

// ---------------------------------------------------------------- 書き出し
function html(title, svg) {
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=360">
<title>${title}</title><style>html,body{margin:0;padding:0;background:#777}svg{display:block}</style></head>
<body>${svg}</body></html>`;
}
const files = [
  ['挑む画面_A_帳面の谷', '挑む画面：A 帳面の谷', challengeScreen(THEME.A)],
  ['挑む画面_B_青焼きの工房', '挑む画面：B 青焼きの工房', challengeScreen(THEME.B)],
  ['部品3点_AB比較', '部品3点：A と B', partsSheet()],
];
for (const [n, t, svg] of files) {
  fs.writeFileSync(path.join(OUT, n + '.html'), html(t, svg));
  fs.writeFileSync(path.join(OUT, n + '.svg'), svg);
}
console.log('html/svg written');

if (process.argv.includes('--png')) {
  (async () => {
    const { chromium } = require('playwright');
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 2 });
    for (const [n] of files) {
      await page.goto('file://' + path.join(OUT, n + '.html'));
      await page.screenshot({ path: path.join(OUT, n + '.png') });
      await page.addStyleTag({ content: 'svg{filter:grayscale(1)}' });
      await page.screenshot({ path: path.join(OUT, n + '_グレー.png') });
    }
    await browser.close();
    console.log('png written');
  })();
}
