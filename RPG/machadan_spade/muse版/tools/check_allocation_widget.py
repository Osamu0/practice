#!/usr/bin/env python3
"""Exercise draft allocation, fruit consumption and retraining in an isolated game."""
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
    with tempfile.TemporaryDirectory(prefix="machadan-allocation-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"), copy_function=shutil.copyfile)
        for name in ("VERSION.txt", "RUNTIME_MANIFEST.json"):
            shutil.copyfile(root.parent / name, game / name)
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("allocation_probe_runtime", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        import allocation_widget as aw
        save = clone / "saves/probe.yaml"
        api.cmd_new_save(SimpleNamespace(output=str(save), campaign_id="allocation-probe", force=False))
        fresh = api.load_yaml(save)
        base = copy.deepcopy(fresh)
        base["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        base["play_mode"], base["ero_style"], base["player_body"] = "RP", "machadan", "標準"
        base["partner_pref"]["asked"] = True
        base["world_state"]["onboarding"]["body_received"] = True
        base["world_state"].update(time_of_day="朝", location="ギルド")
        p = base["player"]
        p.update(name="Allocation Probe", age=40, gender="male", base_lp=20)
        p["base_stats"] = {key: 3 for key in aw.STATS}
        aw._recalculate(p)
        p["lp"]["cur"], p["mp"]["cur"] = 17, 2
        base["custom_preserved"] = {"promise": [1, "unchanged"]}

        def write(data):
            errors, _ = api.validate_save_data(data)
            assert not errors, errors
            api.atomic_write(save, api.dump_yaml(data))

        serial = 0
        def render(data, mode="initial", **extra):
            nonlocal serial
            serial += 1
            write(data)
            before = save.read_bytes()
            args = SimpleNamespace(save=str(save), mode=mode, output=str(clone / f"state/runtime/widget-{serial}.html"),
                actor_id=None, stack_id=None, quantity=1, request_id=None, widget_state=None)
            for key, value in extra.items():
                setattr(args, key, value)
            result = aw.render(api, args)
            assert save.read_bytes() == before
            state = json.loads(Path(result["state_path"]).read_text())
            return result, state

        def store(state, name="answer.json"):
            path = clone / "state/runtime" / name
            api.atomic_write(path, json.dumps(state, ensure_ascii=False))
            return path

        def resolve(state, tx="allocation-1", **extra):
            args = SimpleNamespace(save=str(save), widget_state=str(store(state)), confirmation="確定",
                output=str(clone / f"state/runtime/{tx}.yaml"), transaction_id=tx)
            for key, value in extra.items():
                setattr(args, key, value)
            before = save.read_bytes()
            result = aw.resolve(api, args)
            assert save.read_bytes() == before
            return result, api.load_yaml(Path(result["output"]))

        def rejects(name, call):
            before = save.read_bytes()
            try:
                call()
            except api.RuntimeProblem:
                assert save.read_bytes() == before
                cases.append(name)
            else:
                raise AssertionError("invalid allocation accepted: " + name)

        unlit=copy.deepcopy(base)
        write(unlit)
        rejects('initial_widget_waits_for_fire',lambda:render(unlit))
        import onboarding as ob
        write(base)
        granted=ob.grant(api,SimpleNamespace(save=str(save),output=str(clone/'state/runtime/before-allocation-fire.yaml'),transaction_id='allocation-fire'))
        api.cmd_commit_save(SimpleNamespace(current=str(save),candidate=granted['output'],transaction_id='allocation-fire',turn=0,keep=50))
        base=api.load_yaml(save)
        widget, state = render(base)
        assert state["values"] == {key: 3 for key in aw.STATS} and not state["complete"]
        assert "__ALLOCATION_PAYLOAD_JSON__" not in Path(widget["output"]).read_text()
        html = Path(widget["output"]).read_text()
        payload_text = html.split('<script id="allocation-payload" type="application/json">', 1)[1].split('</script>', 1)[0]
        displayed = json.loads(payload_text)
        assert all(field['current'] + field['effective_bonus'] == 6 for field in displayed['fields'])
        assert all(displayed['display_bonus_breakdown'][key]['fire'] == 3 for key in aw.STATS)
        assert displayed['budget']['total'] == 15 and displayed['initial_state']['values'] == state['values']
        cases += ['fire_included_in_display_totals', 'base_draft_and_15_point_budget_unchanged']
        cases.append("render_is_draft_only")
        state["values"]["int"] = 18
        state.update(complete=True, revision=1)
        result, initial = resolve(state)
        assert sum(initial["player"]["base_stats"].values()) == 33
        assert initial["player"]["lp"] == {"cur": 32, "max": 32}
        assert initial["player"]["mp"] == {"cur": 21, "max": 21}
        assert initial['player']['fire_bonus']==base['player']['fire_bonus']
        assert initial['world_state']['onboarding']['initial_base_stats']==initial['player']['base_stats']
        assert ob.status_data(initial)['next_stage']=='tutorial'
        assert initial["custom_preserved"] == base["custom_preserved"]
        assert not aw.validate_transition(api, base, initial, "allocation-1")
        cases.append("initial_candidate_starts_with_full_resources")
        assert resolve(state)[0]["idempotent"]
        cases.append("candidate_retry_is_identical")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=result["output"], transaction_id="allocation-1", turn=0, keep=50))
        assert aw.resolve(api, SimpleNamespace(save=str(save), widget_state=str(store(state)), confirmation="確定",
            output=result["output"], transaction_id="allocation-1"))["idempotent"]
        cases.append("committed_retry_does_not_reapply")
        forged_retry = copy.deepcopy(state)
        forged_retry["actor_id"] = "unknown"
        rejects("committed_retry_still_checks_identity", lambda: resolve(forged_retry))
        rejects("request_cannot_be_used_twice", lambda: resolve(state, "allocation-repeat"))
        write(base)
        bad = copy.deepcopy(state)
        bad["request_id"] = "../../outside"
        rejects("request_path_traversal_is_rejected", lambda: resolve(bad, "traversal"))
        rejects("explicit_chat_confirmation_required", lambda: resolve(state, "no-confirm", confirmation=""))
        rejects("button_or_approximate_confirmation_rejected", lambda: resolve(state, "almost-confirm", confirmation="はい、確定します"))
        for key, value in (("actor_id", "missing-actor"), ("profile_hash", "0" * 64), ("source_revision", 99), ("mode", "respec")):
            bad = copy.deepcopy(state)
            bad[key] = value
            rejects("forged_" + key, lambda bad=bad: resolve(bad, "forged-" + key))
        bad = copy.deepcopy(state)
        bad["source_revision"] = False
        rejects("boolean_source_revision_is_rejected", lambda: resolve(bad, "bool-revision"))
        bad = copy.deepcopy(state)
        bad["values"]["str"] = 2
        rejects("minimum_is_enforced", lambda: resolve(bad, "too-low"))
        bad = copy.deepcopy(state)
        bad["values"]["str"] = 4
        rejects("total_is_enforced", lambda: resolve(bad, "too-many"))
        bad = copy.deepcopy(state)
        bad["values"]["base_lp"] = 20
        rejects("unoffered_field_is_rejected", lambda: resolve(bad, "new-field"))
        changed = copy.deepcopy(base)
        changed["player"]["gold"] = 1
        write(changed)
        rejects("stale_same_revision_source_is_rejected", lambda: resolve(state, "stale"))
        write(base)
        rejects("candidate_live_save_alias_rejected", lambda: resolve(state, "alias", output=str(save)))
        rejects("immutable_package_output_rejected", lambda: resolve(state, "canon", output=str(clone / "世界/Quest_Guild.md")))
        occupied = clone / "state/runtime/occupied.yaml"
        api.atomic_write(occupied, "unrelated file\n")
        rejects("existing_other_candidate_is_not_overwritten", lambda: resolve(state, "occupied", output=str(occupied)))
        assert occupied.read_text() == "unrelated file\n"
        hardlink = clone / "state/runtime/hardlink.yaml"
        import os
        os.link(save, hardlink)
        rejects("hardlink_live_save_alias_rejected", lambda: resolve(state, "hardlink", output=str(hardlink)))
        hardlink.unlink()
        partial = copy.deepcopy(state)
        partial["values"]["int"], partial["complete"], partial["revision"] = 10, False, 7
        reopened, recovered = render(base, request_id=widget["request_id"], widget_state=str(store(partial, "partial.json")))
        assert recovered == partial
        cases.append("partial_draft_reopens_without_spending")
        same_path, same_recovered = render(base, request_id=widget["request_id"],
            widget_state=str(store(partial, "same-path-partial.json")), output=widget["output"])
        assert same_recovered == partial and same_path["output"] == widget["output"]
        cases.append("same_html_path_can_reopen_its_own_draft")
        _, auto_recovered = render(base, request_id=widget["request_id"], output=widget["output"])
        assert auto_recovered == partial
        cases.append("same_request_recovers_its_saved_draft_by_default")
        rollback = copy.deepcopy(partial)
        rollback["revision"] -= 1
        draft_html = Path(widget["output"]).read_bytes()
        rejects("draft_reopen_cannot_roll_back_revision", lambda: render(base,
            request_id=widget["request_id"], widget_state=str(store(rollback, "rollback.json")), output=widget["output"]))
        assert Path(widget["output"]).read_bytes() == draft_html
        later = copy.deepcopy(base)
        later["transaction"]["last_committed_turn"] = 1
        write(later)
        rejects("initial_cannot_reopen_after_adventure_turn", lambda: render(later))
        battle = copy.deepcopy(base)
        battle["runtime_state"]["active_scene"] = "combat"
        write(battle)
        rejects("initial_cannot_run_during_combat", lambda: render(battle))
        named_holder = copy.deepcopy(initial)
        named_holder["fire_state"]["holders"] = [named_holder["player"]["name"]]
        write(named_holder)
        rejects("legacy_named_fire_holder_cannot_restart_creation", lambda: render(named_holder))
        unsafe_name = copy.deepcopy(base)
        unsafe_name["player"]["name"] = "</script><script>unsafe()</script>\u2028"
        escaped, _ = render(unsafe_name)
        html = Path(escaped["output"]).read_text()
        import re
        embedded = re.search(r'<script id="allocation-payload" type="application/json">(.*?)</script>', html, re.S).group(1)
        assert "</script>" not in embedded and "\u2028" not in embedded
        assert json.loads(embedded)["actor_name"] == unsafe_name["player"]["name"]
        cases.append("embedded_json_cannot_close_its_script")
        zero = copy.deepcopy(base)
        zero["player"] = copy.deepcopy(fresh["player"])
        zero["player"].update(name="Zero", age=40, gender="male")
        write(zero)
        rejects('initial_widget_cannot_create_a_body_or_fake_fire',lambda:render(zero))
        _, def_state = render(base)
        def_state["values"]["def"], def_state["complete"] = 18, True
        _, def_initial = resolve(def_state, "initial-high-def")
        assert def_initial["player"]["stat_lp_bonus"] == 7
        assert def_initial["player"]["base_lp"] == 20 and def_initial["player"]["lp"] == {"cur": 39, "max": 39}
        cases.append("high_permanent_def_initializes_derived_lp")
        fallen = copy.deepcopy(base)
        fallen["player"]["lp"]["cur"] = 0
        write(fallen)
        rejects("formed_body_is_not_resurrected", lambda: render(fallen))

        def with_fruit(name="選べる能力の実", count=3, reserved=0):
            data = copy.deepcopy(initial)
            data["world_state"].pop("allocation_state", None)
            # Test ordinary fruit growth after the already-recorded fire was
            # transferred away; the historical grant must remain intact.
            data['fire_state']['holders']=[]
            data['player']['fire_bonus']={key:0 for key in aw.STATS}
            data['player']['fire_lp_bonus']=0
            data["player"]["growth_bonus"]["str"] = 2
            aw._recalculate(data["player"])
            data["item_definitions"] = [{"item_def_id": "fruit-def", "name": name, "category": "consumable", "specification": {}, "provenance": {}, "balance_anchor": {}}]
            data["inventory"]["carried_stacks"] = [{"stack_id": "fruit-stack", "item_def_id": "fruit-def", "name": name,
                "category": "consumable", "count": count, "stack_cap": 10, "slot_cost": 1, "reserved_quantity": reserved}]
            data["inventory"]["bag"]["used_slots"] = 1
            if reserved:
                data["inventory"]["reservations"] = [{"reservation_id": "reserved-fruit", "source_id": "test",
                    "stack_id": "fruit-stack", "quantity": reserved, "status": "reserved"}]
            return data

        fruit = with_fruit()
        _, fruit_state = render(fruit, "fruit", stack_id="fruit-stack", quantity=3)
        fruit_state["values"]["str"] += 1
        fruit_state["values"]["base_lp"] += 6
        fruit_state["complete"] = True
        fruit_result, consumed = resolve(fruit_state, "fruit-use")
        assert consumed["player"]["growth_bonus"]["str"] == 3 and consumed["player"]["base_lp"] == 26
        assert consumed["player"]["base_stats"] == fruit["player"]["base_stats"]
        assert consumed["player"]["lp"] == {"cur": 20, "max": 26}
        assert consumed["inventory"]["carried_stacks"] == [] and consumed["inventory"]["bag"]["used_slots"] == 0
        assert not aw.validate_transition(api, fruit, consumed, "fruit-use")
        cases.append("choice_fruit_consumes_exact_batch_and_splits_growth")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=fruit_result["output"], transaction_id="fruit-use", turn=0, keep=50))
        assert api.load_yaml(save)["inventory"]["carried_stacks"] == []
        assert aw.resolve(api, SimpleNamespace(save=str(save), widget_state=str(store(fruit_state)), confirmation="確定",
            output=fruit_result["output"], transaction_id="fruit-use"))["idempotent"]
        cases.append("fruit_commit_and_retry_use_item_once")
        fixed = with_fruit("STRの実", 2)
        _, fixed_state = render(fixed, "fruit", stack_id="fruit-stack", quantity=1)
        assert set(fixed_state["values"]) == {"str"}
        fixed_state["values"]["str"] += 1
        fixed_state["complete"] = True
        _, fixed_used = resolve(fixed_state, "fixed-fruit")
        assert fixed_used["inventory"]["carried_stacks"][0]["count"] == 1
        assert fixed_used["player"]["growth_bonus"]["str"] == 3
        cases.append("named_fruit_keeps_its_type")
        bad = copy.deepcopy(fixed_state)
        bad["values"] = {"int": 19}
        rejects("named_fruit_cannot_change_type", lambda: resolve(bad, "fixed-forged"))
        lp_fruit = with_fruit("LPの実", 1)
        _, lp_state = render(lp_fruit, "fruit", stack_id="fruit-stack")
        lp_state["values"]["base_lp"], lp_state["complete"] = 21, True
        rejects("lp_fruit_requires_three_point_steps", lambda: resolve(lp_state, "lp-step"))
        reserved = with_fruit("STRの実", 3, 2)
        write(reserved)
        rejects("reserved_fruit_cannot_be_spent", lambda: render(reserved, "fruit", stack_id="fruit-stack", quantity=2))
        _, reserved_state = render(reserved, "fruit", stack_id="fruit-stack", quantity=1)
        reserved_state["values"]["str"] += 1
        reserved_state["complete"] = True
        _, reserved_used = resolve(reserved_state, "reserved-partial")
        assert reserved_used["inventory"]["carried_stacks"][0]["count"] == 2
        assert reserved_used["inventory"]["carried_stacks"][0]["reserved_quantity"] == 2
        assert reserved_used["inventory"]["reservations"] == reserved["inventory"]["reservations"]
        assert reserved_used["dice_state"] == reserved["dice_state"]
        cases.append("unreserved_fruit_use_preserves_reservations_and_dice")
        write(fruit)
        rejects("unknown_actor_rejected", lambda: render(fruit, "fruit", actor_id="unknown", stack_id="fruit-stack"))
        rejects("unknown_item_rejected", lambda: render(fruit, "fruit", stack_id="missing"))
        unknown = with_fruit("能力の実", 1)
        write(unknown)
        rejects("untyped_fruit_needs_identification", lambda: render(unknown, "fruit", stack_id="fruit-stack"))
        party = with_fruit("INTの実", 1)
        ally = copy.deepcopy(party["player"])
        ally.update(character_id="Ally", name="Ally", build_complete=False, inn_share="self",
            voice_sample={"daily": "hello", "battle": "go", "ero": ""})
        party["party"] = [ally]
        _, ally_state = render(party, "fruit", actor_id="Ally", stack_id="fruit-stack")
        ally_state["values"]["int"] += 1
        ally_state["complete"] = True
        _, ally_used = resolve(ally_state, "ally-fruit")
        assert ally_used["player"] == party["player"] and ally_used["party"][0]["growth_bonus"]["int"] == 1
        cases.append("party_id_targets_only_that_actor")

        respec = copy.deepcopy(initial)
        respec["world_state"].pop("allocation_state", None)
        respec["world_state"]["onboarding"].update(initial_base_stats=copy.deepcopy(respec["player"]["base_stats"]), fire_granted=True, fire_explained=True, fire_grant_transaction_id="previous-fire")
        respec["player"]["gold"] = 500
        respec["player"]["base_lp"] = 26
        respec["player"]["growth_bonus"]["str"] = 4
        respec["player"]["fire_bonus"] = {key: 3 for key in aw.STATS}
        respec["player"]["fire_lp_bonus"] = 12
        respec["fire_state"]["holders"] = [respec["player"]["character_id"]]
        respec["world_state"]["time_of_day"] = "夕"
        aw._recalculate(respec["player"])
        respec["player"]["mp"]["cur"] = 2
        _, respec_state = render(respec, "respec")
        unchanged = copy.deepcopy(respec_state)
        unchanged["complete"] = True
        rejects("no_op_retraining_does_not_charge", lambda: resolve(unchanged, "respec-noop"))
        assert sum(respec_state["values"].values()) == 37 and respec_state["values"]["str"] == 7
        respec_state["values"]["int"], respec_state["values"]["str"], respec_state["complete"] = 3, 22, True
        respec_result, retrained = resolve(respec_state, "retrain")
        assert retrained["player"]["gold"] == 400
        assert retrained["world_state"]["day"] == respec["world_state"]["day"] + 1 and retrained["world_state"]["time_of_day"] == "朝"
        for key in ("growth_bonus", "base_lp", "job_lp_bonus", "fire_bonus", "fire_lp_bonus", "equipment_bonus", "temporary_modifiers"):
            assert retrained["player"][key] == respec["player"][key], key
        assert retrained["world_state"]["onboarding"] == respec["world_state"]["onboarding"]
        assert retrained["player"]["mp"]["cur"] == 2
        assert not aw.validate_transition(api, respec, retrained, "retrain")
        assert sum(aw._permanent_stats(retrained["player"]).values()) == 37
        assert sum(retrained["player"]["base_stats"].values()) == 33 and sum(retrained["player"]["growth_bonus"].values()) == 4
        cases.append("paid_half_day_retraining_preserves_all_permanent_points_and_birth_receipt")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=respec_result["output"], transaction_id="retrain", turn=0, keep=50))
        committed_respec = api.load_yaml(save)
        assert committed_respec["player"]["gold"] == 400
        assert committed_respec["world_state"]["onboarding"]["initial_base_stats"] == respec["world_state"]["onboarding"]["initial_base_stats"]
        cases.append("retraining_normal_commit_preserves_birth_snapshot")
        _, full_state = render(respec, "respec")
        full_state["values"]["str"], full_state["values"]["int"], full_state["complete"] = 3, 22, True
        full_result, full_after = resolve(full_state, "full-growth-move")
        assert full_after["player"]["growth_bonus"]["str"] == 0 and full_after["player"]["growth_bonus"]["int"] == 4
        assert aw._permanent_stats(full_after["player"]) == full_state["values"]
        assert full_after["player"]["base_lp"] == 26 and full_after["player"]["mp"] == {"cur": 2, "max": 25}
        assert full_after["world_state"]["onboarding"]["initial_base_stats"] == respec["world_state"]["onboarding"]["initial_base_stats"]
        assert full_after["inventory"] == respec["inventory"]
        assert not aw.validate_transition(api, respec, full_after, "full-growth-move")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=full_result["output"], transaction_id="full-growth-move", turn=0, keep=50))
        cases.append("fruit_growth_moves_to_another_stat_without_consuming_or_regranting_fruit")
        repeated_source = api.load_yaml(save)
        _, repeated_state = render(repeated_source, "respec")
        repeated_state["values"]["str"], repeated_state["values"]["int"], repeated_state["complete"] = 22, 3, True
        _, repeated = resolve(repeated_state, "full-growth-repeat")
        assert sum(aw._permanent_stats(repeated["player"]).values()) == 37
        assert sum(repeated["player"]["base_stats"].values()) == 33 and sum(repeated["player"]["growth_bonus"].values()) == 4
        assert repeated["player"]["base_lp"] == 26
        assert repeated["world_state"]["onboarding"]["initial_base_stats"] == repeated_source["world_state"]["onboarding"]["initial_base_stats"]
        cases.append("repeated_full_retraining_cannot_duplicate_growth_points")
        _, lp_state = render(respec, "respec")
        lp_state["values"] = {key: 3 for key in aw.STATS}
        lp_state["values"]["def"], lp_state["complete"] = 22, True
        lp_result, lp_after = resolve(lp_state, "full-def-growth")
        assert lp_after["player"]["stat_lp_bonus"] == 9 and lp_after["player"]["base_lp"] == 26
        assert lp_after["player"]["lp"]["max"] == 47 and lp_after["player"]["lp"]["cur"] == respec["player"]["lp"]["cur"]
        cases.append("full_retraining_derives_lp_from_permanent_def_without_healing")
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=lp_result["output"], transaction_id="full-def-growth", turn=0, keep=50))
        high_lp = api.load_yaml(save)
        high_lp["player"]["lp"]["cur"] = high_lp["player"]["lp"]["max"]
        _, shrink_state = render(high_lp, "respec")
        shrink_state["values"]["def"], shrink_state["values"]["int"], shrink_state["complete"] = 3, 22, True
        _, shrunk = resolve(shrink_state, "full-def-shrink")
        assert shrunk["player"]["stat_lp_bonus"] == 0 and shrunk["player"]["base_lp"] == 26
        assert shrunk["player"]["lp"] == {"cur": 38, "max": 38} and shrunk["player"]["mp"]["cur"] == high_lp["player"]["mp"]["cur"]
        cases.append("reducing_permanent_def_clamps_lp_and_preserves_lp_fruit")
        historic = copy.deepcopy(respec)
        historic["world_state"]["allocation_state"] = copy.deepcopy(initial["world_state"]["allocation_state"])
        old_receipt = historic["world_state"]["allocation_state"]["resolutions"][0]
        old_receipt.update(mode="respec", fee_gold=100, duration_minutes=720)
        for key in ("respec_rule", "permanent_points_before", "permanent_points_after"):
            old_receipt.pop(key, None)
        historic_errors = []
        aw.validate_state(historic, historic_errors)
        assert not historic_errors and not aw.validate_transition(api, historic, copy.deepcopy(historic), "ordinary-history")
        cases.append("historical_33_point_receipts_remain_valid_without_new_fields")
        def_fruit = with_fruit("DEFの実", 1)
        def_fruit["player"]["growth_bonus"]["def"] = 1
        def_fruit["player"]["equipment_bonus"]["def"] = 10
        aw._recalculate(def_fruit["player"])
        _, def_fruit_state = render(def_fruit, "fruit", stack_id="fruit-stack")
        def_fruit_state["values"]["def"] += 1
        def_fruit_state["complete"] = True
        _, def_fruit_after = resolve(def_fruit_state, "tracked-def-fruit")
        assert def_fruit_after["player"]["stat_lp_bonus"] == 1
        assert def_fruit_after["player"]["base_lp"] == 20 and def_fruit_after["player"]["lp"] == {"cur": 20, "max": 21}
        assert def_fruit_after["player"]["effective_stats"]["def"] == 15
        cases.append("tracked_def_fruit_updates_lp_but_equipment_def_does_not")
        due = copy.deepcopy(respec)
        due["world_state"]["day"] = 4
        _, due_state = render(due, "respec")
        due_state["values"] = copy.deepcopy(respec_state["values"])
        due_state["complete"] = True
        due_result, due_after = resolve(due_state, "retrain-due")
        assert due_after["world_state"]["day"] == 5 and due_after["debt_state"]["collection_pending"] is True
        api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=due_result["output"], transaction_id="retrain-due", turn=0, keep=50))
        cases.append("half_day_due_date_triggers_collection_and_commits")
        pending = copy.deepcopy(respec)
        pending["world_state"]["day"] = 5
        pending["debt_state"]["collection_pending"] = True
        write(pending)
        rejects("pending_collection_cannot_be_skipped_by_retraining", lambda: render(pending, "respec"))
        free_move = copy.deepcopy(respec)
        free_move["player"]["base_stats"], free_move["player"]["growth_bonus"] = aw._split_permanent(respec_state["values"])
        aw._recalculate(free_move["player"])
        assert aw.validate_transition(api, respec, free_move, "free-respec")
        cases.append("ordinary_patch_cannot_bypass_paid_retraining")
        write(respec)
        free_candidate = clone / "state/runtime/free-retrain.yaml"
        api.atomic_write(free_candidate, api.dump_yaml(free_move))
        rejects("normal_commit_rejects_free_retraining", lambda: api.cmd_commit_save(SimpleNamespace(
            current=str(save), candidate=str(free_candidate), transaction_id="free-respec", turn=0, keep=50)))
        growth_only_move = copy.deepcopy(respec)
        growth_only_move["player"]["growth_bonus"].update(str=0, int=4)
        aw._recalculate(growth_only_move["player"])
        assert aw.validate_transition(api, respec, growth_only_move, "free-growth-move")
        cases.append("growth_only_redistribution_cannot_bypass_retraining")

        def weighted(data, weight=7, tracked=True):
            from encumbrance import recalculate
            value = copy.deepcopy(data)
            value["item_definitions"].append({"item_def_id": "weight-def", "name": "Weight Probe", "category": "equipment",
                "specification": {"weight": weight}, "provenance": {}, "balance_anchor": {}})
            value["item_instances"].append({"instance_id": "weight-instance", "item_def_id": "weight-def", "name": "Weight Probe",
                "location": "equipped", "slot_cost": 0, "owner_character_id": value["player"]["character_id"], "specification_snapshot": {"weight": weight}})
            value["player"]["equipment"]["armor_instance_id"] = "weight-instance"
            if tracked:
                recalculate(value, value["player"]["character_id"])
            else:
                value["player"].pop("encumbrance", None)
            return value

        heavy = weighted(respec, 14)
        assert heavy["player"]["encumbrance"]["applied_penalty"] == 4
        _, heavy_state = render(heavy, "respec")
        heavy_state["values"], heavy_state["complete"] = copy.deepcopy(respec_state["values"]), True
        _, heavy_after = resolve(heavy_state, "heavy-retrain")
        assert heavy_after["player"]["encumbrance"]["applied_penalty"] == 0
        assert heavy_after["player"]["effective_stats"]["spd"] == 6
        assert heavy_after["player"]["temporary_modifiers"]["spd"] == 0
        assert not aw.validate_transition(api, heavy, heavy_after, "heavy-retrain")
        cases.append("retraining_strength_recomputes_weight_without_stacking")
        str_heavy = weighted(with_fruit("STRの実", 1))
        _, str_heavy_state = render(str_heavy, "fruit", stack_id="fruit-stack")
        str_heavy_state["values"]["str"] += 1
        str_heavy_state["complete"] = True
        _, str_heavy_after = resolve(str_heavy_state, "heavy-str-fruit")
        assert str_heavy_after["player"]["effective_stats"]["spd"] == str_heavy["player"]["effective_stats"]["spd"] + 1
        cases.append("strength_fruit_updates_encumbrance")
        spd_heavy = weighted(with_fruit("SPDの実", 1), 10)
        _, spd_heavy_state = render(spd_heavy, "fruit", stack_id="fruit-stack")
        spd_heavy_state["values"]["spd"] += 1
        spd_heavy_state["complete"] = True
        _, spd_heavy_after = resolve(spd_heavy_state, "heavy-spd-fruit")
        assert spd_heavy_after["player"]["effective_stats"]["spd"] == 0
        assert spd_heavy_after["player"]["encumbrance"]["applied_penalty"] == 4
        cases.append("speed_fruit_respects_weight_penalty_floor")
        unknown_weight = weighted(with_fruit("INTの実", 1), tracked=False)
        unknown_weight["item_definitions"][-1]["specification"].pop("weight")
        unknown_weight["item_instances"][-1]["specification_snapshot"].pop("weight")
        _, unknown_weight_state = render(unknown_weight, "fruit", stack_id="fruit-stack")
        unknown_weight_state["values"]["int"] += 1
        unknown_weight_state["complete"] = True
        _, unknown_after = resolve(unknown_weight_state, "unknown-weight-int")
        assert unknown_after["player"]["temporary_modifiers"] == unknown_weight["player"]["temporary_modifiers"]
        assert "encumbrance" not in unknown_after["player"]
        cases.append("unrelated_int_fruit_does_not_require_legacy_weight")
        unknown_strength = copy.deepcopy(unknown_weight)
        unknown_strength["item_definitions"][0]["name"] = "STRの実"
        unknown_strength["inventory"]["carried_stacks"][0]["name"] = "STRの実"
        write(unknown_strength)
        rejects("strength_edit_requires_typed_equipped_weight", lambda: render(unknown_strength, "fruit", stack_id="fruit-stack"))
        combat_fruit = with_fruit()
        combat_fruit["runtime_state"]["active_scene"] = "combat"
        write(combat_fruit)
        rejects("fruit_is_not_a_free_combat_action", lambda: render(combat_fruit, "fruit", stack_id="fruit-stack"))
        bad = copy.deepcopy(retrained)
        bad["player"]["gold"] += 1
        assert aw.validate_transition(api, respec, bad, "retrain")
        cases.append("commit_rejects_wrong_retraining_fee")
        bad = copy.deepcopy(retrained)
        bad["world_state"]["day"] -= 1
        assert aw.validate_transition(api, respec, bad, "retrain")
        cases.append("commit_rejects_missing_half_day")
        bad = copy.deepcopy(consumed)
        bad["inventory"] = copy.deepcopy(fruit["inventory"])
        assert aw.validate_transition(api, fruit, bad, "fruit-use")
        cases.append("commit_rejects_growth_without_consumption")
        bad = copy.deepcopy(consumed)
        bad["player"]["growth_bonus"]["def"] += 1
        aw._recalculate(bad["player"])
        assert aw.validate_transition(api, fruit, bad, "fruit-use")
        cases.append("commit_rejects_unconfirmed_extra_growth")
        bad = copy.deepcopy(consumed)
        bad["world_state"]["allocation_state"]["resolutions"][0]["values"]["str"] += 1
        assert aw.validate_transition(api, fruit, bad, "fruit-use")
        cases.append("commit_rejects_forged_receipt")
        bad = copy.deepcopy(consumed)
        bad["world_state"].pop("allocation_state")
        assert aw.validate_transition(api, consumed, bad, "erase")
        cases.append("receipts_are_append_only")
        ordinary = copy.deepcopy(base)
        ordinary["player"]["growth_bonus"]["chm"] += 1
        aw._recalculate(ordinary["player"])
        assert not aw.validate_transition(api, base, ordinary, "event-growth")
        cases.append("ordinary_nonfruit_event_growth_remains_legal")
        print_artifact = Path(temporary) / "last-widget.html"
        shutil.copyfile(widget["output"], print_artifact)
    return {"ok": True, "cases": len(cases), "case_ids": cases, "live_game_untouched": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
