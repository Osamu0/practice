"""rules_sim.py が 規則の計算.md の受け入れ条件どおりに動くかを、いくつか確かめる（写しの確かめ）。
使い方： python3 03_仕様/tools/rules_sim_test.py
"""
from rules_sim import P, Cfg, State, Obj, build

ok = 0
ng = 0


def check(name, cond, info=""):
    global ok, ng
    if cond:
        ok += 1
        print(f"  OK  {name}")
    else:
        ng += 1
        print(f"  NG  {name} {info}")


def board(rows, cfg=None):
    s = State(rows, cfg or Cfg())
    s.kind = "none"
    return s


def link_all(s, ids):
    for a in ids:
        for b in ids:
            oa, ob = s.objs[a], s.objs[b]
            if a < b and abs(oa.x - ob.x) + abs(oa.y - ob.y) == 1:
                s.links.add((a, b))


FLOOR = [".......", ".......", ".......", ".......", "##.....", "##.....", "##....."]

# R-02：地面の東の端から板3枚を張り出す。2枚は地面の上（支えの列 x=0,1）、1枚（x=2）は張り出し
#   当主なし：M東 = load(2)×(2−1) = 板1 = 1、R東 = load(0)×(1−0) = 板1 = 1 → 等しいのでずれない
#   東の端の板に当主：M東 = (板1＋当主3)×1 = 4 ＞ R東 = 1 → ずれる
R02 = [".......", ".......", ".......", ".......", "##....#", "##....#", "##....#"]
w_pl, w_ld = P["part.plank.weight"], P["leader.weight"]
check("R-02（値）当主なしは M東 ≤ R東、当主ありは M東 ＞ R東", w_pl * 1 <= w_pl * 1 and (w_pl + w_ld) * 1 > w_pl * 1)
s = board(R02)
L = s.add(Obj("leader", 6, 3))  # 板の上にいない
ids = [s.add(Obj("part", x, 3, "plank")) for x in (0, 1, 2)]
link_all(s, ids)
t = s.do(("wait",))
check("R-02 当主が乗っていないと板はずれない", [t.objs[i].x for i in ids] == [0, 1, 2] and all(t.objs[i].y == 3 for i in ids), [(t.objs[i].x, t.objs[i].y) for i in ids])
s = board(R02)
L = s.add(Obj("leader", 2, 2))  # 東の端の板の上
ids = [s.add(Obj("part", x, 3, "plank")) for x in (0, 1, 2)]
link_all(s, ids)
t = s.do(("wait",))
check("R-02 東の端に当主が乗ると、板と当主が一緒に東へ1マスずれる", [t.objs[i].x for i in ids] == [1, 2, 3] and (t.objs[L].x, t.objs[L].y) == (3, 2), [(t.objs[i].x, t.objs[i].y) for i in ids] + [(t.objs[L].x, t.objs[L].y)])
check("R-02 ずれた手では落ちない（板も当主も y はそのまま）", all(t.objs[i].y == 3 for i in ids) and t.dead is None, t.dead)

# R-04：西に地面の上の板を足し、重りで押さえるとずれない
s = board(FLOOR)
L = s.add(Obj("leader", 3, 2))
ids = [s.add(Obj("part", x, 3, "plank")) for x in (0, 1, 2, 3)]
link_all(s, ids)
W = s.add(Obj("part", 0, 2, "stoneWeight"))
t = s.do(("wait",))
# xW=0,xE=1。M東 = (1)*1 + (1+3)*2 = 9、R東 = (1+3)*1 = 4 → ずれる。重り3では足りない
check("R-04（値の確かめ）石の重り1つ＋板1では当主（重さ3）を東端2マス先で押さえきれない", t.objs[ids[0]].x == 1)
s = board(FLOOR)
L = s.add(Obj("leader", 2, 2))
ids = [s.add(Obj("part", x, 3, "plank")) for x in (0, 1, 2)]
link_all(s, ids)
W = s.add(Obj("part", 0, 2, "stoneWeight"))
t = s.do(("wait",))
# M東 = (1+3)*1 = 4、R東 = (1+3)*1 = 4 → 等しいのでずれない
check("R-04 張り出し1マス・当主3 と 西1マスに石3＋板 は釣り合ってずれない", t.objs[ids[0]].x == 0)

