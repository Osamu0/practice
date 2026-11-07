#!/usr/bin/env python3
"""Verify paid, confirmed campaign cosmetics without changing canonical files."""
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
from types import SimpleNamespace

sys.dont_write_bytecode = True


def check(root):
    cases = []
    with tempfile.TemporaryDirectory(prefix="machadan-appearance-check-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root.parent, game, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"))
        manifest_path = game / "RUNTIME_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["version"] = re.search(r"(?im)^version:\s*(\S.*)$", (game / "VERSION.txt").read_text()).group(1).strip()
        manifest["files"] = [{"path": path.relative_to(game).as_posix(), "size": path.stat().st_size,
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in sorted(game.rglob("*")) if path.is_file() and path != manifest_path]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("machadan_appearance_probe", clone / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        import appearance_customization as appearance
        import debt_contracts
        from save_changes import state_view
        parser = api.build_parser()

        def command(*arguments):
            args = parser.parse_args(list(map(str, arguments)))
            value = args.handler(args)
            if isinstance(value, tuple):
                if value[0]:
                    raise api.RuntimeProblem(str(value[1]))
                return value[1]
            return value

        save = clone / "saves/appearance-probe.yaml"
        command("new-save", "--campaign-id", "appearance-probe", "--output", save)
        fresh = api.load_yaml(save)
        fresh["player"]["gold"] = 200000
        api.atomic_write(save, api.dump_yaml(fresh))
        _, routes, _ = api.load_control()
        canonical_before = {path: (clone / path).read_bytes() for path in routes["persona_files"].values()}
        serial = 0

        def propose(changes=None, target="Lilith_000", restore=False, request_id=None):
            nonlocal serial
            serial += 1
            path = clone / f"state/runtime/appearance-{serial}.changes.json"
            if changes is not None:
                api.atomic_write(path, json.dumps(changes, ensure_ascii=False))
            before = save.read_bytes()
            args = SimpleNamespace(save=str(save), character_id=target, changes=str(path) if changes is not None else None,
                                   restore=restore, request_id=request_id or "appearance-probe-" + str(serial),
                                   output=str(clone / f"state/runtime/appearance-{serial}.preview.json"))
            result = appearance.preview(api, args)
            assert save.read_bytes() == before
            return result

        def resolve(request, tx, confirmation="確定"):
            before = save.read_bytes()
            args = SimpleNamespace(save=str(save), request_id=request["request_id"], confirmation=confirmation,
                                   output=str(clone / f"state/runtime/{tx}.appearance.yaml"), transaction_id=tx)
            result = appearance.resolve(api, args)
            assert save.read_bytes() == before
            return result, args

        def reject(name, action):
            before = save.read_bytes()
            try:
                action()
                raise AssertionError("invalid appearance operation accepted: " + name)
            except (api.RuntimeProblem, ValueError):
                assert save.read_bytes() == before
            cases.append(name)

        def commit(candidate, tx):
            return command("commit-save", "--current", save, "--candidate", candidate,
                           "--transaction-id", tx, "--turn", "0")

        reject("no_payoff_cannot_preview", lambda: propose({"hair": "銀色の長髪"}))
        forged = copy.deepcopy(fresh)
        forged["debt_state"]["unlocks"]["named_appearance_customization"] = True
        reject("forged_unlock_cache_cannot_grant_access", lambda: appearance._eligible(api, forged))
        assert not debt_contracts.interaction_gate(fresh, "Lilith_000", "romance")["allowed"]
        cases.append("lilith_gate_unchanged_before_first_payoff")
        for stage in (1, 2):
            current = api.load_yaml(save)
            output = clone / f"state/runtime/payoff-{stage}.yaml"
            tx = "appearance-payoff-" + str(stage)
            command("resolve-debt-payment", "--save", save, "--payment", current["debt_state"]["principal"],
                    "--output", output, "--transaction-id", tx)
            commit(output, tx)
            if stage == 1:
                reject("first_payoff_not_enough_for_appearance", lambda: propose({"hair": "銀色の長髪"}))
                assert debt_contracts.interaction_gate(api.load_yaml(save), "Lilith_000", "romance")["allowed"]
        unlocked = api.load_yaml(save)
        assert unlocked["world_state"]["appearance_customization"] == {"version": 1, "overrides": {}, "resolutions": []}
        cases.append("second_payoff_unlocks_option_without_changing_appearance")
        flags_false = copy.deepcopy(unlocked)
        flags_false["debt_state"]["unlocks"]["named_appearance_customization"] = False
        appearance._eligible(api, flags_false)
        errors, _ = api.validate_save_data(flags_false)
        assert errors, "inconsistent unlock cache was accepted"
        cases.append("payoff_proof_is_authoritative_and_stale_cache_is_invalid")
        for character_id in routes["persona_files"]:
            assert appearance._target(api, character_id)["character_id"] == character_id
        cases.append("all_ten_canonical_named_adults_resolve")
        reject("unknown_named_id_rejected", lambda: propose({"hair": "銀色"}, "Unknown_001"))
        reject("display_name_is_not_canonical_id", lambda: propose({"hair": "銀色"}, "リリス"))
        for key in ("name", "age", "personality", "voice", "stats", "abilities", "equipment", "relationship"):
            reject("noncosmetic_field_" + key, lambda key=key: propose({key: "changed"}))
        for value in ("17歳に見える顔", "五歳の姿", "小学生の外見"):
            reject("explicit_minor_appearance_" + str(len(value)), lambda value=value: propose({"face": value}))
        for height in (0, -1, True, float("inf")):
            reject("invalid_height_" + str(height), lambda height=height: propose({"height_cm": height}))
        reject("bounded_text", lambda: propose({"hair": "長" * 1001}))
        reject("bounded_features", lambda: propose({"features": [str(i) for i in range(21)]}))
        request = propose({"hair": "銀色の長髪", "height_cm": 0.5,
                           "build": "小柄な成人の体格", "features": ["見た目だけの小さな角"], "outfit": "青い上着"})
        assert request["draft_only"] and request["preview"]["after"]["height_cm"] == 0.5
        cases.append("fantasy_adult_height_and_small_adult_build_are_allowed")
        reject("chat_confirmation_required", lambda: resolve(request, "appearance-one", "はい"))
        before = save.read_bytes()
        changed_source = api.load_yaml(save)
        changed_source["player"]["gold"] -= 1
        api.atomic_write(save, api.dump_yaml(changed_source))
        reject("source_changed_without_revision_is_stale", lambda: resolve(request, "appearance-one"))
        save.write_bytes(before)
        # A valid but unrelated campaign cannot consume this request.
        other = copy.deepcopy(unlocked)
        other["campaign_id"] = "appearance-other"
        for entry in other["debt_state"]["collection_ledger"]:
            if "campaign_id" in entry:
                entry["campaign_id"] = other["campaign_id"]
        args = SimpleNamespace(save=str(clone / "saves/appearance-other.yaml"), request_id=request["request_id"],
                               confirmation="確定", output=str(clone / "state/runtime/other.appearance.yaml"), transaction_id="other-appearance")
        api.atomic_write(Path(args.save), api.dump_yaml(other))
        reject("cross_campaign_request_rejected", lambda: appearance.resolve(api, args))
        resolved, args = resolve(request, "appearance-one")
        candidate = api.load_yaml(Path(resolved["output"]))
        without = copy.deepcopy(candidate)
        without["world_state"]["appearance_customization"] = copy.deepcopy(unlocked["world_state"]["appearance_customization"])
        assert without == unlocked
        cases.append("candidate_changes_cosmetics_only_no_mechanics_or_relationship")
        forged_candidate = copy.deepcopy(candidate)
        forged_candidate["player"]["gold"] += 1
        assert appearance.validate_transition(api, unlocked, forged_candidate, "appearance-one")
        cases.append("extra_mechanical_change_rejected_at_commit_boundary")
        commit(Path(resolved["output"]), "appearance-one")
        committed = save.read_bytes()
        assert appearance.resolve(api, args)["idempotent"] and save.read_bytes() == committed
        cases.append("same_transaction_retry_is_idempotent")
        reject("consumed_request_cannot_be_reused", lambda: resolve(request, "appearance-again"))
        modified = api.load_yaml(Path(resolved["output"]))
        modified["world_state"]["appearance_customization"]["overrides"]["Lilith_000"]["hair"] = "異なる髪"
        candidate_bytes = Path(resolved["output"]).read_bytes()
        api.atomic_write(Path(resolved["output"]), api.dump_yaml(modified))
        reject("changed_committed_retry_rejected", lambda: appearance.resolve(api, args))
        Path(resolved["output"]).write_bytes(candidate_bytes)
        restored = propose(restore=True)
        restored_candidate, _ = resolve(restored, "appearance-restore")
        commit(Path(restored_candidate["output"]), "appearance-restore")
        current = api.load_yaml(save)
        assert not current["world_state"]["appearance_customization"]["overrides"]
        assert len(current["world_state"]["appearance_customization"]["resolutions"]) == 2
        cases.append("restore_removes_override_and_keeps_audit")
        mia = propose({"hair": "短い銀髪", "eyes": "緑色"}, "Mia_001")
        mia_candidate, _ = resolve(mia, "appearance-mia")
        commit(Path(mia_candidate["output"]), "appearance-mia")
        current = api.load_yaml(save)
        from_lilith, _ = state_view(current, ["turn"], subjects=["Lilith_000"])
        from_mia, _ = state_view(current, ["turn"], subjects=["Mia_001"])
        assert not from_lilith["world_state"]["appearance_customization"]["overrides"]
        assert from_mia["world_state"]["appearance_customization"]["overrides"] == {"Mia_001": {"hair": "短い銀髪", "eyes": "緑色"}}
        audit_view = from_lilith["world_state"]["appearance_customization"]["resolutions"]
        assert isinstance(audit_view, dict) and "recent" not in audit_view
        assert from_lilith["runtime_cast_rules"]["Lilith_000"]["lilith_intimacy_unlocked"] is True
        cases.append("ordinary_view_shows_only_current_named_override_and_keeps_lilith_gate")
        cleared = propose({"hair": None}, "Mia_001")
        cleared_candidate, _ = resolve(cleared, "appearance-mia-clear")
        commit(Path(cleared_candidate["output"]), "appearance-mia-clear")
        current = api.load_yaml(save)
        assert current["world_state"]["appearance_customization"]["overrides"]["Mia_001"] == {"eyes": "緑色"}
        cases.append("field_restore_preserves_other_cosmetic_changes")
        bad = copy.deepcopy(current)
        bad["world_state"]["appearance_customization"]["overrides"]["Mia_001"]["eyes"] = "未確認の変更"
        errors, _ = api.validate_save_data(bad)
        assert errors
        cases.append("override_without_matching_audit_is_invalid")
        assert all((clone / path).read_bytes() == original for path, original in canonical_before.items())
        cases.append("all_canonical_persona_bytes_are_unchanged")
        return {"ok": True, "cases": len(cases), "case_ids": cases, "read_only_source": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    try:
        result = check(parser.parse_args().root.resolve())
    except Exception as exc:
        result = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
