#!/usr/bin/env python3
"""Private GM bookkeeping for exploration; never render this output as story prose."""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

SITES = ("chest-1", "chest-2", "harvest-1", "harvest-2", "boss-loot")
KINDS = {"exploration", "event", "trash", "boss", "rest", "avoid", "passage"}
PHASES = {"signs", "engaged", "escaped", "defeated", "withdrawn"}
TIME_BANDS = ("朝", "昼", "夕", "夜")


def passage_time(data):
    """One passed floor costs 1/6 half-day. Three ticks advance one band."""
    world, run = data["world_state"], data["world_state"]["dungeon_run"]
    if data.get("debt_state", {}).get("collection_pending"):
        raise ValueError("resolve the pending collection before another passage")
    band = world.get("time_of_day")
    if band not in TIME_BANDS:
        raise ValueError("passage requires a known time_of_day")
    ticks = run.get("passage_ticks", 0)
    if not integer(ticks) or ticks < 0:
        raise ValueError("invalid passage_ticks")
    run["passage_ticks"] = ticks + 1
    if (ticks + 1) % 3 == 0:
        index = TIME_BANDS.index(band)
        world["time_of_day"] = TIME_BANDS[(index + 1) % 4]
        if index == 3:
            world["day"] += 1
            debt = data.get("debt_state", {})
            due = debt.get("next_collection_day")
            if integer(due) and world["day"] >= due:
                if world["day"] > due:
                    raise ValueError("passage may not skip a collection day")
                debt["collection_pending"] = True


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def empty_memory():
    return {"version": 1, "records": {}}


def migrate(data, changes):
    world = data.get("world_state", {})
    legacy_sources = world.get("growth_state", {}).setdefault("boss_fruit_legacy_sources", [])
    for boss in world.get("boss_records", []):
        if any(row.get("source_type") == "boss" and row.get("outcome") == "awarded" and
               row.get("source_id") == boss.get("last_defeat_id") and not row.get("rule_version")
               for row in world.get("growth_state", {}).get("resolutions", [])):
            source = f"boss-f{boss['floor']}"
            if source not in legacy_sources:
                legacy_sources.append(source)
                changes.append("legacy boss fruit acquisition projected from an explicit defeat receipt")
    if "dungeon_memory" not in world:
        world["dungeon_memory"] = empty_memory()
        # Existing boss receipts are evidence that today's loot was resolved.
        for boss in world.get("boss_records", []):
            key = f"d{boss['last_defeated_day']}-f{boss['floor']}"
            rec = new_record(boss["last_defeated_day"], boss["floor"], "legacy")
            rec["claims"] = ["boss-loot"]
            world["dungeon_memory"]["records"][key] = rec
        changes.append("M108 dungeon daily resource and pursuit memory initialized; old receipts retained")
    run = world.get("dungeon_run", {})
    run.setdefault("resource_days_by_floor", {})
    # An in-progress old visit must not acquire a fresh set of resources.
    if run.get("active") and not run["resource_days_by_floor"]:
        floor, day = run.get("current_floor"), world.get("day")
        if integer(floor) and integer(day):
            searches = run.get("reward_searches_by_floor", {})
            visited = {floor} | {int(f) for f in searches if str(f).isdigit() and 1 <= int(f) <= 9}
            for visited_floor in visited:
                key = f"d{day}-f{visited_floor}"
                rec = world["dungeon_memory"]["records"].setdefault(key, new_record(day, visited_floor, run["run_id"]))
                old_count = searches.get(visited_floor, searches.get(str(visited_floor), 0))
                if integer(old_count) and old_count:
                    rec["claims"] = list(dict.fromkeys(rec["claims"] + list(SITES[:min(old_count, 4)])))
                if visited_floor == floor:
                    rec["pressure"] = min(6, max(0, run.get("current_floor_scenes", 0)))
                run["resource_days_by_floor"][str(visited_floor)] = day


def new_record(day, floor, run_id):
    return {"day": day, "floor": floor, "created_run_id": run_id,
            "pressure": 0, "claims": [], "actions": [], "incursions": []}


