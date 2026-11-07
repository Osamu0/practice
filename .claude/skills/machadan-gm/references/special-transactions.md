# 特殊処理の保存手順（4.13.0）

通常ターンでこの資料を毎回全文読む必要はない。GMの参照表で指定された節を、
例外・関連節まで最後まで読む。正本の数値・条件は今回のcontextを使う。
本文は保存成功まで未送信にし、同じ操作の再試行では候補とtransaction IDを保つ。
専用候補のcommit前はruntime-contract「返信の軽量チェック」のcheck-responseで本文字数と行動候補を確認する。
通常finish-turnでは同じ検査が保存処理に含まれる。両方を重ねず、成功後も検査した本文と行動候補をそのまま返す。

## 報酬と精算

報酬を作成・提示・受領・辞退・後日清算する時に読む。
報酬の有無や種類数は固定せず、依頼者が提供できるものと物語の自然さに従う。
プレイヤーは全部・一部・辞退を選べる。辞退した成分を自動付与や保留にしない。

報酬受領ターンでは、現金、`inventory_bundle`（inventory / item_definitions /
item_instances）、`world_state.entitlements`の実体変更、
componentのdelivered/declined、`pending_rewards`の追加・削除、
`world_state.reward_ledger`への追記を一つの候補セーブへまとめる。
クエストカードを消す場合は、契約の全component IDを台帳の
delivered/declined/forfeitedまたはpendingへ移し、payer、kind、detailを
すり替えない。pendingの清算時も同じdetailをeffectと実体差分に
照合する。
台帳の新規成分はそのcommitのtransaction IDを保持し、既存成分は消去・
書換え・再追加しない。transaction IDは
`transaction.applied_transaction_ids` に蓄積し、直近でない過去IDも再使用しない。
保留成分を消す時は、対応する delivered /
declined / forfeited を同じ候補の台帳に必ず残す。権利等は
`source_settlement_id/source_component_id`で台帳のdelivered成分と1対1に結ぶ。

delivered成分は実体反映先をeffect.targetに指定し、候補反映後に次を
実行してbefore/after SHA-256をeffectへ写す。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  reward-effect --current <save-path> --candidate <candidate.yaml> \
  --target <player.gold|inventory_bundle|world_state.entitlements|session_log>
