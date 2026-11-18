---
name: game_dev_studio_jp
description: ゲームを、部門ごとに雇ってある仕事人（.claude/agents/ の game-* エージェント103人。現実のゲーム会社の約250職種を割り振ってある）で、企画から保守まで作るための、プロデューサー（メインのClaude）の手順。企画構想立案、プリプロダクション、仕様書作成、プロトタイプ作成、本格的な開発開始、ゲームシステム、コンテンツ制作、統合・演出制作、アルファ版、ベータ版、品質保証・最終審査、保守の12部門。部門の呼び方、渡し方、ゲート（次の部門に進む判定）、進行表、プロジェクトのフォルダの作り方。Use when ゲームを作る・企画する・仕様を書く・プロトタイプを作る・実装する・テストする・リリースする・アップデートするとき、ゲーム開発のチームを動かすとき。
---

# game_dev_studio_jp

ゲームを、役割を分けた仕事人で作るための手順。仕事人は `.claude/agents/game-*` に最初から雇ってある（103人）。現実のゲーム会社の職種（経営、デザイン、プログラム、アート、アニメ、シナリオ、サウンド、制作管理、QA、ローカライズ、リリース、宣伝、販売、運営、研究開発、法務など）を、どの仕事人が兼ねるかは `reference/roster.md`。プロジェクトごとにチームを作り直さない。プロジェクトのフォルダには、そのプロジェクトだけの違い（`開発チーム.md`）だけを書く。

- **プロデューサー**：メインのClaude。部門の順番を決め、仕事人を呼び、返ってきたものをまとめ、ゲートを判定し、`進行表.md` を書き、コミットする
- **オーナー**：ユーザー。企画・縦切り・アルファ・リリースの4つのゲートで、必ず判断をもらう
- **仕事人**：部門ごとのエージェント。作る担当（ファイルを書く）と、見る担当（書き換えない）がいる

目的は、オーナーが「作りたかったのはこれ」と言えるゲームを、出せる品質で出すこと。面白さは早く確かめ、品質は工程の最後でまとめて上げるのではなく、ゲートごとに積み上げる。

## 守ること（全部門共通）

- 既存の特定のゲームの再現（名前、キャラ、絵、音楽、ステージ、見た目）は作らない。ジャンルや仕掛けが似るのはよい。オーナーの企画が特定の作品の再現だったら、その場で止めて、オリジナルの形に変える提案をする
- 実在の人物・団体は出さない
- 事実（市場、規約、ライセンス、エンジンの版）は調べて出典を書く。わからないことは「わからない」と書く。数字を作らない
- 動くものは実際に動かして確かめる。動かせなかったら、そう書く。遊んだふり・テストしたふりをしない
- 決めていないことは「未決」として残す。推測で埋めない
- 外に出ること（公開、投稿、送信、発注、支払い、契約、申し込み、ストアへの提出、本番のサーバーの操作）は、仕事人もプロデューサーもしない。案と書類までを作り、オーナーに渡す
- 人の体や現場が要る仕事（声、モーションキャプチャー、撮影、収録）は、仕事人が手配書と受け入れの条件を書き、手配はオーナーが行う
- 法務・知的財産・財務の仕事人の返事は、専門家に確かめる前の整理。法的・会計の助言として扱わない

## 部門と仕事人

12の部門には、**中心の仕事人**（その部門のために雇った人）と、**加わる仕事人**（職種の専門家で、部門をまたいで参加する人）がいる。中心の仕事人は部門の参考ファイルの「呼ぶ順」に、加わる仕事人は部門の参考ファイルの「この部門に加わる仕事人」にある。