def record(data, create=False):
    world = data["world_state"]
    run = world["dungeon_run"]
    if not run.get("active"):
        raise ValueError("exploration requires an active dungeon expedition")
    floor = run["current_floor"]
    visits = run.setdefault("resource_days_by_floor", {})
    day = visits.get(str(floor), world["day"])
    key = f"d{day}-f{floor}"
    records = world["dungeon_memory"]["records"]
    if create:
        visits.setdefault(str(floor), day)
        records.setdefault(key, new_record(day, floor, run["run_id"]))
    return records.get(key), key


def draw(data):
    tapes = json.loads(Path(__file__).with_name("dice_tape.json").read_text())["tapes"]["d10"]
    cursor = data["dice_state"]["dice_cursor_d10"]
    data["dice_state"]["dice_cursor_d10"] = (cursor + 1) % len(tapes)
    return {"die": "d10", "purpose": "M108-incursion", "cursor": cursor, "result": tapes[cursor]}


def active_incursion(rec):
    return next((x for x in rec["incursions"] if x["phase"] in {"signs", "engaged"}), None)


def hazard_threshold(rec, day, *, including_new=False):
    """Resource depletion is pinned; long-stay counts belong to the actual day."""
    actions = rec["actions"]
    count = sum(a.get("activity_day", rec["day"]) == day for a in actions)
    if not including_new:
        count += 1
    last = 0
    for incursion in rec["incursions"]:
        index = incursion.get("resolved_at", incursion["at"])
        if 1 <= index <= len(actions) and actions[index-1].get("activity_day", rec["day"]) == day:
            last = max(last, sum(a.get("activity_day", rec["day"]) == day for a in actions[:index]))
    return min(8, max(0, count - max(7, last + 3)))


def status(data):
    rec, key = record(data)
    world, run = data["world_state"], data["world_state"]["dungeon_run"]
    rec = rec or new_record(world["day"], run["current_floor"], run["run_id"])
    cleared = run["current_floor"] in world["defeated_floor_bosses"]
    pressure = rec["pressure"]
    source_key = f"boss-f{run['current_floor']}"
    growth = world["growth_state"]
    acquired = source_key in growth.get("boss_fruit_legacy_sources", []) or any(
        row.get("source_type") == "boss" and row.get("source_key") == source_key and
        row.get("outcome") == "awarded" for row in growth["resolutions"])
    return {"gm_only": True, "record": key, "cleared": cleared,
            "passage": {"available": cleared and active_incursion(rec) is None,
                        "ticks": run.get("passage_ticks", 0), "ticks_per_half_day": 6},
            "boss_contact_due": not cleared and pressure >= 6,
            "cue": "quiet" if cleared or pressure == 0 else
                "presence" if pressure <= 2 else "moving" if pressure <= 4 else
                "closing" if pressure == 5 else "contact",
            "active_incursion": active_incursion(rec),
            "boss_fruit": {"source_key": source_key, "rate_percent": 20 if acquired else 30,
                "pity_due": not acquired and growth["boss_fruit_miss_streak"] == 3,
                "daily_eligible": "boss-loot" not in rec["claims"]},
            "available_sites": [x for x in SITES if x not in rec["claims"]],
            "narration": "Show only observable sounds, tracks, terrain, and immediate choices. Do not quote this bookkeeping."}


def arrive(data):
    result = copy.deepcopy(data)
    record(result, True)
    return result