# R-05：支えのない重り2つを縦に積む → 下から順に、重ならない
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
a = s.add(Obj("part", 3, 1, "stoneWeight"))
b = s.add(Obj("part", 3, 0, "stoneWeight"))
t = s.do(("wait",)) if False else None
s.add(Obj("leader", 0, 5))
t = s.do(("wait",))
check("R-05 2つとも落ちて重ならない", (t.objs[a].x, t.objs[a].y) == (3, 5) and (t.objs[b].x, t.objs[b].y) == (3, 4), [(t.objs[a].y), (t.objs[b].y)])

# R-08：上向きのばねの上に重りを落とす → 縮む（当たらない）→ 次の手で max(0,強さ−重さ) 上がる
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
s.add(Obj("leader", 0, 5))
sp = s.add(Obj("part", 3, 5, "spring", "up"))
w = s.add(Obj("part", 3, 1, "pebble"))
t = s.do(("wait",))
check("R-08 落ちて縮む（ばねは傷まない）", t.objs[w].y == 4 and sp in t.comp and t.objs[sp].wear == 0)
t2 = t.do(("wait",))
d = P["part.spring.springPower"] - P["part.pebble.weight"]
check(f"R-08 次の手で {d} マス上がり、その手では落ちない", t2.objs[w].y == 4 - d, t2.objs[w].y)

# R-09：重さ ≥ 強さ → 打ち出さない
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
s.add(Obj("leader", 0, 5))
sp = s.add(Obj("part", 3, 5, "spring", "up"))
w = s.add(Obj("part", 3, 1, "ironWeight"))
t = s.do(("wait",)).do(("wait",))
check(f"R-09 ばね({P['part.spring.springPower']})に鉄の重り({P['part.ironWeight.weight']})は弾まない", P["part.ironWeight.weight"] >= P["part.spring.springPower"] and t.objs[w].y == 4)

# R-12：東向きのばねで打ち出した重りが、重さ ≥ 硬さ の敵に1マス以上動いてからふさがれる → 追い払われる
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
s.add(Obj("leader", 0, 5))
sp = s.add(Obj("part", 1, 5, "ironSpring", "east"))
w = s.add(Obj("part", 2, 5, "stoneWeight"))
e = s.add(Obj("enemy", 5, 5))
s.comp[sp] = (w, (1, 5), (2, 5))
t = s.do(("wait",))
check("R-12 石(3)≥敵の硬さ(3)で追い払う", e not in t.objs and t.objs[w].x == 4, (t.objs[w].x, e in t.objs))

# R-24：墓の上に重い組を落としても壊れない
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
s.add(Obj("leader", 0, 5))
g = s.add(Obj("grave", 3, 5))
w = s.add(Obj("part", 3, 0, "ironWeight"))
t = s.do(("wait",))
check("R-24 墓は残り、重りは墓の上", g in t.objs and t.objs[w].y == 4)

# 当主が落ちて死ぬ高さ
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
L = s.add(Obj("leader", 3, 5 - P["leader.fallDeathHeight"]))
t = s.do(("wait",))
check(f"R-07 {P['leader.fallDeathHeight']} マス落ちると死ぬ", t.dead == "落ちて死ぬ", t.dead)
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
L = s.add(Obj("leader", 3, 5 - P["leader.fallDeathHeight"] + 1))
t = s.do(("wait",))
check(f"R-07 {P['leader.fallDeathHeight'] - 1} マスなら死なない", t.dead is None, t.dead)

