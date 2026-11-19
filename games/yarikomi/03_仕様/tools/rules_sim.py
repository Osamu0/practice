"""規則の計算.md の規則を小さく写した確かめ用の計算（game-spec-balance、2026-11-18）。

本番のコード（src/core/）ではない。値を決めるために、規則の一部を Python で写したもの。
入っている規則：重さ（ずれる 2-4）、落ちる（2-5、当たる、谷底、落ちて死ぬ、下敷き）、弾む（縮む・打ち出す 2-2、投げ当て）、
当主の手（挑む.md 3.1 の「進む」の3候補＝入る・登る・押す、置く、拾う、待つ）、敵（仮の歩く敵）、掟の大風（続きの動き）、長雨（重さの足し）。
谷と一生の小さな模型（Valley）：代の始めの棚（start.parts／heir.startParts）、拾うのはその代で初めて解けたときだけ、
死んだときの遺品（relic.wearOnDeath。2 をこえる部品は墓に入らず消える）、代替わりの傷み（仕掛け＝wearPerGen＋掟の足し、遺品＝wearPerGen だけ・その代替わりで建った墓は除く）。
入っていない規則：燃える（2-1）、引っぱる（2-3、縄・滑車・当主が引く）、水。→ これらの最強の一択・詰みは確かめていない。

値は ../パラメータ表.csv から読む（数を直に書かない）。
"""
import csv
import os
import random
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "..", "パラメータ表.csv")


def load_params(path=CSV_PATH):
    p = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = row["値"].strip()
            try:
                p[row["名前"]] = int(v)
            except ValueError:
                p[row["名前"]] = v
    return p


