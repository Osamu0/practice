"""Read-only regional lore, derived dates and conservative journey estimates.

The canonical JSON supplies narrative facts. This helper never advances time,
collects debt, moves actors, grants stock, or changes campaign state.
"""
from __future__ import annotations

import copy
import heapq
import json
from pathlib import Path
import re
import unicodedata

SCHEMA = "machadan-regional-lore-v1"
VIEW_SCHEMA = "machadan-regional-context-v1"
RELATIVE_PATH = "世界/地方世界設定.json"
BOOK_PATH = "世界/地方世界資料集.md"
SOURCE_LABEL = RELATIVE_PATH + "#REGIONAL_WORLD_VIEW"
TOPICS = ("calendar", "travel", "trade", "governance", "culture", "death")
SUMMARY_KEYS = ("role", "life", "culture", "trade", "governance")
WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_NORMALIZE = re.compile(r"[\s\u3000「」『』\"'【】\[\]（）()]+")
RULES = [
    "日付は絶対日Dayから導く表示。資料を読んでも移動・日付変更・料金支払は成立しない。",
    "数日間の旅をまとめる時も取立日を飛び越えず、既定の時刻・戦闘・報酬の途中処理を守る。旅行だけで宿代や回復を自動付与しない。",
    "新しい都市でも既存の品物価格・Tier・非売品・初昇格一回限り・リリスの契約を維持する。地方制度は個人の恋愛成立や入場許可を代替しない。",
    "未知の土地や暮らしは創作の余地。現在のキャンペーンの約束・破損・物流変化と地域の初期設定を併読する。",
]
LABELS = {
    "region":"ノワールと近郊の共通設定", "cities":"都市", "trade":"交易と商人ギルド", "calendar":"暦と季節", "death":"死と葬送",
    "name":"名称", "overview":"概要", "role":"役割", "character":"街の気風", "landscape":"地形と街並み", "districts":"区画",
    "governance":"統治と法", "economy":"産業と流通", "life":"暮らし", "adult_culture":"成人の恋愛・社交・歓楽文化",
    "culture":"文化", "festivals":"祭りと年中行事", "death_custom":"葬送の習慣", "scene_uses":"物語の入口", "limits":"守る範囲",
    "summary":"普段使う短い案内", "id":"照合ID", "title":"役職", "age":"年齢", "gender":"性別", "voice":"口調",
    "common":"共通事項", "rules":"原則", "members":"構成", "services":"窓口", "imports":"主な受入", "exports":"主な供給",
    "supply":"供給", "restrictions":"制限", "institutions":"制度", "daily_life":"日常", "relations":"街の関係", "customs":"習慣",
    "organization":"組織", "currency":"貨幣", "goods":"品物", "disputes":"争議", "routes":"街道と移動の目安",
    "absolute_day":"絶対日Day", "boundaries":"権限の境界", "branches":"各市の支部", "cadence":"頻度", "city_customs":"都市ごとの習慣",
    "city_id":"都市ID", "custom":"慣習", "day":"日", "days_per_month":"一月の日数", "days_per_year":"一年の日数",
    "details":"詳しい設定", "economic_invariants":"経済で守ること", "epoch":"暦の起点", "era":"紀年法",
    "everyday_supply":"日常の供給", "festival_policy":"祭りの運用", "local_arrangements":"近郊との暮らし", "flows":"商品の流れ",
    "focus":"主な役割", "from_city":"供給元", "funeral_practice":"葬送の手順", "guild_name":"ギルド名",
    "mechanical_invariants":"既存処理を守ること", "month":"月", "months":"該当月", "months_per_year":"一年の月数",
    "office":"役職", "place_id":"場所ID", "political_shape":"地域の統治形態", "public_scene":"公の催し",
    "recurring_events":"定期的な催し", "rescue_and_confirmation":"救助と死亡確認", "returns":"返送と帰還",
    "ruler_name":"統治者名", "schedule":"日程", "schema":"資料形式", "season":"季節", "seasons":"季節の区分",
    "shared_adult_culture":"成人文化の共通前提", "shortage_rules":"品不足の扱い", "source_refs":"既存資料の参照先",
    "structure":"組織の形", "technology_and_story_limits":"技術と物語の境界", "to_cities":"受入先", "weekday":"曜日",
    "weekdays":"曜日の順序", "year":"年", "route_places":"街道の地点名", "place_cities":"近隣の参照都市", "city_personas":"統治者の人物参照",
    "character_id":"人物ID",
    "geography":"地方の地理", "basis":"位置の基準", "city_positions":"各市の位置", "city":"都市", "direction":"方角",
    "coordinate":"模式座標", "gateways":"市外への出入口", "location":"所在", "room_id":"室・区画ID",
    "route_aliases":"街道地点の別名",
    "organization_guide":"組織の早見", "population":"住人と体格", "local_ties":"故郷と人物のつながり",
    "local_materials":"固有素材", "material_rules":"素材の扱い", "appearance":"見た目", "origin":"産地",
    "uses":"得意な用途", "cautions":"加工の注意", "regional_encounters":"この土地の遭遇素材",
    "pirates":"ギャル海賊団", "sea_monsters":"海の怪物", "habitat":"出る場所", "signs":"先に見える兆し",
    "scene":"場面の組立て", "approach":"接近の描写", "choices":"選べる対応", "encounter_rules":"遭遇の扱い",
}


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def normalize(value):
    return _NORMALIZE.sub("", unicodedata.normalize("NFKC", str(value)).casefold())


