"""Read-only eligibility for canonical event stock; no rolls or save writes."""
from __future__ import annotations

import re


# These are encounter locations, not additional occurrence probabilities.
LOCATIONS = {
    "EV-S18": ("酒場", "ぬれねずみ亭", "蜜の味"),
    "EV-S19": ("銭湯", "共同浴場"),
    "EV-S20": ("鉄の咆哮", "鍛冶屋", "テトラ"),
    "EV-S21": ("衛兵詰め所", "詰め所", "牢獄", "シルヴィア"),
}


def companion_ids(save):
    world = save.get("world_state") or {}
    expedition = world.get("expedition_state") or {}
    separated = set(expedition.get("separated_fire_holders") or [])
    result = []
    for member in save.get("party") or []:
        if not isinstance(member, dict):
            continue
        identity = member.get("id") or member.get("character_id") or member.get("name")
        if (identity and identity not in separated and member.get("name") not in separated
                and (member.get("lp") or {}).get("cur", 0) > 0):
            result.append(identity)
    return result


def seed_id(entry):
    explicit = entry.get("canonical_seed_id")
    if explicit:
        return str(explicit)
    match = re.search(r"(?:^|-)(EV-(?:DE|[SRD])\d+)$", str(entry.get("id") or ""))
    return match.group(1) if match else None


def requirements(entry):
    fields = entry.get("fields") or {}
    floors = str(fields.get("適合階層") or "")
    numbers = [int(n) for n in re.findall(r"([1-9])F", floors)]
    identity = seed_id(entry)
    kind = re.search(r"種別\s*(\d+)", str(entry.get("type") or ""))
    return {"type": int(kind.group(1)) if kind else None,
            "floor_min": min(numbers) if numbers else None,
            "floor_max": max(numbers) if numbers else None,
            "requires_companion": "要同行者" in floors or identity in {"EV-D12", "EV-R02", "EV-R08", "EV-R09"},
            "location_aliases": list(LOCATIONS.get(identity, ())) }


def unmet(entry, world_context, *, check_location=True):
    rule = requirements(entry)
    missing = []
    floor = world_context.get("current_floor")
    if entry.get("category") == "dungeon" and rule["floor_min"] is not None:
        if (not isinstance(floor, int) or isinstance(floor, bool)
                or not rule["floor_min"] <= floor <= rule["floor_max"]):
            missing.append("current_floor")
    if rule["requires_companion"] and not world_context.get("companion_ids"):
        missing.append("companion")
    if check_location and rule["location_aliases"]:
        place = str(world_context.get("location") or "")
        if not any(alias in place for alias in rule["location_aliases"]):
            missing.append("location")
    return missing


def canonical_events(api):
    _, _, resources = api.load_control()
    resource = resources["EVENT_INVENTORY_STATE"]["initialize_from"]
    source = api.ROOT / resources[resource]["path"]
    return api.inventory_from_markdown(source, "events", resource)["entries"]


def catalog(api, profile, categories):
    context = profile.get("world_context") or {}
    return [{"seed_id": entry["id"], "category": entry["category"],
             "source": "運用/イベントデッキ.md", **requirements(entry),
             "unmet_conditions": unmet(entry, context)}
            for entry in canonical_events(api) if entry.get("category") in categories]
