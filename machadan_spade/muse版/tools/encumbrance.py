"""Typed M30 equipped-weight calculation for explicitly tracked actors.

Legacy saves without ``actor.encumbrance`` remain valid.  Callers editing
STR/SPD or equipment request typed weights; unrelated old scenes need not
invent a weight from an item's prose description.
"""
from __future__ import annotations


GROUPS = ("base_stats", "growth_bonus", "equipment_bonus", "fire_bonus", "temporary_modifiers")
STATS = ("str", "def", "int", "spd", "tec", "chm")
SLOTS = ("weapon_instance_id", "armor_instance_id", "offhand_instance_id")
RECORD_KEYS = {"version", "total_weight", "raw_penalty", "applied_penalty"}


class EncumbranceError(ValueError):
    pass


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _actors(data):
    result = [data.get("player")]
    for key in ("party", "inn_reserve"):
        if isinstance(data.get(key), list):
            result.extend(data[key])
    return [actor for actor in result if isinstance(actor, dict)]


def _actor(data, actor_id):
    actors = [actor for actor in _actors(data) if actor.get("character_id") == actor_id]
    if not isinstance(actor_id, str) or not actor_id or len(actors) != 1:
        raise EncumbranceError("weight calculation requires one unambiguous character_id")
    return actors[0]


def _record(actor):
    if "encumbrance" not in actor:
        return None
    value = actor["encumbrance"]
    if (not isinstance(value, dict) or set(value) != RECORD_KEYS or value.get("version") != 1
            or isinstance(value.get("version"), bool)
            or any(not _integer(value.get(key)) or value[key] < 0 for key in RECORD_KEYS - {"version"})
            or value["applied_penalty"] > value["raw_penalty"]):
        raise EncumbranceError("encumbrance must contain version=1 and nonnegative integer weight/penalties")
    return value


def _stat(actor, key):
    values = [actor.get(group, {}).get(key) if isinstance(actor.get(group), dict) else None for group in GROUPS]
    if not all(_integer(value) for value in values):
        raise EncumbranceError("weight calculation requires integer stat components: " + key)
    return sum(values)


def _equipped_weight(data, actor):
    equipment = actor.get("equipment")
    if not isinstance(equipment, dict):
        raise EncumbranceError("weight calculation requires typed equipment slots")
    references = [equipment.get(slot) for slot in SLOTS if equipment.get(slot) is not None]
    if any(not isinstance(value, str) or not value for value in references) or len(references) != len(set(references)):
        raise EncumbranceError("equipped instance references must be nonempty and unique")
    # Only the at-most-three referenced instances and their definitions matter.
    # Fixed descriptive markers (e.g. the return bracelet), carried stacks and
    # warehouse contents are not inferred to be equipped weighted instances.
    wanted = set(references)
    instances = {}
    raw_instances = data.get("item_instances", [])
    raw_definitions = data.get("item_definitions", [])
    if not isinstance(raw_instances, list) or not isinstance(raw_definitions, list):
        raise EncumbranceError("item instances and definitions must be lists")
    for instance in raw_instances:
        if isinstance(instance, dict) and instance.get("instance_id") in wanted:
            key = instance["instance_id"]
            if key in instances:
                raise EncumbranceError("duplicate equipped instance_id: " + key)
            instances[key] = instance
    definition_ids = {instance.get("item_def_id") for instance in instances.values()
                      if isinstance(instance.get("item_def_id"), str)}
    definitions = {}
    for definition in raw_definitions:
        if isinstance(definition, dict) and definition.get("item_def_id") in definition_ids:
            key = definition["item_def_id"]
            if key in definitions:
                raise EncumbranceError("ambiguous equipped item definition: " + key)
            definitions[key] = definition
    total, missing = 0, []
    for reference in references:
        instance = instances.get(reference)
        if instance is None:
            raise EncumbranceError("equipped instance is missing: " + reference)
        if (instance.get("location") != "equipped"
                or instance.get("owner_character_id") != actor.get("character_id")):
            raise EncumbranceError("equipped instance ownership/location differs: " + reference)
        snapshot = instance.get("specification_snapshot")
        if not isinstance(snapshot, dict):
            raise EncumbranceError("equipped instance needs a specification_snapshot: " + reference)
        definition = definitions.get(instance.get("item_def_id"), {})
        specification = definition.get("specification", {})
        if not isinstance(specification, dict):
            raise EncumbranceError("equipped definition specification must be a mapping: " + reference)
        weights = []
        for source in (snapshot, specification):
            if "weight" in source:
                value = source["weight"]
                if not _integer(value) or value < 0:
                    raise EncumbranceError("equipped weight must be a nonnegative integer: " + reference)
                weights.append(value)
        if len(set(weights)) > 1:
            raise EncumbranceError("equipped snapshot and definition weights differ: " + reference)
        if weights:
            total += weights[0]
        else:
            missing.append(reference)
    return total, missing


