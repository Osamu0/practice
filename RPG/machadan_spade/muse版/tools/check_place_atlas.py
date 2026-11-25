#!/usr/bin/env python3
"""Check stage graphs, narrow place selection and verifiable source receipts."""
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
    sys.path.insert(0, str(source / "tools"))
    import place_atlas as atlas
    cases = []

    def node(rid, name, floor="1F", entry=False):
        return dict(id=rid, name=name, floor=floor, position="入口から北", purpose="通行と待機", description="固定の石壁と板床。", sensory="木と灯油の匂い。", access="public", entry=entry)

    def place(pid, name, parent=None):
        result = dict(id=pid, name=name, aliases=[name+"の別名"], kind="facility" if parent else "settlement", parent_id=parent,
                      source_refs=["世界/Locations.md"], canon_constraints=["既存の料金と機能を維持。"], overview="検証用の既存舞台。", position="中央通りの北。",
                      architecture={key:"石材と木材を使う。" for key in ("footprint","shell","walls","roof","floors","windows","lighting","water","sanitation","heating")},
                      rooms=[node(pid+"_ENTRY", "入口", entry=True),node(pid+"_BACK", "裏口")],
                      connections=[dict(from_=pid+"_ENTRY",to=pid+"_BACK",via="廊下",access="public",description="同階を北へ歩く。")],
                      sightlines=["入口から裏口まで見える。"],daily_life=["昼は往来がある。"],scene_uses=["待ち合わせ。"],limits=["新規の効果を作らない。"])
        result["architecture"]["levels"]=["1F"]
        result["connections"][0]["from"]=result["connections"][0].pop("from_")
        return result

    city=place("NOIR", "ノワール")
    inn=place("INN", "ぬれねずみ亭", "NOIR")
    forge=place("FORGE", "鉄の咆哮", "NOIR")
    cave=place("HILLSIDE_CAVE_ENTRANCE", "裏山の洞窟", "NOIR")
    data={"schema":atlas.SCHEMA,"places":[city,inn,forge,cave]}
    frozen=copy.deepcopy(data)
    assert atlas.validate(data)==[]
    cases.append("complete_graph_valid")

    def bad(label, change):
        broken=copy.deepcopy(data);change(broken)
        assert atlas.validate(broken), label
        cases.append(label)

    bad("missing_schema",lambda d:d.pop("schema"))
    bad("duplicate_place_id",lambda d:d["places"].append(copy.deepcopy(inn)))
    bad("unknown_parent",lambda d:d["places"][1].update(parent_id="MISSING"))
    bad("parent_cycle",lambda d:d["places"][0].update(parent_id="INN"))
    bad("dangling_room_connection",lambda d:d["places"][1]["connections"][0].update(to="MISSING"))
    bad("disconnected_room",lambda d:d["places"][1]["connections"].clear())
    bad("missing_entry",lambda d:d["places"][1]["rooms"][0].update(entry=False))
    bad("unknown_floor",lambda d:d["places"][1]["rooms"][0].update(floor="2F"))
    bad("duplicate_room_id",lambda d:d["places"][1]["rooms"][0].update(id="NOIR_ENTRY"))
    bad("invalid_access",lambda d:d["places"][1]["rooms"][0].update(access="free-pass"))
    bad("invalid_edge_type_reports_error",lambda d:d["places"][1]["connections"][0].update(to={}))
    bad("invalid_parent_type_reports_error",lambda d:d["places"][1].update(parent_id={}))
    vertical=copy.deepcopy(data)
    vertical["places"][1]["architecture"]["levels"].append("2F")
    vertical["places"][1]["rooms"][1]["floor"]="2F"
    assert atlas.validate(vertical)
    cases.append("vertical_teleport_rejected")
    vertical["places"][1]["connections"][0]["via"]="木のはしご"
    assert atlas.validate(vertical)==[]
    cases.append("explicit_vertical_route_valid")
    campus=copy.deepcopy(data)
    campus["places"][1]["architecture"]["levels"]=["校舎1F","屋外","寮1F","寮2F","校舎B1F"]
    campus["places"][1]["rooms"][0]["floor"]="校舎1F"
    campus["places"][1]["rooms"][1]["floor"]="屋外"
    campus["places"][1]["connections"][0]["via"]="外扉と平坦な通路"
    assert atlas.validate(campus)==[]
    campus["places"][1]["rooms"][1]["floor"]="寮1F"
    assert atlas.validate(campus)==[]
    cases.append("building_prefixed_ground_floors_connect_to_outdoors_without_stairs")
    campus["places"][1]["rooms"][1]["floor"]="寮2F"
    assert atlas.validate(campus)
    campus["places"][1]["connections"][0]["via"]="中庭から寮2Fへ上がる階段"
    assert atlas.validate(campus)==[]
    cases.append("building_prefixed_upper_floor_still_requires_vertical_route")
    campus["places"][1]["rooms"][1]["floor"]="校舎B1F"
    campus["places"][1]["connections"][0]["via"]="外扉と平坦な通路"
    assert atlas.validate(campus)
    campus["places"][1]["connections"][0]["via"]="地下へ降りる石段"
    assert atlas.validate(campus)==[]
    cases.append("building_prefixed_basement_never_treated_as_ground")
    restricted=copy.deepcopy(data)
    restricted["places"][1]["rooms"][1]["access"]="hidden"
    restricted["places"][1]["connections"][0]["access"]="locked"
    assert atlas.validate(restricted)==[]
    assert atlas.project(restricted,{"locations":["ぬれねずみ亭"],"rooms":[]})["places"][0]["rooms"][1]["access"]=="hidden"
    cases.append("locked_hidden_graph_does_not_grant_access")

    def projected(locations, rooms=None, saved=None, interior=False):
        return atlas.project(data,dict(locations=locations,rooms=rooms or [],saved_place_id=saved,dungeon_interior=interior))

    assert [p["id"] for p in projected(["ぬれねずみ亭"])["places"]]==["INN"]
    cases.append("exact_facility")
    assert [p["id"] for p in projected(["ぬれねずみ亭の別名"])["places"]]==["INN"]
    cases.append("exact_alias")
    address=projected(["ノワール/ぬれねずみ亭/2階"])
    assert [p["id"] for p in address["places"]]==["INN"] and [p["id"] for p in address["parent_context"]]==["NOIR"]
    assert "description" not in address["parent_context"][0]["navigation_nodes"][0]
    cases += ["compound_address_leaf_only","parent_navigation_is_bounded"]
    assert projected(["知らない宿の裏口"])["places"]==[]
    assert projected(["新しい無名の村"])["places"]==[]
    cases.append("generic_words_do_not_match_unrelated_stage")
    generic=copy.deepcopy(data);generic["places"][1]["aliases"].append("冒険者ギルド")
    assert atlas.project(generic,dict(locations=["新しい冒険者ギルド"],rooms=[]))["places"]==[]
    assert len(atlas.project(generic,dict(locations=["冒険者ギルド"],rooms=[]))["places"])==1
    cases.append("long_generic_alias_is_exact_only")
    unknown=projected(["未設定の工房"])
    assert unknown["undefined_queries"] and "創作" in atlas.render_view(unknown)
    cases.append("unknown_place_remains_free")
    saved=dict(world_state=dict(location="ぬれねずみ亭",place_id="INN",room_id="INN_BACK",sub_location="裏口"))
    request=atlas.request_from(SimpleNamespace(location=["鉄の咆哮"],room=None),saved)
    assert request["rooms"]==[] and request["saved_place_id"] is None
    assert [p["id"] for p in atlas.project(data,request)["places"]]==["FORGE"]
    cases.append("explicit_destination_ignores_old_room")
    soul=dict(world_state=dict(location=""),hearing_progress=dict(current_step=3,status="in_progress"))
    assert atlas.request_from(SimpleNamespace(scene="start",location=None,room=None),soul)["locations"]==[]
    cases.append("soul_hearing_does_not_load_whole_inn")
    embodied=copy.deepcopy(soul);embodied["hearing_progress"]["current_step"]=7
    assert atlas.request_from(SimpleNamespace(scene="start",location=None,room=None),embodied)["locations"]==["INN_DRENCHED_RAT"]
    assert embodied["world_state"]["location"]==""
    cases.append("embodied_opening_reads_inn_without_moving_save")
    assert atlas.request_from(SimpleNamespace(scene="start",opening_step="SCRIPT_OPENING_FIRE",location=None,room=None),soul)["locations"]==["INN_DRENCHED_RAT"]
    cases.append("explicit_opening_stage_has_known_physical_stage")
    assert [p["id"] for p in projected(["ノワール"],saved="INN")["places"]]==["INN"]
    cases.append("saved_facility_refines_parent_label")
    conflict=projected(["鉄の咆哮"],saved="INN")
    assert [p["id"] for p in conflict["places"]]==["FORGE"] and conflict["stale_position_fields"]==["INN"]
    cases.append("stale_place_id_does_not_override_current_label")
    unknown_label=projected(["新しい未登録の店"],saved="INN")
    assert unknown_label["places"]==[] and unknown_label["stale_position_fields"]==["INN"]
    cases.append("stale_id_does_not_replace_unknown_current_stage")
    assert [p["id"] for p in projected(["ノワール"],["INN_BACK"])["places"]]==["INN"]
    cases.append("unique_room_id_refines_town")
    wrong=projected(["鉄の咆哮"],["INN_BACK"])
    assert [p["id"] for p in wrong["places"]]==["FORGE"] and wrong["room_focus"]==[]
    cases.append("stale_other_facility_room_ignored")
    assert projected(["ぬれねずみ亭"],["裏口"])["room_focus"]==[{"place_id":"INN","room_id":"INN_BACK"}]
    cases.append("generic_room_name_is_scoped")
    aliases=copy.deepcopy(data)
    aliases["places"][1]["aliases"].append("同名店");aliases["places"][2]["aliases"].append("同名店")
    ambiguous=atlas.project(aliases,dict(locations=["同名店"],rooms=[]))
    assert ambiguous["places"]==[] and ambiguous["ambiguous_queries"]
    cases.append("ambiguous_alias_is_not_guessed")
    scoped=copy.deepcopy(data)
    plaza=place("PLAZA","ノワール中央広場","NOIR");plaza["aliases"].append("中央広場")
    village=place("RABI","ラビラビ村");village["rooms"][1]["name"]="村の広場と掲示板"
    village_inn=place("RABI_INN","ラビラビ村の宿","RABI");village_inn["aliases"].append("村の宿")
    clinic=place("NOIR_CLINIC","ノワールの診療所","NOIR");clinic["aliases"].append("保健室")
    scoped["places"] += [plaza,village,village_inn,clinic]
    def scope_view(query, current=None):
        return atlas.project(scoped,dict(locations=[query],rooms=[],source_place_id=current,
                            source_location="ラビラビ村" if current=="RABI" else None,saved_place_id=None))
    v=scope_view("ラビラビ村/中央広場")
    assert [p["id"] for p in v["places"]]==["RABI"] and v["room_focus"]==[{"place_id":"RABI","room_id":"RABI_BACK"}]
    cases.append("named_village_square_never_selects_foreign_city_plaza")
    assert [p["id"] for p in scope_view("ノワール/中央広場")["places"]]==["PLAZA"]
    cases.append("named_city_square_selects_its_own_plaza")
    assert [p["id"] for p in scope_view("中央広場","RABI")["places"]]==["RABI"]
    cases.append("bare_square_prefers_current_village")
    assert [p["id"] for p in scope_view("村の宿","RABI")["places"]]==["RABI_INN"]
    assert scope_view("保健室","RABI")["places"]==[]
    cases.append("generic_facilities_are_scoped_to_current_settlement")
    assert [p["id"] for p in scope_view("ぬれねずみ亭","RABI")["places"]]==["INN"]
    cases.append("proper_destination_can_leave_current_settlement")
    interior=projected(["裏山の洞窟"],interior=True)
    assert interior["places"]==[] and len(interior["exterior_context"])==1 and "内部" in atlas.render_view(interior)
    cases.append("dungeon_interior_does_not_reuse_entrance_graph")
    same_cave=atlas.request_from(SimpleNamespace(location=["裏山の洞窟"],room=None),dict(world_state=dict(location="裏山の洞窟",depth=3)))
    assert atlas.project(data,same_cave)["places"]==[] and same_cave["dungeon_interior"] is True
    cases.append("explicit_same_cave_does_not_override_active_depth")
    explicit=atlas.request_from(SimpleNamespace(location=["裏山の洞窟入口"],room=None),dict(world_state=dict(location="裏山の洞窟",depth=3)))
    assert len(atlas.project(data,explicit)["places"])==1 and explicit["dungeon_interior"] is False
    cases.append("explicit_entrance_arrival_reads_full_exterior")
    book=atlas.renderer(data)
    assert all(room["id"] in book for p in data["places"] for room in p["rooms"])
    assert data==frozen
    cases += ["book_contains_all_stage_nodes","projection_does_not_mutate_canon"]

    with tempfile.TemporaryDirectory(prefix="machadan-place-atlas-") as temp:
        game=Path(temp)/"machadan_spade";root=game/"muse版"
        shutil.copytree(source,root,ignore=shutil.ignore_patterns("saves","state","__pycache__","*.pyc"))
        shutil.copy2(source.parent/"VERSION.txt",game/"VERSION.txt")
        (root/atlas.RELATIVE_PATH).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
        (root/"世界/舞台資料集.md").write_text(book)
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        manifest={"schema":"machadan-runtime-manifest-v1","version":re.search(r"(?im)^version:\s*(.+)$",(game/"VERSION.txt").read_text()).group(1).strip(),"base":"machadan_spade","files":[dict(path=p.relative_to(game).as_posix(),size=p.stat().st_size,sha256=digest(p)) for p in sorted(game.rglob("*")) if p.is_file()]}
        (game/"RUNTIME_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        runtime=root/"tools/machadan_runtime.py";doctor=root/"tools/check_knowledge.py"
        def run(command,expected=True,error=None):
            process=subprocess.run([sys.executable,"-B",*map(str,command)],text=True,capture_output=True)
            payload=json.loads(process.stdout)
            assert (process.returncode==0)==expected,(payload,process.stderr)
            assert payload.get("ok")==expected,payload
            if error:assert any(row.get("code")==error for row in payload.get("errors",[])),payload
            return payload
        save=root/"saves/place-probe.yaml";context=root/"state/runtime/place-probe/context.md"
        receipt=context.with_suffix(".md.receipt.json")
        run([runtime,"new-save","--campaign-id","place-probe","--output",save])
        run([runtime,"prepare-context","--save",save,"--scene","turn","--output",context,"--room","INN_BACK"])
        command=[doctor,"--root",root,"--turn","--save",save,"--receipt",receipt,"--json"]
        run(command)
        rows=json.loads(receipt.read_text())["sources"]
        atlas_rows=[row for row in rows if row["resource"]=="PLACE_ATLAS"]
        assert len(atlas_rows)==1 and atlas_rows[0]["mode"]=="place_view"
        cases += ["cli_room_context_and_turn_receipt","exactly_one_narrow_place_source"]
        original_context=context.read_bytes();original_receipt=receipt.read_bytes()
        run([runtime,"prepare-context","--save",save,"--scene","turn","--location","INN","--output",context])
        id_rows=json.loads(receipt.read_text())["sources"]
        assert any(row["resource"]=="PERSONA" and row["source"]=="人格/Lilith.md" for row in id_rows)
        run(command)
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("canonical_destination_id_also_loads_resident_persona")
        original_save=save.read_bytes()
        sys.path.insert(0,str(root/"tools/_vendor"))
        import yaml
        remembered=yaml.safe_load(original_save)
        remembered["world_state"].update(location="ノワール",place_id="INN",room_id="INN_BACK")
        remembered["world_state"]["campaign_lore"]={"old_INN_renovation":{"location":"INN","text":"SAVED_RENOVATION_UNIQUE"},
            **{f"other_fact_{i}":{"location":"無関係の場所","text":str(i)} for i in range(25)}}
        save.write_text(yaml.safe_dump(remembered,allow_unicode=True,sort_keys=False))
        run([runtime,"prepare-context","--save",save,"--scene","turn","--output",context])
        assert "SAVED_RENOVATION_UNIQUE" in context.read_text()
        remembered_receipt=json.loads(receipt.read_text())
        assert "INN" in remembered_receipt["view_subjects"]
        run(command)
        save.write_bytes(original_save);context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("old_campaign_renovation_survives_bounded_stage_view")
        atlas_path=root/atlas.RELATIVE_PATH;original_atlas=atlas_path.read_bytes()
        atlas_path.write_bytes(original_atlas+b"\n")
        run(command,False,"turn_source_changed")
        atlas_path.write_bytes(original_atlas)
        cases.append("changed_canonical_atlas_rejected")
        changed=context.read_text().replace("# 今回の場所と構造 — GM参照用","# 今回の場所と構造 — 改ざん",1)
        context.write_text(changed);changed_receipt=json.loads(original_receipt)
        changed_receipt["context_sha256"]=digest(context);receipt.write_text(json.dumps(changed_receipt))
        run(command,False,"turn_context_changed")
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("rehashed_projection_body_change_rejected")
        changed_receipt=json.loads(original_receipt)
        changed_receipt["sources"]=[row for row in changed_receipt["sources"] if row["resource"]!="PLACE_ATLAS"]
        text=re.sub(r"(?ms)^### SOURCE: "+re.escape(atlas.SOURCE_LABEL)+r"\n\n.*?(?=^### SOURCE: |\Z)","",context.read_text(),count=1)
        context.write_text(text);changed_receipt["context_sha256"]=digest(context);receipt.write_text(json.dumps(changed_receipt))
        run(command,False,"turn_place_atlas")
        context.write_bytes(original_context);receipt.write_bytes(original_receipt)
        cases.append("missing_stage_projection_rejected")
        before=save.read_bytes()
        run([runtime,"prepare-context","--save",save,"--scene","turn","--location","未設定の小屋","--output",root/"state/runtime/place-probe/unknown.md"])
        assert save.read_bytes()==before
        cases.append("unknown_destination_context_does_not_move_save")
    return {"ok":True,"cases":len(cases),"case_ids":cases,"source_unchanged":True}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent.parent)
    args=parser.parse_args()
    try:result=check(args.root.resolve())
    except Exception as exc:result={"ok":False,"error":str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result.get("ok") else 1)
