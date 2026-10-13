# spicy_novel_jp

エロライトノベル・官能小説向けのAIエージェント用SKILL.md。

## 概要

このスキルは、官能小説の**企画から執筆完了まで**を一貫してサポートします。

## 注意

### AT YOUR OWN RISK: 自己責任で導入してください。

このリポジトリのスキルをインストールしたこと、およびこのリポジトリのスキルを使い生成したコンテンツにより発生した問題の責任所在は、リポジトリオーナーには存在せず、このスキルの使用者に限定されます。

### PERMABANNED SPEEDRUN IS READY: スキルを利用するLLM/AIエージェントサービスの規約・ポリシーに注意を払ってください。

このスキルは殆どのケースにおいてNSFWコンテンツを生成する目的で利用されるものです。
しかし(それがローカルでない限り)、このスキルを利用するLLMやAIエージェントサービスが、NSFWコンテンツの生成を禁止している場合があります。
ご自身の利用するサービスの利用規約・ポリシーを必ず確認した上で、自己判断でご利用ください。


## 対応フロー
- 企画
- 世界観設定（現代・ファンタジー・異世界）
- キャラクター作成
- アウトライン作成
- プロット作成
- 執筆

喘ぎ声が必要な場合は、同梱の `references/aegigoe_skills.md` を併読して使用してください。

## 使い方

このリポジトリ（https://gitgud.io/kagamikami/spicy_novel_jp/）を clone し、Hermes Agentやopencodeなどでこのスキルをインストールするよう伝えてください。

スキルインストーラ（`npx skills` など）は、Release の zip を直接指定できる。

```
npx skills add https://gitgud.io/kagamikami/spicy_novel_jp/-/releases/v5.0.0/downloads/spicy_novel_jp_v5.0.0.zip
```

## ファイル構成

```
.
├── SKILL.md                        # メインスキル
├── README.md
├── LICENSE
├── references/
│   ├── aegigoe_skills.md           # 喘ぎ声表現スキル
│   └── plot-template.md            # プロットテンプレート
└── release/
    └── spicy_novel_jp_v5.0.0.zip   # スキルインストーラ用アーカイブ
```

## 更新履歴

### v5.0.0 (2026-10-04)

v4.2.0 以降の変更をまとめたリリース。

- **gitgud.io Release による配布・自動アップデート対応**（Release の zip をスキルインストーラから直接指定可能に）
- 配布ページを note.com から https://gitgud.io/kagamikami/spicy_novel_jp/ へ変更
- 語彙多様化の参照先を `erotic-paraphrase-jp` から `spicy_novel_vocab_jp` に更新
- `references/plot-template.md` の参照を同梱の `references/aegigoe_skills.md` に統一
- `references/sf-body-modification.md` を削除（特化しすぎのため）
- `references/aegigoe_skills.md` の重複した見出し・テーブル行を削除
- SKILL.md の Hermes memory 節を削除、参照・配布まわりを整理
- README のファイル構成を現状に更新、対応エージェント例示を `opencode` に変更
- バージョンを 4.2.0 から 5.0.0 に更新

## ライセンス

0BSD License

詳細は同梱の `LICENSE` ファイルをご覧ください。