```

金は出力の正のamountも記録する。inventory_bundleは `added_items` から
item_name/quantityを、権利等は `added_entitlements` から新しい
entitlement_idをeffectに記録する。session_logは `append_only: true` を
確認し、`appended_log_entries` から未使用のlog_entry_index /
log_entry_sha256を写す。一つの追記行を複数成分に割り当てない。
declined/forfeitedは `effect: null`。台帳と実体のどちらかだけが
変わった候補は検証で拒否する。entitlementsはused/expired/revoked後も
消さず、statusと残回数だけを更新する。

通常のfinish-turnより先にeffectの計算が必要なら、`apply-changes --draft`で別の下書き候補を
作ってよい。effect取得後に変更JSONを完成させ、通常のapply-changesとvalidate-saveを通す。
下書きのvalidation_errorsを無視してcommitしない。特殊処理で完成済み候補を作った場合は、
末尾の「専用候補の確定」に従い既存のcommitを使う。

## 能力の実と成長の解決

候補可否、外れ、天井、種類、C級支給、提示・受領を扱う前から
`--condition ability_fruit_resolution`を指定し、正本の対象・確率・ダイス消費順を読む。

能力の実のボス・強敵・宝箱・ミミック・C級昇格・クエスト・イベント
供給を解決した時は、外れを含め一意な `resolution_id` を
`world_state.growth_state.resolutions` へ追記し、ダイスcursor、
`boss_fruit_miss_streak`、所持品差分、C級支給statusを同じ候補へまとめる。
既存resolutionを消去・書換え・再追加しない。

実を使う時は供給台帳とは別に`allocation-flow.md`の配分UIと消費記録を使う。
獲得だけで成長させず、使用時の実と対象人物の変化を同じ候補へまとめる。

## 遠征・ダンジョン・死に戻り

### 遠征と死に戻りの二段階commit

- 遠征開始の候補で `world_state.expedition_state` の `active=true`、
  新しい `expedition_id`、kind、同行火持ちを固定する。
  `rebirth_pending=false`、`last_end_reason=none`、ended ID空、receipt=nullで開始する。
- `fire_holders` の名前はplayerまたはpartyの同名レコードに必ず解決できる
  ようにする。一時分断・捕縛者はpartyから消さず、
  `separated_fire_holders` とメンバーのstateで表す。
- 被弾・事故処理で同行火持ち全員がLP0になったら、その第1commitは
  遠征をactiveのまま保ち、LP0と `rebirth_pending=true` を保存する。
  ダンジョンなら `dungeon_run` もその時点のまま保つ。
- pendingセーブを読んだら、本文の別進行、ダイス消費、報酬・成長、関係変化を
  入れず、別の一意transactionで死に戻り精算だけを直ちにcommitする。
  遠征と潜行を閉じ、`last_end_reason=rebirth`、対象expedition ID、
  対象全員の `lp_at_trigger: 0` receipt、`rebirth_pending=false` を残す。
- 精算差分は翌朝のぬれねずみ亭への移動、対象火持ちのLP/MP最大、
  一時的な通常state・`ero_status`解除、保存済み危険帯に応じた借金
  +500/+1,000/+1,500/+2,000Gとtyped debt charge台帳だけ。gold、inventory_bundle、
  プレイヤーと転送対象の装備、ammoを第1commit時点から変えない。
  ログは追記だけとし、クエスト、関係、スキル、報酬、成長、ダイスを同じ
  精算commitで変えない。非火持ちは転送対象ではなく、現地残留によるpartyからの
  離脱は許す。
- 宿への移動ではlocationとplace_id=INN_DRENCHED_RAT、room_id/sub_locationを
  帰還した実在客室へ合わせ、まだ部屋を決めていなければ空へクリアする。
  location_kindを使っている場合はtownへ戻す。
  洞窟や前の部屋のIDを宿へ持ち越さない。宿の新しい部屋を勝手に増やさず構造資料を読む。
- ユーザーへの表示は二つの内部commitを分断せず、死に戻りが即時発動した
  一連の場面として返してよい。

### ダンジョン在庫と探索状態 (M108)

- 現行正本は `世界/Dungeon_Data.md` §1。`tools/dungeon_exploration.py` で出来事一件の候補を作り、通常の検証付き確定へ渡す。数値・段階・抽選枠はGM内部情報で、ユーザーへは音・足跡・地形・魔物の動きで描く。
- 探索・非ボス戦に固定回数上限はない。`dungeon_memory` の日別・階別記録は帰還後も保持する。日またぎの潜行中は `resource_days_by_floor` を固定し、補充は翌日以降の新潜行。
- 初攻略ボスは出来事ごとに接近し、6で接触。先に場所を発見すれば自発的に挑める。攻略済みボスの追跡はなく、再入場で復活しても居場所へ向かわない限り会わない。
- ボスの実は一度獲得するまで30%、以後20%。初獲得前だけ外れ救済。新規resolutionは `rule_version: 2, source_key: boss-f<階>`。日次 `boss-loot` の記録・items差分・ダイスを同じ候補へまとめる。同日の再撃破で再抽選しない。
- 長居襲来は感知と敵の奇襲条件に応じて、兆しからの撤収または不利な接触になる。追跡開始後は腕輪を使えず、通常逃走または既定の帰還の水晶。討伐・奪取した実物装備を既存の所持品規則で確定する。
- dungeon在庫イベントは `used_event_ids` へ一度追記し、`commit-turn --inventory-use events:<ID>` と順序も一致させる。

## 取立て

取立て日前の任意返済は`resolve-debt-payment --save <確定セーブ> --payment <金額>
--output <candidate.yaml> --transaction-id <tx-id>`で候補を作る。
`resolve-debt-collection --save <prepared-candidate> --output <final-candidate>
--transaction-id <tx-id> --payment <金額>`で候補を作れる。
プレイヤーの支払意思を先に確認し、正本と候補の金・借金・次回取立て状態を照合する。
同じ支払いを別IDで二重処理せず、専用候補を下記の既存commit手順で確定する。

解禁根拠は正規完済台帳。初回完済特典はリリスとの関係解禁だけ、次契約50,000G。
第二契約完済で外見変更解禁、次契約100,000G。旧完済3択特典を加えない。
未完済の口説き・CHM・高好感度・スイート契約に例外を作らず、火授与や非性的介抱と区別する。
親密さは任意で、拒否や保留でも解禁と好意を取り消さない。恋人でも借金を免除しない。
関係の成立を保存する時は`runtime_state.interaction={target:人物ID,kind:romanceまたはintimacy,status:established}`
を記録する。リリスが対象に含まれる時はtargetをLilith_000とする。
口説いてかわされた時はstatusをattemptまたはdeclinedとし、恋愛成立として保存しない。
非性的な介抱や火授与にはkindをcareまたはfire_grantとして区別する。

## 外見変更

第二契約の正規完済後だけ利用可。人物の登録IDと希望する外見の項目をJSONへ用意し、
次を実行する。先にdebt場面のcontextへ`--character <対象の正規ID>`を加えて、
その人物の正本と現在キャンペーンの上書きを読む。変更前後を自然な日本語で提示する。
作業用previewとcandidateの出力先は`state/runtime/`配下に置く。
外見JSONで使える項目はhair/eyes/skin/face/build/body_shape/bust/outfit/appearance_notes、
数値のheight_cm、文字列リストのfeatures。指定しない部分は維持する。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  appearance-preview --save <確定セーブ> --character-id <正規ID> \
  --changes <外見JSON> --output <preview.json>
```

