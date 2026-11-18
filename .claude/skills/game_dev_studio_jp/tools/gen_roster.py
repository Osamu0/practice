import sys, os, re
sys.argv = [sys.argv[0], "/dev/null"] + sys.argv[1:]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import gen_agents as gen2
from gen_agents import ALL, PHASE_NAME
REPO = sys.argv[2]

CATS = [
("経営・事業統括部門", "代表取締役 エグゼクティブプロデューサー 事業責任者 経営企画担当 事業企画担当 財務担当 事業開発担当"),
("企画・ゲームデザイン部門", "企画担当者 ゲームプランナー ゲームディレクター クリエイティブディレクター リードゲームデザイナー ゲームデザイナー システムデザイナー ゲームプレイデザイナー レベルデザイナー ワールドデザイナー クエストデザイナー コンバットデザイナー バトルデザイナー AIデザイナー 経済システムデザイナー アイテムデザイナー スキルデザイナー キャラクター能力設計担当 ゲームバランスデザイナー UXデザイナー UIデザイナー チュートリアルデザイナー ソーシャルシステムデザイナー イベントデザイナー"),
("プログラム・技術開発部門", "テクニカルディレクター テクニカルアーキテクト リードプログラマー ゲームプレイプログラマー システムプログラマー エンジンエンジニア グラフィックスプログラマー AIプログラマー 物理演算プログラマー ネットワークプログラマー サーバーエンジニア バックエンドエンジニア フロントエンドエンジニア UIプログラマー ツールプログラマー ビルドエンジニア データベースエンジニア セキュリティエンジニア パフォーマンスエンジニア プラットフォームエンジニア DevOpsエンジニア プロトタイププログラマー"),
("アート・グラフィック部門", "アートディレクター リードアーティスト コンセプトアーティスト キャラクターデザイナー 3Dキャラクターモデラー 背景デザイナー 背景モデラー プロップデザイナー プロップモデラー テクスチャアーティスト マテリアルアーティスト ライティングアーティスト エフェクトアーティスト UIアーティスト 2Dアーティスト イラストレーター テクニカルアーティスト テクニカルアニメーター アートアセット管理担当"),
("アニメーション・映像部門", "アニメーションディレクター リードアニメーター 3Dアニメーター モーションデザイナー リギングアーティスト フェイシャルアニメーター モーションキャプチャー担当 モーションキャプチャーアクター カットシーンディレクター シネマティックアーティスト VFXアーティスト コンポジター 映像編集者"),
("シナリオ・ナラティブ部門", "ナラティブディレクター ナラティブデザイナー シナリオライター メインシナリオライター サブシナリオライター クエストライター 会話ライター キャラクター設定担当 世界観設定担当 ロアライター 台詞監修担当"),
("サウンド・音楽部門", "オーディオディレクター 作曲家 編曲家 サウンドデザイナー フォーリーアーティスト レコーディングエンジニア サウンドエンジニア ミキシングエンジニア ボイスディレクター 音声編集担当 ボイスキャスティング担当 ボイスアクター"),
("制作管理部門", "ゲームプロデューサー ディレクター アシスタントディレクター プロジェクトマネージャー プロダクションマネージャー 制作進行担当 スケジュール管理担当 リソースマネージャー 外注管理担当 会議・情報管理担当"),
("品質保証・QA部門", "QAディレクター QAマネージャー QAリード QAテスター デバッグ担当 機能テスト担当 回帰テスト担当 負荷テスト担当 パフォーマンステスト担当 互換性テスト担当 自動テストエンジニア ユーザビリティテスター プレイテスト担当 セキュリティテスター"),
("ローカライズ部門", "ローカライズディレクター 翻訳者 翻訳コーディネーター カルチャライズ担当 LQAテスター 言語監修者 字幕制作担当 多言語音声制作担当"),
("リリース・配信部門", "リリースマネージャー リリースエンジニア 認証・審査担当 コンプライアンス担当 年齢レーティング担当 配信管理担当 ストア管理担当 データ管理担当"),
("マーケティング・宣伝部門", "マーケティングディレクター マーケティングプランナー マーケティング担当 市場調査担当 広告運用担当 SNSマーケター PR担当 広報担当 ブランドマネージャー コンテンツマーケター インフルエンサーマーケター コミュニティマネージャー イベントプランナー トレーラー監督 モーショングラフィックスデザイナー グラフィックデザイナー Webデザイナー コピーライター カメラマン"),
("販売・出版部門", "パブリッシャー セールスマネージャー 営業担当 流通管理担当 価格戦略担当 ライセンス担当 商品企画担当"),
("運営・ライブサービス部門", "ライブオペレーションディレクター ゲーム運営プランナー 運営担当 ゲームバランス担当 データアナリスト ゲームアナリスト カスタマーサポート 不正対策担当 サーバー運用担当 インフラエンジニア SREエンジニア データベース管理者"),
("研究開発・R&D部門", "研究開発エンジニア AI研究者 機械学習エンジニア データサイエンティスト"),
("人事・総務・経理部門", "人事担当 採用担当 教育担当 経理担当 財務担当 総務担当 施設管理担当"),
("法務・知的財産部門", "法務担当 知的財産担当 契約管理担当 著作権管理担当 商標管理担当"),
("社内IT・調達部門", "社内SE ネットワーク管理者 情報セキュリティ担当 購買担当 調達担当"),
("外部協力会社・専門業者", "開発受託会社スタッフ 3D制作会社スタッフ アニメーション制作会社スタッフ イラスト制作会社スタッフ 音楽制作会社スタッフ 音響制作会社スタッフ 声優 翻訳会社スタッフ QA専門会社スタッフ 広告代理店スタッフ PR会社スタッフ 映像制作会社スタッフ サーバー事業者スタッフ セキュリティ会社スタッフ 法律事務所スタッフ"),
("プロジェクト内の役職・職位", "エグゼクティブプロデューサー プロデューサー ゲームディレクター アシスタントディレクター プロジェクトマネージャー テクニカルディレクター アートディレクター ナラティブディレクター リードゲームデザイナー リードプログラマー リードアーティスト リードアニメーター リードQA チームリーダー シニアスタッフ スタッフ"),
]

