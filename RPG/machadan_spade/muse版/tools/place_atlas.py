"""Deterministic, narrow projections of the canonical physical stage atlas.

Topology is author-defined. A graph describes doors, corridors and stairs; it
does not grant entry rights, reveal secrets to the player or change locations.
Unknown fictional stages remain available for ordinary campaign invention.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import unicodedata

SCHEMA = "machadan-place-atlas-v1"
VIEW_SCHEMA = "machadan-place-context-v1"
RELATIVE_PATH = "世界/舞台構造.json"
SOURCE_LABEL = RELATIVE_PATH + "#PLACE_ATLAS_VIEW"
ACCESS = {"public", "staff", "private", "locked", "hidden", "dangerous"}
ACCESS_LABELS = {"public": "一般", "staff": "関係者", "private": "私室・許可制", "locked": "施錠", "hidden": "未公開・秘密", "dangerous": "危険区域"}
KIND_LABELS = {"city": "町", "town": "町", "settlement": "町・集落", "village": "村", "district": "区画",
               "facility": "施設", "building": "建物", "site": "屋外拠点", "route": "道", "dungeon_entrance": "洞窟入口"}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_STRIP = re.compile(r"[\s\u3000「」『』\"'“”‘’【】\[\]（）()]+")
_GENERIC_ALIASES = {"宿", "宿屋", "村", "町", "道具屋", "鍛冶屋", "聖堂", "大聖堂", "教会", "ギルド", "冒険者ギルド", "魔女の店", "魔法専門店", "学園", "学校", "地下牢", "詰め所", "ダンジョン", "中央広場", "広場", "村の宿", "町の宿", "保健室", "裏口", "受付"}
_ROOM_LABELS = {"中央広場": ("広場",), "広場": ("広場",), "保健室": ("保健室", "医務室"),
                "裏口": ("裏口", "裏玄関", "勝手口"), "地下牢": ("地下牢", "監房", "牢"), "受付": ("受付",)}
_VERTICAL = re.compile(r"階段|石段|木段|段梯子|螺旋|梯子|はしご|昇降|坂|スロープ|斜路|傾斜|吹き?抜け|吹抜け|登り|上り|下り|登る|上る|下る|降り|降る|ロープ|縄|樹道|足場|登降|穴|坑道")

RULES = [
    "構造はGM用の舞台正本。資料にあるだけで人物が知った・入れた・移動した扱いにしない。",
    "扉・廊下・階段の接続を守る。階や部屋を描写の都合で瞬間移動させない。",
    "hidden/locked/private/staffは公開・解錠・許可・発見を意味しない。人物・借金段階・施設の既存条件を優先する。",
    "資料で未設定の小物・人物・物語は自由に補う。未知の場所や部屋というだけでゲームを止めない。継続する変更はキャンペーンへ記録する。",
    "未設定の小部屋を補う時も、確定した階数・外形・主要な部屋のつながりと矛盾させない。改築や新発見による変化はその経緯を記録する。",
    "構造資料は新しい料金・回復・能力・イベント確率を付与しない。該当する数値正本と施設運用を読む。",
    "再訪ではキャンペーンに記録した破損・改装・封鎖・開放などの変化を併読し、初期構造へ巻き戻さない。",
]


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        raise ValueError("invalid place atlas: " + "; ".join(errors[:12]))
    return data


def _strings(value):
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def _floor_position(value):
    value = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if value in {"地上", "屋外", "地表", "外部", "1f", "1階", "地上1階"}:
        return 0
    # Campus floor names may include their building, e.g. 校舎1F/寮1F.
    # Parse a terminal basement marker first so 校舎B1F never becomes ground.
    underground = re.search(r"(?:b|地下)\s*([0-9]+)(?:f|階)?\Z", value)
    if underground:
        return -int(underground.group(1))
    above = re.search(r"([0-9]+)(?:f|階)\Z", value)
    return int(above.group(1)) - 1 if above else value


def validate(data) -> list[str]:
    errors = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("places"), list):
        return ["place atlas requires its schema and places list"]
    places = data["places"]
    if not places or len(places) > 500:
        errors.append("place atlas needs 1..500 existing stages")
    known, all_rooms, alias_owners = {}, set(), {}
    text_fields = ("name", "kind", "overview", "position")
    list_fields = ("aliases", "source_refs", "canon_constraints", "sightlines", "daily_life", "scene_uses", "limits")
    architecture_fields = ("footprint", "shell", "walls", "roof", "floors", "windows", "lighting", "water", "sanitation", "heating")
    for pos, place in enumerate(places):
        label = f"places[{pos}]"
        if not isinstance(place, dict):
            errors.append(label + " must be an object")
            continue
        pid = place.get("id")
        if not isinstance(pid, str) or not _ID.fullmatch(pid) or pid in known:
            errors.append(label + " has an invalid or duplicate id")
        else:
            known[pid] = place
        for key in text_fields:
            if not isinstance(place.get(key), str) or not place[key].strip():
                errors.append(f"{label}.{key} must be nonempty text")
        for key in list_fields:
            if not _strings(place.get(key)):
                errors.append(f"{label}.{key} must be a list of nonempty text")
        parent = place.get("parent_id")
        if parent is not None and (not isinstance(parent, str) or not _ID.fullmatch(parent)):
            errors.append(label + ".parent_id must be a place id or null")
        arch = place.get("architecture")
        if not isinstance(arch, dict):
            errors.append(label + ".architecture is required")
            arch = {}
        levels = arch.get("levels")
        if not _strings(levels) or not levels or len(levels) != len(set(levels)):
            errors.append(label + ".architecture.levels must list distinct floor names")
            levels = []
        for key in architecture_fields:
            if not isinstance(arch.get(key), str) or not arch[key].strip():
                errors.append(f"{label}.architecture.{key} must be nonempty text")
        rooms = place.get("rooms")
        edges = place.get("connections")
        if not isinstance(rooms, list) or not rooms or len(rooms) > 300:
            errors.append(label + ".rooms must contain 1..300 stage nodes")
            continue
        local, entries = {}, []
        for number, room in enumerate(rooms):
            where = f"{label}.rooms[{number}]"
            if not isinstance(room, dict):
                errors.append(where + " must be an object")
                continue
            rid = room.get("id")
            if not isinstance(rid, str) or not _ID.fullmatch(rid) or rid in local or rid in all_rooms:
                errors.append(where + " has an invalid or duplicate room id")
            else:
                local[rid] = room
                all_rooms.add(rid)
            for key in ("name", "floor", "position", "purpose", "description", "sensory"):
                if not isinstance(room.get(key), str) or not room[key].strip():
                    errors.append(where + "." + key + " must be nonempty text")
            if room.get("floor") not in levels:
                errors.append(where + ".floor is not listed in architecture.levels")
            if room.get("access") not in ACCESS:
                errors.append(where + ".access is unsupported")
            if not isinstance(room.get("entry"), bool):
                errors.append(where + ".entry must be boolean")
            elif room["entry"] is True and isinstance(rid, str):
                entries.append(rid)
        if not entries:
            errors.append(label + " needs an entrance node")
        if not isinstance(edges, list):
            errors.append(label + ".connections must be a list")
            continue
        adjacency = {rid: set() for rid in local}
        seen_edges = set()
        for number, edge in enumerate(edges):
            where = f"{label}.connections[{number}]"
            if not isinstance(edge, dict):
                errors.append(where + " must be an object")
                continue
            start, end = edge.get("from"), edge.get("to")
            if not isinstance(start, str) or not isinstance(end, str) or start not in local or end not in local or start == end:
                errors.append(where + " must join two distinct nodes of the same stage")
                continue
            if edge.get("access") not in ACCESS:
                errors.append(where + ".access is unsupported")
            for key in ("via", "description"):
                if not isinstance(edge.get(key), str) or not edge[key].strip():
                    errors.append(where + "." + key + " must be nonempty text")
            if (_floor_position(local[start].get("floor")) != _floor_position(local[end].get("floor"))
                    and not _VERTICAL.search(str(edge.get("via", "")) + " " + str(edge.get("description", "")))):
                errors.append(where + " crosses levels without an explicit stair, ladder, slope or other vertical route")
            edge_key = (*sorted((start, end)), edge.get("via"))
            if edge_key in seen_edges:
                errors.append(where + " repeats an existing physical connection")
            seen_edges.add(edge_key)
            adjacency[start].add(end)
            adjacency[end].add(start)
        reached, pending = set(), list(entries)
        while pending:
            rid = pending.pop()
            if rid in reached:
                continue
            reached.add(rid)
            pending.extend(adjacency.get(rid, set()) - reached)
        if set(local) - reached:
            errors.append(label + " contains nodes disconnected from every entrance: " + ",".join(sorted(set(local) - reached)))
    for pid, place in known.items():
        parent = place.get("parent_id")
        if parent is not None and (not isinstance(parent, str) or parent not in known):
            errors.append(pid + " references an unknown parent")
        chain, current = set(), pid
        while isinstance(current, str) and current in known:
            if current in chain:
                errors.append(pid + " belongs to a parent cycle")
                break
            chain.add(current)
            current = known[current].get("parent_id")
    return errors


def normalize(value):
    return _STRIP.sub("", unicodedata.normalize("NFKC", str(value)).casefold())


def request_from(args, save, scene=None):
    world = (save or {}).get("world_state", {})
    explicit = [v for v in (getattr(args, "location", None) or []) if isinstance(v, str) and v.strip()]
    saved_place = world.get("place_id")
    locations = explicit or ([world["location"]] if isinstance(world.get("location"), str) and world["location"].strip() else [])
    hearing = (save or {}).get("hearing_progress", {})
    opening = getattr(args, "opening_step", None)
    body_scripts = {"SCRIPT_OPENING_REBIRTH", "SCRIPT_OPENING_BONUS", "SCRIPT_OPENING_FIRE", "SCRIPT_OPENING_TUTORIAL"}
    step = hearing.get("current_step") if isinstance(hearing, dict) else None
    embodied_opening = (isinstance(step, int) and not isinstance(step, bool) and step >= 7
                        or isinstance(hearing, dict) and hearing.get("status") == "complete" or opening in body_scripts)
    if not locations and not explicit and (scene or getattr(args, "scene", None)) == "start" and embodied_opening:
        locations = ["INN_DRENCHED_RAT"]
    rooms = [v for v in (getattr(args, "room", None) or []) if isinstance(v, str) and v.strip()]
    if not explicit:
        rooms.extend(world[key] for key in ("room_id", "current_room_id", "sub_location")
                     if isinstance(world.get(key), str) and world[key].strip())
    depth = world.get("depth")
    run = world.get("dungeon_run")
    exterior_destination = any(re.search(r"入口|洞口|外部|外の|外へ|帰還|待機場", value) for value in explicit)
    interior = not exterior_destination and ((isinstance(depth, (int, float)) and not isinstance(depth, bool) and depth > 0)
                                             or isinstance(run, dict) and run.get("active") is True)
    return {"locations": list(dict.fromkeys(locations)), "rooms": list(dict.fromkeys(rooms)),
            "saved_place_id": saved_place if not explicit and isinstance(saved_place, str) else None,
            "source_place_id": saved_place if isinstance(saved_place, str) else None,
            "source_location": world.get("location") if isinstance(world.get("location"), str) else None,
            "dungeon_interior": bool(interior)}


def _matches(places, query):
    wanted = normalize(query)
    exact, embedded = [], []
    for place in places:
        aliases = [place["id"], place["name"], *place.get("aliases", [])]
        if any(normalize(alias) == wanted for alias in aliases):
            exact.append(place)
        elif any(len(normalize(alias)) >= 4 and normalize(alias) not in _GENERIC_ALIASES and normalize(alias) in wanted for alias in aliases):
            embedded.append(place)
    return exact or embedded


def project(data, request):
    places = data["places"]
    by_id = {place["id"]: place for place in places}
    selected, unknown, ambiguous, room_focus, stale = {}, [], [], [], []

    def inside(child, parent):
        current, seen = child, set()
        while current in by_id and current not in seen:
            if current == parent:
                return True
            seen.add(current)
            current = by_id[current].get("parent_id")
        return False

    def leaves(records):
        return [place for place in records if not any(other["id"] != place["id"] and inside(other["id"], place["id"]) for other in records)]

    def exact_name(place, query):
        return normalize(query) in {normalize(value) for value in [place["id"], place["name"], *place.get("aliases", [])]}

    children = {place.get("parent_id") for place in places if place.get("parent_id")}
    source_id = request.get("source_place_id") or request.get("saved_place_id")
    source_label = request.get("source_location")
    source_matches = leaves(_matches(places, source_label)) if source_label else []
    source_scope = source_matches[0]["id"] if len(source_matches) == 1 else None
    if source_id in by_id and (not source_label or any(exact_name(p, source_label) and inside(source_id, p["id"]) for p in source_matches)):
        source_scope = source_id

    def current_chain():
        result, current = [], source_scope
        while current in by_id:
            result.append(by_id[current])
            current = by_id[current].get("parent_id")
        return result

    for query in request.get("locations", []):
        wanted = normalize(query)
        scope_records = leaves([place for place in places if place["id"] in children and any(
            len(normalize(alias)) >= 3 and normalize(alias) not in _GENERIC_ALIASES and normalize(alias) in wanted
            for alias in [place["id"], place["name"], *place.get("aliases", [])])])
        scope = scope_records[0]["id"] if len(scope_records) == 1 else None
        found = _matches(places, query)
        room_context = []
        if scope:
            found = [place for place in found if inside(place["id"], scope)]
            found.extend(place for place in places if inside(place["id"], scope) and place not in found and any(
                len(normalize(alias)) >= 2 and wanted.endswith(normalize(alias)) for alias in [place["name"], *place.get("aliases", [])]))
            room_context = [by_id[scope]]
        elif wanted in _GENERIC_ALIASES and source_scope:
            parent_scope = next((p["id"] for p in current_chain() if p["id"] in children), source_scope)
            found = [place for place in found if inside(place["id"], parent_scope)]
            room_context = current_chain()
        # A room-like address resolves inside its named settlement/campus first;
        # its generic name must not pull in a similarly named foreign facility.
        inferred = []
        for context in room_context:
            inferred = [(context, room) for room in context["rooms"] if normalize(room["name"]) == wanted or
                        (scope and len(normalize(room["name"])) >= 2 and wanted.endswith(normalize(room["name"])))]
            if not inferred:
                labels = next((tokens for label, tokens in sorted(_ROOM_LABELS.items(), key=lambda item: -len(item[0]))
                               if wanted == label or scope and wanted.endswith(label)), ())
                inferred = [(context, room) for room in context["rooms"] if any(token in normalize(room["name"]) for token in labels)]
            if inferred:
                break
        if len(inferred) == 1:
            owner, room = inferred[0]
            found = [owner]
            room_focus.append({"place_id": owner["id"], "room_id": room["id"]})
        if not found:
            unknown.append(query)
        elif len(found) > 1 and all(normalize(query) in {normalize(v) for v in [p["name"], *p.get("aliases", [])]} for p in found):
            ambiguous.append(query)
        else:
            selected.update((place["id"], place) for place in found)
    saved_id = request.get("saved_place_id")
    if saved_id:
        exact_labels = {place["id"] for place in places if any(normalize(query) in
                        {normalize(alias) for alias in [place["id"], place["name"], *place.get("aliases", [])]}
                        for query in request.get("locations", []))}
        if saved_id in by_id and ((not selected and not request.get("locations")) or any(inside(saved_id, pid) or inside(pid, saved_id) for pid in exact_labels)):
            if not any(inside(pid, saved_id) for pid in selected):
                selected[saved_id] = by_id[saved_id]
        elif saved_id not in selected:
            stale.append(saved_id)
    # A saved street/room id can identify its stage even when the higher-level
    # location is only the town name. Generic room names are scoped to a stage.
    for query in request.get("rooms", []):
        exact_ids = [(place, room) for place in places for room in place["rooms"] if room["id"] == query
                     and (not selected or any(inside(place["id"], pid) for pid in selected))]
        scoped = exact_ids or [(place, room) for place in selected.values() for room in place["rooms"]
                              if normalize(room["name"]) == normalize(query)]
        if len(scoped) == 1:
            place, room = scoped[0]
            selected[place["id"]] = place
            room_focus.append({"place_id": place["id"], "room_id": room["id"]})
        elif len(scoped) > 1:
            ambiguous.append(query)
        else:
            unknown.append(query)
    # A facility includes its town as short parent context. Do not also send a
    # second, complete copy of that town when its name was in the same address.
    ancestors = set()
    for place in list(selected.values()):
        parent = place.get("parent_id")
        while parent in by_id:
            ancestors.add(parent)
            parent = by_id[parent].get("parent_id")
    for pid in ancestors:
        selected.pop(pid, None)
    exterior_only = []
    if request.get("dungeon_interior") is True:
        for pid, place in list(selected.items()):
            if pid == "HILLSIDE_CAVE_ENTRANCE":
                exterior_only.append({key: copy.deepcopy(place[key]) for key in
                                      ("id", "name", "overview", "position", "canon_constraints", "limits")})
                selected.pop(pid)
                room_focus = [row for row in room_focus if row["place_id"] != pid]
    parents = {}
    for place in selected.values():
        parent = place.get("parent_id")
        while parent in by_id:
            record = by_id[parent]
            parents[parent] = {key: copy.deepcopy(record[key]) for key in
                               ("id", "name", "kind", "parent_id", "overview", "position", "canon_constraints")}
            parents[parent]["navigation_nodes"] = [{key: room[key] for key in ("id", "name", "floor", "position")}
                                                    for room in record["rooms"]]
            parents[parent]["navigation_connections"] = [{key: copy.deepcopy(edge[key]) for key in ("from", "to", "via", "access")}
                                                          for edge in record["connections"]]
            parent = record.get("parent_id")
    return {"schema": VIEW_SCHEMA, "rules": RULES[:],
            "places": [copy.deepcopy(selected[pid]) for pid in sorted(selected)],
            "parent_context": [parents[pid] for pid in sorted(parents)],
            "exterior_context": exterior_only,
            "room_focus": [dict(items) for items in dict.fromkeys(tuple(row.items()) for row in room_focus)], "undefined_queries": list(dict.fromkeys(unknown)),
            "ambiguous_queries": list(dict.fromkeys(ambiguous)), "stale_position_fields": stale}


def _line(value):
    return str(value).replace("|", "\\|").replace("\n", " / ")


def _bullets(values):
    return ["- " + _line(value) for value in values] if values else ["- 追加指定なし。既存の世界・施設ルールを使う。"]


def render_place(place, heading="##"):
    """Human document and runtime share one exact, complete stage renderer."""
    text = [f"{heading} {place['name']} [{place['id']}]", "",
            f"- 種別: {KIND_LABELS.get(place['kind'], place['kind'])} / 上位舞台: {place.get('parent_id') or 'なし'}",
            "- 別名: " + " / ".join(place.get("aliases", [])), "",
            place["overview"], "", "**位置と周囲**", "", place["position"], "",
            "**既存正本から守る条件**", "", *_bullets(place["canon_constraints"]), "",
            "**建物・地形の構造**", "", "| 項目 | 確定内容 |", "|---|---|"]
    labels = {"levels": "階層", "footprint": "敷地・平面", "shell": "外観", "walls": "壁", "roof": "屋根", "floors": "床", "windows": "窓", "lighting": "灯り", "water": "水", "sanitation": "衛生・排水", "heating": "熱源・暖房"}
    for key, label in labels.items():
        value = place["architecture"][key]
        text.append(f"| {label} | {_line(' / '.join(value) if isinstance(value, list) else value)} |")
    text += ["", "**部屋・区画一覧**", "", "| ID | 部屋・区画 | 階 | 位置 | 用途 | 出入り |", "|---|---|---|---|---|---|"]
    for room in place["rooms"]:
        text.append("| " + " | ".join(_line(v) for v in (room["id"], room["name"], room["floor"], room["position"], room["purpose"], ACCESS_LABELS[room["access"]] + ("・入口" if room["entry"] else ""))) + " |")
    text += ["", "**区画ごとの描写**", ""]
    for room in place["rooms"]:
        text += [f"- **{room['name']} [{room['id']}]** {room['description']} 感覚: {room['sensory']}"]
    names = {room["id"]: room["name"] for room in place["rooms"]}
    text += ["", "**つながり（双方向。出入りの条件は別）**", "", "| 始点 | 終点 | 通り方・扉・階段 | 条件 | 位置の補足 |", "|---|---|---|---|---|"]
    for edge in place["connections"]:
        text.append("| " + " | ".join(_line(v) for v in (names[edge["from"]] + " [" + edge["from"] + "]", names[edge["to"]] + " [" + edge["to"] + "]", edge["via"], ACCESS_LABELS[edge["access"]], edge["description"])) + " |")
    for key, title in (("sightlines", "見通し・音の通り方"), ("daily_life", "時間帯と日常の使われ方"), ("scene_uses", "物語の舞台として使えること"), ("limits", "運用上の境界"), ("source_refs", "既存設定の参照先")):
        text += ["", f"**{title}**", "", *_bullets(place[key])]
    return "\n".join(text).rstrip() + "\n"


def render_view(view):
    text = ["# 今回の場所と構造 — GM参照用", "", *_bullets(view["rules"]), ""]
    for parent in view["parent_context"]:
        text += [f"## 周辺案内: {parent['name']} [{parent['id']}]", "", parent["overview"], "", parent["position"], "",
                 *_bullets(parent["canon_constraints"]), "", "| 街路・周辺区画 | 位置 |", "|---|---|"]
        text += [f"| {_line(node['name'])} [{node['id']}] | {_line(node['position'])} |" for node in parent["navigation_nodes"]]
        text += ["", "街路の接続（区画の説明・建物の内装は必要時だけ読む）:"]
        text += [f"- {edge['from']} ↔ {edge['to']}: {edge['via']}（{ACCESS_LABELS[edge['access']]}）" for edge in parent["navigation_connections"]]
        text += [""]
    for place in view["places"]:
        text += [render_place(place), ""]
    for place in view.get("exterior_context", []):
        text += [f"## 外部の位置だけ参照: {place['name']} [{place['id']}]", "", place["position"], "",
                 "現在は洞窟内部の探索。入口の部屋のつながりを各階の固定マップとして適用しない。内部は現在階のDungeon_Dataと確定済みの潜行状態を使う。", "",
                 *_bullets(place["canon_constraints"]), *_bullets(place["limits"]), ""]
    if view["room_focus"]:
        text += ["## 現在の部屋・行動対象", "", *_bullets([f"{row['place_id']} / {row['room_id']}" for row in view["room_focus"]]), ""]
    if view["undefined_queries"]:
        text += ["## 未設定の場所・部屋", "", *_bullets(view["undefined_queries"]), "", "未設定は創作の余地。該当しない既存の部屋へ勝手に置換せず、矛盾しない舞台を補う。", ""]
    if view["ambiguous_queries"]:
        text += ["## 同名の場所", "", *_bullets(view["ambiguous_queries"]), "", "現在地・所属町・既知の経緯で対象を絞る。資料の存在だけで別の店へ移動させない。", ""]
    if view.get("stale_position_fields"):
        text += ["## 古い位置IDの内部補完", "", *_bullets(view["stale_position_fields"]), "", "所在地ラベルと一致しない古いIDは今回の部屋として採用しない。移動が成立した候補で位置項目を揃える。", ""]
    return "\n".join(text).rstrip() + "\n"


def renderer(data):
    """Generate the complete browsable document from the sole JSON source."""
    text = ["# マチャダン 舞台資料集", "", "この資料は世界/舞台構造.jsonから生成した閲覧用。構造の修正はJSONへ反映して再生成する。",
            "通常プレイではこの全文を毎回読まず、現在地・移動先に対応する場所資料と親町の短い案内を読む。", "",
            *_bullets(RULES), "", "## 収録場所", "", "| 場所ID | 場所 | 上位舞台 |", "|---|---|---|"]
    for place in data["places"]:
        text.append(f"| {place['id']} | {_line(place['name'])} | {place.get('parent_id') or 'なし'} |")
    text += [""]
    for place in data["places"]:
        text += [render_place(place), ""]
    return "\n".join(text).rstrip() + "\n"
