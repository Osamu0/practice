// パラメータ表.md の「2.1 式から出る表」と「9章 パラメータ表」を、パラメータ表.csv から作り直す（game-spec-balance、2026-11-25）
// 使い方：node balance_table.mjs        （md の <!-- curves:begin/end --> と <!-- table:begin/end --> の間を書きかえる）
//         node balance_table.mjs --check（書きかえずに、md が CSV と食い違っていないかだけを見る）
// 値の正は CSV。md の表は手で直さない。
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const csvPath = path.join(here, '..', 'パラメータ表.csv');
const mdPath = path.join(here, '..', 'パラメータ表.md');

function parseCSV(text) {
  const rows = []; let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n') { row.push(f); rows.push(row); row = []; f = ''; }
    else if (c !== '\r') f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  return rows.filter(r => r.length > 1);
}

const CH = ['全体', '戦場・塔・ウェーブ', 'タップ攻撃・自動化', '魔物', '英雄', 'パック・レア度', '呪文カード', 'ショップ・コイン', '名声・記録・強化', '解放・はじめの流れ', '宝石（擬似課金。値は経済）', '画面・表記・上限・音・保存'];
const rows = parseCSV(fs.readFileSync(csvPath, 'utf8'));
const head = rows[0];
const names = new Set();
for (const r of rows.slice(1)) {
  if (r.length !== head.length) throw new Error(`列の数が違う（${r.length}／${head.length}）：${r[1]}`);
  if (names.has(r[1])) throw new Error('名前が2回：' + r[1]);
  names.add(r[1]);
}
const esc = s => s.replace(/\|/g, '\\|');
let out = '';
for (let c = 0; c < CH.length; c++) {
  const rs = rows.slice(1).filter(r => Number(r[0]) === c);
  if (!rs.length) continue;
  if (out) out += '\n';
  out += `### 9.${c}. ${CH[c]}\n| ${head.slice(1).join(' | ')} |\n|${head.slice(1).map(() => '---').join('|')}|\n`;
  for (const r of rs) out += `| \`${r[1]}\` | ${r.slice(2).map(esc).join(' | ')} |\n`;
}
const curves = execFileSync('node', [path.join(here, 'curves.mjs')], { encoding: 'utf8' });

let md = fs.readFileSync(mdPath, 'utf8');
const put = (tag, body) => {
  const re = new RegExp(`(<!-- ${tag}:begin -->\\n)[\\s\\S]*?(<!-- ${tag}:end -->)`);
  if (!re.test(md)) throw new Error('md に印がない：' + tag);
  md = md.replace(re, (_, a, b) => a + body.replace(/\n*$/, '\n') + b);
};
const before = md;
put('table', out);
put('curves', curves);
if (process.argv.includes('--check')) {
  console.log(before === md ? 'md の表は CSV と同じ' : 'md の表が CSV と食い違っている（node balance_table.mjs で作り直す）');
  process.exit(before === md ? 0 : 1);
}
fs.writeFileSync(mdPath, md);
console.log(`書きかえた：9章 ${rows.length - 1} 行、2.1 の表`);
