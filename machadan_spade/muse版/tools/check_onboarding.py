#!/usr/bin/env python3
"""Test the one-time fire grant and legacy repair only in a disposable game."""
from __future__ import annotations
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
sys.dont_write_bytecode = True


def check(root):
    cases = []
    with tempfile.TemporaryDirectory(prefix="machadan-onboarding-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"), copy_function=shutil.copyfile)
        for name in ("VERSION.txt", "RUNTIME_MANIFEST.json"):
            shutil.copyfile(root.parent / name, game / name)
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("onboarding_probe_runtime", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        import onboarding as ob
        save = clone / "saves/probe.yaml"
        api.cmd_new_save(SimpleNamespace(output=str(save), campaign_id="fire-probe", force=False))
        fresh = api.load_yaml(save)

        def write(value):
            errors, _ = api.validate_save_data(value)
            assert not errors, errors
            api.atomic_write(save, api.dump_yaml(value))

        def reject(call):
            before = save.read_bytes()
            try:
                call()
                raise AssertionError("invalid grant accepted")
            except api.RuntimeProblem:
                assert save.read_bytes() == before

        assert ob.status_data(fresh)["next_stage"] == "hearing"
        assert ob.status_data(fresh)["allocation_budget"] == {"minimum": 3, "bonus_points": 15,
            "total": 33, "base_lp": 20, "rule": ob.CURRENT_RULE, "legacy": False}
        base = copy.deepcopy(fresh)
        base["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        base["play_mode"], base["ero_style"], base["player_body"] = "RP", "machadan", "標準"
        base["partner_pref"]["asked"] = True
        base["player"].update(name="Probe", gender="male", age=40)
        assert ob.status_data(base)["next_stage"] == "rebirth"
        born = copy.deepcopy(base)
        player = born["player"]
        player["base_stats"] = {key: 3 for key in ob.STATS}
        player["base_lp"] = 20
        player["effective_stats"] = copy.deepcopy(player["base_stats"])
        player["stats"] = copy.deepcopy(player["effective_stats"])
        player["lp"], player["mp"] = {"cur": 20, "max": 20}, {"cur": 3, "max": 3}
        assert ob.status_data(born)["next_stage"] == "fire"
        cases.append("ordered_hearing_rebirth_fire_before_allocation")
        write(born)
        early_args=SimpleNamespace(save=str(save),output=str(clone/'state/runtime/fire-before-points.yaml'),transaction_id='fire-before-points')
        ob.grant(api,early_args)
        early=api.load_yaml(Path(early_args.output))
        assert early['player']['base_stats']==born['player']['base_stats']
        assert early['player']['effective_stats']=={key:6 for key in ob.STATS}
        assert early['player']['lp']=={'cur':32,'max':32} and early['player']['mp']=={'cur':6,'max':6}
        assert early['world_state']['onboarding']['allocation_complete'] is False
        assert 'initial_base_stats' not in early['world_state']['onboarding']
        assert ob.status_data(early)['next_stage']=='bonus'
        assert not ob.validate_transition(api,born,early,'fire-before-points')
        api.cmd_commit_save(SimpleNamespace(current=str(save),candidate=early_args.output,transaction_id='fire-before-points',turn=0,keep=50))
        cases.append('unallocated_body_receives_exact_fire_without_spending_points')
        repeat_args=SimpleNamespace(save=str(save),output=str(clone/'state/runtime/early-explanation.yaml'),transaction_id='early-explanation')
        ob.grant(api,repeat_args)
        assert api.load_yaml(Path(repeat_args.output))['player']==early['player']
        cases.append('fire_before_points_is_idempotent_and_resumable')
        allocated = copy.deepcopy(born)
        player = allocated["player"]
        player["base_stats"] = dict(zip(ob.STATS, (8, 7, 3, 5, 7, 3)))
        player["effective_stats"] = copy.deepcopy(player["base_stats"])
        player["stats"] = copy.deepcopy(player["base_stats"])
        player["lp"]["cur"], player["mp"]["cur"] = 17, 1
        allocated["world_state"]["campaign_lore"]["unchanged"] = {"fact": "previous promise"}
        allocated["custom_test_field"] = {"keep": [1, 2, 3]}
        write(allocated)
        before = save.read_bytes()
        output = clone / "state/runtime/fire-one.yaml"
        args = SimpleNamespace(save=str(save), output=str(output), transaction_id="fire-one")
        first = ob.grant(api, args)
        candidate = api.load_yaml(output)
        assert save.read_bytes() == before
        assert candidate["fire_state"]["holders"] == [player["character_id"]]
        actor = candidate["player"]
        assert actor["fire_bonus"] == {key: 3 for key in ob.STATS}
        assert actor["lp"] == {"cur": 29, "max": 32}
        assert actor["mp"] == {"cur": 4, "max": 6}
        assert candidate["world_state"]["campaign_lore"] == allocated["world_state"]["campaign_lore"]
        assert candidate["custom_test_field"] == allocated["custom_test_field"]
        assert first["next_stage"] == "tutorial"
        cases.append("new_grant_deltas_and_read_only_source")
        exact = output.read_bytes()
        assert ob.grant(api, args)["idempotent"] and output.read_bytes() == exact
        cases.append("same_candidate_retry")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=str(output), transaction_id="fire-one", turn=0, keep=50))
        committed = save.read_bytes()
        assert ob.grant(api, args)["idempotent"] and save.read_bytes() == committed
        cases.append("committed_grant_retry")
        already = ob.grant(api, SimpleNamespace(save=str(save), output=str(output.with_name("explained-again.yaml")), transaction_id="fire-again"))
        repeated = api.load_yaml(Path(already["output"]))
        current = api.load_yaml(save)
        assert repeated["player"] == current["player"]
        assert repeated["fire_state"] == current["fire_state"]
        cases.append("already_granted_no_second_bonus")

        wrong = copy.deepcopy(allocated)
        wrong["player"]["base_stats"]["str"] -= 1
        wrong["player"]["effective_stats"]["str"] -= 1
        wrong["player"]["stats"]["str"] -= 1
        write(wrong)
        reject(lambda: ob.grant(api, args))
        cases.append("invalid_initial_allocation_rejected")
        write(allocated)
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(save), transaction_id="alias")))
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(clone / "tools/new.py"), transaction_id="source-path")))
        cases.append("output_alias_and_source_path_rejected")

        legacy = copy.deepcopy(candidate)
        legacy["world_state"].pop("onboarding")
        legacy["active_script"].update(id="SCRIPT_MILKA_WORLD_BRIEFING", status="in_progress", checkpoint="half-way")
        write(legacy)
        assert ob.status(api, SimpleNamespace(save=str(save)))["needs_explanation"]
        legacy_args = SimpleNamespace(save=str(save), output=str(output.with_name("legacy.yaml")), transaction_id="legacy-explain")
        ob.grant(api, legacy_args)
        explained = api.load_yaml(Path(legacy_args.output))
        assert explained["player"] == legacy["player"]
        assert explained["active_script"] == legacy["active_script"]
        cases.append("legacy_explanation_preserves_resources_and_other_script")

        pair = copy.deepcopy(allocated)
        companion = copy.deepcopy(pair["player"])
        companion.update(character_id="companion-one", name="Companion")
        companion["fire_bonus"] = {key: 3 for key in ob.STATS}
        companion["fire_lp_bonus"] = 12
        companion["effective_stats"] = {key: companion["base_stats"][key] + 3 for key in ob.STATS}
        companion["stats"] = copy.deepcopy(companion["effective_stats"])
        companion["lp"], companion["mp"] = {"cur": 30, "max": 32}, {"cur": 4, "max": 6}
        pair["party"] = [companion]
        pair["fire_state"]["holders"] = ["Companion"]  # legacy-name ownership is kept
        write(pair)
        pair_args = SimpleNamespace(save=str(save), output=str(output.with_name("pair.yaml")), transaction_id="pair-grant")
        ob.grant(api, pair_args)
        paired = api.load_yaml(Path(pair_args.output))
        assert paired["player"]["fire_bonus"]["str"] == 2 and paired["player"]["lp"] == {"cur": 25, "max": 28}
        assert paired["party"][0]["lp"] == {"cur": 26, "max": 28}
        assert paired["fire_state"]["holders"] == ["Companion", player["character_id"]]
        cases.append("two_accompanying_holders_recomputed_once")
        active = copy.deepcopy(pair)
        active["world_state"]["expedition_state"].update(active=True, expedition_id="exp-one", kind="other", fire_holders=["Companion"])
        write(active)
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(output.with_name("active-new.yaml")), transaction_id="active-new")))
        cases.append("new_ownership_during_expedition_rejected")

        active_held = copy.deepcopy(legacy)
        active_held["fire_state"]["holders"] = ["Probe"]
        active_held["world_state"]["expedition_state"].update(active=True, expedition_id="exp-two", kind="other", fire_holders=["Probe"])
        write(active_held)
        active_args = SimpleNamespace(save=str(save), output=str(output.with_name("active-explain.yaml")), transaction_id="active-explain")
        active_result = ob.grant(api, active_args)
        active_candidate = api.load_yaml(Path(active_args.output))
        assert active_result["expedition_bonus_reconciliation_deferred"]
        assert active_candidate["player"] == active_held["player"]
        assert active_candidate["world_state"]["expedition_state"] == active_held["world_state"]["expedition_state"]
        cases.append("active_legacy_explanation_preserves_snapshot")

        mature = copy.deepcopy(allocated)
        mature["world_state"]["onboarding"].pop("allocation_rule", None)
        mature["transaction"]["last_committed_turn"] = 10
        mature["player"]["base_stats"]["str"] += 5
        mature["player"]["effective_stats"]["str"] += 5
        mature["player"]["stats"]["str"] += 5
        write(mature)
        late_args = SimpleNamespace(save=str(save), output=str(output.with_name("mature.yaml")), transaction_id="mature-grant")
        ob.grant(api, late_args)
        late = api.load_yaml(Path(late_args.output))
        assert late["player"]["base_stats"] == mature["player"]["base_stats"]
        assert "initial_base_stats" not in late["world_state"]["onboarding"]
        cases.append("grown_legacy_budget_not_reset")
        transferred = copy.deepcopy(paired)
        transferred["fire_state"]["holders"] = ["Companion"]
        transferred["player"]["fire_bonus"] = {key: 0 for key in ob.STATS}
        transferred["player"]["fire_lp_bonus"] = 0
        transferred["player"]["effective_stats"] = copy.deepcopy(transferred["player"]["base_stats"])
        transferred["player"]["stats"] = copy.deepcopy(transferred["player"]["base_stats"])
        transferred["player"]["lp"], transferred["player"]["mp"] = {"cur": 17, "max": 20}, {"cur": 1, "max": 3}
        transferred["world_state"]["onboarding"]["fire_explained"] = False
        write(transferred)
        transferred_args = SimpleNamespace(save=str(save), output=str(output.with_name("transferred.yaml")), transaction_id="transferred-explain")
        ob.grant(api, transferred_args)
        assert api.load_yaml(Path(transferred_args.output))["fire_state"]["holders"] == ["Companion"]
        cases.append("historical_grant_does_not_regive_transferred_fire")

        malformed = copy.deepcopy(candidate)
        malformed["world_state"]["onboarding"]["initial_base_stats"]["str"] += 1
        errors = []
        ob.validate_onboarding(malformed, errors)
        assert errors
        cases.append("initial_receipt_budget_checked")

        assert not ob.validate_transition(api, allocated, candidate, "fire-one")
        cases.append("initial_grant_transition_accepted")
        for key in ("fire_granted", "fire_explained"):
            regressed = copy.deepcopy(candidate)
            regressed["world_state"]["onboarding"][key] = False
            assert ob.validate_transition(api, candidate, regressed, "regress")
        cases.append("grant_and_explanation_history_cannot_rewind")
        for key, value in (("fire_grant_transaction_id", "rewritten"), ("initial_base_stats", {key: 5 for key in ob.STATS})):
            rewritten = copy.deepcopy(candidate)
            rewritten["world_state"]["onboarding"][key] = value
            assert ob.validate_transition(api, candidate, rewritten, "rewrite")
        cases.append("grant_receipt_and_allocation_snapshot_immutable")
        ownerless = copy.deepcopy(candidate)
        ownerless["fire_state"]["holders"] = []
        assert ob.validate_transition(api, allocated, ownerless, "fire-one")
        assert ob.validate_transition(api, allocated, candidate, "wrong-transaction")
        cases.append("ownership_and_current_grant_transaction_required")
        bad_initial = copy.deepcopy(candidate)
        bad_initial["player"]["base_stats"]["str"] -= 1
        assert ob.validate_transition(api, allocated, bad_initial, "fire-one")
        cases.append("new_grant_budget_checked_at_commit")
        tutorial_without_fire = copy.deepcopy(allocated)
        tutorial_without_fire["world_state"]["onboarding"] = {"tutorial_complete": True}
        assert ob.validate_transition(api, allocated, tutorial_without_fire, "premature-tutorial")
        cases.append("tutorial_cannot_skip_fire_explanation")
        old_without_flags = copy.deepcopy(allocated)
        old_without_flags["world_state"].pop("onboarding", None)
        later_without_flags = copy.deepcopy(old_without_flags)
        later_without_flags["world_state"]["campaign_lore"]["normal"] = "normal legacy play"
        assert not ob.validate_transition(api, old_without_flags, later_without_flags, "legacy-play")
        transferred_recorded = copy.deepcopy(candidate)
        transferred_recorded["fire_state"]["holders"] = []
        ob._apply_fire(transferred_recorded["player"], 0, False)
        assert not ob.validate_transition(api, candidate, transferred_recorded, "later-transfer")
        cases.append("legacy_play_and_later_transfer_remain_legal")
        id_expedition = copy.deepcopy(candidate)
        id_expedition["world_state"]["expedition_state"].update(active=True, expedition_id="new-id-expedition", kind="other", fire_holders=[candidate["player"]["character_id"]])
        expedition_errors, _ = api.validate_save_data(id_expedition)
        assert not expedition_errors, expedition_errors
        cases.append("new_grant_character_id_enters_expedition")

        ambiguous = copy.deepcopy(allocated)
        same_name_member = copy.deepcopy(ambiguous["player"])
        same_name_member["character_id"] = "other-same-name"
        ambiguous["player"]["name"] = same_name_member["name"] = "SameName"
        ambiguous["party"] = [same_name_member]
        ambiguous["fire_state"]["holders"] = ["SameName"]
        write(ambiguous)
        ambiguous_status = ob.status(api, SimpleNamespace(save=str(save)))
        assert not ambiguous_status["ok"] and ambiguous_status["requires_identity_review"]
        assert not ambiguous_status["currently_holds_fire"] and not ambiguous_status["needs_grant"]
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(output.with_name("ambiguous.yaml")), transaction_id="ambiguous")))
        cases.append("ambiguous_legacy_name_never_grants_two_people")

        id_collision = copy.deepcopy(allocated)
        other = copy.deepcopy(id_collision["player"])
        other["character_id"] = "other-colliding-name"
        other["name"] = id_collision["player"]["character_id"]
        id_collision["party"] = [other]
        id_collision["fire_state"]["holders"] = [id_collision["player"]["character_id"]]
        write(id_collision)
        assert ob.status(api, SimpleNamespace(save=str(save)))["currently_holds_fire"]
        collision_args = SimpleNamespace(save=str(save), output=str(output.with_name("id-collision.yaml")), transaction_id="id-collision")
        ob.grant(api, collision_args)
        collision_result = api.load_yaml(Path(collision_args.output))
        assert collision_result["player"]["fire_bonus"]["str"] == 3
        assert collision_result["party"][0]["fire_bonus"]["str"] == 0
        cases.append("exact_id_wins_over_another_persons_display_name")

        # Existing points are never subtracted when ALL3 becomes the new rule.
        old45 = copy.deepcopy(allocated)
        old45["world_state"]["onboarding"].pop("allocation_rule", None)
        old45["player"]["base_stats"] = dict(zip(ob.STATS, (10, 9, 5, 7, 9, 5)))
        old45["player"]["effective_stats"] = copy.deepcopy(old45["player"]["base_stats"])
        old45["player"]["stats"] = copy.deepcopy(old45["player"]["base_stats"])
        old45["player"]["mp"] = {"cur": 3, "max": 5}
        write(old45)
        old45_status = ob.status(api, SimpleNamespace(save=str(save)))
        assert old45_status["allocation_rule"] == ob.LEGACY_RULE
        assert old45_status["allocation_total"] == 45 and old45_status["legacy_initial_allocation"]
        assert old45_status["allocation_budget"] == {"minimum": 5, "bonus_points": 15,
            "total": 45, "base_lp": 20, "rule": ob.LEGACY_RULE, "legacy": True}
        old45_args = SimpleNamespace(save=str(save), output=str(output.with_name("legacy45.yaml")), transaction_id="legacy45-grant")
        ob.grant(api, old45_args)
        old45_granted = api.load_yaml(Path(old45_args.output))
        assert old45_granted["player"]["base_stats"] == old45["player"]["base_stats"]
        assert old45_granted["world_state"]["onboarding"]["initial_base_stats"] == old45["player"]["base_stats"]
        assert old45_granted["world_state"]["onboarding"]["legacy_initial_allocation"] is True
        assert not ob.validate_transition(api, old45, old45_granted, "legacy45-grant")
        cases.append("untagged_legacy45_grandfathered_without_subtracting_points")

        old_partial = copy.deepcopy(old45)
        old_partial["player"]["base_stats"] = {key: 5 for key in ob.STATS}
        old_partial["player"]["effective_stats"] = copy.deepcopy(old_partial["player"]["base_stats"])
        old_partial["player"]["stats"] = copy.deepcopy(old_partial["player"]["base_stats"])
        old_partial_status = ob.status_data(old_partial)
        assert old_partial_status["next_stage"] == "bonus"
        assert old_partial_status["allocation_minimum"] == 5 and old_partial_status["allocation_total"] == 45
        cases.append("untagged_partial_all5_keeps_original_budget")

        old_receipt = copy.deepcopy(old45_granted)
        old_receipt["world_state"]["onboarding"].pop("allocation_rule")
        old_receipt["world_state"]["onboarding"].pop("legacy_initial_allocation")
        write(old_receipt)
        old_receipt_errors = []
        ob.validate_onboarding(old_receipt, old_receipt_errors)
        assert not old_receipt_errors
        assert ob.status_data(old_receipt)["already_granted"]
        assert ob.status_data(old_receipt)["allocation_rule"] == ob.LEGACY_RULE
        cases.append("existing45_grant_receipt_stays_valid")

        wrong_new_budget = copy.deepcopy(old45)
        wrong_new_budget["world_state"]["onboarding"]["allocation_rule"] = ob.CURRENT_RULE
        write(wrong_new_budget)
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(output.with_name("wrong-new-budget.yaml")), transaction_id="wrong-new-budget")))
        cases.append("explicit_new33_rule_rejects_45_points")

        unknown_origin = copy.deepcopy(mature)
        unknown_origin["world_state"]["onboarding"].pop("allocation_rule", None)
        write(unknown_origin)
        assert ob.status_data(unknown_origin)["allocation_rule"] == ob.UNKNOWN_LEGACY_RULE
        assert ob.status_data(unknown_origin)["allocation_budget"]["total"] is None
        unknown_args = SimpleNamespace(save=str(save), output=str(output.with_name("unknown-origin.yaml")), transaction_id="unknown-origin")
        ob.grant(api, unknown_args)
        unknown_result = api.load_yaml(Path(unknown_args.output))
        assert unknown_result["player"]["base_stats"] == unknown_origin["player"]["base_stats"]
        assert "initial_base_stats" not in unknown_result["world_state"]["onboarding"]
        cases.append("grown_unknown_origin_preserved_without_fabricated_budget")

        wrong_rule = copy.deepcopy(candidate)
        wrong_rule["world_state"]["onboarding"]["allocation_rule"] = ob.LEGACY_RULE
        assert ob.validate_transition(api, candidate, wrong_rule, "change-rules")
        cases.append("committed_initial_rules_cannot_be_rewritten")

        built33 = copy.deepcopy(allocated)
        built33["player"].update(build_complete=True, job="戦士", job_lp_bonus=10)
        built33["player"]["job_profile"].update(combat_role="frontline", magic_role="noncaster", solo_suitability="good")
        built33["player"]["lp"] = {"cur": 27, "max": 30}
        write(built33)
        built33_args = SimpleNamespace(save=str(save), output=str(output.with_name("built33.yaml")), transaction_id="built33")
        ob.grant(api, built33_args)
        built33_candidate = api.load_yaml(Path(built33_args.output))
        assert built33_candidate["player"]["lp"] == {"cur": 39, "max": 42}
        assert sum(built33_candidate["world_state"]["onboarding"]["initial_base_stats"].values()) == 33
        assert not ob.validate_transition(api, built33, built33_candidate, "built33")
        cases.append("valid_new33_job_build_gets_initial_receipt")

        built45 = copy.deepcopy(built33)
        built45["player"]["base_stats"] = copy.deepcopy(old45["player"]["base_stats"])
        built45["player"]["effective_stats"] = copy.deepcopy(built45["player"]["base_stats"])
        built45["player"]["stats"] = copy.deepcopy(built45["player"]["base_stats"])
        built45["player"]["mp"] = {"cur": 3, "max": 5}
        write(built45)
        assert ob.status_data(built45)["next_stage"] == "fire"
        reject(lambda: ob.grant(api, SimpleNamespace(save=str(save), output=str(output.with_name("built45-invalid.yaml")), transaction_id="built45-invalid")))
        cases.append("new33_cannot_escape_budget_by_selecting_job_first")

        # Initial allocation may already have materialised a weight record.
        # The fire raises both STR and SPD; don't retain its old weight loss.
        from encumbrance import recalculate
        equipped = copy.deepcopy(allocated)
        equipped["item_definitions"].append({"item_def_id": "weight-def", "name": "Weight Probe", "category": "equipment",
            "specification": {"weight": 12}, "provenance": {}, "balance_anchor": {}})
        equipped["item_instances"].append({"instance_id": "weight-instance", "item_def_id": "weight-def", "name": "Weight Probe",
            "location": "equipped", "slot_cost": 0, "owner_character_id": equipped["player"]["character_id"], "specification_snapshot": {"weight": 12}})
        equipped["player"]["equipment"]["armor_instance_id"] = "weight-instance"
        recalculate(equipped, equipped["player"]["character_id"])
        assert equipped["player"]["encumbrance"]["applied_penalty"] == 4
        assert equipped["player"]["effective_stats"]["spd"] == 1
        write(equipped)
        tracked_args = SimpleNamespace(save=str(save), output=str(output.with_name("tracked-fire.yaml")), transaction_id="tracked-fire")
        source_bytes = save.read_bytes()
        tracked_result = ob.grant(api, tracked_args)
        tracked = api.load_yaml(Path(tracked_args.output))
        assert save.read_bytes() == source_bytes
        assert tracked["player"]["encumbrance"] == {"version": 1, "total_weight": 12, "raw_penalty": 1, "applied_penalty": 1}
        assert tracked["player"]["effective_stats"]["spd"] == tracked["player"]["stats"]["spd"] == 7
        assert tracked["player"]["temporary_modifiers"]["spd"] == -1
        assert tracked["player"]["lp"] == {"cur": 29, "max": 32}
        assert tracked["player"]["mp"] == {"cur": 4, "max": 6}
        assert tracked_result["deltas"][0]["after"]["effective_stats"]["spd"] == 7
        cases.append("tracked_equipped_fire_recomputes_weight_without_extra_resource_recovery")
        tracked_bytes = Path(tracked_args.output).read_bytes()
        assert ob.grant(api, tracked_args)["idempotent"]
        assert Path(tracked_args.output).read_bytes() == tracked_bytes and save.read_bytes() == source_bytes
        cases.append("tracked_fire_candidate_retry_does_not_stack_weight_or_bonus")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=tracked_args.output, transaction_id="tracked-fire", turn=0, keep=50))
        committed_tracked = save.read_bytes()
        assert ob.grant(api, tracked_args)["idempotent"] and save.read_bytes() == committed_tracked
        cases.append("tracked_fire_committed_retry_is_idempotent")
        return {"ok": True, "cases": len(cases), "case_ids": cases, "source_mutated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(check(parser.parse_args().root.resolve()), ensure_ascii=False))
