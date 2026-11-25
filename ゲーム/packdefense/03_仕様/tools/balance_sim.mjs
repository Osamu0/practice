// 数値設計のシミュレーション（game-spec-balance、2026-11-25）
// 縦切り（M3）の中身（魔物4・英雄6・呪文3・レア度3・強化6項目、パックは見習いと鉄壁）で、
// 戦場を2次元で動かし（魔物の位置・英雄の射程・指の輪・パック・呪文）、ラン→強化→ランをくり返す。
// 値はすべて 03_仕様/パラメータ表.csv から読む（この中に数値の既定は持たない。表とずれないため）。
//
// 使い方：node balance_sim.mjs [時間=2] [シード=1] [--skill good|normal|weak|none] [--strategy cheap|tap|hero|tower|spell]
//                              [--pack best|novice|saveIron] [--drill] [--headStart] [--tapNoMarket] [--noshop] [--quit k]
//                              [--runs] [--waves] [--set 名前=値 ...]
//   --headStart  早出（あれば。MVP の必須ではない）を強化に足す。既定は早出なし
//   --runs  ランごとの行を出す   --waves  ウェーブごとの行を出す（最初のランだけ）
//   --set   表の値を上書き（例 --set monster.hp.growthRate=1.3）
// 確かめた環境：Node 22（2026-11-25）。乱数はシードつき。
//
// 置き方（仮の割り切り。04 のプロトで確かめること）
// - 指：反応 react 秒ごとに狙いを決め直し、輪は speed px/秒で動く。いちばん早く塔に着く魔物を狙い、
//   どの魔物も packSafe 秒より遠ければパックを開けに行く。押さえっぱなし（離さない）
//   当てる率 hit：輪を動く魔物に重ねきれない・指を離す・見落とす、をまとめた割合（腕ごと 0.85／0.7／0.55）
// - 呪文は案S2（置き場2枠）。火は3体以上まとまったら・氷は塔の近くに3体以上・回復は塔が55%未満
// - ショップ：傷んでいたら修理、上限までいちばん高い買えるパック（経済の素朴な買い手）。--drill で余りを訓練に
// - 生き延びたコイン ＝ wave.clear.coinRatio × このウェーブで倒した魔物のコインの合計（第2版）
// - パックの1枚めは pack.<type>.firstCard、2枚め以降は spellShare。開いていないレア度は開いている1つ下の段へ
// - 重なる相手：同じ英雄がいれば開けた場所にいちばん近い同じ英雄、いなければ hero.power がいちばん小さい英雄（同じなら塔から遠い）
// - 強化画面：自動化を先に、あとは戦い方（--strategy）の項目だけ、安い順に買えるだけ

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const csvPath = path.join(here, '..', 'パラメータ表.csv');

// ---- CSV を読む ----
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
  return rows;
}
const rows = parseCSV(fs.readFileSync(csvPath, 'utf8'));
const head = rows[0]; const iName = head.indexOf('名前'), iVal = head.indexOf('値');
const T = new Map();
for (const r of rows.slice(1)) if (r[iName]) T.set(r[iName], r[iVal]);

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) if (args[i] === '--set') { const [k, v] = args[++i].split('='); if (!T.has(k)) throw new Error('表にない名前: ' + k); T.set(k, v); }
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const pos = args.filter((a, i) => !a.startsWith('--') && !['--set', '--skill', '--strategy', '--pack', '--quit'].includes(args[i - 1]));

const num = k => { if (!T.has(k)) throw new Error('表にない名前: ' + k); const v = Number(T.get(k)); if (!Number.isFinite(v)) throw new Error(`数でない: ${k}=${T.get(k)}`); return v; };
const list = k => { if (!T.has(k)) throw new Error('表にない名前: ' + k); return T.get(k).split('/').map(Number); };

// ---- 乱数 ----
function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const hours = Number(pos[0] ?? 2), seed = Number(pos[1] ?? 1);
const rand = rng(seed);
const pick = (arr, w) => { let s = 0; for (const x of w) s += x; let r = rand() * s; for (let i = 0; i < arr.length; i++) { r -= w[i]; if (r < 0) return arr[i]; } return arr[arr.length - 1]; };

const SKILL = {
  good: { react: 0.2, speed: 1500, packSafe: 2.0, hit: 0.85 },
  normal: { react: 0.35, speed: 1000, packSafe: 2.5, hit: 0.7 },
  weak: { react: 0.55, speed: 700, packSafe: 3.0, hit: 0.55 },
  none: null, // 指を使わない（パックは開かない。自動化だけ）
};
const skillName = opt('--skill', 'normal'); const skill = SKILL[skillName];
const strategy = opt('--strategy', 'cheap');
const useDrill = args.includes('--drill');
const noShop = args.includes('--noshop');
const packRule = opt('--pack', 'best'); // best：いちばん高い買えるもの／novice：見習いだけ／saveIron：鉄壁が並んだら鉄壁だけ（ためて買う） // パックを買わない（指だけで何ウェーブもつか）
const showRuns = args.includes('--runs'), showWaves = args.includes('--waves');

