"""数値の破綻（詰み・最強の一択・無限稼ぎ／実質の上乗せ）を確かめる（game-spec-balance、2026-11-18）。

使い方：  python3 03_仕様/tools/balance_check.py            （全部。数分かかる。問題が1件でもあれば終わりの値は 1）
          python3 03_仕様/tools/balance_check.py quick      （盤面の探しを浅くする）
値は ../パラメータ表.csv から読む。課題の盤面はすべて【仮】（課題の中身は 07 で作る。ここでは数値を試すためだけの形）。
"""
import itertools
import os
import re
import sys

from rules_sim import P, Cfg, State, Obj, build, solve, fmt_act, pv, WET_MATERIAL, Valley, parse_parts, trial_map

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
    # 仮3 は 1.2 の直した決まり（組み合わせる物も道具なしでは越えられない）に合わせて直した【仮】：
    # 高さ2の壁の向こうの、深さ2の穴の底に敵。当主が飛び下りると 3 マス落ちて死ぬ。押しても届かない。重い物を落とす・投げるが要る
    "仮3 壁の向こうの穴の敵（追い払う・仮）": dict(kind="repel", edir=0, map=[
        ".......",
        ".......",
        "..#....",
        "..#....",
        "###.###",
        "###.###",
        "#######"], objs=[
        ".......", ".......", ".......", "L......", ".......", "...E...", "......."]),
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
    "仮6 高さ3の段差（谷と一生 1.2 の形）": dict(kind="cross", goal=(6, 1), map=[
        ".......",
        ".......",
        ".....##",
        ".....##",
        ".....##",
        "#######",
        "#######"], objs=[
        ".......", ".......", ".......", ".......", "L......", ".......", "......."]),
}
STEP_ONLY = {"仮1 段差を越える（渡る）"}  # 谷と一生 1.2 の「段差だけで止める課題（高さ3未満）」に当たる仮の課題

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
# 杭（M2 の決め(b)、2026-11-19）：杭を真下が地面のマスに置くと、その1マスが固定。杭を含む組は動かない
STAKE_TOOLS = {
    "杭": [(0, 0, "stake", None)],
    "杭＋板(東)": [(0, 0, "stake", None), (1, 0, "plank", None)],
    "杭＋板2(東)": [(0, 0, "stake", None), (1, 0, "plank", None), (2, 0, "plank", None)],
    "杭＋板3(東)": [(0, 0, "stake", None)] + [(i, 0, "plank", None) for i in (1, 2, 3)],
    "杭の上に板（柱）": [(0, 1, "stake", None), (0, 0, "plank", None)],
}
BASE_TOOLS = len(TOOLS) - 1  # 杭なしの 21 種（1.2 の目安の数え方はこれまでと同じ）
TOOLS.update(STAKE_TOOLS)


def matrix(cfg, label, tools=TOOLS, main=False):
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
            say(f"  注：{cn} は、どの道具1つでも {DEPTH} 手以内に解けない（2つで解けるかは下で見る。詰みかどうかは「道具2つ」で決める）")
    if allsolve:
        for tn in allsolve:
            if tn != "（素手）":
                problem("最強の一択", f"{label}：{tn} 1つで仮の課題{len(names)}つが全部解ける")
    if res[("（素手）", names[0])][0] is not None or any(res[("（素手）", cn)][0] is not None for cn in names):
        bare = [cn for cn in names if res[("（素手）", cn)][0] is not None]
        say(f"  注：素手で解ける仮の課題 {bare}（課題の作りの問題。数値ではない）")
    return res, nsol


cfg1 = Cfg()
res1, nsol1 = matrix(cfg1, "掟なし・癖なし（挑む.md 3.1：地面・固定物・支えのある組に登れる）", main=True)
say("\n  解き方の例:")
for (tn, cn), (n, path) in res1.items():
    if n is not None and tn in ("ironSpring(up)", "spring(up)", "板4", "板3＋西端に石", "stoneWeight", "石＋ばね(東)"):
        say(f"   {tn} / {cn}: " + " → ".join(fmt_act(a) for a in path))
