"""One-time introductory fire grant; canonical bonuses remain separate from allocation.

This helper never writes a live save.  It builds a complete, retryable candidate
for the existing validated commit path, including explanation/ownership flags.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re


STATS = ("str", "def", "int", "spd", "tec", "chm")
CURRENT_RULE = "all3-plus15-v1"
LEGACY_RULE = "legacy-all5-plus15-v1"
UNKNOWN_LEGACY_RULE = "legacy-preserved"
INITIAL_RULES = {CURRENT_RULE: (3, 33), LEGACY_RULE: (5, 45)}
FLAGS = ("body_received", "allocation_complete", "fire_granted", "fire_explained", "tutorial_complete")
SCRIPT_FOR_STAGE = {"rebirth": "SCRIPT_OPENING_REBIRTH", "bonus": "SCRIPT_OPENING_BONUS",
                    "fire": "SCRIPT_OPENING_FIRE", "tutorial": "SCRIPT_OPENING_TUTORIAL"}


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _stat_budget_matches(values, minimum, total):
    return (isinstance(values, dict) and set(values) == set(STATS)
            and all(_integer(values[key]) and values[key] >= minimum for key in STATS)
            and sum(values.values()) == total)


def _allocation_valid(player, rule=CURRENT_RULE):
    if rule not in INITIAL_RULES:
        return False
    minimum, total = INITIAL_RULES[rule]
    return _stat_budget_matches(player.get("base_stats"), minimum, total) and player.get("base_lp") == 20


def _unallocated_body_valid(player, rule=CURRENT_RULE):
    """A formed body may receive fire before any of its 15 points are spent."""
    if rule != CURRENT_RULE:
        return False
    return player.get("base_stats") == {key: 3 for key in STATS} and player.get("base_lp") == 20


def _legacy_progress(data):
    player = data.get("player", {})
    stats = player.get("base_stats", {})
    has_body = isinstance(stats, dict) and any(_integer(v) and v > 0 for v in stats.values()) and player.get("base_lp", 0) > 0
    turn = data.get("transaction", {}).get("last_committed_turn", 0)
    return player.get("build_complete") is True or (_integer(turn) and turn > 0 and has_body)


def _allocation_rule(data):
    """Keep already allocated legacy points; only fresh creation adopts ALL3."""
    saved = _onboarding(data)
    explicit = saved.get("allocation_rule")
    if isinstance(explicit, str) and explicit in {*INITIAL_RULES, UNKNOWN_LEGACY_RULE}:
        return explicit
    snapshot = saved.get("initial_base_stats")
    for rule in (LEGACY_RULE, CURRENT_RULE):
        if _stat_budget_matches(snapshot, *INITIAL_RULES[rule]):
            return rule
    player = data.get("player", {})
    values = player.get("base_stats")
    # Older, partially completed allocation has already established the ALL5
    # body. Continue its 15-point allocation rather than taking those points.
    if (player.get("base_lp") == 20 and isinstance(values, dict) and set(values) == set(STATS)
            and all(_integer(values[key]) and values[key] >= 5 for key in STATS)
            and 30 <= sum(values.values()) <= 45):
        return LEGACY_RULE
    if _legacy_progress(data):
        return UNKNOWN_LEGACY_RULE
    return CURRENT_RULE


def _actors(data):
    return [data["player"], *[member for member in data.get("party", []) if isinstance(member, dict)]]


def _identities(actor):
    return {str(actor[key]) for key in ("character_id", "name") if actor.get(key)}


def _resolve_holders(data, holders):
    """Resolve stable IDs first; never fan a legacy name out to several people.

    Unseen holders may be staying at the inn or on a separate expedition. They
    do not participate in this scene and are not an ambiguity by themselves.
    """
    actors = _actors(data)
    resolved, errors = set(), []
    for reference in holders:
        by_id = [actor for actor in actors if actor.get("character_id") == reference]
        matches = by_id if by_id else [actor for actor in actors if actor.get("name") == reference]
        if len(matches) > 1:
            errors.append("ambiguous fire holder identity: " + str(reference))
        elif len(matches) == 1:
            resolved.add(matches[0].get("character_id"))
    return resolved, errors


def _owns(actor, holders, data):
    resolved, _ = _resolve_holders(data, holders)
    return actor.get("character_id") in resolved


def _onboarding(data):
    value = data.get("world_state", {}).get("onboarding", {})
    return value if isinstance(value, dict) else {}


def validate_onboarding(data, errors):
    """Optional field validation; do not impose initial budgets on old/grown saves."""
    world = data.get("world_state")
    if not isinstance(world, dict) or "onboarding" not in world:
        return
    value = world["onboarding"]
    if not isinstance(value, dict):
        errors.append("world_state.onboarding must be a mapping")
        return
    for key in FLAGS:
        if key in value and not isinstance(value[key], bool):
            errors.append("world_state.onboarding." + key + " must be a boolean")
    rule = value.get("allocation_rule")
    if rule is not None and (not isinstance(rule, str) or rule not in {*INITIAL_RULES, UNKNOWN_LEGACY_RULE}):
        errors.append("onboarding.allocation_rule is not a supported initial-allocation version")
    if "legacy_initial_allocation" in value and not isinstance(value["legacy_initial_allocation"], bool):
        errors.append("onboarding.legacy_initial_allocation must be a boolean")
    initial = value.get("initial_base_stats")
    if initial is not None:
        accepted = [rule] if isinstance(rule, str) and rule in INITIAL_RULES else list(INITIAL_RULES)
        if not any(_stat_budget_matches(initial, *INITIAL_RULES[item]) for item in accepted):
            errors.append("onboarding.initial_base_stats must match ALL3+15=33 or a preserved legacy ALL5+15=45 receipt")
    tx = value.get("fire_grant_transaction_id")
    if tx is not None and (not isinstance(tx, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", tx) is None):
        errors.append("onboarding.fire_grant_transaction_id must be a safe transaction id")
    if value.get("fire_explained") is True and value.get("fire_granted") is not True:
        errors.append("onboarding.fire_explained requires the historical fire_granted flag")
    if value.get("tutorial_complete") is True and value.get("fire_explained") is not True:
        errors.append("onboarding.tutorial_complete requires the fire explanation")
    # fire_granted is a historical receipt. Later voluntary transfers may remove
    # the player from current holders and must not cause another initial grant.


def validate_transition(api, old, new, transaction_id):
    """Protect the recorded introduction without restricting legacy campaigns.

    A transaction receipt records the chosen grant path. It does not claim to
    prove that a model executed a particular helper or narrated its explanation.
    """
    errors = []
    before, after = _onboarding(old), _onboarding(new)
    for key in ("fire_granted", "fire_explained"):
        if before.get(key) is True and after.get(key) is not True:
            errors.append("onboarding." + key + " is an irreversible historical record")
    for key in ("initial_base_stats", "fire_grant_transaction_id", "allocation_rule", "legacy_initial_allocation"):
        if key in before and after.get(key) != before[key]:
            errors.append("onboarding." + key + " cannot be removed or rewritten")
    if after.get("tutorial_complete") is True and after.get("fire_explained") is not True:
        errors.append("the introductory tutorial cannot complete before the fire explanation")
    if (after.get("tutorial_complete") is True and before.get("tutorial_complete") is not True
            and not status_data(new)["allocation_complete"]):
        errors.append("the introductory tutorial cannot complete before initial allocation")
    if after.get("fire_explained") is True and after.get("fire_granted") is not True:
        errors.append("the fire explanation requires the historical grant record")
    newly_recorded = before.get("fire_granted") is not True and after.get("fire_granted") is True
    if newly_recorded:
        if new.get("hearing_progress", {}).get("status") != "complete":
            errors.append("new fire grant record requires the completed confirmed hearing")
        if after.get("fire_grant_transaction_id") != transaction_id:
            errors.append("new fire grant record must use the current transaction id")
        old_player, new_player = old.get("player", {}), new.get("player", {})
        old_holders = old.get("fire_state", {}).get("holders", [])
        new_holders = new.get("fire_state", {}).get("holders", [])
        _, identity_errors = _resolve_holders(new, new_holders)
        errors.extend(identity_errors)
        old_owned = _owns(old_player, old_holders, old)
        new_owned = _owns(new_player, new_holders, new)
        if not new_owned and not old_owned:
            errors.append("new fire grant record requires actual player ownership or an existing legacy grant")
        expected_rule = _allocation_rule(old)
        if after.get("allocation_rule") != expected_rule:
            errors.append("new fire grant must preserve the campaign's initial-allocation version")
        if not old_owned and (expected_rule == CURRENT_RULE or not status_data(old)["legacy_progress"]):
            initial = after.get("initial_base_stats")
            if _unallocated_body_valid(new_player, expected_rule):
                if (after.get("allocation_complete") is True or initial is not None
                        or old_player.get("base_stats") != new_player.get("base_stats")):
                    errors.append("fire before allocation must preserve the unspent body and must not fabricate a completed allocation")
            elif not _allocation_valid(new_player, expected_rule) or initial != new_player.get("base_stats"):
                errors.append("new initial grant requires an unspent ALL3 body or the exact preserved completed allocation")
    initial_completed = before.get("allocation_complete") is not True and after.get("allocation_complete") is True
    if initial_completed and before.get("fire_granted") is True and not _legacy_progress(old):
        if not _allocation_valid(new.get("player", {}), after.get("allocation_rule", CURRENT_RULE)):
            errors.append("initial allocation after fire must use the exact versioned budget")
        if after.get("initial_base_stats") != new.get("player", {}).get("base_stats"):
            errors.append("initial allocation must record its own birth snapshot after fire")
        old_rows=old.get("world_state", {}).get("allocation_state", {}).get("resolutions", [])
        new_rows=new.get("world_state", {}).get("allocation_state", {}).get("resolutions", [])
        if not any(isinstance(row,dict) and row.get("mode")=="initial"
                   and row.get("transaction_id")==transaction_id
                   and row.get("actor_id")==new.get("player",{}).get("character_id")
                   for row in new_rows[len(old_rows):]):
            errors.append("initial allocation after fire requires its confirmed allocation receipt")
    return errors


def status_data(data):
    """Infer safe legacy progress without changing an old campaign."""
    saved = _onboarding(data)
    player = data.get("player", {})
    hearing_done = data.get("hearing_progress", {}).get("status") == "complete"
    script = data.get("active_script", {})
    script_id, script_done = script.get("id"), script.get("status") == "complete"
    later_script = script_id in {"SCRIPT_OPENING_BONUS", "SCRIPT_OPENING_FIRE", "SCRIPT_OPENING_TUTORIAL"}
    stats = player.get("base_stats", {})
    has_body_stats = isinstance(stats, dict) and any(_integer(v) and v > 0 for v in stats.values()) and player.get("base_lp", 0) > 0
    mature = _legacy_progress(data)
    rule = _allocation_rule(data)
    minimum, total = INITIAL_RULES.get(rule, (None, None))
    holders = data.get("fire_state", {}).get("holders", [])
    resolved_holders, identity_errors = _resolve_holders(data, holders)
    held = player.get("character_id") in resolved_holders
    historical_grant = saved.get("fire_granted") is True or held
    body = bool(saved.get("body_received") or mature or has_body_stats or later_script
                or (script_id == "SCRIPT_OPENING_REBIRTH" and script_done) or historical_grant)
    allocated = bool(saved.get("allocation_complete") or mature or _allocation_valid(player, rule))
    if rule == CURRENT_RULE and not _allocation_valid(player, rule):
        allocated = False  # selecting a job cannot turn an over-budget new build into legacy data
    explained = saved.get("fire_explained") is True
    tutorial = bool(saved.get("tutorial_complete") or mature
                    or (script_id == "SCRIPT_OPENING_TUTORIAL" and script_done))
    if not hearing_done:
        next_stage = "hearing"
    elif not body:
        next_stage = "rebirth"
    elif rule != CURRENT_RULE and not allocated:
        next_stage = "bonus"  # already-started legacy budgets keep their old order
    elif not historical_grant or not explained:
        next_stage = "fire"
    elif not allocated:
        next_stage = "bonus"
    elif not tutorial:
        next_stage = "tutorial"
    else:
        next_stage = "complete"
    return {"ok": not identity_errors, "next_stage": next_stage, "next_script": SCRIPT_FOR_STAGE.get(next_stage),
            "already_granted": historical_grant, "currently_holds_fire": held,
            "needs_explanation": hearing_done and not explained,
            "needs_grant": not historical_grant and not identity_errors, "legacy_progress": mature,
            "requires_identity_review": bool(identity_errors), "identity_errors": identity_errors,
            "body_received": body, "allocation_complete": allocated,
            "tutorial_complete": tutorial, "initial_allocation_valid": _allocation_valid(player, rule),
            "allocation_rule": rule, "allocation_minimum": minimum,
            "allocation_bonus_points": 15 if total is not None else None, "allocation_total": total,
            "legacy_initial_allocation": rule != CURRENT_RULE,
            "allocation_rule_inferred": "allocation_rule" not in saved,
            # Consumers should use this versioned budget before presenting the
            # allocation prompt. Null means preserve a mature legacy character.
            "allocation_budget": {"minimum": minimum,
                                  "bonus_points": 15 if total is not None else None,
                                  "total": total, "base_lp": 20 if total is not None else None,
                                  "rule": rule, "legacy": rule != CURRENT_RULE},
            "notice": "初期15点と火の補正は別枠。候補作成後は通常のcommitで確定してください"}


def _validated_source(api, source):
    path = Path(source).expanduser()
    if path.is_symlink():
        raise api.RuntimeProblem("onboarding source must not be a symbolic link")
    path = path.resolve()
    data = api.load_yaml(path)
    errors, warnings = api.validate_save_data(data)
    if errors:
        raise api.RuntimeProblem("invalid onboarding save: " + "; ".join(errors))
    return path, data, warnings


def status(api, args):
    path, data, warnings = _validated_source(api, args.save)
    return {**status_data(data), "save": str(path), "warnings": warnings}


def _output_path(api, source, raw):
    supplied = Path(raw).expanduser()
    if supplied.is_symlink():
        raise api.RuntimeProblem("onboarding output must not be a symbolic link")
    output = supplied.resolve()
    if output == source:
        raise api.RuntimeProblem("grant-fire --output must differ from --save")
    root = api.ROOT.resolve()
    if output.is_relative_to(root.parent) and not output.is_relative_to(root / "state/runtime"):
        raise api.RuntimeProblem("generated onboarding output inside the game belongs under state/runtime")
    for directory in (root.parent.parent / "skills", root.parent.parent / "custom-skills"):
        if output.is_relative_to(directory.resolve()):
            raise api.RuntimeProblem("onboarding output may not overwrite skill files")
    return output


def _apply_fire(actor, count, holds):
    stat, lp_bonus = ((3, 12) if count == 1 else (2, 8) if count == 2 else
                      (1, 5) if count == 3 else (0, 3)) if holds and count else (0, 0)
    before = {"effective_stats": copy.deepcopy(actor["effective_stats"]),
              "lp": copy.deepcopy(actor["lp"]), "mp": copy.deepcopy(actor["mp"])}
    actor["fire_bonus"] = {key: stat for key in STATS}
    actor["fire_lp_bonus"] = lp_bonus
    actor["effective_stats"] = {key: sum(actor[group][key] for group in
        ("base_stats", "growth_bonus", "equipment_bonus", "fire_bonus", "temporary_modifiers")) for key in STATS}
    actor["stats"] = copy.deepcopy(actor["effective_stats"])
    maximum_lp = sum(actor[key] for key in ("base_lp", "job_lp_bonus", "fire_lp_bonus", "temporary_lp_bonus")) + actor.get("stat_lp_bonus", 0)
    maximum_mp = actor["effective_stats"]["int"]
    old_lp, old_mp = before["lp"], before["mp"]
    # Preserve the amount already lost. A capacity increase is not a full heal.
    lp_cur = max(0, min(maximum_lp, old_lp["cur"] + maximum_lp - old_lp["max"]))
    if old_lp["max"] > 0 and old_lp["cur"] == 0:
        lp_cur = 0  # explaining/repairing a grant must never resurrect a casualty
    actor["lp"] = {"cur": lp_cur, "max": maximum_lp}
    actor["mp"] = {"cur": max(0, min(maximum_mp, old_mp["cur"] + maximum_mp - old_mp["max"])), "max": maximum_mp}
    return {"character_id": actor["character_id"], "before": before,
            "after": {"effective_stats": copy.deepcopy(actor["effective_stats"]),
                      "lp": copy.deepcopy(actor["lp"]), "mp": copy.deepcopy(actor["mp"])}}


def grant(api, args):
    source, data, warnings = _validated_source(api, args.save)
    output = _output_path(api, source, args.output)
    tx = api.safe_id(args.transaction_id)
    progress = status_data(data)
    if progress["requires_identity_review"]:
        raise api.RuntimeProblem("火の所有者を一意に確認できません。character_idで修正してから授与してください: " +
                                 "; ".join(progress["identity_errors"]))
    if data.get("hearing_progress", {}).get("status") != "complete":
        raise api.RuntimeProblem("finish the confirmed hearing before the fire explanation/grant")
    if not progress["body_received"]:
        raise api.RuntimeProblem("receive the initial body before granting fire")
    rule = progress["allocation_rule"]
    if (not progress["already_granted"] and (rule == CURRENT_RULE or not progress["legacy_progress"])
            and not (_unallocated_body_valid(data["player"], rule) or _allocation_valid(data["player"], rule))):
        raise api.RuntimeProblem("initial fire grant requires the unspent body or a preserved completed allocation for " + rule + " and Base LP20")
    # A successful commit may be retried with its existing, exact pre-commit
    # candidate. No newer save fields are ever overwritten by a regenerated one.
    if data.get("transaction", {}).get("last_transaction_id") == tx and output.is_file():
        old_candidate = api.load_yaml(output)
        digest = api.sha256_bytes(api.dump_yaml(old_candidate).encode("utf-8"))
        if digest == data["transaction"].get("last_candidate_hash"):
            return {"ok": True, "idempotent": True, "already_granted": True,
                    "output": str(output), "next_stage": progress["next_stage"], "warnings": warnings}
        raise api.RuntimeProblem("committed grant candidate differs from its transaction receipt")
    result = copy.deepcopy(data)
    player = result["player"]
    holders = result["fire_state"].setdefault("holders", [])
    if not isinstance(holders, list) or not all(isinstance(value, str) and value for value in holders) or len(holders) != len(set(holders)):
        raise api.RuntimeProblem("fire_state.holders must be unique non-empty identities")
    expedition = result["world_state"].get("expedition_state", {})
    active = expedition.get("active") is True
    if active and not progress["already_granted"]:
        raise api.RuntimeProblem("初回授与は遠征中に行いません。帰還後、宿で説明と授与を行ってください")
    new_ownership = not progress["already_granted"]
    if new_ownership:
        holders.append(player["character_id"])
    changes = []
    if not active:
        actors = _actors(result)
        resolved_holders, identity_errors = _resolve_holders(result, holders)
        if identity_errors:
            raise api.RuntimeProblem("; ".join(identity_errors))
        count = sum(actor.get("character_id") in resolved_holders for actor in actors)
        for actor in actors:
            change = _apply_fire(actor, count, actor.get("character_id") in resolved_holders)
            if "encumbrance" in actor:
                # Fire changes STR/SPD, so a tracked equipped-weight penalty
                # must be derived again. This does not touch the LP/MP deltas.
                from encumbrance import recalculate, EncumbranceError
                try:
                    recalculate(result, actor["character_id"])
                except EncumbranceError as exc:
                    raise api.RuntimeProblem(str(exc)) from exc
                change["after"]["effective_stats"] = copy.deepcopy(actor["effective_stats"])
            changes.append(change)
    # During an active expedition the old participant snapshot and all resource
    # values remain untouched; explaining a legacy grant cannot recalculate it.
    onboarding = result["world_state"].setdefault("onboarding", {})
    onboarding.update(body_received=True, allocation_complete=progress["allocation_complete"], fire_granted=True, fire_explained=True)
    onboarding.setdefault("allocation_rule", rule)
    onboarding.setdefault("legacy_initial_allocation", rule != CURRENT_RULE)
    onboarding.setdefault("tutorial_complete", progress["tutorial_complete"])
    onboarding.setdefault("fire_grant_transaction_id", tx)
    if (rule == CURRENT_RULE or not progress["legacy_progress"]) and _allocation_valid(player, rule):
        onboarding.setdefault("initial_base_stats", copy.deepcopy(player["base_stats"]))
    script = result["active_script"]
    if not (script.get("status") == "in_progress" and not str(script.get("id", "")).startswith("SCRIPT_OPENING_")):
        script.update(id="SCRIPT_OPENING_FIRE", status="complete", checkpoint="fire-explained-and-granted")
    final_errors, final_warnings = api.validate_save_data(result)
    if final_errors:
        raise api.RuntimeProblem("fire grant produced an invalid candidate: " + "; ".join(final_errors))
    text = api.dump_yaml(result)
    identical = output.is_file() and output.read_text(encoding="utf-8") == text
    if output.exists() and not identical:
        raise api.RuntimeProblem("refusing to overwrite a different fire grant candidate: " + str(output))
    if not identical:
        api.atomic_write(output, text)
    return {"ok": True, "idempotent": identical, "output": str(output),
            "already_granted": progress["already_granted"], "new_ownership": new_ownership,
            "next_stage": status_data(result)["next_stage"], "deltas": changes,
            "expedition_bonus_reconciliation_deferred": active,
            "transaction_id": tx, "warnings": [*warnings, *final_warnings],
            "notice": "説明・授与の候補だけを作成しました。同じtransaction IDのcommit成功後に点火の結果を表示してください"}
