// 経済のたたき台のシミュレーション（game-design-economy、2026-11-25）
// 目的：コイン（ラン中）と名声（持ち越し）の入り口と出口が、何時間遊んでも
//   1) 同じウェーブの壁で何ランも止まらない
//   2) 一気に吹き飛ばない（ラン1回で記録が何倍にもならない）
//   3) どの数も 1e300 未満
//   4) 登り直しの時間がランを重ねても増え続けない
// を満たすかを、ざっくり見る。戦いの中身（英雄の役、呪文、魔物の種類、指の腕）は
// 「力の比 R = 守りの力 / 魔物の圧」の1つの数にまとめている。値はすべて仮（パラメータ表は game-spec-balance）。
// 名前は仮。03_仕様/パラメータの名前.md ができたら合わせる。
//
// 使い方：node econ_sim.mjs [遊ぶ時間（時間）=30] [シード=1] [--runs] [--set 名前=値 ...]
//   --runs でランごとの行を全部出す。--set で P の数を上書きして試す（例：--set fame.growth=1.8）
// 確かめた環境：Node 22（2026-11-25）。乱数はシードつき（同じシードなら同じ結果）

const P = {
  // ウェーブの相場（コインの入り・パックの値段・英雄の強さの伸び）と魔物の伸び
  'econ.marketGrowth': 1.2,     // 1ウェーブごとの相場の伸び（コイン・値段・英雄の強さ）
  'wave.pressureGrowth': 1.5,   // 1ウェーブごとの魔物の圧の伸び（耐久×数）。相場より速いので、ランはいつか終わる
  'wave.pressureBase': 1.0,
  // タップ攻撃
  'tap.base': 1.3,               // 第1ウェーブで指だけの力の比が 1.3 になる
  'tap.followsMarket': true,     // タップ攻撃も相場に乗る（後半も指の仕事が残る。combat の決め待ち）
  // コイン
  'coin.perWaveBase': 12,        // 第1ウェーブで落ちるコイン（倒しきったとき）
  'coin.waveClearBonus': 0.2,    // 生き延びたときの上乗せ（落ちたコインの 20%）
  // パック（種類ごとのプールの違いは、この骨では「レア度の割合と値段」だけで見る）
  packs: [
    { id: 'pack.novice', name: '見習いのパック', price: 10, rates: [80, 18, 2, 0], unlockWave: 1 },
    { id: 'pack.iron',   name: '鉄壁のパック',   price: 24, rates: [66, 26, 7, 1], unlockWave: 8 },
    { id: 'pack.wind',   name: '疾風のパック',   price: 24, rates: [66, 26, 7, 1], unlockWave: 15 },
    { id: 'pack.arcane', name: '秘術のパック',   price: 24, rates: [66, 26, 7, 1], unlockWave: 25 },
    { id: 'pack.royal',  name: '王家のパック',   price: 60, rates: [30, 42, 21, 7], unlockWave: 40 },
  ],
  'card.rarityPower': [1, 3, 9, 27],  // コモン・レア・エピック・レジェンドの強さの倍率
  'card.unitPower': 0.12,             // 倍率1の英雄1枚の力（第1ウェーブの相場で）
  'pack.cardsBase': 2,                // 1パックのカードの枚数
  'pack.maxPerWaveBase': 3,           // 1ウェーブに降るパックの上限
  // 塔
  'tower.hp': 100,
  'tower.damagePerDeficit': 130,      // 塔の傷 = これ × (1/R − 1)（R が 1 を下回るほど急に重くなる）
  // ショップの各種の買えるもの（コイン）
  'shop.repairPrice': 8,              // 塔の修理（最大耐久の 40% を戻す）×相場
  'shop.repairAmount': 0.4,
  'shop.drillPrice': 18,              // 英雄の訓練（このランの英雄の力 +10%）×相場×1.5^回数
  'shop.drillGrowth': 1.5,
  'shop.drillEffect': 0.10,
  'shop.sealPrice': 14,               // 封の格上げ（次に降るパック1つの最低レア度を1段上げる）×相場
  // 名声
  'fame.perWaveBase': 0.05,              // 第1ウェーブを生き延びたときの名声
  'fame.growth': 2.35,                // 1ウェーブごとの名声の伸び（壁の強さ k を決める大事な数。下の「k の見積もり」）
  'fame.beyondRecordMult': 2,         // 前の記録より先のウェーブは名声 2倍
  // 時間
  // 1ウェーブの長さ = min(time.waveMax, time.waveFirst + time.wavePerWave × (w-1)) × [0.35〜1]（力の比が大きいほど早く終わる）
  'time.waveFirst': 35, 'time.wavePerWave': 10, 'time.waveMax': 120,
  'time.shop': 12,                    // 1回のショップ（前と同じものを買う を使う前提）
  'time.fastForwardR': 8,             // 力の比がこれ以上のウェーブは早送り（登り直しを短くする案。writer・balance の決め待ち）
  'time.fastWave': 8,                 // 早送りのウェーブの長さ（秒）
  'time.fastShop': 2,                 // 早送り中のショップ（前と同じものを買う が自動で働く）
  'time.upgradeScreen': 30,           // ランの合間の強化画面
};

