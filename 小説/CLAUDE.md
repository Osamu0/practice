# 小説

## 中身

- `novel_〇〇/`、`novel/`、`spicy_idol/` … 作品ごとのフォルダ（企画メモ、設定、アウトライン、プロット、本文など）
- `キャラクター/` … 作品をまたいで使うキャラクター図鑑
- `参考文体の分析.md`、`スキル化の調査.md` … 文体とスキルの調べもの

## スキルとエージェント

- スキル：`小説/.claude/skills/` の次の5つ
  - `spicy_novel_planning_jp`：企画〜プロット。「どんなものにしたいか」から物語と設定を一緒に膨らませる
  - `spicy_novel_writing_jp`：文体
  - `spicy_novel_writing_team_jp`：執筆チームで本文を書く手順
  - `spicy_novel_vocab_jp`：語彙の言い換え
  - `spicy_novel_jp`：配布されている原本。書き換えない。喘ぎ声の `references/aegigoe_skills.md` はここを読む。企画〜プロットには使わず、`spicy_novel_planning_jp` を使う
- 執筆チーム（掛け合い、執筆、校閲、120点、ネタ出し）：リポジトリの一番上の `.claude/agents/novel/`

## 決め

- 新しい作品は `小説/novel_〇〇/` に作る。
- 作品の中で書く場所の指定は、リポジトリの一番上からの形にする（例：`小説/novel_offkai/文体ルール.md`）。
- どの作品の話かあいまいなときは、作品名かフォルダ名を確かめてから読む。ほかの作品の設定を混ぜない。