<!-- phase-table:begin -->
| # | 部門 | 中心の仕事人 | 加わる仕事人 |
|---|---|---|---|
| 1 | 企画構想立案 | `game-concept-planner`、`game-concept-market`、`game-concept-ideas` | `game-biz-executive`、`game-biz-planning`、`game-biz-finance`、`game-design-creative-director`、`game-art-concept`、`game-story-director`、`game-pm-secretary`、`game-loc-culturalize`、`game-mkt-director`、`game-mkt-copy`、`game-sales-publisher`、`game-sales-pricing`、`game-legal`、`game-legal-ip` |
| 2 | プリプロダクション | `game-preprod-designer`、`game-preprod-tech`、`game-preprod-art`、`game-preprod-producer` | `game-biz-planning`、`game-biz-finance`、`game-design-director`、`game-design-creative-director`、`game-design-systems`、`game-design-world`、`game-design-ux`、`game-tech-director`、`game-tech-engine`、`game-tech-network`、`game-tech-platform`、`game-art-concept`、`game-art-technical`、`game-story-director`、`game-story-lore`、`game-audio-director`、`game-pm-manager`、`game-pm-outsourcing`、`game-rnd-engineer`、`game-legal` |
| 3 | 仕様書作成 | `game-spec-writer`、`game-spec-balance`、`game-spec-review` | `game-design-director`、`game-design-systems`、`game-design-combat`、`game-design-economy`、`game-design-world`、`game-design-quest`、`game-design-ai`、`game-design-ux`、`game-design-social`、`game-story-director`、`game-loc-director`、`game-ops-analyst` |
| 4 | プロトタイプ作成 | `game-proto-programmer`、`game-proto-playtester` | `game-biz-executive`、`game-design-director`、`game-design-creative-director`、`game-design-systems`、`game-design-combat`、`game-design-ux`、`game-art-director`、`game-anim-animator`、`game-qa-usability`、`game-mkt-director`、`game-mkt-planner`、`game-mkt-creative`、`game-rnd-engineer` |
| 5 | 本格的な開発開始 | `game-prod-architect`、`game-prod-planner`、`game-prod-pipeline` | `game-tech-director`、`game-tech-engine`、`game-tech-graphics`、`game-tech-network`、`game-tech-backend`、`game-tech-tools`、`game-tech-platform`、`game-art-technical`、`game-pm-manager`、`game-pm-secretary`、`game-qa-automation` |
| 6 | ゲームシステム | `game-sys-gameplay`、`game-sys-ai`、`game-sys-ui`、`game-sys-code-review` | `game-design-director`、`game-design-systems`、`game-design-combat`、`game-design-ai`、`game-design-ux`、`game-design-social`、`game-tech-director`、`game-tech-engine`、`game-tech-graphics`、`game-tech-network`、`game-tech-backend`、`game-tech-security`、`game-tech-performance`、`game-audio-engineer`、`game-pm-manager`、`game-qa-lead`、`game-qa-automation`、`game-ops-analyst` |
| 7 | コンテンツ制作 | `game-content-level`、`game-content-scenario`、`game-content-art`、`game-content-sound` | `game-design-director`、`game-design-world`、`game-design-quest`、`game-tech-tools`、`game-art-director`、`game-art-concept`、`game-art-3d`、`game-art-lighting`、`game-art-vfx`、`game-art-ui`、`game-art-technical`、`game-anim-animator`、`game-anim-mocap`、`game-story-director`、`game-story-lore`、`game-story-quest-writer`、`game-story-dialogue`、`game-story-dialogue-review`、`game-audio-director`、`game-audio-composer`、`game-audio-voice`、`game-pm-manager`、`game-pm-outsourcing`、`game-loc-director`、`game-loc-translator`、`game-loc-culturalize`、`game-legal-ip` |
| 8 | 統合・演出制作 | `game-integ-integrator`、`game-integ-direction` | `game-design-director`、`game-design-creative-director`、`game-tech-graphics`、`game-tech-performance`、`game-art-director`、`game-art-lighting`、`game-art-vfx`、`game-art-ui`、`game-art-technical`、`game-anim-animator`、`game-anim-cinematic`、`game-story-director`、`game-audio-director`、`game-audio-engineer`、`game-audio-voice`、`game-pm-manager` |
| 9 | アルファ版 | `game-alpha-judge`、`game-alpha-playtest` | `game-biz-executive`、`game-design-director`、`game-design-creative-director`、`game-tech-director`、`game-art-director`、`game-pm-manager`、`game-pm-secretary`、`game-qa-lead`、`game-qa-usability`、`game-release-store`、`game-mkt-director`、`game-mkt-planner`、`game-mkt-community`、`game-mkt-pr`、`game-mkt-creative`、`game-sales-publisher` |
| 10 | ベータ版 | `game-beta-bugfix`、`game-beta-polish`、`game-beta-firsttime` | `game-design-director`、`game-design-combat`、`game-design-economy`、`game-design-ux`、`game-tech-performance`、`game-tech-platform`、`game-art-director`、`game-story-dialogue-review`、`game-audio-director`、`game-audio-engineer`、`game-pm-manager`、`game-qa-lead`、`game-qa-automation`、`game-qa-load-compat`、`game-qa-usability`、`game-loc-director`、`game-loc-translator`、`game-loc-culturalize`、`game-loc-lqa`、`game-release-store`、`game-mkt-planner`、`game-mkt-community`、`game-mkt-creative`、`game-mkt-copy`、`game-ops-analyst` |
| 11 | 品質保証・最終審査 | `game-qa-tester`、`game-qa-compliance`、`game-qa-release-judge` | `game-biz-executive`、`game-biz-finance`、`game-design-creative-director`、`game-tech-director`、`game-tech-security`、`game-tech-performance`、`game-tech-platform`、`game-pm-manager`、`game-pm-outsourcing`、`game-qa-lead`、`game-qa-automation`、`game-qa-load-compat`、`game-loc-director`、`game-loc-lqa`、`game-release-manager`、`game-release-store`、`game-mkt-director`、`game-mkt-planner`、`game-mkt-community`、`game-mkt-pr`、`game-mkt-creative`、`game-mkt-copy`、`game-sales-publisher`、`game-sales-pricing`、`game-ops-cs`、`game-ops-infra`、`game-legal`、`game-legal-ip` |
| 12 | 保守 | `game-ops-support`、`game-ops-live` | `game-biz-planning`、`game-biz-finance`、`game-design-economy`、`game-design-quest`、`game-design-social`、`game-tech-backend`、`game-tech-security`、`game-pm-secretary`、`game-release-manager`、`game-mkt-planner`、`game-mkt-community`、`game-sales-pricing`、`game-ops-analyst`、`game-ops-cs`、`game-ops-infra`、`game-legal` |
<!-- phase-table:end -->