LIMIT = (len(TOOLS) - 1) // 2  # 07 の目安：道具1つで解ける種類は半分まで（谷と一生 1.2。杭の 5 種を足して 26 種なら 13 種）
say(f"  1.2 の目安：道具1つで解ける種類は {LIMIT} 種まで")
for cn in CH:
    k = sum(res1[(tn, cn)][0] is not None for tn in TOOLS if tn != "（素手）")
    if k > LIMIT:
        tag = "谷と一生 1.2 の決まりで作らない形" if cn in STEP_ONLY else "要注意"
        say(f"  注：{cn} は {len(TOOLS) - 1} 種のうち {k} 種の道具で解ける（踏み台。{tag}）")
        if cn not in STEP_ONLY:
            problem("最強の一択(課題の作り)", f"{cn}：1.2 の決まりの形なのに、{k} 種の道具1つで解ける（目安 {LIMIT} 種まで）")


# 杭の片持ち（M2）：崖の縁に杭＋板の片持ちが「渡る」の一択にならないか
say("\n[杭（M2 の決め(b)）] 杭の道具で解ける仮の課題、と前の決め（組の全部が固定）との違い")
cross = [cn for cn in CH if CH[cn]["kind"] == "cross"]
old_cfg = Cfg(stake_rule="old", stake_pick=False)
for tn, t in STAKE_TOOLS.items():
    now = [cn.split(" ")[0] for cn in CH if res1[(tn, cn)][0] is not None]
    old = [cn.split(" ")[0] for cn in CH if solve(build(CH[cn], old_cfg, tools=[t]), depth=DEPTH)[0] is not None]
    say(f"  {tn:16s}：今の決め {now if now else 'なし'}／前の決め {old if old else 'なし'}")
for cn in cross:
    ok = [tn for tn in TOOLS if tn != "（素手）" and res1[(tn, cn)][0] is not None]
    st = [tn for tn in ok if tn in STAKE_TOOLS]
    best = min((res1[(tn, cn)][0], tn) for tn in ok) if ok else None
    say(f"  {cn}：解ける道具 {len(ok)} 種（うち杭 {len(st)} 種）。いちばん短い {best}")
    if ok and set(ok) <= set(STAKE_TOOLS):
        problem("最強の一択(杭)", f"{cn}：杭の道具でしか解けない")
nst = {tn: sum(res1[(tn, cn)][0] is not None for cn in cross) for tn in TOOLS if tn != "（素手）"}
top = max(nst.values())
say(f"  「渡る」{len(cross)} つのうち解ける数がいちばん多い道具：{[tn for tn, k in nst.items() if k == top]}（{top} つ）")
if all(nst[tn] == top for tn in STAKE_TOOLS if nst[tn] == top) and all(tn in STAKE_TOOLS for tn, k in nst.items() if k == top):
    problem("最強の一択(杭)", f"「渡る」をいちばん多く解く道具が杭の道具だけ（{top} つ）")
# 杭の片持ち橋は、当主が乗っても、重りを落としても動かない（張り出しの板は壊れうる）
s0 = State([".......", ".......", ".......", ".......", ".......", ".......", "##....#"], Cfg())
k0 = s0.add(Obj("part", 1, 5, "stake"))
ps = [s0.add(Obj("part", x, 5, "plank")) for x in (2, 3, 4)]
s0.links |= {(k0, ps[0]), (ps[0], ps[1]), (ps[1], ps[2])}
s0.add(Obj("leader", 4, 4))
s0.kind = "none"
t0 = s0.do(("wait",))
say(f"  崖の縁の杭＋板3（張り出し3）の東の端に当主：組は{'動かない' if all(t0.objs[i].x == x for i, x in zip(ps, (2, 3, 4))) else '動いた'}（ずれる式なら M東 ＞ R東）。"
    f"重りなしで張り出しをいくらでも長くできる＝「重りで押さえる」の代わりになる")



if not QUICK:
    small = {k: TOOLS[k] for k in ["（素手）", "spring(up)", "ironSpring(up)", "leafSpring(up)", "stoneWeight", "板4", "板3＋西端に石", "石＋ばね(東)"]}
    matrix(Cfg(laws={"longRain"}), "掟：長雨", small)
    matrix(Cfg(laws={"strongWind"}), "掟：大風", small)
    matrix(Cfg(traits={"hasty"}), "癖：せっかち（ばねに焼き込み）", small)
    matrix(Cfg(traits={"strong"}), "癖：怪力", small)
    matrix(Cfg(fall_cells=1), "rule.fall.cellsPerTurn=1 にしたとき", small)

