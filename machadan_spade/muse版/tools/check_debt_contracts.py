#!/usr/bin/env python3
"""Verify staged payoff options and unchanged payment rules in an isolated game."""
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
    with tempfile.TemporaryDirectory(prefix="machadan-debt-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"), copy_function=shutil.copyfile)
        for name in ("VERSION.txt", "RUNTIME_MANIFEST.json"):
            shutil.copyfile(root.parent / name, game / name)
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("debt_probe_runtime", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        import debt_contracts as dc
        save = clone / "saves/probe.yaml"
        api.cmd_new_save(SimpleNamespace(output=str(save), campaign_id="debt-probe", force=False))
        base = api.load_yaml(save)
        base["player"]["gold"] = 200000
        base["custom_debt_probe"] = {"preserve": ["world", 7]}

        def write(data):
            errors, _ = api.validate_save_data(data)
            assert not errors, errors
            api.atomic_write(save, api.dump_yaml(data))

        def state_errors(data):
            result = []
            dc.validate_state(data, result)
            return result

        def reject(name, call):
            before = save.read_bytes()
            try:
                call()
            except api.RuntimeProblem:
                assert save.read_bytes() == before
                cases.append(name)
            else:
                raise AssertionError("invalid debt action accepted: " + name)

        def payment(data, amount, tx):
            write(data)
            before = save.read_bytes()
            args = SimpleNamespace(save=str(save), payment=amount, output=str(clone / f"state/runtime/{tx}.yaml"), transaction_id=tx, force=False)
            result = dc.resolve_payment(api, args)
            assert save.read_bytes() == before
            return result, api.load_yaml(Path(result["output"])), args

        def collection(data, amount, tx):
            write(data)
            before = save.read_bytes()
            args = SimpleNamespace(save=str(save), payment=amount, output=str(clone / f"state/runtime/{tx}.yaml"), transaction_id=tx, force=False, benefit=None)
            result = api.cmd_resolve_debt_collection(args)
            assert save.read_bytes() == before
            return result, api.load_yaml(Path(result["output"])), args

        def commit(result, tx):
            return api.cmd_commit_save(SimpleNamespace(current=str(save), candidate=result["output"], transaction_id=tx, turn=0, keep=50))

        def charge(data, amount, tx="charge-probe", reason="inn"):
            result = copy.deepcopy(data)
            debt = result["debt_state"]
            before = debt["principal"]
            debt["principal"] += amount
            result["player"]["debt"] = debt["principal"]
            debt["collection_ledger"].append({"collection_id": tx, "transaction_id": tx,
                "event_kind": "charge", "collection_day": result["world_state"]["day"],
                "contract_id_before": debt["contract_id"], "contract_id_after": debt["contract_id"],
                "principal_before_payment": before, "principal_after_resolution": debt["principal"],
                "charge_amount": amount, "reason": reason, "source_id": "existing-rule-probe"})
            assert not api._validate_debt_transition(data, result, tx)
            return result

        assert [dc.principal_schedule(n) for n in range(5)] == [10000, 50000, 100000, 150000, 200000]
        assert [dc.expected_benefit(n) for n in range(1, 5)] == ["lilith_intimacy", "named_appearance_customization", None, None]
        cases.append("fixed_contract_principals_and_one_option_per_first_two_stages")
        assert dc.debt_unlocks(base) == {"lilith_intimacy": False, "named_appearance_customization": False}
        cases.append("fresh_contract_has_no_unlock")

        fine = charge(base, 3000, "existing-crime-fine", reason="crime_fine")
        assert not state_errors(fine) and fine["player"]["debt"] == 13000
        assert fine["player"]["gold"] == base["player"]["gold"] and not any(dc.debt_unlocks(fine).values())
        cases.append("existing_fixed_fine_records_atomic_debt_without_unlock")
        bad_fine = copy.deepcopy(fine)
        bad_fine["debt_state"]["principal"] = bad_fine["player"]["debt"] = 13100
        bad_fine["debt_state"]["collection_ledger"][-1].update(charge_amount=3100, principal_after_resolution=13100)
        assert api._validate_debt_transition(base,bad_fine,"existing-crime-fine") and state_errors(bad_fine)
        cases.append("regional_law_cannot_invent_a_different_fine")

        partial_result, partial, partial_args = payment(base, 1000, "partial")
        assert partial["debt_state"]["principal"] == 9000 and partial["player"]["gold"] == 199000
        assert partial["debt_state"]["cycle_paid"] == 1000 and not any(dc.debt_unlocks(partial).values())
        assert partial["custom_debt_probe"] == base["custom_debt_probe"]
        cases.append("voluntary_partial_payment_does_not_unlock")
        assert dc.resolve_payment(api, partial_args)["idempotent"]
        cases.append("same_payment_candidate_retry_is_identical")

        first_result, first, first_args = payment(base, 10000, "first-payoff")
        assert first["debt_state"]["principal"] == first["player"]["debt"] == 50000
        assert dc.debt_unlocks(first) == {"lilith_intimacy": True, "named_appearance_customization": False}
        assert first["debt_state"]["active_benefits"] == [] and first["enterprise_state"] == base["enterprise_state"]
        assert first["debt_state"]["benefit_selection"] == base["debt_state"]["benefit_selection"]
        assert first["debt_state"]["collection_ledger"][-1]["completed_stage"] == 1
        cases.append("first_full_payoff_unlocks_only_lilith_and_renews_exactly_50000")
        commit(first_result, "first-payoff")
        assert dc.resolve_payment(api, first_args)["idempotent"]
        assert commit(first_result, "first-payoff")["idempotent"]
        cases.append("committed_payment_and_commit_retries_do_not_reapply")
        bad_retry = copy.copy(first_args)
        bad_retry.payment = 100
        reject("committed_payment_retry_cannot_change_amount", lambda: dc.resolve_payment(api, bad_retry))

        paid_one = api.load_yaml(save)
        second_result, second, second_args = payment(paid_one, 50000, "second-payoff")
        assert dc.debt_unlocks(second) == {"lilith_intimacy": True, "named_appearance_customization": True}
        assert second["debt_state"]["principal"] == 100000 and second["enterprise_state"] == paid_one["enterprise_state"]
        assert second["debt_state"]["active_benefits"] == []
        cases.append("second_payoff_adds_only_persistent_named_appearance_option")
        commit(second_result, "second-payoff")
        paid_two = api.load_yaml(save)
        third_result, third, _ = payment(paid_two, 100000, "third-payoff")
        assert third["debt_state"]["principal"] == 150000
        assert dc.debt_unlocks(third) == dc.debt_unlocks(paid_two)
        assert third["debt_state"]["collection_ledger"][-1]["unlocked_benefit"] is None
        cases.append("later_payoff_raises_only_the_next_fixed_contract_and_keeps_options")
        commit(third_result, "third-payoff")

        pending = copy.deepcopy(base)
        pending["world_state"]["day"] = 5
        pending["debt_state"]["collection_pending"] = True
        none_result, none, _ = collection(pending, 0, "nonpayment")
        assert none["debt_state"]["principal"] == 10100 and none["debt_state"]["missed_collections"] == 1
        assert none["debt_state"]["next_collection_day"] == 10 and not any(dc.debt_unlocks(none).values())
        cases.append("nonpayment_keeps_five_day_cycle_and_existing_100g_penalty")
        commit(none_result, "nonpayment")
        due_partial_result, due_partial, _ = collection(pending, 100, "due-partial")
        assert due_partial["debt_state"]["principal"] == 9980 and due_partial["debt_state"]["scheduled_due"] == 750
        assert not any(dc.debt_unlocks(due_partial).values())
        cases.append("scheduled_partial_payment_keeps_existing_fee_and_unlocks_nothing")
        commit(due_partial_result, "due-partial")
        scheduled_result, scheduled, scheduled_args = collection(pending, 10000, "scheduled-payoff")
        assert scheduled["debt_state"]["principal"] == 50000
        assert dc.debt_unlocks(scheduled) == dc.debt_unlocks(first)
        assert scheduled["debt_state"]["collection_ledger"][-1]["campaign_id"] == base["campaign_id"]
        assert api.cmd_resolve_debt_collection(scheduled_args)["idempotent"]
        commit(scheduled_result, "scheduled-payoff")
        assert api.cmd_resolve_debt_collection(scheduled_args)["idempotent"]
        cases.append("scheduled_payoff_and_both_retry_paths_share_typed_unlock_proof")

        charged = charge(base, 123)
        _, charged_paid, _ = payment(charged, 10123, "fees-payoff")
        assert charged_paid["debt_state"]["principal"] == 50000 and dc.debt_unlocks(charged_paid)["lilith_intimacy"]
        cases.append("first_payoff_includes_all_added_fees_and_exact_final_remainder")
        write(charged)
        before_flags = dc.debt_unlocks(charged)
        underpaid = dc.payment_candidate(charged, 10000, "underpaid-fees")
        assert underpaid["debt_state"]["principal"] == 123 and dc.debt_unlocks(underpaid) == before_flags
        assert not api._validate_debt_transition(charged, underpaid, "underpaid-fees")
        cases.append("paying_original_10000_without_added_fees_is_not_a_full_payoff")

        for target in ("Lilith", "Lilith_000", "リリス"):
            for kind in ("romance", "conquest", "intimacy", "private_bath"):
                assert not dc.interaction_gate(base, target, kind)["allowed"]
                assert dc.interaction_gate(first, target, kind)["allowed"]
        cases.append("lilith_target_gate_requires_the_first_complete_receipt")
        for target in ("Mia_000", "Lilith_123", {"character_id": "Mia_000", "name": "リリス"}):
            assert dc.interaction_gate(base, target, "romance")["allowed"]
        for kind in ("conversation", "care", "fire_grant", "gift", "trust", "suite_contract", "sweet_contract", "部屋契約"):
            assert dc.interaction_gate(base, "Lilith_000", kind)["allowed"]
        cases.append("other_npcs_trust_care_fire_grant_and_room_contracts_are_unrestricted")
        for status in ("attempt", "declined"):
            attempted = copy.deepcopy(base)
            attempted["runtime_state"]["interaction"] = {"target": "Lilith_000", "kind": "romance", "status": status}
            assert not state_errors(attempted)
        established = copy.deepcopy(base)
        established["runtime_state"]["interaction"] = {"target": "Lilith_000", "kind": "romance", "status": "established"}
        assert state_errors(established)
        established["runtime_state"]["interaction"]["target"] = "Mia_000"
        assert not state_errors(established)
        cases.append("flirting_attempt_can_be_declined_but_cannot_establish_a_locked_relationship")

        for relationship in ({"type": "lover", "love_level": 0}, {"type": "friend", "love_level": 1},
                             {"type": "friend", "love_level": 1.0}, {"type": "friend", "love_level": "100"}):
            bad = copy.deepcopy(base)
            bad["npc_relationship"] = [{"character_id": "Lilith_000", "relationship": relationship}]
            assert state_errors(bad)
        cases.append("structured_relationship_and_love_level_cannot_bypass_payoff_gate")
        lover = copy.deepcopy(first)
        lover["npc_relationship"] = [{"character_id": "Lilith_000", "relationship": {"type": "lover", "love_level": 100}}]
        assert not state_errors(lover)
        forgiven = copy.deepcopy(lover)
        forgiven["debt_state"]["principal"] = forgiven["player"]["debt"] = 1
        assert api._validate_debt_transition(lover, forgiven, "forgive")
        raised = copy.deepcopy(lover)
        raised["debt_state"]["principal"] = raised["player"]["debt"] = 60000
        assert api._validate_debt_transition(lover, raised, "affection-raise")
        cases.append("lover_status_neither_forgives_nor_silently_increases_current_debt")

        for key in dc.UNLOCK_KEYS:
            bad = copy.deepcopy(base)
            bad["debt_state"]["unlocks"][key] = True
            assert state_errors(bad) and api._validate_debt_transition(base, bad, "fake-unlock")
        cases.append("mutable_unlock_flags_without_payoff_proof_are_rejected")
        bad = copy.deepcopy(base)
        bad["world_state"]["goals"]["debt_clear"] = True
        assert state_errors(bad) and not dc.debt_unlocks(bad)["lilith_intimacy"]
        cases.append("goal_flag_is_not_a_payoff_proof")
        for field, value in (("campaign_id", "another-campaign"), ("payment", 9999), ("completed_stage", 2), ("principal_after_resolution", 20000)):
            bad = copy.deepcopy(first)
            bad["debt_state"]["collection_ledger"][-1][field] = value
            assert state_errors(bad) and not any(dc.debt_unlocks(bad).values())
        cases.append("payoff_proof_binds_campaign_full_payment_stage_and_next_principal")
        tiny = copy.deepcopy(first)
        tiny["debt_state"]["collection_ledger"][-1].update(payment=1, principal_before_payment=1)
        assert state_errors(tiny) and not any(dc.debt_unlocks(tiny).values())
        cases.append("fabricated_one_gold_payoff_cannot_skip_the_initial_principal_history")
        erased = copy.deepcopy(second)
        erased["debt_state"]["unlocks"]["named_appearance_customization"] = False
        assert state_errors(erased) and api._validate_debt_transition(second, erased, "revoke")
        cases.append("earned_appearance_option_is_persistent")
        extra = copy.deepcopy(first)
        extra["debt_state"]["active_benefits"] = [{"benefit_id": "facility_investment"}]
        assert api._validate_debt_transition(base, extra, "first-payoff")
        extra = copy.deepcopy(first)
        extra["enterprise_state"]["lilith_investments"].append({"investment_id": "hidden-investment"})
        assert api._validate_debt_transition(base, extra, "first-payoff")
        cases.append("payoff_cannot_sneak_in_an_enterprise_perk_or_investment")
        write(base)
        invalid_args = SimpleNamespace(save=str(save), payment=10000, output=str(save), transaction_id="alias", force=False)
        reject("debt_payment_cannot_overwrite_live_save", lambda: dc.resolve_payment(api, invalid_args))
        invalid_args.output = str(clone / "世界/Quest_Guild.md")
        reject("debt_payment_cannot_overwrite_canon", lambda: dc.resolve_payment(api, invalid_args))
        invalid_args.output = str(clone / "state/runtime/bad-units.yaml")
        invalid_args.payment = 101
        reject("voluntary_payment_preserves_100g_units", lambda: dc.resolve_payment(api, invalid_args))
        write(pending)
        reject("voluntary_payment_does_not_bypass_pending_collection", lambda: dc.resolve_payment(api, invalid_args))
    return {"ok": True, "cases": len(cases), "case_ids": cases, "source_mutated": False}


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
