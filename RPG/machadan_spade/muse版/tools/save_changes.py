"""Bounded save views and lossless, optimistic JSON-pointer changes.

Views never replace the canonical save. Changes apply to a complete prepared
candidate, so fields omitted from a view remain byte-semantically intact.
"""
from __future__ import annotations

import copy
from typing import Any


def state_view(save: dict, scenes: list[str], subjects: list[str] | None = None) -> tuple[dict, list[str]]:
    view = copy.deepcopy(save)
    # A projection must never trust a display-only field copied into raw data.
    view.pop("runtime_cast_rules", None)
    omitted: list[str] = []
    if not set(scenes) & {"combat", "dungeon", "status", "skills", "magic", "shop", "enterprise"}:
        # Conversational scenes use effective values; calculation components
        # remain available as exact save fields when a new action needs them.
        detail_keys = {"base_stats", "growth_bonus", "equipment_bonus", "fire_bonus",
                       "temporary_modifiers", "base_lp", "job_lp_bonus", "fire_lp_bonus",
                       "temporary_lp_bonus", "stat_lp_bonus", "migration_legacy"}
        actors = [(view.get("player"), "/player")]
        actors += [(actor, f"/party/{i}") for i, actor in enumerate(view.get("party", []))]
        for actor, path in actors:
            if isinstance(actor, dict):
                for key in detail_keys:
                    if key in actor:
                        del actor[key]
                        omitted.append(path + "/" + key)

    def summarize(container: dict, key: str, path: str, keep: int = 4) -> None:
        value = container.get(key)
        if isinstance(value, list) and len(value) > keep:
            container[key] = {"total": len(value), "recent": value[-keep:] if keep else [],
                              "read_full_at": path}
            omitted.append(path)

    summarize(view, "session_log", "/session_log", 6)
    summarize(view, "memory_log", "/memory_log", 6)
    session = view.get("session_log")
    if isinstance(session, dict) and "read_full_at" not in session:
        summarize(session, "entries", "/session_log/entries", 6)
        previous = session.get("previous")
        if isinstance(previous, str) and len(previous) > 2000:
            session["previous"] = {"characters": len(previous), "read_full_at": "/session_log/previous",
                                   "notice": "過去ログ全文は保存済み。過去の出来事を確認する時だけこの参照先を読む"}
            omitted.append("/session_log/previous")
    memory = view.get("memory_log")
    if isinstance(memory, dict) and "read_full_at" not in memory:
        for category in ("encounters", "battles", "ero", "turning_points"):
            summarize(memory, category, "/memory_log/" + category, 6)
    transaction = view.get("transaction")
    if isinstance(transaction, dict):
        summarize(transaction, "applied_transaction_ids", "/transaction/applied_transaction_ids", 1)
    world = view.get("world_state")
    if isinstance(world, dict):
        summarize(world, "reward_ledger", "/world_state/reward_ledger", 2)
        growth = world.get("growth_state")
        if isinstance(growth, dict):
            summarize(growth, "resolutions", "/world_state/growth_state/resolutions", 2)
        allocation = world.get("allocation_state")
        if isinstance(allocation, dict):
            summarize(allocation, "resolutions", "/world_state/allocation_state/resolutions", 2)
        appearance = world.get("appearance_customization")
        if isinstance(appearance, dict):
            from appearance_customization import overrides_for
            all_overrides = appearance.get("overrides", {})
            appearance["overrides"] = overrides_for(save, subjects or [])
            if appearance["overrides"] != all_overrides:
                omitted.append("/world_state/appearance_customization/overrides")
            history = appearance.get("resolutions")
            if isinstance(history, list) and history:
                appearance["resolutions"] = {"total": len(history),
                    "read_full_at": "/world_state/appearance_customization/resolutions"}
                omitted.append("/world_state/appearance_customization/resolutions")
        # Old promises and facts about today's cast must survive the bounded
        # view even when they happened elsewhere and are not among recent facts.
        lore = world.get("campaign_lore")
        if isinstance(lore, dict) and len(lore) > 12:
            import json
            location = str(world.get("location", ""))
            identities = set(str(value) for value in (subjects or []) if value)
            actors = [save.get("player"), *save.get("party", [])]
            for actor in actors:
                if isinstance(actor, dict):
                    identities.update(str(actor[key]) for key in ("character_id", "name") if actor.get(key))
            for key in ("current_characters", "present_npc_ids", "active_npc_ids", "current_npc_ids"):
                values = world.get(key)
                if isinstance(values, list):
                    identities.update(str(value) for value in values if isinstance(value, str))

            def card_identities(value: Any) -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in {"name", "client", "npc_id", "character_id", "location", "location_id", "quest_id", "event_id"} and isinstance(child, str):
                            identities.add(child)
                        elif isinstance(child, (dict, list)):
                            card_identities(child)
                elif isinstance(value, list):
                    for child in value:
                        card_identities(child)

            card_identities(world.get("quest_card"))
            card_identities(save.get("active_event"))
            identities = {value.casefold() for value in identities if len(value) >= 2}

            def relevant_fact(key: str, value: Any) -> bool:
                if key == location or (isinstance(value, dict) and value.get("location") == location):
                    return True
                if isinstance(value, dict):
                    if value.get("unresolved") is True or value.get("status") in {"pending", "open", "unresolved", "promised"}:
                        return True
                    if value.get("resolved") is False and (
                        value.get("kind") in {"promise", "commitment", "quest"} or "約束" in key):
                        return True
                text = (str(key) + " " + json.dumps(value, ensure_ascii=False)).casefold()
                return any(identity in text for identity in identities)

            relevant = {k: v for k, v in lore.items() if relevant_fact(k, v)}
            keys = list(lore)
            relevant.update({k: lore[k] for k in keys[-8:]})
            world["campaign_lore"] = {"entries": relevant, "total": len(lore),
                                      "read_full_at": "/world_state/campaign_lore"}
            omitted.append("/world_state/campaign_lore")
    debt = view.get("debt_state")
    if isinstance(debt, dict):
        for key in ("ledger", "history", "payment_history", "collection_history", "collection_ledger"):
            summarize(debt, key, f"/debt_state/{key}", 2)
    if "Lilith_000" in (subjects or []):
        from debt_contracts import debt_unlocks
        unlocked = debt_unlocks(save).get("lilith_intimacy") is True
        view["runtime_cast_rules"] = {"Lilith_000": {
            "lilith_intimacy_unlocked": unlocked,
            "preferred_call": copy.deepcopy(save.get("partner_pref", {}).get("call", [])),
            "rule": ("初回完済済み。隠していた強い好意を露わにしてよい。親密さはプレイヤーが選び、借金は免除しない。"
                     if unlocked else "初回完済前。口説き・CHM・好感度・部屋契約でも絶対になびかず、隠れた好意を漏らさない。火授与・非性的な介抱と会話は可。"),
        }}
    return view, omitted


