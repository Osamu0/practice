// 遊んだ記録を、貼りつけやすい文字にする（プレイテストの材料）。DOM を使わない。
import type { WaveStat } from './game.ts';

const pct = (a: number, tot: number): string => tot > 0 ? Math.round(a / tot * 100) + '%' : '-';
const avg = (a: number[]): string => a.length ? (a.reduce((s, x) => s + x, 0) / a.length).toFixed(1) : '-';

/** 1ウェーブを1行に */
export function waveLine(s: WaveStat): string {
  const tot = s.dmg.finger + s.dmg.auto + s.dmg.hero + s.dmg.spell;
  const misplace = s.whiffPresses + s.spellWhiff;
  return [
    `R${s.run} ${s.mode.toUpperCase()} W${s.wave} ${s.time.toFixed(1)}秒 ${s.result}`,
    `押さえ${s.presses}回(計${s.holdTime.toFixed(1)}秒) 指の当たり${s.hitsMonster} 空振り${s.whiffAttacks}/${s.attacks}`,
    `置き間違い${misplace}(当たらない押さえ${s.whiffPresses}・呪文の空振り${s.spellWhiff}) 呪文${s.spellCasts}回 取りやめ${s.spellCancel} あふれ${s.spellOverflow}`,
    `パック 降った${s.packsDropped} 開けた${s.packsOpened} 持ち越し${s.packsCarried} 開けるまで平均${avg(s.openDelays)}秒[${s.openDelays.map(x => x.toFixed(1)).join(',')}]`,
    `傷の割合 指${pct(s.dmg.finger, tot)} 自動${pct(s.dmg.auto, tot)} 英雄${pct(s.dmg.hero, tot)} 呪文${pct(s.dmg.spell, tot)}`,
    `塔の傷 北${Math.round(s.towerDmg.n)} 東${Math.round(s.towerDmg.e)} 南${Math.round(s.towerDmg.s)} 西${Math.round(s.towerDmg.w)} 残り${s.towerHpEnd} 倒した${s.kills} 英雄${s.heroesEnd}`,
  ].join(' | ');
}

export interface RunLog { run: number; reached: number; prevRecord: number; fame: number; time: number; knobs: string }

export function exportText(head: string[], waves: WaveStat[], runs: RunLog[], note: string): string {
  const out: string[] = ['# 開けて守れ！ プロト q123 の記録 v1', ...head.map(h => '# ' + h)];
  let lastKnobs = '';
  for (const s of waves) {
    if (s.knobs !== lastKnobs) { out.push(`## 設定：${s.knobs}  シード=${s.seed}`); lastKnobs = s.knobs; }
    out.push(waveLine(s));
  }
  if (runs.length) {
    out.push('## Q3 のラン');
    for (const r of runs) out.push(`R${r.run} 第${r.reached}ウェーブまで（前の記録${r.prevRecord}） ${(r.time / 60).toFixed(1)}分 名声+${Math.floor(r.fame)} | ${r.knobs}`);
  }
  // まとめ（全部のウェーブを足したもの）
  if (waves.length) {
    const sum = (f: (s: WaveStat) => number) => waves.reduce((a, s) => a + f(s), 0);
    const tot = sum(s => s.dmg.finger + s.dmg.auto + s.dmg.hero + s.dmg.spell);
    const delays = waves.flatMap(s => s.openDelays);
    out.push(`## まとめ ${waves.length}ウェーブ ${(sum(s => s.time) / 60).toFixed(1)}分 指の当たり${sum(s => s.hitsMonster)} 置き間違い${sum(s => s.whiffPresses + s.spellWhiff)}` +
      ` 開けた${sum(s => s.packsOpened)} 開けるまで平均${avg(delays)}秒 傷 指${pct(sum(s => s.dmg.finger), tot)} 自動${pct(sum(s => s.dmg.auto), tot)}` +
      ` 英雄${pct(sum(s => s.dmg.hero), tot)} 呪文${pct(sum(s => s.dmg.spell), tot)}`);
  }
  if (note.trim()) out.push('## ひとこと', note.trim());
  return out.join('\n');
}