# 道具2つ（1つでは解けない課題に、2つなら解けるか）
say("\n[道具2つ] 1つで解けなかった課題だけ")
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

TOOLS_X = {"板3＋東端に石（階段）": [(i, 1, "plank", None) for i in range(3)] + [(2, 0, "stoneWeight", None)]}
for tn, t in TOOLS_X.items():
    n, path = solve(build(CH["仮6 高さ3の段差（谷と一生 1.2 の形）"], cfg1, tools=[t]), depth=DEPTH)
    say(f"  （1.2 の確かめ）{tn} 1つで仮6 → " + ("解けない" if n is None else f"{n}手 " + " → ".join(fmt_act(a) for a in path)))

say("\n[rule.fall.cellsPerTurn の確かめ] 当主が宙で歩けるか（割れ目の上を、落ちきる前に渡れるか）")
for fc in (1, 2, 3, P["rule.fall.cellsPerTurn"]):
    st = build(CH["仮2 割れ目を渡る（渡る）"], Cfg(fall_cells=fc), tools=[TOOLS["pebble"]])
    n, path = solve(st, depth=DEPTH)
    say(f"  cellsPerTurn={fc}：小石1つで仮2 → " + ("解けない" if n is None else f"{n}手 " + " → ".join(fmt_act(a) for a in path)))
    if n is not None:
        if fc == P["rule.fall.cellsPerTurn"]:
            problem("最強の一択(値)", f"今の rule.fall.cellsPerTurn={fc} で、踏み台に乗って割れ目の上を宙で歩いて渡れる")
        else:
            say(f"  注：cellsPerTurn={fc} に下げると、宙で歩いて渡れる（今の値 {P['rule.fall.cellsPerTurn']} では起きない。下げるなら挑む.md に「支えのない当主は待つだけ」を先に）")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("3b. 代の始めの棚だけで、どの仮の課題が解けるか（墓が素手で届かない場所でも詰まないか）")
say("=" * 70)


def tools_from(parts):
    """棚の部品だけで組める道具（この写しで試す形だけ）"""
    have = {p: parts.count(p) for p in set(parts)}
    out = {}
    for tn, t in TOOLS.items():
        if t is None:
            continue
        need = {}
        for c in t:
            need[c[2]] = need.get(c[2], 0) + 1
        if all(have.get(p, 0) >= n for p, n in need.items()):
            out[tn] = (t, need)
    return out


for label, key in (("一代目 start.parts", "start.parts"), ("二代目から heir.startParts", "heir.startParts")):
    parts = parse_parts(P[key])
    cand = tools_from(parts)
    say(f"\n  [{label}] {P[key]} → 組める道具 {len(cand)} 種：{list(cand)}")
    for cn in CH:
        best = None
        for tn, (t, need) in cand.items():
            r = res1.get((tn, cn))
            if r and r[0] is not None and (best is None or r[0] < best[1]):
                best = (tn, r[0])
        if best is None:  # 2つ持つ（部品が足りる組だけ）
            names = list(cand)
            for i, a in enumerate(names):
                for bb in names[i:]:
                    na, nb = cand[a][1], cand[bb][1]
                    tot = {p: na.get(p, 0) + nb.get(p, 0) for p in set(na) | set(nb)}
                    if any(parts.count(p) < n for p, n in tot.items()):
                        continue
                    st = build(CH[cn], cfg1, tools=[cand[a][0], cand[bb][0]])
                    n, path = solve(st, depth=DEPTH + 2, cap=400000)
                    if n is not None and (best is None or n < best[1]):
                        best = (f"{a}+{bb}", n)
        say(f"   {cn}：" + ("解けない" if best is None else f"{best[0]} で {best[1]}手"))
    if key == "heir.startParts" and not any(True for _ in cand):
        problem("詰み", "heir.startParts で組める道具がない")