# 下敷き：石の重り(3)は当主の硬さ(4)未満、鉄の重り(5)は以上
for part, dies in (("stoneWeight", False), ("ironWeight", True)):
    s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"])
    s.add(Obj("leader", 3, 5))
    s.add(Obj("part", 3, 1, part))
    t = s.do(("wait",))
    check(f"下敷き：{part} が当主に落ちる → 死ぬ={dies}", (t.dead == "下敷き") == dies, t.dead)

# R-25：大風 → 落ちたあと東へ最大 driftCells
s = board([".......", ".......", ".......", ".......", ".......", ".......", "#######"], Cfg(laws={"strongWind"}))
s.add(Obj("leader", 0, 5))
w = s.add(Obj("part", 3, 1, "pebble"))
t = s.do(("wait",))
check("R-25 大風で落ちたあと東へ流れる", t.objs[w].x == 3 + P["law.strongWind.driftCells"] and t.objs[w].y == 5, (t.objs[w].x, t.objs[w].y))

# 当主のばね跳び：2段の段から上向きばねへ落ち、次の手で打ち上げ、頂で東の高い段へ進む
s = board([".......", ".......", "....###", "##..###", "##..###", "##..###", "#######"], Cfg())
s.kind = "cross"
s.goal = (4, 1)
L = s.add(Obj("leader", 1, 2))
sp = s.add(Obj("part", 2, 5, "spring", "up"))
t = s.do(("enter", 1))
t = t.do(("wait",))
check("ばね跳び：当主が打ち上げられる", t.objs[L].y == 4 - (P["part.spring.springPower"] - P["leader.weight"]), (t.objs[L].x, t.objs[L].y))

FLAT = [".......", ".......", ".......", ".......", ".......", ".......", "#######"]

# R-21：真下が空きのマスへ入ると、その手の 2-5 で落ちる。支えのある組へ登ったときは落ちない
s = board([".......", ".......", ".......", ".......", "###.###", "#######", "#######"])
L = s.add(Obj("leader", 2, 3))
check("R-21 真下が空きのマスへは「入る」の候補が出る", ("enter", 1) in s.actions())
t = s.do(("enter", 1))
check("R-21 入った手の 2-5 で落ちる（1マス下で止まる）", t.dead is None and (t.objs[L].x, t.objs[L].y) == (3, 4), (t.objs[L].x, t.objs[L].y))
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
pb = s.add(Obj("part", 3, 5, "pebble"))
t = s.do(("climb", 1))
check("R-21 支えのある組の上へ登った手では落ちない", t.dead is None and (t.objs[L].x, t.objs[L].y) == (3, 4) and (t.objs[pb].x, t.objs[pb].y) == (3, 5), (t.objs[L].x, t.objs[L].y))

# C-10：押せる重さの組は押せる。重い組には「押す」の候補が出ない
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
s.add(Obj("part", 3, 5, "ironWeight"))
check(f"C-10 鉄の重り({P['part.ironWeight.weight']}) ＞ 押せる重さ({P['leader.pushWeight']}) には押すが出ない", ("push", 1) not in s.actions())

# C-20：支えのある押せる組の隣 → 「押す」と「登る」が別の候補。選んだほうだけが起きる
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
pb = s.add(Obj("part", 3, 5, "pebble"))
acts = s.actions()
check("C-20 同じ向きに「押す」と「登る」の2つの候補が出る", ("push", 1) in acts and ("climb", 1) in acts, acts)
tp = s.do(("push", 1))
check("C-20 押すを選ぶと、組が1マス動き、当主は組のあったマスへ（上には乗らない）", (tp.objs[pb].x, tp.objs[pb].y) == (4, 5) and (tp.objs[L].x, tp.objs[L].y) == (3, 5))
tc = s.do(("climb", 1))
check("C-20 登るを選ぶと、当主は組の上へ、組は動かない", (tc.objs[pb].x, tc.objs[pb].y) == (3, 5) and (tc.objs[L].x, tc.objs[L].y) == (3, 4))

