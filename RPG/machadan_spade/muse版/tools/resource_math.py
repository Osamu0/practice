"""Derived LP/MP capacities; permanent DEF and LP-fruit growth stay separate.

Existing actors without the optional stat_lp_bonus record retain their old
capacity contract. New allocation and newly created actors opt into M102.
Capacity changes never recover spent resources unless creation requests refill.
"""
from __future__ import annotations


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def stat_lp_bonus(actor):
    base_map, growth_map = actor.get("base_stats"), actor.get("growth_bonus")
    if not isinstance(base_map, dict) or not isinstance(growth_map, dict):
        raise ValueError("permanent DEF requires base/growth mappings")
    base, growth = base_map.get("def"), growth_map.get("def")
    if not _integer(base) or not _integer(growth) or base < 0 or growth < 0:
        raise ValueError("permanent DEF requires nonnegative integer base and growth")
    return max(0, (base + growth - 3) // 2)


def validate_stat_lp(actor, label, errors):
    if "stat_lp_bonus" not in actor:
        return
    value = actor["stat_lp_bonus"]
    if not _integer(value) or value < 0:
        errors.append(label + ".stat_lp_bonus must be a nonnegative integer")
        return
    try:
        if value != stat_lp_bonus(actor):
            errors.append(label + ".stat_lp_bonus must equal floor((permanent DEF-3)/2), minimum0")
    except (ValueError, TypeError, AttributeError) as exc:
        errors.append(label + ".stat_lp_bonus: " + str(exc))


def recalculate(actor, *, track=False, refill=False):
    if track or "stat_lp_bonus" in actor:
        actor["stat_lp_bonus"] = stat_lp_bonus(actor)
    parts = [actor.get(key, 0) for key in
             ("base_lp", "job_lp_bonus", "fire_lp_bonus", "temporary_lp_bonus", "stat_lp_bonus")]
    if not all(_integer(value) for value in parts):
        raise ValueError("LP capacity components must be integers")
    lp_max = sum(parts)
    effective = actor.get("effective_stats")
    mp_max = effective.get("int") if isinstance(effective, dict) else None
    if lp_max < 0 or not _integer(mp_max) or mp_max < 0:
        raise ValueError("LP/MP capacities must be nonnegative integers")
    for key, maximum in (("lp", lp_max), ("mp", mp_max)):
        meter = actor.get(key)
        current = meter.get("cur") if isinstance(meter, dict) else None
        if not _integer(current) or current < 0:
            raise ValueError(key + " current value must be a nonnegative integer")
        actor[key] = {"cur": maximum if refill else min(current, maximum), "max": maximum}
    return actor