def resolve(data, action_id, kind, site=None, event_id=None, awareness="late", pursuit_outcome=None, loot_instance_ids=None):
    if kind not in KINDS or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", action_id):
        raise ValueError("invalid exploration action")
    result = copy.deepcopy(data)
    rec, _ = record(result, True)
    if any(a["id"] == action_id for r in result["world_state"]["dungeon_memory"]["records"].values() for a in r["actions"]):
        raise ValueError("action already resolved; reuse the existing receipt, do not reroll")
    world, run = result["world_state"], result["world_state"]["dungeon_run"]
    cleared = run["current_floor"] in world["defeated_floor_bosses"]
    pursuit = active_incursion(rec)
    if kind == "passage":
        if not cleared:
            raise ValueError("passage is only available on a boss-cleared floor")
        if site or event_id or pursuit_outcome or loot_instance_ids:
            raise ValueError("passage cannot claim resources, consume an event, or settle a pursuit")
        if pursuit:
            raise ValueError("resolve the pursuit before passing through")
    if pursuit_outcome:
        if not pursuit or pursuit_outcome not in {"escaped", "defeated", "withdrawn"}:
            raise ValueError("no matching active pursuit")
        if pursuit_outcome == "withdrawn" and pursuit["phase"] != "signs":
            raise ValueError("contact has begun; resolve escape or combat instead")
        pursuit["phase"] = pursuit_outcome
        pursuit["resolved_at"] = len(rec["actions"]) + 1
        if loot_instance_ids:
            if pursuit_outcome not in {"escaped", "defeated"}:
                raise ValueError("incursion equipment requires defeat or a successful seizure/escape")
            pursuit["loot_claimed"] = True
            pursuit["loot_instance_ids"] = list(loot_instance_ids)
    elif pursuit:
        raise ValueError("resolve the approaching/engaged pursuit before another exploration scene")
    if not cleared and rec["pressure"] >= 6 and kind != "boss":
        raise ValueError("boss contact is due: resolve the boss encounter or return")
    if site:
        if site not in SITES or site in rec["claims"]:
            raise ValueError("resource site unavailable until a later-day reentry")
        if site == "boss-loot" and kind != "boss":
            raise ValueError("boss loot requires a boss resolution")
        rec["claims"].append(site)
        floor = str(run["current_floor"])
        run["reward_searches_by_floor"][floor] = run["reward_searches_by_floor"].get(floor, 0) + 1
    if event_id:
        if event_id in run["used_event_ids"]:
            raise ValueError("event instance already used")
        run["used_event_ids"].append(event_id)
    run["current_floor_scenes"] += 1
    run["danger_zones_resolved"] += 1  # compatibility name; now counts substantive resolutions
    run["last_scene_kind"] = kind if kind in {"trash", "boss", "event", "exploration"} else "event"
    run["event_due"] = kind == "trash"  # pacing hint, not an encounter immunity
    if kind == "trash":
        run["trash_encounters_used"] += 1
    if not cleared:
        rec["pressure"] = min(6, rec["pressure"] + 1)
        if rec["pressure"] == 6:
            run["boss_route_found"] = True
    activity_day = world["day"]
    action = {"id": action_id, "kind": kind, "roll": None, "site": site, "activity_day": activity_day}
    if kind == "passage":
        action["run_id"] = run["run_id"]
        passage_time(result)
    # Boss contact takes precedence. One incident is counted once, not per combat round.
    since = len(rec["actions"]) + 1
    threshold = hazard_threshold(rec, activity_day)
    if threshold and not pursuit and kind != "boss" and (cleared or rec["pressure"] < 6):
        roll = draw(result)
        action["roll"] = roll
        if roll["result"] <= threshold:
            rec["incursions"].append({"id": action_id, "at": since,
                "origin_floor": min(9, run["current_floor"] + 1),
                "phase": "signs" if awareness == "early" else "engaged",
                "loot_claimed": False, "loot_instance_ids": []})
    rec["actions"].append(action)
    return result


