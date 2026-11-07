"""Small M51 movement policy; no generation, save writes or extra model calls."""
from __future__ import annotations
import re

STYLES = {"normal", "direct", "stroll", "wander", "idle"}
URGENCIES = {"none", "player_rush", "quest_time_pressure", "medical_emergency"}


def plan(style, area="town", urgency="none"):
    if style not in STYLES or area not in {"town", "road", "dungeon"} or urgency not in URGENCIES:
        raise ValueError("invalid movement style/location kind/urgency")
    threshold = 0
    if area != "dungeon" and urgency == "none" and style != "direct":
        threshold = 2 if style == "normal" else 8 if style == "wander" and area == "town" else 4
    return {"style": style, "location_kind": area, "urgency": urgency,
            "threshold": threshold, "percent": threshold * 10, "roll_required": threshold > 0,
            "inventory_events_allowed": style == "idle" or area == "dungeon"}


def from_args(args, world, scenes, area_hint=None):
    style = getattr(args, "movement_style", None)
    if style is None:
        if getattr(args, "movement_urgency", "none") != "none":
            raise ValueError("movement urgency requires --movement-style")
        return None
    area = getattr(args, "location_kind", None) or area_hint or ("road" if "travel" in scenes else "town")
    if world.get("depth") is not None or "dungeon" in scenes:
        area = "dungeon"
    return plan(style, area, getattr(args, "movement_urgency", "none"))


def validate(api, draft, save, before=None):
    movement = draft.get("movement")
    if movement is None:
        return None
    if not isinstance(movement, dict):
        raise api.RuntimeProblem("response.movement must be a mapping")
    area = movement.get("location_kind", "town")
    source = before or save
    if source.get("world_state", {}).get("depth") is not None or source.get("runtime_state", {}).get("scene_id") == "dungeon":
        area = "dungeon"
    try:
        selected = plan(movement.get("style"), area, movement.get("urgency", "none"))
    except (ValueError, TypeError) as exc:
        raise api.RuntimeProblem(str(exc)) from exc
    occurrence, kind = draft.get("random_event_roll"), draft.get("random_event_type_roll")
    if not selected["roll_required"]:
        if occurrence is not None or kind is not None:
            raise api.RuntimeProblem("急ぎ・直行・ダンジョンではM51を振りません")
        return {**selected, "occurred": False, "rolls_checked": 0}
    if before is None:
        raise api.RuntimeProblem("movement roll validation requires the prepared/before save")
    start = before.get("dice_state", {}).get("dice_cursor_d10")
    end = save.get("dice_state", {}).get("dice_cursor_d10")

    def verify(roll):
        if not isinstance(roll, dict) or roll.get("die") != "d10":
            raise api.RuntimeProblem("random_event_roll requires die=d10, result and cursor")
        cursor, result = roll.get("cursor"), roll.get("result")
        if (type(cursor) is not int or type(result) is not int or not 1 <= result <= 10
                or type(start) is not int or type(end) is not int or not start <= cursor < end
                or api._fixed_tape_value("d10", cursor) != result):
            raise api.RuntimeProblem("movement roll must match the fixed tape and committed cursor range")
        return cursor, result

    cursor, result = verify(occurrence)
    occurred = result <= selected["threshold"]
    rolls = [result]
    if occurred:
        type_cursor, type_result = verify(kind)
        if type_cursor != cursor + 1:
            raise api.RuntimeProblem("movement type roll must immediately follow its occurrence roll")
        rolls.append(type_result)
        if draft.get("c7_roll") is not None:
            raise api.RuntimeProblem("M51が出た場面へC-7を重ねません")
    elif kind is not None:
        raise api.RuntimeProblem("M51が外れた時は種別を振りません")
    system = "\n".join(draft.get("system_blocks", []))
    shown = [int(value) for value in re.findall(r"\bd10 = (10|[1-9])(?!\d)", system)]
    for value in set(rolls):
        if shown.count(value) < rolls.count(value):
            raise api.RuntimeProblem("movement dice must be shown as d10 = <result> in system_blocks")
    return {**selected, "occurred": occurred, "rolls_checked": len(rolls)}
