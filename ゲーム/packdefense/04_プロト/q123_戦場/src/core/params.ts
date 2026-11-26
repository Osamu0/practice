// パラメータ表.csv（03_仕様。値の正）を読んで、プロトで使う値にする。
// DOM・時間・Math.random を使わない（Node でテストできる）。
// CSV にない値（プロトだけの値）は proto.ts に置く。

export type Csv = Map<string, string>;

/** 「章,名前,値,…」の先頭3列だけを読む（4列めより後ろの文に「,」があっても崩れない） */
export function parseCsv(text: string): Csv {
  const m: Csv = new Map();
  const lines = text.replace(/^﻿/, '').split(/\r?\n/);
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const a = line.indexOf(','), b = line.indexOf(',', a + 1), c = line.indexOf(',', b + 1);
    if (a < 0 || b < 0) continue;
    const name = line.slice(a + 1, b).trim();
    const val = line.slice(b + 1, c < 0 ? undefined : c).trim();
    m.set(name, val);
  }
  return m;
}

export interface MonsterP { hp: number; speed: number; atk: number; atkInterval: number; coin: number; cost: number; fromWave: number; size: number }
export interface HeroP { dmg: number; interval: number; range: number; projSpeed: number; lineWidth: number; slow: number; slowTime: number }
export interface PackP { price: number; cards: number; rarityWeights: number[]; spellShare: number; firstCard: string }
export interface UpgradeP { costBase: number; costGrowth: number; effect: number }

export interface Params {
  marketGrowth: number;
  towerYRatio: number; towerHp: number; towerHitR: number; towerDanger: number; towerRegen: number; towerDestroyFx: number;
  announce: number; spawnFirst: number; spawnPerWave: number; spawnCap: number; durMax: number; clearFx: number;
  coinBase: number; clearCoinRatio: number; budgetBase: number; budgetPerWave: number; budgetCap: number;
  rushSpeed: number; rushAtk: number; rushDouble: number; rushHitRatio: number; pullForward: boolean; pullGap: number;
  tapInterval: number; tapDamage: number; ringOffsetDefault: number; ringOffsetOptions: number[];
  ringVis: number; ringHit: number; ringTop: number; hiddenR: number; hiddenMax: number;
  autoRatio: number[]; autoRatioMax: number; autoInterval: number; autoRange: number; autoRingR: number; autoMove: number;
  monster: Record<'slime' | 'wolf' | 'swarm', MonsterP>;
  hpGrowthRate: number; attackRange: number; swarmGroup: number; swarmSpread: number;
  dirWeight: { n: number; e: number; s: number; w: number };
  typeWeight: Record<'slime' | 'wolf' | 'swarm', number>;
  packetBase: number; packetPerWaves: number; packetCap: number; groupGap: number; telegraph: number; entryMargin: number; coinFly: number;
  hero: Record<'sword' | 'archer' | 'shield' | 'spear', HeroP>;
  stackMul: number; sameMax: number; fieldMax: number; placeSpread: number; placeMinGap: number; heroSpawnFx: number;
  rarityPower: number[];
  pack: Record<'novice' | 'iron', PackP>;
  hitsToOpen: number[]; dropTimes: number[]; dropTele: number; dropRingMin: number; dropRingMax: number;
  dropDirBias: number; dropMinGap: number; dropAngle: number; openFx: number[];
  fire1: { power: number; radius: number }; ice1: { radius: number; slow: number; duration: number };
  spellPreview: number; slotCount: number; spellModeDefault: 'S1' | 'S2';
  coinStart: number; shopBuyMax: number; firstShopCoinMin: number;
  fameBase: number; fameGrowth: number; fameBeyond: number; fameKillShare: number;
  up: Record<'tapDmg' | 'heroDmg' | 'towerHp' | 'tapAuto', UpgradeP>;
  introDirOrder: string[]; firstSpellWave: number;
  limitMonster: number; limitPack: number; damageTextMax: number; damageTextTime: number;
}

export interface Loaded { p: Params; missing: string[]; used: string[] }