# C-21：平らな地面の上の板1枚に登る → 手の終わりにも板の上。真下が空きの板（支えのない組）には登れない
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
pl = s.add(Obj("part", 3, 5, "plank"))
t = s.do(("climb", 1))
check("C-21 地面の上の板に登り、手の終わりにも板の真上のマスにいる", (t.objs[L].x, t.objs[L].y) == (3, 4) and (t.objs[pl].x, t.objs[pl].y) == (3, 5) and t.dead is None)
s = board([".......", ".......", ".......", ".......", ".......", ".......", "###.###"])
L = s.add(Obj("leader", 2, 5))
s.add(Obj("part", 3, 5, "plank"))  # 真下 (3,6) が空き＝支えのない組
acts = s.actions()
check("C-21 支えのない板には「登る」の候補が出ない（押すは出てよい）", ("climb", 1) not in acts and ("push", 1) in acts, acts)

# C-11 の残り：固定物（墓）に登れる。頭の上がふさがっていると、段が高すぎると、登るは出ない
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
s.add(Obj("grave", 3, 5))
check("C-11 墓（固定物）にも登れる", ("climb", 1) in s.actions() and ("push", 1) not in s.actions())
s = board([".......", ".......", ".......", ".......", "..#....", ".......", "#######"])
L = s.add(Obj("leader", 2, 5))
s.add(Obj("part", 3, 5, "pebble"))
check("C-11 頭の上がふさがっていると登るが出ない", ("climb", 1) not in s.actions())
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
s.add(Obj("part", 3, 5, "pebble"))
s.add(Obj("part", 3, 4, "pebble"))
check(f"C-11 2段に積んだ物（{P['leader.climbHeight']}段より高い）には登るが出ない", ("climb", 1) not in s.actions())
s = board([".......", ".......", ".......", ".......", "...#...", "...#...", "#######"])
L = s.add(Obj("leader", 2, 5))
check("C-11 地面の段差（高さ2）には登るが出ない", ("climb", 1) not in s.actions())
s = board([".......", ".......", ".......", ".......", ".......", "...##..", "#######"])
L = s.add(Obj("leader", 2, 5))
check("C-11 地面の段差（高さ1）には登るが出る", ("climb", 1) in s.actions())

# 敵は足場にならない（プロデューサーの決め 2026-11-19）
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
s.add(Obj("enemy", 3, 5))
acts = s.actions()
check("C-11 支えのある敵には「登る」の候補が出ない（押すは重さしだい）", ("climb", 1) not in acts and ("push", 1) in acts, acts)

# 先祖の仕掛けは挑む中は拾えない（挑む.md 3章）
s = board(FLAT)
L = s.add(Obj("leader", 2, 5))
s.add(Obj("part", 3, 5, "plank", anc=True))
check("先祖の仕掛けには「拾う」の候補が出ない", not any(a[0] == "pick" for a in s.actions()))

# ---- 谷と一生の模型 ----
from rules_sim import Valley, Grave, parse_parts

TABLE = ["plank", "pebble", "stoneWeight", "spring", "rope"]

# V-08：一代目の棚は start.parts
v = Valley(seed=7)
check("V-08 一代目の棚は start.parts と同じで、どれも傷み0、道具0", sorted(p for p, _ in v.shelf) == sorted(parse_parts(P["start.parts"])) and all(w == 0 for _, w in v.shelf) and v.tools == [])

# H-20：代替わりのあとの棚は、親の持ち物に関係なく heir.startParts
v = Valley(seed=7)
v.shelf = [("ironWeight", 0)] * P["leader.carryParts"]
v.tools = [{(0, 0): ("plank", 0), (1, 0): ("plank", 0)}]
v.die()
v.succession()
first = sorted(v.shelf)
v.shelf = []
v.die()
v.succession()
check("H-20 代替わりの棚は heir.startParts（傷み0・道具0）で、毎代同じ", first == sorted((p, 0) for p in parse_parts(P["heir.startParts"])) and sorted(v.shelf) == first and v.tools == [])

