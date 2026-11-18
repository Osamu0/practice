"""数値の破綻（詰み・最強の一択・無限稼ぎ／実質の上乗せ）を確かめる（game-spec-balance、2026-11-18）。

使い方：  python3 03_仕様/tools/balance_check.py            （全部。数分かかる）
          python3 03_仕様/tools/balance_check.py quick      （盤面の探しを浅くする）
値は ../パラメータ表.csv から読む。課題の盤面はすべて【仮】（課題の中身は 07 で作る。ここでは数値を試すためだけの形）。
"""
import itertools
import os
import re
import sys

from rules_sim import P, Cfg, build, solve, fmt_act, pv, WET_MATERIAL

QUICK = len(sys.argv) > 1 and sys.argv[1] == "quick"
DEPTH = 8 if QUICK else 10
problems = []


def say(*a):
    print(*a)


def problem(tag, msg):
    problems.append((tag, msg))
    say(f"  !! [{tag}] {msg}")


PARTS = ["plank", "ironBar", "stake", "rope", "longRope", "pulley", "chain", "spring", "ironSpring", "leafSpring",
         "stoneWeight", "ironWeight", "pebble", "sandbag", "flint", "striker", "oilCloth", "fuse"]
MATERIAL = {"plank": "木", "ironBar": "鉄", "stake": "木", "rope": "縄布", "longRope": "縄布", "pulley": "木", "chain": "鉄",
            "spring": "真鍮", "ironSpring": "鉄", "leafSpring": "木", "stoneWeight": "石", "ironWeight": "鉄", "pebble": "石",
            "sandbag": "縄布", "flint": "火打ち石", "striker": "鉄", "oilCloth": "縄布", "fuse": "縄布"}
SPRINGS = ["spring", "ironSpring", "leafSpring"]
WEIGHTS = ["pebble", "sandbag", "stoneWeight", "ironWeight"]
MAX_USEFUL = P["board.size"] - 1  # 7×7 で、これより遠くへは飛べない

# ------------------------------------------------------------------
say("=" * 70)
say("1. 弾む距離の表（弾む距離＝max(0, 強さ−重さ)）と、弾まない詰み")
say("=" * 70)


def wt(part, laws):
    w = pv(part, "weight")
    if "longRain" in laws and part in WET_MATERIAL:
        w += P["law.longRain.wetWeightAdd"]
    return w


conds = [
    ("掟なし", set(), set(), set()),
    ("長雨", {"longRain"}, set(), set()),
    ("鉄が採れない", {"noIron"}, set(), {"鉄"}),
    ("長雨＋鉄が採れない", {"longRain", "noIron"}, set(), {"鉄"}),
    ("せっかち", set(), {"hasty"}, set()),
]
for mat in ["木", "縄布", "真鍮", "石", "火打ち石"]:
    conds.append((f"素材「{mat}」が採れない（仮の掟）", set(), set(), {mat}))
    conds.append((f"長雨＋素材「{mat}」が採れない", {"longRain"}, set(), {mat}))

