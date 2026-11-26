// 自動の指（計算の芯だけで動かす）。人の目安ではない。強さの比べの物差し。
//  fast：毎歩、塔にいちばん近い魔物へ瞬時に輪を合わせる（1回目の自動の指）
//  slow：見直しは 0.4秒ごと（倒した直後は 0.25秒待つ）、指の速さは 900px/秒まで。初めての人の手の遅さのまね
import type { Game } from '../src/core/game.ts';

export interface Bot { tick(g: Game): void }

function pickTarget(g: Game, packs: boolean): { x: number; y: number; isPack: boolean } | null {
  let best: { x: number; y: number } | null = null, bd = 1e9;
  for (const m of g.monsters) { if (!g.visible(m)) continue; const d = Math.hypot(m.x - g.towerX, m.y - g.towerY); if (d < bd) { bd = d; best = m; } }
  const pk = packs ? g.packs.find(q => q.tele <= 0) : undefined;
  if (pk && (!best || bd > 130)) return { x: pk.x, y: pk.y, isPack: true };
  return best ? { x: best.x, y: best.y, isPack: false } : null;
}

export function fastBot(packs = true): Bot {
  return { tick(g) {
    const t = pickTarget(g, packs);
    if (t) { const y = Math.min(g.H, t.y + g.k.ringOffset); if (!g.fingerOn) g.pointerDown(t.x, y); else g.pointerMove(t.x, y); }
    else if (g.fingerOn) g.pointerUp();
  } };
}

export function slowBot(packs = true, opt = { react: 0.4, afterKill: 0.25, speed: 900 }): Bot {
  let fx = 195, fy = 600, next = 0, aim: { x: number; y: number; isPack: boolean } | null = null, kills = 0;
  return { tick(g) {
    const t = g.t / 60;
    if (g.stat.kills !== kills) { kills = g.stat.kills; next = Math.min(next, t + opt.afterKill); }
    if (t >= next) {
      next = t + opt.react;
      const tg = pickTarget(g, packs);
      aim = tg ? { x: tg.x, y: Math.min(g.H, tg.y + g.k.ringOffset), isPack: tg.isPack } : null;
      // 押さえ直し：狙いが変わったらいったん離して押し直す（パックの決め C の押さえ始めが効くように）
      if (tg && g.fingerOn && Math.hypot(aim!.x - fx, aim!.y - fy) > 60) g.pointerUp();
    }
    if (!aim) { if (g.fingerOn) g.pointerUp(); return; }
    const dx = aim.x - fx, dy = aim.y - fy, d = Math.hypot(dx, dy), mv = opt.speed / 60;
    if (d > mv) { fx += dx / d * mv; fy += dy / d * mv; } else { fx = aim.x; fy = aim.y; }
    // パックへは指を浮かせて動かし、着いてから押す（人がパックを「押しに行く」形）
    if (aim.isPack && Math.hypot(aim.x - fx, aim.y - fy) > 4) { if (g.fingerOn) g.pointerUp(); return; }
    if (!g.fingerOn) g.pointerDown(fx, fy); else g.pointerMove(fx, fy);
  } };
}

/** いまのウェーブが終わるまで（または steps 歩）回す。ショップでは買えるだけ買う（見習い） */
export function runWave(g: Game, bot: Bot | null, maxSteps = 60 * 200): void {
  for (let i = 0; i < maxSteps && g.scene === 'fight'; i++) { bot?.tick(g); g.step(); }
  while (g.scene === 'cleared' || g.scene === 'destroyed') g.step();
}
