"""Empty, generation-scoped stock and confirmed-save refill requests.

The installer never invents fiction. This module supplies bounded requests to
the GM and verifies their origin before the existing append transaction runs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import uuid


CONTRACT = "machadan-refill-context-v1"
APPEND_SCHEMA = "machadan-inventory-append-v1"


def _version(api) -> str:
    path = api.ROOT.parent / "VERSION.txt"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    match = re.search(r"^version:\s*(\S+)", text, re.I | re.M)
    return match.group(1) if match else "unversioned"


def _paths(api) -> dict[str, Path]:
    return {"mobs": api.MOBS_PATH, "events": api.EVENTS_PATH}


def _marker_path(api) -> Path:
    return api.MOBS_PATH.parent / "lifecycle.json"


def _marker(api) -> dict:
    path = _marker_path(api)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _new_marker(api, version: str, reason: str) -> dict:
    epoch = uuid.uuid4().hex[:16]
    return {"schema": "machadan-inventory-lifecycle-v1", "package_version": version,
            "generation": version + "-" + epoch, "id_epoch": epoch,
            "reason": reason, "created_at": api.now_iso()}


def _empty(api, kind: str, marker: dict) -> dict:
    data = api.default_inventory(kind)
    data.update(generation=marker.get("generation", "uninitialized"),
                package_version=marker.get("package_version", _version(api)))
    return data


def initialize_unlocked(api, only: set[str] | None = None, force: bool = False) -> dict:
    """Create containers only. A missing stock file is not a request for seeds."""
    if force:
        raise api.RuntimeProblem("--forceで在庫を消しません。版更新のinventory-resetを使ってください")
    mapping = {"MOB_INVENTORY_STATE": "mobs", "EVENT_INVENTORY_STATE": "events"}
    chosen = [kind for resource, kind in mapping.items() if only is None or resource in only]
    marker = _marker(api)
    if not marker.get("generation"):
        marker = _new_marker(api, _version(api), "empty-initialization")
        api.atomic_write(_marker_path(api), json.dumps(marker, ensure_ascii=False, indent=2) + "\n")
    created, preserved = [], []
    for kind in chosen:
        path = _paths(api)[kind]
        relative = path.relative_to(api.ROOT).as_posix()
        if path.is_file():
            preserved.append(relative)
            continue
        api.atomic_write(path, api.dump_yaml(_empty(api, kind, marker)))
        created.append(relative)
    return {"created": created, "preserved": preserved, "generation": marker["generation"],
            "mode": "empty-until-confirmed-refill"}


def initialize(api, only: set[str] | None = None, force: bool = False) -> dict:
    """Public wrapper for callers that do not already hold stock locks."""
    with api.file_locks([api.inventory_lock_path(kind) for kind in ("mobs", "events")]):
        return initialize_unlocked(api, only, force)


def _read_states(api) -> dict:
    marker = _marker(api)
    states = {}
    for kind, path in _paths(api).items():
        state = api.load_yaml(path) if path.is_file() else _empty(api, kind, marker)
        errors, _ = api.validate_inventory_state(state, kind)
        if errors:
            raise api.RuntimeProblem("invalid " + kind + " inventory: " + "; ".join(errors))
        states[kind] = state
    return states


def reset(api, args) -> dict:
    """Discard only stock-owned files on a genuine package-version change."""
    if getattr(args, "reason", None) != "package-upgrade":
        raise api.RuntimeProblem("inventory-reset requires --reason package-upgrade")
    version = str(getattr(args, "generation", "") or "")
    if version != _version(api):
        raise api.RuntimeProblem("reset generation must equal the installed package version")
    with api.file_locks([api.inventory_lock_path(kind) for kind in ("mobs", "events")]):
        old = _marker(api)
        existing = {}
        for kind, path in _paths(api).items():
            if path.is_file():
                try:
                    existing[kind] = api.load_yaml(path)
                except Exception:
                    existing[kind] = None
        if (old.get("package_version") == version and old.get("generation") and
                all(isinstance(existing.get(kind), dict) and
                    existing[kind].get("generation") == old["generation"]
                    for kind in ("mobs", "events"))):
            return {"ok": True, "idempotent": True, "generation": old["generation"],
                    "discarded": [], "preserved_saves": True}
        marker = _new_marker(api, version, "package-upgrade")
        discarded = []
        # This directory is exclusively stock data, append receipts and stock backups.
        stock_root = api.MOBS_PATH.parent
        if stock_root.is_symlink():
            raise api.RuntimeProblem("stock directory must not be a symbolic link")
        if stock_root.is_dir():
            for path in sorted(stock_root.rglob("*"), reverse=True):
                if path.is_symlink():
                    path.unlink()
                elif path.is_file():
                    discarded.append(path.relative_to(api.ROOT).as_posix())
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
        # Old append inputs can live among unrelated runtime work. Remove only
        # positively identified append payloads; save candidates/turns stay intact.
        for runtime in (api.ROOT / "state" / "runtime", api.ROOT / "tools" / "runtime"):
            if not runtime.is_dir() or runtime.is_symlink():
                continue
            for path in runtime.rglob("*.json"):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                if isinstance(value, dict) and value.get("schema") == APPEND_SCHEMA:
                    discarded.append(path.relative_to(api.ROOT).as_posix())
                    path.unlink()
        for kind, path in _paths(api).items():
            api.atomic_write(path, api.dump_yaml(_empty(api, kind, marker)))
        api.atomic_write(_marker_path(api), json.dumps(marker, ensure_ascii=False, indent=2) + "\n")
        return {"ok": True, "idempotent": False, "generation": marker["generation"],
                "discarded": discarded, "preserved_saves": True}


def status(api, args=None) -> dict:
    """Inspect stock without creating files, importing seeds, or refilling."""
    states, marker = _readonly_states(api)
    return {"ok": True, **{kind: api.inventory_summary(state) for kind, state in states.items()},
            "generation": marker.get("generation"),
            "refill_contract": CONTRACT, "mode": "empty-until-confirmed-refill"}


def _readonly_states(api) -> tuple[dict, dict]:
    """Stable multi-file view without creating lockfiles in a read-only command."""
    paths = [*_paths(api).values(), _marker_path(api)]
    def snapshot():
        return {path: path.read_bytes() if path.is_file() else None for path in paths}
    for _ in range(3):
        before = snapshot()
        states = _read_states(api)
        marker = _marker(api)
        if before == snapshot():
            return states, marker
    raise api.RuntimeProblem("stock changed during inspection; retry the same read")


def refill_request(api, save_path) -> dict:
    """Read-only reminder used after a save is committed or a turn starts."""
    try:
        path, save = _confirmed_save(api, save_path)
    except (api.RuntimeProblem, OSError, ValueError, TypeError):
        return {"status": "needs_campaign", "required": False, "refill_contract": CONTRACT}
    profile = _profile(save)
    try:
        states, _ = _readonly_states(api)
    except (api.RuntimeProblem, OSError, ValueError, TypeError) as exc:
        return {"status": "unavailable", "required": False, "blocking": False,
                "refill_contract": CONTRACT, "detail": str(exc)}
    shortage = {}
    for kind, state in states.items():
        if not profile["readiness"][kind]:
            continue
        # Count only this campaign's candidates when deciding whether it has a
        # usable initial stock. Global capacity remains enforced by append.
        available = {category: sum(
            isinstance(entry, dict) and entry.get("category") == category and
            entry.get("status", "unused") == "unused" and
            entry.get("campaign_id") == save.get("campaign_id")
            for entry in state.get("entries", [])) for category in state["limits"]}
        summary = api.inventory_summary(state)
        eligible = set(_event_categories(profile)) if kind == "events" else set(state["limits"])
        shortage[kind] = [category for category, count in available.items()
                          if category in eligible and count < 2 and summary[category]["open"] > 0]
    shortage = {kind: categories for kind, categories in shortage.items() if categories}
    return {"status": "needed" if shortage else
            ("waiting" if profile["readiness"]["waiting_for"] else "ready"),
            "required": bool(shortage), "save": str(path), "campaign_id": save.get("campaign_id"),
            "kinds": shortage, "readiness": profile["readiness"], "refill_contract": CONTRACT,
            "command": ["inventory-template", "--save", str(path), "--output", "<refill.json>", "--max", "8"],
            "blocking": False}


def _confirmed_save(api, raw_path) -> tuple[Path, dict]:
    raw = Path(raw_path).expanduser()
    if raw.is_symlink():
        raise api.RuntimeProblem("refill save cannot be a symbolic link")
    path = raw.resolve()
    save_root = (api.ROOT / "saves").resolve()
    # Work candidates and historical saves cannot trigger generation.
    if path.parent != save_root or not path.is_file():
        raise api.RuntimeProblem("補充対象はsaves直下の確定済みセーブを指定してください")
    save = api.load_yaml(path)
    errors, _ = api.validate_save_data(save)
    if errors:
        raise api.RuntimeProblem("refill save is invalid: " + "; ".join(errors))
    return path, save


def readiness(save: dict) -> dict:
    progress = save.get("hearing_progress", {})
    player = save.get("player", {})
    hearing = isinstance(progress, dict) and progress.get("status") == "complete"
    job = str(player.get("job") or "").strip() if isinstance(player, dict) else ""
    job_ready = bool(isinstance(player, dict) and player.get("build_complete") is True and job)
    return {"mobs": hearing, "events": job_ready,
            "waiting_for": ([] if hearing else ["hearing_completion"]) +
                           ([] if job_ready else ["confirmed_job"])}


def _profile(save: dict) -> dict:
    from event_connections import companion_ids
    ready = readiness(save)
    player = save.get("player", {})
    pref = save.get("partner_pref", {})
    world = save.get("world_state", {})
    world = world if isinstance(world, dict) else {}
    run = world.get("dungeon_run", {})
    run = run if isinstance(run, dict) else {}
    confirmed_pref = {}
    if ready["mobs"] and isinstance(pref, dict):
        for key in ("personalities", "sub_personalities", "body_height", "body_build", "body_bust", "call"):
            confirmed_pref[key] = copy.deepcopy(pref.get(key, []))
    return {"campaign_id": save.get("campaign_id"), "readiness": ready,
            "partner_preferences": confirmed_pref,
            "ng": copy.deepcopy(save.get("ng", [])),
            "job": player.get("job") if ready["events"] else None,
            "job_profile": copy.deepcopy(player.get("job_profile")) if ready["events"] else None,
            "world_context": {"location": world.get("location"),
                              "location_kind": world.get("location_kind"),
                              "dungeon_active": run.get("active") is True,
                               "current_floor": run.get("current_floor") or world.get("depth"),
                               "companion_ids": companion_ids(save)},
            "world_rule_resources": ["WORLD", "LOCATIONS", "DUNGEON_DATA", "MAGITECH"]}


def _fingerprint(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _prefix(marker: dict, campaign: str) -> str:
    epoch = str(marker.get("id_epoch") or "")
    campaign_hash = hashlib.sha256(campaign.encode()).hexdigest()[:8]
    return "STK-" + epoch + "-" + campaign_hash + "-"


def _event_categories(profile: dict, requested_kind=None) -> list[str]:
    world = profile.get("world_context", {})
    kind = requested_kind or world.get("location_kind")
    floor_known = isinstance(world.get("current_floor"), int) and not isinstance(world.get("current_floor"), bool) and 1 <= world["current_floor"] <= 9
    if world.get("dungeon_active"):
        kind = "dungeon"
    if kind == "dungeon":
        return ["dungeon"] if floor_known else []
    if kind in {"town", "road"}:
        return [kind]
    return ["town", "road"] + (["dungeon"] if floor_known else [])


def template(api, args) -> dict:
    maximum = getattr(args, "max", 8)
    if not isinstance(maximum, int) or not 1 <= maximum <= 8:
        raise api.RuntimeProblem("--max must be in 1..8")
    raw_save = getattr(args, "save", None)
    if not raw_save:
        return {"ok": True, "status": "needs_campaign", "added": 0,
                "refill_contract": CONTRACT,
                "next_action": "inventory-template --save <committed-save> --output <refill.json> --max 8"}
    save_path, save = _confirmed_save(api, raw_save)
    profile = _profile(save)
    ready = profile["readiness"]
    with api.file_locks([api.inventory_lock_path(kind) for kind in ("mobs", "events")]):
        initialize_unlocked(api)
        states = _read_states(api)
        marker = _marker(api)
        capacity = {kind: api.inventory_summary(state) for kind, state in states.items()}
    campaign = str(save["campaign_id"])
    prefix = _prefix(marker, campaign)
    requested = {"mobs": {}, "events": {}}
    categories = []
    location_kind = getattr(args, "location_kind", None)
    mob_order = ["town", "companions", "brothel", "students", "travelers"]
    event_order = _event_categories(profile, location_kind)
    for kind, order in (("mobs", mob_order), ("events", event_order)):
        if not ready[kind]:
            continue
        categories.extend((kind, category) for category in order if capacity[kind][category]["open"] > 0)
    # One per category on each refill keeps requests small and includes all kinds.
    for kind, category in categories[:maximum]:
        requested[kind][category] = 1
    total = sum(sum(values.values()) for values in requested.values())
    context = {"schema": CONTRACT, "generation": marker["generation"],
               "package_version": marker["package_version"], "campaign_id": campaign,
               "save_path": str(save_path), "profile_sha256": _fingerprint(profile),
               "id_prefix": prefix, "profile": profile, "requested_counts": requested}
    payload = {"schema": APPEND_SCHEMA, "run_id": "refill-REPLACE-ME", "context": context,
               "capacity_snapshot": capacity,
               "rules": {"max_total_entries": min(maximum, total), "requested_counts": requested,
                         "category_ids": {kind: list(state["limits"]) for kind, state in states.items()},
                         "entry_identity": {"id_prefix": prefix, "campaign_id": campaign,
                                            "generation": marker["generation"]},
                         "generation_guidance": [
                             "Use only confirmed preferences/job in context.profile. Empty preferences mean no preference.",
                             "Generate only requested categories/counts; leave kinds waiting for confirmation empty.",
                             "Keep world rules, NPC autonomy and player choices. No predetermined ending.",
                             "Dungeon events obey the current floor and never grant an unearned early boss route.",
                             "Canonical event copies keep title/type/fields, set canonical_seed_id, and end their new id with that seed ID.",
                             "Use canonical_event_candidates, including EV-S16..21 and EV-DE01..06, only when unmet_conditions is empty.",
                             "Stock limits remain town/road/dungeon=15 each. Do not load the entire seed deck into stock or reset used entries.",
                         ],
                         "mob_required": ["id", "campaign_id", "generation", "category", "name", "age>=18", "status=unused"],
                         "event_required": ["id", "campaign_id", "generation", "category", "title", "status=unused", "non-empty fields or description"]},
               "mobs": [], "events": []}
    from event_connections import catalog, canonical_events, unmet
    payload["rules"]["canonical_event_candidates"] = catalog(api, profile, requested["events"])
    selected_seed = getattr(args, "event_seed", None)
    if selected_seed:
        seed = next((entry for entry in canonical_events(api) if entry["id"] == selected_seed), None)
        if seed is None or not requested["events"].get(seed["category"]):
            raise api.RuntimeProblem("canonical event seed is missing or its category has no requested capacity")
        missing = unmet(seed, profile["world_context"])
        if missing:
            raise api.RuntimeProblem("canonical event conditions not met: " + ", ".join(missing))
        entry = copy.deepcopy(seed)
        entry.update(id=prefix + selected_seed, canonical_seed_id=selected_seed,
                     campaign_id=campaign, generation=marker["generation"], status="unused")
        # A seed may return on a later visit, but never reuse its stock instance ID.
        known = {str(item.get("id")) for item in states["events"].get("entries", [])}
        suffix = 1
        while entry["id"] in known:
            suffix += 1
            entry["id"] = prefix + str(suffix) + "-" + selected_seed
        payload["events"] = [entry]
    output = Path(args.output).expanduser()
    if (output.resolve().is_relative_to(api.ROOT.resolve()) and
            not output.resolve().is_relative_to((api.ROOT / "state" / "runtime").resolve())):
        raise api.RuntimeProblem("refill output inside the runtime must be in state/runtime")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    identical = output.is_file() and output.read_text(encoding="utf-8") == text
    if output.exists() and not identical and not getattr(args, "force", False):
        raise api.RuntimeProblem("refusing to overwrite existing refill request: " + str(output))
    if not identical:
        api.atomic_write(output, text)
    return {"ok": True, "status": "ready" if total else ("waiting" if ready["waiting_for"] else "full"),
            "output": str(output), "idempotent": identical, "max": maximum,
            "requested_total": total, "readiness": ready, "generation": marker["generation"],
            "schema": str(api.INVENTORY_APPEND_SCHEMA), "capacity": capacity}


def append_guard(api, payload: dict, states: dict) -> None:
    context = payload.get("context")
    if not isinstance(context, dict) or context.get("schema") != CONTRACT:
        raise api.RuntimeProblem("inventory refill needs current contextual template; run inventory-template --save")
    marker = _marker(api)
    generation = marker.get("generation")
    if not generation or context.get("generation") != generation or any(
            state.get("generation") != generation for state in states.values()):
        raise api.RuntimeProblem("stale inventory generation; prepare a new refill request")
    _, save = _confirmed_save(api, context.get("save_path") or "")
    profile = _profile(save)
    if context.get("campaign_id") != save.get("campaign_id") or context.get("profile_sha256") != _fingerprint(profile):
        raise api.RuntimeProblem("confirmed refill profile changed; prepare a new refill request")
    if context.get("profile") != profile:
        raise api.RuntimeProblem("refill profile does not match the confirmed save")
    prefix = _prefix(marker, str(save["campaign_id"]))
    if context.get("id_prefix") != prefix:
        raise api.RuntimeProblem("refill identity prefix does not match generation/campaign")
    requested = context.get("requested_counts")
    if not isinstance(requested, dict):
        raise api.RuntimeProblem("refill request is missing requested_counts")
    for kind in ("mobs", "events"):
        entries = payload.get(kind, [])
        if not isinstance(entries, list):
            raise api.RuntimeProblem(kind + " additions must be a list")
        if entries and not profile["readiness"][kind]:
            raise api.RuntimeProblem(kind + " refill is waiting for confirmed hearing/job")
        counts = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise api.RuntimeProblem("inventory entries must be mappings")
            if entry.get("campaign_id") != save["campaign_id"] or entry.get("generation") != generation:
                raise api.RuntimeProblem("entry campaign/generation does not match refill request")
            entry_id = str(entry.get("id") or "")
            if not entry_id.startswith(prefix) or len(entry_id) <= len(prefix):
                raise api.RuntimeProblem("new stock ids must use the generation/campaign prefix")
            category = str(entry.get("category") or "")
            if kind == "events" and category == "dungeon" and not (
                    isinstance(profile["world_context"].get("current_floor"), int) and
                    not isinstance(profile["world_context"].get("current_floor"), bool) and
                    1 <= profile["world_context"]["current_floor"] <= 9):
                raise api.RuntimeProblem("dungeon refill waits until a canonical floor is known")
            counts[category] = counts.get(category, 0) + 1
            seed_id = entry.get("canonical_seed_id")
            if seed_id is not None or entry_id.endswith("-EV-D10"):
                from event_connections import canonical_events, unmet
                if kind != "events" or not isinstance(seed_id, str) or not entry_id.endswith("-" + seed_id):
                    raise api.RuntimeProblem("canonical copies need canonical_seed_id and a matching stock ID suffix")
                canonical = next((item for item in canonical_events(api) if item["id"] == seed_id), None)
                if canonical is None or canonical.get("category") != category:
                    raise api.RuntimeProblem("canonical seed is missing or has a different category")
                if set(entry) - (set(canonical) | {"canonical_seed_id", "campaign_id", "generation"}):
                    raise api.RuntimeProblem("canonical event copies cannot add alternate content fields")
                missing = unmet(canonical, profile["world_context"])
                if missing:
                    raise api.RuntimeProblem("canonical event conditions not met: " + ", ".join(missing))
                for key in ("title", "type"):
                    if entry.get(key) != canonical.get(key):
                        raise api.RuntimeProblem("canonical event content may not be rewritten")
                clean_fields = lambda item: {key: value for key, value in (item.get("fields") or {}).items() if key != "状態"}
                if clean_fields(entry) != clean_fields(canonical):
                    raise api.RuntimeProblem("canonical event fields may not be rewritten")
        allowed = requested.get(kind, {})
        if not isinstance(allowed, dict):
            raise api.RuntimeProblem("invalid refill requested_counts")
        if any(category not in states[kind]["limits"] or not isinstance(count, int) or
               isinstance(count, bool) or count != 1 for category, count in allowed.items()):
            raise api.RuntimeProblem("refill requests add at most one per known category")
        for category, count in counts.items():
            limit = allowed.get(category, 0)
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0 or count > limit:
                raise api.RuntimeProblem("refill exceeds requested category count: " + kind + "/" + category)
