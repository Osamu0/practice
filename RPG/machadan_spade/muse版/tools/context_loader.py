"""Assemble complete relevant sections, with bounded state and explicit receipts.

An unknown fictional subject is an opening for the GM. A damaged packaged
rule is an installation problem. These are deliberately different cases.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
from pathlib import Path

from save_changes import state_view


def exploration_floor_terms(world):
    """Include the source habitat of active lower-floor pursuers in GM context."""
    run = world.get("dungeon_run", {})
    floor = run.get("current_floor") or world.get("depth")
    floors = [floor] if isinstance(floor, int) and not isinstance(floor, bool) else []
    if run.get("active") and floors:
        day = run.get("resource_days_by_floor", {}).get(str(floor), world.get("day"))
        rec = world.get("dungeon_memory", {}).get("records", {}).get(f"d{day}-f{floor}", {})
        for incursion in rec.get("incursions", []):
            origin = incursion.get("origin_floor")
            if incursion.get("phase") in {"signs", "engaged"} and origin not in floors:
                if isinstance(origin, int) and not isinstance(origin, bool) and 1 <= origin <= 9:
                    floors.append(origin)
    return [f"{number}F" for number in floors]


OPENING = {
    1: ["SCRIPT_OPENING_AWAKENING", "SCRIPT_OPENING_PLAY_MODE"],
    2: ["SCRIPT_OPENING_NAME"], 3: ["SCRIPT_OPENING_BODY"],
    4: ["SCRIPT_OPENING_DESIRE"], 5: ["SCRIPT_OPENING_PARTNER"],
    6: ["SCRIPT_OPENING_STYLE"],
    7: ["SCRIPT_OPENING_REBIRTH", "SCRIPT_OPENING_FIRE", "SCRIPT_OPENING_BONUS", "SCRIPT_OPENING_TUTORIAL"],
}


def atlas_defined_subject(place_view, term):
    """A missing old service-catalog entry must not erase a loaded building."""
    from place_atlas import normalize, _floor_position
    wanted = normalize(term)
    if not wanted:
        return False
    known = set()
    floors = set()
    for place in [*place_view.get("places", []), *place_view.get("parent_context", []),
                  *place_view.get("exterior_context", [])]:
        aliases = [place.get("id"), place.get("name"), *place.get("aliases", [])]
        known.update(normalize(value) for value in aliases if value)
        floors.update(_floor_position(value) for value in place.get("architecture", {}).get("levels", []))
        for room in [*place.get("rooms", []), *place.get("navigation_nodes", [])]:
            known.update(normalize(room[key]) for key in ("id", "name") if room.get(key))
    if wanted in known:
        return True
    parts = [value.strip() for value in re.split(r"[/／>＞]", str(term)) if value.strip()]
    return len(parts) > 1 and all(normalize(value) in known or _floor_position(value) in floors for value in parts)


def resolve_phase(args, save, scenes):
    """Use committed cards, never an assumed player intention, for auto routing."""
    requested = getattr(args, "phase", "auto")
    world = (save or {}).get("world_state", {})
    cards = [world.get("quest_card"), (save or {}).get("active_event")]
    has_card = any(isinstance(card, dict) and (card.get("quest_id") or card.get("event_id"))
                   for card in cards)
    if requested != "auto":
        if requested in {"advance", "offer", "settle"} and "quest" in scenes and not has_card:
            return "create", "依頼カードが未確定のため生成に必要な規則を取得"
        return requested, "explicit"
    if "quest" in scenes:
        return ("advance", "committed_card") if has_card else ("create", "no_committed_card")
    if "event" in scenes:
        ongoing = has_card or isinstance(world.get("event_reward_contract"), dict)
        return ("advance", "committed_event") if ongoing else ("probe", "event_occurrence_first")
    # Combat can begin during an existing quest. Its card does not prove combat
    # has already started, so auto keeps encounter-creation rules conservatively.
    return "create", "conservative_default"


def semantic_span(text, specification):
    """Resolve whole meaningful sections despite Markdown-looking comment lines.

    Endpoints are exact source headings, not fixed character/line budgets. An
    edited/missing endpoint raises and the caller loads the same source in full.
    """
    lines = text.splitlines()
    start_marker = specification.get("start")
    end_marker = specification.get("end_before")
    if start_marker is None:
        start = 0
    else:
        matches = [i for i, line in enumerate(lines) if line.strip() == start_marker]
        if len(matches) != 1:
            raise ValueError("semantic start heading is missing or ambiguous: " + str(start_marker))
        start = matches[0]
    if end_marker is None:
        end = len(lines)
    else:
        matches = [i for i, line in enumerate(lines) if i > start and line.strip() == end_marker]
        if len(matches) != 1:
            raise ValueError("semantic end heading is missing or ambiguous: " + str(end_marker))
        end = matches[0]
    if start >= end:
        raise ValueError("empty semantic section")
    return {"id": "PHASE_" + specification["id"], "title": specification["id"],
            "start": start + 1, "end": end, "line_count": end - start}


def location_kind(args, world, scenes):
    explicit = getattr(args, "location_kind", None)
    if "dungeon" in scenes or world.get("dungeon_run", {}).get("active") is True:
        return "dungeon"
    if explicit:
        return explicit
    stored = world.get("location_kind") or world.get("location_type")
    if stored in {"town", "road", "dungeon"}:
        return stored
    # Backward compatible hints for old saves; explicit --location-kind wins.
    location = str(world.get("location", "")).casefold()
    return "road" if any(word in location for word in ("travel", "街道", "道中", "街の外", "峠")) else "town"


def project_inventory(stock, resource, place_kind, campaign_id, world_context=None, event_type=None):
    from event_connections import unmet, requirements
    wanted = set(stock.get("limits", {})) if resource == "MOB_INVENTORY_STATE" else {place_kind}
    entries = []
    for category in sorted(wanted):
        entries.extend([item for item in stock.get("entries", [])
                        if item.get("category") == category and item.get("status") == "unused"
                         and (resource != "EVENT_INVENTORY_STATE" or event_type is None
                              or requirements(item)["type"] == event_type)
                         and (resource != "EVENT_INVENTORY_STATE" or world_context is None
                              or not unmet(item, world_context))
                        and (not item.get("campaign_id") or item.get("campaign_id") == campaign_id)][:4])
    return {"schema": stock.get("schema"), "kind": stock.get("kind"), "entries": entries,
            "notice": "表示外の未使用在庫はinventory-statusと元の在庫YAMLで参照できる。空なら在庫確認か新規生成を行う"}


def context_paths(args, api):
    """Reject all read/write aliases before even inventory initialization runs."""
    source = Path(args.save).expanduser().resolve() if args.save else None
    output = Path(args.output).expanduser().resolve() if args.output else api.DEFAULT_CONTEXT.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    candidate = (Path(args.candidate_save_output).expanduser().resolve()
                 if getattr(args, "candidate_save_output", None) else None)
    changes = candidate.with_suffix(".changes.json") if candidate else None
    paths = [(label, path) for label, path in (
        ("save", source), ("output", output), ("receipt", receipt),
        ("candidate", candidate), ("changes_template", changes)) if path is not None]
    for position, (label, path) in enumerate(paths):
        for other_label, other in paths[:position]:
            if path == other:
                raise api.RuntimeProblem(f"context paths alias: {label} and {other_label}")
    game = api.ROOT.parent.resolve()
    runtime_output = (api.ROOT / "state/runtime").resolve()
    workspace = game.parent
    skill_roots = [(workspace / name).resolve() for name in ("skills", "custom-skills")]
    for label, target in paths:
        if label == "save":
            continue
        if target.is_relative_to(game) and not target.is_relative_to(runtime_output):
            raise api.RuntimeProblem("generated context/candidate paths must stay outside canonical game files and saves, or in state/runtime: " + str(target))
        if any(target.is_relative_to(directory) for directory in skill_roots):
            raise api.RuntimeProblem("generated context/candidate must not overwrite a skill: " + str(target))
        if source is not None and (source.parent.name == "saves" or "saves" in source.parent.parts):
            # External save stores deserve the same protection as ROOT/saves.
            ancestors = [parent for parent in source.parents if parent.name == "saves"]
            if any(target.is_relative_to(parent) for parent in ancestors):
                raise api.RuntimeProblem("generated files must not be placed inside a save store: " + str(target))
    return source, output, receipt, candidate, changes


def build_context(args, api) -> dict:
    root = api.ROOT
    save_path, output_path, receipt_path, candidate_path, changes_path = context_paths(args, api)
    _, routes, resources = api.load_control()
    index = api.load_anchors()
    scene = api.resolve_scene(routes, args.scene)
    included = []
    for requested in getattr(args, "include_scene", None) or []:
        resolved = api.resolve_scene(routes, requested)
        if resolved != scene and resolved not in included:
            included.append(resolved)
    save = api.load_yaml(save_path) if save_path else None
    if save is not None:
        errors, warnings = api.validate_save_data(save)
        if errors:
            raise api.RuntimeProblem("save validation failed: " + "; ".join(errors))
    else:
        warnings = []
        if scene != "start" or included:
            raise api.RuntimeProblem("--save is required except for the start scene")
    world = save.get("world_state", {}) if save else {}
    from place_atlas import load as load_atlas, request_from as place_request_from, project as project_places, render_view as render_places, SOURCE_LABEL
    place_request = place_request_from(args, save, scene)
    atlas_path = api.resource_path(resources, "PLACE_ATLAS")
    atlas_data = load_atlas(atlas_path)
    place_view = project_places(atlas_data, place_request)
    regional_data = None
    if "REGIONAL_WORLD" in resources:
        from regional_world import load as load_region, request_from as region_request_from, project as project_region
        regional_path = api.resource_path(resources, "REGIONAL_WORLD")
        regional_data = load_region(regional_path)
        regional_request = region_request_from(args, save, place_view, atlas_data, regional_data)
        regional_view = project_region(regional_data, regional_request)
    prior_state = (save or {}).get("runtime_state", {})
    prior_style = prior_state.get("ero_scene")
    if prior_style is None:
        prior_style = prior_state.get("active_scene") in {"ero", "style"}
    style_switch = getattr(args, "intimate_scene", "auto")
    explicit_style = "style" in [scene, *included] or "yuri" in (getattr(args, "condition", None) or [])
    if style_switch == "off" and explicit_style:
        raise api.RuntimeProblem("専用文体を終了する時は次の通常場面を指定し、styleとyuriを外してください")
    if style_switch == "auto":
        style_active = explicit_style or prior_style is True
    else:
        style_active = style_switch == "on"
    if style_active and "style" not in [scene, *included]:
        included.append("style")
    if save and save.get("debt_state", {}).get("collection_pending") and "debt" not in [scene, *included]:
        included.append("debt")
    scenes = [scene, *included]
    phase, phase_reason = resolve_phase(args, save, scenes)
    place_kind = location_kind(args, world, scenes)
    from movement_events import from_args as movement_from_args
    try:
        movement = movement_from_args(args, world, scenes, place_kind)
    except ValueError as exc:
        raise api.RuntimeProblem(str(exc)) from exc
    packs = routes["scene_packs"]
    notes = []
    selected = []
    cached_text = {}
    resolved_subjects = []

    def text_for(path):
        if path not in cached_text:
            cached_text[path] = path.read_text(encoding="utf-8")
        return cached_text[path]

    def select(path, resource, origin, anchor=None):
        relative = path.relative_to(root).as_posix()
        for item in list(selected):
            if item["relative"] != relative:
                continue
            old = item["anchor"]
            if old is None or (anchor is not None and old["start"] <= anchor["start"] and old["end"] >= anchor["end"]):
                if origin not in item["origins"]:
                    item["origins"].append(origin)
                return
            if anchor is None or (anchor["start"] <= old["start"] and anchor["end"] >= old["end"]):
                selected.remove(item)
        selected.append({"path": path, "relative": relative, "resource": resource,
                         "anchor": anchor, "origins": [origin]})

    def query(path, resource, terms, origin):
        info = index.get("files", {}).get(path.relative_to(root).as_posix(), {})
        anchors = info.get("anchors", [])
        lines = text_for(path).splitlines()
        found = False
        for term in dict.fromkeys(str(t).strip() for t in terms if str(t).strip()):
            folded = term.casefold()
            exact = [a for a in anchors if a["id"].casefold() == folded or a["title"].casefold() == folded]
            title = exact or [a for a in anchors if folded in a["title"].casefold()]
            candidates = title or [a for a in anchors if any(folded in line.casefold()
                                  for line in lines[a["start"]-1:a["end"]])]
            # Remove enclosing headings; preserve all distinct leaf matches.
            leaves = [a for a in candidates if not any(
                b is not a and a["start"] <= b["start"] and a["end"] >= b["end"]
                and (a["start"], a["end"]) != (b["start"], b["end"])
                for b in candidates)]
            if not leaves:
                if resource == "LOCATIONS" and atlas_defined_subject(place_view, term):
                    notes.append({"kind": "atlas_defined_place", "resource": resource, "term": term,
                                  "action": "構造はPLACE_ATLASで確定済み。サービスの未定義部分は既存の汎用ルールと施設limitsの範囲で補完し、部屋や階数を作り替えない。"})
                    found = True
                    continue
                notes.append({"kind": "undefined_subject", "resource": resource, "term": term,
                              "action": "既存設定と矛盾しない範囲で創作し、必要な事実をキャンペーンへ記録する"})
                continue
            if len(leaves) > 6:
                # Broad ambiguous words must not accidentally load a whole corpus.
                notes.append({"kind": "broad_query", "resource": resource, "term": term,
                              "candidates": [a["id"] for a in leaves],
                              "action": "必要になった対象名または節IDで絞り直す。物語全体を止めない"})
                continue
            for anchor in leaves:
                select(path, resource, origin, anchor)
            resolved_subjects.append({"resource": resource, "term": term,
                                      "anchors": [a["id"] for a in leaves]})
            found = True
        return found

    legacy_terms = list(getattr(args, "term", None) or [])
    typed = {key: list(getattr(args, key, None) or []) for key in ("location", "enemy", "item", "topic")}
    if world.get("location"):
        typed["location"].append(str(world["location"]))
    # A canonical place id supplied as the destination must also resolve its
    # existing service section and resident persona; ids are not prose aliases.
    typed["location"].extend(place["name"] for place in place_view["places"])
    for kind in ("enemy", "item"):
        # Legacy --term remains an explicit search input, never an automatic location alias.
        typed[kind].extend(legacy_terms)
    typed["topic"].extend(legacy_terms)
    if not typed["location"]:
        typed["location"].extend(legacy_terms)
    floor = world.get("dungeon_run", {}).get("current_floor") or world.get("depth")
    floor_terms = exploration_floor_terms(world)

    def terms_for(resource, kind=""):
        if resource == "LOCATIONS":
            return typed["location"]
        if resource == "MONSTERS":
            return list(dict.fromkeys(typed["enemy"] + floor_terms)) if len(floor_terms) > 1 else typed["enemy"] or floor_terms
        if resource == "DUNGEON_DATA":
            return floor_terms or typed["topic"]
        if resource == "ITEMS":
            return typed["item"]
        return typed["topic"]

    phase_loading = routes.get("phase_loading", {})
    phase_profiles = phase_loading.get("profiles", {}) if any(
        name in phase_loading.get("scenes", []) for name in scenes) else {}
    conditions = set()

    def add_entry(entry, origin):
        resource = entry.get("resource")
        if not resource:
            return
        if resource in {"PLACE_ATLAS", "REGIONAL_WORLD"}:
            # The atlas is one canonical source, but its authoring data must
            # never become an all-town/all-building prompt on an ordinary turn.
            return
        path = api.resource_path(resources, resource)
        profile = phase_profiles.get(resource)
        source_scene = origin.split(":")[1] if ":" in origin else None
        if profile and profile.get("scenes") and source_scene not in profile["scenes"]:
            profile = None
        if profile:
            specifications = [*profile.get("common", []),
                              *profile.get("phases", {}).get(phase, [])]
            for condition in sorted(conditions):
                specifications.extend(profile.get("conditions", {}).get(condition, []))
            if profile.get("rank_sections") and phase in profile.get("rank_phases", ["create", "offer", "advance", "settle", "probe"]):
                rank = str((save or {}).get("player", {}).get("rank") or "E").upper()
                if rank not in profile["rank_sections"]:
                    select(path, resource, origin + ":unknown-rank-recovery")
                    notes.append({"kind": "rank_selector_recovered", "resource": resource,
                                  "action": "ランクを一意に照合できないため同じ正本全文で補完済み"})
                    return
                specifications.extend(profile["rank_sections"][rank])
            specifications = [spec for spec in specifications
                              if phase in spec.get("phases", ["create", "offer", "advance", "settle", "probe"])]
            if specifications:
                try:
                    anchors = [semantic_span(text_for(path), s) for s in specifications]
                except (ValueError, KeyError) as exc:
                    select(path, resource, origin + ":phase-recovery")
                    notes.append({"kind": "phase_selector_recovered", "resource": resource,
                                  "detail": str(exc), "action": "同じ正本の全文で補完済み"})
                else:
                    for anchor in anchors:
                        select(path, resource, origin + ":phase:" + phase, anchor)
                if resource == "ITEMS" and typed["item"]:
                    query(path, resource, typed["item"], origin + ":named-items")
                return
        mode = entry.get("mode") or resources[resource].get("load", "full")
        if mode not in {"section", "sections"}:
            select(path, resource, origin)
            return
        selectors = entry.get("selectors") or entry.get("default_selectors") or []
        if not selectors:
            if not query(path, resource, terms_for(resource), origin):
                if entry.get("fallback_full"):
                    select(path, resource, origin + ":full-recovery")
                    notes.append({"kind": "selector_recovered", "resource": resource,
                                  "action": "必要な追加資料の節を絞れなかったため、同じ資料の全文を読込済み"})
                else:
                    notes.append({"kind": "available_on_demand", "resource": resource,
                                  "path": path.relative_to(root).as_posix(),
                                  "action": "この資料が必要になった時にtopicまたはtermで該当節を追加取得する"})
            return
        for selector in selectors:
            try:
                anchor = api.anchor_for_selector(index, path.relative_to(root).as_posix(), selector)
            except api.RuntimeProblem:
                # Required source is present: recover internally by reading its full text.
                select(path, resource, origin + ":selector-recovery")
                notes.append({"kind": "selector_recovered", "resource": resource,
                              "selector": selector, "action": "同じ正本の全文で補完済み"})
                continue
            select(path, resource, origin, anchor)

    base = routes.get("base_pack", {})
    for group in ("required", "verify_after_turn"):
        for entry in api._entry_list(base.get(group)):
            add_entry(entry, "base_pack" if group == "required" else "base_pack.verify_after_turn")
    known_conditions = {e.get("when") for p in packs.values()
                        for group in ("conditional", "after") for e in p.get(group, [])}
    known_conditions |= set(routes.get("global_conditions", {}))
    conditions = set(prior_state.get("style_conditions", [])) if style_active and style_switch == "auto" else set()
    for condition in getattr(args, "condition", None) or []:
        if condition in known_conditions:
            conditions.add(condition)
        else:
            close = difflib.get_close_matches(condition, sorted(known_conditions), n=2, cutoff=.88)
            if len(close) == 1:
                conditions.add(close[0])
                notes.append({"kind": "condition_corrected", "from": condition, "to": close[0]})
            else:
                notes.append({"kind": "undefined_condition", "condition": condition,
                              "action": "新しい行動として既存の汎用判定を応用する"})
                conditions.add("general_check")
    for condition in sorted(conditions):
        for entry in routes.get("global_conditions", {}).get(condition, []):
            add_entry(entry, "condition:global:" + condition)
    for name in scenes:
        pack = packs[name]
        for entry in pack.get("required", []):
            add_entry(entry, "scene:" + name)
        for group in ("conditional", "after"):
            for entry in pack.get(group, []):
                if entry.get("when") not in conditions:
                    continue
                for rid in ([entry["resource"]] if entry.get("resource") else []) + entry.get("resources", []):
                    add_entry({**entry, "resource": rid}, f"{group}:{name}:{entry['when']}")

    if movement and movement["roll_required"]:
        add_entry({"resource": "RANDOM_EVENT_RULES", "mode": "full"}, "movement:M51")

    if "start" in scenes:
        step = (save or {}).get("hearing_progress", {}).get("current_step", 1)
        if (save or {}).get("hearing_progress", {}).get("status") == "complete":
            step = 7
        opening = getattr(args, "opening_step", None)
        script = (save or {}).get("active_script", {})
        if step == 7 and save:
            from onboarding import status_data
            initial = status_data(save)
            ids = [initial["next_script"]] if initial.get("next_script") else []
            if opening:
                ids = [opening]
        else:
            ids = [opening] if opening else ([script["id"]] if script.get("status") == "in_progress"
                                           and script.get("id", "").startswith("SCRIPT_")
                                           else OPENING.get(step, OPENING[7]))
        if ids:
            add_entry({"resource": "TEMPLATES", "mode": "sections",
                       "selectors": [{"id": s, "match": "[" + s + "]"} for s in ids]}, "dynamic:start:current_script")
        if any(s in {"SCRIPT_OPENING_BONUS", "SCRIPT_OPENING_FIRE", "SCRIPT_OPENING_TUTORIAL"} for s in ids):
            add_entry({"resource": "NUMBERS", "mode": "sections", "selectors": [
                {"match": "2. プレイヤー"}, {"match": "3. リリスの火"}]}, "dynamic:start:initial_values_and_fire")

    # The v3 id is authoritative. Unknown original characters may live only in save data.
    requests = list(getattr(args, "character", None) or [])
    persona_locations = [*typed["location"], *(alias for place in place_view["places"] for alias in place.get("aliases", []))]
    generic_locations = {"道具屋", "大聖堂", "聖堂", "鍛冶屋", "ギルド", "魔女の店"}
    for record in routes.get("location_personas", []):
        if any(alias.casefold() == location.casefold() or
               (alias not in generic_locations and alias.casefold() in location.casefold())
               for alias in record["aliases"]
               for location in persona_locations):
            requests.extend(record["characters"])
    if "start" in scenes or "debt" in scenes:
        requests.append("Lilith_000")
    aliases = routes.get("persona_aliases", {})
    requests = [aliases.get(str(value), value) for value in requests]
    for path in api.persona_paths(routes, requests, save):
        select(path, "PERSONA", "dynamic:persona")
    for value in requests:
        rid = aliases.get(str(value), value)
        if rid not in routes.get("persona_files", {}) and not any(
                p.stem.casefold() == str(rid).casefold() for p in (root / "人格").glob("*.md")):
            notes.append({"kind": "campaign_character", "character": value,
                          "action": "セーブ内の人物設定を使う。新規人物なら世界に合う設定を作って記録する"})

    for name in scenes:
        for entry in packs[name].get("dynamic", []):
            kind = entry.get("kind", "")
            if kind in {"active_save", "save_template", "active_character_personas", "shopkeeper_persona",
                        "target_character_personas", "lilith_persona"}:
                continue
            resource = entry.get("resource")
            if not resource:
                continue
            if movement and not movement["inventory_events_allowed"] and kind == "event_inventory":
                continue
            if name == "event" and phase == "probe" and kind in {"event_inventory", "overworld_context"}:
                continue  # Occurrence/type is determined before stock/material expansion.
            if kind in {"event_inventory", "mob_inventory"}:
                # Runtime-selected stock is projected below; use of an entry remains transaction-checked.
                add_entry(entry, f"dynamic:{name}:{kind}")
            elif entry.get("mode") == "full":
                add_entry(entry, f"dynamic:{name}:{kind}")
            else:
                query(api.resource_path(resources, resource), resource,
                      terms_for(resource, kind), f"dynamic:{name}:{kind}")

    manifest = []
    contents = []
    for item in selected:
        anchor = item["anchor"]
        text = text_for(item["path"])
        if anchor:
            text = "\n".join(text.splitlines()[anchor["start"]-1:anchor["end"]])
        # Show only usable stock for the current setting; never drop stock from disk.
        mode = "section" if anchor else "full"
        if item["resource"] in {"EVENT_INVENTORY_STATE", "MOB_INVENTORY_STATE"}:
            stock = api.load_yaml(item["path"])
            from event_connections import companion_ids
            run = world.get("dungeon_run") or {}
            event_context = {"location": world.get("location"),
                             "current_floor": run.get("current_floor") or world.get("depth"),
                             "companion_ids": companion_ids(save or {})}
            text = api.dump_yaml(project_inventory(stock, item["resource"], place_kind,
                                                  (save or {}).get("campaign_id"), event_context,
                                                  getattr(args, "event_type", None)))
            mode = "view"
        source = item["relative"] + ("#" + anchor["id"] if anchor else "")
        row = {"source": source, "sha256": hashlib.sha256(text.encode()).hexdigest(),
               "file_sha256": hashlib.sha256(item["path"].read_bytes()).hexdigest(),
               "mode": mode, "resource": item["resource"], "origin": item["origins"][0],
               "origins": item["origins"]}
        if anchor:
            row.update(start=anchor["start"], end=anchor["end"])
        manifest.append(row)
        contents.append((source, text))
    omitted = []
    save_hash = None
    place_text = render_places(place_view)
    manifest.append({"source": SOURCE_LABEL, "sha256": hashlib.sha256(place_text.encode()).hexdigest(),
                     "file_sha256": hashlib.sha256(atlas_path.read_bytes()).hexdigest(),
                     "mode": "place_view", "resource": "PLACE_ATLAS", "origin": "dynamic:current_stage"})
    contents.append((SOURCE_LABEL, place_text))
    if regional_data is not None:
        from regional_world import render_view as render_region, SOURCE_LABEL as REGION_LABEL
        regional_text = render_region(regional_view)
        manifest.append({"source": REGION_LABEL, "sha256": hashlib.sha256(regional_text.encode()).hexdigest(),
                         "file_sha256": hashlib.sha256(regional_path.read_bytes()).hexdigest(),
                         "mode": "regional_view", "resource": "REGIONAL_WORLD", "origin": "dynamic:regional_setting"})
        contents.append((REGION_LABEL, regional_text))
    view_subjects = [*requests, *typed["location"], *typed["topic"]]
    if regional_data is not None:
        from regional_world import view_subjects as regional_subjects
        view_subjects.extend(regional_subjects(regional_view))
    # Old campaign changes to a named building must survive bounded lore even
    # when the save's human location label is only its parent town.
    for place in [*place_view["places"], *place_view["parent_context"], *place_view.get("exterior_context", [])]:
        view_subjects.extend([place["id"], place["name"]])
    view_subjects.extend(row["room_id"] for row in place_view["room_focus"])
    # Include exactly the canonical cast whose persona was actually loaded,
    # including automatic party/shopkeeper selection, in the bounded overlay.
    selected_personas = {item["relative"] for item in selected if item["resource"] == "PERSONA"}
    view_subjects.extend(cid for cid, path in routes.get("persona_files", {}).items()
                         if path in selected_personas)
    view_subjects = list(dict.fromkeys(view_subjects))
    if save is not None:
        save_hash = hashlib.sha256(save_path.read_bytes()).hexdigest()
        view, omitted = state_view(save, scenes, subjects=view_subjects)
        text = api.dump_yaml(view)
        manifest.append({"source": str(save_path), "sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "file_sha256": save_hash, "mode": "view", "resource": "ACTIVE_SAVE", "origin": "base_pack"})
        contents.append(("ACTIVE_SAVE_VIEW — 表示専用。これをセーブへ上書きしない", "~~~yaml\n" + text.rstrip() + "\n~~~"))
    control = [{"source": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in (api.REGISTRY_PATH, api.ROUTES_PATH, api.ANCHORS_PATH)]
    body = ["# GENERATED CURRENT CONTEXT — NOT CANONICAL", "", f"- scene: {scene}",
            "- included_scenes: " + (", ".join(included) or "(none)"),
            f"- phase: {phase}", f"- location_kind: {place_kind}",
            f"- selected_prose_scene: {'dedicated' if style_active else 'ordinary'}",
            f"- saved_prose_mode: {(save or {}).get('ero_style') or '(not selected)'}",
            "- ACTIVE_SAVE_VIEWは確定済みの変更前状態。今回の場面切替はsave_state_patchに従う。",
            "- runtime_cast_rulesは完済台帳から導いた現在の人物制約。リリスの未解禁の好意を先取りしない。",
            "- appearance_customization.overridesは当該キャンペーンの外見だけ正本より優先。指定のない外見・成人性・人格・口調・関係・戦闘能力は正本どおり。",
            "- 設定済みの事実とルールを守り、未設定の物語は自由に広げる。",
            "- 検索メモは内部で補うための情報。未定義というだけでゲームを止めない。", "",
            "## Source receipt", ""]
    body += [f"- {s['source']} | sha256={s['sha256']} | {s['origin']}" for s in manifest]
    body += ["", "## Reference notes", json.dumps(notes, ensure_ascii=False), "",
             "## Save access", f"- save_revision: {(save or {}).get('save_revision')}",
             f"- save_sha256: {save_hash}",
             "- 表示を省いた履歴の詳細は read-save --save <current-save> --pointer <JSON-pointer> で取得する。",
             "- 通常の変更はapply-changesで完全な候補へ反映する。表示用抜粋からセーブを作り直さない。", ""]
    if movement:
        body += ["## Movement event plan (GM only)", json.dumps(movement, ensure_ascii=False),
                 "移動1回にM51は1回だけ。出た出来事は通り過ぎられる形にし、EV在庫は消費しない。確率・発生名は本文へ読み上げない。外れ・直行・急ぎの移動部分は2〜3行で到着し、水増ししない。", ""]
    if phase == "probe" and "event" in scenes:
        body += ["## 発生判定後の追加取得", "",
                 "発生しなければ通常描写へ進む。発生した場合は、同じ確定セーブから --phase create と選ばれた種別・対象を指定してcontextを再生成する。",
                 "probeだけでは在庫選定・新しい出来事の本文・報酬を確定しない。判定済みのダイス値とcursorを同じ候補へ引き継ぎ、発生判定を振り直さない。", ""]
    if phase == "advance" and "quest" in scenes:
        body += ["## 進行段階の切替", "",
                 "確定済みカードの事実・人物・制約・報酬契約を使って進行する。新しい依頼を作る場合はcreate、報酬の提示・受領・辞退・保留・清算を処理する場合はofferまたはsettleで再取得してから本文と候補を確定する。",
                 "進行から完結へ自然に到達してよい。追加取得のためにプレイヤーへ再入力を求めず、同じ入力と確定済み判定結果を引き継いで内部で切り替える。", ""]
    for source, text in contents:
        body += ["### SOURCE: " + source, "", text.rstrip(), ""]
    output_text = "\n".join(body).rstrip() + "\n"
    output = output_path
    candidate_output = None
    candidate_text = None
    candidate_idempotent = False
    if getattr(args, "candidate_save_output", None):
        if save is None:
            raise api.RuntimeProblem("--candidate-save-output requires --save")
        candidate_output = candidate_path
        if candidate_output.resolve() == save_path.resolve():
            raise api.RuntimeProblem("candidate output must not overwrite the current save")
    digest = hashlib.sha256(output_text.encode()).hexdigest()
    patch = {"active_scene": scene, "scene_id": scene, "context_pack_hash": digest,
             "ero_scene": style_active,
             "style_conditions": ["yuri"] if style_active and "yuri" in conditions else []}
    if candidate_output:
        candidate = copy.deepcopy(save)
        candidate.setdefault("runtime_state", {}).update(patch)
        errors, _ = api.validate_save_data(candidate)
        if errors:
            raise api.RuntimeProblem("context candidate is invalid: " + "; ".join(errors))
        candidate_text = api.dump_yaml(candidate)
        candidate_idempotent = candidate_output.is_file() and candidate_output.read_text(encoding="utf-8") == candidate_text
        if candidate_output.exists() and not candidate_idempotent and not getattr(args, "force_candidate", False):
            raise api.RuntimeProblem("refusing to overwrite existing candidate: " + str(candidate_output))
    receipt = {"schema": "machadan-context-receipt-v1", "scene": scene, "primary_scene": scene,
               "included_scenes": included, "generated_at": api.now_iso(), "control": control,
               "phase": phase, "phase_reason": phase_reason, "location_kind": place_kind,
               "conditions": sorted(conditions),
               "view_subjects": view_subjects,
               "place_request": place_request,
               "regional_request": regional_request if regional_data is not None else None,
               "sources": manifest, "context_sha256": digest, "warnings": warnings,
               "reference_notes": notes, "resolved_subjects": resolved_subjects,
               "ero_scene": style_active, "ero_style": (save or {}).get("ero_style"),
               "save_sha256": save_hash, "save_revision": (save or {}).get("save_revision"),
               "omitted_state_paths": omitted, "characters": len(output_text)}
    if movement:
        receipt["movement_event_plan"] = movement
    api.atomic_write(output, output_text)
    api.atomic_write(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    if candidate_output and not candidate_idempotent:
        api.atomic_write(candidate_output, candidate_text)
    changes_template = None
    if candidate_output:
        changes_template = changes_path
        if not changes_template.exists():
            api.atomic_write(changes_template, json.dumps({
                "schema": "machadan-save-changes-v1", "save_revision": save["save_revision"],
                "save_sha256": save_hash, "operations": [],
                "response": {"schema": "machadan-response-v1", "main_text": "", "system_blocks": [], "choices": [],
                             **({"movement": {key: movement[key] for key in ("style", "location_kind", "urgency")}} if movement else {})},
            }, ensure_ascii=False, indent=2) + "\n")
    return {"ok": True, "scene": scene, "resolved_scene": scene, "included_scenes": included,
            "phase": phase, "phase_reason": phase_reason, "location_kind": place_kind,
            "output": str(output), "receipt": str(receipt_path), "sources": len(manifest),
            "sha256": digest, "context_pack_hash": digest, "save_state_patch": patch,
            "candidate_save": str(candidate_output) if candidate_output else None,
            "candidate_idempotent": candidate_idempotent, "warnings": warnings,
            "changes_template": str(changes_template) if changes_template else None,
            **({"movement_event_plan": movement} if movement else {}),
            "reference_notes": notes, "save_sha256": save_hash,
            "save_revision": (save or {}).get("save_revision"), "characters": len(output_text)}