// ---- 縦切りの中身（仮の顔ぶれ。個々の英雄・呪文の表は combat が 04 のあとに作る） ----
const MONSTERS = ['slime', 'wolf', 'swarm', 'skeleton'];
const TYPE_W = { slime: 3, wolf: 2, swarm: 1.5, skeleton: 1.5 }; // 湧きの型の重み（表の spawn.typeWeight.<type>）
for (const m of MONSTERS) TYPE_W[m] = num(`spawn.typeWeight.${m}`);
const HEROES = {
  sword1: { role: 'sword', rarity: 0 }, archer1: { role: 'archer', rarity: 0 }, shield1: { role: 'shield', rarity: 0 },
  archer2: { role: 'archer', rarity: 1 }, spear1: { role: 'spear', rarity: 1 }, sword2: { role: 'sword', rarity: 2 },
};
const SPELLS = { fire1: { rarity: 0 }, heal1: { rarity: 0 }, ice1: { rarity: 1 } };
const PACKS = {
  novice: { price: num('pack.novice.price'), w: list('pack.novice.rarityWeights'), spell: num('pack.novice.spellShare'), first: T.get('pack.novice.firstCard'),
    heroes: ['sword1', 'archer1', 'shield1', 'archer2', 'sword2'], spells: ['fire1', 'heal1', 'ice1'] },
  iron: { price: num('pack.iron.price'), w: list('pack.iron.rarityWeights'), spell: num('pack.iron.spellShare'), first: T.get('pack.iron.firstCard'),
    heroes: ['sword1', 'shield1', 'spear1', 'sword2'], spells: ['heal1', 'ice1'] },
};
const IRON_RECORD = 8; // 鉄壁は記録 第8で並ぶ（縦切りは packType の強化がないので、記録だけで並べる）
const RP = list('card.rarityPower');
const HB = role => ({
  dmg: num(`hero.base.${role}.dmg`), interval: num(`hero.base.${role}.interval`), range: num(`hero.base.${role}.range`),
  proj: T.has(`hero.base.${role}.projSpeed`) ? num(`hero.base.${role}.projSpeed`) : 0,
});

// ---- 強化（縦切りの6項目） ----
const MVP_HEAD = args.includes('--headStart');
const tapNoMarket = args.includes('--tapNoMarket'); // タップ攻撃を相場に乗せない（比べるため）
const quitK = Number(opt('--quit', '0')); // 記録の k ウェーブ手前でランをやめる（稼ぎの近道がないかを見る） // MVP の「早出」（経済の headStart）を足して試す
const UPG = ['tapDmg', 'tapAuto', 'heroDmg', 'spellPower', 'towerHp', 'packHits', ...(MVP_HEAD ? ['headStart'] : [])].map(id => ({
  id, base: num(`upgrade.${id}.costBase`), growth: num(`upgrade.${id}.costGrowth`),
  max: T.get(`upgrade.${id}.maxLevel`) === 'なし' ? Infinity : num(`upgrade.${id}.maxLevel`),
}));
const lv = Object.fromEntries(UPG.map(u => [u.id, 0]));
const cost = u => u.base * Math.pow(u.growth, lv[u.id]);
const autoRatio = list('tapAuto.ratio'), packHitsMul = [1, ...list('upgrade.packHits.effect')];

// ---- 式 ----
const mg = num('econ.marketGrowth');
const market = n => Math.pow(mg, n - 1);
const spawnDur = n => Math.min(num('wave.spawn.cap'), num('wave.spawn.first') + num('wave.spawn.perWave') * (n - 1));
const budget = n => Math.min(num('wave.budget.cap'), num('wave.budget.base') + num('wave.budget.perWave') * (n - 1));
const hpGrowth = n => Math.pow(num('monster.hp.growthRate'), n - 1);
const famePerWave = n => num('fame.perWaveBase') * Math.pow(num('fame.growth'), n - 1);