### 中心の仕事人（35人）

| # | 部門 | 仕事人 | 役割 | 書くか |
|---|---|---|---|---|
| 1 | 企画構想立案 | `game-concept-planner` | 企画書（一文の企画、コアの面白さ、売り、規模） | 書く |
| | | `game-concept-market` | 市場・競合調査（出典つき） | 書かない |
| | | `game-concept-ideas` | アイデア出し30個以上、ありがち度順（どの部門からも呼べる） | 書かない |
| 2 | プリプロダクション | `game-preprod-designer` | デザインの柱、コアループ、スコープ | 書く |
| | | `game-preprod-tech` | 技術選定、技術リスク | 書く |
| | | `game-preprod-art` | アートディレクション（見た目・音・UIの方向） | 書く |
| | | `game-preprod-producer` | マイルストーン、リスク表、削る順番 | 書く |
| 3 | 仕様書作成 | `game-spec-writer` | GDD、機能仕様、受け入れ条件 | 書く |
| | | `game-spec-balance` | パラメータ表、成長曲線、シミュレーション | 書く |
| | | `game-spec-review` | 仕様レビュー（抜け・矛盾・実装・テスト） | 書かない |
| 4 | プロトタイプ作成 | `game-proto-programmer` | 問いを確かめる最小のプロトタイプ | 書く |
| | | `game-proto-playtester` | 遊んで、続ける／直す／捨てるの材料 | 書かない |
| 5 | 本格的な開発開始 | `game-prod-architect` | 本番の設計と土台のコード、規約 | 書く |
| | | `game-prod-planner` | バックログ（タスク分解） | 書く |
| | | `game-prod-pipeline` | ビルド・テスト・アセット取り込み・版 | 書く |
| 6 | ゲームシステム | `game-sys-gameplay` | 操作・ルール・進行・保存の実装 | 書く |
| | | `game-sys-ai` | 敵・NPCの振る舞い | 書く |
| | | `game-sys-ui` | 画面、HUD、設定、アクセシビリティ | 書く |
| | | `game-sys-code-review` | コードレビュー | 書かない |
| 7 | コンテンツ制作 | `game-content-level` | ステージ・マップ・配置 | 書く |
| | | `game-content-scenario` | 設定、物語、会話、文言 | 書く |
| | | `game-content-art` | 絵の資産、資産一覧 | 書く |
| | | `game-content-sound` | 効果音・BGM、サウンド一覧 | 書く |
| 8 | 統合・演出制作 | `game-integ-integrator` | つないで通しで遊べるビルドにする | 書く |
| | | `game-integ-direction` | 手ざわりと見せ場の演出 | 書く |
| 9 | アルファ版 | `game-alpha-judge` | アルファ判定 | 書かない |
| | | `game-alpha-playtest` | 通しのプレイテスト | 書かない |
| 10 | ベータ版 | `game-beta-bugfix` | バグ修正 | 書く |
| | | `game-beta-polish` | 調整・ポリッシュ（機能は足さない） | 書く |
| | | `game-beta-firsttime` | 初見プレイヤー（仕様を読まずに遊ぶ） | 書かない |
| 11 | 品質保証・最終審査 | `game-qa-tester` | テスト計画・実行・バグ報告（本番コードは触らない） | テストとバグ表だけ |
| | | `game-qa-compliance` | 規約・権利・年齢区分・ライセンス審査 | 書かない |
| | | `game-qa-release-judge` | リリース判定 | 書かない |
| 12 | 保守 | `game-ops-support` | 不具合の切り分け、パッチ、パッチノート | 書く |
| | | `game-ops-live` | 運営・アップデート計画 | 書く |

