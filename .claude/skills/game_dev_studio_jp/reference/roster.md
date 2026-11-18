# 職種の名簿

現実のゲーム会社の職種を、このスキルの仕事人（`.claude/agents/game-*`）に割り振った表。同じ仕事をする職種は1人の仕事人がまとめて兼ねる。部門をまたいで参加する仕事人もいる（「参加する部門」の列）。

- **★** は、人の体や現場が要る職種。仕事人は手配書・発注書・受け入れの条件までを作り、手配そのものはオーナーが行う
- 外部協力会社は、その仕事の仕事人が発注書を書き、`game-pm-outsourcing` がまとめる。外への連絡と発注はオーナーが行う
- この表と仕事人のファイルは `tools/gen_agents.py` と `tools/gen_roster.py` から作っている。職種や仕事人を足すときは `gen_agents.py` を直して、両方を流し直す

## 経営・事業統括部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 代表取締役 | `game-biz-executive` | 01、04、09、11 |
| エグゼクティブプロデューサー | `game-biz-executive` | 01、04、09、11 |
| 事業責任者 | `game-biz-executive` | 01、04、09、11 |
| 経営企画担当 | `game-biz-planning` | 01、02、12 |
| 事業企画担当 | `game-biz-planning` | 01、02、12 |
| 財務担当 | `game-biz-finance` | 01、02、11、12 |
| 事業開発担当 | `game-biz-planning` | 01、02、12 |

## 企画・ゲームデザイン部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 企画担当者 | `game-concept-planner` | 01 |
| ゲームプランナー | `game-concept-planner` | 01 |
| ゲームディレクター | `game-design-director` | 02、03、04、06、07、08、09、10 |
| クリエイティブディレクター | `game-design-creative-director` | 01、02、04、08、09、11 |
| リードゲームデザイナー | `game-preprod-designer` | 02 |
| ゲームデザイナー | `game-preprod-designer` | 02 |
| システムデザイナー | `game-design-systems` | 02、03、04、06 |
| ゲームプレイデザイナー | `game-design-systems` | 02、03、04、06 |
| レベルデザイナー | `game-content-level` | 07 |
| ワールドデザイナー | `game-design-world` | 02、03、07 |
| クエストデザイナー | `game-design-quest` | 03、07、12 |
| コンバットデザイナー | `game-design-combat` | 03、04、06、10 |
| バトルデザイナー | `game-design-combat` | 03、04、06、10 |
| AIデザイナー | `game-design-ai` | 03、06 |
| 経済システムデザイナー | `game-design-economy` | 03、10、12 |
| アイテムデザイナー | `game-design-economy` | 03、10、12 |
| スキルデザイナー | `game-design-combat` | 03、04、06、10 |
| キャラクター能力設計担当 | `game-design-combat` | 03、04、06、10 |
| ゲームバランスデザイナー | `game-spec-balance` | 03 |
| UXデザイナー | `game-design-ux` | 02、03、04、06、10 |
| UIデザイナー | `game-design-ux` | 02、03、04、06、10 |
| チュートリアルデザイナー | `game-design-ux` | 02、03、04、06、10 |
| ソーシャルシステムデザイナー | `game-design-social` | 03、06、12 |
| イベントデザイナー | `game-design-quest` | 03、07、12 |

