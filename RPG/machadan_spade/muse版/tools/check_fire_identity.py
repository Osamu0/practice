#!/usr/bin/env python3
"""Check ID/legacy-name fire-holder resolution without modifying any save."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def check(root: Path) -> dict:
    sys.path.insert(0, str(root / "tools"))
    spec = importlib.util.spec_from_file_location("machadan_fire_identity_probe", root / "tools/machadan_runtime.py")
    rt = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = rt
    spec.loader.exec_module(rt)
    cases: list[str] = []

    def fixture(legacy: bool = False, duplicates: bool = False) -> dict:
        data = rt.load_yaml(root / "セーブ雛形.yaml")
        player = data["player"]
        player.update(character_id="PC_FIRE", name="Twin" if duplicates else "Player")
        player["lp"] = {"cur": 0, "max": 20}
        player["mp"] = {"cur": 0, "max": 10}
        player["ero_status"] = []
        player["buffs"] = []
        ally = copy.deepcopy(player)
        ally.update(character_id="PT_FIRE", name="Twin" if duplicates else "Ally", state="down")
        other = copy.deepcopy(player)
        other.update(character_id="PT_OTHER", name="Twin" if duplicates else "Other", state="")
        other["lp"]["cur"] = 5
        data["party"] = [ally, other]
        refs = [player["name"], ally["name"]] if legacy else [player["character_id"], ally["character_id"]]
        data["fire_state"]["holders"] = refs
        world = data["world_state"]
        world.update(day=1, depth=None, time_of_day="夜", location="街道")
        world["expedition_state"] = {
            "active": True, "expedition_id": "identity-expedition", "kind": "travel",
            "fire_holders": refs, "separated_fire_holders": [], "rebirth_pending": True,
            "last_end_reason": "none", "last_ended_expedition_id": "", "rebirth_receipt": None,
        }
        data["debt_state"]["principal"] = player["debt"]
        return data

    def settlement(old: dict, legacy_receipt: bool = False) -> dict:
        new = copy.deepcopy(old)
        old_exp = old["world_state"]["expedition_state"]
        receipt = []
        for reference in old_exp["fire_holders"]:
            actor = rt._expedition_member(old, reference)
            record = {"name": actor["name"], "lp_at_trigger": 0}
            if not legacy_receipt:
                record["character_id"] = actor["character_id"]
            receipt.append(record)
            recovered = rt._expedition_member(new, reference)
            for key in ("lp", "mp"):
                recovered[key]["cur"] = recovered[key]["max"]
            recovered["ero_status"] = []
            recovered["buffs"] = []
            if "state" in recovered:
                recovered["state"] = ""
        world = new["world_state"]
        world.update(day=2, depth=None, time_of_day="朝", location="ぬれねずみ亭")
        world["expedition_state"] = {
            "active": False, "expedition_id": "", "kind": "none", "fire_holders": [],
            "separated_fire_holders": [], "rebirth_pending": False,
            "last_end_reason": "rebirth", "last_ended_expedition_id": old_exp["expedition_id"],
            "rebirth_receipt": {"expedition_id": old_exp["expedition_id"], "fire_holders": receipt},
        }
        fee = rt._rebirth_fee(old["world_state"])
        new["player"]["debt"] += fee
        new["debt_state"]["principal"] = new["player"]["debt"]
        new["debt_state"]["collection_pending"] = old["debt_state"]["collection_pending"] or (
            world["day"] >= old["debt_state"]["next_collection_day"])
        return new

    def state_errors(data: dict) -> list[str]:
        errors: list[str] = []
        rt._validate_expedition_state(data, data["world_state"], errors)
        return errors

    def expect(name: str, errors: list[str], snippet: str | None = None) -> None:
        if snippet is None and errors or snippet is not None and not any(snippet in error for error in errors):
            raise RuntimeError(name + ": " + repr(errors))
        cases.append(name)

    data = fixture()
    if rt._expedition_member(data, "PC_FIRE") is not data["player"] or rt._expedition_member(data, "PT_FIRE") is not data["party"][0]:
        raise RuntimeError("stable IDs did not resolve")
    cases.append("stable_id_resolution")
    if rt._expedition_member(data, "Ally") is not data["party"][0]:
        raise RuntimeError("unique legacy name did not resolve")
    cases.append("unique_legacy_name_resolution")
    data["party"][1]["name"] = "PC_FIRE"
    if rt._expedition_member(data, "PC_FIRE") is not data["player"]:
        raise RuntimeError("display name took precedence over an exact ID")
    cases.append("exact_id_precedes_display_name")
    duplicate = fixture(duplicates=True)
    if rt._expedition_member(duplicate, "Twin") is not None or rt._expedition_member(duplicate, "PT_FIRE") is not duplicate["party"][0]:
        raise RuntimeError("duplicate display names were not resolved safely")
    cases.append("duplicate_name_requires_id")
    expect("active_expedition_with_ids_and_duplicate_names", state_errors(duplicate))
    duplicate["world_state"]["expedition_state"]["fire_holders"] = ["Twin"]
    duplicate["fire_state"]["holders"] = ["Twin"]
    expect("ambiguous_legacy_name_rejected", state_errors(duplicate), "must resolve")
    data = fixture()
    data["world_state"]["expedition_state"]["fire_holders"] = ["Player", "Ally"]
    data["world_state"]["expedition_state"]["separated_fire_holders"] = ["PT_FIRE"]
    expect("mixed_id_and_legacy_registration", state_errors(data))
    data["world_state"]["expedition_state"]["fire_holders"] = ["PC_FIRE", "Player"]
    data["world_state"]["expedition_state"]["separated_fire_holders"] = []
    expect("same_actor_aliases_not_two_holders", state_errors(data), "same actor")
    old = fixture(duplicates=True)
    new = settlement(old)
    expect("id_receipt_duplicate_display_names", state_errors(new))
    expect("id_party_recovered_as_fire_holder", rt._validate_adventure_transition(old, new))
    legacy = fixture(legacy=True)
    legacy_new = settlement(legacy, legacy_receipt=True)
    expect("legacy_name_receipt_still_works", state_errors(legacy_new))
    expect("legacy_name_rebirth_still_works", rt._validate_adventure_transition(legacy, legacy_new))
    bad = copy.deepcopy(new)
    for item in bad["world_state"]["expedition_state"]["rebirth_receipt"]["fire_holders"]:
        item.pop("character_id")
    expect("ambiguous_name_only_receipt_rejected", rt._validate_adventure_transition(old, bad), "unambiguously")
    bad = copy.deepcopy(new)
    bad["world_state"]["expedition_state"]["rebirth_receipt"]["fire_holders"][0]["name"] = "Wrong display"
    expect("receipt_id_and_name_must_agree", rt._validate_adventure_transition(old, bad), "display name")
    bad_old = copy.deepcopy(old)
    bad_old["party"][0]["lp"]["cur"] = 1
    expect("every_holder_must_be_lp_zero", rt._validate_adventure_transition(bad_old, new), "every expedition fire holder")
    bad_old = copy.deepcopy(old)
    bad_old["world_state"]["expedition_state"]["rebirth_pending"] = False
    expect("two_commit_rebirth_required", rt._validate_adventure_transition(bad_old, new), "rebirth_pending=true")
    bad = copy.deepcopy(new)
    bad["player"]["gold"] += 1
    expect("rebirth_cannot_add_gold", rt._validate_adventure_transition(old, bad), "must not change player.gold")
    bad = copy.deepcopy(new)
    bad["player"]["debt"] += 1
    bad["debt_state"]["principal"] += 1
    expect("rebirth_fee_exact", rt._validate_adventure_transition(old, bad), "exactly 500G")
    bad = copy.deepcopy(new)
    bad["party"].pop(0)
    expect("fire_holder_party_member_retained", rt._validate_adventure_transition(old, bad), "retain fire holder")
    bad = copy.deepcopy(new)
    bad["party"][1]["lp"]["cur"] += 1
    expect("non_fire_party_member_unchanged", rt._validate_adventure_transition(old, bad), "non-fire party member")
    unique = fixture()
    bad = copy.deepcopy(unique)
    bad["world_state"]["expedition_state"]["fire_holders"] = ["Player", "Ally"]
    expect("active_snapshot_not_rewritten", rt._validate_adventure_transition(unique, bad), "fire_holders are immutable")
    historical = copy.deepcopy(new)
    historical["party"] = []
    expect("historical_receipt_survives_departure", state_errors(historical))
    return {"ok": True, "cases": len(cases), "case_ids": cases, "read_only": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
