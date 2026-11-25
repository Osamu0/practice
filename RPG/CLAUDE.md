# RPG（マチャダン スペード）

## 中身

- `machadan_spade/` … マチャダン スペード Muse版の本体とセーブ
- `.claude/skills/machadan-gm`、`.claude/skills/machadan-doctor` … 進行と検査・修復のスキル

## 決め

- `machadan_spade/` の中身は配布物で、改ざん検査（RUNTIME_MANIFEST の SHA-256）の対象。手で書き換えない。直すときは machadan-doctor の手順に従う。
- コマンドは、リポジトリの一番上で実行する。
- ツールがスキルの場所を見つけられるように、検査のときは `MACHADAN_WORKSPACE=RPG/.claude` を付ける。

  ```bash
  MACHADAN_WORKSPACE=RPG/.claude python3 RPG/machadan_spade/muse版/tools/check_knowledge.py \
    --root RPG/machadan_spade/muse版 --strict --anchors --json
  ```
