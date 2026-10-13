# spicy_novel_vocab_jp

官能小説・エロラノベの地の文で、性器・身体部位や行為・反応を描写する際に同じ表現の繰り返しを避け、語彙を多様化するためのリファレンススキル。

官能小説執筆の総合スキル [spicy_novel_jp](https://gitgud.io/kagamikami/spicy_novel_jp/)を強化するコンパニオンスキル。頻出する主語・述語の言い換えで単調さを排除し、文学性を高める。

このリポジトリおよびスキルは上記スキルを前提とするエクスパンションである。注意点も上記のREADMEを参照すること。


## 構成

```
spicy_novel_vocab_jp/
├── SKILL.md                      # インデックス + 運用ルール（v4.0.0）
├── LICENSE                       # 0BSD License
├── reference/                    # カテゴリ別語彙（26ファイル）
│   ├── S1-male.md 〜 S12-testicles.md   # 主語（名詞表現）
│   └── P1-insertion.md 〜 P14-body-reaction.md  # 述語（動詞・状態表現）
└── release/
    └── spicy_novel_vocab_jp_v4.0.0.zip   # スキルインストーラ用アーカイブ
```

## 使い方

このスキルはリファレンスが主体。全文を一度に読み込まず、描写に必要なカテゴリのファイルだけを `reference/` から選択的に読み込む。

例：挿入〜抽送シーン → S1 / S3 / S9 / P1 / P2 / P7

## インストール

gitgud.io の Release に添付した zip から、スキルインストーラで直接インストールできる。

```
npx skills add https://gitgud.io/kagamikami/spicy_novel_vocab_jp/-/releases/v4.0.0/downloads/spicy_novel_vocab_jp_v4.0.0.zip
```

手動の場合はリポジトリを clone して、`SKILL.md` と `reference/` をスキルディレクトリへ配置する。

## 配布

本スキルの配布・最新版は gitgud.io で公開。
https://gitgud.io/kagamikami/spicy_novel_vocab_jp/

## 更新履歴

### v4.0.0 (2026-10-04)

- gitgud.io Release による配布に対応（Release の zip をスキルインストーラから直接指定可能に）
- 配布 zip を `release/spicy_novel_vocab_jp_v4.0.0.zip` として追加
- README にインストール手順と本更新履歴を追記

### v3.5.0 まで

- 語彙の再編・整理（S3 / S4 / S6 / S7 / S8 / S9 / S10 / S11 / P10）
- 喘ぎ声の参照先を spicy_novel_jp 同梱の `references/aegigoe_skills.md` に変更
- 配布ページを note.com から gitgud.io へ変更
- 0BSD LICENSE を追加

## ライセンス

0BSD License

詳細は同梱の `LICENSE` ファイルをご覧ください。