### 加わる仕事人（68人、職種の部門ごと）

<!-- group-table:begin -->
| 職種の部門 | 仕事人 | 役割 | 参加する部門 |
|---|---|---|---|
| 経営・事業 | `game-biz-executive` | 事業判断 | 01、04、09、11 |
|  | `game-biz-planning` | 事業企画 | 01、02、12 |
|  | `game-biz-finance` | 財務・予算 | 01、02、11、12 |
| 企画・ゲームデザイン | `game-design-director` | ゲームディレクター | 02、03、04、06、07、08、09、10 |
|  | `game-design-creative-director` | クリエイティブディレクター | 01、02、04、08、09、11 |
|  | `game-design-systems` | システムデザイン | 02、03、04、06 |
|  | `game-design-combat` | バトル・スキル設計 | 03、04、06、10 |
|  | `game-design-economy` | 経済・アイテム設計 | 03、10、12 |
|  | `game-design-world` | ワールドデザイン | 02、03、07 |
|  | `game-design-quest` | クエスト・イベント設計 | 03、07、12 |
|  | `game-design-ai` | AIデザイン | 03、06 |
|  | `game-design-ux` | UX・UI・チュートリアル設計 | 02、03、04、06、10 |
|  | `game-design-social` | ソーシャル設計 | 03、06、12 |
| プログラム・技術 | `game-tech-director` | テクニカルディレクター | 02、05、06、09、11 |
|  | `game-tech-engine` | エンジン・システム | 02、05、06 |
|  | `game-tech-graphics` | グラフィックス | 05、06、08 |
|  | `game-tech-network` | ネットワーク | 02、05、06 |
|  | `game-tech-backend` | サーバー・バックエンド | 05、06、12 |
|  | `game-tech-tools` | ツール | 05、07 |
|  | `game-tech-security` | セキュリティ・不正対策 | 06、11、12 |
|  | `game-tech-performance` | パフォーマンス | 06、08、10、11 |
|  | `game-tech-platform` | プラットフォーム | 02、05、10、11 |
| アート・グラフィック | `game-art-director` | アート監修 | 04、07、08、09、10 |
|  | `game-art-concept` | コンセプト・デザイン | 01、02、07 |
|  | `game-art-3d` | 3Dモデル・質感 | 07 |
|  | `game-art-lighting` | ライティング | 07、08 |
|  | `game-art-vfx` | エフェクト | 07、08 |
|  | `game-art-ui` | UIアート | 07、08 |
|  | `game-art-technical` | テクニカルアート | 02、05、07、08 |
| アニメーション・映像 | `game-anim-animator` | アニメーション | 04、07、08 |
|  | `game-anim-cinematic` | カットシーン・映像 | 08 |
|  | `game-anim-mocap` | モーションキャプチャー手配 | 07 |
| シナリオ・ナラティブ | `game-story-director` | ナラティブ設計 | 01、02、03、07、08 |
|  | `game-story-lore` | 世界観・キャラ設定 | 02、07 |
|  | `game-story-quest-writer` | サブシナリオ・クエスト | 07 |
|  | `game-story-dialogue` | 会話 | 07 |
|  | `game-story-dialogue-review` | 台詞監修 | 07、10 |
| サウンド・音楽 | `game-audio-director` | オーディオ監修 | 02、07、08、10 |
|  | `game-audio-composer` | 作曲・編曲 | 07 |
|  | `game-audio-engineer` | 音の実装・ミックス | 06、08、10 |
|  | `game-audio-voice` | ボイス | 07、08 |
| 制作管理 | `game-pm-manager` | 進行管理 | 02、05、06、07、08、09、10、11 |
|  | `game-pm-outsourcing` | 外注・調達 | 02、07、11 |
|  | `game-pm-secretary` | 会議・情報管理 | 01、05、09、12 |
| 品質保証・QA | `game-qa-lead` | QAリード | 06、09、10、11 |
|  | `game-qa-automation` | 自動テスト | 05、06、10、11 |
|  | `game-qa-load-compat` | 負荷・互換性テスト | 10、11 |
|  | `game-qa-usability` | ユーザビリティテスト | 04、09、10 |
| ローカライズ | `game-loc-director` | ローカライズ計画 | 03、07、10、11 |
|  | `game-loc-translator` | 翻訳・字幕 | 07、10 |
|  | `game-loc-culturalize` | カルチャライズ | 01、07、10 |
|  | `game-loc-lqa` | LQA・言語監修 | 10、11 |
| リリース・配信 | `game-release-manager` | リリース管理 | 11、12 |
|  | `game-release-store` | ストアページ | 09、10、11 |
| マーケティング・宣伝 | `game-mkt-director` | マーケティング戦略 | 01、04、09、11 |
|  | `game-mkt-planner` | 宣伝の計画・広告 | 04、09、10、11、12 |
|  | `game-mkt-community` | SNS・コミュニティ | 09、10、11、12 |
|  | `game-mkt-pr` | PR・広報 | 09、11 |
|  | `game-mkt-creative` | 宣伝の制作物 | 04、09、10、11 |
|  | `game-mkt-copy` | コピー | 01、10、11 |
| 販売・出版 | `game-sales-publisher` | 販売計画 | 01、09、11 |
|  | `game-sales-pricing` | 価格戦略 | 01、11、12 |
| 運営・ライブサービス | `game-ops-analyst` | データ分析 | 03、06、10、12 |
|  | `game-ops-cs` | カスタマーサポート | 11、12 |
|  | `game-ops-infra` | インフラ・サーバー運用 | 11、12 |
| 研究開発 | `game-rnd-engineer` | 研究開発 | 02、04 |
| 法務・知的財産 | `game-legal` | 法務・契約 | 01、02、11、12 |
|  | `game-legal-ip` | 知的財産・ライセンス | 01、07、11 |
<!-- group-table:end -->