// ---- 画面（塔を原点、基準の画面 390×844、塔の高さ yRatio） ----
const HALF_W = 195, TOWER_Y = 844 * num('field.tower.yRatio');
const TOP = -TOWER_Y, BOT = 844 - TOWER_Y;
const RING_TOP = num('tap.ring.topLimit') - TOWER_Y, RING_BOT = (844 - 34 - 0) - TOWER_Y - num('tap.ring.offset.default') + 0; // 指は下の端の手前まで
const DIRS = { n: [0, -1], e: [1, 0], s: [0, 1], w: [-1, 0] };
const DIRW = { n: num('spawn.dirWeight.n'), e: num('spawn.dirWeight.e'), s: num('spawn.dirWeight.s'), w: num('spawn.dirWeight.w') };
const margin = num('spawn.entry.margin');
const startDist = d => (d === 'e' || d === 'w') ? HALF_W + margin : (d === 'n' ? TOWER_Y + margin : (844 - TOWER_Y) + margin);
const onScreen = m => Math.abs(m.x) <= HALF_W && m.y >= TOP && m.y <= BOT;
const DT = 1 / 30;
// 急ぐ：wave.duration.max をこえたら、速さ × monster.rush.speedMul、攻撃の速さ × monster.rush.atkMul、さらに monster.rush.doubleEvery 秒ごとに攻撃の速さ2倍
const rushAtk = wt => wt <= num('wave.duration.max') ? 1 : num('monster.rush.atkMul') * Math.pow(2, Math.floor((wt - num('wave.duration.max')) / num('monster.rush.doubleEvery')));

let record = 0, fame = 0, totalTime = 0, runNo = 0, metSpell = false, epicOpen = false;
const global = { over: 0, waves: 0, maxMonsters: 0, maxProj: 0, maxWaveTime: 0, maxNum: 0, maxWaveTimeAt: 0 };
const note = v => { if (v > global.maxNum) global.maxNum = v; return v; };

