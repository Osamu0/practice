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
  spellMode: 'S1' | 'S2';  // 呪文の形
  dropBias: number;        // pack.drop.dirBias：0／0.6／1.0
  hitsMul: number;         // 開けるのに要る回数の倍率：0.5／1／1.5
  forceSpell: boolean;     // 各ショップの最初のパックの2枚めを呪文にする（Q2 で呪文を必ず見るため）
  auto: number;            // 自動化の段（AUTO_LEVELS の番号）
  sound: boolean;
  sameSeed: boolean;       // 毎回同じシードで始める（設定どうしを同じ湧きで比べたいとき）
  pullForward: boolean;    // spawn.pullForward：魔物が0のとき次の組を前倒しで出す
}

export const KNOB_CHOICES = {
  ringOffset: [0, 40, 56, 72],
  towerY: [0.48, 0.5, 0.55],
  dropBias: [0, 0.6, 1.0],
  hitsMul: [0.5, 1, 1.5],
} as const;

export function defaultKnobs(p: Params): Knobs {
  return {
    mode: 'q1', ringOffset: p.ringOffsetDefault, towerY: p.towerYRatio, showBand: true, introDirs: true,
    spellMode: p.spellModeDefault, dropBias: p.dropDirBias, hitsMul: 1, forceSpell: true, auto: 0, sound: true, sameSeed: false, pullForward: p.pullForward,
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
