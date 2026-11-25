#!/usr/bin/env python3
"""Exercise real context assembly in a disposable copy, never live state."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile


def check(root: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="machadan-route-check-") as temporary:
        temporary = Path(temporary)
        game = temporary / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns(
            "saves", "state", "runtime", "__pycache__", "*.pyc"))
        for name in ("VERSION.txt", "RUNTIME_MANIFEST.json"):
            if (root.parent / name).is_file():
                shutil.copy2(root.parent / name, game / name)
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("machadan_route_probe_runtime", clone / "tools/machadan_runtime.py")
        rt = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = rt
        spec.loader.exec_module(rt)
        parser = rt.build_parser()

        def command(arguments):
            args = parser.parse_args(list(map(str, arguments)))
            result = args.handler(args)
            if isinstance(result, tuple):
                if result[0]:
                    raise rt.RuntimeProblem(str(result[1]))
                return result[1]
            return result

        save = temporary / "route-probe.yaml"
        command(["new-save", "--output", save, "--campaign-id", "route-probe"])
        data = rt.load_yaml(save)
        data["world_state"]["location"] = "ミアの店"
        member = copy.deepcopy(data["player"])
        member.update(character_id="Mia_001", name="ミア", age=19, gender="female")
        data["party"] = [member]
        rt.atomic_write(save, rt.dump_yaml(data))
        routes = rt.load_yaml(clone / "運用/ルーティング表.yaml")
        checked = []
        lengths = {}

        def context(label, scene, *extra):
            output = temporary / (label + ".md")
            result = command(["prepare-context", "--scene", scene, "--save", save,
                              "--output", output, *extra])
            receipt = json.loads(output.with_suffix(".md.receipt.json").read_text())
            if not result.get("ok") or not output.read_text().strip():
                raise rt.RuntimeProblem("empty/failed context: " + label)
            # No source can be emitted both in full and in partial form.
            rows = receipt["sources"]
            for row in rows:
                path = row["source"].split("#", 1)[0]
                if row["mode"] == "full" and any(
                    other is not row and other["source"].split("#", 1)[0] == path for other in rows
                ):
                    raise rt.RuntimeProblem("duplicated full/partial source: " + path)
            lengths[label] = result["characters"]
            return result, receipt

        for scene, pack in routes["scene_packs"].items():
            _, receipt = context(scene, scene, "--enemy", "スライム", "--item", "薬草")
            loaded = {row["resource"] for row in receipt["sources"]}
            expected = {row["resource"] for row in pack.get("required", []) if row.get("resource")
                        and (row.get("mode") == "full" or row.get("selectors"))}
            expected.add("TURN_CONTRACT")
            expected.add("STYLE_CARD")
            missing = expected - loaded
            if missing:
                raise rt.RuntimeProblem(f"scene {scene} misses required content: {sorted(missing)}")
            common_style = next(e for e in routes["base_pack"]["required"]
                                if e.get("resource") == "STYLE_CARD")
            style_rows = [row for row in receipt["sources"] if row["resource"] == "STYLE_CARD"]
            if not any(row["mode"] == "full" for row in style_rows):
                loaded_style_ids = {row["source"].partition("#")[2] for row in style_rows}
                needed_style_ids = {s["id"] for s in common_style["selectors"]}
                if not needed_style_ids <= loaded_style_ids:
                    raise rt.RuntimeProblem(f"scene {scene} misses common prose style sections")
            if not any(row["source"] == "人格/Mia.md" for row in receipt["sources"]):
                raise rt.RuntimeProblem("v3 party character_id did not load Mia persona")
            checked.append(scene)
        # Shopkeeper inference must work without a party or explicit --character.
        data["party"] = []
        rt.atomic_write(save, rt.dump_yaml(data))
        _, receipt = context("shopkeeper", "shop")
        if not any(row["source"] == "人格/Mia.md" for row in receipt["sources"]):
            raise rt.RuntimeProblem("location did not load its shopkeeper persona")
        data["world_state"]["location"] = "旅先で初めて訪れた道具屋"
        rt.atomic_write(save, rt.dump_yaml(data))
        _, receipt = context("original_shop", "shop")
        if any(row["source"] == "人格/Mia.md" for row in receipt["sources"]):
            raise rt.RuntimeProblem("a new shop was incorrectly assigned the canonical shopkeeper")
        _, receipt = context("unknown_subject", "turn", "--location", "未設定の時計屋",
                             "--character", "NewClockmaker", "--item", "未設定の時計部品",
                             "--condition", "new_story_action")
        if not any(note["kind"] == "undefined_subject" for note in receipt["reference_notes"]):
            raise rt.RuntimeProblem("unknown fictional subject did not remain a creative opening")
        context("dungeon_combat", "dungeon", "--include-scene", "combat")
        context("production_request", "quest", "--condition", "production_request")
        # Semantic boundaries are source headings, never line/character caps.
        # A missing endpoint must fail this installation test even though live
        # assembly can recover conservatively with the same full source.
        from context_loader import semantic_span, project_inventory, location_kind
        from save_changes import state_view
        _, _, resources = rt.load_control()
        phase_spans = 0
        for resource, profile in routes.get("phase_loading", {}).get("profiles", {}).items():
            source_text = (clone / resources[resource]["path"]).read_text()
            spans = list(profile.get("common", []))
            for group in ("phases", "conditions", "rank_sections"):
                for specifications in profile.get(group, {}).values():
                    spans.extend(specifications)
            for specification in spans:
                semantic_span(source_text, specification)
                phase_spans += 1
        _, probe_receipt = context("event_probe", "event", "--phase", "probe")
        if probe_receipt.get("phase") != "probe" or {"EVENT_INVENTORY_STATE", "ENCOUNTERS"} & {
                row["resource"] for row in probe_receipt["sources"]}:
            raise rt.RuntimeProblem("event probe loaded stock/materials before an occurrence")
        _, expanded_receipt = context("event_expanded", "event", "--phase", "create")
        if "EVENT_INVENTORY_STATE" not in {row["resource"] for row in expanded_receipt["sources"]}:
            raise rt.RuntimeProblem("expanded event lost its selected inventory source")
        _, no_card_receipt = context("quest_no_card", "quest", "--phase", "advance")
        if no_card_receipt.get("phase") != "create":
            raise rt.RuntimeProblem("uncommitted quest skipped generation requirements")
        phase_data = copy.deepcopy(data)
        card = {"quest_id": "Q-phase", "client": "昔の依頼人", "fixed_facts": ["原因は固定"],
                "progress": {"status": "active"}, "amendments": [],
                "reward_contract": {"settlement_id": "phase-reward", "offered": False,
                                    "payer": "昔の依頼人", "components": [], "delivery_plan": []}}
        card["immutable_hash"] = rt._quest_hash(card)
        phase_data["world_state"]["quest_card"] = card
        phase_data["world_state"]["campaign_lore"] = {
            "古い約束": {"kind": "promise", "status": "pending", "text": "遠方へ薬を届ける約束"},
            "古い人物設定": {"character_id": "Nell_011", "text": "魔女が覚えている合言葉"},
            "古い依頼人設定": {"npc": "昔の依頼人", "text": "受注前に決めた事情"},
            **{f"最近の別件{i}": {"text": "別の場所の記録"} for i in range(20)}}
        before_lore = copy.deepcopy(phase_data)
        view, _ = state_view(phase_data, ["quest"], subjects=["Nell_011"])
        if not {"古い約束", "古い人物設定", "古い依頼人設定"} <= set(
                view["world_state"]["campaign_lore"]["entries"]):
            raise rt.RuntimeProblem("bounded view lost an old promise/current cast/quest fact")
        if phase_data != before_lore:
            raise rt.RuntimeProblem("bounded view mutated the complete save")
        phase_save = temporary / "phase-save.yaml"
        rt.atomic_write(phase_save, rt.dump_yaml(phase_data))
        phase_lengths = {}
        for phase in ("auto", "create", "advance", "settle"):
            output = temporary / ("quest-phase-" + phase + ".md")
            result = command(["prepare-context", "--scene", "quest", "--save", phase_save,
                              "--output", output, "--phase", phase,
                              "--character", "Nell_011", "--condition", "production_request"])
            receipt = json.loads(output.with_suffix(".md.receipt.json").read_text())
            text = output.read_text()
            if any(note["kind"] == "phase_selector_recovered" for note in receipt["reference_notes"]):
                raise rt.RuntimeProblem("phase selector unexpectedly fell back to full source")
            if phase == "auto" and receipt["phase"] != "advance":
                raise rt.RuntimeProblem("committed quest card did not select advance automatically")
            if "遠方へ薬を届ける約束" not in text or "魔女が覚えている合言葉" not in text:
                raise rt.RuntimeProblem("current quest context lost old continuity facts")
            if not {"QUEST_DESIGN", "QUEST_PARTS", "QUEST_GUILD", "ENTERPRISE", "ITEMS", "SKILLS"} <= {
                    row["resource"] for row in receipt["sources"]}:
                raise rt.RuntimeProblem("phase optimization dropped a production dependency")
            style_ids = {row["source"].partition("#")[2] for row in receipt["sources"]
                         if row["resource"] == "STYLE_CARD"}
            expected_style = {selector["id"] for entry in routes["base_pack"]["required"]
                              if entry.get("resource") == "STYLE_CARD" for selector in entry["selectors"]}
            if not expected_style <= style_ids:
                raise rt.RuntimeProblem("phase optimization lost common prose rules")
            phase_lengths[phase] = result["characters"]
        if phase_lengths["advance"] >= phase_lengths["create"]:
            raise rt.RuntimeProblem("quest advance reloaded the entire creation pack")
        named_output = temporary / "quest-named-equipment.md"
        command(["prepare-context", "--scene", "quest", "--save", phase_save,
                 "--output", named_output, "--phase", "advance", "--condition", "production_request",
                 "--item", "WEAPONS", "--condition", "ability_fruit_resolution"])
        named_text = named_output.read_text()
        named_receipt = json.loads(named_output.with_suffix(".md.receipt.json").read_text())
        if not any(row["resource"] == "ITEMS" and row["source"].endswith("#WEAPONS") for row in named_receipt["sources"]):
            raise rt.RuntimeProblem("phase-specific item loading omitted an explicitly requested item category")
        if "GUILD_FRUIT_SUPPLY" not in named_text:
            raise rt.RuntimeProblem("ability fruit resolution lost guild supply exceptions")
        original_routes = (clone / "運用/ルーティング表.yaml").read_text()
        changed_routes = copy.deepcopy(routes)
        changed_routes["phase_loading"]["profiles"]["QUEST_DESIGN"]["common"][0]["start"] = "## MISSING_HEADING"
        rt.atomic_write(clone / "運用/ルーティング表.yaml", rt.dump_yaml(changed_routes))
        try:
            fallback_output = temporary / "phase-fallback.md"
            command(["prepare-context", "--scene", "quest", "--save", phase_save,
                     "--output", fallback_output, "--phase", "advance"])
            fallback = json.loads(fallback_output.with_suffix(".md.receipt.json").read_text())
            if not any(row["resource"] == "QUEST_DESIGN" and row["mode"] == "full"
                       for row in fallback["sources"]):
                raise rt.RuntimeProblem("missing phase heading did not recover from the canonical full source")
        finally:
            rt.atomic_write(clone / "運用/ルーティング表.yaml", original_routes)
        # Combat exceptions remain present when the encounter is already active.
        _, combat_receipt = context("combat_advance", "combat", "--phase", "advance", "--enemy", "スライム")
        combat_text = (temporary / "combat_advance.md").read_text()
        for required in ("Evasion Focus", "LP0", "No_Mercy_Protocol", "Phase D", "最低2"):
            if required not in combat_text:
                raise rt.RuntimeProblem("combat advance lost a core rule/exception: " + required)
        road_kind = location_kind(type("Args", (), {"location_kind": None})(),
                                  {"location": "町から続く街道"}, ["event"])
        stock = {"schema": "test", "kind": "events", "limits": {"town": 15, "road": 15, "dungeon": 15},
                 "entries": [{"id": "town", "category": "town", "status": "unused"},
                             {"id": "road", "category": "road", "status": "unused", "campaign_id": "here"},
                             {"id": "other", "category": "road", "status": "unused", "campaign_id": "elsewhere"}]}
        projected = project_inventory(stock, "EVENT_INVENTORY_STATE", road_kind, "here")
        if road_kind != "road" or [item["id"] for item in projected["entries"]] != ["road"]:
            raise rt.RuntimeProblem("road projection mixed town or another campaign's stock")
        _, road_receipt = context("road_event", "event", "--phase", "create", "--location-kind", "road")
        if road_receipt.get("location_kind") != "road":
            raise rt.RuntimeProblem("explicit location kind was not carried into the receipt")
        # All output aliases must be rejected before any file initialization or
        # write can destroy the committed YAML or a read-only canonical source.
        alias_cases = [
            ["--output", save],
            ["--output", temporary / "alias.md", "--candidate-save-output", save],
            ["--output", temporary / "same.md", "--candidate-save-output", temporary / "same.md"],
            ["--output", temporary / "alias.md", "--candidate-save-output", temporary / "alias.md.receipt.json"],
            ["--output", clone / "saves/generated.md"],
            ["--output", clone / "運用/コア運用ルール.md"],
        ]
        save_bytes = save.read_bytes()
        core_bytes = (clone / "運用/コア運用ルール.md").read_bytes()
        for options in alias_cases:
            try:
                command(["prepare-context", "--scene", "turn", "--save", save, *options])
            except rt.RuntimeProblem:
                pass
            else:
                raise rt.RuntimeProblem("unsafe context path alias/canonical overwrite was accepted")
            if save.read_bytes() != save_bytes or (clone / "運用/コア運用ルール.md").read_bytes() != core_bytes:
                raise rt.RuntimeProblem("rejected context paths changed committed/canonical bytes")
        for kind in ("receipt", "changes"):
            alias_source = temporary / ("derived.md.receipt.json" if kind == "receipt" else "derived.changes.json")
            rt.atomic_write(alias_source, save_bytes.decode())
            options = (["--output", temporary / "derived.md"] if kind == "receipt" else
                       ["--output", temporary / "derived-output.md", "--candidate-save-output", temporary / "derived.yaml"])
            try:
                command(["prepare-context", "--scene", "turn", "--save", alias_source, *options])
            except rt.RuntimeProblem:
                pass
            else:
                raise rt.RuntimeProblem("derived receipt/changes path aliased the source save")
            if alias_source.read_bytes() != save_bytes:
                raise rt.RuntimeProblem("derived output overwrote the save")
        # Real v3 histories are nested dictionaries, not top-level arrays.
        history_data = copy.deepcopy(data)
        history_data["session_log"] = {"previous": "過去ログの保存本文。" * 500,
                                       "entries": [{"day": 1, "text": f"過去の出来事{i}"} for i in range(180)]}
        history_data["memory_log"] = {name: [{"day": 1, "text": f"記憶{i}"} for i in range(180)]
                                      for name in ("encounters", "battles", "ero", "turning_points")}
        before_history = copy.deepcopy(history_data)
        history_view, omitted = state_view(history_data, ["turn"])
        for pointer in ("/session_log/entries", "/session_log/previous", "/memory_log/encounters",
                        "/memory_log/battles", "/memory_log/ero", "/memory_log/turning_points"):
            from save_changes import read_pointer
            if read_pointer(history_view, pointer).get("read_full_at") != pointer or pointer not in omitted:
                raise rt.RuntimeProblem("nested history did not expose its exact full-save pointer")
        if history_data != before_history:
            raise rt.RuntimeProblem("history projection altered the complete source")
        history_save = temporary / "long-history.yaml"
        rt.atomic_write(history_save, rt.dump_yaml(history_data))
        history_prepared = temporary / "long-history-prepared.yaml"
        prepared_info = command(["prepare-context", "--scene", "turn", "--save", history_save,
                                 "--output", temporary / "long-history.md", "--candidate-save-output", history_prepared])
        history_changes = temporary / "long-history-patch.json"
        history_changes.write_text(json.dumps({"schema": "machadan-save-changes-v1",
            "save_revision": prepared_info["save_revision"], "save_sha256": prepared_info["save_sha256"],
            "operations": [{"op": "add", "path": "/world_state/campaign_lore/履歴保存確認", "value": "現在の追加事実"}]}))
        history_final = temporary / "long-history-final.yaml"
        command(["apply-changes", "--current", history_save, "--prepared", history_prepared,
                 "--changes", history_changes, "--output", history_final])
        command(["commit-save", "--current", history_save, "--candidate", history_final,
                 "--transaction-id", "history-lossless-probe", "--turn", "0"])
        committed_history = rt.load_yaml(history_save)
        if any(committed_history[key] != before_history[key] for key in ("session_log", "memory_log")):
            raise rt.RuntimeProblem("ordinary commit lost old nested history")
        debt_projection, _ = state_view({"debt_state": {"collection_ledger": list(range(100))}}, ["turn"])
        if debt_projection["debt_state"]["collection_ledger"]["read_full_at"] != "/debt_state/collection_ledger":
            raise rt.RuntimeProblem("canonical debt collection ledger remained unbounded")
        allocation_projection, allocation_omitted = state_view({"world_state": {"allocation_state":
            {"version": 1, "resolutions": [{"request_id": f"historic-{i}"} for i in range(100)]}}}, ["turn"])
        projected = allocation_projection["world_state"]["allocation_state"]["resolutions"]
        if projected.get("total") != 100 or len(projected.get("recent", [])) != 2 or "/world_state/allocation_state/resolutions" not in allocation_omitted:
            raise rt.RuntimeProblem("allocation history remained unbounded in ordinary context")
        # The same saved world fact must survive the lossless change pipeline.
        prepared = temporary / "prepared.yaml"
        result = command(["prepare-context", "--scene", "turn", "--save", save,
                          "--output", temporary / "change-context.md", "--candidate-save-output", prepared])
        changes = temporary / "changes.json"
        changes.write_text(json.dumps({"schema": "machadan-save-changes-v1",
            "save_revision": result["save_revision"], "save_sha256": result["save_sha256"],
            "operations": [{"op": "add", "path": "/world_state/campaign_lore/時計屋",
                            "value": {"name": "路地の時計屋", "owner": "時計職人", "confirmed": True}}]}, ensure_ascii=False))
        final = temporary / "final.yaml"
        command(["apply-changes", "--current", save, "--prepared", prepared,
                 "--changes", changes, "--output", final])
        command(["commit-save", "--current", save, "--candidate", final,
                 "--transaction-id", "route-probe-lore", "--turn", "0"])
        value = command(["read-save", "--save", save, "--pointer", "/world_state/campaign_lore/時計屋"])
        if value["value"]["name"] != "路地の時計屋":
            raise rt.RuntimeProblem("campaign fact did not survive commit")
        # Verify document routing only: no prose or story content is generated.
        dedicated_cases = 0
        original = rt.load_yaml(save)
        for mode in ("machadan", "rabilabi"):
            mode_save = temporary / ("profile-" + mode + ".yaml")
            mode_data = copy.deepcopy(original)
            mode_data["ero_style"] = mode
            rt.atomic_write(mode_save, rt.dump_yaml(mode_data))

            def profile_context(label, *options):
                output = temporary / (mode + "-" + label + ".md")
                candidate = temporary / (mode + "-" + label + ".yaml")
                result = command(["prepare-context", "--scene", "turn", "--save", mode_save,
                                  "--output", output, "--candidate-save-output", candidate, *options])
                receipt = json.loads(output.with_suffix(".md.receipt.json").read_text())
                return result, receipt, candidate

            def require_profile(receipt, active, extra=False):
                resources = {row["resource"] for row in receipt["sources"]}
                full = {row["resource"] for row in receipt["sources"] if row["mode"] == "full"}
                if receipt.get("ero_scene") is not active or receipt.get("ero_style") != mode:
                    raise rt.RuntimeProblem("prose scene state or saved mode was lost")
                if active and not {"STYLE_CARD", "INTIMATE_RULES", "STYLE_DICTIONARY"} <= full:
                    raise rt.RuntimeProblem("dedicated prose documents were not loaded in full")
                if ("YURI_STYLE" in resources) != extra:
                    raise rt.RuntimeProblem("conditional style document was not retained/reset correctly")
                if not active and {"INTIMATE_RULES", "STYLE_DICTIONARY", "YURI_STYLE"} & resources:
                    raise rt.RuntimeProblem("dedicated style leaked into a completed ordinary scene")

            _, receipt, candidate = profile_context("entry", "--intimate-scene", "on", "--condition", "yuri")
            require_profile(receipt, True, True)
            command(["commit-save", "--current", mode_save, "--candidate", candidate,
                     "--transaction-id", "profile-entry-" + mode, "--turn", "0"])
            dedicated_cases += 1
            _, receipt, _ = profile_context("continued")
            require_profile(receipt, True, True)
            dedicated_cases += 1
            _, receipt, _ = profile_context("changed-condition", "--intimate-scene", "on")
            require_profile(receipt, True, False)
            dedicated_cases += 1
            _, receipt, candidate = profile_context("exit", "--intimate-scene", "off")
            require_profile(receipt, False, False)
            command(["commit-save", "--current", mode_save, "--candidate", candidate,
                     "--transaction-id", "profile-exit-" + mode, "--turn", "0"])
            _, receipt, _ = profile_context("ordinary-again")
            require_profile(receipt, False, False)
            dedicated_cases += 2
        legacy = copy.deepcopy(original)
        legacy["runtime_state"].pop("ero_scene", None)
        legacy["runtime_state"].pop("style_conditions", None)
        legacy["runtime_state"]["active_scene"] = "ero"
        legacy_save = temporary / "legacy-profile.yaml"
        rt.atomic_write(legacy_save, rt.dump_yaml(legacy))
        legacy_output = temporary / "legacy-profile.md"
        command(["prepare-context", "--scene", "resume", "--save", legacy_save, "--output", legacy_output])
        legacy_receipt = json.loads(legacy_output.with_suffix(".md.receipt.json").read_text())
        if legacy_receipt.get("ero_scene") is not True or "style" not in legacy_receipt["included_scenes"]:
            raise rt.RuntimeProblem("legacy prose-scene resume did not load the dedicated documents")
        dedicated_cases += 1
        seed_output = temporary / "voice-documents.md"
        command(["prepare-context", "--scene", "style", "--save", save, "--output", seed_output,
                 "--condition", "needs_voice_seed"])
        seed_receipt = json.loads(seed_output.with_suffix(".md.receipt.json").read_text())
        if not {"VOICE_A", "VOICE_B", "VOICE_C"} <= {row["resource"] for row in seed_receipt["sources"]}:
            raise rt.RuntimeProblem("requested voice references were omitted without a topic filter")
        dedicated_cases += 1
        return {"ok": True, "scenes": len(checked), "scene_ids": checked,
                "additional_cases": 6, "common_style_checked_scenes": len(checked),
                "dedicated_style_cases": dedicated_cases,
                "phase_cases": 12, "semantic_spans": phase_spans,
                "unsafe_path_cases": len(alias_cases) + 2, "nested_history_cases": 8,
                "phase_context_characters": phase_lengths,
                "context_characters": lengths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
