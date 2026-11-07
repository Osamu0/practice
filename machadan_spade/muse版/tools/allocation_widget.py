"""Draft-only ability allocation widgets and validated candidate construction.

Only ``resolve`` accepts the player's explicit chat confirmation.  Neither API
commits a save.  The immutable local request binds the editable values to the
source revision, actor and canonical budget; browser-provided rules are ignored.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

STATS = ("str", "def", "int", "spd", "tec", "chm")
SCHEMA = "machadan-allocation-widget-v1"
STATE_SCHEMA = "machadan-allocation-widget-state-v1"
REQUEST_SCHEMA = "machadan-allocation-request-v1"
MODES = {"initial", "fruit", "respec"}
FRUITS = {key.upper() + "の実": key for key in STATS}
FRUITS.update({"LPの実": "base_lp", "選べる能力の実": "choice"})
RESPEC_FEE = 100
RESPEC_MINUTES = 720
DAYPARTS = ("朝", "昼", "夕", "夜")
MAX_JSON_BYTES = 65536


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_json(api, path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise api.RuntimeProblem("allocation JSON is missing or exceeds 64 KiB")
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key: " + key)
                result[key] = value
            return result
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise api.RuntimeProblem("invalid allocation JSON: " + str(exc)) from exc


def _source(api, raw):
    supplied = Path(raw).expanduser()
    if supplied.is_symlink():
        raise api.RuntimeProblem("allocation source must not be a symbolic link")
    source = supplied.resolve()
    data = api.load_yaml(source)
    errors, warnings = api.validate_save_data(data)
    if errors:
        raise api.RuntimeProblem("invalid allocation save: " + "; ".join(errors))
    return source, data, warnings


def _output(api, source, raw):
    supplied = Path(raw).expanduser()
    if supplied.is_symlink():
        raise api.RuntimeProblem("allocation output must not be a symbolic link")
    output = supplied.resolve()
    if output == source or (output.exists() and source.exists() and output.samefile(source)):
        raise api.RuntimeProblem("allocation output must differ from the live save")
    root = api.ROOT.resolve()
    if output.is_relative_to(root.parent) and not output.is_relative_to(root / "state/runtime"):
        raise api.RuntimeProblem("generated allocation files inside the game belong under state/runtime")
    for directory in (root.parent.parent / "skills", root.parent.parent / "custom-skills"):
        if output.is_relative_to(directory.resolve()):
            raise api.RuntimeProblem("allocation output may not overwrite skill files")
    return output


def _request_path(api, request_id):
    api.safe_id(request_id)
    return api.RUNTIME_DIR / "allocation_requests" / (request_id + ".json")


def _actor(api, data, actor_id):
    actors = [data.get("player"), *data.get("party", [])]
    matches = [actor for actor in actors if isinstance(actor, dict) and actor.get("character_id") == actor_id]
    if len(matches) != 1:
        raise api.RuntimeProblem("allocation requires one known player/party character_id")
    return matches[0]


def _state(api, raw):
    if isinstance(raw, dict) and raw.get("schema") != STATE_SCHEMA and isinstance(raw.get("state"), dict):
        raw = raw["state"]
    if not isinstance(raw, dict) or raw.get("schema") != STATE_SCHEMA:
        raise api.RuntimeProblem("unsupported allocation widget state schema")
    if not _integer(raw.get("revision")) or raw["revision"] < 0:
        raise api.RuntimeProblem("allocation widget revision must be an integer >= 0")
    if not _integer(raw.get("source_revision")) or raw["source_revision"] < 0:
        raise api.RuntimeProblem("allocation source revision must be an integer >= 0")
    if not isinstance(raw.get("complete"), bool):
        raise api.RuntimeProblem("allocation complete must be a boolean")
    if not isinstance(raw.get("profile_hash"), str) or re.fullmatch(r"[0-9a-f]{64}", raw["profile_hash"]) is None:
        raise api.RuntimeProblem("allocation profile_hash must be a SHA256 digest")
    api.safe_id(str(raw.get("request_id") or ""))
    if len(_json(raw).encode("utf-8")) > MAX_JSON_BYTES:
        raise api.RuntimeProblem("allocation widget state exceeds 64 KiB")
    return raw


def _ledger(data):
    value = data.get("world_state", {}).get("allocation_state", {})
    return value.get("resolutions", []) if isinstance(value, dict) else []


def _permanent_stats(actor):
    return {key: actor["base_stats"][key] + actor["growth_bonus"][key] for key in STATS}


def _split_permanent(values):
    """Keep the initial33 bucket while redistributing every permanent point.

    The first fifteen planned points above ALL3 go into base_stats in STATS
    order. All remaining points go into growth_bonus. This deterministic
    internal split changes neither the visible totals nor the birth receipt.
    """
    base, remaining = {key: 3 for key in STATS}, 15
    for key in STATS:
        initial = min(remaining, values[key] - 3)
        base[key] += initial
        remaining -= initial
    if remaining:
        raise ValueError("full retraining needs at least the initial33 permanent points")
    return base, {key: values[key] - base[key] for key in STATS}


def _respec_time(api, data):
    world = data["world_state"]
    if world.get("time_of_day") not in DAYPARTS:
        raise api.RuntimeProblem("set the scene's 朝/昼/夕/夜 before starting half-day retraining")
    index = DAYPARTS.index(world["time_of_day"]) + 2
    new_day = world["day"] + index // 4
    debt = data.get("debt_state", {})
    pending, due = debt.get("collection_pending") is True, debt.get("next_collection_day")
    if pending and new_day != world["day"]:
        raise api.RuntimeProblem("resolve the pending debt collection before retraining into another day")
    if not pending and _integer(due) and new_day > due:
        raise api.RuntimeProblem("resolve the scheduled debt collection before retraining past its day")
    return {"day": new_day, "time_of_day": DAYPARTS[index % 4],
            "collection_pending": pending or _integer(due) and new_day >= due}


def _profile(api, data, mode, actor_id, stack_id=None, quantity=1):
    if mode not in MODES:
        raise api.RuntimeProblem("allocation mode must be initial, fruit or respec")
    actor = _actor(api, data, actor_id)
    fields = []
    item = None
    active = data.get("world_state", {}).get("expedition_state", {}).get("active") is True
    if data.get("runtime_state", {}).get("active_scene") == "combat":
        raise api.RuntimeProblem("ability allocation/fruit use requires a calm scene outside combat")
    if mode in {"initial", "respec"} and active:
        raise api.RuntimeProblem("initial allocation/retraining is unavailable during an expedition")
    if mode == "initial":
        onboarding = data.get("world_state", {}).get("onboarding", {})
        if actor is not data["player"] or data.get("hearing_progress", {}).get("status") != "complete":
            raise api.RuntimeProblem("initial allocation requires the player's completed hearing")
        if onboarding.get("body_received") is not True:
            raise api.RuntimeProblem("receive the initial body before opening allocation")
        if data.get("transaction", {}).get("last_committed_turn") != 0:
            raise api.RuntimeProblem("initial allocation is only available before adventure turns")
        if actor["lp"]["max"] > 0 and actor["lp"]["cur"] == 0:
            raise api.RuntimeProblem("initial allocation cannot resurrect an already formed body")
        holders = data.get("fire_state", {}).get("holders", [])
        held = False
        for reference in holders:
            resolved = api._expedition_member(data, reference)
            if ((resolved is not None and resolved.get("character_id") == actor_id)
                    or resolved is None and reference == actor.get("name")):
                held = True
        if onboarding.get("initial_base_stats") is not None or onboarding.get("allocation_complete") is True:
            raise api.RuntimeProblem("initial allocation is finished; use paid retraining")
        if not (onboarding.get("fire_granted") is True and onboarding.get("fire_explained") is True and held):
            raise api.RuntimeProblem("receive and explain Lilith's fire before initial allocation")
        if onboarding.get("allocation_rule") not in {None, "all3-plus15-v1"}:
            raise api.RuntimeProblem("this widget creates ALL3+15 characters only")
        values = actor["base_stats"]
        if not (all(values[key] >= 3 for key in STATS) and sum(values.values()) <= 33):
            raise api.RuntimeProblem("initial allocation cannot replace an existing exceptional build")
        if actor["base_lp"] not in {0, 20} or any(actor["growth_bonus"].values()):
            raise api.RuntimeProblem("initial allocation cannot replace permanent growth")
        for key in STATS:
            fields.append(_field(actor, key, max(3, values[key]), 3, 18, 1))
        budget = 15
        note = "初期の15点を配分。火・装備・成長は別枠です。チャットで『確定』するまで能力には反映されません。"
    elif mode == "respec":
        if (not all(actor["base_stats"][key] >= 3 for key in STATS)
                or sum(actor["base_stats"].values()) != 33):
            raise api.RuntimeProblem("retraining supports the normal ALL3+15 allocation; exceptional/cursed builds need a separate ruling")
        if data["player"].get("gold", 0) < RESPEC_FEE:
            raise api.RuntimeProblem("retraining requires 100G")
        _respec_time(api, data)
        permanent = _permanent_stats(actor)
        if any(permanent[key] < 3 for key in STATS) or any(actor["growth_bonus"][key] < 0 for key in STATS):
            raise api.RuntimeProblem("exceptional permanent reductions need a separate ruling before retraining")
        budget = sum(permanent.values()) - 18
        for key in STATS:
            fields.append(_field(actor, key, permanent[key], 3, 3 + budget, 1))
        note = "実や成長で増えた分も含め、6能力の恒久ポイントをすべて再配分。100G・半日。各能力3以上、合計はそのまま。LPの実の増加分は残り、LP/MPは回復しません。"
    else:
        if not _integer(quantity) or not 1 <= quantity <= 10:
            raise api.RuntimeProblem("fruit quantity must be an integer in 1..10")
        stacks = data.get("inventory", {}).get("carried_stacks", [])
        matches = [stack for stack in stacks if isinstance(stack, dict) and stack.get("stack_id") == stack_id]
        if len(matches) != 1:
            raise api.RuntimeProblem("select one carried fruit stack_id; warehouse/instance items must be moved to a carried stack first")
        stack = matches[0]
        definitions = [definition for definition in data.get("item_definitions", [])
                       if definition.get("item_def_id") == stack.get("item_def_id")]
        name = stack.get("name")
        if name not in FRUITS or len(definitions) != 1 or definitions[0].get("name") != name:
            raise api.RuntimeProblem("unknown or untyped ability fruit")
        if quantity > stack["count"] - stack["reserved_quantity"]:
            raise api.RuntimeProblem("fruit quantity exceeds unreserved carried stock")
        if actor["base_lp"] < 20 or any(actor["base_stats"][key] < 3 for key in STATS):
            raise api.RuntimeProblem("finish a normal character body before using ability fruit")
        targets = (*STATS, "base_lp") if FRUITS[name] == "choice" else (FRUITS[name],)
        for key in targets:
            current = actor["base_lp"] if key == "base_lp" else actor["base_stats"][key] + actor["growth_bonus"][key]
            step = 3 if key == "base_lp" else 1
            fields.append(_field(actor, key, current, current, current + quantity * step, step))
        item = {"stack_id": stack_id, "item_def_id": stack["item_def_id"], "name": name, "quantity": quantity}
        budget = quantity
        note = "選んだ実を使う配分案です。チャットで『確定』するまで実は減りません。"
    from encumbrance import preview, EncumbranceError
    recalc_weight = (mode != "fruit" or FRUITS[item["name"]] in {"str", "spd", "choice"}
                     or "encumbrance" in actor)
    try:
        encumbrance = preview(data, actor_id, require_weights=recalc_weight)
    except EncumbranceError as exc:
        raise api.RuntimeProblem(str(exc)) from exc
    encumbrance["previous_applied_penalty"] = actor.get("encumbrance", {}).get("applied_penalty", 0)
    return {"mode": mode, "actor_id": actor_id, "actor_name": str(actor.get("name", ""))[:200],
            "fields": fields, "budget": {"total": budget, "unit_label": "個" if mode == "fruit" else "点", "require_all": True},
            "initial_values": {field["key"]: field["current"] for field in fields}, "note": note,
            "item": item, "respec": {"fee_gold": RESPEC_FEE, "duration_minutes": RESPEC_MINUTES,
                "rule": "permanent-all3-v1", "permanent_total": sum(permanent.values()),
                "initial_points": 15, "growth_points": sum(permanent.values()) - 33} if mode == "respec" else None,
            "resource_profile": {"lp": copy.deepcopy(actor["lp"]), "mp": copy.deepcopy(actor["mp"]),
                "base_lp": 20 if mode == "initial" else actor["base_lp"],
                "lp_fixed_bonus": sum(actor[key] for key in ("job_lp_bonus", "fire_lp_bonus", "temporary_lp_bonus")),
                "permanent_def": actor["base_stats"]["def"] + actor["growth_bonus"]["def"],
                "permanent_int": actor["base_stats"]["int"] + actor["growth_bonus"]["int"],
                "int_fixed_bonus": sum(actor[group]["int"] for group in ("equipment_bonus", "fire_bonus", "temporary_modifiers")),
                "stat_lp_tracked": mode in {"initial", "respec"} or "stat_lp_bonus" in actor,
                "initial_full": mode == "initial"},
            "encumbrance": encumbrance, "encumbrance_recalculate": recalc_weight}


def _field(actor, key, current, minimum, maximum, step):
    bonus = (sum(actor[group][key] for group in ("growth_bonus", "equipment_bonus", "fire_bonus", "temporary_modifiers"))
             if key in STATS else sum(actor[group] for group in ("job_lp_bonus", "fire_lp_bonus", "temporary_lp_bonus")) + actor.get("stat_lp_bonus", 0))
    return {"key": key, "label": "Base LP" if key == "base_lp" else key.upper(), "short": "LP" if key == "base_lp" else key.upper(),
            "current": current, "minimum": minimum, "maximum": maximum, "step": step, "cost": 1, "effective_bonus": bonus}


def _load_request(api, request_id):
    envelope = _read_json(api, _request_path(api, request_id))
    if not isinstance(envelope, dict) or envelope.get("schema") != REQUEST_SCHEMA or envelope.get("request_id") != request_id:
        raise api.RuntimeProblem("allocation request envelope mismatch")
    if (not isinstance(envelope.get("profile"), dict) or
            envelope.get("profile_hash") != _hash(envelope.get("profile"))):
        raise api.RuntimeProblem("allocation request profile was changed")
    if (not _integer(envelope.get("source_revision")) or envelope["source_revision"] < 0
            or not isinstance(envelope.get("campaign_id"), str)
            or not isinstance(envelope.get("source_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", envelope["source_sha256"]) is None):
        raise api.RuntimeProblem("allocation request source identity is malformed")
    return envelope


def _verify_state_identity(api, envelope, state):
    for key in ("request_id", "source_revision", "profile_hash"):
        if state.get(key) != envelope.get(key):
            raise api.RuntimeProblem("allocation widget " + key + " does not match its request")
    for key in ("mode", "actor_id"):
        if state.get(key) != envelope["profile"].get(key):
            raise api.RuntimeProblem("allocation widget " + key + " was changed")


def _verify(api, data, envelope, state=None):
    if envelope.get("source_sha256") != _hash(data) or envelope.get("source_revision") != data.get("save_revision") or envelope.get("campaign_id") != data.get("campaign_id"):
        raise api.RuntimeProblem("allocation draft is stale; reopen against the current save")
    profile = envelope["profile"]
    item = profile.get("item") or {}
    recomputed = _profile(api, data, profile.get("mode"), profile.get("actor_id"), item.get("stack_id"), item.get("quantity", 1))
    if profile != recomputed:
        raise api.RuntimeProblem("allocation request no longer matches the actor/rules/items")
    if any(receipt.get("request_id") == envelope["request_id"] for receipt in _ledger(data)):
        raise api.RuntimeProblem("allocation request has already been consumed")
    if state is not None:
        _verify_state_identity(api, envelope, state)
    return profile


def _values(api, profile, values, require_all=True):
    fields = profile["fields"]
    if not isinstance(values, dict) or set(values) != {field["key"] for field in fields}:
        raise api.RuntimeProblem("allocation values must contain exactly the offered fields")
    used = 0
    for field in fields:
        value = values[field["key"]]
        if (not _integer(value) or value < field["minimum"] or value > field["maximum"]
                or (value - field["minimum"]) % field["step"]):
            raise api.RuntimeProblem("allocation value violates minimum/maximum/step: " + field["key"])
        used += (value - field["minimum"]) // field["step"] * field["cost"]
    if used > profile["budget"]["total"] or require_all and used != profile["budget"]["total"]:
        raise api.RuntimeProblem("allocate exactly the offered budget")
    return used


def _write_exact(api, path, text):
    with api.file_locks([api.save_lock_path(path)]):
        if path.is_symlink():
            raise api.RuntimeProblem("allocation files must not be symbolic links")
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise api.RuntimeProblem("refusing to overwrite a different allocation file: " + str(path))
        if not path.exists():
            api.atomic_write(path, text)


def _embedded_json(payload):
    return (_json(payload).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _write_widget_files(api, output, state_path, template, payload, envelope, data, reopening):
    """Refresh only this request's generated drafts, never unrelated content."""
    rendered = template.replace("__ALLOCATION_PAYLOAD_JSON__", _embedded_json(payload))
    state_text = _json(payload["initial_state"]) + "\n"
    with api.file_locks([api.save_lock_path(output), api.save_lock_path(state_path)]):
        for path in (output, state_path):
            if path.is_symlink():
                raise api.RuntimeProblem("allocation draft files must not be symbolic links")
        prior_states = []
        if output.exists() and output.read_text(encoding="utf-8") != rendered:
            if not reopening:
                raise api.RuntimeProblem("refusing to overwrite a different allocation widget")
            prefix, suffix = template.split("__ALLOCATION_PAYLOAD_JSON__")
            old_html = output.read_text(encoding="utf-8")
            if not old_html.startswith(prefix) or not old_html.endswith(suffix):
                raise api.RuntimeProblem("existing HTML is not this allocation template")
            try:
                prior_payload = json.loads(old_html[len(prefix):-len(suffix)] if suffix else old_html[len(prefix):])
            except (ValueError, TypeError) as exc:
                raise api.RuntimeProblem("existing allocation HTML has an invalid payload") from exc
            immutable_before = {key: value for key, value in prior_payload.items() if key != "initial_state"} if isinstance(prior_payload, dict) else None
            immutable_after = {key: value for key, value in payload.items() if key != "initial_state"}
            if immutable_before != immutable_after:
                raise api.RuntimeProblem("existing allocation HTML belongs to a different request/profile")
            prior_states.append(_state(api, prior_payload.get("initial_state")))
        if state_path.exists() and state_path.read_text(encoding="utf-8") != state_text:
            if not reopening:
                raise api.RuntimeProblem("refusing to overwrite a different allocation draft state")
            prior_states.append(_state(api, _read_json(api, state_path)))
        for previous in prior_states:
            _verify(api, data, envelope, previous)
            _values(api, envelope["profile"], previous.get("values"), require_all=False)
            incoming = payload["initial_state"]
            if (previous["revision"] > incoming["revision"] or previous["revision"] == incoming["revision"]
                    and previous["values"] != incoming["values"]):
                raise api.RuntimeProblem("reopened allocation draft must not replace a newer/different revision")
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            api.atomic_write(output, rendered)
        if not state_path.exists() or state_path.read_text(encoding="utf-8") != state_text:
            api.atomic_write(state_path, state_text)