P = load_params()
W = H = P["board.size"]
DIRS = {"up": (0, -1), "down": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPP = {"up": "down", "down": "up", "east": "west", "west": "east"}
WET_MATERIAL = {"plank", "stake", "rope", "longRope", "pulley", "leafSpring", "sandbag", "oilCloth", "fuse"}


def pv(part, key, default=None):
    return P.get(f"part.{part}.{key}", default)


class Obj:
    __slots__ = ("kind", "part", "x", "y", "wear", "facing", "padd", "dist", "edir", "byLeader", "anc")

    def __init__(self, kind, x, y, part=None, facing=None, padd=0, wear=0, edir=0, byLeader=False, anc=False):
        self.kind, self.part, self.x, self.y = kind, part, x, y
        self.wear, self.facing, self.padd, self.dist, self.edir, self.byLeader = wear, facing, padd, 0, edir, byLeader
        self.anc = anc  # 先祖が据えた仕掛け（挑む中は拾えない：挑む.md 3章）

    def copy(self):
        o = Obj(self.kind, self.x, self.y, self.part, self.facing, self.padd, self.wear, self.edir, self.byLeader, self.anc)
        o.dist = self.dist
        return o


class Cfg:
    """1つの盤面の条件（掟・癖・規則の読み方の切り替え）"""

    def __init__(self, laws=(), traits=(), fall_cells=None):
        self.laws = set(laws)
        self.traits = set(traits)
        self.fall_cells = fall_cells if fall_cells is not None else P["rule.fall.cellsPerTurn"]

    def push_w(self):
        return P["leader.pushWeight"] + (P["trait.strong.pushWeightAdd"] if "strong" in self.traits else 0)

    def fall_death(self):
        return P["leader.fallDeathHeight"] + (P["trait.clumsy.fallHeightAdd"] if "clumsy" in self.traits else 0)


class State:
    def __init__(self, terrain, cfg):
        self.terrain = terrain  # list of str, '#'=地面 '.'=空き
        self.cfg = cfg
        self.objs = {}
        self.links = set()
        self.comp = {}  # spring id -> (G obj id, spring pos, G pos)
        self.nid = 0
        self.inv = ()
        self.dead = None
        self.goal = None
        self.kind = None
        self.moved = set()

    def copy(self):
        s = State.__new__(State)
        s.terrain, s.cfg = self.terrain, self.cfg
        s.objs = {k: o.copy() for k, o in self.objs.items()}
        s.links = set(self.links)
        s.comp = dict(self.comp)
        s.nid, s.inv, s.dead, s.goal, s.kind = self.nid, self.inv, self.dead, self.goal, self.kind
        s.moved = set()
        return s

    def add(self, o):
        i = self.nid
        self.nid += 1
        self.objs[i] = o
        return i

    # --- 盤面 ---
    def ground(self, x, y):
        return 0 <= x < W and 0 <= y < H and self.terrain[y][x] == "#"

    def occ(self):
        return {(o.x, o.y): i for i, o in self.objs.items()}

    def free(self, x, y, occ, ignore=()):
        if not (0 <= x < W and 0 <= y < H):
            return False
        if self.terrain[y][x] == "#":
            return False
        j = occ.get((x, y))
        return j is None or j in ignore

    def weight(self, i):
        o = self.objs[i]
        if o.kind == "leader":
            w = P["leader.weight"]
        elif o.kind == "enemy":
            w = P["enemy.crawler.weight"]
        elif o.kind == "cargo":
            w = P["challenge.cargo.weight"]
        elif o.kind == "grave":
            w = 0
        else:
            w = pv(o.part, "weight")
            if "longRain" in self.cfg.laws and o.part in WET_MATERIAL:
                w += P["law.longRain.wetWeightAdd"]
        return w

    def hardness(self, i):
        o = self.objs[i]
        if o.kind == "leader":
            return P["leader.hardness"]
        if o.kind == "enemy":
            return P["enemy.crawler.hardness"]
        if o.kind == "cargo":
            return P["challenge.cargo.hardness"]
        if o.kind == "grave":
            return 10 ** 9
        return pv(o.part, "hardness")

    def power(self, i):
        o = self.objs[i]
        return pv(o.part, "springPower") + o.padd

    def groups(self):
        parent = {i: i for i in self.objs}

        def f(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for a, b in self.links:
            if a in parent and b in parent:
                parent[f(a)] = f(b)
        g = {}
        for i in self.objs:
            g.setdefault(f(i), []).append(i)
        return [sorted(v) for v in g.values()]

    def gweight(self, g):
        return sum(self.weight(i) for i in g)

    def fixed(self, g):
        for i in g:
            o = self.objs[i]
            if o.kind == "grave":
                return True
            if o.part == "stake" and self.ground(o.x, o.y + 1):
                return True
        return False

    def supported_set(self, gs):
        occ = self.occ()
        gid = {}
        for k, g in enumerate(gs):
            for i in g:
                gid[i] = k
        sup = {k for k, g in enumerate(gs) if self.fixed(g)}
        changed = True
        while changed:
            changed = False
            for k, g in enumerate(gs):
                if k in sup:
                    continue
                for i in g:
                    o = self.objs[i]
                    bx, by = o.x, o.y + 1
                    if by >= H:
                        continue
                    if self.ground(bx, by):
                        sup.add(k); changed = True; break
                    j = occ.get((bx, by))
                    if j is not None and gid[j] != k and gid[j] in sup:
                        sup.add(k); changed = True; break
        return sup, gid

    def order(self, gs):
        def key(g):
            return (-max(self.objs[i].y for i in g), min(self.objs[i].x for i in g), min(g))
        return sorted(gs, key=key)

    def remove(self, i):
        del self.objs[i]
        self.links = {l for l in self.links if i not in l}
        self.comp = {s: v for s, v in self.comp.items() if s != i and v[0] != i}

    def break_obj(self, i, why):
        o = self.objs.get(i)
        if o is None:
            return
        if o.kind == "leader":
            self.dead = why
        elif o.kind == "part":
            o.wear += P["rule.impact.wearAdd"]
            if o.wear > 2:
                self.remove(i)
        elif o.kind in ("enemy", "cargo"):
            self.remove(i)

    def move_group(self, g, dx, dy):
        for i in g:
            self.objs[i].x += dx
            self.objs[i].y += dy

    # --- 2-2 弾む ---
    def step_bounce(self):
        for s in sorted(self.comp):
            if s not in self.comp:
                continue
            gi, spos, gpos = self.comp.pop(s)
            if s not in self.objs or gi not in self.objs:
                continue
            so, go = self.objs[s], self.objs[gi]
            if (so.x, so.y) != spos or (go.x, go.y) != gpos:
                continue
            gs = self.groups()
            g = next(x for x in gs if gi in x)
            if any(i in self.moved for i in g):
                continue
            d = max(0, self.power(s) - self.gweight(g))
            dx, dy = DIRS[so.facing]
            moved = 0
            for _ in range(d):
                occ = self.occ()
                block = None
                ok = True
                for i in g:
                    o = self.objs[i]
                    nx, ny = o.x + dx, o.y + dy
                    if not (0 <= nx < W and 0 <= ny < H) or self.ground(nx, ny):
                        ok = False
                        continue
                    j = occ.get((nx, ny))
                    if j is not None and j not in g:
                        ok = False
                        block = j
                if not ok:
                    if moved >= 1 and block is not None:
                        bo = self.objs[block]
                        if bo.kind == "part" and pv(bo.part, "springPower") is not None and bo.facing == OPP[so.facing]:
                            self.comp[block] = (gi, (bo.x, bo.y), (self.objs[gi].x, self.objs[gi].y))
                        else:
                            bgs = self.groups()
                            bg = next(x for x in bgs if block in x)
                            if not self.fixed(bg) and self.gweight(g) >= self.hardness(block):
                                self.break_obj(block, "投げ当て")
                    break
                self.move_group(g, dx, dy)
                moved += 1
            for i in g:
                if i in self.objs:
                    self.objs[i].dist = 0
                    self.moved.add(i)
            if moved:
                self.drift(g)
            if self.dead:
                return

    def drift(self, g):
        if "strongWind" not in self.cfg.laws:
            return
        for _ in range(P["law.strongWind.driftCells"]):
            occ = self.occ()
            if all(i in self.objs and self.free(self.objs[i].x + 1, self.objs[i].y, occ, g) for i in g):
                self.move_group(g, 1, 0)
            else:
                break

    # --- 2-4 ずれる ---
    def step_slide(self):
        gs = self.groups()
        sup, gid = self.supported_set(gs)
        occ = self.occ()
        for g in self.order(gs):
            if any(i in self.moved or i not in self.objs for i in g):
                continue
            if len(g) < 2 or self.fixed(g):
                continue
            k = gid[g[0]]
            if k not in sup:
                continue
            gset = set(g)
            cols = []
            for i in g:
                o = self.objs[i]
                by = o.y + 1
                if by < H and (self.ground(o.x, by) or (occ.get((o.x, by)) is not None and occ[(o.x, by)] not in gset and gid[occ[(o.x, by)]] in sup)):
                    cols.append(o.x)
            if not cols:
                continue
            xW, xE = min(cols), max(cols)
            load = {}
            stack = set()
            for x in set(self.objs[i].x for i in g):
                top = min(self.objs[i].y for i in g if self.objs[i].x == x)
                l = sum(self.weight(i) for i in g if self.objs[i].x == x)
                y = top - 1
                while y >= 0 and occ.get((x, y)) is not None and occ[(x, y)] not in gset:
                    j = occ[(x, y)]
                    l += self.weight(j)
                    stack.add(j)
                    y -= 1
                load[x] = l
            mE = sum(l * (x - xE) for x, l in load.items() if x > xE)
            rE = sum(l * (xE - x) for x, l in load.items() if x < xE)
            mW = sum(l * (xW - x) for x, l in load.items() if x < xW)
            rW = sum(l * (x - xW) for x, l in load.items() if x > xW)
            east, west = mE > rE, mW > rW
            if east == west:
                continue
            dx = 1 if east else -1
            # 積み重なった物は、その組ごと一緒に動かす
            mv = set(g)
            for j in stack:
                mv |= set(next(x for x in gs if j in x))
            if all(self.free(self.objs[i].x + dx, self.objs[i].y, occ, mv) for i in mv):
                self.move_group(list(mv), dx, 0)
                self.moved |= mv
                occ = self.occ()

    # --- 2-5 落ちる ---
    def step_fall(self):
        done = set()
        while True:
            gs = self.groups()
            cand = [g for g in self.order(gs) if not any(i in self.moved or i in done for i in g) and not self.fixed(g)]
            if not cand:
                break
            g = cand[0]
            done |= set(g)
            self.fall_group(g)
            if self.dead:
                return
        gs = self.groups()
        sup, gid = self.supported_set(gs)
        for k, g in enumerate(gs):
            if k in sup:
                for i in g:
                    self.objs[i].dist = 0

    def fall_group(self, g):
        fell = 0
        blockers = []
        for _ in range(self.cfg.fall_cells):
            gs = self.groups()
            sup, gid = self.supported_set(gs)
            if gid[g[0]] in sup:
                break
            occ = self.occ()
            blockers = []
            exit_ = False
            for i in g:
                o = self.objs[i]
                ny = o.y + 1
                if ny >= H:
                    exit_ = True
                    continue
                if self.ground(o.x, ny):
                    blockers.append(None)
                j = occ.get((o.x, ny))
                if j is not None and j not in g:
                    blockers.append(j)
            if blockers:
                break
            self.move_group(g, 0, 1)
            fell += 1
            if exit_ or any(self.objs[i].y >= H for i in g):
                for i in list(g):
                    if self.objs[i].kind == "leader":
                        self.dead = "谷底へ落ちる"
                    self.remove(i)
                return
        if fell == 0:
            return
        for i in g:
            self.objs[i].dist += fell
            self.moved.add(i)
        gd = max(self.objs[i].dist for i in g)
        # 止まった：真下の物を見る
        occ = self.occ()
        below = []
        for i in g:
            o = self.objs[i]
            j = occ.get((o.x, o.y + 1))
            if j is not None and j not in g and j not in below:
                below.append(j)
        compressed = False
        for j in sorted(below):
            bo = self.objs[j]
            if bo.kind == "part" and pv(bo.part, "springPower") is not None and bo.facing == "up":
                gi = min(i for i in g if self.objs[i].x == bo.x)
                self.comp[j] = (gi, (bo.x, bo.y), (self.objs[gi].x, self.objs[gi].y))
                compressed = True
                break
        if compressed:
            for i in g:
                self.objs[i].dist = 0
        else:
            if gd >= P["rule.impact.minFall"]:
                gs = self.groups()
                for j in sorted(below):
                    if j not in self.objs:
                        continue
                    bg = next(x for x in gs if j in x)
                    if self.fixed(bg):
                        continue
                    if self.gweight(g) >= self.hardness(j):
                        self.break_obj(j, "下敷き")
            if any(self.objs[i].kind == "leader" for i in g if i in self.objs) and gd >= self.cfg.fall_death():
                self.dead = "落ちて死ぬ"
        if not self.dead:
            self.drift([i for i in g if i in self.objs])

    # --- 段3 敵（仮：歩いて、崖の手前で向きを変える） ---
    def step_enemy(self):
        gs = self.groups()
        sup, gid = self.supported_set(gs)
        for i in sorted(self.objs):
            o = self.objs.get(i)
            if o is None or o.kind != "enemy" or o.edir == 0:
                continue
            if gid[i] not in sup:
                continue
            occ = self.occ()
            tx = o.x + o.edir
            j = occ.get((tx, o.y))
            if j is not None and self.objs[j].kind == "leader":
                self.dead = "敵"
                return
            below_ok = (o.y + 1 < H) and (self.ground(tx, o.y + 1) or occ.get((tx, o.y + 1)) is not None)
            if self.free(tx, o.y, occ) and below_ok:
                o.x = tx
            else:
                o.edir = -o.edir

    # --- 1手 ---
    def leader(self):
        for i, o in self.objs.items():
            if o.kind == "leader":
                return i
        return None

    # --- 段1「進む」の3候補（挑む.md 3.1）。どれも手の始めの盤面で決める ---
    def _climb_solid(self, x, y, occ, sup, gid):
        """登る足場：地面、固定物、支えのある組のマス（当主と敵は除く）"""
        if not (0 <= x < W and 0 <= y < H):
            return False
        if self.ground(x, y):
            return True
        j = occ.get((x, y))
        if j is None or self.objs[j].kind in ("leader", "enemy"):
            return False  # 当主と敵は足場にならない（プロデューサーの決め、2026-11-19）
        return gid[j] in sup  # sup には固定の組も入っている

    def climb_dest(self, d):
        """登るの行き先 (x', y-k)。候補に出ないなら None"""
        L = self.objs[self.leader()]
        tx = L.x + d
        if not (0 <= tx < W):
            return None
        occ = self.occ()
        sup, gid = self.supported_set(self.groups())
        if not self._climb_solid(tx, L.y, occ, sup, gid):
            return None
        for k in range(1, P["leader.climbHeight"] + 1):
            ty = L.y - k
            if ty < 0:
                return None  # 盤の上の外
            if not self.free(L.x, ty, occ):
                return None  # 頭の上がふさがっている
            if self.free(tx, ty, occ):
                return (tx, ty)  # いちばん小さい k
            if not self._climb_solid(tx, ty, occ, sup, gid):
                return None  # 途中のマスが足場でない（支えのない組など）
        return None  # climbHeight 段より上にしか空きがない

    def push_ok(self, d):
        L = self.objs[self.leader()]
        tx = L.x + d
        if not (0 <= tx < W):
            return False
        occ = self.occ()
        j = occ.get((tx, L.y))
        if j is None:
            return False
        g = next(x for x in self.groups() if j in x)
        if self.fixed(g) or any(self.objs[i].kind == "leader" for i in g):
            return False
        if self.gweight(g) > self.cfg.push_w():
            return False
        return all(self.free(self.objs[i].x + d, self.objs[i].y, occ, g) for i in g)

    def enter_ok(self, d):
        L = self.objs[self.leader()]
        return self.free(L.x + d, L.y, self.occ())

    def pickable(self, g):
        """拾える組：部品1つだけの組か、自分が置いた道具。先祖の仕掛けと固定の組は拾えない"""
        if not all(self.objs[i].kind == "part" for i in g) or self.fixed(g):
            return False
        if any(self.objs[i].anc for i in g):
            return False
        return len(g) == 1 or all(self.objs[i].byLeader for i in g)

    def actions(self):
        acts = [("wait",)]
        li = self.leader()
        L = self.objs[li]
        occ = self.occ()
        for d in (-1, 1):
            if self.enter_ok(d):
                acts.append(("enter", d))
            if self.climb_dest(d) is not None:
                acts.append(("climb", d))
            if self.push_ok(d):
                acts.append(("push", d))
        # 置く
        for ti, tool in enumerate(sorted(set(self.inv))):
            seen = set()
            for (ax, ay) in ((L.x + 1, L.y), (L.x - 1, L.y), (L.x, L.y - 1), (L.x, L.y + 1)):
                for (dx, dy, *_r) in tool:
                    ox, oy = ax - dx, ay - dy
                    if (ox, oy) in seen:
                        continue
                    seen.add((ox, oy))
                    if all(self.free(ox + tx, oy + ty, occ) for (tx, ty, *_r2) in tool):
                        acts.append(("place", tool, ox, oy))
        # 拾う（隣の、拾える組）
        for g in self.groups():
            if not self.pickable(g):
                continue
            if any(abs(self.objs[i].x - L.x) + abs(self.objs[i].y - L.y) == 1 for i in g):
                acts.append(("pick", tuple(g)))
        return acts

    def do(self, act):
        s = self.copy()
        li = s.leader()
        L = s.objs[li]
        if act[0] == "enter":
            if not s.enter_ok(act[1]):
                return None
            L.x += act[1]
        elif act[0] == "climb":
            dest = s.climb_dest(act[1])
            if dest is None:
                return None
            L.x, L.y = dest
        elif act[0] == "push":
            d = act[1]
            if not s.push_ok(d):
                return None
            j = s.occ()[(L.x + d, L.y)]
            g = next(x for x in s.groups() if j in x)
            s.move_group(g, d, 0)
            L.x += d
        elif act[0] == "place":
            _, tool, ox, oy = act
            ids = []
            for (tx, ty, part, facing, wear, padd) in tool:
                ids.append(s.add(Obj("part", ox + tx, oy + ty, part, facing, padd, wear, byLeader=True)))
            pos = {(s.objs[i].x, s.objs[i].y): i for i in ids}
            for i in ids:
                o = s.objs[i]
                for dx, dy, side, oside in ((1, 0, "east", "west"), (0, 1, "down", "up")):
                    j = pos.get((o.x + dx, o.y + dy))
                    if j is None:
                        continue
                    if s._conn(o, side) and s._conn(s.objs[j], oside):
                        s.links.add((min(i, j), max(i, j)))
            inv = list(s.inv)
            inv.remove(tool)
            s.inv = tuple(inv)
        elif act[0] == "pick":
            g = act[1]
            if len(s.inv) >= P["leader.carryTools"]:
                return None
            mx = min(s.objs[i].x for i in g)
            my = min(s.objs[i].y for i in g)
            tool = tuple(sorted((s.objs[i].x - mx, s.objs[i].y - my, s.objs[i].part, s.objs[i].facing, s.objs[i].wear, s.objs[i].padd) for i in g))
            for i in g:
                s.remove(i)
            s.inv = tuple(sorted(s.inv + (tool,)))
        elif act[0] != "wait":
            raise ValueError(act)
        s.step_rules()
        return s

    def _conn(self, o, side):
        if pv(o.part, "springPower") is not None:
            return side != o.facing
        if o.part == "stake":
            return side != "down"
        return True

    def step_rules(self):
        self.moved = set()
        for f in (self.step_bounce, self.step_slide, self.step_fall):
            f()
            if self.dead:
                return
        self.step_enemy()

    def solved(self):
        if self.dead:
            return False
        li = self.leader()
        if self.kind == "cross":
            o = self.objs[li]
            return (o.x, o.y) == self.goal
        if self.kind == "repel":
            return not any(o.kind == "enemy" for o in self.objs.values())
        if self.kind == "carry":
            return any(o.kind == "cargo" and (o.x, o.y) == self.goal for o in self.objs.values())
        return False

    def key(self):
        objs = tuple(sorted((o.kind, o.part, o.x, o.y, o.wear, o.facing, o.padd, min(o.dist, 9), o.edir) for o in self.objs.values()))
        lk = tuple(sorted(tuple(sorted(((self.objs[a].x, self.objs[a].y), (self.objs[b].x, self.objs[b].y)))) for a, b in self.links))
        ck = tuple(sorted(((self.objs[s].x, self.objs[s].y), v[2]) for s, v in self.comp.items() if s in self.objs))
        return (objs, lk, ck, self.inv)


def make_tool(spec, cfg=None):
    """spec: [(dx, dy, part, facing)]。せっかちの当主が組むと、ばねに強さの足しを焼き込む"""
    padd = P["trait.hasty.springPowerAdd"] if cfg and "hasty" in cfg.traits else 0
    out = []
    for (dx, dy, part, facing) in spec:
        pa = padd if pv(part, "springPower") is not None else 0
        out.append((dx, dy, part, facing, 0, pa))
    return tuple(sorted(out))


def build(ch, cfg, tools=(), extra=()):
    s = State(ch["map"], cfg)
    s.kind = ch["kind"]
    s.goal = ch.get("goal")
    for y, row in enumerate(ch["objs"]):
        for x, c in enumerate(row):
            if c == "L":
                s.add(Obj("leader", x, y))
            elif c == "E":
                s.add(Obj("enemy", x, y, edir=ch.get("edir", 0)))
            elif c == "C":
                s.add(Obj("cargo", x, y))
            elif c == "T":
                s.add(Obj("grave", x, y))
    for (x, y, part, facing, wear) in extra:  # 先祖の仕掛け（据えた物）
        s.add(Obj("part", x, y, part, facing, 0, wear, anc=True))
    # 先祖の仕掛けはつなぎ点でつなぐ
    pos = {(o.x, o.y): i for i, o in s.objs.items() if o.kind == "part"}
    for (x, y), i in pos.items():
        for dx, dy in ((1, 0), (0, 1)):
            j = pos.get((x + dx, y + dy))
            if j is not None:
                s.links.add((min(i, j), max(i, j)))
    s.inv = tuple(sorted(make_tool(t, cfg) for t in tools))
    return s


def solve(start, depth=10, cap=300000):
    """手の数が少ない順に探す。解ける最短の手数を返す（解けなければ None）"""
    if start.solved():
        return 0, []
    q = deque([(start, [])])
    seen = {start.key()}
    n = 0
    while q:
        s, path = q.popleft()
        if len(path) >= depth:
            continue
        for a in s.actions():
            t = s.do(a)
            if t is None:
                continue
            if t.dead:
                continue
            k = t.key()
            if k in seen:
                continue
            seen.add(k)
            n += 1
            np = path + [a]
            if t.solved():
                return len(np), np
            if n > cap:
                return None, "cap"
            q.append((t, np))
    return None, []


def fmt_act(a):
    if a[0] == "place":
        return f"置く{[t[2] + ('' if t[3] is None else '(' + t[3] + ')') for t in a[1]]}@({a[2]},{a[3]})"
    if a[0] in ("enter", "climb", "push"):
        name = {"enter": "入る", "climb": "登る", "push": "押す"}[a[0]]
        return ("→" if a[1] == 1 else "←") + name
    if a[0] == "pick":
        return "拾う"
    return "待つ"


# ======================================================================
# 谷と一生の小さな模型（継承の一周.md 5章・6.3、谷と一生の流れ.md 1.1・3章・4章）
# 盤面の規則は持たない。部品の数・傷み・代だけを数える。
# ======================================================================
WEAR_MAX = 2  # 壊れかけ（傷みの段の上限。これをこえたら消える）


def parse_parts(spec):
    """'plank:3,stoneWeight:1' → ['plank', 'plank', 'plank', 'stoneWeight']"""
    out = []
    for item in str(spec).split(","):
        item = item.strip()
        if not item:
            continue
        pid, n = item.split(":")
        out += [pid.strip()] * int(n)
    return out


def split_tool(cells):
    """cells: {(x, y): (part, wear)}。消えた部品を除いたあと、つながりで分ける（2.1 と同じ。つなぎ点は隣どうしで近似）。
    2つ以上つながった塊は道具、1つだけは部品として返す"""
    left = dict(cells)
    tools, parts = [], []
    while left:
        start = min(left, key=lambda p: (p[1], p[0]))
        comp, q = {}, [start]
        while q:
            p = q.pop()
            if p not in left:
                continue
            comp[p] = left.pop(p)
            x, y = p
            q += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        if len(comp) >= 2:
            tools.append(comp)
        else:
            parts.append(next(iter(comp.values())))
    return tools, parts


class Grave:
    def __init__(self, gen, tools, parts):
        self.gen = gen  # 建った代（その代の当主が死んで建った）
        self.tools = tools  # [{(x, y): (part, wear)}]
        self.parts = parts  # [(part, wear)]

    def count(self):
        return sum(len(t) for t in self.tools) + len(self.parts)


class Valley:
    """relic_decay：墓の遺品も代替わりで傷むか。relic_skip_new：その代替わりで建った墓の遺品には足さないか（今の仕様＝True）"""

    def __init__(self, seed=1, relic_decay=True, relic_skip_new=True, first_pick_only=True, death_cap=False):
        self.seed = seed
        self.gen = 1
        self.laws = set()
        self.year = P["valley.startYear"]
        self.shelf = [(p, 0) for p in parse_parts(P["start.parts"])]
        self.tools = []
        self.graves = []
        self.fixtures = []  # [{(x, y): (part, wear)}] 谷に据えた仕掛け
        self.picked = set()  # この代に拾った場所（この代の記録から決まる、の写し）
        self.relic_decay, self.relic_skip_new, self.first_pick_only = relic_decay, relic_skip_new, first_pick_only
        # death_cap：True＝遺品になるときの傷みを壊れかけ（2）で止める（前の仕様。毎代取り戻すと消えない：パラメータ表 13.3 #10）。
        # False（既定＝今の仕様）＝2 をこえる部品は墓に入らず消える
        self.death_cap = death_cap

    # 結果：拾う（谷と一生の流れ.md 3章）
    def solve(self, place, table):
        self.year += P["challenge.yearsCost"]
        if self.first_pick_only and place in self.picked:
            return []
        self.picked.add(place)
        rng = random.Random(f"{self.seed}/代{self.gen}/場所{place}/拾う")
        got = [table[rng.randrange(len(table))] for _ in range(min(P["pickup.drawCount"], max(1, len(table))))] if table else []
        self.shelf += [(p, 0) for p in got]
        self.shelf = self.shelf[:P["leader.carryParts"]]  # あふれは置いていく（どれを置くかの選びは見ない）
        return got

    def place_fixture(self, cells):
        """棚の部品から据える仕掛けを作る（cells: {(x, y): part}）。棚に無ければ作らない"""
        need = list(cells.values())
        names = [p for p, _ in self.shelf]
        for p in need:
            if p not in names:
                return False
            names.remove(p)
        fx = {}
        for pos, p in cells.items():
            k = next(i for i, (q, _) in enumerate(self.shelf) if q == p)
            fx[pos] = self.shelf.pop(k)
        self.fixtures.append(fx)
        return True

    # 取り戻す（継承の一周.md 5章：道具→部品の順、入る分だけ）
    def retrieve(self, grave):
        while grave.tools and len(self.tools) < P["leader.carryTools"]:
            self.tools.append(grave.tools.pop(0))
        while grave.parts and len(self.shelf) < P["leader.carryParts"]:
            self.shelf.append(grave.parts.pop(0))

    def die(self):
        w = P["relic.wearOnDeath"]
        if self.death_cap:
            tools = [{pos: (p, min(WEAR_MAX, wr + w)) for pos, (p, wr) in t.items()} for t in self.tools]
            parts = [(p, min(WEAR_MAX, wr + w)) for p, wr in self.shelf]
        else:
            tools, parts = [], []
            for t in self.tools:
                tt, pp = split_tool(self._wear_cells(t, lambda p: w))
                tools += tt
                parts += pp
            parts += [(p, wr + w) for p, wr in self.shelf if wr + w <= WEAR_MAX]
        g = Grave(self.gen, tools, parts)
        self.graves.append(g)
        self.tools, self.shelf = [], []
        return g

    def _wear_cells(self, cells, add):
        out = {}
        for pos, (p, wr) in cells.items():
            a = add(p)
            if wr + a <= WEAR_MAX:
                out[pos] = (p, wr + a)
        return out

    def succession(self, new_laws=()):
        """継承の一周.md 6.3 の 1〜5"""
        self.year += P["succession.yearsBetween"]  # 1
        self.laws = set(new_laws)  # 2（引き方は見ない）
        # 3 作業台：見ない
        self.shelf = [(p, 0) for p in parse_parts(P["heir.startParts"])]  # 4
        self.tools = []
        # 5 谷の仕掛け：wearPerGen ＋ 掟の足し ＋ 災いの足し
        def fx_add(p):
            a = P["fixture.wearPerGen"] + P["calamity.fixtureWearAdd"]
            if "longRain" in self.laws and p in WET_MATERIAL:
                a += P["law.longRain.fixtureWearAdd"]
            return a
        nf = []
        for fx in self.fixtures:
            fx = self._wear_cells(fx, fx_add)
            t, ps = split_tool(fx)
            nf += t + [{(0, 0): q} for q in ps]  # 1つだけ残った部品も、その場の仕掛けとして残す
        self.fixtures = nf
        # 5 墓の遺品：wearPerGen だけ。この代替わりで建った墓（この代の当主の墓）は除く
        if self.relic_decay:
            for g in self.graves:
                if self.relic_skip_new and g.gen == self.gen:
                    continue
                add = P["fixture.wearPerGen"]
                tools, parts = [], []
                for t in g.tools:
                    tt, pp = split_tool(self._wear_cells(t, lambda p: add))
                    tools += tt
                    parts += pp
                parts += [(p, wr + add) for p, wr in g.parts if wr + add <= WEAR_MAX]
                g.tools, g.parts = tools, parts
        self.gen += 1
        self.picked = set()

    def stock(self):
        """谷に眠る部品（墓の遺品＋据えた仕掛け）"""
        return sum(g.count() for g in self.graves) + sum(len(f) for f in self.fixtures)
