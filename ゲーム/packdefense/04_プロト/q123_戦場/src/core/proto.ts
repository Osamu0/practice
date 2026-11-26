// プロトだけの値（CSV に無いもの）。触りたい数はここに集めてある。
// CSV の値は params.ts が読む。ここはプロトの問いのための切り替えと、仕様が「04 のあと」にしている細部。
import type { Params } from './params.ts';

export type Mode = 'q1' | 'q2' | 'q3';
export type Role = 'sword' | 'archer' | 'shield' | 'spear';
export type SpellId = 'fire1' | 'ice1';
export type PackType = 'novice' | 'iron';

/** 画面のつまみ（設定）。localStorage に入れる */
export interface Knobs {
  mode: Mode;
  ringOffset: number;      // tap.ring.offset：0／40／56／72
  towerY: number;          // field.tower.yRatio：0.48／0.50／0.55
  showBand: boolean;       // 南の「指で打てない帯」と、輪の動ける線を見せる
  introDirs: boolean;      // 第1ウェーブの方向を intro.wave1.dirOrder（東→東西→四方）にする
  spellMode: 'S1a' | 'S1b' | 'S2';  // 呪文の形：S1a 開けた場所で起きる／S1b いちばん魔物の多い所で起きる／S2 置き場
  dropBias: number;        // pack.drop.dirBias：0／0.6／1.0
  hitsMul: number;         // 開けるのに要る回数の倍率：0.5／1／1.5
  forceSpell: boolean;     // 各ショップの最初のパックの2枚めを呪文にする（Q2 で呪文を必ず見るため）
  auto: number;            // 自動化の段（AUTO_LEVELS の番号）
  sound: boolean;
  sameSeed: boolean;       // 毎回同じシードで始める（設定どうしを同じ湧きで比べたいとき）
  pullForward: boolean;    // spawn.pullForward：魔物が0のとき次の組を前倒しで出す
  // --- 2回目に足した（CSV の値は変えず、ここで上書きする。0 は「CSV のまま」）
  budgetBase: number;      // wave.budget.base の上書き（0＝CSV）
  packetBase: number;      // spawn.packet.base の上書き（同時に湧く組の数。0＝CSV）
  slimeHpMul: number;      // monster.slime.hp の倍率
  swarmFrom: number;       // monster.swarm.fromWave の上書き（0＝CSV）
  dropSync: boolean;       // パックの降る時刻を湧きの山（組の湧く時刻）に合わせる
  packRule: 'A' | 'B' | 'C'; // 輪がパックに当たる決め
  startCoin: number;       // coin.start の上書き（0＝CSV）
  priceMul: number;        // パックの値段の倍率（pack.<type>.price にかける）
}

export const KNOB_CHOICES = {
  ringOffset: [0, 40, 56, 72],
  towerY: [0.48, 0.5, 0.55],
  dropBias: [0, 0.6, 1.0],
  hitsMul: [1, 2, 3],
  budgetBase: [0, 24, 28, 32],
  packetBase: [0, 3, 4],
  slimeHpMul: [1, 1.5, 2],
  swarmFrom: [0, 2, 3],
  startCoin: [0, 15, 25],
  priceMul: [1, 0.7, 0.5],
} as const;

/** 序盤の圧のプリセット（Q1）。値は遅い指の自動の目安で決めた（test/calib.ts。README） */
export const PRESSURE: { name: string; v: Pick<Knobs, 'budgetBase' | 'packetBase' | 'slimeHpMul' | 'pullForward'> }[] = [
  { name: 'CSV のまま', v: { budgetBase: 0, packetBase: 0, slimeHpMul: 1, pullForward: true } },
  { name: 'やや強い', v: { budgetBase: 28, packetBase: 3, slimeHpMul: 1.5, pullForward: false } },
  { name: '強い', v: { budgetBase: 32, packetBase: 4, slimeHpMul: 2, pullForward: false } },
];
export const RULE_NAME = { A: 'A 両方に当たる', B: 'B 魔物がいない時だけ', C: 'C 押さえ始めのパックだけ' };
export const SPELL_NAME = { S1a: 'S1a 開けた場所', S1b: 'S1b 魔物の多い所', S2: 'S2 置き場2枚' };

/** CSV の値につまみの上書きをかけた Params（CSV そのものは変えない） */
export function applyOverrides(base: Params, k: Knobs): Params {
  const p: Params = structuredClone(base);
  if (k.budgetBase) p.budgetBase = k.budgetBase;
  if (k.packetBase) p.packetBase = k.packetBase;
  p.monster.slime.hp = base.monster.slime.hp * k.slimeHpMul;
  if (k.swarmFrom) p.monster.swarm.fromWave = k.swarmFrom;
  if (k.startCoin) p.coinStart = k.startCoin;
  p.pack.novice.price = base.pack.novice.price * k.priceMul;
  p.pack.iron.price = base.pack.iron.price * k.priceMul;
  return p;
}

