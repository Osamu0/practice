#!/usr/bin/env python3
"""Regression scenarios for M108's persistent exploration state and save boundary."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.dont_write_bytecode = True


def check(root):
    # The installer owns the live workspace's exclusive gate while doctor runs.
    # Exercise real mutating CLIs against an independent runtime and gate; never
    # bypass the installation lock or copy the user's saves and mutable state.
    with tempfile.TemporaryDirectory(prefix="machadan-dungeon-workspace-") as directory:
        workspace = Path(directory)
        game = workspace / "machadan_spade"
        shutil.copytree(root.parent, game,
            ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"))
        isolated_root = game / "muse版"
        previous = {key: os.environ.get(key) for key in ("MACHADAN_ROOT", "MACHADAN_WORKSPACE")}
        os.environ.update(MACHADAN_ROOT=str(isolated_root), MACHADAN_WORKSPACE=str(workspace))
        try:
            return _check_isolated(isolated_root)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _check_isolated(root):
    sys.path.insert(0, str(root / "tools"))
    import machadan_runtime as rt
    import dungeon_exploration as dx
    assert rt.ROOT.resolve() == root.resolve(), "regression runtime must use its isolated workspace"

    def run_cli(command):
        result = subprocess.run(command,capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError("isolated dungeon CLI failed: " + (result.stdout + result.stderr)[-5000:])
        return result
    cases = []
    with tempfile.TemporaryDirectory(prefix="machadan-dungeon-") as directory:
        folder = Path(directory)
        save = folder / "save.yaml"
        rt.cmd_new_save(SimpleNamespace(output=str(save), campaign_id="dungeon-check", force=False))
        base = rt.load_yaml(save)

        def fixture(cleared=False):
            data = copy.deepcopy(base)
            p = data["player"]
            p.update(name="Explorer", base_lp=20, lp={"cur":20,"max":20})
            data["fire_state"]["holders"] = [p["character_id"]]
            w = data["world_state"]
            w.update(depth=1, deepest_depth_reached=2 if cleared else 1, location="裏山の洞窟", time_of_day="朝")
            w["expedition_state"].update(active=True, expedition_id="run-a",kind="dungeon", fire_holders=[p["character_id"]])
            w["dungeon_run"].update(active=True,run_id="run-a",current_floor=1,boss_route_found=cleared)
            if cleared:
                w["defeated_floor_bosses"] = [1]
                w["boss_records"] = [{"boss_id":"boss-f1", "floor":1, "first_defeated_day":1,
                    "last_defeated_day":1,"rematch_available_day":1,"last_defeat_id":"old-defeat",
                    "last_defeated_expedition_id":"previous-run"}]
            return dx.arrive(data)

        def valid(data):
            errors, _ = rt.validate_save_data(data)
            assert not errors, errors

        def transition(a,b):
            valid(b)
            errors = rt._validate_adventure_transition(a,b)
            assert not errors, errors

        a = fixture()
        valid(a)
        for i in range(6):
            b = dx.resolve(a,f"quiet-{i}","avoid")
            transition(a,b)
            a=b
        assert dx.status(a)["boss_contact_due"]
        try: dx.resolve(a,"too-late","exploration")
        except ValueError: pass
        else: raise AssertionError("uncleared boss contact can be ignored")
        b=dx.resolve(a,"boss-escape","boss")
        transition(a,b)
        assert dx.status(b)["boss_contact_due"]
        cases.append("noncombat_route_reaches_boss_and_escape_does_not_reset_pressure")

        a=fixture(True)
        for i in range(17):
            pending=dx.status(a)["active_incursion"]
            b=dx.resolve(a,f"long-{i}","trash" if pending else "event",
                pursuit_outcome="escaped" if pending else None)
            transition(a,b);a=b
        assert a["world_state"]["dungeon_run"]["current_floor_scenes"]==17
        assert not dx.status(a)["boss_contact_due"]
        cases.append("cleared_floor_allows_long_exploration_without_boss_hunt")

        a=fixture(True)
        b=dx.resolve(a,"gather","exploration",site="harvest-1");transition(a,b)
        c=copy.deepcopy(b);c["world_state"]["day"]=2
        transition(b,c)
        assert "harvest-1" not in dx.status(c)["available_sites"]
        c["world_state"]["dungeon_run"]["resource_days_by_floor"]={}
        assert rt._validate_adventure_transition(b,c)
        cases.append("overnight_stay_preserves_depletion_and_rejects_day_unpinning")

        a=fixture(True);a["world_state"]["day"]=2
        b=dx.resolve(a,"after-midnight","event");transition(a,b)
        assert dx.status(b)["record"]=="d1-f1"
        cases.append("arrival_pins_resources_even_before_first_incident")

        a=fixture(True);a=dx.resolve(a,"harvest-once","exploration",site="harvest-1")
        ended=copy.deepcopy(a)
        ended["world_state"]["dungeon_run"]=copy.deepcopy(base["world_state"]["dungeon_run"])
        ended["world_state"]["expedition_state"]=copy.deepcopy(base["world_state"]["expedition_state"])
        ended["world_state"]["expedition_state"].update(last_end_reason="return",last_ended_expedition_id="run-a")
        transition(a,ended)
        reentered=copy.deepcopy(ended)
        reentered["world_state"]["expedition_state"].update(active=True, expedition_id="run-b",kind="dungeon",
            fire_holders=[reentered["player"]["character_id"]],last_end_reason="none",last_ended_expedition_id="")
        reentered["world_state"]["dungeon_run"].update(active=True,run_id="run-b",current_floor=1,boss_route_found=True)
        reentered=dx.arrive(reentered);transition(ended,reentered)
        assert "harvest-1" not in dx.status(reentered)["available_sites"]
        ended2=copy.deepcopy(ended);ended2["world_state"]["day"]=2
        reentered2=copy.deepcopy(reentered);reentered2["world_state"]["day"]=2
        reentered2["world_state"]["dungeon_run"]["resource_days_by_floor"]={}
        reentered2=dx.arrive(reentered2);transition(ended2,reentered2)
        assert "harvest-1" in dx.status(reentered2)["available_sites"]
        cases.append("same_day_reentry_stays_depleted_and_next_day_reentry_replenishes")

        a=fixture(True);rec,_=dx.record(a)
        for i in range(8):
            rec["actions"].append({"id":f"seed-{i}","kind":"event","roll":None,"site":None})
        a["world_state"]["dungeon_run"].update(current_floor_scenes=8,danger_zones_resolved=8)
        rec["incursions"]=[{"id":"seed-7","at":8,"origin_floor":2,"phase":"engaged","loot_claimed":False,"loot_instance_ids":[]}]
        valid(a)
        moved=copy.deepcopy(a);moved["world_state"]["dungeon_run"].update(current_floor=2,current_floor_scenes=0,danger_zones_resolved=0)
        moved=dx.arrive(moved)
        assert rt._validate_adventure_transition(a,moved)
        assert rt._validate_adventure_transition(a,ended)
        b=dx.resolve(a,"escape","trash",pursuit_outcome="escaped");transition(a,b)
        cursor=b["dice_state"]["dice_cursor_d10"]
        for i in range(3):
            c=dx.resolve(b,f"cooldown-{i}","event");transition(b,c);b=c
        assert b["dice_state"]["dice_cursor_d10"]==cursor
        cases.append("engaged_pursuit_blocks_free_exit_and_cooldown_begins_after_resolution")

        # A wipe is settled by the pre-existing strict rebirth path, without an escape detour.
        wiped=copy.deepcopy(a);wiped["world_state"]["expedition_state"]["rebirth_pending"]=True
        returned=copy.deepcopy(ended);returned["world_state"]["day"]=2
        returned["world_state"]["expedition_state"]["last_end_reason"]="rebirth"
        returned["world_state"]["dungeon_memory"]=copy.deepcopy(wiped["world_state"]["dungeon_memory"])
        assert not dx.validate_adventure(wiped,returned)
        cases.append("pending_rebirth_can_close_a_pursuit_without_escape_commit")

        a=fixture(True);b=dx.resolve(a,"unearned","boss",site="boss-loot")
        assert any("actual" in x for x in rt._validate_adventure_transition(a,b))
        cases.append("boss_loot_cannot_be_claimed_without_a_defeat")

        legacy=fixture(True);legacy["world_state"].pop("dungeon_memory")
        run=legacy["world_state"]["dungeon_run"]
        run.update(current_floor=2,resource_days_by_floor={},reward_searches_by_floor={"1":2,"2":2})
        changes=[];dx.migrate(legacy,changes)
        assert {"chest-1","chest-2"} <= set(legacy["world_state"]["dungeon_memory"]["records"]["d1-f1"]["claims"])
        cases.append("legacy_migration_preserves_depletion_on_all_visited_floors")

        # A successful first acquisition changes only this stable boss source to 20%.
        def fruit_row(rid, source, cursor, awarded=True, modern=True):
            rare=rt._fixed_tape_value("d10",cursor)
            typ=rt._fixed_tape_value("d10",(cursor+1)%500)
            row={"resolution_id":rid,"source_type":"boss","source_id":rid,
                "outcome":"awarded" if awarded else "miss","day":1,
                "rolls":[{"die":"d10","purpose":"rarity","cursor":cursor,"result":rare}],
                "items":[]}
            if awarded:
                row["rolls"].append({"die":"d10","purpose":"fruit-type","cursor":(cursor+1)%500,"result":typ})
                row["items"]=[{"name":rt.FRUIT_ITEM_BY_D10[typ],"count":1}]
            if modern: row.update(rule_version=2,source_key=source)
            return row
        eight=next(i for i in range(500) if rt._fixed_tape_value("d10",i)==8)
        nine=next(i for i in range(500) if rt._fixed_tape_value("d10",i)==9)
        a=fixture(True);g=a["world_state"]["growth_state"]
        first=fruit_row("first-fruit","boss-f1",eight)
        g["resolutions"]=[first,fruit_row("repeat-fruit","boss-f1",eight)]
        errors=[];rt._validate_growth_state(a,a["world_state"],errors)
        assert any(">= 9" in x for x in errors), errors
        g["resolutions"]=[first,fruit_row("repeat-fruit","boss-f1",nine)]
        errors=[];rt._validate_growth_state(a,a["world_state"],errors);assert not errors,errors
        cases.append("first_boss_fruit_accepts_8_but_repeat_requires_9_or_10")
        legacy=fixture(True);g=legacy["world_state"]["growth_state"]
        row=fruit_row("old-defeat","boss-f1",eight,modern=False);g["resolutions"]=[row]
        dx.migrate(legacy,[])
        assert g["boss_fruit_legacy_sources"]==["boss-f1"]
        g["resolutions"].append(fruit_row("repeat-old","boss-f1",eight))
        errors=[];rt._validate_growth_state(legacy,legacy["world_state"],errors)
        assert any(">= 9" in x for x in errors),errors
        cases.append("legacy_success_is_projected_without_reinterpreting_historical_dice")
        a=fixture(True)
        for i in range(7): a=dx.resolve(a,f"draw-{i}","event")
        b=dx.resolve(a,"draw-8","trash")
        action=dx.record(b)[0]["actions"][-1]
        roll=action["roll"]
        b["world_state"]["growth_state"]["resolutions"].append({
            "resolution_id":"strong-miss","source_type":"strong","source_id":"strong-miss",
            "outcome":"miss","items":[],"day":1,"rolls":[copy.deepcopy(roll)]})
        assert any("distinct" in x for x in dx.validate_transition(a,b))
        cases.append("hazard_and_reward_cannot_reuse_the_same_d10")

        a=fixture(True)
        b=dx.resolve(a,"open-chest","exploration",site="chest-1")
        cursor=a["dice_state"]["dice_cursor_d6"]
        b["dice_state"]["dice_cursor_d6"]=(cursor+1)%600
        b["world_state"]["growth_state"]["resolutions"].append({
            "resolution_id":"chest-receipt","source_type":"chest","source_id":"d1-f1-chest-1",
            "rule_version":2,"floor":1,"resource_day":1,"site_id":"chest-1",
            "outcome":"miss","items":[],"day":1,
            "rolls":[{"die":"d6","purpose":"chest-tier","cursor":cursor,"result":rt._fixed_tape_value("d6",cursor)}]})
        transition(a,b)
        assert not rt._validate_growth_transition(a,b,"chest-tx")
        fake=copy.deepcopy(b)
        fake["world_state"]["growth_state"]["resolutions"][-1]["source_id"]="another-chest"
        assert rt._validate_adventure_transition(a,fake)
        cases.append("chest_draws_are_bound_to_the_actual_daily_site")
        a=fixture(True);rec,_=dx.record(a)
        rec["actions"]=[{"id":f"loot-seed-{i}","kind":"event","roll":None,"site":None} for i in range(8)]
        rec["incursions"]=[{"id":"loot-seed-7","at":8,"origin_floor":2,"phase":"engaged","loot_claimed":False,"loot_instance_ids":[]}]
        a["world_state"]["dungeon_run"].update(current_floor_scenes=8,danger_zones_resolved=8)
        b=dx.resolve(a,"steal-escape","trash",pursuit_outcome="escaped",loot_instance_ids=["stolen-sword"])
        assert any("equipment" in x for x in dx.validate_transition(a,b))
        b["item_instances"].append({"instance_id":"stolen-sword"})
        assert not dx.validate_transition(a,b)
        cases.append("equipment_seized_during_escape_requires_a_real_new_instance_receipt")

        import context_loader
        a=fixture(True);rec,_=dx.record(a)
        rec["incursions"]=[{"phase":"engaged","origin_floor":2}]
        assert context_loader.exploration_floor_terms(a["world_state"])==["1F","2F"]
        rec["incursions"][0]["phase"]="escaped"
        assert context_loader.exploration_floor_terms(a["world_state"])==["1F"]
        cases.append("active_pursuit_loads_real_lower_floor_enemy_context")

        # Optional passage data leaves every existing v3 save readable.
        a=fixture(True)
        assert "passage_ticks" not in a["world_state"]["dungeon_run"]
        valid(a)
        claims=copy.deepcopy(dx.record(a)[0]["claims"])
        for i in range(6):
            b=dx.resolve(a,f"passage-{i}","passage")
            transition(a,b)
            assert dx.record(b)[0]["claims"]==claims
            assert b["world_state"]["dungeon_run"]["reward_searches_by_floor"]=={}
            assert b["world_state"]["dungeon_run"]["used_event_ids"]==[]
            a=b
        assert a["world_state"]["time_of_day"]=="夕"
        assert a["world_state"]["dungeon_run"]["passage_ticks"]==6
        assert a["dice_state"]==base["dice_state"]
        cases.append("six_passages_advance_half_day_without_draws_or_resource_changes")
        try: dx.resolve(fixture(),"uncleared-passage","passage")
        except ValueError: pass
        else: raise AssertionError("uncleared floor allowed passage")
        try: dx.resolve(a,"passage-0","passage")
        except ValueError: pass
        else: raise AssertionError("repeated passage ID was applied twice")
        for keyword in ({"site":"harvest-1"},{"event_id":"EV-FAKE"},{"pursuit_outcome":"escaped"}):
            try: dx.resolve(a,"passage-with-resource","passage",**keyword)
            except ValueError: pass
            else: raise AssertionError("passage mixed an unrelated resolution")
        cases.append("passage_rejects_uncleared_retries_resources_and_event_stock")

        a=fixture(True)
        for i in range(2):a=dx.resolve(a,f"midnight-{i}","passage")
        a["world_state"].update(day=4,time_of_day="夜")
        b=dx.resolve(a,"passage-due-day","passage")
        transition(a,b)
        assert b["world_state"]["day"]==5 and b["world_state"]["time_of_day"]=="朝"
        assert b["debt_state"]["collection_pending"] is True
        assert b["world_state"]["dungeon_run"]["resource_days_by_floor"]==a["world_state"]["dungeon_run"]["resource_days_by_floor"]
        try: dx.resolve(b,"past-due-passage","passage")
        except ValueError: pass
        else: raise AssertionError("passage skipped a pending collection")
        forged=copy.deepcopy(b);forged["world_state"]["day"]=4
        assert dx.validate_transition(a,forged)
        forged=copy.deepcopy(b);forged["debt_state"]["collection_pending"]=False
        assert dx.validate_transition(a,forged)
        cases.append("midnight_passage_stops_on_collection_day_and_pins_resources")

        a=fixture(True);b=dx.resolve(a,"one-passage","passage")
        forged=copy.deepcopy(b);forged["inventory"]["bag"]["max_slots"]+=1
        assert dx.validate_transition(a,forged)
        forged=copy.deepcopy(b);forged["world_state"]["dungeon_run"]["passage_ticks"]=0
        errors=[];dx.validate_memory(forged,errors);assert errors
        assert dx.validate_transition(a,forged)
        cases.append("passage_cannot_grant_inventory_or_reset_its_clock")

        a=fixture(True)
        for i in range(7):a=dx.resolve(a,f"passage-hazard-{i}","passage")
        cursor=a["dice_state"]["dice_cursor_d10"]
        b=dx.resolve(a,"passage-hazard-8","passage");transition(a,b)
        assert b["dice_state"]["dice_cursor_d10"]==(cursor+1)%500
        assert dx.record(b)[0]["actions"][-1]["roll"] is not None
        cases.append("passage_uses_only_the_existing_eighth_incident_hazard")

        a=fixture(True)
        for i in range(7):a=dx.resolve(a,f"previous-day-{i}","event")
        a["world_state"]["day"]=2
        cursor=a["dice_state"]["dice_cursor_d10"]
        b=dx.resolve(a,"new-day-passage","passage");transition(a,b)
        assert b["dice_state"]["dice_cursor_d10"]==cursor
        assert dx.status(b)["record"]=="d1-f1"
        assert dx.record(b)[0]["actions"][-1]["activity_day"]==2
        cases.append("actual_day_resets_overstay_while_resource_day_stays_pinned")

        # Actual CLI candidate + atomic commit, preserving the live save until commit.
        a=fixture();rt.atomic_write(save,rt.dump_yaml(a));before=save.read_bytes()
        candidate=folder/"candidate.yaml"
        command=[sys.executable,"-B",str(root/"tools/dungeon_exploration.py"),"resolve","--save",str(save),
            "--output",str(candidate),"--action-id","cli-scene","--kind","avoid"]
        run_cli(command)
        assert save.read_bytes()==before
        run_cli([sys.executable,"-B",str(root/"tools/machadan_runtime.py"),"commit-save",
            "--current",str(save),"--candidate",str(candidate),"--transaction-id","dungeon-commit","--turn","1"],
        )
        assert rt.load_yaml(save)["save_revision"]==a["save_revision"]+1
        cases.append("cli_candidate_is_separate_and_atomic_runtime_commit_accepts_it")
        a=fixture(True);rt.atomic_write(save,rt.dump_yaml(a));before=save.read_bytes()
        passage_candidate=folder/"passage.candidate.yaml"
        run_cli([sys.executable,"-B",str(root/"tools/dungeon_exploration.py"),"resolve","--save",str(save),
            "--output",str(passage_candidate),"--action-id","cli-passage","--kind","passage"])
        assert save.read_bytes()==before
        run_cli([sys.executable,"-B",str(root/"tools/machadan_runtime.py"),"commit-save",
            "--current",str(save),"--candidate",str(passage_candidate),"--transaction-id","passage-commit","--turn","1"])
        passed=rt.load_yaml(save)
        assert passed["world_state"]["dungeon_run"]["passage_ticks"]==1
        assert passed["dice_state"]==a["dice_state"] and passed["inventory"]==a["inventory"]
        cases.append("passage_cli_no_draw_no_reward_and_atomic_commit")
    return cases


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent.parent)
    args=parser.parse_args()
    try:
        cases=check(args.root.resolve())
        print(json.dumps({"ok":True,"cases":len(cases),"scenarios":cases},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False))
        raise