def validate_memory(data, errors):
    world = data.get("world_state", {})
    memory = world.get("dungeon_memory")
    if not isinstance(memory, dict) or memory.get("version") != 1 or not isinstance(memory.get("records"), dict):
        errors.append("world_state.dungeon_memory requires version=1 and records; migrate-save first")
        return
    ids = set()
    for key, rec in memory["records"].items():
        if not isinstance(rec, dict):
            errors.append("dungeon record must be a mapping"); continue
        day, floor = rec.get("day"), rec.get("floor")
        if not integer(day) or not 1 <= day <= world.get("day", 0) or not integer(floor) or not 1 <= floor <= 9 or key != f"d{day}-f{floor}":
            errors.append("invalid dungeon daily floor key")
            continue
        if not isinstance(rec.get("created_run_id"), str) or not rec["created_run_id"]:
            errors.append("daily resource record requires its creating run id")
        if not integer(rec.get("pressure")) or not 0 <= rec["pressure"] <= 6:
            errors.append("dungeon pressure must be 0..6")
        claims, actions, incursions = rec.get("claims"), rec.get("actions"), rec.get("incursions")
        if not isinstance(claims, list) or any(x not in SITES for x in claims) or len(claims) != len(set(claims)):
            errors.append("daily resource claims must be unique known sites")
        if not isinstance(actions, list) or not isinstance(incursions, list):
            errors.append("dungeon actions/incursions must be lists"); continue
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get("id"), str) or action.get("kind") not in KINDS:
                errors.append("invalid dungeon action receipt"); continue
            if action["id"] in ids: errors.append("duplicate dungeon action id")
            ids.add(action["id"])
            activity_day = action.get("activity_day", rec["day"])
            if not integer(activity_day) or not rec["day"] <= activity_day <= world.get("day", 0):
                errors.append("dungeon action activity_day must be a known day")
            roll = action.get("roll")
            if roll is not None:
                from machadan_runtime import _fixed_tape_value
                if (not isinstance(roll, dict) or roll.get("die") != "d10" or
                    not integer(roll.get("cursor")) or not 0 <= roll["cursor"] < 500 or
                    roll.get("result") != _fixed_tape_value("d10", roll["cursor"])):
                    errors.append("incursion roll must match the fixed dice tape")
        for inc in incursions:
            if (not isinstance(inc, dict) or inc.get("phase") not in PHASES or
                not integer(inc.get("at")) or not 8 <= inc["at"] <= len(actions) or
                inc.get("origin_floor") != min(9, floor + 1) or not isinstance(inc.get("loot_claimed"), bool)):
                errors.append("invalid incursion record")
            elif inc["loot_claimed"] and inc["phase"] not in {"defeated", "escaped"}:
                errors.append("incursion equipment requires defeat or successful seizure and escape")
            elif inc["phase"] in {"escaped", "defeated", "withdrawn"} and (
                not integer(inc.get("resolved_at")) or not inc["at"] < inc["resolved_at"] <= len(actions)):
                errors.append("resolved pursuit requires the actual resolution activity")
        if sum(x.get("phase") in {"signs", "engaged"} for x in incursions if isinstance(x, dict)) > 1:
            errors.append("only one pursuit may be active on a floor")
    run = world.get("dungeon_run", {})
    if "passage_ticks" in run and (not integer(run["passage_ticks"]) or run["passage_ticks"] < 0):
        errors.append("dungeon_run.passage_ticks must be a nonnegative integer")
    if run.get("active"):
        actual = sum(action.get("kind") == "passage" and action.get("run_id") == run.get("run_id")
                     for rec in memory["records"].values() if isinstance(rec, dict)
                     for action in rec.get("actions", []) if isinstance(action, dict))
        if run.get("passage_ticks", 0) != actual:
            errors.append("passage_ticks must equal current expedition passage receipts")
    visits = run.get("resource_days_by_floor")
    if not isinstance(visits, dict): errors.append("dungeon_run.resource_days_by_floor must be a mapping")
    elif any(not str(f).isdigit() or not 1 <= int(f) <= 9 or not integer(d) or not 1 <= d <= world.get("day", 0) for f,d in visits.items()):
        errors.append("invalid dungeon visit resource days")
    elif run.get("active") and str(run.get("current_floor")) not in visits:
        errors.append("active floor must pin its resource day on arrival")
    elif run.get("active"):
        key = f"d{visits[str(run['current_floor'])]}-f{run['current_floor']}"
        if key not in memory["records"]:
            errors.append("active floor must create its daily resource record on arrival")