def render(api, args):
    source, data, warnings = _source(api, args.save)
    output = _output(api, source, args.output)
    if output.suffix.lower() != ".html":
        raise api.RuntimeProblem("allocation-widget --output must be an HTML path")
    actor_id = getattr(args, "actor_id", None) or data["player"]["character_id"]
    request_id = getattr(args, "request_id", None)
    reopening = bool(request_id)
    if request_id:
        envelope = _load_request(api, request_id)
        profile = _verify(api, data, envelope)
        if not getattr(args, "actor_id", None):
            actor_id = profile["actor_id"]
        if profile["mode"] != args.mode or profile["actor_id"] != actor_id:
            raise api.RuntimeProblem("reopened allocation request mode/actor mismatch")
    else:
        profile = _profile(api, data, args.mode, actor_id, getattr(args, "stack_id", None), getattr(args, "quantity", 1))
        request_id = "alloc-" + uuid.uuid4().hex
        envelope = {"schema": REQUEST_SCHEMA, "request_id": request_id, "campaign_id": data["campaign_id"],
                    "source_revision": data["save_revision"], "source_sha256": _hash(data),
                    "profile_hash": _hash(profile), "profile": profile}
    state = {"schema": STATE_SCHEMA, "request_id": request_id, "mode": profile["mode"], "actor_id": profile["actor_id"],
             "source_revision": envelope["source_revision"], "profile_hash": envelope["profile_hash"],
             "values": profile["initial_values"], "revision": 0, "complete": False}
    state_path = _output(api, source, output.with_suffix(".state.json"))
    draft = getattr(args, "widget_state", None) or (str(state_path) if reopening and state_path.is_file() else None)
    if draft:
        state = _state(api, _read_json(api, draft))
        _verify(api, data, envelope, state)
        _values(api, profile, state.get("values"), require_all=False)
    state["complete"] = _values(api, profile, state["values"], require_all=False) == profile["budget"]["total"]
    payload = {**copy.deepcopy(profile), "schema": SCHEMA, "request_id": request_id,
               "source_revision": envelope["source_revision"], "profile_hash": envelope["profile_hash"], "initial_state": state}
    # Fruit/retraining values already include permanent growth.
    if profile["mode"] in {"fruit", "respec"}:
        for field in payload["fields"]:
            if field["key"] in STATS:
                field["effective_bonus"] -= _actor(api, data, actor_id)["growth_bonus"][field["key"]]
    # Presentation only: draft values and their signed request remain base /
    # permanent points. Show effective totals without spending fire twice.
    actor = _actor(api, data, actor_id)
    payload["display_bonus_breakdown"] = {
        key: {"fire": actor["fire_bonus"][key], "equipment": actor["equipment_bonus"][key],
              "temporary": actor["temporary_modifiers"][key],
              "growth": actor["growth_bonus"][key] if profile["mode"] == "initial" else 0}
        for key in STATS}
    template = (api.HERE / "allocation_widget_template.html").read_text(encoding="utf-8")
    if template.count("__ALLOCATION_PAYLOAD_JSON__") != 1:
        raise api.RuntimeProblem("allocation widget template payload slot is missing/duplicated")
    _write_widget_files(api, output, state_path, template, payload, envelope, data, reopening)
    _write_exact(api, _request_path(api, request_id), _json(envelope) + "\n")
    return {"ok": True, "output": str(output), "state_path": str(state_path), "request_path": str(_request_path(api, request_id)),
            "request_id": request_id, "mode": profile["mode"], "actor_id": actor_id, "draft_only": True,
            "warnings": warnings, "notice": "配分は下書きです。プレイヤーがチャットで『確定』と答えた後だけallocation-resolveを実行してください"}