def date_for_day(day):
    if not _integer(day) or day < 1:
        raise ValueError("Day must be a positive integer")
    offset = day - 1
    year, year_day = divmod(offset, 360)
    month, date = divmod(year_day, 30)
    season = ("春", "夏", "秋", "冬")[month // 3]
    return {"absolute_day":day,"year":year+1,"month":month+1,"day_of_month":date+1,
            "weekday":WEEKDAYS[offset % 7],"season":season,
            "text":f"箱庭暦{year+1}年{month+1}月{date+1}日（{WEEKDAYS[offset % 7]}）・{season}"}


def validate(data, atlas=None):
    errors = []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return ["regional lore requires its canonical schema"]
    for key in ("region", "trade", "calendar", "death"):
        if not isinstance(data.get(key), dict) or not data[key]:
            errors.append(key+" must contain its complete regional chapter")
    calendar_data=data.get("calendar",{})
    if isinstance(calendar_data,dict):
        for key,value in (("days_per_year",360),("months_per_year",12),("days_per_month",30)):
            if not _integer(calendar_data.get(key)) or calendar_data[key]!=value:errors.append("calendar."+key+" must match the derived-date rule")
        if calendar_data.get("weekdays") != [day+"曜" for day in WEEKDAYS]:errors.append("calendar weekdays must match the continuous seven-day week")
        if calendar_data.get("epoch")!={"absolute_day":1,"year":1,"month":1,"day":1,"weekday":"月曜"}:errors.append("calendar epoch must match Day1")
        elif any(not _integer(calendar_data["epoch"][key]) for key in ("absolute_day","year","month","day")):errors.append("calendar epoch date values must be integers")
        seasons=calendar_data.get("seasons",[])
        if (not isinstance(seasons,list) or any(not isinstance(v,dict) for v in seasons)
                or [(v.get("name"),v.get("months")) for v in seasons]!=[("春",[1,2,3]),("夏",[4,5,6]),("秋",[7,8,9]),("冬",[10,11,12])]):errors.append("calendar seasons must match the derived month ranges")
    cities = data.get("cities")
    if not isinstance(cities,list) or not cities or len(cities)>100:
        return errors+["cities must contain 1..100 records"]
    ids = set()
    for city in cities:
        if not isinstance(city,dict):
            errors.append("city must be an object");continue
        cid = city.get("id")
        if not isinstance(cid,str) or not _ID.fullmatch(cid) or cid in ids:
            errors.append("city id must be unique and stable")
        else:ids.add(cid)
        for key in ("name","role"):
            if not isinstance(city.get(key),str) or not city[key].strip():errors.append(f"{cid}.{key} must be nonempty")
        summary=city.get("summary")
        if not isinstance(summary,dict) or set(summary)!=set(SUMMARY_KEYS):
            errors.append(f"{cid}.summary needs the five short summary fields")
        elif any(not isinstance(summary[k],str) or not summary[k].strip() or len(summary[k])>220 for k in SUMMARY_KEYS):
            errors.append(f"{cid}.summary fields must contain 1..220 characters without truncation")
        for key in ("character","landscape","districts","governance","economy","life","adult_culture","festivals","death_custom","scene_uses","limits"):
            if key not in city or not isinstance(city[key],(str,list,dict)) or not city[key]:errors.append(f"{cid}.{key} must contain the authored setting")
    places = {p.get("id") for p in atlas.get("places",[]) if isinstance(p,dict)} if isinstance(atlas,dict) else None
    if places is not None:
        for cid in ids-places:errors.append("city is absent from the structural atlas: "+cid)
    branches=data.get("trade",{}).get("branches",[]) if isinstance(data.get("trade"),dict) else []
    if not isinstance(branches,list):errors.append("trade.branches must be a list")
    else:
        stage_map={place["id"]:place for place in atlas.get("places",[]) if isinstance(place,dict) and isinstance(place.get("id"),str)} if isinstance(atlas,dict) else {}
        for branch in branches:
            if not isinstance(branch,dict):errors.append("trade branch must be an object");continue
            if branch.get("city_id") is not None and branch["city_id"] not in ids:errors.append("trade branch references an unknown city")
            pid=branch.get("place_id");rid=branch.get("room_id")
            if pid is not None and (not isinstance(pid,str) or not _ID.fullmatch(pid) or (places is not None and pid not in places)):
                errors.append("trade branch references an unknown facility")
            if rid is not None and (not isinstance(rid,str) or not _ID.fullmatch(rid) or not isinstance(pid,str)
                    or (isinstance(atlas,dict) and rid not in {room["id"] for room in stage_map.get(pid,{}).get("rooms",[])})):
                errors.append("trade branch room must belong to its declared facility")
            if "location" in branch and (not isinstance(branch["location"],str) or not branch["location"].strip()):errors.append("trade branch location must be nonempty text")
    references=data.get("place_cities",{})
    if not isinstance(references,dict):errors.append("place_cities must be a mapping")
    else:
        for place,cid in references.items():
            if cid not in ids or not isinstance(place,str) or (places is not None and place not in places):errors.append("invalid place-to-city reference: "+str(place))
    people=data.get("city_personas",{})
    if not isinstance(people,dict):errors.append("city_personas must be a mapping")
    else:
        for cid,values in people.items():
            values=[values] if isinstance(values,str) else values
            if cid not in ids or not isinstance(values,list) or not values or any(not isinstance(v,str) or not _ID.fullmatch(v) for v in values):errors.append("invalid city persona reference: "+str(cid))
    routes=data.get("routes",[])
    if not isinstance(routes,list):return errors+["routes must be a list"]
    route_ids=set()
    for route in routes:
        if not isinstance(route,dict):errors.append("route must be an object");continue
        rid=route.get("id")
        if not isinstance(rid,str) or not _ID.fullmatch(rid) or rid in route_ids:errors.append("route id must be unique and stable")
        else:route_ids.add(rid)
        for key in ("from","to"):
            value=route.get(key)
            if not isinstance(value,str) or not _ID.fullmatch(value) or (places is not None and value not in places):errors.append(f"{rid}.{key} references an unknown stage")
        if route.get("from")==route.get("to"):errors.append(str(rid)+" cannot join a place to itself")
        if not _integer(route.get("foot_minutes")) or route["foot_minutes"]<=0:errors.append(str(rid)+" needs positive foot_minutes")
        cart=route.get("cart_minutes")
        if cart is not None and (not _integer(cart) or cart<=0):errors.append(str(rid)+" cart_minutes must be positive or null")
        for key in ("description","gate"):
            if not isinstance(route.get(key),str) or not route[key].strip():errors.append(f"{rid}.{key} must explain the route")
        if not isinstance(route.get("limits"),list) or not all(isinstance(v,str) and v.strip() for v in route["limits"]):errors.append(str(rid)+" limits must be complete text")
    route_aliases=data.get("route_aliases",{})
    if not isinstance(route_aliases,dict):errors.append("route_aliases must be a mapping")
    else:
        endpoints={route.get(key) for route in routes if isinstance(route,dict) for key in ("from","to") if isinstance(route.get(key),str)}
        for alias,target in route_aliases.items():
            if not isinstance(alias,str) or not alias.strip() or not isinstance(target,str) or target not in endpoints:
                errors.append("route alias must resolve to an existing road endpoint")
    return errors


def load(path, atlas=None):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    errors=validate(data,atlas)
    if errors:raise ValueError("invalid regional lore: "+"; ".join(errors[:12]))
    return data


def request_from(args,save,place_view,atlas,data=None):
    day=(save or {}).get("world_state",{}).get("day",1)
    date_for_day(day)
    topics=list(dict.fromkeys(getattr(args,"world_topic",None) or []))
    if any(topic not in TOPICS for topic in topics):raise ValueError("unknown regional topic")
    by_id={p["id"]:p for p in atlas["places"]}
    city_ids={c["id"] for c in (data or {}).get("cities",[])}
    references=(data or {}).get("place_cities",{})
    found=set()
    for place in [*place_view.get("places",[]),*place_view.get("parent_context",[]),*place_view.get("exterior_context",[])]:
        pid=place["id"];seen=set()
        while pid and pid not in seen:
            seen.add(pid)
            if pid in city_ids:found.add(pid);break
            if pid in references:found.add(references[pid]);break
            pid=by_id.get(pid,{}).get("parent_id")
    reference_ids=[]
    for value in getattr(args,"world_city",None) or []:
        matches=[city["id"] for city in (data or {}).get("cities",[])
                 if normalize(value) in {normalize(city["id"]),normalize(city["name"])}]
        if len(matches)!=1:raise ValueError("reference city must name an existing regional city")
        reference_ids.extend(matches)
    found.update(reference_ids)
    request={"day":day,"city_ids":sorted(found),"topics":topics}
    if reference_ids:request["reference_city_ids"]=sorted(set(reference_ids))
    return request


def project(data,request):
    cities={city["id"]:city for city in data["cities"]}
    topics=request.get("topics",[])
    if not isinstance(topics,list) or any(topic not in TOPICS for topic in topics):raise ValueError("unsupported regional topic")
    selected=[]
    fields={"trade":("economy","local_materials","material_rules","local_ties"),
            "governance":("character","governance"),
            "culture":("adult_culture","life","festivals","population","local_ties"),
            "death":("death_custom",),
            "travel":("landscape","districts","scene_uses","regional_encounters"),
            "calendar":("festivals",)}
    for cid in request.get("city_ids",[]):
        if cid not in cities:raise ValueError("unknown selected regional city")
        city=cities[cid]
        row={key:copy.deepcopy(city[key]) for key in ("id","name","summary")}
        row["details"]={key:copy.deepcopy(city[key]) for topic in topics for key in fields[topic] if key in city}
        selected.append(row)
    chapters={topic:copy.deepcopy(data[topic]) for topic in topics if topic in {"calendar","trade","death"}}
    if "governance" in topics:chapters["region"]=copy.deepcopy(data["region"])
    if "travel" in topics:
        selected_ids=set(request.get("city_ids",[]))
        chapters["routes"]=[copy.deepcopy(route) for route in data.get("routes",[]) if not selected_ids or route["from"] in selected_ids or route["to"] in selected_ids]
        chapters["route_places"]=copy.deepcopy(data.get("route_places",{}))
    return {"schema":VIEW_SCHEMA,"date":date_for_day(request["day"]),"rules":RULES[:],"cities":selected,"chapters":chapters,
            "notice":"所属する既存都市を確定できない場所は、その土地の既存資料とキャンペーン設定で補う。" if not selected else "参照都市は周辺事情の案内。村の自治や既存の人物・地域文化を上書きしない。"}


def view_subjects(view):
    """Keep old announcements for the events whose complete rules were read."""
    identities=[]
    def visit(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key in {"name","place_id","city_id","festival"} and isinstance(child,str) and child.strip():identities.append(child)
                elif isinstance(child,(dict,list)):visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    # Do not expand all old calendar lore on an ordinary date-only turn.
    if "calendar" in view.get("chapters",{}):visit(view["chapters"]["calendar"])
    for city in view.get("cities",[]):
        if "festivals" in city.get("details",{}):visit(city["details"]["festivals"])
    return list(dict.fromkeys(identities))


def _line(value):
    return str(value).replace("|","\\|").replace("\n"," / ")


def _render(value,depth=0):
    if isinstance(value,str):return [value,""]
    if isinstance(value,list):
        lines=[]
        for item in value:
            if isinstance(item,(dict,list)):lines+=_render(item,depth+1)
            else:lines += ["- "+_line(item)]
        return lines+[""]
    if isinstance(value,dict):
        lines=[]
        for key,child in value.items():
            lines += ["**"+LABELS.get(key,key)+"**",""]+_render(child,depth+1)
        return lines
    return [str(value),""]


def _routes(routes,names):
    lines=["| 経路 | 徒歩 | 馬車 | 通り方 |","|---|---|---|---|"]
    for route in routes:
        def display(minutes):
            if minutes is None:return "不可・徒歩への乗換を検討"
            days,remainder=divmod(minutes,1440);hours,mins=divmod(remainder,60)
            return (f"{days}日" if days else "")+(f"{hours}時間" if hours else "")+(f"{mins}分" if mins else "") or "0分"
        lines.append("| "+" | ".join(_line(v) for v in (names.get(route["from"],route["from"])+" ↔ "+names.get(route["to"],route["to"]),display(route["foot_minutes"]),display(route.get("cart_minutes")),route["gate"]))+" |")
    for route in routes:
        lines += ["",f"**{names.get(route['from'],route['from'])} ↔ {names.get(route['to'],route['to'])}**", "",route["description"],*['- '+v for v in route["limits"]],""]
    return lines


def render_view(view):
    lines=["# 今回の地方・暮らし・日付 — GM参照用","",view["date"]["text"]+f" / Day {view['date']['absolute_day']}","",*['- '+v for v in view['rules']],""]
    for city in view["cities"]:
        lines += [f"## {city['name']} [{city['id']}]",""]
        for key in SUMMARY_KEYS:lines += ["- "+LABELS[key]+": "+city["summary"][key]]
        lines += [""]+_render(city["details"])
    for key,value in view["chapters"].items():
        if key=="route_places":continue
        lines += ["## "+LABELS.get(key,key),""]
        lines += _routes(value,view["chapters"].get("route_places",{})) if key=="routes" else _render(value)
    lines += [view["notice"],""]
    return "\n".join(lines).rstrip()+"\n"


def renderer(data):
    lines=["# マチャダン 地方世界資料集","","地方世界設定.jsonから生成した閲覧用。普段は日付と対象都市の短い案内だけを読み、必要なテーマで該当節を追加する。","",*['- '+v for v in RULES],""]
    lines += ["## ノワールと近郊の共通設定",""]+_render(data["region"])
    for city in data["cities"]:
        lines += [f"## {city['name']} [{city['id']}]",""]+_render({k:v for k,v in city.items() if k!="id"})
    for key in ("trade","calendar","death"):
        lines += ["## "+LABELS[key],""]+_render(data[key])
    lines += ["## 街道と移動の目安","", "所要時間は休憩を含む標準の経過時間。天候・迂回・事件による変化は根拠を記録する。","",*_routes(data.get("routes",[]),{**{c['id']:c['name'] for c in data['cities']},**data.get("route_places",{})})]
    return "\n".join(lines).rstrip()+"\n"


def travel_plan(data,from_id,to_id,mode="foot",save=None):
    if mode not in {"foot","cart"}:raise ValueError("travel mode must be foot or cart")
    routes=data.get("routes",[]);graph={}
    names={**{c["id"]:c["name"] for c in data["cities"]},**data.get("route_places",{})}
    for route in sorted(routes,key=lambda route:route["id"]):
        duration=route.get(mode+"_minutes")
        if duration is not None:
            for start,end in ((route["from"],route["to"]),(route["to"],route["from"])):
                graph.setdefault(start,[]).append((end,duration,route))
    pending=[(0,from_id,[])];costs={from_id:0};result=None
    while pending:
        cost,node,path=heapq.heappop(pending)
        if cost!=costs.get(node):continue
        if node==to_id:result=(cost,path);break
        for target,duration,route in graph.get(node,[]):
            next_cost=cost+duration
            if next_cost<costs.get(target,float("inf")):
                costs[target]=next_cost;heapq.heappush(pending,(next_cost,target,[*path,{"route_id":route["id"],"from":node,"to":target,"minutes":duration}]))
    base={"from":from_id,"to":to_id,"from_name":names.get(from_id,from_id),"to_name":names.get(to_id,to_id),"mode":mode,"read_only":True}
    if result is None:
        known_nodes={value for route in routes for value in (route["from"],route["to"])}
        status="undefined_route" if from_id not in known_nodes or to_id not in known_nodes else "no_route_for_mode"
        notice=("この固定経路では指定の交通手段を使えない。馬車を同じ道へ通した扱いにせず、徒歩への乗換や別の旅程を検討する。" if status=="no_route_for_mode" else "この場所への固定旅程は未設定。既存地理に矛盾しない旅程を補い、キャンペーンへ記録できる。")
        return {**base,"status":status,"notice":notice+"実際の移動と日付は別途確定する。"}
    minutes,path=result
    world=(save or {}).get("world_state",{});debt=(save or {}).get("debt_state",{})
    day=world.get("day");due=debt.get("next_collection_day");interrupt=None
    uncertain_phase=world.get("time_of_day") not in {"朝","昼","夕","夜"}
    if _integer(day) and day>=1 and _integer(due):
        phase={"朝":0,"昼":360,"夕":720,"夜":1080}.get(world.get("time_of_day"),1439)
        arrival=(day-1)*1440+phase+minutes
        if debt.get("collection_pending") is True or day<=due and (due-1)*1440<=arrival:interrupt=due
    return {**base,"status":"planned","minutes":minutes,"elapsed_days":minutes//1440,"remaining_hours":(minutes%1440)/60,"segments":path,
            "collection_interrupt_day":interrupt,"departure_time_uncertain":uncertain_phase,
            "notice":"標準の所要時間は通常の休憩を含む経過時間。計算だけでは移動・宿泊・回復・料金・取立ては成立せず、馬車の所持・無料運賃・荷物枠・安全も付与しない。馬車時間は用意や契約をした場合の目安。"+(" 出発時刻が未設定のため、取立ての注意は当日中で最も遅い出発も含めて表示する。" if uncertain_phase else "")+(f" Day {interrupt}の取立てを解決する前に先の日付へ進めない。" if interrupt is not None else "")}


def calendar(api,args):
    if getattr(args,"save",None):
        data,warnings=api._validated_status_save(Path(args.save).expanduser())
        day=data["world_state"]["day"]
    else:day,warnings=args.day,[]
    return {"ok":True,"read_only":True,"date":date_for_day(day),"warnings":warnings}


def travel(api,args):
    from place_atlas import load as load_atlas, RELATIVE_PATH as ATLAS_PATH
    atlas=load_atlas(api.ROOT/ATLAS_PATH)
    data=load(api.ROOT/RELATIVE_PATH)
    by_id={place["id"]:place for place in atlas["places"]}
    anchors={value for route in data.get("routes",[]) for value in (route["from"],route["to"])}
    def endpoint(value):
        hits=[place["id"] for place in atlas["places"] if any(normalize(value)==normalize(alias) for alias in [place["id"],place["name"],*place.get("aliases",[])])]
        hits.extend(target for alias,target in data.get("route_aliases",{}).items() if normalize(alias)==normalize(value))
        hits=list(dict.fromkeys(hits))
        if len(hits)>1:raise api.RuntimeProblem("同名の場所があります。正規場所IDで指定してください")
        actual=hits[0] if hits else value
        current=actual;seen=set()
        while current in by_id and current not in anchors and current not in seen:
            seen.add(current)
            current=by_id[current].get("parent_id")
        return actual,current if current in anchors else actual
    save,warnings=(api._validated_status_save(Path(args.save).expanduser()) if getattr(args,"save",None) else (None,[]))
    start,start_anchor=endpoint(args.from_place);end,end_anchor=endpoint(args.to_place)
    result=travel_plan(data,start_anchor,end_anchor,args.mode,save)
    return {"ok":True,**result,"requested_from":start,"requested_to":end,"from_anchor":start_anchor,"to_anchor":end_anchor,
            "local_access_not_included":True,"local_access_notice":"市外街道区間の目安。施設から門までの市内移動や乗換は、この計算だけで実行・省略した扱いにしない。","warnings":warnings}