## プログラム・技術開発部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| テクニカルディレクター | `game-tech-director` | 02、05、06、09、11 |
| テクニカルアーキテクト | `game-prod-architect` | 05 |
| リードプログラマー | `game-sys-code-review` | 06 |
| ゲームプレイプログラマー | `game-sys-gameplay` | 06 |
| システムプログラマー | `game-tech-engine` | 02、05、06 |
| エンジンエンジニア | `game-tech-engine` | 02、05、06 |
| グラフィックスプログラマー | `game-tech-graphics` | 05、06、08 |
| AIプログラマー | `game-sys-ai` | 06 |
| 物理演算プログラマー | `game-tech-engine` | 02、05、06 |
| ネットワークプログラマー | `game-tech-network` | 02、05、06 |
| サーバーエンジニア | `game-tech-backend` | 05、06、12 |
| バックエンドエンジニア | `game-tech-backend` | 05、06、12 |
| フロントエンドエンジニア | `game-sys-ui` | 06 |
| UIプログラマー | `game-sys-ui` | 06 |
| ツールプログラマー | `game-tech-tools` | 05、07 |
| ビルドエンジニア | `game-prod-pipeline` | 05 |
| データベースエンジニア | `game-tech-backend` | 05、06、12 |
| セキュリティエンジニア | `game-tech-security` | 06、11、12 |
| パフォーマンスエンジニア | `game-tech-performance` | 06、08、10、11 |
| プラットフォームエンジニア | `game-tech-platform` | 02、05、10、11 |
| DevOpsエンジニア | `game-prod-pipeline` | 05 |
| プロトタイププログラマー | `game-proto-programmer` | 04 |

## アート・グラフィック部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| アートディレクター | `game-preprod-art`、`game-art-director` | 02、04、07、08、09、10 |
| リードアーティスト | `game-art-director` | 04、07、08、09、10 |
| コンセプトアーティスト | `game-art-concept` | 01、02、07 |
| キャラクターデザイナー | `game-art-concept` | 01、02、07 |
| 3Dキャラクターモデラー | `game-art-3d` | 07 |
| 背景デザイナー | `game-art-concept` | 01、02、07 |
| 背景モデラー | `game-art-3d` | 07 |
| プロップデザイナー | `game-art-concept` | 01、02、07 |
| プロップモデラー | `game-art-3d` | 07 |
| テクスチャアーティスト | `game-art-3d` | 07 |
| マテリアルアーティスト | `game-art-3d` | 07 |
| ライティングアーティスト | `game-art-lighting` | 07、08 |
| エフェクトアーティスト | `game-art-vfx` | 07、08 |
| UIアーティスト | `game-art-ui` | 07、08 |
| 2Dアーティスト | `game-content-art` | 07 |
| イラストレーター | `game-art-concept` | 01、02、07 |
| テクニカルアーティスト | `game-art-technical` | 02、05、07、08 |
| テクニカルアニメーター | `game-art-technical` | 02、05、07、08 |
| アートアセット管理担当 | `game-content-art` | 07 |

## アニメーション・映像部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| アニメーションディレクター | `game-anim-animator` | 04、07、08 |
| リードアニメーター | `game-anim-animator` | 04、07、08 |
| 3Dアニメーター | `game-anim-animator` | 04、07、08 |
| モーションデザイナー | `game-anim-animator` | 04、07、08 |
| リギングアーティスト | `game-art-technical` | 02、05、07、08 |
| フェイシャルアニメーター | `game-anim-animator` | 04、07、08 |
| モーションキャプチャー担当 | `game-anim-mocap` | 07 |
| ★ モーションキャプチャーアクター | `game-anim-mocap` | 07 |
| カットシーンディレクター | `game-anim-cinematic` | 08 |
| シネマティックアーティスト | `game-anim-cinematic` | 08 |
| VFXアーティスト | `game-art-vfx` | 07、08 |
| コンポジター | `game-anim-cinematic` | 08 |
| 映像編集者 | `game-anim-cinematic` | 08 |

## シナリオ・ナラティブ部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| ナラティブディレクター | `game-story-director` | 01、02、03、07、08 |
| ナラティブデザイナー | `game-story-director` | 01、02、03、07、08 |
| シナリオライター | `game-content-scenario` | 07 |
| メインシナリオライター | `game-content-scenario` | 07 |
| サブシナリオライター | `game-story-quest-writer` | 07 |
| クエストライター | `game-story-quest-writer` | 07 |
| 会話ライター | `game-story-dialogue` | 07 |
| キャラクター設定担当 | `game-story-lore` | 02、07 |
| 世界観設定担当 | `game-story-lore` | 02、07 |
| ロアライター | `game-story-lore` | 02、07 |
| 台詞監修担当 | `game-story-dialogue-review` | 07、10 |