def _recalculate(actor, track=False):
    actor["effective_stats"] = {key: sum(actor[group][key] for group in
        ("base_stats", "growth_bonus", "equipment_bonus", "fire_bonus", "temporary_modifiers")) for key in STATS}
    actor["stats"] = copy.deepcopy(actor["effective_stats"])
    from resource_math import recalculate
    recalculate(actor, track=track)


def _build(api, data, envelope, values, tx):
    profile = _verify(api, data, envelope)
    _values(api, profile, values)
    result = copy.deepcopy(data)
    actor = _actor(api, result, profile["actor_id"])
    before = {key: copy.deepcopy(actor[key]) for key in ("base_stats", "growth_bonus", "base_lp", "lp", "mp")}
    mode = profile["mode"]
    if mode == "respec" and values == _permanent_stats(actor):
        raise api.RuntimeProblem("unchanged allocation does not require paid retraining")
    if mode == "respec":
        actor["base_stats"], actor["growth_bonus"] = _split_permanent(values)
    elif mode == "initial":
        actor["base_stats"] = copy.deepcopy(values)
        actor["base_lp"] = 20
        result["world_state"].setdefault("onboarding", {}).update(
            allocation_rule="all3-plus15-v1", body_received=True, allocation_complete=True,
            initial_base_stats=copy.deepcopy(values))
    else:
        for key, value in values.items():
            delta = value - next(field["minimum"] for field in profile["fields"] if field["key"] == key)
            if key == "base_lp":
                actor["base_lp"] += delta
            else:
                actor["growth_bonus"][key] += delta
        item = profile["item"]
        stacks = result["inventory"]["carried_stacks"]
        stack = next(stack for stack in stacks if stack["stack_id"] == item["stack_id"])
        stack["count"] -= item["quantity"]
        if not stack["count"]:
            stacks.remove(stack)
        result["inventory"]["bag"]["used_slots"] = api._inventory_used_slots(result)
    if mode == "respec":
        result["player"]["gold"] -= RESPEC_FEE
        world = result["world_state"]
        advanced = _respec_time(api, data)
        world.update({key: advanced[key] for key in ("day", "time_of_day")})
        result["debt_state"]["collection_pending"] = advanced["collection_pending"]
    if profile["encumbrance_recalculate"]:
        from encumbrance import recalculate, EncumbranceError
        try:
            recalculate(result, actor["character_id"])
        except EncumbranceError as exc:
            raise api.RuntimeProblem(str(exc)) from exc
    _recalculate(actor, track=mode in {"initial", "respec"} or "stat_lp_bonus" in actor)
    # Creation starts with full resources. Later fruits/retraining only change
    # capacities and never recover spent LP/MP; a formed LP0 body is rejected.
    if mode == "initial":
        actor["lp"]["cur"], actor["mp"]["cur"] = actor["lp"]["max"], actor["mp"]["max"]
    after = {key: copy.deepcopy(actor[key]) for key in before}
    receipt = {"request_id": envelope["request_id"], "transaction_id": tx, "mode": mode,
               "actor_id": actor["character_id"], "source_revision": data["save_revision"],
               "source_sha256": envelope["source_sha256"], "profile_hash": envelope["profile_hash"],
               "values": copy.deepcopy(values), "before": before, "after": after,
               "consumed": copy.deepcopy(profile["item"]),
               "fee_gold": RESPEC_FEE if mode == "respec" else 0,
               "duration_minutes": RESPEC_MINUTES if mode == "respec" else 0,
               "time_before": {key: data["world_state"][key] for key in ("day", "time_of_day")} if mode == "respec" else None,
               "time_after": {key: result["world_state"][key] for key in ("day", "time_of_day")} if mode == "respec" else None,
               "respec_rule": profile["respec"]["rule"] if mode == "respec" else None,
               "permanent_points_before": sum(_permanent_stats(_actor(api, data, profile["actor_id"])).values()),
               "permanent_points_after": sum(_permanent_stats(actor).values())}
    result["world_state"].setdefault("allocation_state", {"version": 1, "resolutions": []})["resolutions"].append(receipt)
    return result, receipt