say("\n" + "=" * 70)
say("3c. 墓（M13：地の印）が N 個ある場所で、段差が素手で解けるようにならないか")
say("=" * 70)
for cn in ("仮1 段差を越える（渡る）", "仮6 高さ3の段差（谷と一生 1.2 の形）"):
    ch = CH[cn]
    lx, ly = next((x, y) for y, r in enumerate(ch["objs"]) for x, c in enumerate(r) if c == "L")
    floor = [x for x in range(P["board.size"]) if not ch["map"][ly][x] == "#" and ch["map"][ly + 1][x] == "#" and x != lx]
    for nmax in (1, 2, 3, len(floor)):
        now_ok, old_ok, n_sets = 0, 0, 0
        for k in range(1, nmax + 1):
            for cells in itertools.combinations(floor, k):
                gr = [(x, ly) for x in cells]
                n_sets += 1
                if solve(build(ch, Cfg(), graves=gr), depth=DEPTH)[0] is not None:
                    now_ok += 1
                if solve(build(ch, Cfg(grave_solid=True), graves=gr), depth=DEPTH)[0] is not None:
                    old_ok += 1
        say(f"  {cn}：墓 1〜{nmax} 個の置き方 {n_sets} 通り → 素手で解ける 今の決め {now_ok} 通り／前の決め（墓は固定物）{old_ok} 通り")
        if now_ok:
            problem("詰みの逆(墓)", f"{cn}：墓が{nmax}個までの置き方 {now_ok} 通りで素手で解ける")
# 墓が積み重なる（前の決めで、墓の上で死ぬ）と2段の踏み台になった：今の決めでは印は重ならない（マスを取らない）
say("  前の決めでは、墓の上に立って死ぬと墓が2段に積めた（段差2を素手で越えられた）。今の決めでは墓はマスを取らないので、何個あっても盤面は同じ")

say("\n" + "=" * 70)
say("3d. 最初の5分の順（デザインの柱）：start.parts で「予行で板が落ちる → 重りで押さえて渡る」が起きるか")
say("=" * 70)


def trial_run(kind, x0, stone=False, turns=None):
    """試し場：板3の左を x0 に置き、東の端に人形（当主と同じ値）。stone=True なら西の端の板の上に試しの重り（石の重り）"""
    turns = turns or P["trial.maxTurns"]
    st = State(trial_map(kind), Cfg())
    st.kind = "none"
    y = P["trial.size"] - 2
    ids = [st.add(Obj("part", x0 + i, y, "plank")) for i in range(3)]
    st.links |= {(ids[0], ids[1]), (ids[1], ids[2])}
    if stone:
        st.add(Obj("part", x0, y - 1, "stoneWeight"))
    st.add(Obj("leader", x0 + 2, y - 1))  # 人形（当主と同じ値。写しでは当主の物で代える）
    for n in range(1, turns + 1):
        st = st.do(("wait",))
        if st.dead or any(i not in st.objs for i in ids) or any(st.objs[i].y != y for i in ids):
            return n, "板が落ちた" if any(i not in st.objs or st.objs[i].y != y for i in ids) else st.dead
    return None, "止まったまま"


c = P["trial.cliffColumn"]
for kind in ("cliff", "gap"):
    x0 = c - 1  # 2 枚が地面、1 枚が張り出す（R-02 の形）
    a = trial_run(kind, x0, stone=False)
    b = trial_run(kind, x0, stone=True)
    say(f"  試し場「{ {'cliff': '崖', 'gap': '割れ目'}[kind] }」板3 を {x0}〜{x0 + 2} 列、東の端に人形：{a[1]}（{a[0]}手目）"
        f" → 西の端に試しの重り：{b[1] if b[0] else '動かない（押さえられた）'}")
    if a[0] is None or b[0] is not None:
        why = "板が落ちずに東・西へずれ続ける（ずれた先の向こう岸で支えができる）" if a[0] is None else "重りを載せても止まらない"
        problem("最初の5分(試し場)", f"試し場「{ {'cliff': '崖', 'gap': '割れ目'}[kind] }」（trial.gapWidth={P['trial.gapWidth']}）で、人形を乗せた板3 が{why}")