## サウンド・音楽部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| オーディオディレクター | `game-audio-director` | 02、07、08、10 |
| 作曲家 | `game-audio-composer` | 07 |
| 編曲家 | `game-audio-composer` | 07 |
| サウンドデザイナー | `game-content-sound` | 07 |
| ★ フォーリーアーティスト | `game-content-sound` | 07 |
| ★ レコーディングエンジニア | `game-audio-engineer` | 06、08、10 |
| サウンドエンジニア | `game-audio-engineer` | 06、08、10 |
| ミキシングエンジニア | `game-audio-engineer` | 06、08、10 |
| ボイスディレクター | `game-audio-voice` | 07、08 |
| 音声編集担当 | `game-audio-voice` | 07、08 |
| ボイスキャスティング担当 | `game-audio-voice` | 07、08 |
| ★ ボイスアクター | `game-audio-voice` | 07、08 |

## 制作管理部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| ゲームプロデューサー | プロデューサー（メインのClaude）、計画は `game-preprod-producer` | 全部門 |
| ディレクター | `game-design-director` | 02、03、04、06、07、08、09、10 |
| アシスタントディレクター | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| プロジェクトマネージャー | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| プロダクションマネージャー | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| 制作進行担当 | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| スケジュール管理担当 | `game-preprod-producer` | 02 |
| リソースマネージャー | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| 外注管理担当 | `game-pm-outsourcing` | 02、07、11 |
| 会議・情報管理担当 | `game-pm-secretary` | 01、05、09、12 |

## 品質保証・QA部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| QAディレクター | `game-qa-lead` | 06、09、10、11 |
| QAマネージャー | `game-qa-lead` | 06、09、10、11 |
| QAリード | `game-qa-lead` | 06、09、10、11 |
| QAテスター | `game-qa-tester` | 11 |
| デバッグ担当 | `game-qa-tester` | 11 |
| 機能テスト担当 | `game-qa-tester` | 11 |
| 回帰テスト担当 | `game-qa-tester` | 11 |
| 負荷テスト担当 | `game-qa-load-compat` | 10、11 |
| パフォーマンステスト担当 | `game-tech-performance` | 06、08、10、11 |
| 互換性テスト担当 | `game-qa-load-compat` | 10、11 |
| 自動テストエンジニア | `game-qa-automation` | 05、06、10、11 |
| ユーザビリティテスター | `game-qa-usability` | 04、09、10 |
| プレイテスト担当 | `game-proto-playtester` | 04 |
| セキュリティテスター | `game-tech-security` | 06、11、12 |

## ローカライズ部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| ローカライズディレクター | `game-loc-director` | 03、07、10、11 |
| 翻訳者 | `game-loc-translator` | 07、10 |
| 翻訳コーディネーター | `game-loc-director` | 03、07、10、11 |
| カルチャライズ担当 | `game-loc-culturalize` | 01、07、10 |
| LQAテスター | `game-loc-lqa` | 10、11 |
| 言語監修者 | `game-loc-lqa` | 10、11 |
| 字幕制作担当 | `game-loc-translator` | 07、10 |
| 多言語音声制作担当 | `game-audio-voice` | 07、08 |

## リリース・配信部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| リリースマネージャー | `game-release-manager` | 11、12 |
| リリースエンジニア | `game-prod-pipeline` | 05 |
| 認証・審査担当 | `game-qa-compliance` | 11 |
| コンプライアンス担当 | `game-qa-compliance` | 11 |
| 年齢レーティング担当 | `game-qa-compliance` | 11 |
| 配信管理担当 | `game-release-manager` | 11、12 |
| ストア管理担当 | `game-release-store` | 09、10、11 |
| データ管理担当 | `game-release-manager` | 11、12 |