def resolve(api, args):
    if not isinstance(getattr(args, "confirmation", None), str) or args.confirmation.strip() != "確定":
        raise api.RuntimeProblem("allocation requires the player's explicit chat confirmation: 確定")
    source, data, warnings = _source(api, args.save)
    output = _output(api, source, args.output)
    tx = api.safe_id(args.transaction_id)
    state = _state(api, _read_json(api, args.widget_state))
    envelope = _load_request(api, state["request_id"])
    _verify_state_identity(api, envelope, state)
    if state.get("complete") is not True:
        raise api.RuntimeProblem("allocation draft is not complete")
    if data["transaction"].get("last_transaction_id") == tx and output.is_file():
        receipts = [entry for entry in _ledger(data) if entry.get("request_id") == state["request_id"] and entry.get("transaction_id") == tx]
        candidate = api.load_yaml(output)
        digest = api.sha256_bytes(api.dump_yaml(candidate).encode("utf-8"))
        if len(receipts) == 1 and receipts[0].get("values") == state.get("values") and digest == data["transaction"].get("last_candidate_hash"):
            return {"ok": True, "idempotent": True, "output": str(output), "request_id": state["request_id"], "transaction_id": tx}
        raise api.RuntimeProblem("committed allocation retry differs from its receipt/candidate")
    _verify(api, data, envelope, state)
    result, receipt = _build(api, data, envelope, state.get("values"), tx)
    errors, final_warnings = api.validate_save_data(result)
    if errors:
        raise api.RuntimeProblem("allocation produced an invalid candidate: " + "; ".join(errors))
    text = api.dump_yaml(result)
    identical = output.is_file() and output.read_text(encoding="utf-8") == text
    _write_exact(api, output, text)
    return {"ok": True, "output": str(output), "idempotent": identical, "request_id": state["request_id"],
            "transaction_id": tx, "draft_only": True, "receipt": receipt, "warnings": [*warnings, *final_warnings],
            "notice": "確定回答に基づく候補を作成しました。同じtransaction IDの通常commit成功後に結果を表示してください"}