// 強化画面（名声）。値段 = base × growth^レベル
const UPG = [
  { id: 'upg.heroPower', name: '英雄の力 ×1.1',      base: 5,   growth: 1.5, max: Infinity },
  { id: 'upg.tapPower',  name: 'タップ攻撃 ×1.1',    base: 4,   growth: 1.5, max: Infinity },
  { id: 'upg.towerHp',   name: '塔の耐久 +10%',      base: 6,   growth: 1.5, max: Infinity },
  { id: 'upg.coinGain',  name: 'コインの稼ぎ ×1.1',  base: 8,   growth: 1.5, max: 15 },
  { id: 'upg.autoTap',   name: 'タップ攻撃の自動化', base: 25,  growth: 3.0, max: 5 },   // 1段ごとに 指の 12%（上限 60%）
  { id: 'upg.packCards', name: 'パックの枚数 +1',    base: 40,  growth: 12,  max: 3 },
  { id: 'upg.packSlots', name: '降るパックの上限 +1', base: 60,  growth: 15,  max: 2 },
  { id: 'upg.headStart', name: '早出（記録の 10% 先から出発）', base: 150, growth: 6, max: 5 },
];

function rng(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// --set 名前=値 で P の数を上書きできる（調整の試し用）
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) if (args[i] === '--set') { const [k, v] = args[++i].split('='); if (!(k in P)) throw new Error('知らない名前: ' + k); P[k] = Number(v); }
const pos = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--set');
const hours = Number(pos[0] ?? 30);
const seed = Number(pos[1] ?? 1);
const showRuns = process.argv.includes('--runs');
const rand = rng(seed);

const lv = Object.fromEntries(UPG.map(u => [u.id, 0]));
const cost = u => u.base * Math.pow(u.growth, lv[u.id]);
let fame = 0, record = 0, totalTime = 0, maxNum = 0, run = 0;
const note = v => { if (v > maxNum) maxNum = v; return v; };
const unlocked = w => P.packs.filter(p => p.unlockWave <= Math.max(record, w));

function drawRarity(rates, minR) {
  let x = rand() * 100, r = 0;
  for (; r < 3; r++) { if (x < rates[r]) break; x -= rates[r]; }
  return Math.max(r, minR);
}

