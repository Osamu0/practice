#!/usr/bin/env python3
"""Read-only M30 tests for allocation/fruit candidate recalculation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True


def runtime_integration(root):
    """Exercise actual runtime CLI handlers in a private, manifested fixture."""
    cases = []
    with tempfile.TemporaryDirectory(prefix="machadan-weight-flow-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root.parent, game, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"))
        manifest_path = game / "RUNTIME_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        version = re.search(r"(?im)^version:\s*(\S.*)$", (game / "VERSION.txt").read_text())
        manifest["version"] = version.group(1).strip()
        # Private test manifest only. Never alter live/distributed manifests to
        # conceal changed bytes; this fixture records the implementation tested.
        manifest["files"] = [
            {"path": path.relative_to(game).as_posix(), "size": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(game.rglob("*")) if path.is_file() and path != manifest_path
        ]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("machadan_weight_flow_runtime", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        parser = api.build_parser()

        def command(*arguments):
            args = parser.parse_args(list(map(str, arguments)))
            value = args.handler(args)
            if isinstance(value, tuple):
                if value[0]:
                    raise api.RuntimeProblem(str(value[1]))
                return value[1]
            return value

        import encumbrance
        save = clone / "saves/weight-flow.yaml"
        command("new-save", "--campaign-id", "weight-flow", "--output", save)
        data = api.load_yaml(save)
        actor = data["player"]
        base = dict(zip(api.STAT_KEYS, (8, 5, 5, 5, 5, 5)))
        actor.update(name="Weight Probe", age=30, gender="male", job="旅人", build_complete=True,
                     base_stats=base, effective_stats={key: base[key] + 3 for key in base},
                     stats={key: base[key] + 3 for key in base}, base_lp=20, fire_lp_bonus=12,
                     fire_bonus={key: 3 for key in base}, lp={"cur": 17, "max": 32}, mp={"cur": 3, "max": 8}, gold=200)
        actor_id = actor["character_id"]
        data["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        data.update(play_mode="RP", ero_style="machadan", player_body="標準")
        data["partner_pref"]["asked"] = True
        data["world_state"].update(location="ギルド", time_of_day="朝")
        data["world_state"]["onboarding"].update(allocation_rule="all3-plus15-v1", body_received=True,
            allocation_complete=True, fire_granted=True, fire_explained=True, tutorial_complete=True,
            initial_base_stats=copy.deepcopy(base), fire_grant_transaction_id="fixture-fire")
        data["fire_state"]["holders"] = [actor_id]
        encumbrance.recalculate(data, actor_id)
        errors, _ = api.validate_save_data(data)
        assert not errors, errors
        api.atomic_write(save, api.dump_yaml(data))
        # A request rendered while unencumbered must not survive later equipment
        # changes, even though its six allocation controls still look valid.
        request = command("allocation-widget", "--save", save, "--mode", "respec", "--actor-id", actor_id,
                          "--output", clone / "state/runtime/old-weight-widget.html")
        old_widget = json.loads(Path(request["state_path"]).read_text())
        serial = 0

        def apply_commit(operations):
            nonlocal serial
            serial += 1
            context = clone / f"state/runtime/weight-{serial}.md"
            prepared = clone / f"state/runtime/weight-{serial}.prepared.yaml"
            final = clone / f"state/runtime/weight-{serial}.final.yaml"
            command("prepare-context", "--save", save, "--scene", "turn", "--output", context,
                    "--candidate-save-output", prepared)
            changes = prepared.with_suffix(".changes.json")
            payload = json.loads(changes.read_text())
            payload["operations"] = operations
            changes.write_text(json.dumps(payload, ensure_ascii=False))
            before = save.read_bytes()
            command("apply-changes", "--current", save, "--prepared", prepared, "--changes", changes, "--output", final)
            assert save.read_bytes() == before, "candidate creation wrote the current save"
            candidate = api.load_yaml(final)
            assert candidate["player"]["lp"] == {"cur": 17, "max": 32}
            assert candidate["player"]["mp"] == {"cur": 3, "max": 8}
            turn = api.load_yaml(save)["transaction"]["last_committed_turn"] + 1
            command("commit-save", "--current", save, "--candidate", final,
                    "--transaction-id", "weight-flow-" + str(serial), "--turn", turn)
            return api.load_yaml(save)

        definition = {"item_def_id": "weight-def", "name": "Weight Probe", "category": "equipment",
                      "specification": {"weight": 15}, "provenance": {}, "balance_anchor": {}}
        instance = {"instance_id": "weight-instance", "item_def_id": "weight-def", "name": "Weight Probe",
                    "location": "equipped", "slot_cost": 0, "owner_character_id": actor_id,
                    "specification_snapshot": {"weight": 15}}
        equipped = apply_commit([
            {"op": "add", "path": "/item_definitions/-", "value": definition},
            {"op": "add", "path": "/item_instances/-", "value": instance},
            {"op": "replace", "path": "/player/equipment/weapon_instance_id", "value": "weight-instance"},
        ])
        assert equipped["player"]["encumbrance"] == {"version": 1, "total_weight": 15, "raw_penalty": 4, "applied_penalty": 4}
        assert equipped["player"]["effective_stats"]["spd"] == 4
        cases.append("runtime_equip_refreshes_initial_zero_weight_record")
        old_widget["values"].update(str=7, spd=6)
        old_widget.update(complete=True, revision=1)
        old_state_path = clone / "state/runtime/old-weight-answer.json"
        old_state_path.write_text(json.dumps(old_widget, ensure_ascii=False))
        before = save.read_bytes()
        try:
            command("allocation-resolve", "--save", save, "--widget-state", old_state_path, "--confirmation", "確定",
                    "--output", clone / "state/runtime/stale-weight.yaml", "--transaction-id", "stale-weight")
            raise AssertionError("widget with old equipment snapshot was accepted")
        except api.RuntimeProblem as exc:
            assert "stale" in str(exc) and save.read_bytes() == before
        cases.append("runtime_equipment_change_invalidates_widget_request")
        grown = apply_commit([{"op": "replace", "path": "/player/growth_bonus/str", "value": 2}])
        assert grown["player"]["encumbrance"]["raw_penalty"] == 2
        assert grown["player"]["effective_stats"]["spd"] == 6
        assert grown["world_state"]["onboarding"]["initial_base_stats"] == base
        cases.append("runtime_strength_growth_refreshes_weight_without_healing")
        # temporary_modifiers.spd is the existing aggregate, including the
        # tracked weight component. Apply a new -3 effect as a delta to it.
        affected = apply_commit([{"op": "replace", "path": "/player/temporary_modifiers/spd",
                                 "value": grown["player"]["temporary_modifiers"]["spd"] - 3}])
        assert affected["player"]["encumbrance"]["applied_penalty"] == 2
        assert affected["player"]["effective_stats"]["spd"] == 3
        cases.append("runtime_temporary_spd_delta_preserves_weight_component")
        companion = copy.deepcopy(affected["player"])
        companion.update(character_id="new-weight-companion", name="Companion", fire_bonus={key: 0 for key in base},
                         fire_lp_bonus=0, lp={"cur": 15, "max": 20}, mp={"cur": 2, "max": 5},
                         equipment={"weapon_instance_id": None, "armor_instance_id": None, "offhand_instance_id": None, "fixed": []},
                         temporary_modifiers={key: 0 for key in base}, growth_bonus={key: 0 for key in base})
        companion.pop("encumbrance")
        companion["effective_stats"] = dict(base)
        companion["stats"] = dict(base)
        joined = apply_commit([{"op": "add", "path": "/party/-", "value": companion}])
        assert joined["party"][0]["encumbrance"] == {"version": 1, "total_weight": 0, "raw_penalty": 0, "applied_penalty": 0}
        assert joined["party"][0]["stat_lp_bonus"] == 1  # Permanent DEF5, M102.
        assert joined["party"][0]["lp"] == {"cur": 15, "max": 21}
        assert joined["party"][0]["mp"] == {"cur": 2, "max": 5}
        cases.append("runtime_new_actor_starts_typed_weight_tracking")
    return cases


def check(root: Path) -> dict:
    spec = importlib.util.spec_from_file_location("machadan_encumbrance_probe", root / "tools/encumbrance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = []

    def fixture():
        actor = {"character_id": "player", "name": "Same name", "base_stats": {key: 6 for key in module.STATS},
                 "equipment": {"weapon_instance_id": "weapon", "armor_instance_id": "armor",
                               "offhand_instance_id": "offhand", "fixed": ["帰還の腕輪"]},
                 "lp": {"cur": 17, "max": 20}, "mp": {"cur": 3, "max": 6}}
        actor["base_stats"]["str"] = 8
        for group in module.GROUPS[1:]:
            actor[group] = {key: 0 for key in module.STATS}
        actor["effective_stats"] = dict(actor["base_stats"])
        actor["stats"] = dict(actor["effective_stats"])
        data = {"player": actor, "party": [], "inn_reserve": [], "item_instances": [], "item_definitions": []}
        for key, weight in (("weapon", 7), ("armor", 5), ("offhand", 2)):
            data["item_instances"].append({"instance_id": key, "item_def_id": key + "-def", "location": "equipped",
                                          "owner_character_id": "player", "specification_snapshot": {"weight": weight}})
            data["item_definitions"].append({"item_def_id": key + "-def", "specification": {"weight": weight}})
        return data

    def reject(name, data, *, recalc=False):
        before = copy.deepcopy(data)
        try:
            (module.recalculate if recalc else module.preview)(data, "player")
            raise AssertionError(name + " was accepted")
        except module.EncumbranceError:
            assert data == before, name + " mutated data on rejection"
        cases.append(name)

    data = fixture()
    before = copy.deepcopy(data)
    profile = module.preview(data, "player")
    assert profile["total_weight"] == 14 and profile["raw_penalty"] == 6
    assert profile["applied_penalty"] == 6 and profile["effective_spd"] == 0
    assert profile["raw_spd_bonus"] == profile["str_bonus"] == 0 and data == before
    cases.append("read_only_preview_includes_offhand_weight")
    module.recalculate(data, "player")
    actor = data["player"]
    assert actor["temporary_modifiers"]["spd"] == -6 and actor["effective_stats"]["spd"] == 0
    assert actor["encumbrance"] == {"version": 1, "total_weight": 14, "raw_penalty": 6, "applied_penalty": 6}
    before = copy.deepcopy(data)
    module.recalculate(data, "player")
    assert data == before
    cases.append("repeated_recalculation_does_not_stack_penalty")
    actor["base_stats"]["str"] += 1
    module.recalculate(data, "player")
    assert actor["temporary_modifiers"]["spd"] == -5 and actor["effective_stats"]["spd"] == 1
    cases.append("strength_growth_restores_correct_spd")
    actor["base_stats"]["str"] = 1
    module.recalculate(data, "player")
    assert actor["encumbrance"]["raw_penalty"] == 13 and actor["encumbrance"]["applied_penalty"] == 6
    assert actor["temporary_modifiers"]["spd"] == -6 and actor["effective_stats"]["spd"] == 0
    cases.append("raw_penalty_capped_at_available_spd")
    actor["base_stats"]["spd"] = 10
    module.recalculate(data, "player")
    assert actor["encumbrance"]["applied_penalty"] == 10 and actor["effective_stats"]["spd"] == 0
    cases.append("spd_growth_recomputes_floor_cap")
    for key in module.SLOTS:
        actor["equipment"][key] = None
    for instance in data["item_instances"]:
        instance.update(location="bag", owner_character_id=None)
    module.recalculate(data, "player")
    assert actor["effective_stats"]["spd"] == 10 and actor["temporary_modifiers"]["spd"] == 0
    cases.append("unequipping_removes_previous_penalty_once")
    data = fixture()
    actor = data["player"]
    actor["base_stats"].update(str=9, spd=8)
    actor["temporary_modifiers"].update(spd=-2, int=1)
    lp, mp = copy.deepcopy(actor["lp"]), copy.deepcopy(actor["mp"])
    module.recalculate(data, "player")
    assert actor["temporary_modifiers"]["spd"] == -7 and actor["effective_stats"]["spd"] == 1
    assert module.preview(data, "player")["raw_spd_bonus"] == -2
    actor["base_stats"]["str"] += 2
    module.recalculate(data, "player")
    assert actor["temporary_modifiers"]["spd"] == -5 and actor["effective_stats"]["spd"] == 3
    assert actor["temporary_modifiers"]["int"] == 1 and actor["lp"] == lp and actor["mp"] == mp
    cases.append("other_modifiers_and_resources_are_preserved")
    errors = []
    module.validate_state(data, errors)
    assert not errors, errors
    cases.append("valid_optional_record_passes")
    for key, value in (("total_weight", 100), ("raw_penalty", 100), ("applied_penalty", 0)):
        bad = copy.deepcopy(data)
        bad["player"]["encumbrance"][key] = value
        errors = []
        module.validate_state(bad, errors)
        assert errors, key + " record forgery passed"
    cases.append("forged_record_rejected")
    bad = copy.deepcopy(data)
    bad["player"]["stats"]["spd"] += 1
    errors = []
    module.validate_state(bad, errors)
    assert errors
    cases.append("stale_spd_mirror_rejected")
    data = fixture()
    for instance in data["item_instances"]:
        instance["specification_snapshot"].pop("weight")
    before = copy.deepcopy(data)
    assert module.preview(data, "player")["total_weight"] == 14 and data == before
    cases.append("typed_definition_fallback_is_read_only")
    data = fixture()
    data["item_instances"][0]["specification_snapshot"].pop("weight")
    data["item_definitions"][0]["specification"].pop("weight")
    before = copy.deepcopy(data)
    unknown = module.preview(data, "player", require_weights=False)
    assert not unknown["weights_known"] and unknown["total_weight"] is None
    assert unknown["missing_instance_ids"] == ["weapon"]
    module.recalculate(data, "player", require_weights=False)
    errors = []
    module.validate_state(data, errors)
    assert data == before and not errors
    cases.append("untracked_legacy_unknown_weight_stays_unchanged")
    reject("str_or_spd_edit_requires_typed_weight", data)
    for value in (None, True, 1.5, -1, "7"):
        data = fixture()
        data["item_instances"][0]["specification_snapshot"]["weight"] = value
        reject("invalid_weight_type_" + str(value), data)
    data = fixture()
    data["item_definitions"][0]["specification"]["weight"] = 8
    reject("snapshot_definition_weight_conflict", data)
    data = fixture()
    data["player"]["equipment"]["armor_instance_id"] = "weapon"
    reject("same_instance_not_counted_twice", data)
    data = fixture()
    data["item_instances"].append(copy.deepcopy(data["item_instances"][0]))
    reject("duplicate_equipped_instance_id", data)
    data = fixture()
    data["item_definitions"].append(copy.deepcopy(data["item_definitions"][0]))
    reject("duplicate_equipped_definition_id", data)
    data = fixture()
    data["item_instances"][0]["owner_character_id"] = "someone-else"
    reject("equipped_owner_must_match", data)
    data = fixture()
    data["item_instances"].append({"instance_id": "bag-heavy", "item_def_id": "bag-heavy-def", "location": "bag",
                                   "specification_snapshot": {"weight": 999}})
    assert module.preview(data, "player")["total_weight"] == 14
    cases.append("carried_or_warehouse_items_not_equipped_weight")
    companion = copy.deepcopy(data["player"])
    companion["character_id"] = "companion"
    companion["equipment"] = {key: None for key in module.SLOTS}
    data["party"] = [companion]
    assert module.preview(data, "player")["total_weight"] == 14
    cases.append("duplicate_display_names_use_stable_id")
    companion["character_id"] = "player"
    reject("duplicate_actor_id_rejected", data)
    data = fixture()
    data["player"]["base_stats"]["int"] = "bad"
    reject("failed_recalculation_is_atomic", data, recalc=True)
    cases.extend(runtime_integration(root))
    return {"ok": True, "cases": len(cases), "case_ids": cases, "read_only_source": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    try:
        result = check(parser.parse_args().root.resolve())
    except (AssertionError, ValueError, OSError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