def validate_state(data, errors):
    """Optional save metadata only; old saves and non-fruit growth stay legal."""
    world = data.get("world_state")
    state = world.get("allocation_state") if isinstance(world, dict) else None
    if state is None:
        return
    if (not isinstance(state, dict) or state.get("version") != 1 or isinstance(state.get("version"), bool)
            or not isinstance(state.get("resolutions"), list)):
        errors.append("allocation_state requires version1/resolutions list")
        return
    seen_requests, seen_transactions = set(), set()
    for entry in state["resolutions"]:
        if not isinstance(entry, dict):
            errors.append("allocation receipt must be a mapping")
            continue
        for key, seen in (("request_id", seen_requests), ("transaction_id", seen_transactions)):
            value = entry.get(key)
            if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is None or value in seen:
                errors.append("allocation receipt requires a unique safe " + key)
            if isinstance(value, str):
                seen.add(value)
        if entry.get("mode") not in MODES or not isinstance(entry.get("actor_id"), str):
            errors.append("allocation receipt mode/actor_id is invalid")
        if not isinstance(entry.get("values"), dict):
            errors.append("allocation receipt values must be a mapping")
        for key in ("source_sha256", "profile_hash"):
            value = entry.get(key)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                errors.append("allocation receipt " + key + " must be a SHA256 digest")
        if not all(isinstance(entry.get(key), dict) for key in ("before", "after")):
            errors.append("allocation receipt requires before/after mappings")
        if not all(_integer(entry.get(key)) and entry[key] >= 0 for key in ("fee_gold", "duration_minutes")):
            errors.append("allocation receipt fee/duration must be nonnegative integers")
        if entry.get("mode") == "fruit":
            consumed = entry.get("consumed")
            if (not isinstance(consumed, dict) or consumed.get("name") not in FRUITS
                    or not _integer(consumed.get("quantity")) or not 1 <= consumed["quantity"] <= 10
                    or not all(isinstance(consumed.get(key), str) and consumed[key] for key in ("stack_id", "item_def_id"))):
                errors.append("fruit allocation receipt requires a typed carried-stack consumption")
        elif entry.get("consumed") is not None:
            errors.append("non-fruit allocation receipt cannot consume an item")
        if not _integer(entry.get("source_revision")) or entry["source_revision"] < 0:
            errors.append("allocation receipt source_revision must be >=0")