### 加わる仕事人の呼び方

- **全員を毎回呼ばない**。プロジェクトに要る人だけを、`開発チーム.md` の「使う仕事人」で決める。既定は、中心の35人＋監修（ディレクター職）＋そのゲームに要る専門家
  - 例：1画面のブラウザゲームなら、ネットワーク・サーバー・3D・モーキャプ・ボイス・ローカライズ・販売は呼ばない
  - 例：オンライン対戦なら、`game-tech-network`、`game-tech-backend`、`game-tech-security`、`game-qa-load-compat`、`game-ops-infra` を足す
- **監修・判定の担当**（`game-biz-executive`、`game-design-director`、`game-design-creative-director`、`game-tech-director`、`game-art-director`、`game-audio-director`、`game-story-dialogue-review` など）は、作る担当のあと、ゲートの前に呼ぶ
- **専門の作る担当**（バトル、経済、ネットワーク、作曲、翻訳など）は、中心の仕事人の仕事のうち、その専門の部分を受け持つ。中心の仕事人と同じファイルを書くときは、どちらが書くかを渡すときに決める（例：戦闘の機能仕様は `game-design-combat` が書き、`game-spec-writer` はGDDからつなぐ）
- **宣伝・販売・法務**は、ゲームを外に出すときだけ。出さない（自分で遊ぶだけの）プロジェクトでは呼ばない

## 全体の流れ

```
1 企画 ──[ゲートA：オーナー]──> 2 プリプロ ──> 3 仕様 ──> 4 プロト ──┐
          （プロトで「捨てる」なら 2 か 1 に戻る） <──────────────────┘
4 で縦切りまで ──[ゲートB：オーナー]──> 5 開発開始 ──> 6 システム ⇄ 7 コンテンツ ──> 8 統合・演出
──> 9 アルファ ──[ゲートC：オーナー]──> 10 ベータ ──> 11 QA・最終審査 ──[ゲートD：オーナー]──> リリース ──> 12 保守
```