function doRun() {
  run++;
  const heroMult = Math.pow(1.1, lv['upg.heroPower']);
  const tapMult = Math.pow(1.1, lv['upg.tapPower']) * (1 + 0.12 * lv['upg.autoTap'] * 0.5); // 自動は指の半分の場面で効く、と見る
  const towerMax = P['tower.hp'] * (1 + 0.1 * lv['upg.towerHp']);
  const coinMult = Math.pow(1.1, lv['upg.coinGain']);
  const cards = P['pack.cardsBase'] + lv['upg.packCards'];
  const slots = P['pack.maxPerWaveBase'] + lv['upg.packSlots'];
  const start = Math.max(1, Math.floor(record * 0.1 * lv['upg.headStart']));

  let tower = towerMax, coins = 0, army = 0, drills = 0, w = 0, time = 0, fameRun = 0, coinLost = 0;
  const bought = {}; let repairs = 0, seals = 0, coinSpent = 0, coinIn = 0;
  let nFast = 0, nSlow = 0;
  let pending = []; // 次のウェーブに降るパック（買ったときに中身を決める）

  for (w = 1; ; w++) {
    const market = Math.pow(P['econ.marketGrowth'], w - 1);
    const pressure = note(P['wave.pressureBase'] * Math.pow(P['wave.pressureGrowth'], w - 1));
    // 降ってきたパックを開ける（この骨では全部開けたと見る）
    for (const pk of pending) army += pk;
    pending = [];
    const tap = P['tap.base'] * tapMult * (P['tap.followsMarket'] ? market : 1);
    const R = (tap + army * heroMult * (1 + P['shop.drillEffect'] * drills)) / pressure;
    const skipped = w < start; // 早出：時間をかけずに通る（名声なし、コインはふつうに入って自動で買う）
    const fast = R >= P['time.fastForwardR']; if (!skipped) { if (fast) nFast++; else nSlow++; }
    if (!skipped) time += fast ? P['time.fastWave'] : Math.min(P['time.waveMax'], P['time.waveFirst'] + P['time.wavePerWave'] * (w - 1)) * Math.max(0.35, Math.min(1, 1.5 / R));
    tower -= Math.max(0, 1 / Math.max(R, 1e-9) - 1) * P['tower.damagePerDeficit'];
    const killFrac = Math.min(1, R);
    let gain = P['coin.perWaveBase'] * market * coinMult * killFrac;
    if (tower <= 0) { coins += gain; coinIn += gain; break; }
    gain *= 1 + P['coin.waveClearBonus'];
    coins = note(coins + gain); coinIn += gain;
    if (!skipped) {
      const f = P['fame.perWaveBase'] * Math.pow(P['fame.growth'], w - 1) * (w > record ? P['fame.beyondRecordMult'] : 1);
      fameRun += f;
    }
    // ショップ（素朴な買い方：傷んでいたら修理 → 上限まで、いちばん「1枠あたりの力」が大きいパックを買えるだけ → 余りで訓練）
    if (!skipped) time += fast ? P['time.fastShop'] : P['time.shop'];
    if (tower < towerMax * 0.6) {
      const pr = P['shop.repairPrice'] * market;
      if (coins >= pr) { coins -= pr; coinSpent += pr; tower = Math.min(towerMax, tower + towerMax * P['shop.repairAmount']); repairs++; }
    }
    const avail = unlocked(w).slice().sort((a, b) => b.price - a.price);
    for (let s = 0; s < slots; s++) {
      const pk = avail.find(p => coins >= p.price * market);
      if (!pk) break;
      const pr = pk.price * market; coins -= pr; coinSpent += pr;
      bought[pk.name] = (bought[pk.name] ?? 0) + 1;
      let minR = 0;
      const sp = P['shop.sealPrice'] * market;
      if (pk.id !== 'pack.novice' && coins >= sp * 3) { coins -= sp; coinSpent += sp; minR = 1; seals++; }
      let pow = 0;
      for (let c = 0; c < cards; c++) pow += P['card.rarityPower'][drawRarity(pk.rates, c === 0 ? minR : 0)];
      pending.push(note(pow * P['card.unitPower'] * market));
    }
    // 余ったコインは訓練へ（パックの上限で使い切れないコインの出口）
    for (;;) {
      const dp = P['shop.drillPrice'] * market * Math.pow(P['shop.drillGrowth'], drills);
      if (coins < dp) break;
      coins -= dp; coinSpent += dp; drills++;
    }
  }
  coinLost = coins;
  const reached = w - 1; // 生き延びたウェーブ
  const beat = reached > record;
  record = Math.max(record, reached);
  fame = note(fame + fameRun);
  time += P['time.upgradeScreen'];
  totalTime += time;
  // 強化画面：自動化を先に、あとは安いものから買えるだけ
  const spent = []; let buying = true;
  while (buying) {
    buying = false;
    const cands = UPG.filter(u => lv[u.id] < u.max && cost(u) <= fame);
    if (!cands.length) break;
    const auto = cands.find(u => u.id === 'upg.autoTap' && lv[u.id] === 0);
    const u = auto ?? cands.sort((a, b) => cost(a) - cost(b))[0];
    fame -= cost(u); lv[u.id]++; spent.push(u.id); buying = true;
  }
  return { nFast, nSlow, run, reached, start, beat, time, fameRun, coinIn, coinSpent, coinLost, bought, repairs, seals, drills, spent: spent.length };
}