def _redistributions(old, new):
    """Find equal-total moves of completed ordinary permanent stat points."""
    changed = set()
    old_actors = {actor["character_id"]: actor for actor in [old.get("player"), *old.get("party", [])] if isinstance(actor, dict)}
    new_actors = {actor["character_id"]: actor for actor in [new.get("player"), *new.get("party", [])] if isinstance(actor, dict)}
    onboarding = old.get("world_state", {}).get("onboarding", {})
    for actor_id in old_actors.keys() & new_actors.keys():
        left, right = old_actors[actor_id], new_actors[actor_id]
        was_complete = (left.get("build_complete") is True or old.get("transaction", {}).get("last_committed_turn", 0) > 0
                        or actor_id != old.get("player", {}).get("character_id")
                        or onboarding.get("allocation_complete") is True or onboarding.get("initial_base_stats") is not None)
        stats = (_permanent_stats(left), _permanent_stats(right))
        normal = all(all(_integer(values[key]) and values[key] >= 3 for key in STATS)
                     and sum(values.values()) >= 33 for values in stats)
        if was_complete and normal and sum(stats[0].values()) == sum(stats[1].values()) and stats[0] != stats[1]:
            changed.add(actor_id)
    return changed


def validate_transition(api, old, new, transaction_id):
    """Append-only receipts; replay each new receipt from its immutable request.

    Checks the affected mechanics, allowing ordinary story/log changes alongside
    a confirmed allocation. It deliberately does not classify all event growth
    as fruit consumption.
    """
    errors = []
    before, after = _ledger(old), _ledger(new)
    if not isinstance(before, list) or not isinstance(after, list) or after[:len(before)] != before:
        return ["allocation_state.resolutions is append-only"]
    added = after[len(before):]
    redistributed = _redistributions(old, new)
    if not added:
        # An equal-total redistribution of a completed normal creation is
        # retraining, not an event growth grant. Keep that narrow distinction:
        # other story growth and exceptional/cursed transformations stay legal.
        if redistributed:
            errors.append("redistributing completed permanent stat points requires a confirmed allocation receipt")
        return errors
    if len(added) != 1:
        return ["one confirmed allocation request is allowed per commit"]
    receipt = added[0]
    try:
        if not isinstance(receipt, dict) or receipt.get("transaction_id") != transaction_id:
            raise api.RuntimeProblem("allocation receipt must use the current transaction_id")
        allowed_redistribution = {receipt.get("actor_id")} if receipt.get("mode") in {"initial", "respec"} else set()
        if redistributed - allowed_redistribution:
            errors.append("another actor's permanent points cannot be redistributed by this allocation receipt")
        envelope = _load_request(api, str(receipt.get("request_id") or ""))
        expected, expected_receipt = _build(api, old, envelope, receipt.get("values"), transaction_id)
        if receipt != expected_receipt:
            errors.append("allocation receipt differs from its canonical resolution")
        actor_id = envelope["profile"]["actor_id"]
        if _actor(api, new, actor_id) != _actor(api, expected, actor_id):
            errors.append("allocated actor differs from its confirmed resolution")
        mode = envelope["profile"]["mode"]
        if mode == "fruit" and new.get("inventory") != expected.get("inventory"):
            errors.append("fruit consumption does not match its confirmed carried-stack delta")
        if mode == "initial" and new["world_state"].get("onboarding") != expected["world_state"].get("onboarding"):
            errors.append("initial allocation flags differ from their confirmed resolution")
        if mode == "respec":
            if new["player"].get("gold") != expected["player"].get("gold"):
                errors.append("retraining must charge exactly 100G")
            if any(new["world_state"].get(key) != expected["world_state"].get(key) for key in ("day", "time_of_day")):
                errors.append("retraining must advance exactly half a day")
            if new.get("debt_state") != expected.get("debt_state"):
                errors.append("retraining must preserve debt terms and trigger any collection due that day")
    except (api.RuntimeProblem, KeyError, TypeError, ValueError) as exc:
        errors.append("invalid allocation resolution: " + str(exc))
    return errors
