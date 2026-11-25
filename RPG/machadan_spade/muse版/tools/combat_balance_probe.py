#!/usr/bin/env python3
"""Deterministic, dependency-free combat balance probe for the Muse rules.

This is a diagnostic model, not a second rules engine.  It deliberately models a
small, documented subset of combat so that changes to hit chances, encounter
composition, and representative risk can be compared reproducibly.  Narrative
control, most consumables/bespoke skills, scouting, retreat, status effects, and
boss puzzle counters remain outside the model; a GM must still test those at the
table.

Examples:
    python3 combat_balance_probe.py --self-test
    python3 combat_balance_probe.py --json --trials 5000 --seed 9001
    python3 combat_balance_probe.py --early-calibration --json --trials 5000 --seed 9042
    python3 combat_balance_probe.py --campaign-calibration --campaign-growth sparse --campaign-stocked --json --trials 5000 --seed 9042

The default all-floor report uses historical Base45 allocations only. It is not
validation of the new Base33 progression. Use --early-calibration for the
declared fresh-build comparison with purchased gear and basic starting skills.
"""

# Historical v4.12 fixed enemy fixtures. v4.13 live catalog: 運用/戦闘調整データ.json; use balance_v413.py.
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from typing import Iterable

sys.dont_write_bytecode = True


SEED = 90_042
TRIALS = 5_000
ROUND_LIMIT = 60
FLOORS = (1, 3, 5, 7, 8)
TWO_D10_COUNTS = tuple(range(1, 11)) + tuple(range(9, 0, -1))


def opposed_probability(attacker_bonus: int, defender_bonus: int) -> Fraction:
    """Exact P(attacker + 2d10 >= defender + 2d10).

    The attacker wins ties, as specified by the combat rules.  There are exactly
    10,000 equiprobable pairs of 2d10 results, so no floating-point arithmetic is
    used in the calculation.
    """

    wins = 0
    for attacker_sum, attacker_count in enumerate(TWO_D10_COUNTS, start=2):
        for defender_sum, defender_count in enumerate(TWO_D10_COUNTS, start=2):
            if attacker_bonus + attacker_sum >= defender_bonus + defender_sum:
                wins += attacker_count * defender_count
    return Fraction(wins, 10_000)


@dataclass(frozen=True)
class Blueprint:
    name: str
    lp: int
    strength: int
    defense: int
    intelligence: int
    speed: int
    technique: int
    role: str = "attacker"
    attack_kind: str = "physical"
    penetration: bool = False
    multiattack: int = 1
    area_every: int = 0
    area_kind: str = ""
    area_channelled: bool = False
    frontline: bool = True
    cunning: bool = False
    threat: str = "standard"
    fire_light_counter: bool = False
    rage_at: float = 0.0
    rage_strength: int = 0
    regeneration: int = 0
    stun_chance: float = 0.0
    initial_job: str = ""
    magic_power: int = 0
    magic_cost: int = 0
    magic_min_int: int = 7
    healing_potions: int = 0


@dataclass
class Unit:
    spec: Blueprint
    lp: int
    mp: int
    observed_healer: bool = False
    skip_actions: int = 0
    grit_remaining: int = 0
    strong_remaining: int = 0
    sweep_remaining: int = 0
    focus_remaining: int = 0
    vital_remaining: int = 0
    first_aid_remaining: int = 0
    first_aid_targets: set[str] = field(default_factory=set)
    healing_potions: int = 0

    @classmethod
    def from_blueprint(cls, spec: Blueprint) -> "Unit":
        return cls(spec=spec, lp=spec.lp, mp=spec.intelligence,
                   grit_remaining=1 if spec.initial_job == "warrior" else 0,
                   strong_remaining=2 if spec.initial_job == "warrior" else 0,
                   sweep_remaining=2 if spec.initial_job == "warrior" else 0,
                   focus_remaining=2 if spec.initial_job == "mage" else 0,
                   vital_remaining=2 if spec.initial_job in {"hunter", "thief"} else 0,
                   first_aid_remaining=2 if spec.initial_job == "priest" else 0,
                   healing_potions=spec.healing_potions)

    @property
    def active(self) -> bool:
        return self.lp > 0


# Representative canonical enemies from 数値正本.md.  Every standard/elite
# composition below names an existing individual; this probe never fabricates a
# weaker clone.  Missing legal weak roles produce an explicitly under-budget
# composition, as the live rules require, rather than a hidden stat nerf.
GOBLIN = Blueprint("ゴブリンの小兵", 25, 10, 5, 4, 8, 6, threat="weak")
BAT = Blueprint("大コウモリ", 18, 8, 4, 3, 13, 7)
NOVICE = Blueprint("駆け出しの女冒険者", 23, 7, 6, 8, 7, 6,
                   attack_kind="magic", magic_power=3, magic_cost=2)
PETITE_SLIME = Blueprint("プチスライム娘", 36, 9, 11, 6, 5, 4, threat="weak")
DESIRE_YOUNG = Blueprint("欲望の幼体", 40, 11, 8, 13, 9, 7, attack_kind="magic")
IMP = Blueprint("インプガール", 25, 8, 5, 10, 12, 9, attack_kind="magic")
WORKER_BEE = Blueprint("ワーカービー", 15, 10, 5, 6, 14, 10, threat="weak")
CAT_BURGLAR = Blueprint("猫獣人の女盗賊", 65, 17, 7, 8, 17, 16, cunning=True)
ACID_JELLY = Blueprint("アシッドジェリー", 57, 13, 15, 7, 4, 5)
SHADOW_STALKER = Blueprint(
    "影潜み", 69, 21, 7, 6, 15, 13, cunning=True, threat="strong"
)
LAMIA = Blueprint("ラミアダンサー（6F侵入個体）", 79, 18, 11, 15, 13, 12, cunning=True)
ALRAUNE = Blueprint("アルラウネ（6F侵入個体）", 87, 11, 13, 18, 7, 11, attack_kind="magic")
DARK_KNIGHT = Blueprint(
    "闇の騎士", 115, 26, 19, 9, 11, 17,
    penetration=True, cunning=True, threat="strong",
)
DARK_ELF = Blueprint(
    "ダークエルフの暗殺者", 63, 20, 11, 19, 21, 23,
    multiattack=2, cunning=True, threat="strong",
)

STANDARD_COMPOSITIONS: dict[int, dict[int, list[Blueprint]]] = {
    1: {1: [BAT], 2: [BAT, GOBLIN], 3: [BAT, NOVICE]},
    3: {1: [DESIRE_YOUNG], 2: [DESIRE_YOUNG, PETITE_SLIME], 3: [DESIRE_YOUNG, IMP]},
    5: {1: [CAT_BURGLAR], 2: [CAT_BURGLAR, WORKER_BEE], 3: [CAT_BURGLAR, ACID_JELLY]},
    # 7F has no native standard/weak roster; named 6F individuals enter from
    # the adjacent floor.  The two-PC case is deliberately one point under.
    7: {1: [LAMIA], 2: [LAMIA], 3: [LAMIA, ALRAUNE]},
}

ELITE_COMPOSITIONS: dict[int, dict[int, list[Blueprint]]] = {
    5: {
        1: [SHADOW_STALKER],
        2: [SHADOW_STALKER, WORKER_BEE],
        3: [SHADOW_STALKER, WORKER_BEE],
    },
    # No legal weak roster exists at 7F/8F.  A single named strong enemy is
    # used as a transparent lower-bound stress case instead of invented mobs.
    7: {1: [DARK_KNIGHT], 2: [DARK_KNIGHT], 3: [DARK_KNIGHT]},
    8: {1: [DARK_ELF], 2: [DARK_ELF], 3: [DARK_ELF]},
}

BOSSES: dict[int, Blueprint] = {
    1: Blueprint("はぐれ狼", 64, 16, 7, 3, 12, 9, cunning=True),
    3: Blueprint(
        "スライムクイーン", 57, 11, 15, 10, 6, 7,
        area_every=3, area_kind="magic", cunning=True,
    ),
    5: Blueprint(
        "キラービークイーン", 65, 19, 11, 6, 17, 15,
        multiattack=2, cunning=True,
    ),
    7: Blueprint(
        "ミノタウロスの長", 181, 32, 17, 5, 9, 13,
        penetration=True, cunning=True, rage_at=0.30, rage_strength=10,
        stun_chance=0.30,
    ),
    8: Blueprint(
        "エルダーリッチ", 120, 11, 16, 33, 15, 21,
        area_every=4, area_kind="magic", area_channelled=True,
        frontline=False, cunning=True,
        regeneration=5,
    ),
}


PARTY_NAMES = (
    "solo_fighter",
    "solo_production",
    "fighter_plus_producer",
    "frontline_healer_attacker",
)


def _progression(floor: int) -> tuple[int, int]:
    """Return representative permanent-growth and equipment point budgets."""

    return {
        1: (0, 2),
        3: (3, 4),
        5: (7, 6),
        7: (10, 8),
        8: (13, 10),
    }[floor]


def _fire_bonus(size: int) -> tuple[int, int]:
    return {1: (3, 12), 2: (2, 8), 3: (1, 5)}[size]


def _lp_fruits(floor: int) -> int:
    """Declared representative LP-fruit allocation, not free level growth."""

    return {1: 0, 3: 0, 5: 1, 7: 1, 8: 2}[floor]