function runOnce() {
  runNo++;
  const first = runNo === 1;
  const tapMul = Math.pow(num('upgrade.tapDmg.effect'), lv.tapDmg);
  const heroMul = Math.pow(num('upgrade.heroDmg.effect'), lv.heroDmg);
  const spellMul = Math.pow(num('upgrade.spellPower.effect'), lv.spellPower);
  const towerMax = num('tower.hp.base') * Math.pow(num('upgrade.towerHp.effect'), lv.towerHp);
  const healPow = num('spell.heal1.power') + 0.02 * lv.spellPower > 0.5 ? 0.5 : num('spell.heal1.power') + 0.02 * lv.spellPower;
  let tower = towerMax, coins = num('coin.start');
  const heroes = []; let carried = [], bought = []; const slots = [];
  let drills = 0, runFame = 0, time = 0, w;
  const dmgBy = { finger: 0, auto: 0, hero: 0, spell: 0 };
  const waveLog = [];
  let packSeq = 0;

  const makePack = (type, wShop) => {
    const P = PACKS[type]; const cards = [];
    const nCards = num('pack.<type>.cards');
    for (let c = 0; c < nCards; c++) {
      // 1枚めは pack.<type>.firstCard（hero／spell）、2枚め以降の1枚ずつが pack.<type>.spellShare の割合で呪文
      let isSpell = c === 0 ? P.first === 'spell' : rand() < P.spell;
      if (first && wShop === num('intro.firstSpellWave') - 1 && c === 1) isSpell = true; // はじめのランの第4ウェーブに呪文を必ず1枚
      let r = pick([0, 1, 2], P.w.slice(0, 3));
      if (first && wShop < num('unlock.rare.fromWave') - 1) { r = 0; isSpell = false; } // はじめのパックはコモンの英雄だけ
      // 開いていないレア度は、開いている1つ下の段に落とす（引き直さない）
      const open = rr => rr === 0 || (rr === 1 ? !(first && wShop < num('unlock.rare.fromWave') - 1) : rr === 2 ? epicOpen : false);
      while (!open(r)) r--;
      const ids = isSpell ? P.spells : P.heroes; const tbl = isSpell ? SPELLS : HEROES;
      let cand = [];
      for (let rr = r; rr >= 0 && !cand.length; rr--) cand = ids.filter(id => tbl[id].rarity === rr);
      const id = cand[Math.floor(rand() * cand.length)];
      cards.push({ kind: isSpell ? 'spell' : 'hero', id, rarity: tbl[id].rarity, power: market(wShop) });
    }
    const rar = Math.max(...cards.map(c => c.rarity));
    const hits = Math.max(1, Math.ceil([num('pack.hitsToOpen.common'), num('pack.hitsToOpen.rare'), num('pack.hitsToOpen.epic')][rar] * packHitsMul[lv.packHits]));
    packSeq++;
    return { type, cards, rarity: rar, hits };
  };

  const heroCountDir = () => { const c = { n: 0, e: 0, s: 0, w: 0 }; for (const h of heroes) c[h.dir]++; return c; };
  const dirOf = (x, y) => Math.abs(x) * (844 / 390) > Math.abs(y) ? (x > 0 ? 'e' : 'w') : (y > 0 ? 's' : 'n');
  const placeHero = (card, x, y) => {
    const same = heroes.filter(h => h.id === card.id);
    if (same.length < num('hero.sameMax') && heroes.length < num('hero.field.max')) {
      // 並べる：パックの位置から spread の内、ほかの英雄から minGap 以上
      let px = x, py = y;
      for (let t = 0; t < 12; t++) {
        const ok = heroes.every(h => Math.hypot(h.x - px, h.y - py) >= num('hero.place.minGap'));
        if (ok) break;
        const a = rand() * Math.PI * 2, r = num('hero.place.spread') * (0.5 + 0.5 * rand());
        px = x + Math.cos(a) * r; py = y + Math.sin(a) * r;
      }
      const hb = HB(HEROES[card.id].role);
      heroes.push({ id: card.id, role: HEROES[card.id].role, rarity: card.rarity, x: px, y: py, dir: dirOf(px, py), power: card.power, cd: num('hero.spawn.fxTime'), ...hb });
    } else if (same.length) {
      same.sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y))[0].power += card.power * num('hero.stack.dmgMul');
    } else {
      // 同じ英雄がいない（戦場がいっぱい）：力（hero.power）がいちばん小さい英雄に重なる。同じなら塔からいちばん遠い英雄
      heroes.slice().sort((a, b) => a.power - b.power || Math.hypot(b.x, b.y) - Math.hypot(a.x, a.y))[0].power += card.power * num('hero.stack.dmgMul');
    }
  };

  const startW = MVP_HEAD ? Math.max(1, Math.floor(record * 0.1 * lv.headStart)) : 1;
  for (w = 1; ; w++) {
    const skipped = w < startW; // 早出でとばすウェーブ：戦いは同じに計算するが、時間と名声は数えない
    const m = market(w), hpg = hpGrowth(w), B = budget(w), dur = spawnDur(w);
    // 湧きの予定
    const types = MONSTERS.filter(t => num(`monster.${t}.fromWave`) <= w);
    const events = []; let left = B;
    const cheapest = Math.min(...types.map(t => num(`monster.${t}.cost`)));
    while (left >= cheapest - 1e-9) {
      const ok = types.filter(t => num(`monster.${t}.cost`) <= left + 1e-9);
      const t = pick(ok, ok.map(x => TYPE_W[x]));
      left -= num(`monster.${t}.cost`);
      events.push({ type: t });
    }
    // 湧きを「いっぺんに来る組」にまとめる（組の中はちがう方向）
    const pk = Math.min(num('spawn.packet.cap'), num('spawn.packet.base') + Math.floor((w - 1) / num('spawn.packet.perWaves')));
    const nPk = Math.ceil(events.length / pk);
    events.forEach((e, i) => {
      const g = Math.floor(i / pk);
      e.t = dur * (g + 0.5) / nPk;
      if (first && w === 1) { const f = i / events.length; e.dir = f < 0.25 ? 'e' : f < 0.5 ? (i % 2 ? 'e' : 'w') : pick(['n', 'e', 's', 'w'], [1, 1, 1, 1]); }
      else {
        const used = events.slice(g * pk, i).map(x => x.dir);
        const ds = ['n', 'e', 's', 'w'].filter(d => !used.includes(d));
        e.dir = pick(ds, ds.map(d => DIRW[d]));
      }
    });
    // パックの降る予定
    const drops = [];
    carried.forEach(p => drops.push({ p, at: 0 }));
    const half = Math.ceil(bought.length / 2);
    bought.forEach((p, i) => drops.push({ p, at: i < half ? 0 : list('pack.drop.times')[1] * dur }));
    carried = []; bought = [];
    const ground = []; // { p, x, y, tele, hits }
    const monsters = []; const projs = [];
    let ei = 0, clock = 0, wt = 0, lastSpawn = -9, maxMon = 0, leakDmg = 0;
    const finger = { x: 0, y: -60, tgt: null, react: 0, cd: 0 };
    const auto = { x: 0, y: 0, cd: 0 };
    let spellCd = 0;
    let killCoin = 0; // このウェーブで倒した魔物のコインの合計（生き延びたコインの元）
    const killed = (mo) => {
      mo.dead = true;
      const c = num('wave.coin.base') * m * num(`monster.${mo.type}.coin`) / B; coins += c; killCoin += c; // 湧きを全部倒すと wave.coin.base × 相場
      if (w >= startW) runFame += famePerWave(w) * num('fame.killShare') * num(`monster.${mo.type}.cost`) / (mo.type === 'swarm' ? num('monster.swarm.groupSize') : 1) / B * (w > record ? num('fame.beyondRecordMul') : 1);
    };
    const hit = (mo, d, src) => { if (mo.dead) return; const real = Math.min(mo.hp, d); mo.hp -= d; dmgBy[src] += real; if (mo.hp <= 1e-9) killed(mo); };
    const eta = mo => Math.max(0, mo.dist - mo.stop) / (mo.speed * mo.slowMul * (wt > num('wave.duration.max') ? num('monster.rush.speedMul') : 1));
    const castSpell = (card, cx, cy) => {
      if (card.id === 'heal1') { tower = Math.min(towerMax, tower + towerMax * healPow); return; }
      if (card.id === 'fire1') { const d = num('spell.fire1.power') * card.power * spellMul; for (const mo of monsters) if (!mo.dead && Math.hypot(mo.x - cx, mo.y - cy) <= num('spell.fire1.radius')) hit(mo, d, 'spell'); return; }
      if (card.id === 'ice1') { for (const mo of monsters) if (!mo.dead && Math.hypot(mo.x - cx, mo.y - cy) <= num('spell.ice1.radius')) { mo.slowMul = Math.min(mo.slowMul, num('spell.ice1.slow')); mo.slowT = Math.max(mo.slowT, num('spell.ice1.duration')); } }
    };
    const openPack = g => {
      for (const c of g.p.cards) {
        if (c.kind === 'hero') placeHero(c, g.x, g.y);
        else { metSpell = true; if (slots.length >= num('spell.slot.count')) castSpell(slots.shift(), 0, 0); slots.push(c); }
      }
    };

    for (;;) {
      wt += DT;
      // 前倒し：戦場に魔物がいなければ、次の湧きを待たない
      const alive = monsters.length;
      if (T.get('spawn.pullForward') === '入' && alive === 0 && ei < events.length && events[ei].t > clock && wt - lastSpawn >= num('spawn.pullForward.minGap')) clock = events[ei].t;
      clock += DT;
      while (ei < events.length && events[ei].t <= clock && monsters.length < num('limit.monster.max')) {
        const e = events[ei++]; lastSpawn = wt;
        const [dx, dy] = DIRS[e.dir]; const sd = startDist(e.dir);
        const n = e.type === 'swarm' ? num('monster.swarm.groupSize') : 1;
        const lat = (rand() - 0.5) * 16;
        for (let k = 0; k < n; k++) {
          const sp = e.type === 'swarm' ? num('monster.swarm.spread') : 0;
          const a = rand() * Math.PI * 2, r = rand() * sp;
          const along = sd + Math.cos(a) * r, side = lat + Math.sin(a) * r;
          monsters.push({ type: e.type, dist: along, side, dx, dy, x: dx * along - dy * side, y: dy * along + dx * side,
            hp: num(`monster.${e.type}.hp`) * hpg, speed: num(`monster.${e.type}.speed`), size: num(`monster.${e.type}.size`),
            stop: num('tower.hitRadius') + num(`monster.${e.type}.size`) + num('monster.attackRange'), atkCd: 0, slowMul: 1, slowT: 0 });
          note(num(`monster.${e.type}.hp`) * hpg);
        }
      }
      // パックが降る
      for (const d of drops) if (!d.done && d.at <= clock) {
        d.done = true;
        const cnt = heroCountDir(); const mx = Math.max(...Object.values(cnt));
        const dir = pick(['n', 'e', 's', 'w'], ['n', 'e', 's', 'w'].map(k => 1 + num('pack.drop.dirBias') * (mx - cnt[k])));
        let x = 0, y = 0;
        for (let t = 0; t < 20; t++) {
          const base = Math.atan2(DIRS[dir][1], DIRS[dir][0]);
          const a = base + (rand() * 2 - 1) * num('pack.drop.angleSpread') * Math.PI / 180;
          const r = num('pack.drop.ring.min') + rand() * (num('pack.drop.ring.max') - num('pack.drop.ring.min'));
          x = Math.cos(a) * r; y = Math.sin(a) * r;
          x = Math.max(-HALF_W + 20, Math.min(HALF_W - 20, x));
          const gap = t < 10 ? num('pack.drop.minGap') : num('pack.drop.minGap') / 2;
          if (ground.every(g => Math.hypot(g.x - x, g.y - y) >= gap) && heroes.every(h => Math.hypot(h.x - x, h.y - y) >= gap)) break;
        }
        ground.push({ p: d.p, x, y, tele: num('pack.drop.telegraph'), hits: 0 });
      }
      // 魔物が進む・塔を攻める
      for (const mo of monsters) {
        if (mo.slowT > 0) { mo.slowT -= DT; if (mo.slowT <= 0) mo.slowMul = 1; }
        const sp = mo.speed * mo.slowMul * (wt > num('wave.duration.max') ? num('monster.rush.speedMul') : 1);
        if (mo.dist > mo.stop) { mo.dist = Math.max(mo.stop, mo.dist - sp * DT); mo.x = mo.dx * mo.dist - mo.dy * mo.side; mo.y = mo.dy * mo.dist + mo.dx * mo.side; }
        else { mo.atkCd -= DT * rushAtk(wt); if (mo.atkCd <= 0) { mo.atkCd += num(`monster.${mo.type}.atkInterval`); const a = wt > num('wave.duration.max') ? Math.max(num(`monster.${mo.type}.atk`) * num('monster.atk.growth'), towerMax * num('monster.rush.hitRatio')) : num(`monster.${mo.type}.atk`) * num('monster.atk.growth'); tower -= a; leakDmg += a; } }
      }
      for (const g of ground) if (g.tele > 0) g.tele -= DT;
      // 指
      const tapD = num('tap.damage') * (tapNoMarket ? 1 : m) * tapMul;
      if (skill) {
        finger.react -= DT;
        if (finger.react <= 0 || (finger.tgt && finger.tgt.dead)) {
          finger.react = skill.react;
          let best = null, be = Infinity;
          for (const mo of monsters) if (!mo.dead && onScreen(mo) && mo.y >= RING_TOP - 34 && mo.y <= RING_BOT + 34) { const e = eta(mo); if (e < be) { be = e; best = mo; } }
          const packs = ground.filter(g => g.tele <= 0);
          if (packs.length && (!best || be > skill.packSafe)) {
            packs.sort((a, b) => b.p.rarity - a.p.rarity || Math.hypot(a.x - finger.x, a.y - finger.y) - Math.hypot(b.x - finger.x, b.y - finger.y));
            finger.tgt = packs[0];
          } else finger.tgt = best;
        }
        if (finger.tgt) {
          const tx = Math.max(-HALF_W, Math.min(HALF_W, finger.tgt.x)), ty = Math.max(RING_TOP, Math.min(RING_BOT, finger.tgt.y));
          const dx = tx - finger.x, dy = ty - finger.y, d = Math.hypot(dx, dy), st = skill.speed * DT;
          if (d <= st) { finger.x = tx; finger.y = ty; } else { finger.x += dx / d * st; finger.y += dy / d * st; }
        }
        finger.cd -= DT;
        while (finger.cd <= 0) {
          finger.cd += num('tap.interval');
          const R = num('tap.ring.radius.hit');
          for (const mo of monsters) if (!mo.dead && onScreen(mo) && Math.hypot(mo.x - finger.x, mo.y - finger.y) <= R) hit(mo, tapD * skill.hit, 'finger');
          for (const g of ground) if (g.tele <= 0 && !g.opened && Math.hypot(g.x - finger.x, g.y - finger.y) <= R) { g.hits++; if (g.hits >= g.p.hits) { g.opened = true; openPack(g); } }
        }
      }
      // 自動化
      if (lv.tapAuto > 0) {
        let best = null, bd = Infinity;
        for (const mo of monsters) if (!mo.dead && onScreen(mo)) { const d = Math.hypot(mo.x, mo.y); if (d <= num('tapAuto.range') && d < bd) { bd = d; best = mo; } }
        if (best) { const dx = best.x - auto.x, dy = best.y - auto.y, d = Math.hypot(dx, dy), st = num('tapAuto.ring.moveSpeed') * DT; if (d <= st) { auto.x = best.x; auto.y = best.y; } else { auto.x += dx / d * st; auto.y += dy / d * st; } }
        auto.cd -= DT;
        if (auto.cd <= 0) { auto.cd += num('tapAuto.interval'); if (best) for (const mo of monsters) if (!mo.dead && Math.hypot(mo.x - auto.x, mo.y - auto.y) <= num('tapAuto.ring.radius')) hit(mo, tapD * autoRatio[lv.tapAuto - 1], 'auto'); }
      }
      // 英雄
      for (const h of heroes) {
        h.cd -= DT; if (h.cd > 0) continue;
        let tgt = null, td = Infinity;
        for (const mo of monsters) if (!mo.dead && onScreen(mo) && Math.hypot(mo.x - h.x, mo.y - h.y) <= h.range) { const d = Math.hypot(mo.x, mo.y); if (d < td) { td = d; tgt = mo; } }
        if (!tgt) { h.cd = 0; continue; }
        h.cd += h.interval;
        const d = h.dmg * RP[h.rarity] * h.power * heroMul * (1 + num('shop.item.drill.effect') * drills);
        if (h.role === 'sword') hit(tgt, d, 'hero');
        else if (h.role === 'archer') projs.push({ tgt, d, t: Math.hypot(tgt.x - h.x, tgt.y - h.y) / h.proj });
        else if (h.role === 'shield') { for (const mo of monsters) if (!mo.dead && onScreen(mo) && Math.hypot(mo.x - h.x, mo.y - h.y) <= h.range) { hit(mo, d, 'hero'); mo.slowMul = Math.min(mo.slowMul, num('hero.base.shield.slow')); mo.slowT = Math.max(mo.slowT, num('hero.base.shield.slowTime')); } }
        else if (h.role === 'spear') {
          const vx = tgt.x - h.x, vy = tgt.y - h.y, L = Math.hypot(vx, vy) || 1, ux = vx / L, uy = vy / L, hw = num('hero.base.spear.lineWidth') / 2;
          for (const mo of monsters) if (!mo.dead && onScreen(mo)) { const px = mo.x - h.x, py = mo.y - h.y, along = px * ux + py * uy, perp = Math.abs(px * uy - py * ux); if (along >= 0 && along <= h.range && perp <= hw + mo.size * 0.5) hit(mo, d, 'hero'); }
        }
      }
      for (const p of projs) { p.t -= DT; if (p.t <= 0) { p.done = true; if (!p.tgt.dead) hit(p.tgt, p.d, 'hero'); } }
      for (let i = projs.length - 1; i >= 0; i--) if (projs[i].done) projs.splice(i, 1);
      if (projs.length > global.maxProj) global.maxProj = projs.length;
      // 呪文（案S2 の置き場）
      spellCd -= DT;
      if (slots.length && spellCd <= 0 && skill) {
        spellCd = 0.5;
        for (let si = 0; si < slots.length; si++) {
          const c = slots[si]; let used = false;
          if (c.id === 'heal1' && tower < towerMax * 0.55) { castSpell(c, 0, 0); used = true; }
          else if (c.id !== 'heal1') {
            const R = c.id === 'fire1' ? num('spell.fire1.radius') : num('spell.ice1.radius');
            let best = null, bc = 0;
            for (const mo of monsters) if (!mo.dead && onScreen(mo) && (c.id === 'fire1' || eta(mo) < 4)) { let k = 0; for (const o of monsters) if (!o.dead && Math.hypot(o.x - mo.x, o.y - mo.y) <= R) k++; if (k > bc) { bc = k; best = mo; } }
            if (best && (bc >= 3 || (c.id === 'fire1' && eta(best) < 1.5))) { castSpell(c, best.x, best.y); used = true; }
          }
          if (used) { slots.splice(si, 1); break; }
        }
      }
      for (let i = monsters.length - 1; i >= 0; i--) if (monsters[i].dead) monsters.splice(i, 1);
      for (let i = ground.length - 1; i >= 0; i--) if (ground[i].opened) ground.splice(i, 1);
      if (monsters.length > maxMon) maxMon = monsters.length;
      if (tower <= 0) break;
      if (ei >= events.length && monsters.length === 0) break;
      if (wt > 600) { tower = 0; break; } // 止まったウェーブの安全弁（起きたら不具合）
    }
    if (maxMon > global.maxMonsters) global.maxMonsters = maxMon;
    if (wt > global.maxWaveTime) { global.maxWaveTime = wt; global.maxWaveTimeAt = w; }
    if (!skipped) time += wt; global.waves++; if (wt > num('wave.duration.max')) global.over++;
    // 開けていないパックは持ち越し（ウェーブを生き延びたとき）
    for (const g of ground) carried.push(g.p);
    for (const d of drops) if (!d.done) carried.push(d.p);
    const waveRow = { w, wt, tower: Math.max(0, tower) / towerMax, heroes: heroes.length, leak: leakDmg, maxMon, coins: 0, fame: 0 };
    if (tower <= 0) { waveLog.push(waveRow); break; }
    // 生き延びた
    coins += num('wave.clear.coinRatio') * killCoin; // wave.clear.coin ＝ coinRatio × このウェーブで倒した魔物のコインの合計
    if (!skipped) runFame += famePerWave(w) * (w > record ? num('fame.beyondRecordMul') : 1);
    tower = Math.min(towerMax, tower + towerMax * num('tower.regen.waveEnd'));
    if (!skipped) time += num('wave.clear.fxTime') + (first ? 15 : 8); // ショップ（はじめのランは見て選ぶ。あとは「前と同じものを買う」）
    if (first && w === 1) coins = Math.max(coins, num('intro.firstShop.coinMin'));
    // ショップ
    if (tower < towerMax * 0.6 && coins >= num('shop.item.repair.price') * m) { coins -= num('shop.item.repair.price') * m; tower = Math.min(towerMax, tower + towerMax * num('shop.item.repair.effect')); }
    const can = Math.min(num('shop.pack.buyMax'), num('limit.pack.max') - carried.length);
    const avail = ['iron', 'novice'].filter(t => t === 'novice' || ((packRule === 'best' || packRule === 'saveIron') && Math.max(record, w) >= IRON_RECORD));
    for (let s = 0; s < (noShop ? 0 : can); s++) {
      const ironOk = avail.includes('iron');
      const t = packRule === 'saveIron' && Math.max(record, w) >= IRON_RECORD ? (coins >= PACKS.iron.price * m ? 'iron' : null) : avail.find(t => coins >= PACKS[t].price * m);
      if (!t) break;
      coins -= PACKS[t].price * m; bought.push(makePack(t, w));
    }
    if (useDrill) for (;;) { const dp = num('shop.item.drill.price') * m * Math.pow(num('shop.item.drill.priceGrowth'), drills); if (coins < dp) break; coins -= dp; drills++; }
    waveRow.coins = coins; waveRow.fame = runFame;
    waveLog.push(waveRow);
    if (quitK > 0 && record > quitK && w >= record - quitK) { w++; break; } // 記録の手前でランをやめる（このウェーブは生き延びた）
  }
  const reached = w - 1;
  const beat = reached > record;
  record = Math.max(record, reached);
  if (record >= num('unlock.epic.record')) epicOpen = true;
  fame = note(fame + runFame);
  time += num('tower.destroyed.fxTime') + 4 + (first ? 40 : 20); // 結果と強化画面
  totalTime += time;
  // 強化画面
  const want = { cheap: ['tapDmg', 'heroDmg', 'spellPower', 'towerHp', 'packHits'], tap: ['tapDmg'], hero: ['heroDmg'], tower: ['towerHp'], spell: ['spellPower'] }[strategy];
  let bought2 = 0;
  for (;;) {
    let c = UPG.filter(u => lv[u.id] < u.max && cost(u) <= fame && (u.id !== 'spellPower' || metSpell));
    const autoU = c.find(u => u.id === 'tapAuto') ?? c.find(u => u.id === 'headStart');
    const u = autoU ?? c.filter(u => want.includes(u.id)).sort((a, b) => cost(a) - cost(b))[0];
    if (!u) break;
    fame -= cost(u); lv[u.id]++; bought2++;
  }
  return { run: runNo, reached, beat, min: time / 60, runFame, dmgBy, waveLog, upg: { ...lv }, bought2, heroes: heroes.length };
}

