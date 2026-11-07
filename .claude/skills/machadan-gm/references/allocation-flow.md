# ステータス配分のウィジェット

初期配分、能力の実を使う時、ギルドで再訓練する時だけ読む。
普段の散策・会話・戦闘ではこの資料やHTMLを読み込まない。
画面の大きい数値は火・装備等を含む最終能力。初期の基礎3・火+3なら6と表示する。
保存用state.valuesは従来どおり基礎値（実・再訓練では恒久値）のまま。表示の6を基礎へ転記したり、火に配分点を使ったりしない。
更新前の画面は最新の確定セーブから再表示する。古い画面の最終値からstateを手作業で作らない。
操作案内は現在必要な入力だけを短いシステム文で示す。確定後は実際の能力差分・消費・料金・時間とHUDを返し、
GMの感想・労い・次工程の予告・継続の促しを付けない。初期配分後の外出案内は場面内の人物の台詞と地の文で行う。

## 共通の手順

1. 本人の希望を確かめ、対象人物、操作、使う実の個数を決める。
   初期配分は主人公のみ。実と再訓練は在場の主人公・同行者のcharacter_idを指定する。
   初期配分前にはonboarding-statusで火の授与と説明が済んでいること、工程がbonusであること、allocation_budgetを確認する。
2. 下記のallocation-widgetを**確定済みの現行セーブ**へ実行する。
   戻ったoutputのHTMLをMUSEのwidget.createで即時表示する。

   ```json
   {"kind":"html_file","data":{"path":"<outputの絶対パス>","fallback_text":"各能力への配分をチャットで入力し、最後に『確定』と送ってください。"},"present_now":true}
   ```

   返ったwidget_idとrequest_id、source-save、state_pathを今回の操作記録へ保持する。
   HTMLリンクを渡すだけで終わらせない。既定の配分を本人の回答にしない。
3. ＋／−は配分案の編集だけで、セーブ、実の個数、所持金、時間を変更しない。
   下限・上限と残数は画面に表示する。質問中や調整中に勝手に次へ進まない。
   キャンセルなら結果を反映せず、その操作を終える。
4. プレイヤーがチャットで「確定」と送った時だけ、実際のwidget_idを指定して
   widget.stateを取得する。ラッパーを含む完全なJSONを加工せず一時ファイルへ保存する。
   version0かつstate空なら未回答として、画面を再表示する。画面の数値を会話から復元しない。
5. 同じ現行セーブと回収stateを使い、専用の候補を作る。

   ```bash
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     allocation-resolve --save <committed-save> --widget-state <actual-widget-state.json> \
     --confirmation 確定 --output <tx-id>.allocation.yaml --transaction-id <tx-id>
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     validate-save <tx-id>.allocation.yaml
   python3 machadan_spade/muse版/tools/machadan_runtime.py \
     commit-save --current <committed-save> --candidate <tx-id>.allocation.yaml \
     --transaction-id <tx-id> --turn <target-turn>
   ```

   初期配分はゲーム内ターンを増やさず、実使用・再訓練は通常の次ターンを使う。
   同じstate・候補・transaction IDでだけ再試行する。別内容を同じIDへ上書きしない。
6. 保存成功後だけ、実際の能力差分・実の消費・料金・時間と読取専用HUDを返す。
   再訓練で取立て日になった時は、次の時間進行前に既定の取立てを扱う。

## 各モード

出力は今回のキャンペーンのstate/runtime配下へ置く。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  allocation-widget --save <committed-save> --mode initial --output <request-id>.allocation.html
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  allocation-widget --save <committed-save> --mode fruit --actor-id <character-id> \
  --stack-id <carried-stack-id> --quantity <1..10> --output <request-id>.allocation.html
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  allocation-widget --save <committed-save> --mode respec --actor-id <character-id> \
  --output <request-id>.allocation.html
```

- **initial:** 肉体を得て、火の受取と説明を保存してから表示する。
  新規は各3を下限に15点を足し、合計33を確定する。Base LP20に下記の
  DEF由来LPなどを加えて上限を計算し、LP/MPを満タンで開始する。
  初期配分の完了と出生時の配分記録を保存後、短い外出案内へ進む。既に持つ火や装備の補正は配分しない。火は画面の最終値へ反映する。
- **fruit:** 本人が使うと決めた持ち歩きの1種類の実を、指定個数だけ配分する。
  STR等の固定実はその能力だけ、LPの実は1個でBase LP+3、選べる実は
  1個ごとに6能力のどれか+1かBase LP+3。現在までの成長は減らせず、
  −で戻せるのは今回の配分案だけ。未予約の実だけを使い、受取時には成長しない。
  戦闘外の落ち着いて使える場面で行い、上限増加だけで現在LP/MPを回復しない。
- **respec:** ギルドでの転職とは別の再訓練。初期配分、通常能力の実、明記された
  成長を含む6能力の恒久値をすべて配分し直せる。各能力3以上・再訓練前と同じ
  恒久合計を守り、100Gと半日（朝→夕／昼→夜／夕→翌朝／夜→翌昼）を同時に記録する。
  LPの実で増えたBase LPはそのまま残し、6能力への点数換算や返還はしない。
  装備・火・一時補正は配分しない。出生時の配分記録と実の使用履歴を保ち、
  今回の変更前後を配分台帳へ追記する。変更なしなら再訓練不要。
  遠征・戦闘中は使えず、LP/MPを回復しない。
  転職も行う時は、新しい職業・プロフィール・由来技能の整理を先に通常保存してから、
  この画面を出す。転職だけで配分を変えない。

## LP・MPの再計算（M102）

恒久DEFは基礎値と獲得済み成長の合計。DEF由来LPは
`stat_lp_bonus = max(0, (恒久DEF - 3) // 2)` とし、装備・火・一時補正を含めない。
最大LPは `base_lp + job_lp_bonus + fire_lp_bonus + temporary_lp_bonus + stat_lp_bonus`、
最大MPは再計算後の実効INT。LPの実は引き続き1個でBase LP+3となり、DEF由来LPとは別に保持する。
実使用・再訓練後の現在LP/MPは `min(変更前の現在値, 新しい上限)` とし、
上限が増えても回復せず、0からも復帰しない。初期作成だけは計算後の上限まで満たして開始する。

## 再開と不一致

同じセーブのまま開き直す時は、同じrequest_idと回収済みのstate JSONを
allocation-widgetの`--request-id`と`--widget-state`へ渡すと配分案を復元できる。
別の行動でセーブが更新された時は古い画面を確定せず、最新セーブから新しい操作を作る。
値域、合計、対象人物、実の残数、プロフィール、source revision/hashはバックエンドで再検査する。
画面やJSONが申告した予算・補正・料金を計算根拠に使わない。

装備がある場合は、装備個体のspecification_snapshot.weightへ確認済みの数値重量を保持する。
STRの変化で重量超過が変わるため、encumbranceの計算結果をSPD予告と確定値へ反映する。
旧自由記述から重量を推測せず、不足する既定装備の情報は同じ正本から内部補完して保存後に開き直す。

MUSE widget非対応時は同じ項目をチャットで聞き、対象requestの正規state.valuesへ本人の配分を
写して同じallocation-resolveを使う。元requestの識別情報を保持し、値を検証したcomplete stateを
作る。最後の「確定」待ちは省略しない。