## マーケティング・宣伝部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| マーケティングディレクター | `game-mkt-director` | 01、04、09、11 |
| マーケティングプランナー | `game-mkt-planner` | 04、09、10、11、12 |
| マーケティング担当 | `game-mkt-planner` | 04、09、10、11、12 |
| 市場調査担当 | `game-concept-market` | 01 |
| 広告運用担当 | `game-mkt-planner` | 04、09、10、11、12 |
| SNSマーケター | `game-mkt-community` | 09、10、11、12 |
| PR担当 | `game-mkt-pr` | 09、11 |
| 広報担当 | `game-mkt-pr` | 09、11 |
| ブランドマネージャー | `game-mkt-director` | 01、04、09、11 |
| コンテンツマーケター | `game-mkt-creative` | 04、09、10、11 |
| インフルエンサーマーケター | `game-mkt-community` | 09、10、11、12 |
| コミュニティマネージャー | `game-mkt-community` | 09、10、11、12 |
| イベントプランナー | `game-mkt-planner` | 04、09、10、11、12 |
| トレーラー監督 | `game-mkt-creative` | 04、09、10、11 |
| モーショングラフィックスデザイナー | `game-mkt-creative` | 04、09、10、11 |
| グラフィックデザイナー | `game-mkt-creative` | 04、09、10、11 |
| Webデザイナー | `game-mkt-creative` | 04、09、10、11 |
| コピーライター | `game-mkt-copy` | 01、10、11 |
| ★ カメラマン | `game-mkt-creative` | 04、09、10、11 |

## 販売・出版部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| パブリッシャー | `game-sales-publisher` | 01、09、11 |
| セールスマネージャー | `game-sales-publisher` | 01、09、11 |
| 営業担当 | `game-sales-publisher` | 01、09、11 |
| 流通管理担当 | `game-sales-publisher` | 01、09、11 |
| 価格戦略担当 | `game-sales-pricing` | 01、11、12 |
| ライセンス担当 | `game-legal-ip` | 01、07、11 |
| 商品企画担当 | `game-biz-planning` | 01、02、12 |

## 運営・ライブサービス部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| ライブオペレーションディレクター | `game-ops-live` | 12 |
| ゲーム運営プランナー | `game-ops-live` | 12 |
| 運営担当 | `game-ops-live` | 12 |
| ゲームバランス担当 | `game-spec-balance` | 03 |
| データアナリスト | `game-ops-analyst` | 03、06、10、12 |
| ゲームアナリスト | `game-ops-analyst` | 03、06、10、12 |
| カスタマーサポート | `game-ops-cs` | 11、12 |
| 不正対策担当 | `game-tech-security` | 06、11、12 |
| サーバー運用担当 | `game-ops-infra` | 11、12 |
| インフラエンジニア | `game-ops-infra` | 11、12 |
| SREエンジニア | `game-ops-infra` | 11、12 |
| データベース管理者 | `game-ops-infra` | 11、12 |

## 研究開発・R&D部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 研究開発エンジニア | `game-rnd-engineer` | 02、04 |
| AI研究者 | `game-rnd-engineer` | 02、04 |
| 機械学習エンジニア | `game-rnd-engineer` | 02、04 |
| データサイエンティスト | `game-ops-analyst` | 03、06、10、12 |

## 人事・総務・経理部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 人事担当 | プロデューサー（メインのClaude）：`開発チーム.md` で、プロジェクトに呼ぶ仕事人を選ぶ | — |
| 採用担当 | プロデューサー（メインのClaude）：足りない役割があれば、新しい仕事人を `.claude/agents/` に足す | — |
| 教育担当 | `game-pm-secretary` | 01、05、09、12 |
| 経理担当 | `game-biz-finance` | 01、02、11、12 |
| 財務担当 | `game-biz-finance` | 01、02、11、12 |
| 総務担当 | 置かない：AIのチームには、事務所・備品の仕事がない | — |
| 施設管理担当 | 置かない：AIのチームには、建物・設備の仕事がない | — |

## 法務・知的財産部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 法務担当 | `game-legal` | 01、02、11、12 |
| 知的財産担当 | `game-legal-ip` | 01、07、11 |
| 契約管理担当 | `game-legal` | 01、02、11、12 |
| 著作権管理担当 | `game-legal-ip` | 01、07、11 |
| 商標管理担当 | `game-legal-ip` | 01、07、11 |