- 6・7・8 は並べて回す。バックログのタスクごとに、システム → コンテンツ → 統合の順で縦に通す
- 部門の終わりには、必ずゲートの判定をする（`reference/gates.md`）。オーナーのゲート（A〜D）以外は、プロデューサーが判定して `進行表.md` に書く
- 小さなゲーム（数日で作るもの）は、部門をまとめてよい（`reference/gates.md` の「小さなゲームの近道」）。ただし、企画のゲートAとリリースのゲートDは飛ばさない

## 1つの部門の回し方

1. **入る**：`進行表.md` を読み、いまの部門と、前の部門のゲートの結果を確かめる。部門の参考ファイル `reference/NN_*.md` を読む
2. **作る担当を呼ぶ**：部門のファイルの「呼ぶ順」に従う。互いに依存しない担当は**同時に**呼ぶ
3. **見る担当を呼ぶ**：作ったものに、見る担当（レビュー、プレイテスト、判定）を呼ぶ。見る担当には、作った担当の考えや言い訳を渡さない
4. **直す**：指摘を「必ず直す／直したほうがいい」でまとめ、作った担当に戻して直させる（小さな直しはプロデューサーが直してよい）。指摘がぶつかったら、デザインの柱 → オーナーの決め → 出せる品質、の順で決める
5. **ゲート**：部門のゲートの条件を照らす。通ったら `進行表.md` に書き、コミットする。通らなければ、足りないものを挙げて、その部門か前の部門に戻る
6. **オーナーへ**：オーナーのゲートでは、判断に要るもの（短い要約、遊べるビルドの起動方法、スクリーンショット、決めてほしいこと）だけを渡す

## 呼ぶときの渡し方（全員共通）

- **プロジェクトのフォルダ**のパスと、**その仕事のファイル**（読むもの、書く場所）を渡す。仕事人は、自分のファイルの「最初に読むもの」を自分で読む
- やってほしいことを1つに絞る。複数あるなら分けて呼ぶ
- `開発チーム.md` の、その仕事人に関係する追加の観点を渡す
- ほかの仕事人の指摘や、プロデューサーの考えは、必要なもの以外渡さない（特に、見る担当と `game-beta-firsttime` には渡さない）
- 返してほしい形を伝える（仕事人のファイルに書いてある形）

## プロジェクトのフォルダ

`games/<プロジェクト名>/` に作る。フォルダの形、`進行表.md` と `開発チーム.md` の書き方は `reference/project_folder.md`。新しいプロジェクトは、最初にこのフォルダと `進行表.md` を作ってから、企画構想立案の部門に入る。

## 参考ファイル

| ファイル | 中身 |
|---|---|
| `reference/roster.md` | 約250の職種と、それを兼ねる仕事人・参加する部門の名簿 |
| `reference/project_folder.md` | プロジェクトのフォルダの形、`進行表.md`、`開発チーム.md` |
| `reference/gates.md` | ゲートの一覧と判定のしかた、戻り方、小さなゲームの近道 |
| `reference/01_concept.md` | 企画構想立案：企画書の型、呼ぶ順、ゲートA |
| `reference/02_preproduction.md` | プリプロダクション：デザインの柱、コアループ、技術・アート・計画 |
| `reference/03_spec.md` | 仕様書作成：GDDの型、機能仕様の型、パラメータ表 |
| `reference/04_prototype.md` | プロトタイプ作成：問いの立て方、プレイテスト、縦切り、ゲートB |
| `reference/05_production_start.md` | 本格的な開発開始：設計、バックログ、パイプライン |
| `reference/06_systems.md` | ゲームシステム：実装とレビューの回し方 |
| `reference/07_content.md` | コンテンツ制作：レベル、シナリオ、アート、サウンド |
| `reference/08_integration.md` | 統合・演出制作：通しのビルド、演出 |
| `reference/09_alpha.md` | アルファ版：条件、判定、ゲートC |
| `reference/10_beta.md` | ベータ版：バグ表、調整、初見テスト |
| `reference/11_qa_release.md` | 品質保証・最終審査：テスト、審査、リリースの条件、ゲートD |
| `reference/12_maintenance.md` | 保守：不具合受付、パッチ、アップデート |
| `reference/sources.md` | 工程の定義を調べた出典 |
| `tools/gen_agents.py`、`tools/gen_roster.py` | 仕事人のファイル、名簿、この表を作り直すスクリプト（仕事人を直すときは `gen_agents.py` を直して両方を流す） |