for name, laws, traits, nomat in conds:
    add = P["trait.hasty.springPowerAdd"] if "hasty" in traits else 0
    sp = [s for s in SPRINGS if MATERIAL[s] not in nomat]
    ws = [w for w in WEIGHTS if MATERIAL[w] not in nomat]
    rows = []
    for s in sp:
        pw = pv(s, "springPower") + add
        d = {w: max(0, pw - wt(w, laws)) for w in ws}
        d["当主"] = max(0, pw - P["leader.weight"])
        d["荷(仮)"] = max(0, pw - P["challenge.cargo.weight"])
        rows.append((s, pw, d))
    if name == "掟なし" or name == "せっかち" or name == "長雨" or name == "鉄が採れない":
        say(f"\n[{name}]  ばね（強さ）: " + "  ".join(f"{w}" for w in ws + ["当主", "荷(仮)"]))
        for s, pw, d in rows:
            say(f"  {s:11s}({pw}): " + "  ".join(f"{d[w]:>2d}" for w in ws + ["当主", "荷(仮)"]))
    # 詰み1：残ったばねが、残った重りのどれも弾まない
    for s, pw, d in rows:
        if all(d[w] == 0 for w in ws):
            problem("詰み", f"{name}：{s} はどの重りも弾まない")
    # 詰み2：残った重りが、残ったばねのどれでも弾まない
    for w in ws:
        if rows and all(d[w] == 0 for s, pw, d in rows):
            problem("詰み", f"{name}：{w} はどのばねでも弾まない")
    # 詰み3：当主を1段より高く上げられるばねがない（登れない段差を、ばねで越える道が消える）
    if not any(d["当主"] >= P["leader.climbHeight"] + 1 for s, pw, d in rows):
        problem("詰み(候補)", f"{name}：当主を{P['leader.climbHeight'] + 1}マス以上弾ませるばねがない（ばね以外の道があれば詰みではない）")
    # 強すぎ：盤の端から端より遠くへ飛ぶ組み合わせ（意味がない＝強さの差が消える）
    for s, pw, d in rows:
        over = [w for w in ws if d[w] > MAX_USEFUL]
        if over:
            say(f"  注：{name}：{s} は {over} を {MAX_USEFUL} マスより遠くへ飛ばす（盤の壁で止まるので差がなくなる）")
    # 当主の打ち上げと落ちて死ぬ高さ
    for s, pw, d in rows:
        if d["当主"] >= P["leader.fallDeathHeight"] + (0):
            say(f"  注：{name}：{s} で当主は {d['当主']} マス上がる → 同じ場所へ落ちると落ちて死ぬ高さ（{P['leader.fallDeathHeight']}）以上")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("2. 素材を1つ外したとき、各系統に部品が残るか（部品と素材.md 決まり1）")
say("=" * 70)
FAMILY = {"骨組み": ["plank", "ironBar", "stake"], "縄": ["rope", "longRope", "chain"], "ばね": SPRINGS,
          "重り": WEIGHTS, "火": ["flint", "striker"]}
for mat in sorted(set(MATERIAL.values())):
    for fam, ps in FAMILY.items():
        left = [p for p in ps if MATERIAL[p] != mat]
        if not left:
            problem("詰み", f"素材「{mat}」がないと系統「{fam}」が空")
say("  （空になる系統がなければ、上に !! は出ない）")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("3. 仮の課題 × 道具1つ：どの道具で、どの課題が解けるか（最強の一択を探す）")
say("=" * 70)
say(f"  探す深さ：{DEPTH} 手。道具は1つだけ持って入る（置いて、拾って、また置ける）")

CH = {
    "仮1 段差を越える（渡る）": dict(kind="cross", goal=(6, 2), map=[
        ".......",
        ".......",
        ".......",
        ".....##",
        ".....##",
        "#######",
        "#######"], objs=[
        ".......", ".......", ".......", ".......", "L......", ".......", "......."]),
    "仮2 割れ目を渡る（渡る）": dict(kind="cross", goal=(6, 4), map=[
        ".......",
        ".......",
        ".......",
        ".......",
        ".......",
        "##..###",
        "##..###"], objs=[
        ".......", ".......", ".......", ".......", "L......", ".......", "......."]),
    "仮3 敵を落とす（追い払う）": dict(kind="repel", edir=0, map=[
        ".......",
        ".......",
        ".......",
        "...#...",
        "...#...",
        "######.",
        "######."], objs=[
        ".......", ".......", ".......", ".......", "L....E.", ".......", "......."]),
    "仮4 荷を段の上へ運ぶ（運ぶ）": dict(kind="carry", goal=(6, 2), map=[
        ".......",
        ".......",
        ".......",
        ".....##",
        "####.##",
        "####.##",
        "#######"], objs=[
        ".......", ".......", ".......", "LC.....", ".......", ".......", "......."]),
    "仮5 穴から高い段へ（渡る）": dict(kind="cross", goal=(6, 0), map=[
        ".......",
        ".....##",
        "##...##",
        "##...##",
        "#######",
        "#######",
        "#######"], objs=[
        ".......", ".L.....", ".......", ".......", ".......", ".......", "......."]),
}

TOOLS = {"（素手）": None}
for p in ["plank", "ironBar", "stoneWeight", "ironWeight", "pebble", "sandbag"]:
    TOOLS[p] = [(0, 0, p, None)]