/** CSV と違う値の一覧（記録の行に出す） */
export function overrideList(base: Params, k: Knobs): string[] {
  const o: string[] = [];
  if (k.budgetBase && k.budgetBase !== base.budgetBase) o.push(`wave.budget.base=${k.budgetBase}(CSV ${base.budgetBase})`);
  if (k.packetBase && k.packetBase !== base.packetBase) o.push(`spawn.packet.base=${k.packetBase}(CSV ${base.packetBase})`);
  if (k.slimeHpMul !== 1) o.push(`monster.slime.hp=${base.monster.slime.hp * k.slimeHpMul}(CSV ${base.monster.slime.hp})`);
  if (k.swarmFrom && k.swarmFrom !== base.monster.swarm.fromWave) o.push(`monster.swarm.fromWave=${k.swarmFrom}(CSV ${base.monster.swarm.fromWave})`);
  if (k.pullForward !== base.pullForward) o.push(`spawn.pullForward=${k.pullForward ? '入' : '切'}(CSV ${base.pullForward ? '入' : '切'})`);
  if (k.startCoin && k.startCoin !== base.coinStart) o.push(`coin.start=${k.startCoin}(CSV ${base.coinStart})`);
  if (k.priceMul !== 1) o.push(`pack.price×${k.priceMul}(見習い${base.pack.novice.price * k.priceMul}・鉄壁${base.pack.iron.price * k.priceMul}、CSV ${base.pack.novice.price}・${base.pack.iron.price})`);
  if (k.hitsMul !== 1) o.push(`pack.hitsToOpen×${k.hitsMul}(${base.hitsToOpen.map(h => h * k.hitsMul).join('/')}、CSV ${base.hitsToOpen.join('/')})`);
  if (k.dropSync) o.push('pack.drop.times=湧きの山に合わせる(CSV 0/0.4)');
  if (k.dropBias !== base.dropDirBias) o.push(`pack.drop.dirBias=${k.dropBias}(CSV ${base.dropDirBias})`);
  if (k.ringOffset !== base.ringOffsetDefault) o.push(`tap.ring.offset=${k.ringOffset}(CSV ${base.ringOffsetDefault})`);
  if (k.towerY !== base.towerYRatio) o.push(`field.tower.yRatio=${k.towerY}(CSV ${base.towerYRatio})`);
  return o;
}

/** オーナーが初めて開いたときの既定（q123 2回目、プロデューサーの指定）。CSV のままの組は csvKnobs */
export function defaultKnobs(p: Params): Knobs {
  return { ...csvKnobs(p), ...PRESSURE[1].v, packRule: 'B', hitsMul: 2, dropSync: true, spellMode: 'S1b', swarmFrom: 2, startCoin: 15, priceMul: 0.7 };
}

/** すべて CSV のまま（1回目の既定） */
export function csvKnobs(p: Params): Knobs {
  return {
    mode: 'q1', ringOffset: p.ringOffsetDefault, towerY: p.towerYRatio, showBand: true, introDirs: true,
    spellMode: p.spellModeDefault === 'S1' ? 'S1a' : 'S2', dropBias: p.dropDirBias, hitsMul: 1, forceSpell: true, auto: 0, sound: true, sameSeed: false, pullForward: p.pullForward,
    budgetBase: 0, packetBase: 0, slimeHpMul: 1, swarmFrom: 0, dropSync: false, packRule: 'A', startCoin: 0, priceMul: 1,
  };
}

/** 自動化の段。Q3 の「なし／中／強」に、CSV の上限（tapAuto.ratio.max）を足した。
 *  「強」はデザインの柱の「指と同じ」：威力 1.0 倍・間隔も指と同じ（プロト専用。製品には入れない） */
export function autoLevels(p: Params): { name: string; ratio: number; interval: number }[] {
  return [
    { name: 'なし', ratio: 0, interval: p.autoInterval },
    { name: '中', ratio: p.autoRatio[2] ?? 0.36, interval: p.autoInterval },          // CSV の段3
    { name: '上限', ratio: p.autoRatioMax, interval: p.autoInterval },                // CSV の tapAuto.ratio.max
    { name: '強', ratio: 1, interval: p.tapInterval },                                // 指と同じ（比べるためだけ）
  ];
}

/** パックの顔ぶれ（経済.md 4.1 から。呪文は2種だけに絞った） */
export const POOL: Record<PackType, { heroes: Role[]; spells: { id: SpellId; w: number }[] }> = {
  novice: { heroes: ['sword', 'archer', 'shield'], spells: [{ id: 'fire1', w: 3 }, { id: 'ice1', w: 1 }] },
  iron: { heroes: ['shield', 'spear', 'sword'], spells: [{ id: 'ice1', w: 2 }, { id: 'fire1', w: 1 }] },
};

export const NAME = {
  role: { sword: '剣士', archer: '弓使い', shield: '盾の騎士', spear: '槍兵' } as Record<Role, string>,
  spell: { fire1: '火の玉', ice1: '氷' } as Record<SpellId, string>,
  pack: { novice: '見習いのパック', iron: '鉄壁のパック' } as Record<PackType, string>,
  rarity: ['コモン', 'レア', 'エピック'],
};

/** Q2 は第2ウェーブから始める。第1ウェーブのショップで買ったことにするパック */
export const Q2_START = { wave: 2, packs: ['novice', 'novice'] as PackType[], coins: 0, lastWave: 4 };
/** Q3 は「強化を3つほど買った状態から」（計画 M2） */
export const Q3_START_UPGRADES = { tapDmg: 1, heroDmg: 1, towerHp: 1 };
/** Q3 の目安の長さ（秒）。こえたら知らせるだけ（止めない） */
export const Q3_RUN_TARGET = 600;

/** 魔物の湧く位置の横のぶれ（道の中心から ±） */
export const SPAWN_LATERAL = 50;
/** 当たったときにはじかれる距離（アート 5.4） */
export const KNOCKBACK = 3;
