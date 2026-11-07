# 初回ヒアリングのウィジェット運用

## 基本契約

HTMLをファイルリンクとして渡すだけでは完了しない。各ステップで必ずMUSEの
`widget.create` と `widget.state` を使う。ウィジェットが使えないクライアントでは、
同じ項目を通常のチャット選択肢＋自由入力で一つずつ聞く。

## 表示と入力待ち (4.13.1)

地の文・場面内の台詞・ウィジェット・システム表示で進める。質問の確定、肉体の獲得、
火の授与、配分の完了ごとに、GMから進捗説明・感想・手順の予告・継続の促しを付けない。
工程名と順序は内部用であり、次の工程の一覧を読み上げない。入力を待つ時は、現在の選択肢または
「＋／−で配分し、チャットに『確定』と入力してください。」等の必要な操作だけを短いシステム文で示して終える。
HUD、能力変化、数値・条件・例外、ダイス内訳、選択肢、精算・収支の表示は省略しない。
地の文と登場人物としてのリリスの台詞、本人からの質問への回答は残す。GMの声の例外はコア§17の3点だけ。
配分画面の大きい数値は火を含む最終能力で、基礎と火の内訳も出す。保存用の基礎値と最終値を混ぜない。
ヒアリング・初期配分でウィジェットを表示して入力待ちにする場合は、返信のinteractionに実際のwidget_idと今の操作案内を記録する。ウィジェット非対応時はチャットの選択肢を出す。

## 共通手順

1. widget namespaceが未読なら、そのターンの実際のツール定義を読み込む。
2. `widget.create` を次の正確な形で呼ぶ。`path` と `fallback_text` は
   必ず `data` の中、`present_now` はトップレベルに置く。

   ```json
   {
     "kind": "html_file",
     "data": {
       "path": "/absolute/path/to/hearing_form_stepN.html",
       "fallback_text": "フォームが開けない場合は、このチャットで同じ項目に答えてください。"
     },
     "present_now": true
   }
   ```
3. 返った `widget_id` は応答回収まで作業中の操作記録に保持する。回答確定前の
   widget IDだけを現行セーブへ直接書かない。回答をcommitする時に
   `apply-hearing-state --widget-id` が `hearing_progress.widget_ids` へ監査用に保存する。
4. ユーザーが操作して「確定」と送るまで次へ進まない。
5. 記憶した回答ではなく、必ずその `widget_id` を指定し、
   `widget.state` を `{"widget_id":"<widget-id>"}` で呼ぶ。
6. `widget.state` 応答のラッパー `version` が0かつ `state` が空なら、
   既定値が見えているだけで未回答と扱う。このラッパー `version` と、HTML state内の
   `revision` は別物。ランタイムが `hearing_progress.widget_state_versions`へ
   保存するのは検証済みstateの `revision` である。
7. 必須項目と値域を検証し、問題があれば同じステップで修正を求める。
8. `widget.state` が返した完全なJSONを、対象キャンペーンの一時作業パスへ
   加工せず保存する。
9. ヒアリングの各ステップごとに `<tx-id>` を一つ作り、次を実行する。

   ```bash
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     apply-hearing-state --save <source-save-or-prepared-candidate> \
     --state <widget-state.json> --widget-id <widget-id> \
     --output <tx-id>.hearing-candidate.yaml
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     validate-save <tx-id>.hearing-candidate.yaml
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     commit-save --current <current-save> \
     --candidate <tx-id>.hearing-candidate.yaml \
     --transaction-id <tx-id> --turn <current-last-committed-turn>
   ```

   `--save` と `--output` は必ず別パスにする。開始contextの最初の回答では、
   context hash済みのprepared candidateをsourceにし、それを失わない。
   二回目以降は確定済み現行セーブをsourceにする。
10. 三コマンドの成功後にだけ次のステップを表示する。再試行は同じ
    state JSON、候補、transaction IDを使う。回答を変えた場合は新しい
    widget revisionとtransaction IDでやり直す。`--force` で別の候補を押し流さない。