ch2 = CH["仮2 割れ目を渡る（渡る）"]
need_stone_tools = {"板3＋西端に石": TOOLS["板3＋西端に石"]}
plank_only = {k: TOOLS[k] for k in ("plank", "板2", "板3")}
po = {k: res1[(k, "仮2 割れ目を渡る（渡る）")][0] for k in plank_only}
ws = {k: solve(build(ch2, cfg1, tools=[t]), depth=DEPTH)[0] for k, t in need_stone_tools.items()}
pair = solve(build(ch2, cfg1, tools=[TOOLS["板3"], TOOLS["stoneWeight"]]), depth=DEPTH + 2, cap=400000)
say(f"  本番 仮2（割れ目 幅2）で start.parts（{P['start.parts']}）：板だけの道具 {po}、板3＋西端に石 {ws}、板3と石を別に持つ {pair[0]}手")
n, path = solve(build(ch2, cfg1, tools=[TOOLS["板3"]]), depth=DEPTH)
if n is not None:
    say(f"   板3 だけの解き方：" + " → ".join(fmt_act(a) for a in path))
    say("   → 板3 は張り出すと毎手 東・西へずれ続け（13.4 ずれ続ける板）、当主はそれに乗って運ばれて渡る。重りは要らない")
    problem("最初の5分(規則・課題の作り)", "仮2 と start.parts では、板3 だけで渡れて「重りで押さえて渡る」が要らない（ずれた板が向こう岸に乗り、当主を運ぶ）。"
            "幅2の割れ目は、張り出し1マスの片持ち（重りで押さえられる長さ）では届かない")

say("\n" + "=" * 70)
say("4. 先祖の仕掛けと、解いた課題の繰り返し（無限稼ぎ・実質の上乗せ）")
say("=" * 70)
# 一代目が仮2に橋（板4）を据えた。二代目は素手で来る（先祖の仕掛けは挑む中は拾えない）
bridge = [(x, 4, "plank", None, 0) for x in range(1, 5)]
wear_per_gen = P["fixture.wearPerGen"]
for gen_after in range(0, 4):
    w = gen_after * wear_per_gen
    parts = [b[:4] + (w,) for b in bridge] if w <= 2 else []
    st = build(CH["仮2 割れ目を渡る（渡る）"], cfg1, tools=[], extra=parts)
    n, path = solve(st, depth=DEPTH)
    left = "残る" if parts else "消えた"
    say(f"  据えてから{gen_after}代あと：傷み{min(w, 3)}・橋は{left} → 素手で {'解ける ' + str(n) + '手' if n is not None else '解けない'}")
w = 0
seq = []
for g in range(1, 4):
    w += wear_per_gen + P["law.longRain.fixtureWearAdd"]
    seq.append(w)
say(f"  長雨の代が続くと、木の仕掛けの傷み：{seq}（2をこえたら消える）")

say("\n  同じ場所を1代に何度も解いたとき拾える部品（谷と一生 3章：その代で初めて解けたときだけ）")
TABLE = ["plank", "pebble", "stoneWeight", "spring", "rope"]
for rule, first in (("今の仕様（初めてだけ）", True), ("決まりがない場合（前の仕様）", False)):
    v = Valley(seed=3, first_pick_only=first)
    v.shelf = []
    got = []
    for k in range(10):
        got += v.solve("仮2", TABLE)
    say(f"   {rule}：同じ場所を10回 → 拾う {len(got)} 個、引けた種類 {sorted(set(got))}、年は {10 * P['challenge.yearsCost']} 年進む")
    if first and len(got) > P["pickup.drawCount"]:
        problem("無限稼ぎ", f"1代に同じ場所で {len(got)} 個拾えた")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("5. 代をまたいで手元に来る部品の数（遺品・仕掛け・拾う）：上乗せになるか")
say("=" * 70)