for s in SPRINGS:
    for f in ["up", "east", "west"]:
        TOOLS[f"{s}({f})"] = [(0, 0, s, f)]
TOOLS["板2"] = [(0, 0, "plank", None), (1, 0, "plank", None)]
TOOLS["板3"] = [(i, 0, "plank", None) for i in range(3)]
TOOLS["板4"] = [(i, 0, "plank", None) for i in range(4)]
TOOLS["板3＋西端に石"] = [(i, 1, "plank", None) for i in range(3)] + [(0, 0, "stoneWeight", None)]
TOOLS["板＋ばね(上)"] = [(0, 0, "spring", "up"), (0, 1, "plank", None)]
TOOLS["石＋ばね(東)"] = [(0, 0, "stoneWeight", None), (1, 0, "spring", "east")]


def matrix(cfg, label, tools=TOOLS):
    say(f"\n[{label}]")
    names = list(CH)
    say("  道具".ljust(22) + " | " + " | ".join(n.split(" ")[0] for n in names))
    res = {}
    for tn, t in tools.items():
        row = []
        for cn in names:
            st = build(CH[cn], cfg, tools=[] if t is None else [t])
            n, path = solve(st, depth=DEPTH)
            res[(tn, cn)] = (n, path)
            row.append("  -  " if n is None else f"{n:>3d}手")
        say(f"  {tn:20s} | " + " | ".join(row))
    allsolve = [tn for tn in tools if all(res[(tn, cn)][0] is not None for cn in names)]
    nsol = {tn: sum(res[(tn, cn)][0] is not None for cn in names) for tn in tools}
    say(f"  {len(names)}つ全部を1つで解ける道具：{allsolve if allsolve else 'なし'}")
    for cn in names:
        ok = [tn for tn in tools if res[(tn, cn)][0] is not None]
        say(f"  {cn}：解ける道具 {len(ok)} 種")
        if not ok:
            problem("道具1つでは解けない(仮の課題)", f"{label}：{cn} は、どの道具1つでも {DEPTH} 手以内に解けない（2つで解けるかは下で見る）")
    if allsolve:
        for tn in allsolve:
            if tn != "（素手）":
                problem("最強の一択", f"{label}：{tn} 1つで仮の課題{len(names)}つが全部解ける")
    if res[("（素手）", names[0])][0] is not None or any(res[("（素手）", cn)][0] is not None for cn in names):
        bare = [cn for cn in names if res[("（素手）", cn)][0] is not None]
        say(f"  注：素手で解ける仮の課題 {bare}（課題の作りの問題。数値ではない）")
    return res, nsol


cfg0 = Cfg()
res0, nsol0 = matrix(cfg0, "掟なし・癖なし・登れるのは地面だけ（仕様のまま）")
cfg1 = Cfg(climb_objects=True)
res1, nsol1 = matrix(cfg1, "物の上にも登れる（仕様の読み方の違いを試す）")
say("\n  解き方の例（物の上にも登れる）:")
for (tn, cn), (n, path) in res1.items():
    if n is not None and tn in ("ironSpring(up)", "spring(up)", "板4", "板3＋西端に石", "stoneWeight", "石＋ばね(東)"):
        say(f"   {tn} / {cn}: " + " → ".join(fmt_act(a) for a in path))


if not QUICK:
    small = {k: TOOLS[k] for k in ["（素手）", "spring(up)", "ironSpring(up)", "leafSpring(up)", "stoneWeight", "板4", "板3＋西端に石", "石＋ばね(東)"]}
    matrix(Cfg(laws={"longRain"}, climb_objects=True), "掟：長雨（物の上にも登れる）", small)
    matrix(Cfg(laws={"strongWind"}, climb_objects=True), "掟：大風（物の上にも登れる）", small)
    matrix(Cfg(traits={"hasty"}, climb_objects=True), "癖：せっかち（物の上にも登れる。ばねに焼き込み）", small)
    matrix(Cfg(traits={"strong"}, climb_objects=True), "癖：怪力（物の上にも登れる）", small)
    matrix(Cfg(fall_cells=1, climb_objects=True), "rule.fall.cellsPerTurn=1 にしたとき（物の上にも登れる）", small)

