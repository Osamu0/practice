"""rules_sim.py（03_仕様/tools）で盤面を進め、TS の写し（src/core.ts）と照らすためのケースを書き出す（捨てる前提）。
使い方：python3 tools/make_cases.py   → test/cases.json
中身：A 課題「崖の先の印」の解き方・外れ方、B 課題でのでたらめな手、C 試し場の地形（平ら・崖・割れ目）で道具と重りを落として待つ、D 受け入れ条件の盤面（R-02/R-04/R-05/R-08/R-09/R-30）
"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_challenge import CH, SHELF, NAMED, use, norm  # noqa: E402
from rules_sim import P, Cfg, State, Obj, build, trial_map, make_tool  # noqa: E402

def dump_state(s):
    return dict(terrain=s.terrain, nid=s.nid, goal=s.goal,
                objs=[dict(id=i, kind=o.kind, part=o.part, x=o.x, y=o.y, wear=o.wear, facing=o.facing, dist=o.dist, byLeader=o.byLeader)
                      for i, o in s.objs.items()],
                links=[list(l) for l in sorted(s.links)],
                comp=[[k, v[0], v[1][0], v[1][1], v[2][0], v[2][1]] for k, v in sorted(s.comp.items())],
                inv=[[[c[0], c[1], c[2], c[3], c[4]] for c in t] for t in s.inv])

def jd(a): return json.dumps(a, separators=(",", ":"), ensure_ascii=False)

def key(s):
    objs = sorted(jd([o.kind, o.part, o.x, o.y, o.wear, o.facing, min(o.dist, 9)]) for o in s.objs.values())
    links = sorted(jd(sorted([[s.objs[a].x, s.objs[a].y], [s.objs[b].x, s.objs[b].y]])) for a, b in s.links if a in s.objs and b in s.objs)
    comp = sorted(jd([[s.objs[k].x, s.objs[k].y], list(v[2])]) for k, v in s.comp.items() if k in s.objs)
    li = s.leader()
    solved = bool(s.goal) and li is not None and s.solved()
    return dict(objs=objs, links=links, comp=comp, dead=s.dead, inv=len(s.inv), solved=solved)

def enc(s, a):
    if a[0] in ("enter", "climb", "push"): return dict(t=a[0], d=a[1])
    if a[0] == "place": return dict(t="place", cells=[list(c[:5]) for c in a[1]], ox=a[2], oy=a[3])
    if a[0] == "pick": return dict(t="pick", cells=[[s.objs[i].x, s.objs[i].y] for i in a[1]])
    return dict(t="wait")

def episode(name, s, acts):
    out = dict(name=name, start=dump_state(s), steps=[])
    for a in acts:
        if a[0] == "wait" and s.leader() is None:  # 試し場（当主なし）：写しの do() は当主が要るので、規則だけ進める
            t = s.copy(); t.step_rules()
        else:
            t = s.do(a)
        if t is None: break
        out["steps"].append(dict(act=enc(s, a), key=key(t)))
        s = t
        if s.dead: break
    return out

use(True)  # 課題の条件は「印で止まる」（check_challenge.py）
cases = []
rnd = random.Random(7)
from rules_sim import solve
# A
for nm, t in NAMED.items():
    st = build(CH, Cfg(), tools=[t])
    n, path = solve(st, depth=10)
    if n: cases.append(episode(f"A 解く：{nm}", st, path))
use(False)
for nm in ("板3（重りなし）", "板4（重りなし）"):
    st = build(CH, Cfg(), tools=[NAMED[nm]])
    n, path = solve(st, depth=10)  # 条件そのままなら板だけで「解ける」手順（ずれて運ばれる）。印で止まる条件では解けない
    use(True)
    cases.append(episode(f"A 運ばれる手順：{nm}", st, path + [("wait",)] * 3))
    use(False)
use(True)

pool = [p for p, n in SHELF.items() for _ in range(n)]
cells4 = [(x, y) for y in range(4) for x in range(4)]
def rand_tool():
    while True:
        k = rnd.randint(1, 6)
        ps = rnd.sample(pool, k); pos = rnd.sample(cells4, k)
        cs = [(x, y, p, rnd.choice(("up", "east", "west", "down")) if p in ("spring", "ironSpring") else None) for (x, y), p in zip(pos, ps)]
        at = {(x, y) for x, y, _, _ in cs}
        if any(p == "sandbag" and (x, y + 1) in at for x, y, p, _ in cs):
            continue  # 砂袋の下のつなぎ点は写しと TS で違う（params.ts）。照合では使わない
        return norm(cs)
# B
for e in range(250):
    st = build(CH, Cfg(), tools=[rand_tool()])
    acts, s = [], st
    for _ in range(14):
        opts = [a for a in s.actions() if s.do(a) is not None]
        a = rnd.choice(opts); acts.append(a); s = s.do(a)
        if s.dead: break
    cases.append(episode(f"B でたらめ {e}", st, acts))
# C
for e in range(250):
    kind = rnd.choice(("flat", "cliff", "gap"))
    m = trial_map(kind)
    if kind == "cliff":  # プロトの試し場の崖の縁（params.ts の TRIAL_CLIFF_COLUMN）
        m = m[:-1] + ["".join("#" if x <= 2 else "." for x in range(7))]
    st = State(m, Cfg())
    tool = rand_tool()
    w = max(c[0] for c in tool) + 1; h = max(c[1] for c in tool) + 1
    ox = rnd.randint(0, 7 - w); oy = 5 - (h - 1)
    if oy < 0: continue
    ids = []
    for (dx, dy, p, f) in tool:
        ids.append(st.add(Obj("part", ox + dx, oy + dy, p, f, 0, 0, byLeader=True)))
    pos = {(st.objs[i].x, st.objs[i].y): i for i in ids}
    for i in ids:
        o = st.objs[i]
        for dx, dy, side, oside in ((1, 0, "east", "west"), (0, 1, "down", "up")):
            j = pos.get((o.x + dx, o.y + dy))
            if j is not None and st._conn(o, side) and st._conn(st.objs[j], oside):
                st.links.add((min(i, j), max(i, j)))
    occ = st.occ()
    for _ in range(rnd.randint(0, 2)):  # 試しの重り・人形を、列のいちばん上から
        x = rnd.randint(0, 6)
        if (x, 0) in occ or st.ground(x, 0): continue
        if rnd.random() < 0.5: st.add(Obj("part", x, 0, rnd.choice(("stoneWeight", "pebble", "ironWeight"))))
        elif st.leader() is None: st.add(Obj("leader", x, 0))
        occ = st.occ()
    st.kind = "none"
    cases.append(episode(f"C 試し場 {kind} {e}", st, [("wait",)] * rnd.randint(3, 8)))
# D 受け入れ条件の盤面（規則の計算.md 11章）
def board(rows): return rows
def mkst(m, objs, links=()):
    st = State(m, Cfg()); st.kind = "none"
    ids = [st.add(Obj(k, x, y, p, f)) for (k, x, y, p, f) in objs]
    for a, b in links: st.links.add((ids[a], ids[b]))
    return st
cl = trial_map("cliff")
# R-02：地面の東の端から板3（2枚が地面）、当主なし → ずれない。東の端に当主 → ずれる
cases.append(episode("D R-02 当主なし", mkst(cl, [("part", 2, 5, "plank", None), ("part", 3, 5, "plank", None), ("part", 4, 5, "plank", None)], [(0, 1), (1, 2)]), [("wait",)] * 2))
cases.append(episode("D R-02 東の端に当主", mkst(cl, [("part", 2, 5, "plank", None), ("part", 3, 5, "plank", None), ("part", 4, 5, "plank", None), ("leader", 4, 4, None, None)], [(0, 1), (1, 2)]), [("wait",)] * 3))
cases.append(episode("D R-04 西に石", mkst(cl, [("part", 2, 5, "plank", None), ("part", 3, 5, "plank", None), ("part", 4, 5, "plank", None), ("part", 2, 4, "stoneWeight", None), ("leader", 4, 4, None, None)], [(0, 1), (1, 2), (0, 3)]), [("wait",)] * 3))
fl = trial_map("flat")
cases.append(episode("D R-05 重り2つ縦", mkst(fl, [("part", 3, 1, "stoneWeight", None), ("part", 3, 0, "stoneWeight", None)]), [("wait",)] * 2))
cases.append(episode("D R-08 上向きのばねに重り", mkst(fl, [("part", 3, 5, "spring", "up"), ("part", 3, 1, "pebble", None)]), [("wait",)] * 4))
cases.append(episode("D R-09 重すぎて弾まない", mkst(fl, [("part", 3, 5, "spring", "up"), ("part", 3, 1, "ironWeight", None)]), [("wait",)] * 3))
cases.append(episode("D R-12風 東向きのばねで投げ当て", mkst(["......."] * 4 + ["##....."] + ["#######"] * 2, [("part", 1, 3, "spring", "up"), ("part", 1, 0, "stoneWeight", None), ("part", 4, 5, "pebble", None)]), [("wait",)] * 4))
r30 = ["......."] * 6 + ["#######"]
cases.append(episode("D R-30 2つを同時に壊す", (lambda st: ([setattr(st.objs[i], "wear", 2) for i in (0, 1)], st)[1])(
    mkst(r30, [("part", 2, 5, "pebble", None), ("part", 3, 5, "pebble", None), ("part", 2, 2, "ironBar", None), ("part", 3, 2, "ironBar", None)], [(2, 3)])), [("wait",)] * 3))
os.makedirs(os.path.join(HERE, "..", "test"), exist_ok=True)
with open(os.path.join(HERE, "..", "test", "cases.json"), "w", encoding="utf-8") as f:
    json.dump(cases, f, ensure_ascii=False)
print(f"{len(cases)} ケース、{sum(len(c['steps']) for c in cases)} 手を test/cases.json に書いた")