def chronicle(gens, solves_per_life, relic_decay, relic_skip_new=True, farm=False, heir_override=None, death_cap=False):
    """部品の数だけを数える粗い模型（強さの差は見ない）。一生で solves_per_life の場所を解き、
    1つおきに部品3つの仕掛けを据える。代の始めに、新しい墓から順に棚の上限まで取り戻す（墓にはいつも届くとする）。
    farm：同じ場所を5回ずつ解く。戻り値：[(代, 代の始めの手元, 谷に眠る部品, 取り戻した部品の傷み)]"""
    v = Valley(seed=11, relic_decay=relic_decay, relic_skip_new=relic_skip_new, death_cap=death_cap)
    out = []
    for g in range(1, gens + 1):
        if heir_override is not None and g > 1:
            v.shelf = [(p, 0) for p in heir_override]
        n0 = len(v.shelf)
        for gr in reversed(v.graves):
            v.retrieve(gr)
        got_w = [w for _, w in v.shelf[n0:]]
        hand = len(v.shelf) + sum(len(t) for t in v.tools)
        stock = v.stock()
        for k in range(solves_per_life):
            # 1つおきに、棚の部品3つで道具を組んで挑み、解けたら据える（道具は盤面にあるので、拾うの前に棚から出ている）
            if k % 2 == 0 and len(v.shelf) >= 3:
                v.fixtures.append({(i, 0): v.shelf.pop() for i in range(3)})
            for _ in range(5 if farm else 1):
                v.solve(f"場所{k}", TABLE)
        v.die()
        v.succession()
        out.append((g, hand, stock, got_w))
    return out


heir_n = len(parse_parts(P["heir.startParts"]))
cap = P["leader.carryParts"]
cases = (
    ("A 墓の遺品は傷まない（前の仕様）", dict(relic_decay=False, death_cap=True)),
    ("B 遺品も傷む・死んだ直後の代替わりから足す", dict(relic_decay=True, relic_skip_new=False, death_cap=True)),
    ("C 遺品も傷む・次の代替わりから足す・死んだとき 2 で止める", dict(relic_decay=True, relic_skip_new=True, death_cap=True)),
    ("D C＋死んだとき壊れかけ(2)をこえる部品は消える（今の仕様）", dict(relic_decay=True, relic_skip_new=True, death_cap=False)),
)
summary = {}
for label, kw in cases:
    r = chronicle(30, 5, **kw)
    summary[label] = r
    say(f"\n  [{label}] 一生で5つ解く。代:代の始めの手元/谷に眠る部品")
    say("   " + "  ".join(f"{g}代:{a}/{s}" for g, a, s, _ in r[:10]))
    tail = [s for _, _, s, _ in r[10:]]
    say(f"   11〜30代の谷に眠る部品：最小 {min(tail)}・最大 {max(tail)}。手元の最大 {max(a for _, a, _, _ in r)}（棚の上限 {cap}＋道具）")
    ws = [w for _, _, _, gw in r[1:] for w in gw]
    if ws:
        say(f"   二代目から取り戻した部品の傷み：0={ws.count(0)} 1={ws.count(1)} 2={ws.count(2)}（取り戻した数 {len(ws)}）")
    if kw.get("relic_decay") and max(tail) > max(s for _, _, s, _ in r[:10]) + 2:
        problem("実質の上乗せ", f"{label}：谷に眠る部品が増え続ける")
    if not kw.get("relic_decay"):
        say("   → 谷に眠る部品が代ごとに増え続ける（遺品が傷まない場合。今の仕様ではない）")
r = chronicle(30, 5, relic_decay=True, relic_skip_new=True, farm=True)
say(f"\n  [D（今の仕様）で、同じ場所を5回ずつ解く] 谷に眠る部品：" + " ".join(f"{g}代:{s}" for g, a, s, _ in r[:10]))
r0 = chronicle(10, 5, relic_decay=True, relic_skip_new=True, heir_override=[])
say(f"\n  [子に最初の部品なし（前の仕様）・墓にはいつも届くとき] 代の始めの手元：" + " ".join(f"{g}代:{a}" for g, a, s, _ in r0))
say(f"   今の仕様は heir.startParts（{heir_n} 個）＋取り戻した遺品。墓が届かない場所でも {heir_n} 個で組める（3b）")
say("   手元に来るのは棚の上限（leader.carryParts）でいつも頭打ち。遺品・仕掛けが積もっても、1代が持てる力は上がらない")

