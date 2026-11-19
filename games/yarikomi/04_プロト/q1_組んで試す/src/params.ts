// Q1 のプロトの数値とつまみ（捨てる前提）。
// 規則の値は 03_仕様/パラメータ表.csv の写し（2026-11-19 時点）。csv を変えたらここも直す。
// 「つまみ」はプロトだけの値。プレイテストで触る。画面の「メニュー → つまみ」からも一部を変えられる。

export const P = {
  'board.size': 7,
  'rule.fall.cellsPerTurn': 7,
  'rule.impact.minFall': 2,
  'rule.impact.wearAdd': 1,
  'leader.weight': 3,
  'leader.hardness': 4,
  'leader.fallDeathHeight': 3,
  'leader.climbHeight': 1,
  'leader.pushWeight': 3,
  'leader.carryTools': 2,
  'bench.size.firstGen': 4,
  'trial.size': 7,
  'trial.startColumn': 1,
  'trial.maxTurns': 20,
  'trial.cliffColumn': 3, // csv の値。プロトでは下の TRIAL_CLIFF_COLUMN を使う
  'trial.gapWidth': 2,
  'playback.stepMs': 300,
  'playback.fastStepMs': 100,
  'playback.gapMs': 120,
} as const;

export type PartId = 'plank' | 'ironBar' | 'spring' | 'ironSpring' | 'stoneWeight' | 'ironWeight' | 'pebble' | 'sandbag';

export interface PartDef {
  id: PartId; name: string; family: string; material: string;
  weight: number; hardness: number; springPower?: number;
  /** つなぎ点のない辺（部品と素材.md 2章の「つなぎ点（案）」） */
  noConn?: 'down';
  /** 何をする部品か（一言。部品を選んだとき説明の帯に出す） */
  does: string;
}

// 部品 8 種（Q1。杭は外した：進行表 2026-11-19）。値は csv の part.<id>.*
export const PARTS: Record<PartId, PartDef> = {
  plank: { id: 'plank', name: '板', family: '骨組み', material: '木', weight: 1, hardness: 2, does: '組の形を作る。軽い。つなげて板の道にする' },
  ironBar: { id: 'ironBar', name: '鉄の棒', family: '骨組み', material: '鉄', weight: 3, hardness: 6, does: '組の形を作る。重いので重りにもなる' },
  spring: { id: 'spring', name: 'ばね', family: 'ばね', material: '真鍮', weight: 1, hardness: 4, springPower: 5, does: '上から物が落ちると縮み、次の手で押す面の向きへ打ち出す' },
  ironSpring: { id: 'ironSpring', name: '強いばね', family: 'ばね', material: '鉄', weight: 3, hardness: 6, springPower: 7, does: 'ばねより強く打ち出す。自分も重い' },
  stoneWeight: { id: 'stoneWeight', name: '石の重り', family: '重り', material: '石', weight: 3, hardness: 5, does: '重さで板の端を押さえる。落とすと当たって傷める' },
  ironWeight: { id: 'ironWeight', name: '鉄の重り', family: '重り', material: '鉄', weight: 5, hardness: 7, does: 'いちばん重い重り' },
  pebble: { id: 'pebble', name: '小石', family: '重り', material: '石', weight: 1, hardness: 3, does: '軽い重り' },
  // 砂袋のつなぎ点は 上・東・西（部品と素材.md）。rules_sim.py は砂袋の下にもつなぐ（写しの簡略）。照合では砂袋の下につながる形を使わない
  sandbag: { id: 'sandbag', name: '砂袋', family: '重り', material: '縄・布', weight: 2, hardness: 2, noConn: 'down', does: '重り。下にはつながらない' },
};

export const PART_ORDER: PartId[] = ['plank', 'ironBar', 'spring', 'ironSpring', 'stoneWeight', 'ironWeight', 'pebble', 'sandbag'];

// ===== つまみ（プロトだけ） =====
export const KNOBS = {
  /** 棚の部品の数 */
  SHELF: { plank: 4, ironBar: 1, spring: 1, ironSpring: 1, stoneWeight: 1, ironWeight: 1, pebble: 2, sandbag: 1 } as Record<PartId, number>,
  /** 作業台の大きさ（一代目：bench.size.firstGen） */
  BENCH_SIZE: P['bench.size.firstGen'] as number,
  /** 作業台の枠（px）。マス＝枠÷大きさ（アート 4.3：288） */
  BENCH_FRAME_PX: 288,
  /** ドラッグ中、部品を指の上に浮かせる量（px）。アート 4.5：56 */
  DRAG_LIFT_PX: 56,
  /** 置く先のマスを「浮かせた部品の下」で決めるか（'ghost'）、「指の下」で決めるか（'finger'） */
  DRAG_TARGET: 'ghost' as 'ghost' | 'finger',
  /** 試し場の地形に「課題の形」（課題の地形だけ。当主・印・敵・仕掛けは入れない）を出すか */
  TRIAL_SHOW_CHALLENGE_TERRAIN: true,
  /** 指がこの距離（px）より動いたらドラッグとみなす（それより短いのはタップ） */
  DRAG_START_PX: 8,
  /** 試し場の崖の、地面のある最後の列。csv は 3。課題の崖の縁（2）に合わせ、置いたとたんに張り出す形にした */
  TRIAL_CLIFF_COLUMN: 2,
  /** 試し場の初めの地形 */
  TRIAL_START_TERRAIN: 'cliff' as 'flat' | 'cliff' | 'gap' | 'challenge',
  /** 課題の条件：印の上で「止まる」（その手で規則に動かされていない）ことまで求めるか。tools/check_challenge.py の説明 */
  GOAL_MUST_STOP: true,
  /** ずれたときの説明の帯に、東と西の重みを丸で出すか（未決：game-design-ux。Q1 で見る） */
  EXPLAIN_SLIDE_WITH_DOTS: true,
  /** 置き間違いとみなす時間：置いてからこの時間内に「ひとつ戻す」「動かす」「外す」をしたら数える（ms）。
   *  置いた先は、ドラッグなら DRAG_TARGET の決まりで枠が出ていたマス、タップなら指の下のマス。枠どおりに置けたものは数えない */
  MISTAKE_WINDOW_MS: 8000,
  /** 1段の再生の時間（ms） */
  STEP_MS: P['playback.stepMs'] as number,
  GAP_MS: P['playback.gapMs'] as number,
};