# 道具2つ（1つでは解けない課題に、2つなら解けるか）
say("\n[道具2つ・物の上にも登れる] 1つで解けなかった課題だけ")
pair_tools = ["spring(up)", "ironSpring(up)", "leafSpring(up)", "spring(east)", "stoneWeight", "pebble", "板2", "板4"]
for cn in CH:
    if any(res1[(tn, cn)][0] is not None for tn in TOOLS):
        continue
    found = []
    for a, b in itertools.combinations_with_replacement(pair_tools, 2):
        st = build(CH[cn], cfg1, tools=[TOOLS[a], TOOLS[b]])
        n, path = solve(st, depth=DEPTH + 2, cap=600000)
        if n is not None:
            found.append((a, b, n, path))
    say(f"  {cn}：2つで解ける組 {len(found)} 通り " + ", ".join(f"{a}+{b}({n}手)" for a, b, n, _ in found[:8]))
    for a, b, n, path in found[:2]:
        say(f"    例 {a}+{b}: " + " → ".join(fmt_act(x) for x in path))
    if not found:
        problem("詰み(仮の課題)", f"{cn}：道具2つでも {DEPTH + 2} 手以内に解けない（縄・火が要る形の可能性。縄・火はこの写しに入っていない）")

say("\n[rule.fall.cellsPerTurn の確かめ] 当主が宙で歩けるか（割れ目の上を、落ちきる前に渡れるか）")
for fc in (1, 2, 3, P["rule.fall.cellsPerTurn"]):
    st = build(CH["仮2 割れ目を渡る（渡る）"], Cfg(fall_cells=fc, climb_objects=True), tools=[TOOLS["pebble"]])
    n, path = solve(st, depth=DEPTH)
    say(f"  cellsPerTurn={fc}：小石1つで仮2 → " + ("解けない" if n is None else f"{n}手 " + " → ".join(fmt_act(a) for a in path)))
    if n is not None and fc < P["leader.fallDeathHeight"] + 4:
        problem("最強の一択(値)", f"rule.fall.cellsPerTurn={fc} だと、踏み台に乗って割れ目の上を宙で歩いて渡れる")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("4. 先祖の仕掛けと、解いた課題の繰り返し（無限稼ぎ・実質の上乗せ）")
say("=" * 70)
# 一代目が仮2に橋（板4）を据えた。二代目は素手で来る
bridge = [(x, 4, "plank", None, 0) for x in range(1, 5)]
say("  （橋に乗るには物の上に登る必要があるので、ここは「物の上にも登れる」読み方で試す）")
wear_per_gen = P["fixture.wearPerGen"]
for gen_after in range(0, 4):
    w = gen_after * wear_per_gen
    parts = [b[:4] + (w,) for b in bridge] if w <= 2 else []
    st = build(CH["仮2 割れ目を渡る（渡る）"], cfg1, tools=[], extra=parts)
    n, path = solve(st, depth=DEPTH)
    left = "残る" if parts else "消えた"
    say(f"  据えてから{gen_after}代あと：傷み{min(w, 3)}・橋は{left} → 素手で {'解ける ' + str(n) + '手' if n is not None else '解けない'}")
# 長雨の代が続いたとき
w = 0
seq = []
for g in range(1, 4):
    w += wear_per_gen + P["law.longRain.fixtureWearAdd"]
    seq.append(w)
say(f"  長雨の代が続くと、木の仕掛けの傷み：{seq}（2をこえたら消える）")

say("\n  解いた課題をもう一度解けるとき、1代で拾える部品（据えた橋があれば素手で何度でも解ける）")
draw = P["pickup.drawCount"]
cap = P["leader.carryParts"]
for repeats in (1, 3, 10, 100):
    got = draw * repeats
    say(f"   同じ場所を{repeats}回：拾う {got} 個（棚に持てるのは {cap} 個まで） 年は {repeats * P['challenge.yearsCost']} 年進む")
problem("無限稼ぎ(仕様の穴)", "解けた場所をもう一度解けるか、2回目も拾えるかが仕様にない。据えた仕掛けがあると素手で何度でも解け、年月しか払わない（寿命が未決なので、年月はただ）")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("5. 代をまたいで手元に来る部品の数（遺品・仕掛け・拾う）：上乗せになるか")
say("=" * 70)