# 1つの道具を、どの代も墓から取り戻して持ち続けたら、何代もつか（直さない）
say("\n  先祖の道具（板3）を、どの代も親の墓から取り戻して持ち歩き、直さずに使い続けると、何代まで残るか")
lineage = {}
for label, kw in (("B 直後から足す（前の案）", dict(relic_skip_new=False, death_cap=True)), ("C 次の代替わりから・死んだとき 2 で止める（前の案）", dict(relic_skip_new=True, death_cap=True)),
                  ("D 次の代替わりから・死んだとき 2 をこえる部品は消える（今の仕様）", dict(relic_skip_new=True, death_cap=False))):
    v = Valley(seed=5, **kw)
    v.tools = [{(i, 0): ("plank", 0) for i in range(3)}]
    trace = []
    for g in range(1, 21):
        if g > 1:
            for gr in reversed(v.graves):
                v.retrieve(gr)
        if not v.tools:
            break
        trace.append(max(w for t in v.tools for _, w in t.values()))
        v.die()
        v.succession()
    lineage[label] = len(trace)
    say(f"   {label}：{len(trace)} 代が使えた（各代の始めの傷み {trace}）" + ("（20代で打ち切り＝消えない）" if len(trace) >= 20 else ""))
    if len(trace) >= 20:
        say(f"   → {label} は毎代取り戻すと消えない" + ("" if kw["death_cap"] else "（今の仕様なので問題）"))
    if len(trace) >= 20 and not kw["death_cap"]:
        problem("実質の上乗せ", f"{label}：毎代取り戻すと、遺品の道具が壊れかけのまま消えない（relic.wearOnDeath が 2 で止まり、新しい墓は傷まないため）。焼き込んだ癖も代をこえて残る")

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

say("\n  パラメータの名前.md（game-spec-writer）の名前と、値の写し")
nm = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "パラメータの名前.md")
if os.path.exists(nm):
    ntxt = open(nm, encoding="utf-8").read()
    names, copies = set(), {}
    for line in ntxt.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.match(r"^`?[a-z][A-Za-z0-9]*(\.[A-Za-z0-9<>]+)+`?$", cells[0]):
            k = cells[0].strip("`")
            names.add(k)
            if cells[1]:
                copies[k] = cells[1]
    names_bad = 0
    pcols = ["weight", "flammability", "burnTurns", "hardness", "springPower", "ropeLength"]
    for line in ntxt.splitlines():  # 部品の表の写し（燃えやすさの 0 など、素材で決まった値）
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0] in PARTS:
            for key, cell in zip(pcols, cells[1:]):
                k = f"part.{cells[0]}.{key}"
                if re.match(r"^-?\d+$", cell) and str(P.get(k)) != cell:
                    say(f"  写しの食い違い：{k} 名前の一覧「{cell}」 csv「{P.get(k)}」")
                    names_bad += 1
                if cell == "—" and k in P:
                    say(f"  名前の一覧では無い値（—）なのに csv にある：{k}")
                    names_bad += 1

    def norm(v):
        v = str(v).strip()
        if "未決" in v:
            return "未決"
        if v.startswith("（空欄") or v == "":
            return ""
        m2 = re.match(r"^(-?\d+)", v)
        return m2.group(1) if m2 else v
    for k, cell in copies.items():
        if k not in P:
            continue
        if norm(cell) != norm(P[k]):
            say(f"  写しの食い違い：{k} 名前の一覧「{cell}」 csv「{P[k]}」")
            names_bad += 1
    pending = ("challenge.vs.protectTurns", "challenge.cargo.", "enemy.crawler.")  # 名前の一覧に足される途中（仕様レビュー 直したほうがいい 15）
    wait = []
    for k in P:
        if k.startswith("part.") or k in names:
            continue
        if k.startswith(pending):
            wait.append(k)
            continue
        say(f"  名前の一覧にない：{k}")
        names_bad += 1
    if wait:
        say(f"  注：名前の一覧に足される途中（game-spec-writer）：{wait}")
    say(f"  値の写し {len(copies)} 件を見た。食い違い・抜け：{names_bad} 件")
    if names_bad:
        problem("表", f"パラメータの名前.md と csv の食い違い・抜けが {names_bad} 件")

# ------------------------------------------------------------------
say("\n" + "=" * 70)
say("まとめ：見つかった問題")
say("=" * 70)
for tag, msg in problems:
    say(f"  [{tag}] {msg}")
say(f"  計 {len(problems)} 件")
sys.exit(1 if problems else 0)
