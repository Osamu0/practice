#!/usr/bin/env python3
"""Exercise the ordinary turn pipeline and retry boundaries in a disposable game."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
sys.dont_write_bytecode = True


def check(root):
    with tempfile.TemporaryDirectory(prefix="machadan-turn-flow-") as tmp:
        game = Path(tmp) / "machadan_spade"
        shutil.copytree(root.parent, game, ignore=shutil.ignore_patterns("state", "saves", "__pycache__", "*.pyc"))
        runtime = game / "muse版"
        sys.path.insert(0, str(runtime / "tools"))
        spec = importlib.util.spec_from_file_location("turn_flow_probe_runtime", runtime / "tools/machadan_runtime.py")
        api = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = api
        spec.loader.exec_module(api)
        parser = api.build_parser()
        def command(*args):
            parsed = parser.parse_args(list(map(str, args)))
            value = parsed.handler(parsed)
            if isinstance(value, tuple):
                if value[0]:
                    raise api.RuntimeProblem(str(value[1]))
                return value[1]
            return value
        save = runtime / "saves/probe.yaml"
        command("new-save", "--campaign-id", "flow-probe", "--output", save)
        before = save.read_bytes()
        context = runtime / "state/runtime/probe.context.md"
        prepared = context.with_suffix(".candidate.yaml")
        ready = command("begin-turn", "--scene", "event", "--phase", "probe", "--save", save,
                        "--output", context, "--candidate-save-output", prepared)
        assert ready["turn_check"]["ok"] and save.read_bytes() == before
        changes = prepared.with_suffix(".changes.json")
        payload = json.loads(changes.read_text())
        payload["operations"] = [{"op": "add", "path": "/world_state/campaign_lore/時計屋",
                                  "value": {"name": "時計屋", "confirmed": True}}]
        payload["response"] = {"schema": "machadan-response-v1", "main_text": "検証本文。" * 130,
                               "system_blocks": [], "choices": ["時計屋へ話しかける", "通りを見渡す"]}
        changes.write_text(json.dumps(payload, ensure_ascii=False))
        final = runtime / "state/runtime/probe.final.yaml"
        html = runtime / "state/runtime/probe.status.html"
        args = ("finish-turn", "--current", save, "--prepared", prepared, "--changes", changes,
                "--output", final, "--transaction-id", "flow-probe-one", "--turn", "1", "--status-output", html)
        import copy
        rejected = []
        for label, invalid in (("missing_response", None),
                               ("short_body", {**payload["response"], "main_text": "短い本文。"}),
                               ("long_body", {**payload["response"], "main_text": "長" * 801}),
                               ("missing_choices", {**payload["response"], "choices": []})):
            bad_payload = copy.deepcopy(payload)
            if invalid is None:
                bad_payload.pop("response", None)
            else:
                bad_payload["response"] = invalid
            changes.write_text(json.dumps(bad_payload, ensure_ascii=False))
            try:
                command(*args)
                raise AssertionError("invalid reply was committed: " + label)
            except api.RuntimeProblem:
                assert save.read_bytes() == before
                rejected.append(label)
        changes.write_text(json.dumps(payload, ensure_ascii=False))
        result = command(*args)
        committed = save.read_bytes()
        assert result["committed"] and html.exists()
        assert result["response_check"]["main_text_characters"] == 650
        assert result["choices_text"] == "1. 時計屋へ話しかける\n2. 通りを見渡す\n\n自由入力もできます。"
        assert "検証本文。" not in json.dumps(result, ensure_ascii=False)
        assert api.load_yaml(save)["world_state"]["campaign_lore"]["時計屋"]["name"] == "時計屋"
        assert "response" not in api.load_yaml(save)
        again = command(*args)
        assert again["committed"] and save.read_bytes() == committed
        payload["operations"][0]["value"]["name"] = "異なる店"
        changes.write_text(json.dumps(payload, ensure_ascii=False))
        try:
            command(*args)
            raise AssertionError("changed retry was accepted")
        except api.RuntimeProblem:
            assert save.read_bytes() == committed
        # The post-hearing flow must insert the grant and explanation exactly once.
        initial = runtime / "saves/opening.yaml"
        command("new-save", "--campaign-id", "opening-flow", "--output", initial)
        opening_data = api.load_yaml(initial)
        opening_data["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        opening_data.update(play_mode="RP", player_body="標準体格", ero_style="machadan")
        opening_data["partner_pref"]["asked"] = True
        actor = opening_data["player"]
        allocated = dict(zip(api.STAT_KEYS, (6, 6, 6, 5, 5, 5)))
        actor.update(name="開始テスト", age=30, base_stats=allocated, effective_stats=dict(allocated), stats=dict(allocated),
                     base_lp=20, lp={"cur": 20, "max": 20}, mp={"cur": 6, "max": 6})
        assert sum(allocated.values()) == 33
        assert opening_data["world_state"]["onboarding"]["allocation_rule"] == "all3-plus15-v1"
        opening_data["world_state"]["onboarding"].update(body_received=True, allocation_complete=True)
        api.atomic_write(initial, api.dump_yaml(opening_data))
        opening_ctx = runtime / "state/runtime/opening.md"
        opening_prepared = runtime / "state/runtime/opening.prepared.yaml"
        first = command("begin-turn", "--scene", "turn", "--save", initial,
                        "--output", opening_ctx, "--candidate-save-output", opening_prepared)
        assert first["onboarding"]["next_stage"] == "fire" and first["deferred_scene"] == "turn"
        receipt = json.loads(Path(first["receipt"]).read_text())
        assert any(row["source"].endswith("#SCRIPT_OPENING_FIRE") for row in receipt["sources"])
        assert any(row["resource"] == "NUMBERS" for row in receipt["sources"])
        fire = runtime / "state/runtime/fire.candidate.yaml"
        command("grant-fire", "--save", opening_prepared, "--output", fire, "--transaction-id", "opening-grant")
        command("commit-save", "--current", initial, "--candidate", fire,
                "--transaction-id", "opening-grant", "--turn", "0")
        granted = api.load_yaml(initial)
        assert granted["player"]["lp"] == {"cur": 32, "max": 32}
        assert granted["player"]["mp"] == {"cur": 9, "max": 9}
        assert granted["player"]["base_stats"] == allocated
        assert sum(granted["player"]["effective_stats"].values()) == 51
        next_prepared = runtime / "state/runtime/tutorial.prepared.yaml"
        tutorial = command("begin-turn", "--scene", "turn", "--save", initial,
                           "--output", runtime / "state/runtime/tutorial.md", "--candidate-save-output", next_prepared)
        assert tutorial["onboarding"]["next_stage"] == "tutorial"
        change = next_prepared.with_suffix(".changes.json")
        cp = json.loads(change.read_text())
        cp["operations"] = [{"op": "replace", "path": "/world_state/onboarding/tutorial_complete", "value": True}]
        cp["response"] = {"schema": "machadan-response-v1", "main_text": "リリスが街へ通じる扉を示した。",
                          "choices": ["ギルドへ向かう", "リリスに質問する"]}
        change.write_text(json.dumps(cp))
        command("finish-turn", "--current", initial, "--prepared", next_prepared, "--changes", change,
                "--output", runtime / "state/runtime/tutorial.final.yaml", "--transaction-id", "opening-tutorial", "--turn", "0")
        ordinary = command("begin-turn", "--scene", "turn", "--save", initial,
                           "--output", runtime / "state/runtime/ordinary.md",
                           "--candidate-save-output", runtime / "state/runtime/ordinary.prepared.yaml")
        assert ordinary["onboarding"]["next_stage"] == "complete" and "deferred_scene" not in ordinary
        assert api.load_yaml(initial)["player"]["fire_bonus"]["str"] == 3
        # Untagged old campaigns keep their original ALL5+15 allocation and
        # can finish the introduction without being relabelled as new ALL3+15.
        import copy
        from onboarding import status_data
        legacy_path = runtime / "saves/legacy-opening.yaml"
        legacy = copy.deepcopy(opening_data)
        legacy["campaign_id"] = "legacy-opening"
        legacy["game_version"] = "4.1.3"
        legacy["world_state"]["onboarding"].pop("allocation_rule", None)
        legacy_stats = dict(zip(api.STAT_KEYS, (8, 8, 8, 7, 7, 7)))
        legacy["player"].update(base_stats=legacy_stats, effective_stats=dict(legacy_stats), stats=dict(legacy_stats),
                                mp={"cur": 8, "max": 8})
        api.atomic_write(legacy_path, api.dump_yaml(legacy))
        command("migrate-save", legacy_path, "--in-place")
        migrated = api.load_yaml(legacy_path)
        assert "allocation_rule" not in migrated["world_state"]["onboarding"]
        assert migrated["player"]["base_stats"] == legacy_stats
        assert status_data(migrated)["next_stage"] == "fire"
        legacy_ctx = runtime / "state/runtime/legacy.md"
        legacy_prepared = runtime / "state/runtime/legacy.prepared.yaml"
        legacy_ready = command("begin-turn", "--scene", "turn", "--save", legacy_path,
                               "--output", legacy_ctx, "--candidate-save-output", legacy_prepared)
        assert legacy_ready["onboarding"]["next_stage"] == "fire"
        legacy_fire = runtime / "state/runtime/legacy-fire.yaml"
        command("grant-fire", "--save", legacy_prepared, "--output", legacy_fire, "--transaction-id", "legacy-grant")
        command("commit-save", "--current", legacy_path, "--candidate", legacy_fire,
                "--transaction-id", "legacy-grant", "--turn", "0")
        legacy_granted = api.load_yaml(legacy_path)
        assert legacy_granted["player"]["base_stats"] == legacy_stats
        assert legacy_granted["player"]["mp"] == {"cur": 11, "max": 11}
        assert legacy_granted["world_state"]["onboarding"]["allocation_rule"] == "legacy-all5-plus15-v1"
        assert legacy_granted["world_state"]["onboarding"]["initial_base_stats"] == legacy_stats
        legacy_granted["game_version"] = "4.1.3"
        tagged_migrated, _ = api.migrate_data(legacy_granted)
        assert tagged_migrated["world_state"]["onboarding"]["allocation_rule"] == "legacy-all5-plus15-v1"
        assert tagged_migrated["world_state"]["onboarding"]["initial_base_stats"] == legacy_stats
        # An older receipt may already have the 45-point snapshot but no tag.
        legacy_granted["world_state"]["onboarding"].pop("allocation_rule")
        legacy_granted["game_version"] = "4.1.3"
        api.atomic_write(legacy_path, api.dump_yaml(legacy_granted))
        command("migrate-save", legacy_path, "--in-place")
        old_receipt = api.load_yaml(legacy_path)
        assert "allocation_rule" not in old_receipt["world_state"]["onboarding"]
        assert old_receipt["world_state"]["onboarding"]["initial_base_stats"] == legacy_stats
        assert status_data(old_receipt)["next_stage"] == "tutorial"
        # A partially allocated legacy body must finish its original budget.
        partial_path = runtime / "saves/legacy-partial.yaml"
        partial = copy.deepcopy(legacy)
        partial["campaign_id"] = "legacy-partial"
        partial["world_state"]["onboarding"]["allocation_complete"] = False
        partial_stats = {key: 5 for key in api.STAT_KEYS}
        partial["player"].update(base_stats=partial_stats, effective_stats=dict(partial_stats), stats=dict(partial_stats),
                                 mp={"cur": 5, "max": 5})
        api.atomic_write(partial_path, api.dump_yaml(partial))
        command("migrate-save", partial_path, "--in-place")
        partial_migrated = api.load_yaml(partial_path)
        assert "allocation_rule" not in partial_migrated["world_state"]["onboarding"]
        assert partial_migrated["player"]["base_stats"] == partial_stats
        assert status_data(partial_migrated)["next_stage"] == "bonus"
        # A pre-onboarding save receives false flags, but no new budget tag.
        old_flags_path = runtime / "saves/legacy-no-flags.yaml"
        old_flags = copy.deepcopy(legacy)
        old_flags["campaign_id"] = "legacy-no-flags"
        old_flags["world_state"].pop("onboarding", None)
        api.atomic_write(old_flags_path, api.dump_yaml(old_flags))
        command("migrate-save", old_flags_path, "--in-place")
        old_flags_migrated = api.load_yaml(old_flags_path)
        saved_flags = old_flags_migrated["world_state"]["onboarding"]
        assert "allocation_rule" not in saved_flags
        assert all(saved_flags[key] is False for key in
                   ("body_received", "allocation_complete", "fire_granted", "fire_explained", "tutorial_complete"))
        assert status_data(old_flags_migrated)["allocation_rule"] == "legacy-all5-plus15-v1"
        assert status_data(old_flags_migrated)["next_stage"] == "fire"
        # Growth may increase today's stats beyond 45. The original recorded
        # allocation still identifies the legacy budget and is never rewritten.
        grown_path = runtime / "saves/legacy-grown.yaml"
        grown = copy.deepcopy(old_receipt)
        grown["campaign_id"] = "legacy-grown"
        grown["game_version"] = "4.1.3"
        grown["player"].update(build_complete=True, job="旅人")
        for key in ("base_stats", "effective_stats", "stats"):
            grown["player"][key]["str"] += 5
        grown_stats = copy.deepcopy(grown["player"]["base_stats"])
        api.atomic_write(grown_path, api.dump_yaml(grown))
        command("migrate-save", grown_path, "--in-place")
        grown_migrated = api.load_yaml(grown_path)
        assert "allocation_rule" not in grown_migrated["world_state"]["onboarding"]
        assert grown_migrated["world_state"]["onboarding"]["initial_base_stats"] == legacy_stats
        assert grown_migrated["player"]["base_stats"] == grown_stats
        assert status_data(grown_migrated)["allocation_rule"] == "legacy-all5-plus15-v1"
        assert status_data(grown_migrated)["next_stage"] == "complete"
        # A bad source is rejected before a turn can be narrated/committed.
        card = runtime / "運用/毎ターンの約束.md"
        card.write_text(card.read_text() + "\nchanged\n")
        try:
            command("begin-turn", "--scene", "turn", "--save", save,
                    "--output", runtime / "state/runtime/bad.md",
                    "--candidate-save-output", runtime / "state/runtime/bad.yaml")
            raise AssertionError("modified canonical source was accepted")
        except api.RuntimeProblem:
            assert save.read_bytes() == committed
        return {"ok": True, "cases": 16 + len(rejected) + 3, "checks": [*rejected,
                "reply count and action footer", "no duplicate prose in tool result", "reply stays outside the save",
                "read-only begin", "lossless commit",
                "same-transaction retry", "changed retry rejected", "damaged source rejected",
                "mandatory fire source routing", "grant and exact numeric commit",
                "tutorial follows grant", "completed opening does not replay",
                "new ALL3+15 allocation and exact fire resources", "legacy ALL5+15 grant preserved",
                "legacy snapshot migration keeps original rule", "legacy partial allocation is not retagged",
                "explicit legacy allocation rule preserved", "legacy default flags do not adopt new budget",
                "grown legacy actor retains original allocation receipt"]}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(check(p.parse_args().root.resolve()), ensure_ascii=False))
