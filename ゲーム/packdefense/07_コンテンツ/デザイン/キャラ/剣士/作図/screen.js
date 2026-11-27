// 画面確認（段階6）。スタイル見本の戦場の剣士を新しい剣士に差し替えたものを 画面確認/ に作る（元のファイルは書き換えない）。
// node screen.js  → ../画面確認/*.svg を書く。PNG は shot.js で書き出す（下の run.sh）
const fs = require('fs'), path = require('path');
const { H, M, O, s1 } = require('./lineup.js');
const SRC = path.resolve(__dirname, '../../../../../02_プリプロ/スタイル見本/戦場_色.svg');
const OUT = path.resolve(__dirname, '../画面確認');
fs.mkdirSync(OUT, { recursive: true });
const src = fs.readFileSync(SRC, 'utf8');
let n = 0; const u = (svg) => { n++; return svg.replace(/id="(sw\d+)"/g, `id="$1_${n}"`).replace(/url\(#(sw\d+)\)/g, `url(#$1_${n})`); };
const a = src.indexOf('    <!-- 英雄：剣士'), b = src.indexOf('    <!-- 落ちたコイン');
if (a < 0 || b < 0) throw new Error('見本の英雄の場所が見つからない');
const hero = (x, y, pose = 'idle0') => `<g transform="translate(${x} ${y})">${u(s1.ped() + s1.draw(pose))}</g>`;
const newHero = `    <!-- 英雄：剣士 sword1（07 の設定画の版。台座の中心 250,480 は見本と同じ） -->\n    ${hero(250, 480)}\n\n`;
const base = src.slice(0, a) + newHero + src.slice(b);
const gray = (svg) => svg.replace(/<defs>/, '<defs><filter id="gsall" color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0"/></filter>').replace('<g id="all"', '<g id="all" filter="url(#gsall)"');
fs.writeFileSync(path.join(OUT, '戦場_差し替え.svg'), base);
fs.writeFileSync(path.join(OUT, '戦場_差し替え_白黒.svg'), gray(base));
// 半分の大きさ：同じ絵を 195×422 に縮めたもの
const half = base.replace('width="390" height="844" viewBox="0 0 390 844"', 'width="195" height="422" viewBox="0 0 390 844"');
if (half === base) throw new Error('半分の置きかえに失敗');
fs.writeFileSync(path.join(OUT, '戦場_差し替え_半分.svg'), half);
// いちばん混み合った場面：魔物が多い（四方から）、英雄が塔のまわりに6人、効果が重なる
let crowd = '';
const fire = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${r}" fill="#FF9A3A" fill-opacity="0.35"/><circle cx="${x}" cy="${y}" r="${r * 0.6}" fill="#FFD24A" fill-opacity="0.4"/>`;
const star = (x, y) => `<path d="M${x - 5} ${y} L${x + 5} ${y} M${x} ${y - 5} L${x} ${y + 5} M${x - 3.5} ${y - 3.5} L${x + 3.5} ${y + 3.5} M${x - 3.5} ${y + 3.5} L${x + 3.5} ${y - 3.5}" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>`;
crowd += `    <!-- 混雑：燃える地面（地面の上・キャラの下） -->\n` + fire(300, 450, 30) + fire(120, 300, 22);
const mons = [
  [M.slime, 318, 452], [M.slime, 352, 470], [M.swarm, 300, 500], [M.goblin, 196, 300], [M.goblin, 222, 270], [M.wolf, 90, 440], [M.wolf, 60, 420],
  [M.skeleton, 175, 560], [M.skeleton, 212, 590], [M.orc, 196, 660], [M.slime, 120, 300], [M.swarm, 80, 330], [M.goblin, 330, 300],
];
const heroes = [[250, 480, 'hit'], [140, 480, 'idle0'], [235, 382, 'windup'], [150, 380, 'idle1'], [262, 520, 'stack'], [128, 520, 'recover']];
const items = [...mons.map(([f, x, y]) => [y, `<g transform="translate(${x} ${y})">${u(f())}</g>`]), ...heroes.map(([x, y, p]) => [y, hero(x, y, p)])];
items.sort((p, q) => p[0] - q[0]);
crowd += items.map(i => '    ' + i[1]).join('\n') + '\n';
crowd += `    <g transform="translate(236 170)">${M.bat()}</g><g transform="translate(270 200)">${M.bat()}</g><g transform="translate(150 210)">${M.bat()}</g>\n`;
crowd += `    <g transform="translate(262 466)">${O.arrow()}</g>` + star(224, 478) + star(208, 396) + star(118, 512);
crowd += [[300, 425, '1.8万'], [330, 448, '2.4万'], [100, 410, '9,800'], [200, 548, '3.1万'], [214, 286, '12万']].map(([x, y, t], i) => `<g transform="translate(${x} ${y})">${O.dmg(t, i === 4 ? 17 : 13)}</g>`).join('');
crowd += `<g transform="translate(320 440)">${O.ring()}</g>`;
const crowdSvg = base.replace('    <!-- 落ちたコイン', `    <!-- ここから 画面確認の混雑（仮の魔物・英雄・効果。作図/lineup.js） -->\n${crowd}\n    <!-- 落ちたコイン`);
// 混雑の場面では、見本のもとのスライム・攻撃の輪はそのまま残る
fs.writeFileSync(path.join(OUT, '混雑.svg'), crowdSvg);
fs.writeFileSync(path.join(OUT, '混雑_白黒.svg'), gray(crowdSvg));
console.log('ok');
