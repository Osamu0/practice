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

# R-02：地面の東の端から板3枚を張り出し（支えの列1列）、東端に当主 → 一緒に東へ1マスずれ、その手では落ちない
s = board(FLOOR)
L = s.add(Obj("leader", 3, 2))
ids = [s.add(Obj("part", x, 3, "plank")) for x in (1, 2, 3)]
link_all(s, ids)
t = s.do(("wait",))
check("R-02 板と当主が一緒に東へ1マス", [t.objs[i].x for i in ids] == [2, 3, 4] and t.objs[L].x == 4 and t.objs[L].y == 2, [(t.objs[i].x, t.objs[i].y) for i in ids])
t2 = t.do(("wait",))
check("R-02 次の手で落ちる（ここでは谷底まで→当主は死ぬ）", t2.dead is not None, t2.dead)

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
t = s.do(("move", 1))
t = t.do(("wait",))
check("ばね跳び：当主が打ち上げられる", t.objs[L].y == 4 - (P["part.spring.springPower"] - P["leader.weight"]), (t.objs[L].x, t.objs[L].y))

print(f"\n{ok} OK / {ng} NG")