def pointer_parts(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("path must be a JSON pointer such as /player/gold")
    if not pointer:
        return []
    parts = pointer[1:].split("/")
    for part in parts:
        import re
        if re.search(r"~(?![01])", part):
            raise ValueError("invalid JSON-pointer escape")
    return [part.replace("~1", "/").replace("~0", "~") for part in parts]


def _index(part: str, size: int, *, add: bool = False) -> int:
    if add and part == "-":
        return size
    if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
        raise ValueError("list position must be a non-negative index or '-' for append")
    position = int(part)
    if position < 0 or position >= size + int(add):
        raise ValueError("list position is outside the existing list")
    return position


def read_pointer(data: Any, pointer: str) -> Any:
    value = data
    for part in pointer_parts(pointer):
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"save path does not exist: {pointer}")
            value = value[part]
        elif isinstance(value, list):
            value = value[_index(part, len(value))]
        else:
            raise ValueError(f"save path crosses a scalar: {pointer}")
    return copy.deepcopy(value)


def apply_operations(candidate: dict, operations: list[dict]) -> dict:
    if not isinstance(operations, list) or not 1 <= len(operations) <= 256:
        raise ValueError("changes must contain 1..256 operations")
    result = copy.deepcopy(candidate)
    protected = {"schema", "schema_version", "campaign_id", "created_at", "updated_at",
                 "save_revision", "game_version", "content_manifest_hash", "transaction"}
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("each change must be an object")
        kind = operation.get("op")
        if kind not in {"add", "replace", "remove", "test"}:
            raise ValueError("supported changes are add, replace, remove and test")
        parts = pointer_parts(operation.get("path"))
        if not parts:
            raise ValueError("replacing or deleting the entire save is not allowed")
        if kind != "test" and (parts[0] in protected or parts[0] == "runtime_state"):
            raise ValueError("runtime identity, revision and context are managed by the tool")
        if kind == "test":
            if read_pointer(result, operation["path"]) != operation.get("value"):
                raise ValueError(f"test failed: {operation['path']}")
            continue
        if kind in {"add", "replace"} and "value" not in operation:
            raise ValueError("add and replace require value")
        parent: Any = result
        for part in parts[:-1]:
            if isinstance(parent, dict) and part in parent:
                parent = parent[part]
            elif isinstance(parent, list):
                parent = parent[_index(part, len(parent))]
            else:
                raise ValueError(f"parent does not exist: {operation['path']}")
        key = parts[-1]
        if isinstance(parent, dict):
            if kind in {"replace", "remove"} and key not in parent:
                raise ValueError(f"path does not exist: {operation['path']}")
            if kind == "remove":
                del parent[key]
            else:
                parent[key] = copy.deepcopy(operation["value"])
        elif isinstance(parent, list):
            position = _index(key, len(parent), add=kind == "add")
            if kind == "add":
                parent.insert(position, copy.deepcopy(operation["value"]))
            elif kind == "remove":
                parent.pop(position)
            else:
                parent[position] = copy.deepcopy(operation["value"])
        else:
            raise ValueError(f"parent is not a container: {operation['path']}")
    return result
