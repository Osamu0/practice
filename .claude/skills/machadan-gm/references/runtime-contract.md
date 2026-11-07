# 通常進行の契約（4.13.3）

## 物語外発言とシステム表示

コア§17を全場面に適用する。GMからの進捗説明・感想・労い・手順の予告・継続の促しは出さない。
通常の死への物語外の嘲笑、場面外からのリリスの掛け声・茶々・実況も付けない。
地の文と場面内の登場人物の台詞は残し、HUD・選択肢・ダイス内訳・精算／収支・クエストカードは全量維持する。
必要な手続きは今の操作だけを短いシステム文で示し、本人発信のルール・状況・仕様の質問には答える。
GMの声の例外は既存のお仕置き、一意に復旧できない進行不能な異常通知、本当の停止など安全・同意の確認だけ。
お仕置きの5トリガー、ペナルティ、嘲笑は維持する。例外を追加しない。

## 正本と作業ファイル

本体は`machadan_spade/muse版/`、現在状態は`saves/*.yaml`にある。
正本の所在と優先順位は`運用/正本レジストリ.yaml`、場面の読込は`運用/ルーティング表.yaml`に従う。
`state/runtime/<campaign-id>/`のcontext、receipt、候補は作業用であり正本ではない。
保存用の完全データと、MUSEが読む表示用の抜粋を混同しない。

## 場面と段階

最も具体的な主場面を--sceneに一つ指定し、追加は--include-sceneで渡す。

| scene | 用途 |
|---|---|
| start／resume／turn | 初回質問・導入／保存位置から再開／通常会話や移動 |
| event／quest | 移動途中・散策・小イベント／依頼の作成・受注・進行・報酬 |
| combat／dungeon | 戦闘／入場・探索・階層進行・導線・帰還 |
| shop／magic／skills | 売買・治療・装備／魔法／技能・強化・転職 |
| generation／enterprise | 人物候補生成／店舗・工房・研究・商品開発 |
| style／chekyun／status／debt／manage | 場面専用文体／画像用テキスト／状態確認／借金／管理 |

段階は--phase autoが既定。今回の意図が明確ならcreate（作成）、offer（提示）、
advance（進行）、settle（精算）、probe（発生前の確認）を指定する。
生成済みの依頼を進める時は確定した事実・利害・制約・達成条件・報酬契約を毎回読む。
プレイヤーの解決方法は自由であり、例示されたmain/altや予定の結末へ戻さない。

現在地は--location、敵は--enemy、品物は--item、技能・話題は--topic、登場者は
--character <CHAR_ID>で絞る。旧--termも明示検索として使える。
場所種別が分かる時は--location-kind town／road／dungeonを渡す。未設定の店や人物名だけで停止しない。
街路や建物内の行動では、現在の場所と必要な移動先を具体名で指定する。
例えば`--location ぬれねずみ亭`で宿だけの構造と親町の短い案内を読み、
建物から建物へ移るなら移動先も`--location`で追加する。場所の資料を読むだけでは移動は成立しない。
セーブの`world_state.location`を具体名で保ち、使う場合は`place_id`・`room_id`・`sub_location`も
実際の現在地へ同時に合わせる。移動しなかった時は現在地を変えない。
部屋同士は扉・廊下・階段のつながりに沿って描き、同じ「保健室」「裏口」を他施設と取り違えない。
特定の室を扱う時は`--location ラビラビ村 --room 中央広場`のように所属する場所と室を組み合わせる。
出来事の途中で次の施設が舞台になったら、本文と判定の前に同じ確定セーブから対象の場所資料を追加取得する。
同じプレイヤー入力と確定済みの出目を引き継ぎ、資料を読むためだけに入力を求め直したり振り直したりしない。
`世界/舞台資料集.md`は人間向けの全体閲覧用。通常ターンで全巻を読み足さず、
contextに投影された当該場所の資料を末尾まで読む。窓や秘密区画の存在だけで侵入・発見・解錠に成功しない。
破損・改装・封鎖や新しい施設は`campaign_lore`へ保存し、再訪で初期配置へ戻さない。
場所の変化には`place_id`と、分かる場合は`room_id`を含め、古い記録でも再訪時に拾えるようにする。

地方世界の通常読込は、Dayから導く日付と対象都市の短い暮らしの案内だけ。
必要な話題に応じて`--world-topic`を追加し、その節を末尾まで読む。複数必要なら繰り返す。