const fmt = n => n < 1e4 ? (n < 10 ? n.toFixed(1) : n.toFixed(0)) : n.toExponential(2);
console.log(`シード ${seed}、${hours}時間ぶん、指 ${skillName}、強化 ${strategy}${useDrill ? '、訓練あり' : ''}`);
const runs = [];
const marks = [0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50, 75, 100, 150, 200].filter(h => h <= hours); let mi = 0;
while (totalTime < hours * 3600) {
  const r = runOnce(); runs.push(r);
  if (showWaves && r.run === 1) for (const x of r.waveLog) console.log(`  第${x.w}ウェーブ ${x.wt.toFixed(0)}秒 塔${(x.tower * 100).toFixed(0)}% 受けた傷${x.leak.toFixed(0)} 英雄${x.heroes} 画面の魔物の最多${x.maxMon} コイン残り${x.coins.toFixed(0)} 名声${x.fame.toFixed(1)}`);
  if (showRuns) { const d = r.dmgBy, s = d.finger + d.auto + d.hero + d.spell || 1; console.log(`ラン${r.run} 第${r.reached}${r.beat ? '★' : ''} ${r.min.toFixed(1)}分 名声+${fmt(r.runFame)} 指${(100 * d.finger / s).toFixed(0)}% 自動${(100 * d.auto / s).toFixed(0)}% 英雄${(100 * d.hero / s).toFixed(0)}% 呪文${(100 * d.spell / s).toFixed(0)}% 英雄${r.heroes}人 強化 ${JSON.stringify(r.upg)}`); }
  while (mi < marks.length && totalTime >= marks[mi] * 3600) { console.log(`${String(marks[mi]).padStart(4)}時間：ラン${runNo}回、記録 第${record}、直近 ${r.min.toFixed(1)}分`); mi++; }
}
const firsts = runs.slice(0, 6).map(r => `第${r.reached}(${r.min.toFixed(1)}分)`).join(' → ');
let stuck = 0, maxStuck = 0, best = 0; for (const r of runs) { if (r.reached > best) { best = r.reached; stuck = 0; } else { stuck++; maxStuck = Math.max(maxStuck, stuck); } }
const tot = runs.reduce((a, r) => { for (const k in r.dmgBy) a[k] += r.dmgBy[k]; return a; }, { finger: 0, auto: 0, hero: 0, spell: 0 });
const ts = tot.finger + tot.auto + tot.hero + tot.spell;
console.log('---');
console.log(`最初のラン：${firsts}`);
console.log(`ラン ${runs.length} 回、記録 第${record}、記録が伸びないランの最長の連続 ${maxStuck} 回`);
console.log(`与えた傷の割合（全部のラン）：指 ${(100 * tot.finger / ts).toFixed(0)}%、自動 ${(100 * tot.auto / ts).toFixed(0)}%、英雄 ${(100 * tot.hero / ts).toFixed(0)}%、呪文 ${(100 * tot.spell / ts).toFixed(0)}%`);
console.log(`画面の魔物の最多 ${global.maxMonsters}（上限 ${num('limit.monster.max')}）、弾の最多 ${global.maxProj}（上限 ${num('limit.projectile.max')}）、いちばん長いウェーブ ${global.maxWaveTime.toFixed(0)}秒（第${global.maxWaveTimeAt}、上限の目安 ${num('wave.duration.max')}）、目安をこえたウェーブ ${global.over}／${global.waves}`);
console.log(`いちばん大きい数 ${global.maxNum.toExponential(2)}（1e300 未満：${global.maxNum < 1e300 ? 'はい' : 'いいえ'}）`);
console.log(`強化 ${JSON.stringify(lv)}、名声の残り ${fmt(fame)}`);
