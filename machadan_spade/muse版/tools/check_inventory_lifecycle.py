#!/usr/bin/env python3
"""Exercise refill lifecycle only in a disposable runtime copy."""
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


def check(root: Path) -> dict:
    count = 0
    with tempfile.TemporaryDirectory(prefix="machadan-stock-check-") as temporary:
        game = Path(temporary) / "machadan_spade"
        clone = game / "muse版"
        shutil.copytree(root, clone, ignore=shutil.ignore_patterns(
            "saves", "state", "runtime", "__pycache__", "*.pyc"))
        for name in ("VERSION.txt", "RUNTIME_MANIFEST.json"):
            if (root.parent / name).is_file():
                shutil.copy2(root.parent / name, game / name)
        sys.path.insert(0, str(clone / "tools"))
        spec = importlib.util.spec_from_file_location("machadan_inventory_probe_runtime", clone / "tools/machadan_runtime.py")
        rt = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = rt
        spec.loader.exec_module(rt)
        spec2 = importlib.util.spec_from_file_location("machadan_inventory_probe_lifecycle", clone / "tools/inventory_lifecycle.py")
        lifecycle = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(lifecycle)

        def reject(call, message):
            try:
                call()
            except rt.RuntimeProblem:
                return
            raise AssertionError(message)

        def tree():
            return {p.relative_to(clone).as_posix(): p.read_bytes()
                    for p in clone.rglob("*") if p.is_file()}

        before = tree()
        empty_status = lifecycle.status(rt)
        assert empty_status["mobs"]["students"]["total"] == 0
        assert tree() == before, "status created files"
        count += 1

        lifecycle.initialize(rt)
        assert all(not rt.load_yaml(path)["entries"] for path in (rt.MOBS_PATH, rt.EVENTS_PATH))
        assert "dungeon" in rt.load_yaml(rt.EVENTS_PATH)["limits"]
        count += 1

        save_path = clone / "saves" / "stock-check.yaml"
        rt.cmd_new_save(SimpleNamespace(output=str(save_path), campaign_id="stock-check", force=False))
        save_bytes = save_path.read_bytes()
        turn_journal = clone / "saves" / "_transactions" / "turn.json"
        rt.atomic_write(turn_journal, '{"preserve": true}\n')
        old = rt.load_yaml(rt.EVENTS_PATH)
        old["limits"].pop("dungeon")
        old.pop("generation", None)
        rt.atomic_write(rt.EVENTS_PATH, rt.dump_yaml(old))
        append_journal = rt.EVENTS_PATH.parent / "_transactions" / "old.json"
        rt.atomic_write(append_journal, '{"schema":"machadan-inventory-append-transaction-v1"}\n')
        old_payload = clone / "state" / "runtime" / "old.json"
        legacy_payload = clone / "tools" / "runtime" / "old-refill.json"
        work_payload = clone / "state" / "runtime" / "keep.json"
        rt.atomic_write(old_payload, '{"schema":"machadan-inventory-append-v1"}\n')
        rt.atomic_write(legacy_payload, '{"schema":"machadan-inventory-append-v1"}\n')
        rt.atomic_write(work_payload, '{"schema":"machadan-save-changes-v1"}\n')
        reset_args = SimpleNamespace(reason="package-upgrade", generation=lifecycle._version(rt))
        reset_result = lifecycle.reset(rt, reset_args)
        assert not reset_result["idempotent"]
        assert "dungeon" in rt.load_yaml(rt.EVENTS_PATH)["limits"]
        assert save_path.read_bytes() == save_bytes and turn_journal.is_file() and work_payload.is_file()
        assert not append_journal.exists() and not old_payload.exists() and not legacy_payload.exists()
        count += 1

        states = lifecycle._read_states(rt)
        states["events"]["applied_runs"].append("keep-receipt")
        rt.atomic_write(rt.EVENTS_PATH, rt.dump_yaml(states["events"]))
        assert lifecycle.reset(rt, reset_args)["idempotent"]
        assert "keep-receipt" in rt.load_yaml(rt.EVENTS_PATH)["applied_runs"]
        count += 1

        output = clone / "state" / "runtime" / "request.json"
        args = SimpleNamespace(save=str(save_path), output=str(output), max=8, force=True, location_kind="town")
        result = lifecycle.template(rt, args)
        assert result["status"] == "waiting" and result["requested_total"] == 0
        pending = json.loads(output.read_text())
        assert not pending["context"]["profile"]["partner_preferences"]
        before = tree()
        request = lifecycle.refill_request(rt, save_path)
        assert request["status"] == "waiting" and not request["blocking"] and tree() == before
        assert lifecycle.template(rt, SimpleNamespace(save=None, max=8))["status"] == "needs_campaign"
        count += 1

        save = rt.load_yaml(save_path)
        save["hearing_progress"].update(status="complete", current_step=7,
            completed_steps=["playmode", "profile", "body_profile", "desire", "partner", "style"])
        save["play_mode"] = "RP"
        save["ero_style"] = "machadan"
        save["player_body"] = "標準"
        save["player"].update(name="Probe", gender="male", age=40)
        save["partner_pref"]["asked"] = True
        rt.atomic_write(save_path, rt.dump_yaml(save))
        result = lifecycle.template(rt, args)
        assert result["readiness"]["mobs"] and not result["readiness"]["events"]
        assert result["requested_total"] == 5
        payload = json.loads(output.read_text())
        assert payload["context"]["profile"]["partner_preferences"]["personalities"] == []
        count += 1

        player = save["player"]
        player.update(build_complete=True, job="職人", base_lp=20, lp={"cur": 20, "max": 20})
        player["base_stats"] = {key: 1 for key in rt.STAT_KEYS}
        player["effective_stats"] = copy.deepcopy(player["base_stats"])
        player["stats"] = copy.deepcopy(player["base_stats"])
        player["mp"] = {"cur": 1, "max": 1}
        rt.atomic_write(save_path, rt.dump_yaml(save))
        result = lifecycle.template(rt, args)
        assert result["readiness"]["events"] and result["requested_total"] == 6
        payload = json.loads(output.read_text())
        context = payload["context"]
        payload["run_id"] = "refill-test"
        payload["events"] = [{"id": context["id_prefix"] + "event-1", "category": "town", "title": "Probe", "status": "unused",
                               "campaign_id": save["campaign_id"], "generation": context["generation"], "description": "Probe"}]
        states = lifecycle._read_states(rt)
        before = tree()
        lifecycle.append_guard(rt, payload, states)
        lifecycle.append_guard(rt, payload, states)
        assert tree() == before, "guard changed state on retry"
        count += 1

        candidate = clone / "state" / "runtime" / "candidate.yaml"
        rt.atomic_write(candidate, rt.dump_yaml(save))
        reject(lambda: lifecycle.template(rt, SimpleNamespace(save=str(candidate), output=str(output), max=8, force=True)),
               "uncommitted candidate triggered refill")
        stale = copy.deepcopy(payload)
        stale["context"]["generation"] = "old-generation"
        reject(lambda: lifecycle.append_guard(rt, stale, states), "stale stock generation accepted")
        wrong_id = copy.deepcopy(payload)
        wrong_id["events"][0]["id"] = "EV-S01"
        reject(lambda: lifecycle.append_guard(rt, wrong_id, states), "old id was reused")
        count += 1

        changed = copy.deepcopy(save)
        changed["partner_pref"]["call"] = ["名前"]
        rt.atomic_write(save_path, rt.dump_yaml(changed))
        reject(lambda: lifecycle.append_guard(rt, payload, states), "changed confirmed preferences accepted old refill")
        rt.atomic_write(save_path, rt.dump_yaml(save))
        count += 1

        changed = copy.deepcopy(save)
        changed["world_state"]["location"] = "Different place"
        rt.atomic_write(save_path, rt.dump_yaml(changed))
        reject(lambda: lifecycle.append_guard(rt, payload, states), "changed location accepted old refill")
        rt.atomic_write(save_path, rt.dump_yaml(save))
        count += 1

        _, _, resources = rt.load_control()
        save["world_state"]["depth"] = 1
        rt.atomic_write(save_path, rt.dump_yaml(save))
        args.location_kind = "dungeon"
        lifecycle.template(rt, args)
        payload = json.loads(output.read_text())
        context = payload["context"]
        payload["run_id"] = "refill-canonical-test"
        seed_id = resources["EVENT_INVENTORY_STATE"]["initialize_from"]
        seed = rt.inventory_from_markdown(rt.ROOT / resources[seed_id]["path"], "events", seed_id)
        canonical = copy.deepcopy(next(item for item in seed["entries"] if item["id"] == "EV-D10"))
        canonical.update(id=context["id_prefix"] + "EV-D10", canonical_seed_id="EV-D10",
                         campaign_id=save["campaign_id"], generation=context["generation"])
        payload["events"] = [canonical]
        lifecycle.append_guard(rt, payload, states)
        canonical["fields"]["導入"] = "rewritten"
        reject(lambda: lifecycle.append_guard(rt, payload, states), "forged EV-D10 content accepted")
        count += 1

        # Exercise the real supplied seed parser, contextual copier, and guard.
        # Formerly EV-DE headings were silently merged into the previous entry.
        ids = {item["id"] for item in seed["entries"]}
        assert all("EV-DE%02d" % number in ids for number in range(1, 7))
        assert len(seed["entries"]) == 55
        from event_connections import requirements, unmet
        from context_loader import project_inventory
        for number, first, last in [(1, 1, 3), (2, 3, 6), (3, 4, 9), (4, 2, 9), (5, 1, 9), (6, 3, 9)]:
            item = next(entry for entry in seed["entries"] if entry["id"] == "EV-DE%02d" % number)
            rule = requirements(item)
            assert (rule["type"], rule["floor_min"], rule["floor_max"]) == (11, first, last)
            context = {"current_floor": first, "companion_ids": ["ally"]}
            assert not unmet(item, context)
            context["current_floor"] = 10
            assert "current_floor" in unmet(item, context)
        count += 1

        args.event_seed = "EV-DE01"
        lifecycle.template(rt, args)
        payload = json.loads(output.read_text())
        payload["run_id"] = "refill-de-test"
        assert payload["events"][0]["canonical_seed_id"] == "EV-DE01"
        lifecycle.append_guard(rt, payload, states)
        wrong = copy.deepcopy(payload)
        wrong["events"][0]["fields"]["導入"] = "rewritten"
        reject(lambda: lifecycle.append_guard(rt, wrong, states), "modified supplement accepted as exact copy")
        wrong = copy.deepcopy(payload)
        wrong["events"][0]["description"] = "alternate content"
        reject(lambda: lifecycle.append_guard(rt, wrong, states), "alternate scene content bypassed canonical copy guard")
        args.event_seed = "EV-DE02"
        reject(lambda: lifecycle.template(rt, args), "wrong-floor seed was offered")
        args.event_seed = "EV-DE05"
        reject(lambda: lifecycle.template(rt, args), "companion event was offered while solo")
        count += 1

        # A complete append uses the unchanged stock transaction and is retryable.
        rt.atomic_write(output, json.dumps(payload, ensure_ascii=False))
        append_args = SimpleNamespace(input=str(output), max=8, keep=50)
        appended = rt.cmd_inventory_append(append_args)
        assert appended["ok"]
        assert rt.cmd_inventory_append(append_args)["idempotent"]
        args.event_seed = "EV-DE01"
        lifecycle.template(rt, args)
        later = json.loads(output.read_text())
        assert later["events"][0]["id"] != payload["events"][0]["id"]
        context = {"current_floor": 1, "companion_ids": []}
        stock = rt.load_yaml(rt.EVENTS_PATH)
        visible = project_inventory(stock, "EVENT_INVENTORY_STATE", "dungeon", save["campaign_id"], context, 11)
        assert len(visible["entries"]) == 1
        context["current_floor"] = 9
        assert not project_inventory(stock, "EVENT_INVENTORY_STATE", "dungeon", save["campaign_id"], context, 11)["entries"]
        count += 1

        # Venue-specific additions remain available when their actual venue matches.
        forge = next(entry for entry in seed["entries"] if entry["id"] == "EV-S20")
        assert "location" in unmet(forge, {"location": "中央広場"})
        assert not unmet(forge, {"location": "鍛冶屋「鉄の咆哮」"})
        assert not unmet(next(entry for entry in seed["entries"] if entry["id"] == "EV-DE05"),
                         {"current_floor": 1, "companion_ids": ["ally"]})
        count += 1

        old = copy.deepcopy(save)
        old["world_state"]["dungeon_run"].update(active=True, run_id="route-test", current_floor=1)
        new = copy.deepcopy(old)
        identity = payload["events"][0]["id"]
        new["world_state"]["dungeon_run"]["used_event_ids"] = [identity]
        operations = [{"kind": "events", "id": identity}]
        rt._validate_dungeon_event_operations(old, new, operations, {"events": stock})
        old["world_state"]["dungeon_run"]["current_floor"] = 9
        new["world_state"]["dungeon_run"]["current_floor"] = 9
        reject(lambda: rt._validate_dungeon_event_operations(old, new, operations, {"events": stock}),
               "direct event consumption bypassed floor eligibility")
        count += 1
    return {"ok": True, "cases": count, "source_mutated": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    print(json.dumps(check(args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