MANUAL = {
 "人事担当": "プロデューサー（メインのClaude）：`開発チーム.md` で、プロジェクトに呼ぶ仕事人を選ぶ",
 "採用担当": "プロデューサー（メインのClaude）：足りない役割があれば、新しい仕事人を `.claude/agents/` に足す",
 "総務担当": "置かない：AIのチームには、事務所・備品の仕事がない",
 "施設管理担当": "置かない：AIのチームには、建物・設備の仕事がない",
 "社内SE": "置かない：作業の環境はクラウドのコンテナで、社内の機器がない",
 "ネットワーク管理者": "置かない：社内のネットワークがない（ゲームの通信は `game-tech-network`）",
 "チームリーダー": "職位：部門でいちばん先に呼ぶ担当（下の「職位の扱い」）",
 "シニアスタッフ": "職位：難しい仕事は、その職種の担当に「シニアとして」と観点を足して渡す",
 "スタッフ": "職位：各部門の作る担当",
}
EXTERNAL = {"モーションキャプチャーアクター","ボイスアクター","声優","カメラマン","フォーリーアーティスト","レコーディングエンジニア"}

owner = {}
for a in ALL:
    for j in a["jobs"]:
        owner.setdefault(j, []).append(a)
def phases_of(a):
    return list(a["phases"]) if isinstance(a["phases"], dict) else a["phases"]

missing = []
lines = ["# 職種の名簿", "",
 "現実のゲーム会社の職種を、このスキルの仕事人（`.claude/agents/game-*`）に割り振った表。同じ仕事をする職種は1人の仕事人がまとめて兼ねる。部門をまたいで参加する仕事人もいる（「参加する部門」の列）。",
 "",
 "- **★** は、人の体や現場が要る職種。仕事人は手配書・発注書・受け入れの条件までを作り、手配そのものはオーナーが行う",
 "- 外部協力会社は、その仕事の仕事人が発注書を書き、`game-pm-outsourcing` がまとめる。外への連絡と発注はオーナーが行う",
 "- この表と仕事人のファイルは `tools/gen_agents.py` と `tools/gen_roster.py` から作っている。職種や仕事人を足すときは `gen_agents.py` を直して、両方を流し直す",
 ""]
for cat, titles in CATS:
    lines += [f"## {cat}", "", "| 職種 | 仕事人 | 参加する部門 |", "|---|---|---|"]
    for t in titles.split():
        star = "★ " if t in EXTERNAL else ""
        if t in ("ゲームプロデューサー", "プロデューサー"):
            lines.append(f"| {t} | プロデューサー（メインのClaude）、計画は `game-preprod-producer` | 全部門 |")
        elif t in owner:
            ags = owner[t]
            ps = sorted({p for a in ags for p in phases_of(a)})
            lines.append(f"| {star}{t} | " + "、".join(f"`{a['name']}`" for a in ags) + " | " + "、".join(ps) + " |")
        elif t in MANUAL:
            lines.append(f"| {t} | {MANUAL[t]} | — |")
        else:
            missing.append(t)
    lines.append("")
