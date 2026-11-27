// 並べ図（段階4）。node lineup_sheet.js ../並べ図.svg
const fs = require('fs');
const { H, M, O, s1 } = require('./lineup.js');
const K = '#1B2233';
const F = `font-family="IPAGothic, 'IPAゴシック', 'Hiragino Sans', sans-serif"`;
let n = 0; const u = (svg) => { n++; return svg.replace(/id="(sw\d+)"/g, `id="$1_${n}"`).replace(/url\(#(sw\d+)\)/g, `url(#$1_${n})`); };
const hero = (pose, opt) => s1.ped() + s1.draw(pose, opt);
const T = (x, y, t, sz = 12, w = 400, c = '#333', a = 'middle') => `<text x="${x}" y="${y}" font-size="${sz}" font-weight="${w}" fill="${c}" text-anchor="${a}">${t}</text>`;
const heroes = [
  ['剣士 待つ', () => hero('idle0')], ['剣士 当て(左)', () => hero('hit')], ['剣士 立つ最後(P2)', () => hero('spawnEnd')], ['剣士 重なり(P3)', () => hero('stack')], ['剣士 当て(右)', () => hero('hitR')],
  ['いまの見本', H.old], ['sword2 仮', H.sword2], ['盾の騎士 仮', H.knight], ['槍兵 仮', H.spear], ['弓使い 仮', H.archer], ['魔法使い 仮', H.mage], ['僧侶 仮', H.priest], ['斥候 仮', H.scout],
];
const mons = [['スライム', M.slime], ['ゴブリン', M.goblin], ['コウモリ', M.bat], ['オオカミ', M.wolf], ['骸骨の兵士', M.skeleton], ['オーク', M.orc], ['群れ', M.swarm], ['大物', M.boss]];
const defs = `<defs>
<filter id="gs"><feColorMatrix type="saturate" values="0"/></filter>
<filter id="sil"><feColorMatrix type="matrix" values="0 0 0 0 0.106  0 0 0 0 0.133  0 0 0 0 0.2  0 0 0 1 0"/></filter>
<filter id="blur2"><feGaussianBlur stdDeviation="3"/></filter>
<pattern id="tile" width="64" height="64" patternUnits="userSpaceOnUse"><rect width="64" height="64" fill="#A9CB8C"/><rect width="32" height="32" fill="#A2C585"/><rect x="32" y="32" width="32" height="32" fill="#A2C585"/></pattern>
<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0.8"/></linearGradient>
</defs>`;
const W = 1640;
let s = '';
let y = 0;
s += T(24, 38, '剣士 sword1 並べ図（段階4）', 24, 700, K, 'start');
s += T(24, 62, 'game-art-concept 2026-11-27。剣士は 監修_段階2 の直しを入れた A どんぶり兜 × A-1。ほかの英雄・魔物・物は、アートディレクション 3.2・3.3・5.2 の影の形と大きさから描いた比べ用の仮（本番の姿ではない）。', 13, 400, '#444', 'start');
s += T(24, 80, '同じ比率で並べた。足もと（台座の中心・魔物の影の中心）を同じ線にそろえた。点線は台座の下の端からの高さ 44 / 51 / 58（剣士の重なりの剣の先＝51、槍兵の仮の槍の先＝58）。', 13, 400, '#444', 'start');

// 1. 顔ぶれ 2倍
y = 100;
const sc = 2, step = 58;
s += `<rect x="16" y="${y}" width="${W - 32}" height="300" rx="8" fill="#A9CB8C"/>`;
s += T(28, y + 22, '1. 顔ぶれ（2倍）英雄', 15, 700, K, 'start');
let base = y + 250;
[44, 51, 58].forEach((h, k) => { const yy = base + 6 * sc - h * sc; s += `<path d="M28 ${yy} H${W - 28}" stroke="${h === 58 ? '#B5653A' : h === 51 ? '#D9413A' : '#2F6FD6'}" stroke-dasharray="5 4" stroke-width="1"/>` + T(W - 40 - k * 70, yy - 3, `高さ${h}`, 11, 700, '#333', 'end'); });
heroes.forEach(([lab, f], i) => { const cx = 70 + i * step * sc / 1.0 * 0.92; s += `<g transform="translate(${cx} ${base}) scale(${sc})">${u(f())}</g>` + T(cx, base + 36, lab, 11, 700, K); });
y += 316;
s += `<rect x="16" y="${y}" width="${W - 32}" height="330" rx="8" fill="#A9CB8C"/>`;
s += T(28, y + 22, '1. 顔ぶれ（2倍）魔物と物。左端は比べる用の剣士', 15, 700, K, 'start');
base = y + 280;
for (const h of [44]) { const yy = base + 6 * sc - h * sc; s += `<path d="M28 ${yy} H${W - 28}" stroke="#2F6FD6" stroke-dasharray="5 4" stroke-width="1"/>`; }
const row2 = [['剣士 待つ', () => hero('idle0'), 50], ...mons.map(([l, f]) => [l, f, l === '大物' ? 90 : l === 'オーク' || l === 'オオカミ' ? 64 : 50]), ['塔 56×96', O.tower, 90], ['パック 26×38', O.pack, 50], ['攻撃の輪 半径28', O.ring, 70]];
let cx = 70;
row2.forEach(([lab, f, w], i) => { if (i) cx += (w + row2[i - 1][2]) / 2 * sc * 0.8; const dy = lab.startsWith('攻撃') ? -40 : 0; s += `<g transform="translate(${cx} ${base + dy * sc / 2}) scale(${sc})">${u(f())}</g>` + T(cx, base + 40, lab, 11, 700, K); });
s += `<g transform="translate(${cx + 110} ${base - 30}) scale(${sc})">${O.dmg('12')}</g>` + T(cx + 110, base + 40, 'ダメージの数 13px', 11, 700, K);
y += 346;

// 2. 見分けの条件
s += T(24, y + 20, '2. 見分けの条件：同じ並びを 1倍・色／2倍・影だけ／2倍・ぼかし（色だけ）／2倍・白黒（1倍の並びは 2倍の段の名前と同じ順）', 15, 700, K, 'start');
y += 30;
const cmp = [['剣士', () => hero('idle0')], ['いま', H.old], ['sword2', H.sword2], ['騎士', H.knight], ['槍兵', H.spear], ['弓', H.archer], ['魔法', H.mage], ['僧侶', H.priest], ['斥候', H.scout], ['スライム', M.slime], ['ゴブリン', M.goblin], ['骸骨', M.skeleton], ['コウモリ', M.bat], ['オオカミ', M.wolf]];
const rowOf = (scale, filter, x0, y0, bg) => { let r = `<rect x="${x0}" y="${y0}" width="${cmp.length * 46 * scale + 20}" height="${62 * scale}" rx="6" fill="${bg}"/>`; r += `<g ${filter ? `filter="url(#${filter})"` : ''}>`; cmp.forEach(([l, f], i) => { r += `<g transform="translate(${x0 + 30 * scale / 1.3 + 8 + i * 46 * scale} ${y0 + 54 * scale}) scale(${scale})">${u(f())}</g>`; }); r += '</g>'; if (scale >= 2) cmp.forEach(([l], i) => r += T(x0 + 30 * scale / 1.3 + 8 + i * 46 * scale, y0 + 62 * scale + 14, l, 11, 700, K)); return r; };
s += T(28, y + 14, '1倍・色（草地）', 12, 700, K, 'start') + rowOf(1, null, 150, y, '#A9CB8C');
s += T(830, y + 14, '1倍・白黒', 12, 700, K, 'start') + `<g filter="url(#gs)">${rowOf(1, null, 920, y, '#A9CB8C')}</g>`;
y += 80;
s += T(28, y + 14, '2倍・影だけ', 12, 700, K, 'start') + rowOf(2, 'sil', 150, y, '#E9EDE2');
y += 152;
s += T(28, y + 14, '2倍・ぼかし', 12, 700, K, 'start') + `<g filter="url(#blur2)">${rowOf(2, null, 150, y, '#A9CB8C')}</g>`;
y += 152;
s += T(28, y + 14, '2倍・白黒', 12, 700, K, 'start') + `<g filter="url(#gs)">${rowOf(2, null, 150, y, '#A9CB8C')}</g>`;
y += 152;

// 3. 取り違えの確かめ（3倍）と、帯の金・茶
s += T(24, y + 20, '3. 取り違えやすいものを 3倍で（左＝色、右＝白黒）。剣士・僧侶の頭巾・骸骨の兵士の兜・スライム（きのこ）・魔法使い・盾の騎士', 15, 700, K, 'start');
y += 30;
const tri = [['剣士', () => hero('idle0')], ['僧侶', H.priest], ['骸骨', M.skeleton], ['スライム', M.slime], ['魔法使い', H.mage], ['盾の騎士', H.knight]];
for (const g of [0, 1]) {
  const x0 = 24 + g * 800;
  s += `<g ${g ? 'filter="url(#gs)"' : ''}><rect x="${x0}" y="${y}" width="780" height="200" rx="8" fill="#A9CB8C"/>`;
  tri.forEach(([l, f], i) => s += `<g transform="translate(${x0 + 70 + i * 128} ${y + 168}) scale(3)">${u(f())}</g>`);
  s += '</g>';
  tri.forEach(([l], i) => s += T(x0 + 70 + i * 128, y + 196, l, 12, 700, K));
}
y += 216;
s += T(24, y + 20, '4. 帯の色：茶 #6A4A34（監修の推し）と 金 #E8B730。sword2 の仮（金の縁）と並べる。1倍・3倍・白黒', 15, 700, K, 'start');
y += 30;
const belts = [['帯 茶', () => hero('idle0', { belt: 'brown' })], ['帯 金', () => hero('idle0', { belt: 'gold' })], ['sword2 仮', H.sword2]];
s += `<rect x="24" y="${y}" width="1592" height="190" rx="8" fill="#A9CB8C"/>`;
belts.forEach(([l, f], i) => {
  s += `<g transform="translate(${70 + i * 130} ${y + 160}) scale(3)">${u(f())}</g>` + T(70 + i * 130, y + 184, l, 12, 700, K);
  s += `<g filter="url(#gs)"><g transform="translate(${470 + i * 130} ${y + 160}) scale(3)">${u(f())}</g></g>` + T(470 + i * 130, y + 184, l + '（白黒）', 12, 700, K);
  s += `<g transform="translate(${900 + i * 50} ${y + 100})">${u(f())}</g>` + T(900 + i * 50, y + 120, l.replace('sword2 仮', 's2'), 10, 700, K);
  s += `<rect x="${1070 + i * 50 - 22}" y="${y + 50}" width="44" height="60" fill="#DCCBA4"/><g transform="translate(${1070 + i * 50} ${y + 100})">${u(f())}</g>`;
});
s += T(900, y + 30, '1倍 草地', 12, 700, K, 'start') + T(1050, y + 30, '1倍 道', 12, 700, K, 'start');
y += 206;

// 5. 背景の上で
s += T(24, y + 20, '5. 地面の上で（1倍と3倍）：草地・市松・丘・道', 15, 700, K, 'start');
y += 30;
const grounds = [['草地 #A9CB8C', '#A9CB8C'], ['市松 #A2C585', '#A2C585'], ['丘 #8DB06F', '#8DB06F'], ['道 #DCCBA4', '#DCCBA4']];
grounds.forEach(([l, c], i) => {
  const x0 = 24 + i * 400;
  s += `<rect x="${x0}" y="${y}" width="390" height="180" rx="8" fill="${c}"/>` + T(x0 + 10, y + 18, l, 12, 700, K, 'start');
  s += `<g transform="translate(${x0 + 50} ${y + 120})">${u(hero('idle0'))}</g>`;
  s += `<g transform="translate(${x0 + 90} ${y + 120})">${u(M.slime())}</g>`;
  s += `<g transform="translate(${x0 + 250} ${y + 160}) scale(3)">${u(hero('idle0'))}</g>`;
});
y += 196;

// 6. 場面
s += T(24, y + 20, '6. 場面（2倍）：塔の左と右に立つ剣士、同じ剣士2人が重なり矢印が出ている、魔物・パック・攻撃の輪・ダメージの数。右＝同じ場面の白黒', 15, 700, K, 'start');
y += 30;
const scene = () => {
  let o = `<rect width="320" height="210" fill="url(#tile)"/><rect x="138" y="0" width="44" height="210" fill="#DCCBA4"/><rect x="0" y="108" width="320" height="44" fill="#DCCBA4"/>`;
  o += `<g transform="translate(160 150)">${O.tower()}</g>`;
  o += `<g transform="translate(108 168)">${u(hero('idle0'))}</g>`;              // 塔の左
  o += `<g transform="translate(214 168)">${u(hero('windupR'))}</g>`;             // 塔の右（構え・右）
  o += `<g transform="translate(250 104)">${u(hero('stack'))}</g><g transform="translate(278 112)">${u(hero('idle1'))}</g><g transform="translate(250 57)">${O.arrow()}</g>`; // 重なり
  o += `<g transform="translate(60 132)">${u(M.slime())}</g><g transform="translate(60 118)">${O.ring()}</g><g transform="translate(72 92)">${O.dmg('12')}</g>`;
  o += `<g transform="translate(30 182)">${u(M.goblin())}</g><g transform="translate(292 186)">${u(M.skeleton())}</g><g transform="translate(220 52)">${u(M.bat())}</g>`;
  o += `<rect x="45" y="0" width="30" height="60" fill="url(#beam)"/><g transform="translate(60 64)">${O.pack()}</g>`;
  return o;
};
s += `<g transform="translate(24 ${y}) scale(2)">${scene()}</g>`;
s += `<g filter="url(#gs)"><g transform="translate(680 ${y}) scale(2)">${scene()}</g></g>`;
s += `<g transform="translate(1340 ${y})">${scene()}</g>` + T(1340, y + 226, '1倍', 12, 700, K, 'start');
y += 440;
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${y}" viewBox="0 0 ${W} ${y}" ${F}>\n<!-- 剣士 sword1 並べ図。game-art-concept 2026-11-27。作図/lineup_sheet.js で作る -->\n${defs}<rect width="${W}" height="${y}" fill="#F4F2EC"/>\n${s}\n</svg>\n`;
fs.writeFileSync(process.argv[2], svg);