def validate_transition(old, new):
    errors = []
    ow, nw = old["world_state"], new["world_state"]
    before = ow.get("dungeon_memory", {}).get("records", {})
    after = nw.get("dungeon_memory", {}).get("records", {})
    old_run, run = ow["dungeon_run"], nw["dungeon_run"]
    same_run = old_run.get("active") and run.get("active") and old_run.get("run_id") == run.get("run_id")
    if same_run:
        old_visits = old_run.get("resource_days_by_floor", {})
        if any(run.get("resource_days_by_floor", {}).get(k) != v for k,v in old_visits.items()):
            errors.append("resource days cannot reset during a delve, including overnight")
        added_passages = [action for key, rec in after.items()
                          for action in rec.get("actions", [])[len(before.get(key, {}).get("actions", [])):]
                          if action.get("kind") == "passage"]
        if run.get("passage_ticks", 0) != old_run.get("passage_ticks", 0) + len(added_passages):
            errors.append("passage clock advances exactly once per passed floor")
        if added_passages:
            if len(added_passages) != 1 or old_run["current_floor"] not in ow["defeated_floor_bosses"]:
                errors.append("passage requires one previously cleared current floor")
            if added_passages[0].get("run_id") != old_run["run_id"] or added_passages[0].get("site"):
                errors.append("passage receipt must match its expedition and have no resource site")
            expected = copy.deepcopy(old)
            try:
                passage_time(expected)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                if any(nw.get(key) != expected["world_state"].get(key) for key in ("day", "time_of_day")):
                    errors.append("passage time must match its one-tick clock")
                if new.get("debt_state", {}).get("collection_pending") != expected.get("debt_state", {}).get("collection_pending"):
                    errors.append("passage must stop on and mark the collection day")
            if any(old.get(key) != new.get(key) for key in ("inventory", "item_definitions", "item_instances")):
                errors.append("passage cannot acquire or spend items")
            if (old.get("player", {}).get("gold") != new.get("player", {}).get("gold") or
                    old_run.get("reward_searches_by_floor") != run.get("reward_searches_by_floor") or
                    old_run.get("used_event_ids") != run.get("used_event_ids")):
                errors.append("passage cannot claim rewards or consume event stock")
    for key, prev in before.items():
        cur = after.get(key)
        if not isinstance(cur, dict): errors.append("daily dungeon history cannot be removed"); continue
        for field in ("day", "floor", "created_run_id"):
            if prev[field] != cur.get(field): errors.append("daily dungeon identity is immutable")
        for field in ("claims", "actions"):
            if cur.get(field, [])[:len(prev[field])] != prev[field]: errors.append(f"dungeon {field} is append-only")
        if cur.get("pressure", 0) < prev["pressure"]: errors.append("boss pressure cannot decrease")
        for index, inc in enumerate(prev["incursions"]):
            if index >= len(cur.get("incursions", [])): errors.append("incursion history cannot be removed"); continue
            nxt = cur["incursions"][index]
            if any(nxt.get(k) != inc[k] for k in ("id", "at", "origin_floor")):
                errors.append("incursion identity is immutable")
            allowed = {"signs": PHASES, "engaged": {"engaged", "escaped", "defeated"}}.get(inc["phase"], {inc["phase"]})
            if nxt.get("phase") not in allowed: errors.append("pursuit cannot reset or withdraw after contact")
            if inc["phase"] in {"escaped", "defeated", "withdrawn"} and nxt.get("resolved_at") != inc.get("resolved_at"):
                errors.append("pursuit resolution activity is immutable")
            if inc["loot_claimed"] and not nxt.get("loot_claimed"): errors.append("incursion loot cannot be claimed again")
            if inc["loot_claimed"] and nxt.get("loot_instance_ids") != inc.get("loot_instance_ids"):
                errors.append("claimed incursion equipment receipt is immutable")
        for inc in cur.get("incursions", []):
            prev_inc = next((x for x in prev["incursions"] if x["id"] == inc["id"]), {})
            if inc["loot_claimed"] and not prev_inc.get("loot_claimed"):
                ids = inc.get("loot_instance_ids", [])
                old_ids = {x.get("instance_id") for x in old.get("item_instances", [])}
                new_ids = {x.get("instance_id") for x in new.get("item_instances", [])}
                if not ids or len(ids) != len(set(ids)) or any(x not in new_ids - old_ids for x in ids):
                    errors.append("incursion loot must identify newly acquired equipment instances in the same commit")
    if run.get("active"):
        try:
            current, key = record(new)
        except (KeyError, ValueError): return errors
        for key2, rec in after.items():
            prev = before.get(key2)
            if rec == prev: continue
            if key2 != key: errors.append("only the current floor resource record may change")
            if prev is None and rec["day"] != nw["day"]:
                errors.append("new resource records require the current day")
            added = len(rec["actions"]) - len(prev["actions"] if prev else [])
            if not 0 <= added <= 1: errors.append("resolve one substantive incident per commit")
            base_pressure = prev["pressure"] if prev else 0
            expected_pressure = min(6, base_pressure + added) if rec["floor"] not in ow["defeated_floor_bosses"] else base_pressure
            if rec["pressure"] != expected_pressure:
                errors.append("boss approach must advance once per resolved incident on uncleared floors")
            if prev:
                if len(rec["claims"]) - len(prev["claims"]) > 1: errors.append("claim at most one resource site per incident")
                if rec["claims"] != prev["claims"] and not added: errors.append("resource claim requires a resolved incident")
                if added and prev["pressure"] >= 6 and run["current_floor"] not in ow["defeated_floor_bosses"] and rec["actions"][-1]["kind"] != "boss":
                    errors.append("boss contact must resolve before more exploration")
            if added:
                old_incursions = prev["incursions"] if prev else []
                pending = active_incursion(prev) if prev else None
                action = rec["actions"][-1]
                if action.get("activity_day", rec["day"]) != ow["day"]:
                    errors.append("new dungeon incidents belong to the current activity day")
                # Only prior incursions can impose a cooldown on this draw.
                hazard_view = {**rec, "incursions": old_incursions}
                threshold = hazard_threshold(hazard_view, ow["day"], including_new=True)
                if action.get("kind") == "passage" and rec.get("claims") != (prev or {}).get("claims", []):
                    errors.append("passage preserves every daily resource claim")
                required_roll = bool(threshold and not pending and action["kind"] != "boss" and
                    (rec["floor"] in ow["defeated_floor_bosses"] or rec["pressure"] < 6))
                roll = action.get("roll")
                if bool(roll) != required_roll:
                    errors.append("long-stay hazard draw is required exactly when eligible")
                expected_new_incursions = int(bool(required_roll and roll and roll["result"] <= threshold))
                if len(rec["incursions"]) - len(old_incursions) != expected_new_incursions:
                    errors.append("incursion creation must match its fixed-tape draw")
                elif expected_new_incursions:
                    inc = rec["incursions"][-1]
                    if inc["id"] != action["id"] or inc["at"] != len(rec["actions"]) or inc["phase"] not in {"signs", "engaged"}:
                        errors.append("new incursion must belong to the triggering incident")
                if pending:
                    nxt = next((x for x in rec["incursions"] if x["id"] == pending["id"]), {})
                    if nxt.get("phase") not in {"escaped", "defeated", "withdrawn"} or nxt.get("resolved_at") != len(rec["actions"]):
                        errors.append("resolve the pursuit before continuing exploration")
            for action in rec["actions"][-added:] if added else []:
                roll = action.get("roll")
                if roll:
                    start, end = old["dice_state"]["dice_cursor_d10"], new["dice_state"]["dice_cursor_d10"]
                    if (roll["cursor"] - start) % 500 >= (end - start) % 500:
                        errors.append("incursion roll must consume a fresh d10 in this commit")
    elif before != after:
        errors.append("return preserves dungeon memory; resolve any incident before closing the delve")
    hazard_cursors = []
    for key, rec in after.items():
        previous_actions = before.get(key, {}).get("actions", [])
        for action in rec["actions"][len(previous_actions):]:
            if action.get("roll"):
                hazard_cursors.append(action["roll"]["cursor"])
    old_growth = ow["growth_state"]["resolutions"]
    growth_cursors = [roll["cursor"] for row in nw["growth_state"]["resolutions"][len(old_growth):]
                      for roll in row.get("rolls", []) if roll.get("die") == "d10"]
    if set(hazard_cursors) & set(growth_cursors):
        errors.append("hazard and reward rolls must consume distinct d10 entries")
    if hazard_cursors and growth_cursors:
        start = old["dice_state"]["dice_cursor_d10"]
        if max((x-start) % 500 for x in hazard_cursors) >= min((x-start) % 500 for x in growth_cursors):
            errors.append("resolve the incursion draw before reward draws")
    return errors