lines += ["## 職位の扱い", "",
 "| 職位 | このスキルでの扱い |", "|---|---|",
 "| エグゼクティブプロデューサー | `game-biz-executive`。オーナーのゲートの前に事業の判定を出す |",
 "| プロデューサー | メインのClaude。部門を回し、ゲートを判定し、進行表を書く |",
 "| ディレクター職（ゲーム、テクニカル、アート、ナラティブ、オーディオ、QA、ローカライズ、マーケティング） | 監修・判定の担当。部門の終わり（ゲート）の前に呼ぶ |",
 "| リード職（ゲームデザイン、プログラム、アート、アニメ、QA） | 部門の中で最初に呼んで方針を決める担当か、レビューの担当 |",
 "| チームリーダー | 部門ごとに「最初に呼ぶ担当」が、その部門のリーダー（各部門のファイルの「呼ぶ順」の1番） |",
 "| シニアスタッフ／スタッフ | 作る担当。難しい仕事には、渡すときに観点を足す |",
 ""]
if missing:
    print("MISSING:", missing); sys.exit(1)
open(os.path.join(REPO, ".claude/skills/game_dev_studio_jp/reference/roster.md"), "w").write("\n".join(lines))

# 部門ごとのメンバー表（SKILL.md 用）と、各部門ファイルに足す節
by_phase = {p: [] for p in PHASE_NAME}
for a in ALL:
    if a["core"]:
        by_phase[a["dept"]].append((a, None))
    else:
        for p, t in a["phases"].items():
            by_phase[p].append((a, t))

def short(a):
    return a["title"].split("：", 1)[1]

sk = ["| # | 部門 | 中心の仕事人 | 加わる仕事人 |", "|---|---|---|---|"]
for p, name in PHASE_NAME.items():
    core = "、".join(f"`{a['name']}`" for a, t in by_phase[p] if t is None)
    extra = "、".join(f"`{a['name']}`" for a, t in by_phase[p] if t is not None)
    sk.append(f"| {int(p)} | {name} | {core} | {extra} |")
SKILL_PHASE = "\n".join(sk)

# 各部門ファイルへ
BEGIN, END = "<!-- members:begin -->", "<!-- members:end -->"
for p, fname in gen2.DEPT.items():
    path = os.path.join(REPO, ".claude/skills/game_dev_studio_jp/reference", fname)
    body = open(path).read()
    sec = [BEGIN, "## この部門に加わる仕事人", "",
           "中心の仕事人（上の「呼ぶ順」）に加えて、プロジェクトに要るときに呼ぶ。`開発チーム.md` で使わないと決めた仕事人は呼ばない。", "",
           "| 仕事人 | 職種 | この部門でやること |", "|---|---|---|"]
    for a, t in by_phase[p]:
        if t is None: continue
        sec.append(f"| `{a['name']}` | {'、'.join(a['jobs'])} | {t} |")
    sec += ["", END]
    s = "\n".join(sec)
    if BEGIN in body:
        body = re.sub(re.escape(BEGIN)+".*?"+re.escape(END), s, body, flags=re.S)
    else:
        body = body.rstrip("\n") + "\n\n" + s + "\n"
    open(path, "w").write(body)
cnt = sum(len(v) for v in by_phase.values())
print("roster ok; agents", len(ALL), "phase slots", cnt)

GROUP = [("経営・事業","game-biz-"),("企画・ゲームデザイン","game-design-"),("プログラム・技術","game-tech-"),("アート・グラフィック","game-art-"),("アニメーション・映像","game-anim-"),("シナリオ・ナラティブ","game-story-"),("サウンド・音楽","game-audio-"),("制作管理","game-pm-"),("品質保証・QA","game-qa-lead game-qa-automation game-qa-load-compat game-qa-usability"),("ローカライズ","game-loc-"),("リリース・配信","game-release-"),("マーケティング・宣伝","game-mkt-"),("販売・出版","game-sales-"),("運営・ライブサービス","game-ops-analyst game-ops-cs game-ops-infra"),("研究開発","game-rnd-"),("法務・知的財産","game-legal")]
g = ["| 職種の部門 | 仕事人 | 役割 | 参加する部門 |", "|---|---|---|---|"]
for gname, pref in GROUP:
    first = True
    for a in ALL:
        if a["core"]: continue
        keys = pref.split()
        ok = a["name"] in keys if len(keys) > 1 else a["name"].startswith(pref)
        if not ok: continue
        g.append(f"| {gname if first else ''} | `{a['name']}` | {short(a)} | {'、'.join(a['phases'])} |")
        first = False
SKILL_GROUP = "\n".join(g)
sp = os.path.join(REPO, ".claude/skills/game_dev_studio_jp/SKILL.md")
sb = open(sp).read()
for tag, txt in (("phase-table", SKILL_PHASE), ("group-table", SKILL_GROUP)):
    b, e = f"<!-- {tag}:begin -->", f"<!-- {tag}:end -->"
    sb = re.sub(re.escape(b) + ".*?" + re.escape(e), b + "\n" + txt + "\n" + e, sb, flags=re.S)
open(sp, "w").write(sb)
print("groups", len(g) - 2)