def _scaled_player(archetype: str, floor: int, size: int) -> Blueprint:
    growth, equipment = _progression(floor)
    fire_stat, fire_lp = _fire_bonus(size)

    if archetype == "fighter":
        base = dict(strength=10, defense=9, intelligence=5, speed=7, technique=9)
        base["strength"] += (growth + 2) // 3 + (equipment + 1) // 2
        base["defense"] += growth // 3 + equipment // 2
        base["technique"] += growth - ((growth + 2) // 3) - (growth // 3)
        role, kind, front = "frontline", "physical", True
        job_lp_bonus = 10
    elif archetype == "producer":
        base = dict(strength=6, defense=7, intelligence=13, speed=7, technique=7)
        base["intelligence"] += (growth + 1) // 2 + (equipment + 2) // 3
        base["defense"] += growth // 4 + equipment // 3
        base["technique"] += growth - ((growth + 1) // 2) - (growth // 4)
        base["technique"] += equipment - ((equipment + 2) // 3) - (equipment // 3)
        role, kind, front = "producer", "magic", False
        job_lp_bonus = 0
    elif archetype == "healer":
        base = dict(strength=6, defense=8, intelligence=12, speed=7, technique=7)
        base["intelligence"] += (growth + 1) // 2 + equipment // 2
        base["defense"] += growth // 3 + equipment - equipment // 2
        base["technique"] += growth - ((growth + 1) // 2) - (growth // 3)
        role, kind, front = "healer", "magic", False
        job_lp_bonus = 0
    elif archetype == "attacker":
        if floor == 7:
            # A prepared deep-floor party brings an arcane attacker against the
            # 7F high-DEF roster instead of blindly using ineffective steel.
            base = dict(strength=6, defense=6, intelligence=12, speed=9, technique=10)
            base["intelligence"] += (growth + 1) // 2 + equipment // 2
            base["technique"] += growth - ((growth + 1) // 2) + equipment - equipment // 2
            role, kind, front = "attacker", "magic", False
        else:
            base = dict(strength=9, defense=6, intelligence=5, speed=10, technique=10)
            base["strength"] += (growth + 1) // 2 + equipment // 2
            base["technique"] += growth - ((growth + 1) // 2) + equipment - equipment // 2
            role, kind, front = "attacker", "physical", False
        job_lp_bonus = 5
    else:  # pragma: no cover - protected by internal callers
        raise ValueError(archetype)

    for key in base:
        base[key] += fire_stat
    return Blueprint(
        name=archetype,
        lp=20 + job_lp_bonus + 3 * _lp_fruits(floor) + fire_lp,
        role=role,
        attack_kind=kind,
        frontline=front,
        initial_job={"fighter": "warrior", "producer": "mage", "healer": "priest",
                     "attacker": "mage" if kind == "magic" else "hunter"}[archetype],
        magic_power=3 if kind == "magic" and archetype != "healer" else 0,
        magic_cost=2 if kind == "magic" and archetype != "healer" else 0,
        **base,
    )


def party_blueprints(party_name: str, floor: int) -> list[Blueprint]:
    layouts = {
        "solo_fighter": ("fighter",),
        "solo_production": ("producer",),
        "fighter_plus_producer": ("fighter", "producer"),
        "frontline_healer_attacker": ("fighter", "healer", "attacker"),
    }
    layout = layouts[party_name]
    party = [_scaled_player(kind, floor, len(layout)) for kind in layout]
    if floor == 8 and len(layout) >= 2:
        # The final member carries the explicit fire/light regeneration counter.
        # Meteor cover is modeled separately only while that telegraphed area
        # spell resolves; it does not halve ordinary magic.
        party[-1] = replace(party[-1], fire_light_counter=True)
    # Names are stable and unique, which makes JSON and debugging easier.
    return [replace(spec, name=f"{spec.name}_{index + 1}") for index, spec in enumerate(party)]


def enemy_blueprints(floor: int, encounter: str, party_size: int) -> list[Blueprint]:
    if encounter == "boss":
        # Escorts are an upper limit, not a mandatory addition.  This probe keeps
        # bosses unescorted so their own curve is visible.
        return [BOSSES[floor]]
    if encounter == "elite":
        return list(ELITE_COMPOSITIONS[floor][party_size])
    return list(STANDARD_COMPOSITIONS[floor][party_size])


def _roll_2d10(rng: random.Random) -> int:
    return rng.randint(1, 10) + rng.randint(1, 10)


def _hit(attacker: Unit, defender: Unit, rng: random.Random) -> tuple[bool, bool]:
    attack_roll = _roll_2d10(rng)
    defense_roll = _roll_2d10(rng)
    hit = attacker.spec.technique + attack_roll >= defender.spec.speed + defense_roll
    return hit, attack_roll >= 19


def _damage(
    attacker: Unit,
    defender: Unit,
    rng: random.Random,
    critical: bool,
    attack_kind: str | None = None,
    cover: bool = False,
    damage_modifier: int = 0,
    base_power: int = 0,
) -> int:
    kind = attack_kind or attacker.spec.attack_kind
    if kind == "magic":
        result = attacker.spec.intelligence + base_power + rng.randint(1, 6) - defender.spec.intelligence
    else:
        defense = defender.spec.defense
        if attacker.spec.penetration:
            defense //= 2
        strength = attacker.spec.strength
        if attacker.spec.rage_at and attacker.lp <= attacker.spec.lp * attacker.spec.rage_at:
            strength += attacker.spec.rage_strength
        result = strength - defense + rng.randint(1, 6)
    result = max(2, max(2, result) + damage_modifier)
    if critical:
        result *= 2
    if kind == "magic" and cover:
        result = (result + 1) // 2
    return result


def _active(units: Iterable[Unit]) -> list[Unit]:
    return [unit for unit in units if unit.active]


def _pick_player_target(attacker: Unit, enemies: list[Unit]) -> Unit:
    # Players focus a nearly defeated foe, then a dangerous/high-TEC foe.
    return min(_active(enemies), key=lambda unit: (unit.lp, -unit.spec.technique, unit.spec.name))


def _pick_enemy_target(attacker: Unit, party: list[Unit]) -> Unit:
    active = _active(party)
    front = [unit for unit in active if unit.spec.frontline]
    if front:
        legal = front
    else:
        legal = active

    # Cunning enemies may target an *observed* healer only after that character
    # has healed.  They never inspect hidden role labels before observation.
    observed = [unit for unit in active if unit.observed_healer]
    can_use_magic = (attacker.spec.attack_kind == "magic"
                     and (not attacker.spec.magic_cost or attacker.mp >= attacker.spec.magic_cost))
    if attacker.spec.cunning and observed and (not front or can_use_magic):
        legal = observed
    return min(legal, key=lambda unit: (unit.lp / unit.spec.lp, unit.lp, unit.spec.name))


def _attack_once(
    attacker: Unit,
    defender: Unit,
    rng: random.Random,
    attack_kind: str | None = None,
    cover: bool = False,
    accuracy_modifier: int = 0,
    damage_modifier: int = 0,
    critical_threshold: int = 19,
    base_power: int = 0,
) -> dict[str, object]:
    attack_roll, defense_roll = _roll_2d10(rng), _roll_2d10(rng)
    margin = attacker.spec.technique + accuracy_modifier + attack_roll - defender.spec.speed - defense_roll
    hit, graze = margin >= 0, -2 <= margin < 0
    critical = attack_roll >= critical_threshold
    dealt = 0
    if hit or graze:
        dealt = (_damage(attacker, defender, rng, critical, attack_kind, cover,
                         damage_modifier, base_power) if hit else 2)
        _hurt(defender, dealt)
    if hit:
        if defender.active and attacker.spec.stun_chance:
            threshold = round(attacker.spec.stun_chance * 10)
            if defender.spec.speed >= 20:
                threshold -= 2
            elif defender.spec.speed >= 15:
                threshold -= 1
            elif defender.spec.speed <= 5:
                threshold += 1
            if defender.spec.initial_job in {"warrior", "priest"}:
                threshold -= 1  # Basic 頑健; no invented status resistance.
            if rng.randint(1, 10) <= max(1, min(9, threshold)):
                defender.skip_actions = max(defender.skip_actions, 1)
    return {"hit": hit, "graze": graze, "damage": dealt,
            "critical": hit and critical, "margin": margin}


def _hurt(defender: Unit, damage: int) -> None:
    if damage >= defender.lp and defender.grit_remaining:
        defender.grit_remaining -= 1
        defender.lp = 1
    else:
        defender.lp = max(0, defender.lp - damage)


@lru_cache(maxsize=16_384)
def _expected_attack(delta: int, raw_damage: int, modifier: int, critical_at: int, target_lp: int) -> float:
    """An explicit player-policy approximation, never an extra game rule.

    Compare current damage choices using the displayed/observed opponent model.
    Exact enemy-stat knowledge is acceptable in this offline sensitivity probe;
    live NPCs/players must still obtain their knowledge through play.
    """
    total = 0.0
    normal = [max(2, max(2, raw_damage + die) + modifier) for die in range(1, 7)]
    for attack, ac in enumerate(TWO_D10_COUNTS, 2):
        for defense, dc in enumerate(TWO_D10_COUNTS, 2):
            margin = delta + attack - defense
            if margin >= 0:
                damage = sum(min(target_lp, d * (2 if attack >= critical_at else 1)) for d in normal) / 6
            elif margin >= -2:
                damage = min(2, target_lp)
            else:
                continue
            total += ac * dc * damage / 10_000
    return total


def _player_attack(actor: Unit, enemies: list[Unit], rng: random.Random) -> None:
    target = _pick_player_target(actor, enemies)
    if (actor.spec.magic_cost and actor.spec.intelligence >= actor.spec.magic_min_int
            and actor.mp >= actor.spec.magic_cost):
        actor.mp -= actor.spec.magic_cost
        accuracy = 0
        if actor.focus_remaining:
            actor.focus_remaining -= 1
            accuracy = 2
        _attack_once(actor, target, rng, attack_kind="magic", base_power=actor.spec.magic_power,
                     accuracy_modifier=accuracy)
        return
    # A priest has no implicit Magic Bolt. A mage out of MP uses its actual
    # weapon STR; the probe does not create a free at-will offensive spell.
    delta = actor.spec.technique - target.spec.speed
    raw = actor.spec.strength - target.spec.defense
    baseline = _expected_attack(delta, raw, 0, 19, target.lp)
    if actor.sweep_remaining:
        adjacent = [foe for foe in _active(enemies) if foe.spec.frontline][:2]
        if len(adjacent) == 2:
            sweep = sum(_expected_attack(actor.spec.technique - foe.spec.speed,
                                         actor.spec.strength - foe.spec.defense, -2, 19, foe.lp)
                        for foe in adjacent)
            if sweep > baseline:
                actor.sweep_remaining -= 1
                for foe in adjacent:
                    _attack_once(actor, foe, rng, attack_kind="physical", damage_modifier=-2)
                return
    if actor.strong_remaining and _expected_attack(delta - 2, raw, 3, 19, target.lp) > baseline:
        actor.strong_remaining -= 1
        _attack_once(actor, target, rng, attack_kind="physical", accuracy_modifier=-2, damage_modifier=3)
    elif actor.vital_remaining:
        actor.vital_remaining -= 1
        _attack_once(actor, target, rng, attack_kind="physical", critical_threshold=17)
    else:
        _attack_once(actor, target, rng, attack_kind="physical")


def _healer_action(healer: Unit, party: list[Unit], enemies: list[Unit], floor: int, rng: random.Random) -> None:
    wounded = [unit for unit in _active(party) if unit.lp < unit.spec.lp]
    if wounded:
        target = min(wounded, key=lambda unit: unit.lp / unit.spec.lp)
        missing = target.spec.lp - target.lp
        if missing >= 6 and healer.mp >= 2 and healer.spec.intelligence >= 7:
            if floor >= 5 and healer.mp >= 6 and healer.spec.intelligence >= 15:
                healer.mp -= 6
                amount = healer.spec.intelligence + 12 + rng.randint(1, 6)
            else:
                healer.mp -= 2
                amount = healer.spec.intelligence + 5 + rng.randint(1, 6)
            target.lp += min(missing, amount)
            healer.observed_healer = True
            return
        if (missing >= 4 and healer.first_aid_remaining
                and target.spec.name not in healer.first_aid_targets):
            healer.first_aid_remaining -= 1
            healer.first_aid_targets.add(target.spec.name)
            target.lp += min(missing, rng.randint(1, 6) + 2)
            healer.observed_healer = True
            return
    _player_attack(healer, enemies, rng)


def _enemy_attack(actor: Unit, party: list[Unit], rng: random.Random) -> None:
    kind, power = actor.spec.attack_kind, 0
    if actor.spec.magic_cost:
        if actor.mp >= actor.spec.magic_cost and actor.spec.intelligence >= actor.spec.magic_min_int:
            target = _pick_enemy_target(actor, party)
            actor.mp -= actor.spec.magic_cost
            _attack_once(actor, target, rng, attack_kind="magic", base_power=actor.spec.magic_power)
            return
        kind = "physical"
    _attack_once(actor, _pick_enemy_target(actor, party), rng, attack_kind=kind, base_power=power)


def run_fight(
    party_specs: list[Blueprint],
    enemy_specs: list[Blueprint],
    floor: int,
    rng: random.Random,
    round_limit: int = ROUND_LIMIT,
    telemetry: dict | None = None,
) -> tuple[bool, bool, int]:
    party = [Unit.from_blueprint(spec) for spec in party_specs]
    enemies = [Unit.from_blueprint(spec) for spec in enemy_specs]
    prepared_meteor_cover = floor == 8 and len(party_specs) >= 2
    ever_down = False

    def finish(rounds: int) -> tuple[bool, bool, int]:
        if telemetry is not None:
            telemetry.update(
                starting_lp=sum(spec.lp for spec in party_specs),
                remaining_lp=sum(unit.lp for unit in party),
                mp_spent=sum(unit.spec.intelligence - unit.mp for unit in party),
                potions_used=sum(unit.spec.healing_potions - unit.healing_potions for unit in party),
                grit_used=sum(unit.spec.initial_job == "warrior" and unit.grit_remaining == 0 for unit in party),
                strong_blows_used=sum(2 - unit.strong_remaining for unit in party if unit.spec.initial_job == "warrior"),
                sweeps_used=sum(2 - unit.sweep_remaining for unit in party if unit.spec.initial_job == "warrior"),
            )
        return ever_down, not _active(party), rounds

    for round_number in range(1, round_limit + 1):
        order: list[tuple[int, int, Unit, str]] = []
        # Enemy wins an SPD tie: side_key 0 sorts before player side_key 1.
        order.extend((-unit.spec.speed, 1, unit, "party") for unit in party if unit.active)
        order.extend((-unit.spec.speed, 0, unit, "enemy") for unit in enemies if unit.active)
        order.sort(key=lambda row: (row[0], row[1], row[2].spec.name))

        for _, _, actor, side in order:
            if not actor.active:
                continue
            if actor.skip_actions:
                actor.skip_actions -= 1
                continue
            if side == "party":
                if not _active(enemies):
                    break
                if actor.healing_potions and actor.spec.lp - actor.lp >= 20:
                    actor.healing_potions -= 1
                    actor.lp = min(actor.spec.lp, actor.lp + 20)
                elif actor.spec.role == "healer":
                    _healer_action(actor, party, enemies, floor, rng)
                else:
                    _player_attack(actor, enemies, rng)
            else:
                if not _active(party):
                    break
                targets = _active(party)
                channel_turn = (
                    actor.spec.area_channelled
                    and round_number >= 2
                    and (round_number - 2) % actor.spec.area_every == 0
                )
                release_turn = (
                    actor.spec.area_channelled
                    and round_number >= 3
                    and (round_number - 3) % actor.spec.area_every == 0
                )
                unchannelled_area = (
                    actor.spec.area_every
                    and not actor.spec.area_channelled
                    and round_number % actor.spec.area_every == 0
                )
                if channel_turn:
                    # The standard action is spent chanting; no attack occurs.
                    pass
                elif release_turn or unchannelled_area:
                    # The previous round is the warning window. Prepared 8F
                    # multi-PC parties take the canonical full-cover counter;
                    # ordinary single-target magic is never halved.
                    for target in list(targets):
                        _attack_once(
                            actor,
                            target,
                            rng,
                            attack_kind=actor.spec.area_kind or actor.spec.attack_kind,
                            cover=prepared_meteor_cover,
                        )
                else:
                    for _ in range(actor.spec.multiattack):
                        if not _active(party):
                            break
                        _enemy_attack(actor, party, rng)
                counter_active = any(
                    unit.active and unit.spec.fire_light_counter for unit in party
                )
                if actor.active and actor.spec.regeneration and not counter_active:
                    actor.lp = min(actor.spec.lp, actor.lp + actor.spec.regeneration)
            ever_down = ever_down or any(unit.lp == 0 for unit in party)

        if not _active(party) or not _active(enemies):
            return finish(round_number)

    # A timeout is not silently called safe: it remains separate from an actual
    # death-return and is also included in the adverse wipe_or_timeout metric.
    return finish(round_limit + 1)


def probe_scenario(
    party_name: str,
    floor: int,
    encounter: str,
    trials: int,
    seed: int,
) -> dict[str, object]:
    party = party_blueprints(party_name, floor)
    enemies = enemy_blueprints(floor, encounter, len(party))
    rng = random.Random(f"M90:{seed}:{party_name}:{floor}:{encounter}")
    down_count = wipe_count = stalemate_count = round_total = 0
    for _ in range(trials):
        down, wipe, rounds = run_fight(party, enemies, floor, rng)
        down_count += down
        wipe_count += wipe
        stalemate_count += rounds > ROUND_LIMIT
        round_total += min(rounds, ROUND_LIMIT)

    target = {
        "standard": {"someone_lp0": [0.20, 0.30], "death_return": [0.05, 0.10]},
        "elite": {"someone_lp0": [0.35, 0.50], "death_return": [0.12, 0.20]},
        "boss": {"someone_lp0": [0.50, 0.70], "death_return": [0.20, 0.30]},
    }[encounter]
    threat_points = sum({"weak": 1, "standard": 2, "strong": 3}[spec.threat] for spec in enemies)
    threat_budget = None if encounter == "boss" else len(party) + (1 if encounter == "standard" else 2)
    return {
        "floor": floor,
        "encounter": encounter,
        "party_size": len(party),
        "party": party_name,
        "enemies": [spec.name for spec in enemies],
        "someone_lp0": round(down_count / trials, 4),
        "death_return": round(wipe_count / trials, 4),
        "stalemate": round(stalemate_count / trials, 4),
        "wipe_or_timeout": round((wipe_count + stalemate_count) / trials, 4),
        "mean_rounds": round(round_total / trials, 3),
        "round_limit": ROUND_LIMIT,
        "threat_points": threat_points,
        "threat_budget": threat_budget,
        "under_budget": threat_budget is not None and threat_points < threat_budget,
        "reference_target": target,
        "target_applies_only_if_prepared": party_name == "frontline_healer_attacker",
    }


def build_report(trials: int = TRIALS, seed: int = SEED) -> dict[str, object]:
    hit_table = []
    for delta in range(-13, 14):
        chance = opposed_probability(delta, 0)
        hit_table.append(
            {
                "attacker_minus_defender": delta,
                "fraction": f"{chance.numerator}/{chance.denominator}",
                "probability": round(float(chance), 6),
            }
        )

    scenario_plan = [
        (1, "standard"), (1, "boss"),
        (3, "standard"), (3, "boss"),
        (5, "standard"), (5, "elite"), (5, "boss"),
        (7, "standard"), (7, "elite"), (7, "boss"),
        (8, "elite"), (8, "boss"),
    ]
    scenarios = [
        probe_scenario(party, floor, encounter, trials, seed)
        for party in PARTY_NAMES
        for floor, encounter in scenario_plan
    ]
    return {
        "model": "M90 historical_reference_base45 sensitivity probe v2",
        "player_baseline": "historical_reference_base45",
        "new_base33_progression_validated": False,
        "scope": "historical player allocations against listed enemies; not certification of new Base33 deep floors",
        "recommended_initial_command": "combat_balance_probe.py --early-calibration --json --trials 5000 --seed 9042",
        "seed": seed,
        "trials_per_scenario": trials,
        "declared_player_assumptions": {
            "initial_base_tsp": 45,
            "base_lp": 20,
            "job_lp_bonus": {"frontline": 10, "middle": 5, "rear_or_production": 0},
            "lp_fruits_by_floor": {"1": 0, "3": 0, "5": 1, "7": 1, "8": 2},
            "base_tsp_growth_points_by_floor": {"1": 0, "3": 3, "5": 7, "7": 10, "8": 13},
            "equipment_points_by_floor": {"1": 2, "3": 4, "5": 6, "7": 8, "8": 10},
        },
        "rules_modeled": [
            "2d10 opposed hit; attacker wins ties",
            "physical and magic minimum-2 damage",
            "2d10 total 19+ doubles damage",
            "failed opposed attack by 1-2 deals exactly 2 graze damage",
            "representative basic warrior Strong Blow/Sweep twice and Grit once",
            "mage Magic Bolt power 3 / MP2 / INT7 gate and Focus twice; physical fallback",
            "hunter critical threshold 17 twice; priest has no implicit offensive spell",
            "basic first aid 1d6+2 twice, once per living target; heal never revives LP0",
            "penetration halves DEF",
            "fixed SPD initiative; enemy wins ties",
            "named 1/2/3-person compositions with explicit under-budget flags",
            "fire bonus by expedition party size",
            "historical pre-M102 Base LP + job LP + declared LP-fruit + fire LP formula; DEF-derived LP omitted in Base45 reference",
            "observed-healer focus without hidden-role knowledge",
            "finite-MP T1/T3 healing for the healer profile",
            "prepared 7F magic attacker; full cover only for telegraphed 8F Meteor",
            "Meteor spends one action channeling and observes its two-turn recast lock",
            "Elder Lich regeneration, suppressed by the prepared 8F fire/light counter",
            "Minotaur 30% hit-triggered stun and its LP30% rage",
        ],
        "omissions": [
            "most consumables/skills/statuses/binds, defend/evasion, physical resistance",
            "generic enemy spell MP costs/powers unless explicitly supplied by a scenario",
            "Elder Lich domination curse and other bespoke boss actions",
            "Meteor interruption, other scouting/puzzle counters, retreat, return crystal, and player tactics",
            "boss escorts/summons, drops, and between-encounter attrition",
        ],
        "warning": (
            "This is a deterministic regression/sanity probe, not statistical certification. "
            "Use relative changes and gross outliers only; target bands require full MUSE "
            "scenario tests with counters, skills, consumables, terrain, and retreat."
        ),
        "exact_opposed_hit_table": hit_table,
        "scenarios": scenarios,
    }


def _stat_lp_bonus(permanent_defense: int) -> int:
    """M102: only base DEF + permanent DEF growth, before gear/fire/temp."""
    return max(0, (permanent_defense - 3) // 2)


EARLY_BASE33 = {
    "warrior": (8, 7, 3, 5, 7, 3),
    "hunter": (7, 5, 3, 8, 7, 3),
    "mage": (3, 3, 10, 4, 10, 3),
    "priest": (4, 5, 10, 4, 3, 7),
}


def early_party_blueprints(size: int, base_floor: int = 3, geared: bool = True,
                           wound_potions: int = 0) -> list[Blueprint]:
    """Declared fresh-build examples, not default protagonist allocations.

    Base-5 sensitivity adds two to every value while retaining the same 15-point
    allocation. Gear is purchased, not starting loot. One optional wound potion
    belongs to the warrior and costs 50G, spending a standard action when used.
    """
    layouts = {1: ("warrior",), 2: ("warrior", "mage"), 3: ("warrior", "priest", "hunter")}
    fire, fire_lp = _fire_bonus(size)
    party = []
    for job in layouts[size]:
        s, d, intelligence, speed, technique, charisma = [n + base_floor - 3 for n in EARLY_BASE33[job]]
        assert s + d + intelligence + speed + technique + charisma == 6 * base_floor + 15
        stat_lp_bonus = _stat_lp_bonus(d) if base_floor == 3 else 0
        if geared:
            d += 2; speed += 1  # leather armor: DEF+2/SPD+1, 180G, weight3
            if job == "warrior":
                s += 3  # iron longsword: 120G, weight3
            elif job in {"mage", "priest"}:
                s += 1; intelligence += 1  # oak staff: 50G, weight2
            # shortbow: 250G, weight2; no invented STR bonus
        bonus_lp = 10 if job == "warrior" else 5 if job == "hunter" else 0
        party.append(Blueprint(job, 20 + bonus_lp + fire_lp + stat_lp_bonus,
                               s + fire, d + fire, intelligence + fire,
                               speed + fire, technique + fire,
                               role="healer" if job == "priest" else "frontline" if job == "warrior" else "attacker",
                               attack_kind="magic" if job == "mage" else "physical",
                               frontline=job == "warrior", initial_job=job,
                               magic_cost=2 if job == "mage" else 0,
                               magic_power=3 if job == "mage" else 0,
                               healing_potions=wound_potions if job == "warrior" else 0))
    return party


def measure_encounter(party: list[Blueprint], enemies: list[Blueprint], *, trials: int, seed: str,
                      floor: int = 1, round_limit: int = ROUND_LIMIT) -> dict[str, object]:
    rng = random.Random(seed)
    down_count = loss_count = draw_count = round_total = 0
    remaining_ratio = mp_spent = potions_spent = grit_used = 0.0
    wins = 0
    for _ in range(trials):
        telemetry: dict = {}
        down, loss, rounds = run_fight(party, enemies, floor, rng, round_limit, telemetry)
        down_count += down; loss_count += loss; draw_count += rounds > round_limit
        round_total += min(rounds, round_limit)
        mp_spent += telemetry["mp_spent"]; potions_spent += telemetry["potions_used"]; grit_used += telemetry["grit_used"]
        if not loss and rounds <= round_limit:
            wins += 1
            remaining_ratio += telemetry["remaining_lp"] / telemetry["starting_lp"]
    return {"trials": trials, "someone_lp0": round(down_count / trials, 4),
            "party_loss": round(loss_count / trials, 4), "unresolved": round(draw_count / trials, 4),
            "party_win": round((trials - loss_count - draw_count) / trials, 4),
            "mean_rounds": round(round_total / trials, 3), "round_limit": round_limit,
            "mean_winning_party_lp_remaining_ratio": round(remaining_ratio / wins, 4) if wins else None,
            "mean_mp_spent": round(mp_spent / trials, 3), "mean_wound_potions_used": round(potions_spent / trials, 3),
            "mean_warrior_grit_triggers": round(grit_used / trials, 3)}


def early_calibration_report(trials: int = TRIALS, seed: int = SEED) -> dict[str, object]:
    old_wolf = Blueprint("はぐれ狼・旧74LP", 74, 17, 7, 3, 12, 9, cunning=True)
    candidate_wolf = replace(BOSSES[1], name="はぐれ狼・採用64LP")
    rows = []
    for base_floor in (5, 3):
        for size in (1, 2, 3):
            for encounter in ("standard", "old_wolf", "candidate_wolf"):
                for potion in ((0, 1) if encounter == "candidate_wolf" else (0,)):
                    party = early_party_blueprints(size, base_floor, wound_potions=potion)
                    enemies = (list(STANDARD_COMPOSITIONS[1][size]) if encounter == "standard"
                               else [old_wolf if encounter == "old_wolf" else candidate_wolf])
                    key = f"early-v2:{seed}:{base_floor}:{size}:{encounter}:{potion}"
                    result = measure_encounter(party, enemies, trials=trials, seed=key)
                    result.update(base_floor=base_floor, base_total=base_floor * 6 + 15, m102_stat_lp=base_floor==3, party_size=size,
                                  encounter=encounter, warrior_wound_potions=potion,
                                  party=[spec.__dict__ for spec in party], enemies=[spec.__dict__ for spec in enemies])
                    rows.append(result)
    return {"model": "early-level canonical-skills sensitivity probe v3 M102", "seed": seed,
            "gear": {"warrior": "longsword120G+leather180G", "mage/priest": "oak_staff50G+leather180G",
                     "hunter": "shortbow250G+leather180G; arrows extra", "optional_warrior_potion": "50G / LP20 / one action"},
            "lp_rule": "M102 only for current Base33: +max(0,(permanentDEF-3)//2); Base45 rows preserve pre-M102 LP contract",
            "player_policy": ["start full LP/MP; focus lowest observed LP target", "use strongest expected damage among legal basic attack/Strong Blow/Sweep",
                              "mage uses Magic Bolt with finite MP then staff; Focus first two spells",
                              "priest heals a living wounded ally; first aid limited by uses/target; otherwise staff",
                              "hunter uses basic critical skill first two attacks; no unlearned spell",
                              "warrior potion spends one action after missing at least20LP"],
            "limitations": ["offline action policy sees exact stats to compare attacks; live play may not know them",
                            "no scouting/ambush, terrain, bat DEF debuff/poison, defensive tactics, retreats, boss escorts, or previous-fight attrition",
                            "priest Encourage and optional second starting spell, hunter Trip, other custom skills are not modeled",
                            "hunter ammo is not consumed; all standard targets assumed in legal range and two front targets adjacent for Sweep",
                            "Strong Blow adds3 after ordinary minimum2 then critical; Sweep subtracts2 with minimum2 retained",
                            "candidate_wolf identifies the adopted early wolf64LP; old_wolf is a historical sensitivity baseline",
                            "Novice enemy has explicit T1 Magic Bolt power3 MP2, at most4 casts, then physical attacks"],
            "scenarios": rows}


# New Base33 campaign sensitivity model. Kept separate from the historical and
# early-level paths so their declared policies remain reproducible.
@dataclass(frozen=True)
class CampaignProfile:
    spec: Blueprint
    base_total: int
    growth: int
    lp_fruits: int
    gear: str
    gear_positive_points: int
    gear_cost: int
    efficiency: int = 0
    catalyst_power: int = 0
    dragon_slayer: bool = False
    armor_break: bool = False
    spells: tuple[str, ...] = ()
    stat_lp_bonus: int = 0


def campaign_party(floor: int, size: int = 3, growth_mode: str = "modest",
                   prepared: bool = True, allocation: str = "starter_template") -> list[CampaignProfile]:
    """Examples of purchased/trained builds; never automatic level rewards.

    modest: +1/+2/+3/+4/+5 permanent stat points per actor at F2/4/6/8/9.
    These already require 3/6/9/12/15 shared stat-fruit awards for three actors.
    sparse: +0/+1/+1/+2/+2/+3 per actor; only warrior gets one LPfruit F6+.
    No new generated companion receives these points automatically.
    """
    growth = ({2: 1, 4: 2, 6: 3, 7: 4, 8: 4, 9: 5}[floor] if growth_mode == "modest"
              else {2:0,4:1,6:1,7:2,8:2,9:3}[floor] if growth_mode == "sparse" else 0)
    lp_fruits = 1 if floor >= 6 and growth_mode == "modest" else 0
    fire, fire_lp = _fire_bonus(size)
    jobs = {1: ("warrior",), 2: ("warrior", "mage"),
            3: ("warrior", "priest", "mage")}[size]
    rows = []
    for job in jobs:
        templates = ({**EARLY_BASE33, "warrior":(8,7,3,5,7,3), "mage":(3,3,10,4,10,3)}
                     if allocation=="accuracy_focused" else EARLY_BASE33)
        s, d, intelligence, speed, technique, _ = templates[job]
        if job == "warrior":
            technique += (growth + 1) // 2
            s += growth // 2
            permanent_defense = d
            if floor >= 4:
                s += 5; d += 4
                gear, points, price = "bastard350G+chain350G", 9, 700
                weight = 9
            else:
                s += 3; d += 2; speed += 1
                gear, points, price = "longsword120G+leather180G", 6, 300
                weight = 6
            role, front, job_lp = "frontline", True, 10
            spells, efficiency, power = (), 0, 0
        else:
            # A deliberately modest, non-perfect allocation: one TEC fruit at
            # F4, two from F7 onward, remaining fruit into INT.
            tec_growth = min(growth, 2 if floor >= 7 else 1 if floor >= 4 else 0)
            technique += tec_growth
            intelligence += growth - tec_growth
            permanent_defense = d
            efficiency = power = 0
            if floor == 9 and job == "mage" and prepared:
                intelligence += 8; d += 1
                gear, points, price, weight = "sage_orb4500G+adventurer50G", 9, 4550, 3
                power = 1
            elif floor >= 7:
                s += 2; intelligence += 5; d += 2; speed += 1
                gear, points, price, weight = "mithril_rod900G+leather180G", 10, 1080, 5
                efficiency = 1
            elif floor >= 4:
                s += 2; intelligence += 4; d += 2; speed += 1
                gear, points, price, weight = "ruby_rod350G+leather180G", 9, 530, 6
                power = 2  # fire spells only
            else:
                s += 1; intelligence += 1; d += 2; speed += 1
                gear, points, price, weight = "oak_staff50G+leather180G", 5, 230, 5
            role, front, job_lp = ("healer" if job == "priest" else "attacker"), False, 0
            spells = (("heal", "antidote", "great_heal") if job == "priest" and floor >= 6
                      else ("heal", "antidote") if job == "priest"
                      else ("bolt", "fireball", "thunder", "meteor") if floor == 9 and prepared
                      else ("bolt", "fireball", "thunder") if floor >= 7 and prepared
                      else ("bolt", "fireball") if floor >= 4 and prepared else ("bolt",))
        spell_gates={"bolt":7,"fireball":11,"thunder":19,"meteor":23,"heal":7,"antidote":7,"great_heal":15}
        spells=tuple(name for name in spells if intelligence+fire>=spell_gates[name])
        speed -= max(0, weight - (s + fire))
        personal_lp_fruits=lp_fruits if growth_mode!="sparse" else int(job=="warrior" and floor>=6)
        stat_lp_bonus = _stat_lp_bonus(permanent_defense)
        spec = Blueprint(f"{job}_{len(rows)+1}", 20 + job_lp + fire_lp + personal_lp_fruits * 3 + stat_lp_bonus,
                         s + fire, d + fire, intelligence + fire, speed + fire,
                         technique + fire, role=role, frontline=front, initial_job=job,
                         attack_kind="magic" if job == "mage" else "physical",
                         healing_potions=1 if prepared else 0)
        rows.append(CampaignProfile(spec, 33 + growth, growth, personal_lp_fruits, gear, points, price,
                                    efficiency, power, prepared and floor >= 7 and job == "warrior",
                                    prepared and floor >= 4 and job == "warrior", spells, stat_lp_bonus))
    return rows


CAMPAIGN_ENEMIES = {
    "toad": Blueprint("毒ガエル",32,9,7,5,6,5),
    "shaman": Blueprint("ゴブリンシャーマン",29,7,6,11,7,8),
    "snake": Blueprint("沼蛇の女王",74,19,6,7,11,11,cunning=True),
    "orc": Blueprint("オーク兵",65,15,11,5,6,7,rage_at=.5,rage_strength=3),
    "moth": Blueprint("毒蛾",29,7,5,9,10,8),
    "chief": Blueprint("オーク族長",119,21,13,6,7,9,penetration=True,cunning=True),
    "lamia": replace(LAMIA,name="ラミアダンサー"),
    "alraune": replace(ALRAUNE,name="アルラウネ",attack_kind="physical"),
    "arachne": Blueprint("アラクネ",115,22,15,17,11,16,cunning=True),
    "ogre": Blueprint("オーガ",192,31,15,4,9,11,penetration=True,rage_at=.5,rage_strength=10,threat="strong"),
    "minotaur": BOSSES[7],
    "wizard": Blueprint("ハイウィザード",72,9,9,30,13,19,cunning=True,frontline=False),
    "lich": BOSSES[8],
    "queen": Blueprint("サキュバスクイーン",164,24,17,39,18,18,cunning=True),
}


def campaign_enemies(floor: int, encounter: str, variant: str = "current") -> tuple[list[Blueprint], dict]:
    keys = {2:{"standard":("toad","shaman"),"boss":("snake",)},
            4:{"standard":("orc","moth"),"boss":("chief",)},
            6:{"standard":("lamia","alraune"),"boss":("arachne",)},
            7:{"standard":("ogre",),"boss":("minotaur",)},
            8:{"standard":("wizard",),"boss":("lich",)},
            9:{"boss":("queen",)}}[floor][encounter]
    enemies = [CAMPAIGN_ENEMIES[key] for key in keys]
    policy = {"keys":list(keys), "giant_windup":False, "queen_shared_cooldown":False,"queen_whip_windup":False,"cover_mode":"paid","no_fire":False,"finite_innate_mp":False,"permanent_regen_counter":False,"weak_shadow":False,"lich_bolt":False}
    if variant == "candidate":
        changes = {"queen":dict(lp=128,strength=20,defense=14,intelligence=26,speed=13,technique=14),
                   "lich":dict(lp=108,defense=14,intelligence=26,speed=12,technique=16),
                   "wizard":dict(intelligence=23,technique=16),
                   "ogre":dict(strength=29,rage_strength=6),"minotaur":dict(strength=31),
                   "lamia":dict(lp=70,speed=11,technique=12)}
        enemies = [replace(spec,**changes.get(key,{})) for key,spec in zip(keys,enemies)]
        policy.update(giant_windup=True,queen_shared_cooldown=True,queen_whip_windup=True,finite_innate_mp=True,permanent_regen_counter=True,weak_shadow=True,lich_bolt=True)
    return enemies, policy


def _record_campaign_fire_damage(result: dict, target_state: dict, permanent: bool) -> None:
    # Elemental damage stops regeneration even on a two-point graze. The
    # separate Fireball burn rider still requires a full hit.
    if result["damage"] > 0:
        target_state["fire_seen"] = True
        if permanent:
            target_state["regen_disabled"] = True
    if result["hit"]:
        target_state["burn"] = 3


def run_campaign_fight(profiles: list[CampaignProfile], enemy_specs: list[Blueprint],
                       policy: dict, floor: int, rng: random.Random, round_limit: int = 60, stocked: bool = False) -> dict:
    party = [Unit.from_blueprint(p.spec) for p in profiles]
    enemies = [Unit.from_blueprint(p) for p in enemy_specs]
    profile_map = {p.spec.name:p for p in profiles}
    # State is transient to this battle; no canonical save or generated fact.
    states = {}
    enemy_keys = {id(u):key for u,key in zip(enemies,policy["keys"])}
    def state(u):
        return states.setdefault(id(u),dict(poison=0,bleed=0,bound=False,bind_dot=0,
                    bind_source=None,bind_fail=0,controlled=False,channel=False,channel_lp=0,
                    meteor_cd=0,mental_cd=0,mental_last=None,mental_wait=set(),summoned=0,defending=False,covered=False,
                    ether=1 if stocked and u.spec.initial_job in {"mage","priest"} else 0,revived=False,
                    last_summon=-99,whip_pending=False,whip_cd=0,burn=0,fire_seen=False,regen_disabled=False,breaks=2,armor_broken=False,turns=0))
    ever_down=False; casts=controls=interrupts=0
    awakenings=1 if stocked else 0
    def status_roll(target, threshold):
        threshold += -2 if target.spec.speed >=20 else -1 if target.spec.speed>=15 else 1 if target.spec.speed<=5 else 0
        if target.spec.initial_job in {"warrior","priest"}: threshold-=1
        return rng.randint(1,10)<=max(1,min(9,threshold))
    def attack(actor,target,kind="physical",power=0,accuracy=0,damage=0,crit=19,pierce=False,cover=False):
        original_actor,original_target=actor.spec,target.spec
        actor.spec=replace(actor.spec,penetration=pierce,technique=actor.spec.technique+accuracy,
                           stun_chance=actor.spec.stun_chance if pierce else 0)
        target.spec=replace(target.spec,speed=target.spec.speed-(3 if state(target)["bound"] else 0)+(2 if state(target)["defending"] else 0),
                            defense=target.spec.defense+(2 if state(target)["defending"] else 0))
        result=_attack_once(actor,target,rng,attack_kind=kind,base_power=power,damage_modifier=damage,
                            critical_threshold=crit,cover=cover)
        actor.spec,target.spec=original_actor,original_target
        return result
    def choose_spell(actor,target):
        p=profile_map[actor.spec.name]
        choices=[]
        for name,gate,cost,power,critical in (("bolt",7,2,3,19),("fireball",11,4,5,19),("thunder",19,9,8,18)):
            if name=="fireball" and target.spec.regeneration and policy.get("no_fire"):continue
            if name in p.spells and actor.spec.intelligence>=gate and actor.mp>=max(1,cost-p.efficiency):
                c=max(1,cost-p.efficiency)
                bonus=p.catalyst_power if name=="fireball" or p.gear.startswith("sage") else 0
                # Expected damage per MP, with a modest urgency weight to avoid
                # wasting the entire fight on cheap minimum-damage bolts.
                raw=actor.spec.intelligence+power+bonus-target.spec.intelligence
                score=_expected_attack(actor.spec.technique-target.spec.speed,raw,0,critical,target.lp)/(c**.5)
                choices.append((score,name,c,power+bonus,critical))
        if target.spec.regeneration and not state(target)["fire_seen"] and not state(target)["regen_disabled"]:
            fire=[row for row in choices if row[1]=="fireball"]
            if fire:return fire[0]
        return max(choices) if choices else None
    for rnd in range(1,round_limit+1):
        order=sorted([(u.spec.speed,1,u,"party") for u in party if u.active]+
                     [(u.spec.speed,0,u,"enemy") for u in enemies if u.active],key=lambda r:(-r[0],r[1],r[2].spec.name))
        for _,_,actor,side in order:
            if not actor.active:continue
            a=state(actor);a["turns"]+=1
            a["defending"]=False
            if a["burn"]:_hurt(actor,a["burn"]);a["burn"]=0
            if not actor.active:continue
            if not _active(enemies) or not _active(party):break
            if actor.skip_actions:
                actor.skip_actions-=1
            elif a["controlled"]:
                allies=[u for u in party if u.active and u is not actor]
                if allies:attack(actor,min(allies,key=lambda u:u.lp))
                a["controlled"]=False
            elif side=="party":
                p=profile_map[actor.spec.name]
                # A caster may keep casting while bound. A bleeding bind is
                # escaped when its DOT makes remaining bound obviously costly.
                fallen=[u for u in party if not u.active and not state(u)["revived"]]
                incoming_whip=any(u.active and state(u)["whip_pending"] for u in enemies)
                incoming_meteor=any(u.active and state(u)["channel"] for u in enemies)
                returning_from_cover=a["covered"] and not incoming_meteor
                if returning_from_cover:a["covered"]=False
                if returning_from_cover and actor.spec.frontline and policy.get("cover_mode")=="paid":
                    pass # standard action returns the frontline to melee range
                elif incoming_meteor and policy.get("cover_mode")=="paid" and not a["bound"]:
                    a["covered"]=True # standard action to reach previously identified full cover
                elif stocked and awakenings and fallen:
                    victim=min(fallen,key=lambda u:0 if u.spec.role=="healer" else 1 if u.spec.frontline else 2)
                    victim.lp=1;state(victim)["revived"]=True;awakenings-=1
                elif a["bound"] and a["bind_dot"] and a["bind_source"] is not None:
                    source=a["bind_source"]
                    if actor.spec.strength+a["bind_fail"]+_roll_2d10(rng)>=source.spec.strength+_roll_2d10(rng):
                        a["bound"]=False;a["bind_dot"]=0;a["bind_fail"]=0
                    else:a["bind_fail"]+=3
                elif actor.healing_potions and actor.spec.lp-actor.lp>=min(20,actor.spec.lp*.4):
                    actor.healing_potions-=1;actor.lp=min(actor.spec.lp,actor.lp+20)
                elif stocked and a["ether"] and actor.mp<=max(1,p.efficiency):
                    a["ether"]-=1;actor.mp=min(actor.spec.intelligence,actor.mp+5)
                elif policy.get("guard_whip",False) and incoming_whip and not a["bound"] and actor.spec.role!="healer":
                    a["defending"]=True
                elif actor.spec.role=="healer":
                    poisoned=[u for u in _active(party) if state(u)["poison"]]
                    wounded=[u for u in _active(party) if u.lp<u.spec.lp]
                    emergency=any(u.lp<=max(8,u.spec.lp*.35) for u in wounded)
                    if poisoned and actor.mp>=max(1,1-p.efficiency) and not emergency:
                        actor.mp-=max(1,1-p.efficiency);state(poisoned[0])["poison"]=0
                    elif wounded:
                        target=min(wounded,key=lambda u:u.lp/u.spec.lp);missing=target.spec.lp-target.lp
                        heal_cost=max(1,2-p.efficiency)
                        if missing>=8 and actor.mp>=heal_cost and actor.spec.intelligence>=7:
                            actor.mp-=heal_cost;target.lp+=min(missing,actor.spec.intelligence+5+rng.randint(1,6));actor.observed_healer=True
                        elif missing>=4 and actor.first_aid_remaining and target.spec.name not in actor.first_aid_targets:
                            actor.first_aid_remaining-=1;actor.first_aid_targets.add(target.spec.name)
                            target.lp+=min(missing,rng.randint(1,6)+2);actor.observed_healer=True
                        else:attack(actor,_pick_player_target(actor,enemies))
                    else:attack(actor,_pick_player_target(actor,enemies))
                elif actor.spec.initial_job=="mage":
                    target=_pick_player_target(actor,enemies)
                    choice=choose_spell(actor,target)
                    if choice:
                        _,name,cost,power,critical=choice;actor.mp-=cost;casts+=1
                        accuracy=2 if actor.focus_remaining else 0
                        actor.focus_remaining=max(0,actor.focus_remaining-1)
                        result=attack(actor,target,"magic",power,accuracy,crit=critical)
                        if name=="fireball":
                            _record_campaign_fire_damage(result,state(target),bool(policy.get("permanent_regen_counter")))
                    else:attack(actor,target)
                else:
                    target=_pick_player_target(actor,enemies);buff=p.dragon_slayer and (target.spec.threat=="strong" or enemy_keys.get(id(target)) in {"minotaur","lich","queen"})
                    accuracy,damage=(2,5) if buff else (0,0)
                    if p.armor_break and a["breaks"] and not state(target)["armor_broken"]:
                        a["breaks"]-=1;result=attack(actor,target,accuracy=accuracy-2,damage=damage+2)
                        if result["hit"]:target.spec=replace(target.spec,defense=target.spec.defense-2);state(target)["armor_broken"]=True
                    else:
                        delta=actor.spec.technique+accuracy-target.spec.speed
                        raw=actor.spec.strength-target.spec.defense
                        strong=(actor.strong_remaining and _expected_attack(delta-2,raw,damage+3,19,target.lp)>_expected_attack(delta,raw,damage,19,target.lp))
                        if strong:actor.strong_remaining-=1
                        attack(actor,target,accuracy=accuracy-(2 if strong else 0),damage=damage+(3 if strong else 0))
                # A normal action resolves the anti-chain-control protection.
                for enemy in enemies:state(enemy)["mental_wait"].discard(id(actor))
            else:
                key=enemy_keys[id(actor)]
                target=_pick_enemy_target(actor,party)
                if a["channel"]:
                    if a["channel_lp"]-actor.lp>=actor.spec.lp*.25:
                        interrupts+=1;a["channel"]=False;a["meteor_cd"]=3
                    else:
                        for victim in list(_active(party)):attack(actor,victim,"magic",cover=(policy.get("cover_mode")=="free" or state(victim)["covered"]))
                        a["channel"]=False;a["meteor_cd"]=3
                elif key in {"wizard","wizard_summon","lich"} and a["meteor_cd"]==0 and a["turns"]%4==1 and actor.mp>=14:
                    actor.mp-=14
                    a["channel"]=True;a["channel_lp"]=actor.lp
                elif key=="queen" and a["whip_pending"]:
                    for victim in list(_active(party)):
                        result=attack(actor,victim)
                        if result["hit"] and status_roll(victim,3):state(victim)["bleed"]=2
                    a["whip_pending"]=False;a["whip_cd"]=3
                elif key=="queen" and policy.get("queen_whip_windup") and a["whip_cd"]==0 and a["turns"]>1:
                    a["whip_pending"]=True
                elif key in {"lich","queen"} and a["mental_cd"]==0 and (not policy.get("finite_innate_mp") or actor.mp>=4):
                    possible=[u for u in _active(party) if id(u)!=a["mental_last"] and id(u) not in a["mental_wait"]]
                    victim=min(possible,key=lambda u:u.spec.intelligence) if possible else None
                    if victim is not None:
                        if policy.get("finite_innate_mp"):actor.mp-=4
                        bonus=actor.spec.intelligence if key=="lich" else (24 if policy["queen_shared_cooldown"] else 41)
                        if bonus+_roll_2d10(rng)>=victim.spec.intelligence+_roll_2d10(rng):
                            controls+=1
                            if key=="queen" and a["turns"]%2:
                                _hurt(victim,15);victim.skip_actions=max(1,victim.skip_actions)
                            else:state(victim)["controlled"]=True
                        a["mental_last"]=id(victim);a["mental_wait"].add(id(victim))
                        a["mental_cd"]=3 if key=="lich" or policy["queen_shared_cooldown"] else 0
                    else:attack(actor,target)
                elif key=="queen" and a["summoned"]<2 and rnd-a["last_summon"]>=2 and (not policy.get("finite_innate_mp") or actor.mp>=6) and not any(u.active and u not in enemies[:len(enemy_specs)] for u in enemies):
                    summoned=CAMPAIGN_ENEMIES["wizard"]
                    if policy.get("finite_innate_mp"):actor.mp-=6
                    if policy.get("weak_shadow"):summoned=Blueprint("夢魔の影",24,12,5,8,10,9,threat="weak")
                    elif policy["queen_shared_cooldown"]:summoned=replace(summoned,intelligence=23,technique=16)
                    enemies.append(Unit.from_blueprint(replace(summoned,name=f"召喚ハイウィザード{a['summoned']+1}")))
                    enemy_keys[id(enemies[-1])]="shadow" if policy.get("weak_shadow") else "wizard_summon"
                    a["summoned"]+=1;a["last_summon"]=rnd
                elif key in {"alraune","arachne"} and a["turns"]%2==1:
                    for victim in _active(party):
                        if status_roll(victim,5):state(victim).update(bound=True,bind_dot=0,bind_source=actor)
                elif key=="moth":
                    for victim in _active(party):
                        if status_roll(victim,3):state(victim)["poison"]=3
                elif key in {"ogre","minotaur"} and policy["giant_windup"] and a["turns"]%4==1:
                    pass # one fully visible wind-up action
                else:
                    if key=="queen" and not policy.get("queen_whip_windup"):
                        for victim in list(_active(party)):
                            result=attack(actor,victim)
                            if result["hit"] and status_roll(victim,3):state(victim)["bleed"]=2
                    elif key=="lich" and policy.get("lich_bolt") and actor.mp>=2:
                        actor.mp-=2;attack(actor,target,"magic",power=3)
                    else:
                        pierce=actor.spec.penetration and (not policy["giant_windup"] or a["turns"]%4==2)
                        result=attack(actor,target,actor.spec.attack_kind,pierce=pierce)
                        if result["hit"]:
                            poison=3 if key=="toad" else 4 if key in {"snake","arachne"} else 0
                            if poison and status_roll(target,5 if key=="snake" else 3):state(target)["poison"]=poison
                            if key=="lamia" and a["turns"]%3==0 and status_roll(target,3):state(target).update(bound=True,bind_dot=5,bind_source=actor)
                if actor.spec.regeneration and not a["fire_seen"] and not a["regen_disabled"]:actor.lp=min(actor.spec.lp,actor.lp+actor.spec.regeneration)
                a["fire_seen"]=False;a["meteor_cd"]=max(0,a["meteor_cd"]-1);a["mental_cd"]=max(0,a["mental_cd"]-1);a["whip_cd"]=max(0,a["whip_cd"]-1)
            if actor.active:_hurt(actor,a["poison"]+a["bleed"]+(a["bind_dot"] if a["bound"] else 0))
            ever_down|=any(u.lp==0 for u in party)
        if not _active(party) or not _active(enemies):break
    else:rnd=round_limit+1
    assert all(u.mp>=0 for u in party+enemies)
    return dict(someone_lp0=ever_down,party_loss=not _active(party),unresolved=rnd>round_limit,
                rounds=min(rnd,round_limit),remaining_lp=sum(u.lp for u in party),
                mp_spent=sum(u.spec.intelligence-u.mp for u in party)+5*sum(1-state(u)["ether"] for u in party if stocked and u.spec.initial_job in {"mage","priest"}),
                ethers_used=sum(1-state(u)["ether"] for u in party if stocked and u.spec.initial_job in {"mage","priest"}),
                awakenings_used=(1-awakenings) if stocked else 0,casts=casts,controls=controls,interrupts=interrupts)


def campaign_calibration_report(trials: int=TRIALS, seed: int=SEED,
                                growth_mode: str="sparse", stocked: bool=False,
                                allocation: str="starter_template") -> dict:
    rows=[]
    for floor in (2,4,6,7,8,9):
        for encounter in (("standard","boss") if floor!=9 else ("boss",)):
            for variant in (("current","candidate") if floor>=7 or (floor==6 and encounter=="standard") else ("current",)):
                for counter in (("paid_cover_fire","no_cover_fire","paid_cover_no_fire")
                                if floor==8 and encounter=="boss" and variant=="candidate" else ("paid_cover_fire",)):
                    profiles=campaign_party(floor,growth_mode=growth_mode,allocation=allocation)
                    enemies,policy=campaign_enemies(floor,encounter,variant)
                    policy.update(cover_mode="none" if counter.startswith("no_cover") else "paid",
                                  no_fire=counter.endswith("no_fire"))
                    rng=random.Random(f"campaign33:{seed}:{floor}:{encounter}:{variant}:{growth_mode}:{stocked}:{allocation}:{counter}")
                    results=[run_campaign_fight(profiles,enemies,policy,floor,rng,stocked=stocked) for _ in range(trials)]
                    row=dict(floor=floor,encounter="elite" if floor==7 and encounter=="standard" else encounter,
                             variant="pre_audit_reference" if variant=="current" else "adopted_rework",
                             counter=counter,trials=trials,policy=policy,
                             party=[{**p.__dict__,"spec":p.spec.__dict__} for p in profiles],enemies=[e.__dict__ for e in enemies])
                    for key in ("someone_lp0","party_loss","unresolved","rounds","remaining_lp","mp_spent","casts","controls","interrupts","ethers_used","awakenings_used"):
                        row[key]=round(sum(r[key] for r in results)/trials,4)
                    row["party_win"]=round(1-row["party_loss"]-row["unresolved"],4);rows.append(row)
    stats=(3,5,7,9,11,13,16,19,21,23,25)
    checks=[{"effective_ability":stat,"success":{str(dc):sum(c for roll,c in enumerate(TWO_D10_COUNTS,2) if stat+roll>=dc)/100
              for dc in (16,19,22,25,28,31)}} for stat in stats]
    return dict(model="Base33 representative campaign sensitivity probe v3", seed=seed,
        trials_per_scenario=trials, growth_mode=growth_mode, allocation=allocation, stocked=stocked,
        initial_templates=EARLY_BASE33, lp_rule="M102 permanentDEF-derived LP; both enemy-reference and adopted rows use current Base33 actors", single_check_exact_table=checks,
        assumptions=[
            "Initial Base33. Sparse stat growth per actor F2/4/6/7/8/9=0/1/1/2/2/3; LPfruit only warrior F6+. F9 party shared total10 fruits including LPfruit, not 10each",
            "Modest stat growth1/2/3/4/4/5 and one LPfruit each F6+ is a separate optional wealth/grind sensitivity (18 shared fruit total at F9). None means zero fruit",
            "3 actors warrior/priest/mage use declared current33 templates; M102 LP adds max(0,(permanentDEF-3)//2) from base+growth before gear/fire/temp; gear positive point sum<=10 per actor and actual gear prices/weights included",
            "Each actor has one woundpotion50G, uses one action at missing min(20,40%maxLP). Stocked adds one ether100G to each caster and one shared awakening300G; one-action use, each target revival at mostonce",
            "Warrior learns armorbreak1000G F4+ and dragon-slayer2000G F7+; basic StrongBlow/Grit, no rankup, no free XP growth",
            "Mage buys fireball800G F4+, thunder3200G F7+ only when INT19 gate met, optional meteor6000G F9 only INT23+; named Meteor power6 is not selected by this single-target policy",
            "Ruby rod +2power fire only; mithril rod -1MP min1; sage orb +1power. Explicit spell INT gates, Focus twice and finite MP",
            "Priest knows Heal/Antidote, optionally knows GreatHeal2000G F6+; this economical policy uses T1Heal only, plus basic FirstAid, never heals LP0",
            "Enemy Meteor costs14MP, basepower0, charge1action/release1action, 25%maxLP cumulative interruption, two-ownturn recast lock; no unlisted single-target magic",
            "Paidcover consumes every actor action to reach available identified fullcover before Meteor; frontline spends another action to return to melee. No-cover comparison separate",
            "Adopted Queen STR20 DEF14 INT26 SPD13 TEC14 CHM24 LP128; sharedmentalMP4/CD2ownturns, no-repeat/no-chain, whip charge1/release1/CD2; weak shadow24LP costs6MP, max1active/2total",
            "Adopted Lich STR11 DEF14 INT26 SPD12 TEC16 LP108; first fire damage permanently disables regen5, curseMP4, explicit catalogue MagicBolt power3/MP2 on spare actions",
            "Adopted Lamia18/11/15/11/12/17/70; OgreSTR29 rage+6 and MinotaurSTR31 rage+10 with original LP/rage thresholds: windup1->pierce1->normal2; stun only Minotaur piercing thrust"
        ], limitations=[
            "Subset floors2/4/6/7/8/9, not all1-9F certification. F1 separately early-calibrated; F3/F5 physicalresistance/summons and other enemy rosters not covered here",
            "Fresh full LP/MP each fight; no three-encounter carry model, interlude recovery, drops, economy progression, or guarantee of natural fruit supply",
            "Prepared deep gear/spellbooks/skills are expensive, not automatic starting inventory. F9 SageOrb4500G is a declared wealth assumption; listed optional Meteor not needed by policy",
            "Terrain/position/ranges assumed legal and fullcover assumed available; paid movement cost included, but exact line-of-sight and terrain puzzles not simulated",
            "Lamia bind attempts everythird fullhit with default30% status roll; exact ability frequency not canonical. Alraune/Arachne alternate globalbind and basic attack, Moth globalpoison eachaction; schedules are offline policies",
            "Alraune confusion, snake constriction, chief roar, opening ambush, most custom/defensive/reaction skills, retreat and boss escorts omitted; chief result is a lower-bound no-escort fight",
            "Warrior Sweep omitted in campaign policy (still present in early model); priest Encourage omitted. Basic robust/status resistance and graze2 included",
            "Player target/damage selection uses exact stats offline; control chooses lowINT targets. Live actors must use observed knowledge. Named control ability costs/cooldowns tracked; not a complete AI model",
            "LP0 and party wipe are distinct; timeout is separate unresolved, never counted as win. Report rates compare assumptions, not promised live probabilities"
        ],scenarios=rows)


def self_test() -> dict[str, object]:
    assert sum(TWO_D10_COUNTS) == 100
    assert opposed_probability(0, 0) == Fraction(1067, 2000)
    chances = [opposed_probability(delta, 0) for delta in range(-18, 19)]
    assert all(left < right for left, right in zip(chances, chances[1:]))
    assert opposed_probability(100, 0) == 1
    assert opposed_probability(-100, 0) == 0
    assert set(BOSSES) == set(FLOORS)
    assert set(STANDARD_COMPOSITIONS) == {1, 3, 5, 7}
    assert set(ELITE_COMPOSITIONS) == {5, 7, 8}
    assert len(PARTY_NAMES) == 4
    warrior = Unit.from_blueprint(early_party_blueprints(1)[0])
    _hurt(warrior, warrior.lp + 10)
    assert warrior.lp == 1 and warrior.grit_remaining == 0
    _hurt(warrior, 1)
    assert warrior.lp == 0
    caster = Unit.from_blueprint(Blueprint("mage-probe", 20, 5, 5, 7, 5, 5,
                                         initial_job="mage", magic_cost=2, magic_power=3))
    target = Unit.from_blueprint(Blueprint("target", 10000, 5, 5, 5, 5, 5))
    for _ in range(4):
        _player_attack(caster, [target], random.Random(91 + _))
    assert caster.mp == 1 and caster.focus_remaining == 0
    class GrazeDice:
        def __init__(self): self.values = iter((5, 5, 5, 6))
        def randint(self, low, high): return next(self.values)
    actor = Unit.from_blueprint(Blueprint("attacker", 20, 5, 5, 5, 5, 5))
    defender = Unit.from_blueprint(Blueprint("defender", 20, 5, 5, 5, 5, 5))
    graze = _attack_once(actor, defender, GrazeDice())
    assert graze["graze"] and graze["damage"] == 2 and defender.lp == 18
    elemental_state={"burn":0,"fire_seen":False,"regen_disabled":False}
    _record_campaign_fire_damage(graze,elemental_state,True)
    assert elemental_state=={"burn":0,"fire_seen":True,"regen_disabled":True}
    miss_state={"burn":0,"fire_seen":False,"regen_disabled":False}
    _record_campaign_fire_damage({"hit":False,"damage":0},miss_state,True)
    assert miss_state=={"burn":0,"fire_seen":False,"regen_disabled":False}
    assert all(sum(row) == 33 and min(row) >= 3 for row in EARLY_BASE33.values())
    novice = Unit.from_blueprint(NOVICE)
    unhurt_target = Unit.from_blueprint(Blueprint("target", 10000, 5, 5, 5, 5, 5))
    for i in range(5):
        _enemy_attack(novice, [unhurt_target], random.Random(120 + i))
    assert novice.mp == 0  # Four MP2 bolts, then a physical attack.
    priest = Unit.from_blueprint(Blueprint("priest", 25, 6, 8, 12, 6, 4,
                                         initial_job="priest", role="healer"))
    priest.mp = 0
    ally = Unit.from_blueprint(Blueprint("ally", 30, 5, 5, 5, 5, 5)); ally.lp = 1
    _healer_action(priest, [priest, ally], [unhurt_target], 1, random.Random(1))
    healed = ally.lp
    _healer_action(priest, [priest, ally], [unhurt_target], 1, random.Random(2))
    assert ally.lp == healed and priest.first_aid_remaining == 1
    ally.lp = 0; priest.mp = 12
    _healer_action(priest, [priest, ally], [unhurt_target], 1, random.Random(3))
    assert ally.lp == 0 and priest.mp == 12

    assert early_party_blueprints(1)[0].lp==44
    assert early_party_blueprints(1,geared=False)[0].lp==44
    assert early_party_blueprints(1,base_floor=5)[0].lp==42  # pre-M102 history
    assert early_party_blueprints(3)[1].lp==26  # priest permanentDEF5 -> +1
    assert _stat_lp_bonus(3)==0 and _stat_lp_bonus(5)==1 and _stat_lp_bonus(7)==2
    assert _stat_lp_bonus(9)==3  # permanent DEF growth also contributes
    sparse_party=campaign_party(9,growth_mode="sparse")
    assert [p.stat_lp_bonus for p in sparse_party]==[2,1,0]
    assert [p.spec.lp for p in sparse_party]==[40,26,25]
    assert sum(p.growth+p.lp_fruits for p in sparse_party)==10
    assert all(p.gear_positive_points<=10 for p in sparse_party)
    assert EARLY_BASE33["warrior"]==(8,7,3,5,7,3)
    assert EARLY_BASE33["mage"]==(3,3,10,4,10,3)
    assert all("meteor" not in p.spells for p in sparse_party)
    sample_enemies,sample_policy=campaign_enemies(9,"boss","candidate")
    first_campaign=run_campaign_fight(sparse_party,sample_enemies,sample_policy,9,random.Random(4401),stocked=True)
    assert first_campaign==run_campaign_fight(sparse_party,sample_enemies,sample_policy,9,random.Random(4401),stocked=True)
    assert not(first_campaign["party_loss"] and first_campaign["unresolved"])
    assert first_campaign["ethers_used"]<=2 and first_campaign["awakenings_used"]<=1

    # The seeded Monte Carlo path must be byte-for-byte repeatable.
    first = probe_scenario("solo_fighter", 3, "standard", 64, 123)
    second = probe_scenario("solo_fighter", 3, "standard", 64, 123)
    assert first == second
    for key in ("someone_lp0", "death_return", "stalemate", "wipe_or_timeout"):
        assert 0.0 <= float(first[key]) <= 1.0
    assert float(first["death_return"]) <= float(first["someone_lp0"])
    return {
        "self_test": "ok",
        "equal_bonus_exact": "1067/2000",
        "equal_bonus_probability": 0.5335,
        "deterministic_sample": first,
        "early_skill_checks": ["Grit once", "Magic Bolt finite MP", "Focus twice", "graze2", "33-point budgets",
                               "Novice at most4 bolts", "first aid once per living target", "no implicit priest resurrection",
                               "M102 permanentDEF-derived LP; gear/fire excluded; Base45 history unchanged"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    parser.add_argument("--self-test", action="store_true", help="run invariant checks")
    parser.add_argument("--trials", type=int, default=TRIALS, help="trials per scenario")
    parser.add_argument("--seed", type=int, default=SEED, help="deterministic master seed")
    parser.add_argument("--early-calibration", action="store_true",
                        help="compare purchased initial gear/basic skills, Base45/Base33, and explicit 1F candidates")
    parser.add_argument("--campaign-calibration", action="store_true", help="new Base33 low-growth representative prepared-party audit; explicit omissions")
    parser.add_argument("--campaign-growth", choices=("none","sparse","modest"), default="sparse")
    parser.add_argument("--campaign-stocked", action="store_true", help="add paid caster ethers and shared awakening medicine")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.trials < 1:
        raise SystemExit("--trials must be at least 1")
    test_result: dict[str, object] | None = None
    if args.self_test:
        test_result = self_test()
        if not args.json:
            print(json.dumps(test_result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    report = (campaign_calibration_report(args.trials, args.seed, args.campaign_growth, args.campaign_stocked) if args.campaign_calibration
              else early_calibration_report(args.trials, args.seed) if args.early_calibration
              else build_report(args.trials, args.seed))
    if test_result is not None:
        report["self_test"] = test_result
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{report['model']} (seed={args.seed}, trials={args.trials})")
        if not args.early_calibration and not args.campaign_calibration:
            print("旧45点配分の参照試算です。新33点の序盤比較は --early-calibration を使います。深層の新33点適正を検証した結果ではありません。")
        print("Use --json for the exact hit table and all scenario results.")
        if args.campaign_calibration:
            for row in report["scenarios"]:
                print(f"F{row['floor']} {row['encounter']:9s} {row['variant']:9s} down={row['someone_lp0']:.1%} loss={row['party_loss']:.1%} unresolved={row['unresolved']:.1%}")
            return 0
        if args.early_calibration:
            for row in report["scenarios"]:
                print(f"Base{row['base_total']} {row['party_size']}PC {row['encounter']:14s} "
                      f"potion{row['warrior_wound_potions']} down={row['someone_lp0']:.1%} "
                      f"loss={row['party_loss']:.1%} unresolved={row['unresolved']:.1%}")
            return 0
        for row in report["scenarios"]:
            budget_note = " under-budget" if row["under_budget"] else ""
            print(
                f"{row['party']:28s} F{row['floor']} {row['encounter']:8s} "
                f"down={row['someone_lp0']:.1%} return={row['death_return']:.1%} "
                f"timeout={row['stalemate']:.1%}{budget_note}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
