#!/usr/bin/env python3
"""Installation-only checks for regional dates, journey plans and source views."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.dont_write_bytecode = True


def check(source):
    sys.path.insert(0,str(source/'tools'))
    import regional_world as rw
    import place_atlas as pa
    cases=[]
    def stage(pid,name,parent=None):
        return {"id":pid,"name":name,"aliases":[name],"kind":"town" if parent is None else "facility","parent_id":parent,
            "source_refs":["世界/Locations.md"],"canon_constraints":["既存条件を守る。"],"overview":"検査用の舞台。","position":"街道沿い。",
            "architecture":{"levels":["1F"],**{key:"石と木で造る。" for key in ("footprint","shell","walls","roof","floors","windows","lighting","water","sanitation","heating")}},
            "rooms":[{"id":pid+"_ENTRY","name":"入口","floor":"1F","position":"南","purpose":"出入り","description":"木の扉。","sensory":"日光。","access":"public","entry":True}],
            "connections":[],"sightlines":["通りが見える。"],"daily_life":["昼に人が行き交う。"],"scene_uses":["会話。"],"limits":["入場許可は別。"]}
    atlas={"schema":pa.SCHEMA,"places":[stage("NOIR_CITY","ノワール"),stage("CHECK_CITY_CITY","検査用の街"),stage("MIA_SHOP","ミアの店","NOIR_CITY"),stage("HILLSIDE_CAVE_ENTRANCE","裏山の洞窟入口"),stage("RABI","村"),stage("CHECK_CITY_CIVIC_HALL","検査用の街穀穂会館","CHECK_CITY_CITY") ]}
    def city(cid,name):
        return {"id":cid,"name":name,"role":"検査用都市","summary":{key:cid+"_SUMMARY_"+key for key in rw.SUMMARY_KEYS},
            **{key:cid+"_DETAIL_"+key for key in ("character","landscape","districts","governance","economy","life","adult_culture","festivals","death_custom","scene_uses","limits")}}
    def route(rid,start,end,foot,cart):
        return {"id":rid,"from":start,"to":end,"foot_minutes":foot,"cart_minutes":cart,"description":"検査用の街道。","gate":"南門から外で曲がる。","limits":["計画だけで移動しない。"]}
    data={"schema":rw.SCHEMA,"region":{"overview":"REGION_FULL_ONLY"},"trade":{"rules":["TRADE_FULL_ONLY"]},"death":{"rules":["DEATH_FULL_ONLY"]},
        "calendar":{"days_per_year":360,"months_per_year":12,"days_per_month":30,"weekdays":[v+"曜" for v in rw.WEEKDAYS],"epoch":{"absolute_day":1,"year":1,"month":1,"day":1,"weekday":"月曜"},
                    "seasons":[{"name":name,"months":list(range(index*3+1,index*3+4))} for index,name in enumerate(("春","夏","秋","冬"))],"rules":["CALENDAR_FULL_ONLY"],
                    "festivals":[{"name":"月蜜祭","place_id":"RABI","season":"秋"}]},
        "cities":[city("NOIR_CITY","ノワール"),city("CHECK_CITY_CITY","検査用の街")],"place_cities":{"RABI":"NOIR_CITY"},"city_personas":{},
        "route_places":{"HILLSIDE_CAVE_ENTRANCE":"裏山の洞窟入口"},"route_aliases":{"裏山の洞窟":"HILLSIDE_CAVE_ENTRANCE"},"routes":[route("R_DIRECT","NOIR_CITY","CHECK_CITY_CITY",2880,1440),route("R_CAVE","NOIR_CITY","HILLSIDE_CAVE_ENTRANCE",120,None),route("R_LINK","HILLSIDE_CAVE_ENTRANCE","CHECK_CITY_CITY",1000,None)]}
    original=copy.deepcopy(data)
    assert rw.validate(data,atlas)==[]
    cases.append("valid_canonical_setting")
    def reject(label,mutate):
        broken=copy.deepcopy(data);mutate(broken);assert rw.validate(broken,atlas),label;cases.append(label)
    reject("wrong_schema",lambda d:d.update(schema="other"))
    reject("duplicate_city",lambda d:d["cities"].append(copy.deepcopy(d["cities"][0])))
    reject("missing_summary",lambda d:d["cities"][0].pop("summary"))
    reject("unbounded_summary_rejected",lambda d:d["cities"][0]["summary"].update(role="長"*221))
    reject("calendar_length_mismatch",lambda d:d["calendar"].update(days_per_year=365))
    reject("calendar_bool_is_not_integer",lambda d:d["calendar"].update(days_per_month=True))
    reject("calendar_epoch_mismatch",lambda d:d["calendar"]["epoch"].update(day=2))
    reject("calendar_weekday_mismatch",lambda d:d["calendar"]["weekdays"].reverse())
    reject("calendar_season_mismatch",lambda d:d["calendar"]["seasons"][0].update(months=[2,3,4]))
    reject("route_unknown_endpoint",lambda d:d["routes"][0].update(to="UNKNOWN"))
    reject("route_negative_time",lambda d:d["routes"][0].update(foot_minutes=-1))
    reject("route_boolean_time",lambda d:d["routes"][0].update(foot_minutes=True))
    reject("route_cart_zero",lambda d:d["routes"][0].update(cart_minutes=0))
    reject("duplicate_route_id",lambda d:d["routes"].append(copy.deepcopy(d["routes"][0])))
    reject("invalid_city_reference",lambda d:d["place_cities"].update(RABI="UNKNOWN"))
    reject("dangling_route_alias_rejected",lambda d:d["route_aliases"].update(別の洞窟="UNKNOWN"))
    branch_data=copy.deepcopy(data)
    branch_data["trade"]["branches"]=[{"city_id":"NOIR_CITY","place_id":"MIA_SHOP","room_id":"MIA_SHOP_ENTRY","location":"ミアの店"}]
    assert rw.validate(branch_data,atlas)==[]
    cases.append("trade_branch_room_resolves_its_facility")
    branch_data["trade"]["branches"][0]["room_id"]="CHECK_CITY_CITY_ENTRY"
    assert rw.validate(branch_data,atlas)
    cases.append("trade_branch_foreign_or_dangling_room_rejected")
    assert rw.date_for_day(1)["text"]=="箱庭暦1年1月1日（月）・春"
    assert rw.date_for_day(30)["day_of_month"]==30 and rw.date_for_day(31)["month"]==2
    assert rw.date_for_day(90)["season"]=="春" and rw.date_for_day(91)["season"]=="夏"
    assert rw.date_for_day(360)["year"]==1 and rw.date_for_day(361)["year"]==2
    assert rw.date_for_day(361)["weekday"]=="木"
    cases += ["calendar_epoch","calendar_month_rollover","calendar_season_rollover","calendar_year_rollover","weekday_continues_across_year"]
    for invalid in (0,-1,True,1.5,"1"):
        try:rw.date_for_day(invalid)
        except ValueError:pass
        else:raise AssertionError("invalid Day accepted")
    cases.append("invalid_days_rejected")
    def view(topics=None,cities=None,day=1):return rw.project(data,{"day":day,"city_ids":cities if cities is not None else ["NOIR_CITY"],"topics":topics or []})
    ordinary=rw.render_view(view())
    assert len(ordinary)<2000 and "NOIR_CITY_SUMMARY_culture" in ordinary
    assert "CHECK_CITY_CITY_SUMMARY" not in ordinary and "NOIR_CITY_DETAIL" not in ordinary and "TRADE_FULL_ONLY" not in ordinary
    cases += ["ordinary_summary_is_small_and_complete","ordinary_scope_does_not_load_all_cities_or_chapters"]
    culture=rw.render_view(view(["culture"]))
    assert "NOIR_CITY_DETAIL_adult_culture" in culture and "NOIR_CITY_DETAIL_festivals" in culture and "TRADE_FULL_ONLY" not in culture
    assert "DEATH_FULL_ONLY" in rw.render_view(view(["death"])) and "NOIR_CITY_DETAIL_death_custom" in rw.render_view(view(["death"]))
    assert "REGION_FULL_ONLY" in rw.render_view(view(["governance"]))
    assert "CALENDAR_FULL_ONLY" in rw.render_view(view(["calendar"]))
    cases += ["culture_topic_reads_complete_selected_section","death_topic_reads_rules_and_local_custom","governance_topic_reads_common_rules","calendar_topic_is_explicit"]
    local=copy.deepcopy(data)
    local["cities"][0].update(local_materials=[{"name":"MATERIAL_LOCAL_ONLY"}],material_rules=["MATERIAL_RULE_LOCAL_ONLY"],
                             regional_encounters={"rules":["ENCOUNTER_LOCAL_ONLY"]},population=["POPULATION_LOCAL_ONLY"])
    def local_view(topic):
        return rw.render_view(rw.project(local,{"day":1,"city_ids":["NOIR_CITY"],"topics":topic}))
    assert all(token not in local_view([]) for token in ("MATERIAL_LOCAL_ONLY","ENCOUNTER_LOCAL_ONLY","POPULATION_LOCAL_ONLY"))
    assert "MATERIAL_LOCAL_ONLY" in local_view(["trade"]) and "MATERIAL_RULE_LOCAL_ONLY" in local_view(["trade"])
    assert "ENCOUNTER_LOCAL_ONLY" in local_view(["travel"]) and "MATERIAL_LOCAL_ONLY" not in local_view(["travel"])
    assert "POPULATION_LOCAL_ONLY" in local_view(["culture"]) and "ENCOUNTER_LOCAL_ONLY" not in local_view(["culture"])
    assert "MATERIAL_LOCAL_ONLY" not in rw.render_view(rw.project(local,{"day":1,"city_ids":["CHECK_CITY_CITY"],"topics":["trade"]}))
    cases += ["new_local_details_do_not_expand_ordinary_turn","material_topic_reads_complete_local_rules",
              "sea_encounters_are_loaded_only_for_travel","population_is_culture_scoped","local_materials_do_not_leak_to_other_cities"]
    selected={"places":[atlas["places"][2]],"parent_context":[],"exterior_context":[]}
    req=rw.request_from(SimpleNamespace(world_topic=["trade"]),{"world_state":{"day":4}},selected,atlas,data)
    assert req=={"day":4,"city_ids":["NOIR_CITY"],"topics":["trade"]}
    frozen_selection=copy.deepcopy(selected)
    reference=rw.request_from(SimpleNamespace(world_topic=["trade"],world_city=["検査用の街","CHECK_CITY_CITY"]),
                             {"world_state":{"day":4}},selected,atlas,data)
    assert reference=={"day":4,"city_ids":["CHECK_CITY_CITY","NOIR_CITY"],"topics":["trade"],"reference_city_ids":["CHECK_CITY_CITY"]}
    assert selected==frozen_selection
    cases.append("remote_city_reference_is_deduplicated_and_does_not_change_physical_stage")
    try:rw.request_from(SimpleNamespace(world_city=["UNKNOWN_CITY"]),{},selected,atlas,data)
    except ValueError:pass
    else:raise AssertionError("unknown canonical reference city accepted")
    cases.append("unknown_explicit_reference_is_not_a_canonical_city")
    village={"places":[next(place for place in atlas["places"] if place["id"]=="RABI")],"parent_context":[],"exterior_context":[]}
    assert rw.request_from(SimpleNamespace(world_topic=[]),{"world_state":{"day":1}},village,atlas,data)["city_ids"]==["NOIR_CITY"]
    assert rw.request_from(SimpleNamespace(world_topic=[]),{"world_state":{"day":1}},{"places":[]},atlas,data)["city_ids"]==[]
    cases += ["facility_resolves_its_parent_city","nearby_reference_does_not_require_new_city","unknown_places_keep_free_setting"]
    from context_loader import atlas_defined_subject
    hall_view={"places":[atlas["places"][-1]],"parent_context":[],"exterior_context":[]}
    assert atlas_defined_subject(hall_view,"検査用の街穀穂会館") and atlas_defined_subject(hall_view,"CHECK_CITY_CIVIC_HALL_ENTRY")
    assert not atlas_defined_subject(hall_view,"まだ名前のない宿")
    assert not atlas_defined_subject({"places":[atlas["places"][0]]},"ノワールの未知店")
    cases.append("loaded_atlas_building_and_room_are_not_undefined_services")
    plan=rw.travel_plan(data,"NOIR_CITY","CHECK_CITY_CITY","foot")
    assert plan["minutes"]==1120 and [v["route_id"] for v in plan["segments"]]==["R_CAVE","R_LINK"]
    assert rw.travel_plan(data,"CHECK_CITY_CITY","NOIR_CITY","foot")["minutes"]==1120
    assert rw.travel_plan(data,"NOIR_CITY","CHECK_CITY_CITY","cart")["minutes"]==1440
    assert rw.travel_plan(data,"NOIR_CITY","HILLSIDE_CAVE_ENTRANCE","cart")["status"]=="no_route_for_mode"
    assert rw.travel_plan(data,"NOIR_CITY","UNDEFINED","foot")["status"]=="undefined_route"
    assert rw.travel_plan(data,"NOIR_CITY","NOIR_CITY","foot")["minutes"]==0
    cases += ["shortest_valid_route","bidirectional_route","mode_specific_route","cart_unavailable_is_not_invented","unknown_route_returns_creative_opening","same_anchor_has_zero_intercity_time"]
    save={"world_state":{"day":4,"time_of_day":"朝"},"debt_state":{"next_collection_day":5,"collection_pending":False}}
    assert rw.travel_plan(data,"NOIR_CITY","HILLSIDE_CAVE_ENTRANCE","foot",save)["collection_interrupt_day"] is None
    late=copy.deepcopy(save);late["world_state"]["time_of_day"]="夜"
    assert rw.travel_plan(data,"NOIR_CITY","CHECK_CITY_CITY","foot",late)["collection_interrupt_day"]==5
    unknown_time=copy.deepcopy(save);unknown_time["world_state"]["time_of_day"]=""
    p=rw.travel_plan(data,"NOIR_CITY","HILLSIDE_CAVE_ENTRANCE","foot",unknown_time)
    assert p["collection_interrupt_day"]==5 and p["departure_time_uncertain"]
    assert "無料運賃" in p["notice"] and "標準" in p["notice"]
    cases += ["short_route_does_not_invent_due_collection","journey_warns_before_due_day","unknown_departure_time_is_conservative","estimate_grants_no_transport_or_services"]
    minute_data=copy.deepcopy(data);minute_data["routes"][0]["foot_minutes"]=1490
    assert "1日50分" in rw.renderer(minute_data)
    assert data==original
    cases += ["route_minutes_are_not_rounded_away","pure_helpers_never_mutate_canonical_data"]

    with tempfile.TemporaryDirectory(prefix="machadan-region-") as temp:
        game=Path(temp)/"machadan_spade";root=game/"muse版"
        shutil.copytree(source,root,ignore=shutil.ignore_patterns("saves","state","__pycache__","*.pyc"))
        shutil.copy2(source.parent/"VERSION.txt",game/"VERSION.txt")
        (root/pa.RELATIVE_PATH).write_text(json.dumps(atlas,ensure_ascii=False,indent=2)+"\n")
        (root/"世界/舞台資料集.md").write_text(pa.renderer(atlas))
        (root/rw.RELATIVE_PATH).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
        (root/rw.BOOK_PATH).write_text(rw.renderer(data))
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        manifest={"schema":"machadan-runtime-manifest-v1","version":re.search(r"(?im)^version:\s*(.+)$",(game/"VERSION.txt").read_text()).group(1).strip(),"base":"machadan_spade","files":[dict(path=p.relative_to(game).as_posix(),size=p.stat().st_size,sha256=digest(p)) for p in sorted(game.rglob("*")) if p.is_file()]}
        (game/"RUNTIME_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        runtime=root/"tools/machadan_runtime.py";doctor=root/"tools/check_knowledge.py"
        def run(command,good=True,error=None):
            result=subprocess.run([sys.executable,"-B",*map(str,command)],text=True,capture_output=True)
            payload=json.loads(result.stdout)
            assert (result.returncode==0)==good,(payload,result.stderr)
            assert payload.get("ok")==good,payload
            if error:assert any(v.get("code")==error for v in payload.get("errors",[])),payload
            return payload
        current=root/"saves/regional-probe.yaml";context=root/"state/runtime/regional-probe/context.md";receipt=context.with_suffix(".md.receipt.json")
        run([runtime,"new-save","--campaign-id","regional-probe","--output",current])
        original_save=current.read_bytes()
        run([runtime,"prepare-context","--save",current,"--scene","turn","--location","ミアの店","--output",context])
        command=[doctor,"--root",root,"--turn","--save",current,"--receipt",receipt,"--json"]
        run(command)
        rows=json.loads(receipt.read_text())["sources"]
        regional=[row for row in rows if row["resource"]=="REGIONAL_WORLD"]
        assert len(regional)==1 and regional[0]["mode"]=="regional_view"
        assert "NOIR_CITY_SUMMARY" in context.read_text() and "CHECK_CITY_CITY_DETAIL" not in context.read_text()
        cases += ["cli_context_loads_one_verified_regional_source","cli_context_resolves_facility_city"]
        original_context=context.read_bytes();original_receipt=receipt.read_bytes()
        hall_result=run([runtime,"prepare-context","--save",current,"--scene","shop","--location","検査用の街穀穂会館","--output",context])
        hall_notes=[note for note in hall_result["reference_notes"] if note.get("resource")=="LOCATIONS" and note.get("term")=="検査用の街穀穂会館"]
        assert any(note["kind"]=="atlas_defined_place" for note in hall_notes) and not any(note["kind"]=="undefined_subject" for note in hall_notes)
        run(command)
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("new_civic_hall_missing_old_catalog_is_not_free_recreation")
        run([runtime,"prepare-context","--save",current,"--scene","turn","--location","ノワール","--world-topic","culture","--output",context])
        assert "NOIR_CITY_DETAIL_adult_culture" in context.read_text()
        run(command)
        cases.append("cli_world_topic_loads_complete_city_culture")
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        sys.path.insert(0,str(root/"tools/_vendor"))
        import yaml
        remembered=yaml.safe_load(original_save)
        remembered["world_state"]["campaign_lore"]={"old_festival":{"place_id":"RABI","festival":"月蜜祭","date":"1年8月12日","status":"scheduled","text":"SAVED_FESTIVAL_DATE_UNIQUE"},
            **{f"unrelated_{i}":{"location":"関係のない街","text":str(i)} for i in range(25)}}
        current.write_text(yaml.safe_dump(remembered,allow_unicode=True,sort_keys=False))
        run([runtime,"prepare-context","--save",current,"--scene","turn","--location","ノワール","--world-topic","calendar","--output",context])
        assert "SAVED_FESTIVAL_DATE_UNIQUE" in context.read_text()
        run(command)
        current.write_bytes(original_save);context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("old_announced_festival_survives_bounded_calendar_view")
        calendar_result=run([runtime,"world-calendar","--save",current])
        assert calendar_result["date"]["absolute_day"]==1
        assert run([runtime,"world-calendar","--day",361])["date"]["weekday"]=="木"
        trip=run([runtime,"travel-plan","--from","ミアの店","--to","検査用の街","--mode","cart","--save",current])
        assert trip["requested_from"]=="MIA_SHOP" and trip["from_anchor"]=="NOIR_CITY" and trip["minutes"]==1440 and trip["local_access_not_included"]
        same=run([runtime,"travel-plan","--from","ミアの店","--to","ノワール"])
        assert same["minutes"]==0 and same["local_access_not_included"]
        assert run([runtime,"travel-plan","--from","知らない村","--to","検査用の街"])["status"]=="undefined_route"
        assert run([runtime,"travel-plan","--from","ノワール","--to","裏山の洞窟","--mode","foot"])["minutes"]==120
        assert run([runtime,"travel-plan","--from","ノワール","--to","裏山の洞窟","--mode","cart"])["status"]=="no_route_for_mode"
        assert current.read_bytes()==original_save
        cases += ["cli_calendar_is_derived","cli_calendar_year_rollover","cli_facility_journey_refines_route_anchor","cli_same_city_does_not_include_local_access","cli_unknown_place_stays_open","cli_route_alias_resolves_existing_foot_path","cli_route_alias_does_not_enable_cart","all_readonly_commands_leave_save_unchanged"]
        lore_path=root/rw.RELATIVE_PATH;old_lore=lore_path.read_bytes()
        lore_path.write_bytes(old_lore+b"\n")
        run(command,False,"turn_source_changed");lore_path.write_bytes(old_lore)
        cases.append("changed_regional_canonical_source_rejected")
        altered=context.read_text().replace("# 今回の地方・暮らし・日付 — GM参照用","# 今回の地方・暮らし・日付 — 改変",1)
        context.write_text(altered);changed=json.loads(original_receipt);changed["context_sha256"]=digest(context);receipt.write_text(json.dumps(changed))
        run(command,False,"turn_context_changed")
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("rehashed_regional_view_change_rejected")
        changed=json.loads(original_receipt);changed["regional_request"]["day"]=5
        receipt.write_text(json.dumps(changed));run(command,False,"turn_regional_world")
        receipt.write_bytes(original_receipt)
        cases.append("forged_regional_day_rejected")
        changed=json.loads(original_receipt);changed["sources"]=[v for v in changed["sources"] if v["resource"]!="REGIONAL_WORLD"]
        body=re.sub(r"(?ms)^### SOURCE: "+re.escape(rw.SOURCE_LABEL)+r"\n\n.*?(?=^### SOURCE: |\Z)","",context.read_text(),count=1)
        context.write_text(body);changed["context_sha256"]=digest(context);receipt.write_text(json.dumps(changed))
        run(command,False,"turn_regional_world")
        cases.append("missing_regional_source_rejected")
        run([runtime,"prepare-context","--save",current,"--scene","turn","--location","ミアの店",
             "--world-city","検査用の街","--world-topic","trade","--output",context])
        run(command)
        remote_receipt=json.loads(receipt.read_text())
        assert remote_receipt["regional_request"]["reference_city_ids"]==["CHECK_CITY_CITY"]
        assert "CHECK_CITY_CITY_DETAIL_economy" in context.read_text() and "CHECK_CITY_CITY_ENTRY" not in context.read_text()
        assert current.read_bytes()==original_save
        cases += ["cli_remote_reference_has_verified_canonical_projection","remote_reference_does_not_load_city_building_or_move_save"]
        remote_receipt["regional_request"]["reference_city_ids"]=["UNKNOWN_CITY"]
        receipt.write_text(json.dumps(remote_receipt))
        run(command,False,"turn_regional_world")
        cases.append("forged_unknown_reference_city_is_rejected")
    return {"ok":True,"cases":len(cases),"case_ids":cases,"source_unchanged":True}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent.parent)
    try:print(json.dumps(check(parser.parse_args().root.resolve()),ensure_ascii=False,indent=2))
    except Exception as exc:print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False));raise SystemExit(1)
