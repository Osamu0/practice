#!/usr/bin/env python3
"""Read-only capacity tests plus isolated ordinary-turn integration."""
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


def integration(root):
    cases = []
    with tempfile.TemporaryDirectory(prefix="machadan-resource-flow-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root.parent, game, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"))
        manifest_path = game / "RUNTIME_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["version"] = re.search(r"(?im)^version:\s*(\S.*)$", (game / "VERSION.txt").read_text()).group(1).strip()
        # Fixture metadata is rebuilt only inside this disposable copy.
        manifest["files"] = [{"path": path.relative_to(game).as_posix(), "size": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in sorted(game.rglob("*")) if path.is_file() and path != manifest_path]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("machadan_resource_flow_probe", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        parser = api.build_parser()

        def command(*arguments):
            args = parser.parse_args(list(map(str, arguments)))
            result = args.handler(args)
            if isinstance(result, tuple):
                if result[0]:
                    raise api.RuntimeProblem(str(result[1]))
                return result[1]
            return result

        import encumbrance
        import resource_math
        save = clone / "saves/resource-flow.yaml"
        command("new-save", "--campaign-id", "resource-flow", "--output", save)
        data = api.load_yaml(save)
        actor = data["player"]
        base = dict(zip(api.STAT_KEYS, (8, 5, 5, 5, 5, 5)))
        actor.update(name="Resource Probe", age=30, gender="male", job="旅人", build_complete=True,
                     base_stats=base, fire_bonus={key: 3 for key in base}, fire_lp_bonus=12,
                     effective_stats={key: base[key] + 3 for key in base}, stats={key: base[key] + 3 for key in base},
                     base_lp=26, lp={"cur": 17, "max": 38}, mp={"cur": 3, "max": 8})
        data["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        data.update(play_mode="RP", ero_style="machadan", player_body="標準")
        data["partner_pref"]["asked"] = True
        data["world_state"].update(location="ギルド", time_of_day="朝")
        data["world_state"]["onboarding"].update(allocation_rule="all3-plus15-v1", body_received=True,
            allocation_complete=True, fire_granted=True, fire_explained=True, tutorial_complete=True,
            initial_base_stats=copy.deepcopy(base), fire_grant_transaction_id="fixture-resource-fire")
        data["fire_state"]["holders"] = [actor["character_id"]]
        encumbrance.recalculate(data, actor["character_id"])
        resource_math.recalculate(actor, track=True)
        assert actor["stat_lp_bonus"] == 1 and actor["lp"] == {"cur": 17, "max": 39}
        errors, _ = api.validate_save_data(data)
        assert not errors, errors
        api.atomic_write(save, api.dump_yaml(data))
        inventory_before = copy.deepcopy(data["inventory"])
        acquisition_before = copy.deepcopy(data["world_state"]["growth_state"])
        serial = 0

        def turn(operations, rejected=False):
            nonlocal serial
            serial += 1
            context = clone / f"state/runtime/resource-{serial}.md"
            prepared = clone / f"state/runtime/resource-{serial}.prepared.yaml"
            final = clone / f"state/runtime/resource-{serial}.final.yaml"
            command("prepare-context", "--save", save, "--scene", "turn", "--output", context,
                    "--candidate-save-output", prepared)
            changes = prepared.with_suffix(".changes.json")
            payload = json.loads(changes.read_text())
            payload["operations"] = operations
            changes.write_text(json.dumps(payload, ensure_ascii=False))
            before = save.read_bytes()
            try:
                command("apply-changes", "--current", save, "--prepared", prepared, "--changes", changes, "--output", final)
            except api.RuntimeProblem:
                assert rejected and save.read_bytes() == before
                return None
            assert not rejected, "invalid resource change was accepted"
            assert save.read_bytes() == before, "candidate creation wrote the live save"
            candidate = api.load_yaml(final)
            assert candidate["player"]["lp"]["cur"] == 17
            assert candidate["player"]["mp"] == {"cur": 3, "max": 8}
            assert candidate["player"]["base_lp"] == 26
            target_turn = api.load_yaml(save)["transaction"]["last_committed_turn"] + 1
            command("commit-save", "--current", save, "--candidate", final,
                    "--transaction-id", "resource-flow-" + str(serial), "--turn", target_turn)
            return api.load_yaml(save)

        grown = turn([{"op": "replace", "path": "/player/growth_bonus/def", "value": 2}])
        assert grown["player"]["stat_lp_bonus"] == 2 and grown["player"]["lp"]["max"] == 40
        assert grown["inventory"] == inventory_before and grown["world_state"]["growth_state"] == acquisition_before
        cases.append("ordinary_event_def_growth_updates_capacity_without_fruit_use")
        repeated = turn([{"op": "add", "path": "/world_state/campaign_lore/resource-probe", "value": {"fact": "ordinary follow-up"}}])
        assert repeated["player"]["stat_lp_bonus"] == 2 and repeated["player"]["lp"]["max"] == 40
        cases.append("ordinary_followup_does_not_double_stat_bonus")
        frontline = turn([{"op": "replace", "path": "/player/job_lp_bonus", "value": 10},
                          {"op": "replace", "path": "/player/job", "value": "戦士"}])
        assert frontline["player"]["lp"]["max"] == 50
        cases.append("ordinary_job_bonus_changes_capacity_without_healing_or_losing_lp_fruit")
        noncombat = turn([{"op": "replace", "path": "/player/job_lp_bonus", "value": 0},
                         {"op": "replace", "path": "/player/job", "value": "旅人"}])
        assert noncombat["player"]["lp"]["max"] == 40
        cases.append("ordinary_role_change_preserves_base_lp_growth")
        turn([{"op": "replace", "path": "/player/base_lp", "value": -1}], rejected=True)
        cases.append("ordinary_negative_base_lp_rejected_before_commit")
    return cases


def check(root):
    spec = importlib.util.spec_from_file_location("machadan_resource_math_probe", root / "tools/resource_math.py")
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    cases = []

    def actor(defence=5, growth=0, tracked=True):
        result = {"base_stats": {"def": defence}, "growth_bonus": {"def": growth},
                  "equipment_bonus": {"def": 100}, "fire_bonus": {"def": 3}, "temporary_modifiers": {"def": 7},
                  "effective_stats": {"def": defence + growth + 110, "int": 10},
                  "base_lp": 26, "job_lp_bonus": 10, "fire_lp_bonus": 12, "temporary_lp_bonus": 0,
                  "lp": {"cur": 17, "max": 48}, "mp": {"cur": 3, "max": 10}}
        if tracked:
            result["stat_lp_bonus"] = rm.stat_lp_bonus(result)
        return result

    for defence, expected in ((3, 0), (4, 0), (5, 1), (6, 1), (7, 2), (18, 7)):
        sample = actor(defence)
        assert rm.stat_lp_bonus(sample) == expected
        rm.recalculate(sample)
        assert sample["lp"] == {"cur": 17, "max": 48 + expected}
        cases.append("permanent_def_milestone_" + str(defence))
    sample = actor(3, 0)
    assert sample["effective_stats"]["def"] == 113 and rm.stat_lp_bonus(sample) == 0
    sample["growth_bonus"]["def"] = 2
    assert rm.stat_lp_bonus(sample) == 1
    cases.append("equipment_fire_and_temporary_def_do_not_increase_stat_lp")
    sample = actor(5)
    rm.recalculate(sample)
    before = copy.deepcopy(sample)
    rm.recalculate(sample)
    assert sample == before
    cases.append("stat_bonus_is_derived_not_accumulated")
    # The already earned +6 is Base LP, not redistributable initial points.
    sample["base_stats"]["def"] = 7
    rm.recalculate(sample)
    assert sample["base_lp"] == 26 and sample["lp"] == {"cur": 17, "max": 50}
    sample["job_lp_bonus"] = 0
    rm.recalculate(sample)
    assert sample["base_lp"] == 26 and sample["lp"] == {"cur": 17, "max": 40}
    sample["job_lp_bonus"] = 10
    rm.recalculate(sample)
    assert sample["base_lp"] == 26 and sample["lp"] == {"cur": 17, "max": 50}
    cases.append("lp_fruit_growth_survives_respec_and_job_roles")
    sample["effective_stats"]["int"] = 20
    rm.recalculate(sample)
    assert sample["mp"] == {"cur": 3, "max": 20}
    cases.append("increased_mp_capacity_does_not_heal")
    sample["effective_stats"]["int"] = 2
    rm.recalculate(sample)
    assert sample["mp"] == {"cur": 2, "max": 2}
    sample["lp"] = {"cur": 40, "max": 50}
    sample["job_lp_bonus"] = sample["fire_lp_bonus"] = 0
    rm.recalculate(sample)
    assert sample["lp"] == {"cur": 28, "max": 28}
    cases.append("decreased_capacity_clamps_current_resources")
    sample["lp"]["cur"] = sample["mp"]["cur"] = 0
    sample["base_lp"] += 6
    sample["effective_stats"]["int"] = 20
    rm.recalculate(sample)
    assert sample["lp"]["cur"] == sample["mp"]["cur"] == 0
    cases.append("capacity_growth_never_resurrects_or_restores_zero")
    rm.recalculate(sample, refill=True)
    assert sample["lp"]["cur"] == sample["lp"]["max"] and sample["mp"]["cur"] == sample["mp"]["max"]
    cases.append("creation_refill_requires_explicit_option")
    legacy = actor(18, tracked=False)
    errors = []
    rm.validate_stat_lp(legacy, "legacy", errors)
    rm.recalculate(legacy)
    assert not errors and "stat_lp_bonus" not in legacy and legacy["lp"]["max"] == 48
    cases.append("untracked_legacy_capacity_contract_is_preserved")
    rm.recalculate(legacy, track=True)
    assert legacy["stat_lp_bonus"] == 7 and legacy["lp"] == {"cur": 17, "max": 55}
    cases.append("explicit_tracking_derives_permanent_def_without_healing")
    for value in (True, -1, 100):
        bad = actor(5)
        bad["stat_lp_bonus"] = value
        errors = []
        rm.validate_stat_lp(bad, "probe", errors)
        assert errors
        cases.append("invalid_stat_lp_cache_" + str(value))
    for group, value in (("base_stats", True), ("base_stats", -1), ("growth_bonus", True), ("growth_bonus", -1)):
        bad = actor(5)
        bad[group]["def"] = value
        try:
            rm.stat_lp_bonus(bad)
            raise AssertionError("invalid permanent DEF accepted")
        except ValueError:
            pass
        cases.append("invalid_def_" + group + "_" + str(value))
    for field, value in (("base_lp", True), ("job_lp_bonus", False)):
        bad = actor()
        bad[field] = value
        try:
            rm.recalculate(bad)
            raise AssertionError("boolean LP component accepted")
        except ValueError:
            pass
        cases.append("boolean_capacity_component_" + field)
    for key, value in (("lp", True), ("lp", -1), ("mp", True), ("mp", -1)):
        bad = actor()
        bad[key]["cur"] = value
        try:
            rm.recalculate(bad)
            raise AssertionError("invalid current resource accepted")
        except ValueError:
            pass
        cases.append("invalid_current_" + key + "_" + str(value))
    for value in (True, -1):
        bad = actor()
        bad["effective_stats"]["int"] = value
        try:
            rm.recalculate(bad)
            raise AssertionError("invalid MP capacity accepted")
        except ValueError:
            pass
        cases.append("invalid_effective_int_" + str(value))
    cases.extend(integration(root))
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