def chronicle(gens, solves_per_life, relic_decay, start_parts, heir_parts, repeat_farm=False):
    """部品の数だけを数える粗い模型。部品の強さの差は見ない。
    relic_decay：墓の遺品も代替わりで傷むか（仕様は傷まない）"""
    graves = []  # 各墓の遺品：傷みのリスト
    fixtures = []  # 谷の仕掛けの部品の傷み
    out = []
    for g in range(1, gens + 1):
        shelf = list([0] * (start_parts if g == 1 else heir_parts))
        # 墓から取り戻す（いちばん新しい墓から、棚の上限まで）
        for gr in reversed(graves):
            while gr and len(shelf) < cap:
                shelf.append(gr.pop())
        avail_start = len(shelf)
        stock_in_valley = sum(len(x) for x in graves) + len(fixtures)
        # 一生：課題を解いて拾う。半分の課題で道具を据える（部品3つ）
        for k in range(solves_per_life * (5 if repeat_farm else 1)):
            shelf += [0] * draw
            if k % 2 == 0 and len(shelf) >= 3:
                for _ in range(3):
                    fixtures.append(shelf.pop())
            shelf = shelf[:cap]
        # 死：全部が遺品に
        graves.append([min(2, w + P["relic.wearOnDeath"]) for w in shelf])
        # 代替わり：仕掛けが傷む
        fixtures = [w + wear_per_gen for w in fixtures]
        fixtures = [w for w in fixtures if w <= 2]
        if relic_decay:
            graves = [[w + wear_per_gen for w in gr if w + wear_per_gen <= 2] for gr in graves]
        out.append((g, avail_start, stock_in_valley))
    return out


sp = sum(int(x.split(":")[1]) for x in str(P["start.parts"]).split(","))
hp = sum(int(x.split(":")[1]) for x in str(P["heir.startParts"]).split(","))
for label, decay in (("仕様のまま（墓の遺品は傷まない）", False), ("案：墓の遺品も代替わりで傷む", True)):
    say(f"\n  [{label}] 一生で5つ解く。代の始めに手元に持てる部品 / 谷に眠る部品")
    r = chronicle(10, 5, decay, sp, hp)
    say("   " + "  ".join(f"{g}代:{a}/{s}" for g, a, s in r))
r = chronicle(10, 5, False, sp, 0)
say(f"\n  [子に最初の部品なし（今の仕様）] 代の始めの手元：" + " ".join(f"{g}代:{a}" for g, a, s in r))
say("   → 墓から取り戻すまで素手。墓が素手で行けない場所なら、二代目は何も組めない")
problem("詰み(仕様の穴)", "一代目・二代目以降の当主が最初に持つ部品の値がない（継承の一周.md 5章：部品は全部墓に入る）。墓が素手で届かない場所だと、二代目は何も組めず、課題も解けない")
say("   上の数字から：手元に来るのは棚の上限（leader.carryParts）でいつも頭打ち。遺品・仕掛けが積もっても、1代が持てる力は上がらない")
say("   ただし、墓の遺品は傷まないので、谷に眠る部品は代ごとに増え続ける（取り戻しの手間だけ）")

# 焼き込みが重ならないか
say("\n  癖の焼き込みが重なるか：")
say("   遺品の道具＝作った当主の癖のまま。ばらすと癖の効きを失う。組み直すと今の当主の癖。→ 1つの道具に効くのは、いつも1人の当主の癖だけ")
best = max(pv(s, "springPower") for s in SPRINGS) + P["trait.hasty.springPowerAdd"]
say(f"   いちばん強いばね：{best}（強いばね＋せっかち）。盤の大きさ {P['board.size']} なので、軽い物は壁まで飛ぶ")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("6. 子の候補と掟の引き直し（同じ組み合わせを避ける決まりで、引き直しが終わらないか）")
say("=" * 70)
from math import comb