## 社内IT・調達部門

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 社内SE | 置かない：作業の環境はクラウドのコンテナで、社内の機器がない | — |
| ネットワーク管理者 | 置かない：社内のネットワークがない（ゲームの通信は `game-tech-network`） | — |
| 情報セキュリティ担当 | `game-tech-security` | 06、11、12 |
| 購買担当 | `game-pm-outsourcing` | 02、07、11 |
| 調達担当 | `game-pm-outsourcing` | 02、07、11 |

## 外部協力会社・専門業者

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| 開発受託会社スタッフ | `game-pm-outsourcing` | 02、07、11 |
| 3D制作会社スタッフ | `game-art-3d` | 07 |
| アニメーション制作会社スタッフ | `game-anim-animator` | 04、07、08 |
| イラスト制作会社スタッフ | `game-art-concept` | 01、02、07 |
| 音楽制作会社スタッフ | `game-audio-composer` | 07 |
| 音響制作会社スタッフ | `game-audio-engineer` | 06、08、10 |
| ★ 声優 | `game-audio-voice` | 07、08 |
| 翻訳会社スタッフ | `game-loc-translator` | 07、10 |
| QA専門会社スタッフ | `game-qa-tester` | 11 |
| 広告代理店スタッフ | `game-mkt-planner` | 04、09、10、11、12 |
| PR会社スタッフ | `game-mkt-pr` | 09、11 |
| 映像制作会社スタッフ | `game-mkt-creative` | 04、09、10、11 |
| サーバー事業者スタッフ | `game-ops-infra` | 11、12 |
| セキュリティ会社スタッフ | `game-tech-security` | 06、11、12 |
| 法律事務所スタッフ | `game-legal` | 01、02、11、12 |

## プロジェクト内の役職・職位

| 職種 | 仕事人 | 参加する部門 |
|---|---|---|
| エグゼクティブプロデューサー | `game-biz-executive` | 01、04、09、11 |
| プロデューサー | プロデューサー（メインのClaude）、計画は `game-preprod-producer` | 全部門 |
| ゲームディレクター | `game-design-director` | 02、03、04、06、07、08、09、10 |
| アシスタントディレクター | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| プロジェクトマネージャー | `game-pm-manager` | 02、05、06、07、08、09、10、11 |
| テクニカルディレクター | `game-tech-director` | 02、05、06、09、11 |
| アートディレクター | `game-preprod-art`、`game-art-director` | 02、04、07、08、09、10 |
| ナラティブディレクター | `game-story-director` | 01、02、03、07、08 |
| リードゲームデザイナー | `game-preprod-designer` | 02 |
| リードプログラマー | `game-sys-code-review` | 06 |
| リードアーティスト | `game-art-director` | 04、07、08、09、10 |
| リードアニメーター | `game-anim-animator` | 04、07、08 |
| リードQA | `game-qa-lead` | 06、09、10、11 |
| チームリーダー | 職位：部門でいちばん先に呼ぶ担当（下の「職位の扱い」） | — |
| シニアスタッフ | 職位：難しい仕事は、その職種の担当に「シニアとして」と観点を足して渡す | — |
| スタッフ | 職位：各部門の作る担当 | — |

## 職位の扱い

| 職位 | このスキルでの扱い |
|---|---|
| エグゼクティブプロデューサー | `game-biz-executive`。オーナーのゲートの前に事業の判定を出す |
| プロデューサー | メインのClaude。部門を回し、ゲートを判定し、進行表を書く |
| ディレクター職（ゲーム、テクニカル、アート、ナラティブ、オーディオ、QA、ローカライズ、マーケティング） | 監修・判定の担当。部門の終わり（ゲート）の前に呼ぶ |
| リード職（ゲームデザイン、プログラム、アート、アニメ、QA） | 部門の中で最初に呼んで方針を決める担当か、レビューの担当 |
| チームリーダー | 部門ごとに「最初に呼ぶ担当」が、その部門のリーダー（各部門のファイルの「呼ぶ順」の1番） |
| シニアスタッフ／スタッフ | 作る担当。難しい仕事には、渡すときに観点を足す |