# V-04：拾うのはその代で初めて解けたときだけ
v = Valley(seed=7)
v.shelf = []
g1 = v.solve("A", TABLE)
before = list(v.shelf)
g2 = v.solve("A", TABLE)
check(f"V-04 初めて解くと {P['pickup.drawCount']} 個拾う", len(g1) == P["pickup.drawCount"])
check("V-04 同じ代に2回目は0個で、棚は前と同じ", g2 == [] and v.shelf == before)
v2 = Valley(seed=7)
v2.shelf = []
check("V-04 同じシード・同じ記録なら、拾う部品は同じ", v2.solve("A", TABLE) == g1)
v.succession()
check(f"V-04 代替わりのあとは、同じ場所でまた {P['pickup.drawCount']} 個拾える", len(v.solve("A", TABLE)) == P["pickup.drawCount"])

# H-21：前の代の墓 A は wearPerGen だけ傷む（掟の足しなし）。その代替わりで建った墓 B は傷まない
wd, wg = P["relic.wearOnDeath"], P["fixture.wearPerGen"]
v = Valley(seed=7)
v.shelf = [("plank", 0), ("pebble", 1)]  # 死ぬと 0+wd、1+wd
v.tools = [{(0, 0): ("plank", 0), (1, 0): ("plank", 1), (2, 0): ("plank", 0)}]  # 真ん中が先に消える橋
A = v.die()
v.succession()  # A はこの代替わりで建った墓 → 足さない
check("H-21 死んだ直後の代替わりでは、その墓の遺品は傷まない", sorted(A.parts) == [("pebble", min(2, 1 + wd)), ("plank", min(2, wd))] and sorted(A.tools[0].values()) == [("plank", wd), ("plank", wd), ("plank", min(2, 1 + wd))])
v.shelf = [("spring", 0)]
B = v.die()
v.succession(new_laws={"longRain"})  # 長雨でも遺品には掟の足しはない
pl = [w for p, w in A.parts if p == "plank"]
check(f"H-21 前の代の墓 A の遺品は {wg} だけ傷む（長雨の足しはない）", sorted(pl) == [wd + wg, wd + wg, wd + wg] and ("pebble", 2) not in A.parts and all(w <= 2 for _, w in A.parts), A.parts)
check("H-21 壊れかけをこえた部品は消え、残った橋は2つの部品に分かれる", A.tools == [] and len(A.parts) == 3, (A.tools, A.parts))
check("H-21 この代に建った墓 B の遺品は、その代替わりでは変わらない", B.parts == [("spring", wd)], B.parts)

# H-06（直した仕様）：遺品になるとき、壊れかけ（2）をこえる部品は墓に入らず消える
v = Valley(seed=7)
v.shelf = [("plank", 2), ("pebble", 0)]
v.tools = [{(0, 0): ("plank", 0), (1, 0): ("plank", 2), (2, 0): ("plank", 0)}]
G = v.die()
check("H-06 傷み2の部品は死んだとき消え、残りは傷み relic.wearOnDeath で墓に入る", G.parts == [("plank", wd), ("plank", wd), ("pebble", wd)] and G.tools == [], (G.tools, G.parts))
# 毎代取り戻して持ち続けた道具は、作った代＋2代で消える
v = Valley(seed=7)
v.tools = [{(i, 0): ("plank", 0) for i in range(3)}]
n = 0
for g in range(10):
    if g:
        for gr in reversed(v.graves):
            v.retrieve(gr)
    if not v.tools:
        break
    n += 1
    v.die()
    v.succession()
check("H-06 毎代取り戻して持ち続けた道具は 3 代（作った代＋2代）で消える", n == 3, n)

print(f"\n{ok} OK / {ng} NG")
raise SystemExit(1 if ng else 0)
