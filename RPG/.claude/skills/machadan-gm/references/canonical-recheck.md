# 正本再照合プロトコル

MUSEが「資料にない」と判断する前、または資料同士が矛盾して見える時に実行する。

## 検索順

1. 正本レジストリで分野ID、canonical、supporting、superseded、revisionを確認する。
2. 完全一致語で検索する。
3. 表記揺れ、同義語、旧称、英名、CHAR/LOC/RULE/SCRIPT IDで検索する。
4. 関係するM番号が分かる場合だけ、決定台帳をM番号で検索する。
5. canonicalに指定された節を省略せず全文読む。
6. 現行revisionに対応する最新決定を読む。

## 分類

- `stale_summary`: 正本は明確だが、要約・カード・索引が古い。
- `missing_propagation`: 確定変更が一部の現行資料へ反映されていない。
- `generated_stale`: anchors、索引、manifestなど生成物だけが古い。
- `true_conflict`: 同じ優先度の現行正本が異なる内容を断定している。
- `undefined_story`: 正本にも決定台帳にも定義のない人物・場所・出来事・手段。創作できる空白。
- `damaged_required_resource`: 配布manifestに載っている既定の資料が欠落・破損している。

## 処理

- 上三つはdoctorへ渡す。本番の索引やmanifestはその場で書き換えず、検証済み配布物から安全に戻す。
- `undefined_story` は確認や停止をせず、既存世界とルールに合う形で創作する。
  継続する新事実をworld_state.campaign_loreへ記録し、既定の設定を上書きしない。
- `damaged_required_resource` は内部で同じ正本・検証済み配布物から復旧する。
  未定義の人物や場所をこの分類に入れない。
- `true_conflict` は優先順位と最新決定で解決する。それでも結果が一意に決まらず、
  続けると既定ルールやセーブを壊す場合だけ、該当部分を短く確認する。
- 旧資料やsuperseded資料の記述を多数決に使わない。
- 質問前に「正本にあるのに見落とした」可能性を必ず潰す。