def preview(data, actor_id, *, require_weights=True):
    """Return a read-only profile; no save, definition or actor is changed.

    ``raw_spd_bonus`` excludes the old weight penalty, making it suitable for
    frontend allocation previews.  ``str_bonus`` excludes base+growth STR.
    A non-STR/SPD legacy operation can request unknown-weight reporting rather
    than blocking; already tracked actors always require known typed weights.
    """
    actor = _actor(data, actor_id)
    previous = _record(actor)
    old_applied = previous["applied_penalty"] if previous else 0
    strength = _stat(actor, "str")
    spd_without = _stat(actor, "spd") + old_applied
    if strength < 0 or spd_without < 0:
        raise EncumbranceError("STR and SPD before weight penalty must be nonnegative")
    total, missing = _equipped_weight(data, actor)
    if missing and (require_weights or previous is not None):
        raise EncumbranceError("materialise canonical typed equipment weights before editing STR/SPD: " + ", ".join(missing))
    raw_spd_bonus = sum(actor[group]["spd"] for group in GROUPS[2:]) + old_applied
    str_bonus = sum(actor[group]["str"] for group in GROUPS[2:])
    result = {"version": 1, "weights_known": not missing,
              "total_weight": None if missing else total,
              "missing_instance_ids": missing, "str_total": strength,
              "spd_without_penalty": spd_without, "raw_spd_bonus": raw_spd_bonus,
              "str_bonus": str_bonus}
    if missing:
        result.update(raw_penalty=None, applied_penalty=old_applied,
                      effective_spd=_stat(actor, "spd"))
    else:
        raw = max(0, total - strength)
        applied = min(raw, spd_without)
        result.update(raw_penalty=raw, applied_penalty=applied,
                      effective_spd=spd_without - applied)
    return result


def recalculate(data, actor_id, *, require_weights=True):
    """Apply one M30 adjustment to a candidate; repeated calls are stable.

    Only the selected actor's SPD modifier, effective/stat mirrors and weight
    record change. LP/MP and all unrelated components remain caller-owned.
    """
    calculated = preview(data, actor_id, require_weights=require_weights)
    if not calculated["weights_known"]:
        return calculated
    actor = _actor(data, actor_id)
    previous = _record(actor)
    old_applied = previous["applied_penalty"] if previous else 0
    effective = {key: _stat(actor, key) for key in STATS}
    effective["spd"] += old_applied - calculated["applied_penalty"]
    if any(value < 0 for value in effective.values()):
        raise EncumbranceError("weight adjustment cannot leave negative effective stats")
    actor["temporary_modifiers"]["spd"] += old_applied - calculated["applied_penalty"]
    actor["encumbrance"] = {key: calculated[key] for key in ("version", "total_weight", "raw_penalty", "applied_penalty")}
    actor["effective_stats"] = effective
    actor["stats"] = dict(actor["effective_stats"])
    return calculated


def validate_state(data, errors):
    """Validate optional records only; unknown-weight legacy actors stay valid."""
    for actor in _actors(data):
        if "encumbrance" not in actor:
            continue
        label = str(actor.get("character_id") or "unknown actor")
        try:
            calculated = preview(data, actor.get("character_id"), require_weights=True)
            expected = {key: calculated[key] for key in ("version", "total_weight", "raw_penalty", "applied_penalty")}
            if actor["encumbrance"] != expected:
                errors.append(label + ".encumbrance does not match equipped weights and STR/SPD")
            if any(not isinstance(actor.get(key), dict) or actor[key].get("spd") != calculated["effective_spd"]
                   for key in ("effective_stats", "stats")):
                errors.append(label + ".encumbrance SPD does not match the effective-stat mirrors")
        except (EncumbranceError, TypeError) as exc:
            errors.append(label + ".encumbrance: " + str(exc))