## ステップ

| 順 | ファイル | 保存先・検証 |
|---|---|---|
| 1 | `tools/hearing_form_step1_playmode.html` | `play_mode`: `RP` / `GOD` |
| 2 | `tools/hearing_form_step2_profile.html` | `player.name`, `gender`, `age`。ageは整数かつ18以上必須 |
| 3 | `hearing_form_step3_body_female.html` または `_male.html` | `player_body`。片方だけ表示 |
| 4 | `tools/hearing_form_step4_desire.html` | `desire`, `yuri`, `ng`。NGはリスト化 |
| 5 | `tools/hearing_form_step5_partner.html` | 好みの相手像を`partner_pref`の6リストへ保存。全項目任意 |
| 6 | チャット | 文体モード。サンプル提示後に`ero_style`へ保存 |

ステップ6だけはウィジェットを使わない。各段階の前にstartのcontextを再生成してその段階の脚本を読む。全項目の確定後は下の「ヒアリング後の固定導入」へ進む。質問完了は火の授与完了を意味しない。

ステップ3は、性別が「女性」ならfemale、「男性」ならmaleを使う。性別が自由入力・
その他なら、性別の回答を書き換えず「体格の質問は女性体型／男性体型のどちらを
使いますか」と一問だけ尋ね、本人が選んだ方を使う。表記から推測して決めない。

widget stateを手作業でセーブへ転記しない。必ず上の `apply-hearing-state` に完全JSONを渡す。
`apply-hearing-state` は手順1〜5の順序、年齢、revision、完了状態を検証し、正規キーへ変換する。

## 確定後ステータスウィジェット

通常ターンはcommit成功後の確定済みセーブからだけ表示を作る。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  status-view <committed-save.yaml> --mode compact
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  render-status-widget <committed-save.yaml> --output <tx-id>.status.html
```

2番目の出力をヒアリングと同じ `widget.create` 形式の
`kind: html_file` / `present_now: true` で表示する。`fallback_text` は1番目の
`text` にする。ウィジェットは読取専用であり、カードのタップ展開に
`widget.state`、ターン消費、commitは不要。MUSEウィジェット非対応時だけ
compact textを本文後に表示する。

## ウィジェット非対応時のチャット代替（ステップ1〜5）

ウィジェットが使えない時も、セーブへ直接転記しない。同じ項目を一つの
チャット質問で聞き、回答を `machadan.hearing.widget.v2` の次の形へ正規化する。

```json
{
  "schema": "machadan.hearing.widget.v2",
  "schema_version": 2,
  "step": 1,
  "step_id": "playmode",
  "next_step": "profile",
  "revision": 1,
  "valid": true,
  "complete": true,
  "answers": {"playmode": {"choice": "RP", "free_text": ""}},
  "validation": {"errors": []}
}
```

- ステップ1: `step=1`, `step_id=playmode`, `next_step=profile`。`answers.playmode` は
  `{choice, free_text}`。明示回答を正規値 `RP` または `GOD` にする。
- ステップ2: `step=2`, `step_id=profile`, `next_step=body_profile`。`answers` は
  `name` 文字列、`gender:{choice,free_text}`、`age` 18以上の整数。
- ステップ3女性体型: `step=3`, `step_id=body_female`, `next_step=desire`。
  `height`、`bust`、`futanari` は `{choice,free_text}`、`build` は
  `{choices:[],free_text}`。
- ステップ3男性体型: `step=3`, `step_id=body_male`, `next_step=desire`。
  `height`、`size` は `{choice,free_text}`、`muscle` は `{choices:[],free_text}`。
- ステップ4: `step=4`, `step_id=desire`, `next_step=partner_preferences`。
  `desire`、`yuri_tachi`、`yuri_neko` は `{choices:[],free_text}`、`ng` は文字列。
- ステップ5: `step=5`, `step_id=partner_preferences`, `next_step=style`。
  `personalities`、`sub_personalities`、`body_height`、`body_build`、
  `body_bust`、`call` は全て `{choices:[],free_text}`。未指定と
  「おまかせ」は空リストへ正規化する。身長ボタンはcm目安を表示するが、
  stateとセーブでは `とても小柄 / 小柄 / 標準 / 長身 / とても長身` を使う。
  更新前のstateに `sub_personalities` が無い場合だけ旧形式として受理し、
  旧 `長身` は160cm以上の意味を保つため `長身 / とても長身` へ展開する。

未指定のsingleは `{choice:"",free_text:""}`、multiは
`{choices:[],free_text:""}` にする。`revision` は初回1。同じ完了ステップの回答を
修正する時だけ、保存済みrevisionより大きくする。`valid=true`、`complete=true`、
`validation.errors=[]` は、必須値と年齢を実際に検査した後だけ設定する。
このJSONを `apply-hearing-state` に渡し、`--widget-id chat-<tx-id>` として、
通常ウィジェットと同じvalidate/commit手順を通す。

## チャット回答の確定（ステップ6）

ステップ6はウィジェットではないため、現行セーブのコピーを候補にし、
明示された回答だけを次の固定マッピングで記録する。推測で埋めない。

- ステップ6: サンプルと正本の選択肢に従い、`ero_style` を正規値
  `machadan` または `rabilabi` で保存する。`completed_steps` に `style` を一度だけ
  追加し、`current_step=7`、`status=complete` にする。

候補で変更する部分は次の形。他の全セーブ項目は現行セーブからそのまま引き継ぐ。

```yaml
ero_style: machadan  # または rabilabi
hearing_progress:
  status: complete
  current_step: 7
  completed_steps: [playmode, profile, body_profile, desire, partner, style]
  # widget_ids / widget_state_versions は現行値を維持