def validate_adventure(old, new):
    """Called after the runtime's expedition/fire-holder checks."""
    errors = validate_transition(old, new)
    ow, nw = old["world_state"], new["world_state"]
    a, b = ow["dungeon_run"], nw["dungeon_run"]
    oe, ne = ow["expedition_state"], nw["expedition_state"]
    if a["active"]:
        prior_record, _ = record(old)
        rebirth_close = oe.get("rebirth_pending") and ne.get("last_end_reason") == "rebirth" and not b["active"]
        if prior_record and active_incursion(prior_record) and (not b["active"] or a["current_floor"] != b["current_floor"]) and not rebirth_close:
            errors.append("resolve pursuit escape/withdrawal before leaving the floor or dungeon")
    if a["active"] and not b["active"]:
        if ne.get("active") or ne.get("last_ended_expedition_id") != a["run_id"]:
            errors.append("closing dungeon requires the matching expedition end marker")
    if not a["active"] and b["active"]:
        if oe.get("active") or not ne.get("active") or ne.get("kind") != "dungeon" or ne.get("expedition_id") != b["run_id"]:
            errors.append("new delve requires a matching new dungeon expedition")
        for key, value in {"trash_encounters_used":0,"danger_zones_resolved":0,
            "last_scene_kind":"none","event_due":False,"used_event_ids":[],
            "current_floor_scenes":0,"reward_searches_by_floor":{},"camp_used":False}.items():
            if b.get(key) != value: errors.append(f"new delve requires {key}={value!r}")
        if b.get("passage_ticks", 0) != 0:
            errors.append("new delve starts with an empty passage clock")
    if a["active"] and b["active"]:
        if a["run_id"] != b["run_id"]: errors.append("active dungeon run id is immutable")
        if b["used_event_ids"][:len(a["used_event_ids"])] != a["used_event_ids"]:
            errors.append("dungeon event history is append-only")
        if a["camp_used"] and not b["camp_used"]: errors.append("camp cannot reset during a delve")
        if not 0 <= b["trash_encounters_used"] - a["trash_encounters_used"] <= 1:
            errors.append("resolve at most one new non-boss encounter per commit")
        if a["current_floor"] == b["current_floor"]:
            delta = b["current_floor_scenes"] - a["current_floor_scenes"]
            if not 0 <= delta <= 1: errors.append("resolve at most one floor incident per commit")
            if b["danger_zones_resolved"] - a["danger_zones_resolved"] != delta:
                errors.append("compatibility scene counter must match incident resolutions")
            old_count = sum(len(r["actions"]) for r in ow["dungeon_memory"]["records"].values())
            new_count = sum(len(r["actions"]) for r in nw["dungeon_memory"]["records"].values())
            if new_count - old_count != delta:
                errors.append("each resolved floor scene requires exactly one dungeon action receipt")
        else:
            limit = ow["deepest_depth_reached"]
            first_clear = a["current_floor"] not in ow["defeated_floor_bosses"] and a["current_floor"] in nw["defeated_floor_bosses"]
            if b["current_floor"] > limit and not (first_clear and b["current_floor"] == a["current_floor"] + 1):
                errors.append("floor move requires a permanently unlocked destination")
            if b["current_floor_scenes"] != 0 or b["danger_zones_resolved"] != 0:
                errors.append("floor move resets visit scene counters, not daily memory")
    od, nd = ow["deepest_depth_reached"], nw["deepest_depth_reached"]
    if nd > od and not ((od == 0 and nd == 1 and b["active"]) or
        (nd == od + 1 and od not in ow["defeated_floor_bosses"] and od in nw["defeated_floor_bosses"])):
        errors.append("next floor unlock requires first boss defeat")
    previous = {x["boss_id"]: x for x in ow["boss_records"]}
    current = {x["boss_id"]: x for x in nw["boss_records"]}
    if set(previous) - set(current): errors.append("boss records cannot be removed")
    expected_sources = set()
    changed_floors = set()
    for bid, rec in current.items():
        prev = previous.get(bid)
        if prev:
            if any(rec.get(k) != prev.get(k) for k in ("boss_id", "floor", "first_defeated_day")):
                errors.append("boss identity and first defeat are permanent")
            if rec["last_defeat_id"] == prev["last_defeat_id"]:
                if any(rec.get(k) != prev.get(k) for k in ("last_defeated_day", "rematch_available_day", "last_defeated_expedition_id")):
                    errors.append("boss defeat metadata requires a new defeat receipt")
                continue
            if rec["last_defeated_expedition_id"] == prev["last_defeated_expedition_id"]:
                errors.append("boss revives only after leaving the dungeon")
        if not b["active"] or b["current_floor"] != rec["floor"] or rec["last_defeated_expedition_id"] != ne.get("expedition_id"):
            errors.append("boss defeat requires its active floor and expedition")
            continue
        changed_floors.add(rec["floor"])
        if rec["last_defeated_day"] != nw["day"]: errors.append("boss defeat must use the current day")
        cur_rec, key = record(new)
        old_rec = ow["dungeon_memory"]["records"].get(key, {})
        eligible = "boss-loot" not in old_rec.get("claims", [])
        if eligible:
            expected_sources.add(rec["last_defeat_id"])
            if cur_rec is None or "boss-loot" not in cur_rec["claims"]:
                errors.append("eligible boss defeat must claim its daily loot site")
        if rec["floor"] not in ow["defeated_floor_bosses"] and not b["boss_route_found"]:
            errors.append("first boss defeat requires discovery or approaching-boss contact")
    old_rows = ow["growth_state"]["resolutions"]
    added = nw["growth_state"]["resolutions"][len(old_rows):]
    actual = {x["source_id"] for x in added if x.get("source_type") == "boss"}
    if actual != expected_sources:
        errors.append("each eligible daily boss loot claim requires one same-commit growth resolution")
    for row in added:
        if row.get("source_type") == "boss":
            matching = next((x for x in current.values() if x["last_defeat_id"] == row["source_id"]), None)
            if not matching or row.get("rule_version") != 2 or row.get("source_key") != f"boss-f{matching['floor']}":
                errors.append("new boss fruit rolls require M108 rule_version=2 and stable boss-fN source_key")
        elif row.get("source_type") == "chest":
            cur_rec, key = record(new) if b["active"] else (None, "")
            prev_rec = ow["dungeon_memory"]["records"].get(key, {})
            site = row.get("site_id")
            if (not cur_rec or site not in {"chest-1", "chest-2"} or row.get("rule_version") != 2 or
                row.get("floor") != cur_rec["floor"] or row.get("resource_day") != cur_rec["day"] or
                row.get("source_id") != f"{key}-{site}" or
                site not in cur_rec["claims"] or site in prev_rec.get("claims", [])):
                errors.append("new chest rolls require the same-commit daily site claim and stable dN-fN-chest-N identity")
    if b["active"]:
        cur_rec, key = record(new)
        prev_rec = ow["dungeon_memory"]["records"].get(key, {})
        if cur_rec and "boss-loot" in cur_rec["claims"] and "boss-loot" not in prev_rec.get("claims", []) and b["current_floor"] not in changed_floors:
            errors.append("boss-loot claim requires an actual same-commit boss defeat")
        if cur_rec:
            for site in {"chest-1", "chest-2"} & (set(cur_rec["claims"]) - set(prev_rec.get("claims", []))):
                if sum(x.get("source_type") == "chest" and x.get("source_id") == f"{key}-{site}" for x in added) != 1:
                    errors.append("each opened daily chest requires one fruit hit/miss resolution")
    return errors