nc = P["heir.candidates"]
tc = P["heir.traitCount"]
ic = P["heir.inheritTraitCount"]
for pool in (2, 3, 4, 12):
    for tcv, icv in ((tc, ic), (1, 1), (2, 1), (2, 0)):
        # 親が tcv 個の癖を持つときの、子の組み合わせの数
        parent = min(tcv, pool)
        combos = comb(parent, icv) * comb(pool - icv, tcv - icv) if icv <= parent and tcv <= pool else 0
        # 親の癖を icv 個含む組み合わせの種類（重なりを数えすぎないように列挙で数える）
        tr = list(range(pool))
        par = tr[:parent]
        s = set()
        for inh in itertools.combinations(par, min(icv, parent)):
            rest = [t for t in tr if t not in inh]
            for oth in itertools.combinations(rest, tcv - len(inh)):
                s.add(tuple(sorted(inh + oth)))
        combos = len(s)
        mark = "OK" if combos >= nc else "引き直しが終わらない"
        if combos < nc and (tcv, icv) == (tc, ic):
            problem("詰み", f"癖の表が{pool}つ・癖{tcv}・継ぐ{icv}・候補{nc}人：組み合わせが{combos}通りしかない")
        if (tcv, icv) == (tc, ic) or pool in (2, 3):
            say(f"  癖の表{pool:2d}・1人の癖{tcv}・親から継ぐ{icv}：子の組み合わせ{combos:3d}通り（候補{nc}人）→ {mark}")
lp = P["law.perGen"]
for pool in (1, 2, 3, 8):
    combos = comb(pool, lp)
    mark = "OK" if combos >= 2 else "前の代と違う組み合わせが引けない"
    say(f"  掟の表{pool}・代ごとに{lp}つ：組み合わせ{combos}通り → {mark}")
say("  → 掟の表は2つ以上、癖の表は（候補の人数ぶんの組み合わせができる数）以上が要る。データのテストで止める")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("7. 作業台の大きさ")
say("=" * 70)
for name, add in (("基本", 0), ("几帳面", P["trait.meticulous.benchSizeAdd"])):
    for base in (P["bench.size.firstGen"], P["bench.size.base"]):
        v = max(P["bench.size.min"], min(P["bench.size.max"], base + add))
        say(f"  {name}・もとの大きさ{base} → {v}×{v}")
say(f"  板4（仮2の橋）は {P['bench.size.firstGen']}×{P['bench.size.firstGen']} の一代目の作業台に入る：{4 <= P['bench.size.firstGen']}")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("8. パラメータ表.md と パラメータ表.csv の値が合っているか")
say("=" * 70)
md = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "パラメータ表.md")
if os.path.exists(md):
    txt = open(md, encoding="utf-8").read()
    bad = 0
    cols = ["weight", "flammability", "burnTurns", "hardness", "springPower", "ropeLength"]
    matrix_rows = {}
    for line in txt.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] in PARTS:
            matrix_rows[cells[0]] = dict(zip(cols, cells[1:]))
    for k, v in P.items():
        if k.startswith("part."):
            _, pid, key = k.split(".")
            cell = matrix_rows.get(pid, {}).get(key)
            if cell is None:
                say(f"  mdにない：{k}")
                bad += 1
            elif not cell.startswith(str(v)):
                say(f"  食い違い：{k} md「{cell}」 csv「{v}」")
                bad += 1
            continue
        m = re.search(r"^\| `?" + re.escape(k) + r"`? \| ([^|]*)\|", txt, re.M)
        if not m:
            say(f"  mdにない：{k}")
            bad += 1
            continue
        cell = m.group(1).strip()
        if v == "" and cell.startswith("（空欄"):
            continue
        if not cell.startswith(str(v)):
            say(f"  食い違い：{k} md「{cell}」 csv「{v}」")
            bad += 1
    # 部品の表で、md にあって csv にない値
    for pid, row in matrix_rows.items():
        for key, cell in row.items():
            if cell not in ("—", "") and f"part.{pid}.{key}" not in P:
                say(f"  csvにない：part.{pid}.{key}（md「{cell}」）")
                bad += 1
    say(f"  食い違い・抜け：{bad} 件")
    if bad:
        problem("表", f"md と csv の食い違い・抜けが {bad} 件")
else:
    say("  パラメータ表.md がまだない")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("まとめ：見つかった問題")
say("=" * 70)
for tag, msg in problems:
    say(f"  [{tag}] {msg}")
say(f"  計 {len(problems)} 件")