| 今回扱うこと | 指定 |
|---|---|
| 暦、季節、祭り、週の行事 | `--world-topic calendar` |
| ノワールから近郊への道と移動 | `--world-topic travel` |
| 商人ギルド、近郊からの荷物や商売の相談 | `--world-topic trade` |
| 市政、統治者、争議や届出 | `--world-topic governance` |
| 都市の暮らし、成人の恋愛・社交文化 | `--world-topic culture` |
| 非火持ちの死亡、遺族、葬送 | `--world-topic death` |

既定の都市はノワールのみ。近郊の村や学園は、現在地に応じた元の資料を使う。
制度の説明と統治者本人の登場は別。本人と会話する時はgovernance.character_idを
`--character`へ追加して人格正本を読む。街を歩くたび全統治者の人格を読む必要はない。
新しい商業支部は冒険者のランクをリセットせず、能力の実の初C級支給を重複させない。
暦の月末・年末でも取立ての絶対Dayをリセットしない。祭りの告知と変更はキャンペーンへ記録する。

移動の計画は次で読む。これは候補移動の計算だけであり、現在地・金・日付は変わらない。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  travel-plan --save <確定セーブ> --from <出発地> --to <目的地> --mode foot
```

馬車を実際に用意した場合は`--mode cart`を使う。経路の端点は所属都市や村へ絞られ、
市内の短い移動や乗換は別に描写する。途中に取立日が来る場合はその日に進行を区切り、
既定の取立てを解決してから続きを進める。街道の本数ごとに遭遇や宿代を重ねない。
`world-calendar --save <確定セーブ>`で暦を確認できる。新規Day1は箱庭暦1年1月1日月曜。
360日年・30日月・七日週をDayから導き、短い会話や扉の開閉のたびに半日を消費しない。
段階読込で品物一覧を省く時も、今回使う既存品は--itemで指定して価格・効果・制限の該当節を追加取得する。

- 店内で魔導書を買う: --scene shop --include-scene magic
- ダンジョンに入る・探索する・帰る: --scene dungeon。戦闘になる時だけ--include-scene combatも追加。
- 街の小イベントから生産依頼を受ける: --scene event --include-scene quest --condition production_request
- 管理だけの処理: manageか専用コマンド。架空のsystemというsceneを作らない。

| condition | 必ず指定する時 |
|---|---|
| production_request | 製作・修理・料理・研究・発明・店経営など、職業や明示行動に合う依頼を作成・受注・進行する時 |
| noncash_reward | 品物・権利・サービス・協力・紹介・情報など現金以外の報酬を設計・提示・受領する時 |
| ability_fruit_resolution | 能力の実の候補可否、外れ、天井、種類、C級支給、提示・受領を扱う前から |
| victory | 勝利が確定しドロップを処理する時 |
| yuri／needs_voice_seed | 該当の追加文体／未登録人物の声サンプルが必要な時 |

職業・材料・恒久効果などの実現可能性を確認してから依頼を確定する。
追加資料が必要になったら、同じ現行セーブとtx IDで別名のcontextとprepared候補を作り、実際に読む。
例: <tx-id>.reward.context.md／<tx-id>.reward.prepared.yaml。既存候補をforceで押し流さない。
新prepared候補へ、確定済みの未commit差分を一度だけ反映し直す。出目は引き直さない。

## 移動と散策の二段階読込 (4.13.3)

1. 移動・散策では既存begin-turnに`--movement-style normal|direct|stroll|wander|idle`と`--location-kind town|road|dungeon`を指定する。normalはスタイル未指定の目的移動、directは本人が選んだ直行、strollは目的地までぶらぶら、wanderは目的なし散策、idleは移動しない休憩等。通常はeventのprobeで始め、必要な場所構造を読む。
2. 急ぐ根拠がある時だけ`--movement-urgency player_rush|quest_time_pressure|medical_emergency`を付ける。クエストがあるだけでは付けず、曖昧ならnormal。返されたmovement_event_planとM51本文を使い、街・村のwander80％、normal20％、stroll40％、道中のwanderとidle40％。急ぎ・directとダンジョンにはM51を振らない。
3. 抽選ありなら固定d10を1件だけ使い、当選時だけ直後のd10で既存種別表を引く。変更JSONのresponse.movementは雛形のまま使い、response.random_event_rollへdie=d10・result・cursor、当選時だけrandom_event_type_rollへ同じ形を置く。通常のsession_logにも今回の記録を残し、cursorを同じ候補で進める。system_blocksの表示は各`d10 = <出目>`だけ。
4. 移動イベントはM51とC-7の既存素材からその場で作り、EV在庫を消費しない。createへ追加取得する時も同じmovement-styleを渡す。移動しないidleでは従来の適合在庫を使える。ダンジョンは専用規則・在庫を維持する。
5. 困り事・声かけ・目撃等を通り過ぎられる形で示し、「そのまま目的地へ向かう」候補を残す。関わっても1〜3ターンで閉じ、元の用事を乗っ取らない。出来事の続きはadvanceで読み、新しい移動抽選を繰り返さない。見送り後の到着だけは直行相当として短く処理できる。
6. 外れ・急ぎ・directの移動描写は2〜3行で到着する。返信検査も移動部分だけへ650字を強制しない。到着後の本編を同じ返信へ描く時はresponse.movement.arrival_scene=trueとして通常の本文基準を使う。新しい場所の構造と必要資料は先に取得する。
7. 移動を選ぶ場面では同じ行先の直行／ぶらぶらを原則対で出す。緊急なら後者を出さず、戦闘や交渉など移動が主題でない場面へ対を機械的に増やさない。街の自由行動には目的なし散策を自然に置ける。
8. M51が出た場面へC-7を重ねない（responseへc7_rollを記録する場合も同じ）。M47の受注判定と混ぜない。リリス・ミルカの案内は人格の追加サンプルを一度だけ、実際に話した時に既存campaign_loreへ記録する。確率の講義やGMの物語外コメントは付けない。

## 文体

共通の文体部分は全場面で毎回contextに入る。字数上限で途中を切らず、今回の節を末尾まで読む。
専用場面に入る時は--intimate-scene onを指定し、選択済みero_styleを確認する。
文体カード・専用ルール・辞書の全文と、該当追加条件の資料が集まったことをreceiptで確認し、本文を読む。
継続はautoで保存済みruntime_state.ero_sceneとstyle_conditionsを引き継ぐ。
組合せが変わる時はonと今回の条件で指定し直す。終了は次の通常sceneと--intimate-scene offを使う。
ero_styleは好みなので終了時も保持する。初回開始の判断はGMが行う。
声の種が必要ならneeds_voice_seedと--topicで節を指定し、絞れなければ全文で補完する。

## 変更JSONと確定

changes_templateのschema・save_revision・save_sha256を保持し、operationsへ
JSON-pointerのadd／replace／remove／testだけを書く。例:
`{"op":"replace","path":"/player/gold","value":900}`。
必要な新事実は/world_state/campaign_loreへ記録する。過去の細部・計算内訳は
read-save --save <save-path> --pointer <対象パス>で取得する。
省略された表示データをセーブへ書き戻さない。

finish-turnは変更を完全なprepared候補へ反映し、検証・確定してステータスを作る。
通常はlast_committed_turn+1、ヒアリング・管理情報だけなら現行turnを指定する。
一意なtx IDは[A-Za-z0-9][A-Za-z0-9_-]{0,79}。再試行では同じ候補とIDを使う。
最初のcommitを試した後に内容を変える時は新しいIDにする。
採用した全在庫を--inventory-useで渡し、セーブと同時に確定する。単独inventory-useを通常ターンで使わない。

報酬・成長・ダンジョン・遠征・死に戻り・取立てでは`special-transactions.md`の該当節を読む。
専用候補の作成が必要なら既存のapply-changes／validate-save／commit-save／commit-turnを使える。
失敗した候補の結果本文は返さず、同じ候補・tx ID・在庫ID・出目を保ってdoctorで修復する。

初期配分・能力の実・再訓練は`allocation-flow.md`の専用手順を使う。
再訓練は100G・半日で、初期配分と実・明記された成長を含む6能力の恒久値を
各3以上・変更前と同じ合計へ配分し直す（M102）。装備・火・一時補正は対象外。
出生時の配分記録と実の使用履歴は保ち、変更前後と料金・時間を配分台帳へ追記する。
LPの実のBase LP+3は独立して保持し、6能力への変換・返還はしない。転職だけでは配分を変えない。

恒久DEFは`base_stats.def + growth_bonus.def`、DEF由来LPは
`stat_lp_bonus = max(0, (恒久DEF - 3) // 2)`とする。装備・火・一時DEFは含めない。
最大LPは`base_lp + job_lp_bonus + fire_lp_bonus + temporary_lp_bonus + stat_lp_bonus`、
最大MPは実効INT。実使用・再訓練後の現在LP/MPは`min(旧現在値, 新上限)`とし、
上限増加で回復せず、0からも復帰しない。初期作成だけは計算後の上限まで満たす。

## ダイスと表示

出目はdice.pyと保存済みcursorから取得し、drawsを順番どおり使い、next_cursorを変更へ保存する。
必要な個数だけ引く。条件分岐後に不要な追加ロールを先取りしない。実プレイ中にテープをgenerateしない。

```bash
python3 machadan_spade/muse版/tools/dice.py draw d10 <dice-cursor-d10> <count> \
  --tape machadan_spade/muse版/tools/dice_tape.json
```

d6も同じ形。全テープのverifyは導入・更新・異常時の総点検で行う。
本文は未送信で文体・NG・正本・変更内容を照合し、commit成功後だけ返す。
HTMLはwidget.createのkind: html_file／present_now: trueで表示し、dataにpathとfallback_textを置く。
widgetが使えない場合だけcompact textを本文後へ表示する。

## 返信の軽量チェック (4.13.2)

通常は既存のchanges JSONに`response`を入れ、同じ`finish-turn`呼出しで検査する。追加のAI呼出しや全場面再読込は行わない。

| responseの項目 | 内容 |
|---|---|
| schema | `machadan-response-v1` |
| main_text | 地の文と台詞だけの未送信本文。文体カード(p)の文量・被覆を守り、水増ししない |
| system_blocks | 判定内訳、数値・条件、精算・収支、クエストカード等の文字列配列。全量維持し、本文字数に算入しない |
| choices | 現在見えている状況から選べる行動の文字列配列。番号なしで2つ以上、通常3〜5つ。自由入力の案内は自動で付き、既存のHスキップ6番目も維持 |

字数は空白・改行・Markdownの装飾記号を除いた本文の文字数。街・会話600〜800、移動650〜850、戦闘と依頼550〜750、専用場面は既存の600以上を使う。保存済みscene・場面状態と実際の移動から決める。
ヒアリング・導入説明・状態閲覧・専用ウィジェットの配分確定通知等は本文字数の対象外だが、必要な選択面は残す。通常の職業登録や会話を説明扱いにして省略しない。
本人の質問への回答だけなら`prose_kind=explanation`と`short_reason=player_question`、短い相槌だけなら`prose_kind=brief`と`short_reason=brief_acknowledgement`を指定できる。どちらもゲーム状態の変更がない時だけ通る。通常の出来事をこの免除へ回さない。
ヒアリング・初期配分でウィジェットが実際に入力待ちの時だけ、`interaction`へ`type=widget`・実際の`widget_id`・今必要な短い`instruction`を置いてよい。チャット代替時はchoicesを出す。

特殊処理で専用候補をcommitする場合だけ、本文を同じresponse形式のJSONへ一度保存し、commit前に次を実行する（純粋な検査でセーブは変えない）。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  check-response --save <専用候補> --before-save <確定セーブ> --response <未送信返信.json>
```

成功後に既存の専用commitを行い、検査したmain_text・system_blocksと返されたchoices_textをそのまま使う。通常finish-turnでこの別コマンドを重ねて実行しない。
字数の範囲外・候補不足は内部で直し、未確定の結果をプレイヤーへ出さない。保存後に本文を別の短文へ書き換えたり、選択肢だけ落としたりしない。
仕草・周囲の様子・反応などの小説としての質は既存の文体(p)で執筆前と出力前に確認する。機械検査は字数と選択面だけで、長い点検文や引用、語彙スキャンを追加しない。

## 固定導入とリリスの火

初回の質問が完了した後も、宿を出る前の固定導入を必ず行う。
`widget-flow.md`の「ヒアリング後の固定導入とリリスの火」を読み、
`onboarding-status --save <committed-save-path>`の`next_stage`と確定済み進捗で次を決める。
順序は**REBIRTH → FIRE → BONUS → TUTORIAL**。完了済みの質問・肉体覚醒・配分を繰り返さない。
この順序は内部用。工程の完了報告や次工程の予告をGMの声で付けず、現在の場面・表示・必要な操作へ進む。

FIREでは数値正本§3と`SCRIPT_OPENING_FIRE`を読む。
まずリリスが火を分ける提案をし、受取入力を待つ。受取入力後は
`grant-fire --save <prepared-or-current-save> --output <candidate> --transaction-id <tx-id>`で
専用候補を作り、validate-saveと通常commitで確定する。候補だけでは授与済みではない。
保存成功後に「リリス自身の胸の火を主人公の胸へ移す場面→確定実値の変化→リリスの物語としての説明→
地の文で今必要な補正と死に戻り・対価の要点だけ」の順で返す。質問された内容には授与前でも答えてよい。
能力名・補正値・料金表をリリスの台詞で読み上げさせず、grant-fireやcommit等の内部操作も本文へ出さない。

新版の新規主人公はBase各3に15ptを配り、基礎合計33・各能力最低3・Base LP20とする。
実際に使う予算はonboarding-statusのallocation_budgetを先に確認する。既存セーブが従来の45等の予算・
配分を保持する場合は返却予算を優先し、33へ減らしたり再配分させたりしない。
初期配分はbase_stats、火はfire_bonus/fire_lp_bonusへ分け、どちらにも二重加算しない。

完了記録はworld_state.onboardingのbody_received / allocation_complete / fire_granted /
fire_explained / tutorial_completeと既存active_scriptを使う。授与の記録はgrant-fireが候補へまとめる。
火を既に持っているなら説明を補い、授与や点火を初回からやり直さない。
職業未定でも火の授与は行い、build_completeは職業等が揃うまでfalseを保てる。
全て完了してから宿外の自由行動へ進む。新規と既存の予算を混同せず、確定値と完了済み工程を守る。

## 再開と補充

初回質問は現在の段階の脚本だけ読み、回答を確定したらstartを再生成する。
固定脚本の途中は保存されたIDと完了位置から再開する。旧スキーマはdoctorで検証付き移行する。
補充は確定済みセーブのヒアリング完了・職業確定を読み、対象キャンペーンと世代を明記して少数だけ行う。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  inventory-template --save <committed-save-path> --output <refill.json> --max 8
```

テンプレートの条件・空き・世代・schemaを読み、許可された種類だけ作りinventory-appendへ渡す。
再試行では同じJSONとrun_idを使う。候補や未回答の好み・職業から生成しない。
補充待ち・在庫ゼロは正常。登場済みの事実と進行はセーブに残し、未定義の場面は世界に合う創作で続ける。

## 実務の正形とコマンド引数 (4.13.0)

REBIRTH／FIRE／BONUSの新規導入commitは必ず`--turn 0`。冒険開始前にturnを進めない。既存の途中セーブへ導入をやり直さない。

| 操作 | 正しい引数・出力 |
|---|---|
| validate-save | `validate-save <候補.yaml>`。ファイルは位置引数 |
| reward-effect | `--current <現行> --candidate <下書き> --target player.gold`等。JSONをstdoutへ返す。ファイル出力オプションはない |
| apply-changes | `--current <現行> --prepared <完全候補> --changes <変更JSON> --output <別候補>`を全て渡す。下書きだけなら`--draft` |
| resolve-debt-collection | `--save <取立て待ちの候補> --payment <金額> --output <別候補> --transaction-id <一意ID>` |
| dungeon_exploration.py resolve | `--save <現行> --output <別候補> --action-id <一意ID> --kind passage`で攻略済み階の通過。確定は通常のcommit-save |

日付は`/world_state/day`、借金は`/debt_state/principal`と`/debt_state/collection_ledger`、表示互換の借金は`/player/debt`。クエスト進捗は`/world_state/quest_card/progress`全体をreplaceし、未作成の中間キーへ部分追加しない。

報酬の現金・アイテム・権利と台帳、宿代のchargeと日付、取立ての待ち状態と解決の実例は`machadan_spade/muse版/運用/実務手順例.md`を読む。報酬精算に契約外の拾得品・買い物・別の現金増減を混ぜず、別の確定へ分ける。

### 攻略済み階の通り抜け

通過は出来事1件。通常の出来事抽選、資源取得・消費、街のM51は行わない。既存の長居判定だけは発生しうる。通過1階につきpassage_ticksが1進み、3で時間帯が1つ、6で約半日進む。普通探索の既存の時間処理へ、通過分の時間を二重加算しない。通常探索の時間が進んでも端数は消さない。

現在階の通過をresolve→commitした後、階段移動の候補でcurrent_floor・depthと訪問カウンタを更新し、arrive→commitする。通過と別階の資源記録を一つの候補へ混ぜない。連続して通る入力でも1階ずつ確定し、襲来・取立て待ちに入った所で止める。プレイヤーへ内部commitごとの確認は求めず、必要な出来事と選択だけを返す。

日付が取立日に達した候補にはcollection_pending=trueが同時に入る。場面終了後に取立てを解決するまで次の通過へ進めない。日またぎだけでresource_days_by_floorを更新せず、同じ潜行内の枯れた資源を復活させない。帰還だけで時刻を夕へ巻き戻さない。