def main():
    import machadan_runtime as rt
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=["status", "arrive", "resolve"])
    p.add_argument("--save", required=True)
    p.add_argument("--output")
    p.add_argument("--action-id")
    p.add_argument("--kind", choices=sorted(KINDS), default="exploration")
    p.add_argument("--site", choices=SITES)
    p.add_argument("--event-id")
    p.add_argument("--awareness", choices=["early", "late"], default="late")
    p.add_argument("--pursuit-outcome", choices=["escaped", "defeated", "withdrawn"])
    p.add_argument("--loot-instance-id", action="append", default=[])
    args = p.parse_args()
    data = rt.load_yaml(Path(args.save))
    errors, _ = rt.validate_save_data(data)
    if errors and args.operation != "arrive": raise ValueError("; ".join(errors))
    if args.operation == "status":
        result = status(data)
    else:
        if not args.output or (args.operation == "resolve" and not args.action_id):
            raise ValueError("candidate output is required; resolve also requires --action-id")
        if Path(args.save).resolve() == Path(args.output).resolve(): raise ValueError("candidate must differ from committed save")
        candidate = arrive(data) if args.operation == "arrive" else resolve(data, args.action_id, args.kind, args.site, args.event_id, args.awareness, args.pursuit_outcome, args.loot_instance_id)
        if args.operation == "arrive":
            errors, _ = rt.validate_save_data(candidate)
            if errors: raise ValueError("; ".join(errors))
        rt.atomic_write(Path(args.output), rt.dump_yaml(candidate))
        result = {"gm_only": True, "candidate": str(Path(args.output).resolve()), "next": status(candidate),
                  "commit_required": True}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