```

ステップ6は専用のstable transaction IDを使い、`validate-save` 後に
次で確定する。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  validate-save <tx-id>.chat-hearing-candidate.yaml
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  commit-save --current <current-save> \
  --candidate <tx-id>.chat-hearing-candidate.yaml \
  --transaction-id <tx-id> --turn <current-last-committed-turn>
```

候補とcommitが成功するまで次の質問やREBIRTHの本文は出さない。

## ヒアリング後の固定導入とリリスの火（必須）

文体回答をcommitしたら、まず確定済みセーブを次で読む。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  onboarding-status --save <committed-save-path>
```

`next_stage`は`hearing / rebirth / fire / bonus / tutorial / complete`のいずれか。
ヒアリングは完了済みなのに、最初の質問や魂の覚醒へ戻してはいけない。
`next_stage`と`active_script`の確定進捗から、未完了の最初の工程だけを読む。
順序は**REBIRTH → FIRE → BONUS → TUTORIAL**で統一する。

| 工程 | 読む固定脚本・確定内容 |
|---|---|
| rebirth | `SCRIPT_OPENING_REBIRTH`。宿の舞台構造を読んで指定済みの体格で肉体覚醒を描く。新規の肉体はBase各3、Base LP20、LP20/20、MP3/3として保存する。完了時に`world_state.onboarding.body_received=true`と現在地「ぬれねずみ亭」を記録し、place_idはINN_DRENCHED_RAT、room_idは使った実在客室へ合わせる |
| fire | `SCRIPT_OPENING_FIRE`と数値正本§3。リリスの提案から受取入力を待ち、grant-fireの専用候補を確定する。保存成功後に胸から胸への点火・実値の変化を示し、物語の説明と、今必要な補正・死に戻り・対価の短い地の文を続ける |
| bonus | `SCRIPT_OPENING_BONUS`。`allocation-flow.md`に従いinitialウィジェットを表示し、チャットの「確定」を待つ。`onboarding-status`の`allocation_budget`に従う。新版の新規主人公はBase各3・合計33、Base LP20。DEF由来LPを含めて上限を再計算し、LP/MP満タンで開始する。既存の予算は下記の継承規則で守り、確定後に`allocation_complete=true`を記録する |
| tutorial | `SCRIPT_OPENING_TUTORIAL`。帰還の腕輪と仕事の窓口だけを短く案内し、その場面の確定時に`tutorial_complete=true`を記録する |
| complete | 火の所有・説明・固定導入の完了を確認し、ギルド訪問等の自由行動へ進む |

各完了記録は`world_state.onboarding`へ置き、同じ候補で`active_script`のID・status・
既存のcursor/checkpointも更新する。直接現行セーブを書き換えず、通常のchangesとcommitを使う。
文体・ヒアリングとこの固定導入は管理工程なので、ゲーム内ターンを勝手に進めない。
`build_complete`は職業とジョブプロフィールを確定するまではfalseでよく、火の授与を
転職まで待たせない。初期配分15ptはbase_stats、火はfire_bonus/fire_lp_bonusへ分ける。
新版の新規主人公はBase各3（6項目で18pt）に15ptを配り、基礎合計33・各能力最低3・Base LP20とする。
配分前には必ずonboarding-statusのallocation_budgetを読む。既存セーブが従来の合計45などの予算を
保持している場合は、その返却予算と確定済み配分を優先する。既存45を33へ下げたり、33を45へ戻したり、
完了済み配分を聞き直したりしない。予算を推測で置き換えず、保存された進捗・値を保つ。

初期作成後の実使用・再訓練にも`allocation-flow.md`の下書き→チャットの「確定」→
実state回収→検証付き保存を使う。再訓練は100G・半日で、実などによる成長を含む
6能力の恒久値を各3以上・変更前と同じ合計で配分し直す。出生時の配分記録は書き換えず、
LPの実のBase LP+3は独立して保持する。転職だけでは配分を変えない。
最大LPはBase LP・職業・火・一時LP補正に、恒久DEFからの
`max(0, (恒久DEF - 3) // 2)`を足す。装備・火・一時DEFはこの導出値に含めず、
最大MPは実効INTに合わせる。実使用・再訓練後は現在値を新上限で切り詰めるだけで、回復しない。

### 火の提案・入力待ち・授与後の説明

1. startの今回の工程を取得し、`SCRIPT_OPENING_FIRE`を末尾まで読む。
   授与前はリリスの物語の台詞で火を分ける提案をし、受取入力を待つ。
   能力名・補正表・死に戻り料金や全例外の読み上げを、最初の台詞へ詰め込まない。
   本人が先に質問した内容には、その場で答えてよい。
2. 「火を受け取る／どんなものか聞く」と自由な質問を示して回答を待つ。
   質問中に受取・点火を決めず、RPで主人公の返事・動作・感情を代筆しない。
3. 受取入力があり、未授与なら、今回の未編集prepared候補または確定済みセーブから次を実行する。

   ```bash
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     grant-fire --save <prepared-or-current-save> --output <tx-id>.fire-candidate.yaml \
     --transaction-id <tx-id>
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     validate-save <tx-id>.fire-candidate.yaml
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     commit-save --current <committed-save-path> --candidate <tx-id>.fire-candidate.yaml \
     --transaction-id <tx-id> --turn <current-last-committed-turn>
   ```

   作業先はstate/runtime等のセーブ外に置く。--saveと--outputは別パス。
   grant-fireは候補作成であり、commit成功前は現行セーブへ授与されていない。
   火持ちID、火の補正、実効値、LP/MP、授与済み・説明済みの記録を同じ候補で扱う。
   火をbase_statsやtemporary_modifiersへ足さず、人数補正や所有フラグを手で偽造しない。
4. 保存成功後の本文は、リリス自身の胸から浮かぶ火を取り出し、主人公の胸へ移す順に描く。
   次に、確定済みセーブから6能力・LP上限・MP上限の授与前→授与後を短く表示する。
   その後にリリスの台詞で火の働きを物語として話し、正確な数値と例外を地の文・表で示す。
   授与済みの実値を基礎配分と混ぜない。grant-fire、commit、内部キー等は台詞や物語本文へ出さない。
   失敗時は同じ候補・同じtx IDを保ち、成功したような本文を出さない。
5. 授与後の説明では、1人+3/+12、2人+2/+8、3人+1/+5、4人以上+0/+3、MP上限は実効INT、
   接触分配、同行人数の固定、全員LP0時の翌朝帰還、危険帯別500/1,000/1,500/2,000Gを伝える。
   回復範囲と残る呪い等、使った資源や世界の出来事は戻らないこと、追加の宿代・治療費なし、
   所持金・所持品を失わないことも、FIREの地の文に従って省略しない。
6. もう一度onboarding-statusを読み、次の未完了工程へ進む。既に火を持つ場合は再授与せず、
   抜けている説明を補う。長い説明の途中ではactive_scriptの位置を保持し、読み終わる前に宿外へ進めない。

### 既存セーブと途中再開

- ヒアリング済みの既存セーブは、その回答を聞き直さない。肉体覚醒や配分まで終わっているなら、
  保存済み進捗・数値とログを確認し、火の説明と未実施の授与から再開する。
- `onboarding-status`が旧記録を推定しきれない時は、`read-save`でactive_scriptと該当ログを読む。
  実際に確定・提示済みのbody_received/allocation_complete/tutorial_completeだけを補い、
  まだ行っていない工程まで済んだ扱いにしない。
- 火をすでに持つ場合は説明不足を補う。説明時に同じ火を受け取らせたり、+3/+12をもう一度足したりしない。
  旧セーブの数値へ既に火の分が含まれるか不明なら、元の値と記録を確かめ、推測で二重加算しない。
- 長い説明は区切ってよいが、完了するまでactive_scriptの位置を保持する。説明途中の再開で冒頭へ戻らない。
  火の授与と説明は宿を出る前の必須工程であり、職業未定・在庫準備待ちを理由に省略しない。

## 回答確定後の入荷（4.11.1）

apply-hearing-stateが作るものは未確定の候補である。この段階では入荷しない。
各回答と最後の文体選択がcommitされた後、次のbegin-turnが確定済みの
hearing_progress.status=completeを確認して人物のrefill_requestを返す。
好みの各欄が空でも「おまかせ」として完了でき、空欄を理由に再質問・停止しない。

人物の準備はinventory-template --save <committed-save-path>で今回のキャンペーン向けに行う。
職業がまだ未定なら依頼・イベントのまとめ入荷は待つ。職業が確定して保存された後に同じ仕組みで要求する。
予定や未送信候補から好み・職業を推測しない。入荷待ちは正常で、固定導入や通常の自由な物語を止めない。
毎朝の自動補充を無効にしている利用者も、必要な初回入荷と在庫切れ時の最小生成は利用できる。

## 再開

- 操作案内が必要な時だけ「未完了の回答欄を表示します。入力後、チャットに『確定』と入力してください。」等の短いシステム文を使う。再開の歓声、完了済み工程の要約、今後の手順の予告、継続の促しは付けない。
- `hearing_progress` に保存された完了済みステップは聞き直さない。
- 回答がcommitされていないwidget IDはセーブの永続状態ではない。当該ターンの
  作業記録にIDが残っていればstateを再取得し、無ければ同じ未完了ステップの
  widgetを再作成する。回答を推測したり次へ進んだりしない。
- widgetが再生できなければ、そのステップだけチャット方式へ切り替える。
- 年齢が空、非整数、18未満なら完了扱いにせず、セーブへcommitしない。
- チャット方式でも完了IDと `current_step` の順序を飛ばさない。未完了の
  最初のステップから再開する。


## 導入commitのターン指定 (4.13.0)

ヒアリングとREBIRTH／FIRE／BONUSは導入管理工程。新規作成からBONUS確定までは、commit-save／finish-turnに必ず`--turn 0`を指定する。通常の冒険ターンとして1へ進めると、initial配分が拒否される。FIREの例も新規導入では`--turn 0`へ置き換える。すでに冒険が始まった既存セーブの再開では、完了済み導入を再実行せず、現在の確定turnを維持する。