/** CSV から Params を作る。CSV に無い・数でない名前は fallback を使い、missing に入れる（画面に出す） */
export function buildParams(csv: Csv): Loaded {
  const missing: string[] = [], used: string[] = [];
  const raw = (name: string): string | undefined => { used.push(name); const v = csv.get(name); if (v === undefined) missing.push(name); return v; };
  const num = (name: string, fb: number): number => {
    const v = raw(name); if (v === undefined) return fb;
    const n = Number(v); if (Number.isFinite(n)) return n;
    if (!missing.includes(name)) missing.push(name + '（数でない：' + v + '）');
    return fb;
  };
  const list = (name: string, fb: number[]): number[] => {
    const v = raw(name); if (v === undefined) return fb;
    const a = v.split('/').map(Number); return a.every(Number.isFinite) ? a : fb;
  };
  const str = (name: string, fb: string): string => raw(name) ?? fb;
  const mon = (t: string, fb: MonsterP): MonsterP => ({
    hp: num(`monster.${t}.hp`, fb.hp), speed: num(`monster.${t}.speed`, fb.speed), atk: num(`monster.${t}.atk`, fb.atk),
    atkInterval: num(`monster.${t}.atkInterval`, fb.atkInterval), coin: num(`monster.${t}.coin`, fb.coin), cost: num(`monster.${t}.cost`, fb.cost),
    fromWave: num(`monster.${t}.fromWave`, fb.fromWave), size: num(`monster.${t}.size`, fb.size),
  });
  const hero = (r: string, fb: Partial<HeroP>): HeroP => ({
    dmg: num(`hero.base.${r}.dmg`, fb.dmg ?? 10), interval: num(`hero.base.${r}.interval`, fb.interval ?? 1), range: num(`hero.base.${r}.range`, fb.range ?? 100),
    projSpeed: r === 'archer' ? num(`hero.base.${r}.projSpeed`, 420) : 0,
    lineWidth: r === 'spear' ? num(`hero.base.${r}.lineWidth`, 24) : 0,
    slow: r === 'shield' ? num(`hero.base.${r}.slow`, 0.6) : 1,
    slowTime: r === 'shield' ? num(`hero.base.${r}.slowTime`, 1.5) : 0,
  });
  const pack = (t: string, fb: PackP): PackP => {
    let w = list(`pack.${t}.rarityWeights`, fb.rarityWeights);
    // プロトはレア度3段（縦切りと同じ）。レジェンドの重みはエピックに足す（経済.md 4.1）
    if (w.length > 3) w = [w[0], w[1], w.slice(2).reduce((s, x) => s + x, 0)];
    return { price: num(`pack.${t}.price`, fb.price), cards: num('pack.<type>.cards', fb.cards), rarityWeights: w,
      spellShare: num(`pack.${t}.spellShare`, fb.spellShare), firstCard: str(`pack.${t}.firstCard`, fb.firstCard) };
  };
  const up = (id: string, fb: UpgradeP): UpgradeP => ({
    costBase: num(`upgrade.${id}.costBase`, fb.costBase), costGrowth: num(`upgrade.${id}.costGrowth`, fb.costGrowth),
    effect: id === 'tapAuto' ? 0 : num(`upgrade.${id}.effect`, fb.effect),
  });
  const p: Params = {
    marketGrowth: num('econ.marketGrowth', 1.2),
    towerYRatio: num('field.tower.yRatio', 0.5), towerHp: num('tower.hp.base', 100), towerHitR: num('tower.hitRadius', 30),
    towerDanger: num('tower.hp.dangerRatio', 0.3), towerRegen: num('tower.regen.waveEnd', 0.1), towerDestroyFx: num('tower.destroyed.fxTime', 1.5),
    announce: num('wave.announce.time', 1), spawnFirst: num('wave.spawn.first', 30), spawnPerWave: num('wave.spawn.perWave', 3),
    spawnCap: num('wave.spawn.cap', 80), durMax: num('wave.duration.max', 120), clearFx: num('wave.clear.fxTime', 0.8),
    coinBase: num('wave.coin.base', 12), clearCoinRatio: num('wave.clear.coinRatio', 0.2),
    budgetBase: num('wave.budget.base', 16), budgetPerWave: num('wave.budget.perWave', 3), budgetCap: num('wave.budget.cap', 120),
    rushSpeed: num('monster.rush.speedMul', 2), rushAtk: num('monster.rush.atkMul', 2), rushDouble: num('monster.rush.doubleEvery', 10),
    rushHitRatio: num('monster.rush.hitRatio', 0.04), pullForward: str('spawn.pullForward', '入') === '入', pullGap: num('spawn.pullForward.minGap', 0.5),
    tapInterval: num('tap.interval', 0.1), tapDamage: num('tap.damage', 10),
    ringOffsetDefault: num('tap.ring.offset.default', 56), ringOffsetOptions: list('tap.ring.offset.options', [0, 40, 56, 72]),
    ringVis: num('tap.ring.radius.visual', 28), ringHit: num('tap.ring.radius.hit', 34), ringTop: num('tap.ring.topLimit', 104),
    hiddenR: num('tap.hiddenMark.radius', 96), hiddenMax: num('tap.hiddenMark.max', 2),
    autoRatio: list('tapAuto.ratio', [0.2, 0.28, 0.36, 0.43, 0.5]), autoRatioMax: num('tapAuto.ratio.max', 0.5),
    autoInterval: num('tapAuto.interval', 0.2), autoRange: num('tapAuto.range', 200), autoRingR: num('tapAuto.ring.radius', 24),
    autoMove: num('tapAuto.ring.moveSpeed', 600),
    monster: {
      slime: mon('slime', { hp: 60, speed: 36, atk: 4, atkInterval: 1, coin: 1, cost: 1, fromWave: 1, size: 15 }),
      wolf: mon('wolf', { hp: 36, speed: 72, atk: 3, atkInterval: 0.8, coin: 1, cost: 1, fromWave: 3, size: 14 }),
      swarm: mon('swarm', { hp: 20, speed: 46, atk: 1.5, atkInterval: 1, coin: 0.75, cost: 3, fromWave: 4, size: 9 }),
    },
    hpGrowthRate: num('monster.hp.growthRate', 1.45), attackRange: num('monster.attackRange', 6),
    swarmGroup: num('monster.swarm.groupSize', 4), swarmSpread: num('monster.swarm.spread', 18),
    dirWeight: { n: num('spawn.dirWeight.n', 1), e: num('spawn.dirWeight.e', 1), s: num('spawn.dirWeight.s', 0.6), w: num('spawn.dirWeight.w', 1) },
    typeWeight: { slime: num('spawn.typeWeight.slime', 3), wolf: num('spawn.typeWeight.wolf', 2), swarm: num('spawn.typeWeight.swarm', 1.5) },
    packetBase: num('spawn.packet.base', 2), packetPerWaves: num('spawn.packet.perWaves', 4), packetCap: num('spawn.packet.cap', 4),
    groupGap: num('spawn.groupGap', 3), telegraph: num('spawn.telegraph.time', 1), entryMargin: num('spawn.entry.margin', 24), coinFly: num('coin.flyTime', 0.5),
    hero: {
      sword: hero('sword', { dmg: 12, interval: 0.8, range: 64 }), archer: hero('archer', { dmg: 10, interval: 1, range: 170 }),
      shield: hero('shield', { dmg: 4, interval: 1, range: 70 }), spear: hero('spear', { dmg: 10, interval: 1.2, range: 120 }),
    },
    stackMul: num('hero.stack.dmgMul', 1), sameMax: num('hero.sameMax', 2), fieldMax: num('hero.field.max', 32),
    placeSpread: num('hero.place.spread', 40), placeMinGap: num('hero.place.minGap', 36), heroSpawnFx: num('hero.spawn.fxTime', 0.3),
    rarityPower: list('card.rarityPower', [1, 3, 9, 27]),
    pack: {
      novice: pack('novice', { price: 10, cards: 2, rarityWeights: [80, 18, 2], spellShare: 0.3, firstCard: 'hero' }),
      iron: pack('iron', { price: 18, cards: 2, rarityWeights: [66, 26, 8], spellShare: 0.4, firstCard: 'hero' }),
    },
    hitsToOpen: [num('pack.hitsToOpen.common', 4), num('pack.hitsToOpen.rare', 6), num('pack.hitsToOpen.epic', 9)],
    dropTimes: list('pack.drop.times', [0, 0.4]), dropTele: num('pack.drop.telegraph', 0.5),
    dropRingMin: num('pack.drop.ring.min', 70), dropRingMax: num('pack.drop.ring.max', 150), dropDirBias: num('pack.drop.dirBias', 0.6),
    dropMinGap: num('pack.drop.minGap', 40), dropAngle: num('pack.drop.angleSpread', 35),
    openFx: [num('fx.open.time.common', 0.3), num('fx.open.time.rare', 0.6), num('fx.open.time.epic', 0.9)],
    fire1: { power: num('spell.fire1.power', 900), radius: num('spell.fire1.radius', 60) },
    ice1: { radius: num('spell.ice1.radius', 80), slow: num('spell.ice1.slow', 0.5), duration: num('spell.ice1.duration', 4) },
    spellPreview: num('spell.preview.time', 0.2), slotCount: num('spell.slot.count', 2),
    spellModeDefault: str('proto.spellMode', 'S2') === 'S1' ? 'S1' : 'S2',
    coinStart: num('coin.start', 6), shopBuyMax: num('shop.pack.buyMax', 3), firstShopCoinMin: num('intro.firstShop.coinMin', 10),
    fameBase: num('fame.perWaveBase', 1), fameGrowth: num('fame.growth', 2.1), fameBeyond: num('fame.beyondRecordMul', 2), fameKillShare: num('fame.killShare', 0.2),
    up: {
      tapDmg: up('tapDmg', { costBase: 5, costGrowth: 1.5, effect: 1.1 }), heroDmg: up('heroDmg', { costBase: 5, costGrowth: 1.5, effect: 1.1 }),
      towerHp: up('towerHp', { costBase: 6, costGrowth: 1.5, effect: 1.08 }), tapAuto: up('tapAuto', { costBase: 30, costGrowth: 6, effect: 0 }),
    },
    introDirOrder: str('intro.wave1.dirOrder', 'e/w/n/s').split('/'), firstSpellWave: num('intro.firstSpellWave', 4),
    limitMonster: num('limit.monster.max', 250), limitPack: num('limit.pack.max', 6),
    damageTextMax: num('limit.damageText.max', 12), damageTextTime: num('ui.damageText.time', 0.6),
  };
  return { p, missing, used };
}

/** 相場 econ.market(n) */
export const market = (p: Params, n: number): number => p.marketGrowth ** (n - 1);
export const budget = (p: Params, n: number): number => Math.min(p.budgetCap, p.budgetBase + p.budgetPerWave * (n - 1));
export const spawnDuration = (p: Params, n: number): number => Math.min(p.spawnCap, p.spawnFirst + p.spawnPerWave * (n - 1));
export const hpGrowth = (p: Params, n: number): number => p.hpGrowthRate ** (n - 1);
export const famePerWave = (p: Params, n: number): number => p.fameBase * p.fameGrowth ** (n - 1);