元の姿へ戻す場合は`--changes`の代わりに`--restore`を使う。previewのrequest_idを保持する。
**この時点では姿は変わらない。** プレイヤーがチャットで「確定」と答えた後だけ次を実行する。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  apply-appearance --save <同じ確定セーブ> --request-id <request-id> \
  --confirmation 確定 --output <candidate.yaml> --transaction-id <tx-id>
```

使える外見項目と変更前後はpreview結果を使い、未定義の能力項目を混ぜない。
saveが変わっていたら古いpreviewを適用せず、新しい変更前後を提示して確認を取り直す。
候補を下記の既存commit手順で確定する。正本人格ファイルを編集しない。
以後は人物読込時のACTIVE_SAVE_VIEWにある対象のoverridesを外見だけへ優先適用する。
人格・口調・成人性・関係・能力・装備所有を変えず、外見変更で恋愛や加入を成立させない。

## 専用候補の確定と再試行

既定の犯罪罰金を記録する場合だけ、debtのcharge台帳にreason=crime_fine、charge_amount=3000と
事件を特定するsource_idを用いる。所持金ではなく既存規定どおり元本へ加え、player.debtと同時更新する。
これは既存の罰金を保存できるようにしたもので、新都市に一律の新罰金や自動処罰を設ける規則ではない。

### target turnと冪等性

- ゲーム内の通常操作は `<target-turn> = last_committed_turn + 1`。
- ヒアリング、context更新、管理情報だけの確定は現行の
  `last_committed_turn` を据え置く。
- 同じtransaction IDと同じ候補の `commit-save` 再試行だけが冪等。
  同じIDを別の候補に使わない。
- `commit-turn` にはセーブと在庫で同じ `<tx-id>` を一度だけ渡す。

### 在庫とセーブの複合確定が失敗した時

`commit-turn` は固定順でロックし、journalを作ってからセーブと在庫を更新する。
どちらかが失敗したら両方を元のbytesへ戻す。別候補を選ばず、候補YAML、
在庫ID、transaction IDを保持し、doctorで原因を解消後に同じ `commit-turn` を
再試行する。結果本文は成功するまで返さない。

完成した専用候補をvalidate-saveで確認し、在庫採用がなければ次で確定する。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  commit-save --current <save-path> --candidate <final-candidate.yaml> \
  --transaction-id <tx-id> --turn <target-turn>
```

在庫採用が1件以上あれば、同じ候補とIDを用い、セーブと在庫をまとめて確定する。

```bash
python3 machadan_spade/muse版/tools/machadan_runtime.py \
  commit-turn --current <save-path> --candidate <final-candidate.yaml> \
  --transaction-id <tx-id> --turn <target-turn> \
  --inventory-use <mobs-or-events>:<entry-id>
```

採用した全IDについて--inventory-useを繰り返す。dungeonの追記IDと在庫操作は順序も一致させる。
成功後の確定済みセーブからstatus-viewとrender-status-widgetを作り、通常の出力契約で返す。
保存に失敗した場合は下書きを公開せず、同じ候補・在庫ID・transaction IDを残してdoctorへ渡す。