const fmt = n => n < 1e4 ? n.toFixed(n < 10 ? 1 : 0) : n.toExponential(2);
const rows = [];
const milestones = [0.25, 0.5, 1, 2, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50].filter(h => h <= hours);
let mi = 0, stuck = 0, maxStuck = 0, lastRecord = 0;
console.log(`シード ${seed}、${hours} 時間ぶん`);
while (totalTime < hours * 3600) {
  const r = doRun();
  if (r.reached > lastRecord) { stuck = 0; lastRecord = r.reached; } else { stuck++; maxStuck = Math.max(maxStuck, stuck); }
  rows.push(r);
  if (showRuns) console.log(`[早${r.nFast}/ふつう${r.nSlow}] ラン${r.run} 出発${r.start} 到達${r.reached}${r.beat ? '★' : ''} ${(r.time / 60).toFixed(1)}分 名声+${fmt(r.fameRun)} コイン入${fmt(r.coinIn)} 使${fmt(r.coinSpent)} 消${fmt(r.coinLost)} 修理${r.repairs} 訓練${r.drills} 封${r.seals} 強化${r.spent} ${JSON.stringify(r.bought)}`);
  while (mi < milestones.length && totalTime >= milestones[mi] * 3600) {
    console.log(`${String(milestones[mi]).padStart(5)}時間：ラン${String(r.run).padStart(4)}回、記録 第${record}ウェーブ、直近ランの長さ ${(r.time / 60).toFixed(1)}分、名声の手持ち ${fmt(fame)}、強化 ${JSON.stringify(lv)}`);
    mi++;
  }
}
// k の見積もり：名声が1ウェーブで何倍になるか → 強化が何段買えるか → 何ウェーブ先へ行けるか。
// k が 1 をこえると記録が吹き飛び、1 より小さいと、ある所から伸びが「ランの回数の対数」になる（壁）。
// 英雄とタップ攻撃は足し算で効くので、2本で ほぼ1本ぶん。コインの稼ぎは、パックの上限に当たると訓練を通してしか効かない
{
  const lvPerWave = Math.log(P['fame.growth']) / Math.log(1.5);
  const wavesPerLv = Math.log(1.1) / Math.log(P['wave.pressureGrowth'] / P['econ.marketGrowth']);
  console.log(`k の見積もり（英雄＋タップの1本ぶんだけ）≈ ${(lvPerWave * wavesPerLv).toFixed(2)}、コインの稼ぎも効くなら ≈ ${(lvPerWave * wavesPerLv * 1.5).toFixed(2)}（1 未満なら、いつか伸びが対数になる。1 をこえると吹き飛ぶ）`);
}
const last = rows.slice(-10);
console.log('---');
console.log(`ラン ${rows.length} 回、記録 第${record}ウェーブ、いちばん大きい数 ${maxNum.toExponential(2)}（1e300 未満：${maxNum < 1e300 ? 'はい' : 'いいえ'}）`);
console.log(`記録が伸びなかったランの最長の連続 ${maxStuck} 回`);
console.log(`最後の10ランの平均の長さ ${(last.reduce((a, r) => a + r.time, 0) / last.length / 60).toFixed(1)}分`);
const firstFive = rows.slice(0, 5).map(r => `第${r.reached}(${(r.time / 60).toFixed(1)}分)`).join(' → ');
console.log(`最初の5ラン：${firstFive}`);
const jumps = rows.slice(1).map((r, i) => r.reached / Math.max(1, rows[i].reached));
console.log(`ラン1回で記録がいちばん伸びた倍率 ${Math.max(...jumps).toFixed(2)} 倍`);
