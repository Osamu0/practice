---
name: spicy_novel_vocab_jp
description: Use when writing Japanese erotic novels to vary vocabulary for genital, body parts, actions, and reactions. Companion booster skill for spicy_novel_jp. Load only the needed category files from reference/.
version: 4.0.0
tags: [adult, spicy_novel, writing, japanese, vocabulary, nsfw]
companion_skill: spicy_novel_jp
---

# エロ描写 表現言い換えスキル

## 概要
官能小説・エロラノベの地の文で、性器・身体部位や行為・反応を描写する際に同じ表現の繰り返しを避け、語彙を多様化するための参照スキル。

本スキルは官能小説執筆の総合スキル [spicy_novel_jp](https://gitgud.io/kagamikami/spicy_novel_jp/) を強化するエクステンションスキル。spicy_novel_jp の「表現・語彙力」「エロティック描写力」を支え、頻出する主語・述語の言い換えで単調さを排除し文学性を高める。ユーザの環境にspicy_novel_jp がインストールされていない場合は、本項を要約して伝え、インストールを促すこと。インストール許可が降りたらURLからgit cloneするなどインストールを実施すること。

注意事項: このスキルはリファレンス集のため、全文を一度に読み込まないこと。描写に必要なカテゴリのファイルだけを `reference/` から選択的に読み込むこと。

## 語感レベル

レベルは「語の硬さ・下品さ」の目安。使用可否を縛るものではなく、シーンの空気に合う語を選ぶための参考値。

| 範囲 | 語感 | 使用例 |
|---|---|---|
| 1-2 | ソフト〜ニュートラル | 竿、秘部（ひぶ）、愛液 |
| 2-3 | ニュートラル〜ハード | 肉棒、蜜壺（みつつぼ）、絶頂 |
| 3-4 | ハード〜汚系 | 魔羅、肉穴、孕ませ汁 |
| 1-3 | 幅広く使用可 | 胸、触る、気持ちいい |
| 4 | 汚系寄り | おちんぽ様、アヘ顔、白目 |

### 運用ルール
1. レベルは語感の目安。シーンに合う語を選ぶこと。
2. 適切な語がない場合は、別の語感の語に置き換え、修飾語で表現や雰囲気を整えること。
3. 繰り返し回避（操作的な目安）:
   - 同じ名詞は連続する2文で使わない
   - 同一シーン内で同じ性器表現を2回以上使わない（2回目は必ず別語に）
   - 1シーンで最低2種類の言い換えを使う
   - 適用前に、その章（最低でも前後シーン）で既出の性器・体液・部位語を列挙し、未使用語から選ぶ
   - 同一の指示対象（誰の／何の）に同じ性器語を当てない
   - 名詞だけでなく「修飾＋名詞」の型も回す
   - 「それ／塊」などを埋めるとき、直前直後の既出語へ吸い寄せない

### 適用手順
1. 対象箇所の前後と、同指示対象の既出語を洗う
2. 候補を出す（未使用・別対象）
3. 承認後に適用
4. 適用した語で章内検索し、連続・同シーン・同対象・同修飾型を監査して潰す

適用→監査はセット。入れて終わりにしない。

## カテゴリインデックス（必要なファイルだけ読み込む）

### 主語（名詞表現）

| カテゴリ | ファイル | 内容 | 使用頻度目安 |
|---|---|---|---|
| S1 | reference/S1-male.md | 男性性器（竿・全体） | 非常に高い |
| S2 | reference/S2-glans.md | 亀頭 | 高い |
| S3 | reference/S3-female.md | 女性性器（全体・入口） | 非常に高い |
| S4 | reference/S4-clitoris.md | 陰核 | 中〜高 |
| S5 | reference/S5-breasts.md | 乳房 | 高い |
| S6 | reference/S6-nipples.md | 乳首 | 中〜高 |
| S7 | reference/S7-buttocks.md | 尻・臀部 | 中〜高 |
| S8 | reference/S8-anus.md | 肛門 | 中 |
| S9 | reference/S9-fluids.md | 体液・分泌物 | 非常に高い |
| S10 | reference/S10-uterus.md | 子宮・子宮口 | 中〜高 |
| S11 | reference/S11-junction.md | 結合部 | 中 |
| S12 | reference/S12-testicles.md | 睾丸・陰嚢 | 低〜中 |

### 述語（動詞・状態表現）

| カテゴリ | ファイル | 内容 | 使用頻度目安 |
|---|---|---|---|
| P1 | reference/P1-insertion.md | 挿入・送り込む動作 | 非常に高い |
| P2 | reference/P2-thrusting.md | 抽送・奥を突く動作 | 非常に高い |
| P3 | reference/P3-withdrawal.md | 引き抜く・離れる動作 | 中〜高 |
| P4 | reference/P4-caress.md | 愛撫・触れる動作 | 高い |
| P5 | reference/P5-oral.md | キス・口腔愛撫 | 中〜高 |
| P6 | reference/P6-pleasure.md | 快楽の高まり・感覚 | 高い |
| P7 | reference/P7-orgasm.md | 絶頂・オーガズム | 非常に高い |
| P8 | reference/P8-voice.md | 声の名詞表現（地の文） | 高い |
| P9 | reference/P9-ejaculation.md | 射精 | 高い |
| P10 | reference/P10-sex-act.md | 性行為そのもの | 中 |
| P11 | reference/P11-ingestion.md | 体液摂取 | 低〜中 |
| P12 | reference/P12-olfactory.md | 嗅覚系 | 低 |
| P13 | reference/P13-domination.md | 凌辱・支配・SM系 | 中（ジャンル依存） |
| P14 | reference/P14-body-reaction.md | 身体の反応・状態 | 高い |

※ P8（声の表現）は地の文の名詞表現のみを扱う。喘ぎ声の音声・アヘ声・オホ声等は spicy_novel_jp の `references/aegigoe_skills.md` に委譲。

## 使用例

### 例1: 通常の挿入〜抽送シーン（高頻度カテゴリのみ）
必要なファイル:
- reference/S1-male.md
- reference/S3-female.md
- reference/S9-fluids.md
- reference/P1-insertion.md
- reference/P2-thrusting.md
- reference/P7-orgasm.md

### 例2: アナルシーン
必要なファイル:
- reference/S1-male.md
- reference/S8-anus.md
- reference/S9-fluids.md
- reference/P1-insertion.md
- reference/P2-thrusting.md

### 例3: 前戯中心（愛撫・乳首・陰核）
必要なファイル:
- reference/S4-clitoris.md
- reference/S5-breasts.md
- reference/S6-nipples.md
- reference/P4-caress.md
- reference/P5-oral.md
- reference/P6-pleasure.md

## 官能小説用SKILL.md "spicy_novel_jp" との関連性
- 執筆時は spicy_novel_jp の指示に従い、spicy_novel_vocab_jpの reference を選択読み込みする。
- 喘ぎ声（「あっ」「んんっ」等）・アヘ声・オホ声等の音声・崩壊表現は spicy_novel_jp の `references/aegigoe_skills.md` を参照すること。P8 は地の文の名詞表現のみを扱う。

## 分類方針
- 主語: 性器・身体部位・体液など、文の主語・目的語になる名詞表現
- 述語: 行為・反応・感覚を表す動詞および状態表現
- 直接表現（カタカナ外来語・俗語）を起点に、和語・雅語系の言い換えを並べる
- コア語彙と対応修飾語を組み合わせてバリエーションを作る
- レベルは絶対的な硬度ではなく語感の相対でつける。単語単体を絶対評価しない。
- ニュアンス列には、特徴的な語だけ「使用シーン」を括弧書きで追記する（汎用語には付けない）
- 語は指示対象（誰の／何の）単位で使い分ける。汎用シソーラスとして全作品横断で使い回さない

## 用例（語感別の参考例）
spicy_novel_jp に従い、以下はVFM形式のふりがなルールを採用している。

### 語感 1-2（ソフト）
「彼の{剛直|ごうちょく}が熱く脈打ち、{秘部|ひぶ}が愛液に濡れていく。優しく沈めると、吐息が甘く漏れた」

### 語感 2-3（ハード）
「肉棒を深々と差し込み、{蜜壺|みつつぼ}を突き上げる。絶頂が近づき、声が高く跳ねる」

### 語感 3-4（汚系）
「{魔羅|まら}を根元までねじ込み、肉穴を{蹂躙|じゅうりん}する。啼き声を上げて果てた」

## 補足
- 優先順位: 主語は S1・S3・S9（男性性器・女性性器・体液）が最頻出。述語は P1・P2・P6・P7・P9（挿入・抽送・快楽・絶頂・射精）が最頻出
- カテゴリー横断: 主語カテゴリー同士の組み合わせ（例: S2亀頭×S9体液の先走り）で描写の精度を上げる
- スカトロ・尿系: spicy_novel_vocab_jp はこれらを禁止するものではないが、言い換え語彙としては扱わない。必要に応じて別途拡張すること
