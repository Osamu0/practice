"""Q1 のプロトの課題「崖の先の印」（仮）が、ねらいどおりかを rules_sim.py の写しで確かめる（捨てる前提）。
使い方：python3 tools/check_challenge.py        （1〜2分）
ねらい：素手・板だけでは解けない。重りで板の西を押さえると解ける。重さが足りないと解けない。解き方は1つではない。

課題の条件（この場所だけの条件。挑む.md 6章「渡る」に足した）：
  当主が印のマスにいて、かつ、その手の段2で当主が規則で動いていない（ずれて運ばれて来ていない）。
  足した理由：「渡る」の条件のままだと、張り出した板が1マスずれて当主を印まで運ぶ手（ずれる＝1マスの平行移動）で、
  板だけで解けてしまう（下の「条件をそのまま」の行）。パラメータ表 13.3 #14 と同じ根っこ。
"""
import os, sys, itertools, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "03_仕様", "tools"))
from rules_sim import P, Cfg, State, build, solve, fmt_act  # noqa: E402

CH = dict(kind="cross", goal=(3, 3), map=[
    ".......",
    ".......",
    ".......",
    "#......",
    "#......",
    "###....",
    "###...."], objs=[
    ".......", ".......", "L......", ".......", ".......", ".......", "......."])

SHELF = {"plank": 4, "ironBar": 1, "spring": 1, "ironSpring": 1, "stoneWeight": 1, "ironWeight": 1, "pebble": 2, "sandbag": 1}
BENCH = 4

_orig_solved, _orig_key = State.solved, State.key
def solved_still(self):
    return _orig_solved(self) and self.leader() not in self.moved
def key_still(self):  # 「動かされたか」で解けたかが変わるので、探しの重複の判定にも入れる
    li = self.leader()
    return (_orig_key(self), li is not None and li in self.moved)
def use(still):
    State.solved, State.key = (solved_still, key_still) if still else (_orig_solved, _orig_key)

def norm(cells):
    mx = min(c[0] for c in cells); my = min(c[1] for c in cells)
    return tuple(sorted((x - mx, y - my, p, f) for x, y, p, f in cells))

def run(t, depth=10):
    return solve(build(CH, Cfg(), tools=[] if t is None else [t]), depth=depth)

PL = "plank"
def row(*ps, y=0): return [(i, y, p, None) for i, p in enumerate(ps)]
NAMED = {
    "板3＋西端の上に石": row(PL, PL, PL, y=1) + [(0, 0, "stoneWeight", None)],
    "板3＋西端の上に鉄の重り": row(PL, PL, PL, y=1) + [(0, 0, "ironWeight", None)],
    "板3＋西端の上に鉄の棒": row(PL, PL, PL, y=1) + [(0, 0, "ironBar", None)],
    "鉄の重り＋板2（並び）": row("ironWeight", PL, PL),
    "板4＋西端の上に鉄の重り": row(PL, PL, PL, PL, y=1) + [(0, 0, "ironWeight", None)],
    "板3＋西端の上に小石（軽い）": row(PL, PL, PL, y=1) + [(0, 0, "pebble", None)],
    "板3＋西端の上に砂袋（軽い）": row(PL, PL, PL, y=1) + [(0, 0, "sandbag", None)],
    "石＋板2（並び・軽い）": row("stoneWeight", PL, PL),
    "板3（重りなし）": row(PL, PL, PL),
    "板4（重りなし）": row(PL, PL, PL, PL),
}

if __name__ == "__main__":
    print("課題「崖の先の印」：\n" + "\n".join("  " + r for r in CH["map"]) + f"\n  当主 (0,2)、印 {CH['goal']}")
    use(True)
    print("\n[この場所の条件（印で止まる）]")
    print(f"  素手：{run(None)[0]}")
    for k, t in NAMED.items():
        n, path = run(t)
        print(f"  {k:24s} {'-' if n is None else str(n) + '手  ' + ' → '.join(fmt_act(a) for a in path)}")
    # 板だけの道具：作業台 4×4 に板 1〜4 枚の、全部の形
    cells = [(x, y) for y in range(BENCH) for x in range(BENCH)]
    shapes = set()
    for k in range(1, SHELF["plank"] + 1):
        for comb in itertools.combinations(cells, k):
            shapes.add(norm([(x, y, PL, None) for x, y in comb]))
    ok = [s for s in shapes if run(s)[0] is not None]
    print(f"  板だけの道具（4×4 に板1〜4枚の形 {len(shapes)} 通り）で解けるもの：{len(ok)} 通り")
    # 棚の部品から、でたらめに作った道具
    rnd = random.Random(1)
    pool = [p for p, n in SHELF.items() for _ in range(n)]
    tried, solved_w, solved_now = 0, 0, []
    springs = ("spring", "ironSpring")
    for _ in range(int(os.environ.get("N", "1500"))):
        k = rnd.randint(1, 6)
        ps = rnd.sample(pool, k)
        pos = rnd.sample(cells, k)
        tool = norm([(x, y, p, rnd.choice(("up", "east", "west")) if p in springs else None) for (x, y), p in zip(pos, ps)])
        tried += 1
        if run(tool, depth=9)[0] is not None:
            heavy = sum(P[f"part.{p}.weight"] for _, _, p, _ in tool if p not in (PL,))
            solved_now.append(tool)
            if any(p in ("stoneWeight", "ironWeight", "ironBar", "pebble", "sandbag") for _, _, p, _ in tool):
                solved_w += 1
    print(f"  でたらめな道具 {tried} 個のうち解けた {len(solved_now)} 個（重り系・鉄の棒を含む {solved_w} 個）")
    nonw = [t for t in solved_now if not any(p in ("stoneWeight", "ironWeight", "ironBar", "pebble", "sandbag") for _, _, p, _ in t)]
    print(f"  そのうち重り系・鉄の棒を含まないもの：{len(nonw)} 個 {nonw[:3]}")
    use(False)
    print("\n[参考：挑む.md の「渡る」の条件そのまま（印にいればよい）]")
    for k in ("板3（重りなし）", "板4（重りなし）"):
        n, path = run(NAMED[k])
        print(f"  {k:24s} {'-' if n is None else str(n) + '手  ' + ' → '.join(fmt_act(a) for a in path)}")
