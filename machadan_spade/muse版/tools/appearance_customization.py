"""Confirmed campaign-local cosmetic overrides for existing adult named cast.

Canonical persona files, identity, personality and mechanics are immutable.
The second complete contract payoff unlocks the option; it never applies a
change automatically. Preview and resolution write only private working files.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
import uuid

SCHEMA = "machadan-appearance-request-v1"
STRINGS = {"hair", "eyes", "skin", "face", "build", "body_shape", "bust", "outfit", "appearance_notes"}
FIELDS = STRINGS | {"height_cm", "features"}
RECEIPT_KEYS = {"request_id", "transaction_id", "character_id", "mode", "source_revision", "source_sha256",
                "persona_sha256", "before", "after"}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MINOR = re.compile(r"未成年|幼児|幼女|幼男|小学生|中学生|高校生|18\s*歳未満|\b(?:underage|preteen|child|under\s*18)\b", re.I)
_AGE = re.compile(r"([0-9]{1,4}|[〇零一二三四五六七八九十]{1,4})\s*(?:歳|才|years?\s*old|[- ]year[- ]old)", re.I)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _empty():
    return {"version": 1, "overrides": {}, "resolutions": []}


def _state(data):
    world = data.get("world_state") if isinstance(data, dict) else None
    return world.get("appearance_customization", _empty()) if isinstance(world, dict) else _empty()


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("appearance text must be nonempty and within its length limit")
    text = value.strip()
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("appearance text contains control characters")
    normalized = unicodedata.normalize("NFKC", text)
    if _MINOR.search(normalized):
        raise ValueError("appearance customization is limited to adult appearances")
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    digits["〇"] = 0
    for match in _AGE.finditer(normalized):
        raw = match.group(1)
        if raw.isdigit():
            number = int(raw)
        elif "十" in raw:
            left, right = raw.split("十", 1)
            number = (digits.get(left, 1) if left else 1) * 10 + (digits.get(right, 0) if right else 0)
        else:
            number = int("".join(str(digits[char]) for char in raw))
        if number < 18:
            raise ValueError("appearance customization cannot specify an underage appearance")
    return text


def _patch(value, *, allow_clear=False):
    if not isinstance(value, dict) or not value or set(value) - FIELDS:
        raise ValueError("appearance changes must contain only supported cosmetic fields")
    result = {}
    for key, item in value.items():
        if item is None and allow_clear:
            result[key] = None
        elif key in STRINGS:
            result[key] = _text(item, 1000)
        elif key == "height_cm":
            if (not isinstance(item, (int, float)) or isinstance(item, bool)
                    or not math.isfinite(item) or not 0 < item <= 100000):
                raise ValueError("height_cm must be a finite positive number no greater than 100000")
            result[key] = item
        elif key == "features":
            if not isinstance(item, list) or len(item) > 20:
                raise ValueError("features must be a list of at most 20 cosmetic descriptions")
            features = [_text(part, 200) for part in item]
            if len(features) != len(set(features)):
                raise ValueError("cosmetic features must be unique")
            result[key] = features
    return result


def _target(api, character_id):
    _, routes, _ = api.load_control()
    relative = routes.get("persona_files", {}).get(character_id)
    if not isinstance(character_id, str) or not isinstance(relative, str):
        raise api.RuntimeProblem("select a canonical named character_id from persona_files")
    path = (api.ROOT / relative).resolve()
    if not path.is_relative_to((api.ROOT / "人格").resolve()) or not path.is_file():
        raise api.RuntimeProblem("canonical persona is missing or outside the persona directory")
    text = path.read_text(encoding="utf-8")
    if not re.search(r"\[CHAR_ID:\s*" + re.escape(character_id) + r"\s*\]", text):
        raise api.RuntimeProblem("persona file and canonical character_id differ")
    age = re.search(r"(?m)^Age:\s*(.+)$", text)
    numeric_age = re.match(r"\s*(\d+)\s*歳", age.group(1)) if age else None
    adult = bool(numeric_age and int(numeric_age.group(1)) >= 18)
    if not adult and age and not numeric_age:
        adult = "成人" in age.group(1) or bool(re.search(r"(?:[2-9][0-9]|[1-9][0-9]{2,})代", age.group(1)))
    if not adult:
        raise api.RuntimeProblem("appearance target must be a canonically confirmed adult")
    name = re.search(r"(?m)^Name:\s*(.+)$", text)
    return {"character_id": character_id, "name": name.group(1).strip() if name else character_id,
            "persona_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "persona_source": relative}


def _eligible(api, data):
    from debt_contracts import debt_unlocks
    if debt_unlocks(data).get("named_appearance_customization") is not True:
        raise api.RuntimeProblem("named appearance customization requires the confirmed second complete contract payoff")


def _source(api, value):
    raw = Path(value).expanduser()
    path = raw.resolve()
    saves = (api.ROOT / "saves").resolve()
    if raw.is_symlink() or path.parent != saves or not path.is_file() or path.suffix not in {".yaml", ".yml"}:
        raise api.RuntimeProblem("appearance requests require a current committed campaign save, not a candidate/history file")
    data = api.load_yaml(path)
    errors, warnings = api.validate_save_data(data)
    if errors:
        raise api.RuntimeProblem("appearance source save is invalid: " + "; ".join(errors))
    return path, data, warnings


def _output(api, value):
    path = Path(value).expanduser().resolve()
    if not path.is_relative_to((api.ROOT / "state/runtime").resolve()):
        raise api.RuntimeProblem("appearance working files must stay under state/runtime")
    return path


def _request_path(api, request_id):
    return api.ROOT / "state/runtime/appearance-requests" / (api.safe_id(request_id) + ".json")


def _write(api, path, content):
    if path.is_symlink():
        raise api.RuntimeProblem("appearance working files must not be symbolic links")
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise api.RuntimeProblem("refusing to overwrite a different appearance request/candidate")
    else:
        api.atomic_write(path, content)


def _load_request(api, request_id):
    path = _request_path(api, request_id)
    if not path.is_file() or path.is_symlink():
        raise api.RuntimeProblem("appearance request is missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("request_id") != request_id:
        raise api.RuntimeProblem("unsupported appearance request")
    digest = value.pop("request_hash", None)
    if digest != _hash(value):
        raise api.RuntimeProblem("appearance request contents changed")
    value["request_hash"] = digest
    return value


def _verify(api, data, request):
    _eligible(api, data)
    if (request.get("campaign_id") != data.get("campaign_id")
            or request.get("source_revision") != data.get("save_revision")
            or request.get("source_sha256") != _hash(data)):
        raise api.RuntimeProblem("appearance preview is stale; reopen it from the current save")
    target = _target(api, request.get("character_id"))
    if target["persona_sha256"] != request.get("persona_sha256"):
        raise api.RuntimeProblem("canonical persona changed after the appearance preview")
    state = _state(data)
    if any(row.get("request_id") == request["request_id"] for row in state["resolutions"]):
        raise api.RuntimeProblem("appearance request has already been applied")
    before = state["overrides"].get(target["character_id"])
    if before != request.get("before"):
        raise api.RuntimeProblem("appearance preview does not match the current override")
    mode = request.get("mode")
    if mode == "restore":
        after = None
    elif mode == "change":
        changes = _patch(request.get("changes"), allow_clear=True)
        after = copy.deepcopy(before or {})
        for key, value in changes.items():
            if value is None:
                after.pop(key, None)
            else:
                after[key] = value
        after = _patch(after) if after else None
    else:
        raise api.RuntimeProblem("unsupported appearance operation")
    if after != request.get("after") or before == after:
        raise api.RuntimeProblem("appearance preview result is inconsistent or unchanged")
    return target, before, after


def preview(api, args):
    source = Path(args.save).expanduser().resolve()
    output = _output(api, args.output)
    request_id = getattr(args, "request_id", None) or "appearance-" + uuid.uuid4().hex
    request_path = _request_path(api, request_id)
    if output == request_path:
        raise api.RuntimeProblem("appearance preview and request need different output paths")
    with api.file_locks([api.save_lock_path(source), api.save_lock_path(output), api.save_lock_path(request_path)]):
        source, data, warnings = _source(api, args.save)
        source_file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        _eligible(api, data)
        target = _target(api, args.character_id)
        before = copy.deepcopy(_state(data)["overrides"].get(target["character_id"]))
        restore = getattr(args, "restore", False)
        if restore and getattr(args, "changes", None):
            raise api.RuntimeProblem("restore does not accept an appearance patch")
        if not restore and not getattr(args, "changes", None):
            raise api.RuntimeProblem("appearance changes JSON is required")
        try:
            if restore:
                changes, after = None, None
            else:
                path = Path(args.changes).expanduser()
                if path.stat().st_size > 65536:
                    raise ValueError("appearance changes JSON exceeds 64KiB")
                changes = _patch(json.loads(path.read_text(encoding="utf-8")), allow_clear=True)
                after = copy.deepcopy(before or {})
                for key, value in changes.items():
                    if value is None:
                        after.pop(key, None)
                    else:
                        after[key] = value
                after = _patch(after) if after else None
            if before == after:
                raise ValueError("appearance is unchanged")
        except (ValueError, OSError) as exc:
            raise api.RuntimeProblem(str(exc)) from exc
        request = {"schema": SCHEMA, "request_id": request_id, "campaign_id": data["campaign_id"],
                   "source_revision": data["save_revision"], "source_sha256": _hash(data),
                   "source_file_sha256": source_file_hash, "character_id": target["character_id"],
                   "persona_sha256": target["persona_sha256"], "mode": "restore" if restore else "change",
                   "before": before, "after": after, "changes": changes}
        request["request_hash"] = _hash(request)
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_file_hash:
            raise api.RuntimeProblem("source changed while preparing appearance preview")
        _write(api, request_path, json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        shown = {"schema": "machadan-appearance-preview-v1", "request_id": request_id, **target,
                 "before": before, "after": after, "mode": request["mode"],
                 "draft_only": True, "confirmation_required": "確定",
                 "notice": "外見表示だけの変更案です。確定しても人格・年齢・能力・関係・装備の効果は変わりません。"}
        _write(api, output, json.dumps(shown, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return {"ok": True, "request_id": request_id, "output": str(output), "draft_only": True,
            "preview": shown, "warnings": warnings}


def _build(api, data, request, transaction_id):
    target, before, after = _verify(api, data, request)
    result = copy.deepcopy(data)
    state = result["world_state"].setdefault("appearance_customization", _empty())
    if after is None:
        state["overrides"].pop(target["character_id"], None)
    else:
        state["overrides"][target["character_id"]] = copy.deepcopy(after)
    receipt = {"request_id": request["request_id"], "transaction_id": transaction_id,
               "character_id": target["character_id"], "mode": request["mode"],
               "source_revision": data["save_revision"], "source_sha256": request["source_sha256"],
               "persona_sha256": target["persona_sha256"], "before": before, "after": after}
    state["resolutions"].append(receipt)
    return result, receipt


def resolve(api, args):
    if not isinstance(args.confirmation, str) or args.confirmation.strip() != "確定":
        raise api.RuntimeProblem("appearance changes require the player's explicit chat confirmation: 確定")
    output = _output(api, args.output)
    request_path = _request_path(api, args.request_id)
    source = Path(args.save).expanduser().resolve()
    transaction_id = api.safe_id(args.transaction_id)
    with api.file_locks([api.save_lock_path(source), api.save_lock_path(output), api.save_lock_path(request_path)]):
        source, data, warnings = _source(api, args.save)
        request = _load_request(api, args.request_id)
        rows = _state(data)["resolutions"]
        if data.get("transaction", {}).get("last_transaction_id") == transaction_id and output.is_file():
            recorded = [row for row in rows if row.get("request_id") == args.request_id and row.get("transaction_id") == transaction_id]
            candidate = api.load_yaml(output)
            if len(recorded) == 1 and api.sha256_bytes(api.dump_yaml(candidate).encode()) == data["transaction"].get("last_candidate_hash"):
                return {"ok": True, "idempotent": True, "output": str(output), "request_id": args.request_id}
            raise api.RuntimeProblem("committed appearance retry differs from its recorded candidate")
        if hashlib.sha256(source.read_bytes()).hexdigest() != request.get("source_file_sha256"):
            raise api.RuntimeProblem("appearance preview is stale; current save bytes changed")
        try:
            result, receipt = _build(api, data, request, transaction_id)
        except (ValueError, TypeError) as exc:
            raise api.RuntimeProblem(str(exc)) from exc
        errors, final_warnings = api.validate_save_data(result)
        if errors:
            raise api.RuntimeProblem("appearance candidate is invalid: " + "; ".join(errors))
        if hashlib.sha256(source.read_bytes()).hexdigest() != request["source_file_sha256"]:
            raise api.RuntimeProblem("source changed while preparing appearance candidate")
        text = api.dump_yaml(result)
        identical = output.is_file() and output.read_text(encoding="utf-8") == text
        _write(api, output, text)
    return {"ok": True, "output": str(output), "request_id": args.request_id, "transaction_id": transaction_id,
            "idempotent": identical, "draft_only": True, "receipt": receipt,
            "warnings": [*warnings, *final_warnings]}


def overrides_for(data, character_ids):
    """Pure projection used by the ordinary bounded save view."""
    state = _state(data)
    overrides = state.get("overrides", {}) if isinstance(state, dict) else {}
    selected = {str(value) for value in character_ids if isinstance(value, str)}
    return {key: copy.deepcopy(value) for key, value in overrides.items() if key in selected}


def validate_state(api, data, errors):
    state = _state(data)
    if (not isinstance(state, dict) or state.get("version") != 1 or isinstance(state.get("version"), bool)
            or set(state) != {"version", "overrides", "resolutions"}
            or not isinstance(state.get("overrides"), dict) or len(state["overrides"]) > 64
            or not isinstance(state.get("resolutions"), list)):
        errors.append("appearance_customization requires version1, bounded overrides and resolutions")
        return
    if not state["overrides"] and not state["resolutions"]:
        return
    try:
        _eligible(api, data)
        known, rebuilt, seen_requests, seen_transactions = {}, {}, set(), set()
        def target(character_id):
            if character_id not in known:
                known[character_id] = _target(api, character_id)
            return known[character_id]
        for character_id, patch in state["overrides"].items():
            target(character_id)
            if _patch(patch) != patch:
                raise ValueError("saved appearance patches must already be normalised")
        for row in state["resolutions"]:
            if not isinstance(row, dict) or set(row) != RECEIPT_KEYS:
                raise ValueError("appearance audit receipt has unsupported fields")
            character_id = row["character_id"]
            target(character_id)
            for key, seen in (("request_id", seen_requests), ("transaction_id", seen_transactions)):
                api.safe_id(row[key])
                if row[key] in seen:
                    raise ValueError("appearance audit request/transaction IDs must be unique")
                seen.add(row[key])
            if (row["mode"] not in {"change", "restore"} or not _integer(row["source_revision"])
                    or row["source_revision"] < 0
                    or any(not isinstance(row[key], str) or _DIGEST.fullmatch(row[key]) is None
                           for key in ("source_sha256", "persona_sha256"))):
                raise ValueError("appearance audit receipt metadata is invalid")
            for key in ("before", "after"):
                if row[key] is not None and _patch(row[key]) != row[key]:
                    raise ValueError("appearance audit patches must already be normalised")
            if row["before"] != rebuilt.get(character_id) or row["before"] == row["after"]:
                raise ValueError("appearance audit before/after chain is inconsistent")
            if row["mode"] == "restore" and row["after"] is not None:
                raise ValueError("appearance restore must remove the campaign override")
            if row["after"] is None:
                rebuilt.pop(character_id, None)
            else:
                rebuilt[character_id] = row["after"]
        if rebuilt != state["overrides"]:
            raise ValueError("appearance overrides must equal the confirmed audit history")
    except (ValueError, TypeError, KeyError, api.RuntimeProblem) as exc:
        errors.append("appearance_customization: " + str(exc))


def validate_transition(api, old, new, transaction_id):
    before, after = _state(old), _state(new)
    if before == after:
        return []
    try:
        if (not isinstance(before, dict) or not isinstance(after, dict)
                or after.get("resolutions", [])[:len(before.get("resolutions", []))] != before.get("resolutions", [])
                or len(after.get("resolutions", [])) != len(before.get("resolutions", [])) + 1):
            raise ValueError("appearance history is append-only, one confirmed change per commit")
        row = after["resolutions"][-1]
        if row.get("transaction_id") != transaction_id:
            raise ValueError("appearance audit must use the current transaction ID")
        request = _load_request(api, row.get("request_id"))
        expected, receipt = _build(api, old, request, transaction_id)
        if row != receipt or after != _state(expected):
            raise ValueError("appearance result differs from the confirmed preview")
        if new != expected:
            raise ValueError("appearance confirmation may change only campaign cosmetic state")
    except (ValueError, TypeError, KeyError, api.RuntimeProblem) as exc:
        return ["invalid appearance transition: " + str(exc)]
    return []
