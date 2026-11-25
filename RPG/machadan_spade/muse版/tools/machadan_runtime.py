#!/usr/bin/env python3
"""Deterministic runtime helper for Machadan Spade on Meta Muse.

This tool owns repeatable state mechanics that must not depend on model memory:
new-save creation, save validation/migration/atomic commit, scene context-pack
assembly, and bounded inventory updates. It never invents story content.
"""
from __future__ import annotations

import argparse
import copy
import html
import hashlib
import json
import os
import re
import shutil
import sys
sys.dont_write_bytecode = True
import tempfile
import time
import uuid
from types import SimpleNamespace
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError as exc:  # pragma: no cover - MUSE runtime is Linux
    raise SystemExit("this runtime requires POSIX fcntl file locking") from exc

_BOOTSTRAP_HERE = Path(__file__).resolve().parent
_VENDOR = _BOOTSTRAP_HERE / "_vendor"
_VENDORED_YAML = _VENDOR / "yaml" / "__init__.py"
if not _VENDORED_YAML.is_file():
    raise SystemExit("bundled YAML runtime is missing; rerun package setup")
sys.path.insert(0, str(_VENDOR))
try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("bundled YAML runtime is missing; rerun package setup") from exc
try:
    Path(yaml.__file__).resolve().relative_to(_VENDOR.resolve())
except (AttributeError, ValueError) as exc:  # pragma: no cover - fail closed
    raise SystemExit("refusing external YAML module; bundled runtime was not loaded") from exc
if getattr(yaml, "__version__", None) != "6.0.3":  # pragma: no cover - package integrity check
    raise SystemExit("bundled YAML runtime version mismatch; expected 6.0.3")

HERE = _BOOTSTRAP_HERE
ROOT = HERE.parent
REGISTRY_PATH = ROOT / "運用" / "正本レジストリ.yaml"
ROUTES_PATH = ROOT / "運用" / "ルーティング表.yaml"
ANCHORS_PATH = HERE / "anchors.json"
SAVE_TEMPLATE = ROOT / "セーブ雛形.yaml"
SAVE_SCHEMA = ROOT / "schemas" / "save_v3.schema.json"
WIDGET_SCHEMA = ROOT / "schemas" / "hearing_widget_state.schema.json"
INVENTORY_APPEND_SCHEMA = ROOT / "schemas" / "inventory_append.schema.json"
RUNTIME_DIR = ROOT / "state" / "runtime"
DEFAULT_CONTEXT = RUNTIME_DIR / "current_context.md"
MOBS_PATH = ROOT / "state" / "inventory" / "mobs.yaml"
EVENTS_PATH = ROOT / "state" / "inventory" / "events.yaml"
CURRENT_SCHEMA = "MachaDun_Save_Muse_v3"
CURRENT_SCHEMA_VERSION = 3
TAPE_REVISION = "machadan-tape-r1"
SAVE_REQUIRED_KEYS = (
    "game_version", "campaign_id", "created_at", "updated_at", "save_revision",
    "content_manifest_hash", "save_format_origin",
    "transaction", "hearing_progress", "active_script", "runtime_state",
    "dice_state", "fire_state", "world_state", "skills", "skill_dormancy",
    "custom_abilities", "active_event", "ammo", "shop_records", "captured_girls",
    "debt_state", "inventory", "item_definitions", "item_instances", "enterprise_state",
    "play_mode", "ero_style", "player", "player_body", "desire", "ng", "yuri",
    "partner_pref", "hearing_check", "spells", "equip", "items", "party",
    "inn_reserve", "npc_relationship", "session_log", "memory_log", "design_applied",
)

STAT_KEYS = ("str", "def", "int", "spd", "tec", "chm")
HUD_TEMPLATE = HERE / "status_dashboard_template.html"
QUEST_MUTABLE_KEYS = {"progress", "amendments"}


class RuntimeProblem(Exception):
    pass


LOCK_TIMEOUT_SECONDS = 10.0


@contextmanager
def file_locks(paths: list[Path], timeout: float = LOCK_TIMEOUT_SECONDS):
    """Acquire exclusive process locks in a fixed order, or fail retryably."""
    unique = sorted({path.resolve() for path in paths}, key=lambda item: str(item))
    opened = []
    deadline = time.monotonic() + timeout
    try:
        for path in unique:
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = path.open("a+", encoding="utf-8")
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        stream.close()
                        raise RuntimeProblem(f"state lock is busy; retry this operation: {path}")
                    time.sleep(0.05)
            stream.seek(0)
            stream.truncate()
            stream.write(f"pid={os.getpid()} acquired={now_iso()}\n")
            stream.flush()
            opened.append(stream)
        yield
    finally:
        for stream in reversed(opened):
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()


def save_lock_path(path: Path) -> Path:
    return path.parent / "_locks" / f"{path.name}.lock"


def inventory_lock_path(kind: str) -> Path:
    return ROOT / "state" / "locks" / f"inventory-{kind}.lock"


@contextmanager
def workspace_gate(timeout: float = 15.0):
    """Shared gate for state-changing runtime commands; installer holds it exclusively.

    The file lives outside the replaceable game tree, so its inode survives an
    upgrade. Per-save and inventory locks still serialize actual writes.
    """
    gate = ROOT.parent.parent / ".machadan-runtime.lock"
    gate.parent.mkdir(parents=True, exist_ok=True)
    with gate.open("a+", encoding="utf-8") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeProblem("更新中です。同じ操作を少し後で再実行してください")
                time.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_id(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise RuntimeProblem("campaign/run id must use A-Z, a-z, 0-9, _ or -")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeProblem(f"missing file: {path}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeProblem(f"invalid YAML {path}: {exc}") from exc


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def package_version() -> str:
    local_version = ROOT.parent / "VERSION.txt"
    if local_version.is_file():
        match = re.search(r"^version:\s*(.+)$", local_version.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1).strip()
    runtime_manifest = ROOT.parent / "RUNTIME_MANIFEST.json"
    if runtime_manifest.is_file():
        try:
            version = json.loads(runtime_manifest.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError):
            version = None
        if isinstance(version, str) and version:
            return version
    # The in-tree template outranks any unrelated workspace-level VERSION.txt.
    if SAVE_TEMPLATE.is_file():
        match = re.search(r'^game_version:\s*["\']?([^"\'\s#]+)',
                          SAVE_TEMPLATE.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1)
    development_version = ROOT.parent.parent / "VERSION.txt"
    if development_version.is_file():
        match = re.search(r"^version:\s*(.+)$", development_version.read_text(encoding="utf-8"), re.M)
        if match:
            return match.group(1).strip()
    raise RuntimeProblem("cannot determine game version from VERSION.txt or save template")


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_adult_value(value: Any, adult_status: Any = None) -> bool:
    if _is_integer(value):
        return value >= 18
    allowed = {
        "成人", "不詳(成人)", "年齢不詳(成人)",
        "canonical_adult", "confirmed_adult", "adult", "unknown(adult)",
    }
    for item in (value, adult_status):
        if item is None:
            continue
        normalized = re.sub(r"\s+", "", str(item)).casefold()
        if normalized in allowed:
            return True
    return False


def _valid_iso(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _require_mapping(data: dict, key: str, errors: list[str]) -> dict | None:
    value = data.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be a mapping")
        return None
    return value


REWARD_EFFECT_TARGETS = {
    "gold": {"player.gold"},
    "item": {"inventory_bundle"},
    "right": {"world_state.entitlements"},
    "service": {"world_state.entitlements", "session_log"},
    "favor": {"world_state.entitlements", "session_log"},
    "referral": {"world_state.entitlements", "session_log"},
    "information": {"world_state.entitlements", "session_log"},
    "legacy": {"session_log"},
}


def _reward_detail_complete(kind: Any, detail: Any, *, estimated: bool = False) -> bool:
    if not isinstance(detail, dict):
        return False
    if estimated and (
        not _is_integer(detail.get("estimated_value_g")) or
        not 0 <= detail["estimated_value_g"] <= 100
    ):
        return False
    if kind == "gold":
        return _is_integer(detail.get("amount")) and detail["amount"] >= 1
    if kind == "item":
        return (
            isinstance(detail.get("item_name"), str) and bool(detail["item_name"]) and
            _is_integer(detail.get("quantity")) and detail["quantity"] >= 1
        )
    if kind in {"right", "service", "favor", "referral", "information"}:
        target = detail.get("delivery_target")
        if target not in REWARD_EFFECT_TARGETS.get(str(kind), set()):
            return False
        if target == "session_log":
            return isinstance(detail.get("summary"), str) and bool(detail["summary"])
        uses = detail.get("uses_remaining")
        expires = detail.get("expires")
        return (
            all(isinstance(detail.get(key), str) and bool(detail[key])
                for key in ("entitlement_id", "name", "issuer")) and
            isinstance(detail.get("scope"), str) and
            isinstance(detail.get("conditions"), list) and
            (uses is None or (_is_integer(uses) and uses >= 1)) and
            (expires is None or isinstance(expires, str))
        )
    return False


def _validate_standard_reward_contract(
    contract: Any, label: str, errors: list[str], entitlements: dict[str, dict],
) -> None:
    if not isinstance(contract, dict):
        errors.append(f"{label} must be a mapping")
        return
    settlement_id = contract.get("settlement_id")
    if not isinstance(settlement_id, str) or not settlement_id:
        errors.append(f"{label}.settlement_id must be a non-empty string")
    offered = contract.get("offered")
    if not isinstance(offered, bool):
        errors.append(f"{label}.offered must be boolean")
    if not isinstance(contract.get("payer"), str) or not contract.get("payer"):
        errors.append(f"{label}.payer must be a non-empty string")
    components = contract.get("components")
    if not isinstance(components, list):
        errors.append(f"{label}.components must be a list")
        return
    if offered is True and not components:
        errors.append(f"{label}.components must not be empty when offered")
    if offered is False and components:
        errors.append(f"{label}.components must be empty when not offered")
    component_ids: set[str] = set()
    entitlement_ids: set[str] = set()
    allowed_states = {
        "offered", "accepted", "earned", "due", "pending",
        "delivered", "declined", "forfeited",
    }
    for index, component in enumerate(components):
        component_label = f"{label}.components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{component_label} must be a mapping")
            continue
        component_id = component.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            errors.append(f"{component_label}.component_id must be a non-empty string")
        elif component_id in component_ids:
            errors.append(f"duplicate reward contract component_id: {component_id}")
        else:
            component_ids.add(component_id)
        kind = component.get("kind")
        if kind not in REWARD_EFFECT_TARGETS or kind == "legacy":
            errors.append(f"{component_label}.kind is invalid")
        if component.get("state") not in allowed_states:
            errors.append(f"{component_label}.state is invalid")
        detail = component.get("detail")
        if component.get("legacy_migration"):
            continue
        if not _reward_detail_complete(kind, detail):
            errors.append(f"{component_label}.detail is incomplete for {kind}")
            continue
        if detail.get("delivery_target") == "world_state.entitlements":
            entitlement_id = detail["entitlement_id"]
            if entitlement_id in entitlement_ids:
                errors.append(f"duplicate reward contract entitlement_id: {entitlement_id}")
            else:
                entitlement_ids.add(entitlement_id)
            existing = entitlements.get(entitlement_id)
            already_delivered = (
                component.get("state") == "delivered" and isinstance(existing, dict) and
                existing.get("source_settlement_id") == settlement_id and
                existing.get("source_component_id") == component_id
            )
            if existing is not None and not already_delivered:
                errors.append(f"reward contract entitlement_id already exists: {entitlement_id}")


def _validate_active_contract_receipts(
    contract: Any, ledger_by_settlement: dict[str, dict[str, dict]],
    ledger_status: dict[str, str], label: str, errors: list[str],
) -> None:
    if not isinstance(contract, dict) or not isinstance(contract.get("settlement_id"), str):
        return
    settlement_id = contract["settlement_id"]
    if ledger_status.get(settlement_id) in {"settled", "declined", "forfeited"}:
        errors.append(f"terminal reward settlement must not retain {label}: {settlement_id}")
    ledger_components = ledger_by_settlement.get(settlement_id, {})
    for component in contract.get("components", []):
        if not isinstance(component, dict) or component.get("state") not in {
            "delivered", "declined", "forfeited",
        }:
            continue
        component_id = component.get("component_id")
        record = ledger_components.get(component_id)
        if not record or record.get("state") != component.get("state"):
            errors.append(
                f"{label} terminal state lacks matching ledger receipt: "
                f"{settlement_id}/{component_id}"
            )


def _reward_effect_value(data: dict, target: str) -> Any:
    if target == "inventory_bundle":
        return {
            "inventory": copy.deepcopy(data.get("inventory")),
            "item_definitions": copy.deepcopy(data.get("item_definitions")),
            "item_instances": copy.deepcopy(data.get("item_instances")),
        }
    value: Any = data
    for part in target.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _reward_value_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_bytes(payload.encode("utf-8"))


def _reward_item_count(data: dict, item_name: str) -> int | None:
    counts = _reward_item_counts(data)
    return counts.get(item_name, 0) if counts is not None else None


def _reward_item_counts(data: dict) -> dict[str, int] | None:
    counts: dict[str, int] = {}
    inventory = data.get("inventory")
    if isinstance(inventory, dict):
        stack_groups = [inventory.get("carried_stacks")]
        warehouse = inventory.get("warehouse")
        stack_groups.append(warehouse.get("stacks") if isinstance(warehouse, dict) else None)
        for items in stack_groups:
            if not isinstance(items, list):
                return None
            for item in items:
                if not isinstance(item, dict):
                    return None
                name, count = item.get("name"), item.get("count")
                if not isinstance(name, str) or not name or not _is_integer(count) or count < 0:
                    return None
                counts[name] = counts.get(name, 0) + count
        for item in data.get("item_instances", []):
            if not isinstance(item, dict):
                return None
            if item.get("location") == "consumed":
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                return None
            counts[name] = counts.get(name, 0) + 1
        return counts
    items = data.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            return None
        name, count = item.get("name"), item.get("count", 1)
        if not isinstance(name, str) or not name or not _is_integer(count) or count < 0:
            return None
        counts[name] = counts.get(name, 0) + count
    return counts


def _reward_log_entries(data: dict) -> list[Any] | None:
    session_log = data.get("session_log")
    if not isinstance(session_log, dict) or not isinstance(session_log.get("entries"), list):
        return None
    return session_log["entries"]


def _validate_reward_state(world_state: dict, errors: list[str]) -> None:
    """Validate optional M83 settlement state while keeping older v2 saves valid."""
    reward_state_version = world_state.get("reward_state_version")
    if reward_state_version != 2:
        errors.append("world_state.reward_state_version must be 2; migrate older saves first")
    for required_key in (
        "event_reward_contract", "pending_rewards", "reward_ledger", "entitlements",
    ):
        if required_key not in world_state:
            errors.append(f"world_state.{required_key} is required; migrate older saves first")
    component_kinds = {
        "gold", "item", "right", "service", "favor", "referral", "information",
    }
    ledger_component_kinds = component_kinds | {"legacy"}
    pending_component_states = {"accepted", "earned", "due", "pending"}
    existing_entitlement_ids = {
        item.get("entitlement_id")
        for item in world_state.get("entitlements", [])
        if isinstance(item, dict) and isinstance(item.get("entitlement_id"), str)
    } if isinstance(world_state.get("entitlements"), list) else set()
    event_contract_id: str | None = None
    event_contract = world_state.get("event_reward_contract")
    if event_contract is not None:
        label = "world_state.event_reward_contract"
        if not isinstance(event_contract, dict):
            errors.append(f"{label} must be null or a mapping")
        else:
            settlement_id = event_contract.get("settlement_id")
            if not isinstance(settlement_id, str) or not settlement_id:
                errors.append(f"{label}.settlement_id must be a non-empty string")
            else:
                event_contract_id = settlement_id
                if not settlement_id.startswith("EVR-"):
                    errors.append(f"{label}.settlement_id must start with EVR-")
            offered = event_contract.get("offered")
            if not isinstance(offered, bool):
                errors.append(f"{label}.offered must be boolean")
            if not isinstance(event_contract.get("payer"), str):
                errors.append(f"{label}.payer must be a string")
            components = event_contract.get("components")
            if not isinstance(components, list):
                errors.append(f"{label}.components must be a list")
            else:
                if offered is True and not components:
                    errors.append(f"{label}.components must not be empty when offered")
                if offered is False and components:
                    errors.append(f"{label}.components must be empty when not offered")
                component_ids: set[str] = set()
                event_entitlement_ids: set[str] = set()
                estimated_total = 0
                for index, component in enumerate(components):
                    component_label = f"{label}.components[{index}]"
                    if not isinstance(component, dict):
                        errors.append(f"{component_label} must be a mapping")
                        continue
                    component_id = component.get("component_id")
                    if not isinstance(component_id, str) or not component_id:
                        errors.append(f"{component_label}.component_id must be a non-empty string")
                    elif component_id in component_ids:
                        errors.append(f"duplicate event reward component_id: {component_id}")
                    else:
                        component_ids.add(component_id)
                    if component.get("kind") not in component_kinds:
                        errors.append(f"{component_label}.kind is invalid")
                    if component.get("state") != "offered":
                        errors.append(
                            f"{component_label}.state must remain offered until immediate settlement"
                        )
                    detail = component.get("detail")
                    if not isinstance(detail, dict):
                        errors.append(f"{component_label}.detail must be a mapping")
                        continue
                    if component.get("legacy_migration"):
                        continue
                    estimated_value = detail.get("estimated_value_g")
                    if not _is_integer(estimated_value) or not 0 <= estimated_value <= 100:
                        errors.append(
                            f"{component_label}.detail.estimated_value_g must be an integer in 0..100"
                        )
                    else:
                        estimated_total += estimated_value
                    if component.get("kind") == "gold":
                        amount = detail.get("amount")
                        if not _is_integer(amount) or not 1 <= amount <= 100:
                            errors.append(f"{component_label}.detail.amount must be an integer in 1..100")
                        elif _is_integer(estimated_value) and amount != estimated_value:
                            errors.append(f"{component_label}.detail.amount must equal estimated_value_g")
                    if component.get("kind") == "item":
                        if not isinstance(detail.get("item_name"), str) or not detail.get("item_name"):
                            errors.append(
                                f"{component_label}.detail.item_name must be a non-empty string"
                            )
                        quantity = detail.get("quantity")
                        if not _is_integer(quantity) or quantity < 1:
                            errors.append(
                                f"{component_label}.detail.quantity must be an integer >= 1"
                            )
                    if component.get("kind") in {
                        "right", "service", "favor", "referral", "information",
                    }:
                        delivery_target = detail.get("delivery_target")
                        if delivery_target not in REWARD_EFFECT_TARGETS.get(
                            str(component.get("kind")), set()
                        ):
                            errors.append(f"{component_label}.detail.delivery_target is invalid")
                        elif delivery_target == "world_state.entitlements":
                            for key in ("entitlement_id", "name", "issuer"):
                                if not isinstance(detail.get(key), str) or not detail.get(key):
                                    errors.append(
                                        f"{component_label}.detail.{key} must be a non-empty string"
                                    )
                            entitlement_id = detail.get("entitlement_id")
                            if isinstance(entitlement_id, str) and entitlement_id:
                                if entitlement_id in event_entitlement_ids:
                                    errors.append(
                                        f"duplicate event reward entitlement_id: {entitlement_id}"
                                    )
                                else:
                                    event_entitlement_ids.add(entitlement_id)
                                if entitlement_id in existing_entitlement_ids:
                                    errors.append(
                                        f"event reward entitlement_id already exists: {entitlement_id}"
                                    )
                            if not isinstance(detail.get("scope"), str):
                                errors.append(f"{component_label}.detail.scope must be a string")
                            if not isinstance(detail.get("conditions"), list):
                                errors.append(f"{component_label}.detail.conditions must be a list")
                            uses = detail.get("uses_remaining")
                            if uses is not None and (not _is_integer(uses) or uses < 1):
                                errors.append(
                                    f"{component_label}.detail.uses_remaining must be null or "
                                    "an integer >= 1"
                                )
                            expires = detail.get("expires")
                            if expires is not None and not isinstance(expires, str):
                                errors.append(
                                    f"{component_label}.detail.expires must be null or a string"
                                )
                        elif delivery_target == "session_log":
                            if not isinstance(detail.get("summary"), str) or not detail.get("summary"):
                                errors.append(
                                    f"{component_label}.detail.summary must be a non-empty string"
                                )
                if estimated_total > 100:
                    errors.append(f"{label} exceeds the 100G-equivalent random-event cap")
    pending_by_settlement: dict[str, set[str]] = {}
    delivered_mirrors: dict[str, set[str]] = {}
    pending = world_state.get("pending_rewards")
    if pending is not None and not isinstance(pending, list):
        errors.append("world_state.pending_rewards must be a list when present")
    elif isinstance(pending, list):
        settlement_ids: set[str] = set()
        for index, entry in enumerate(pending):
            label = f"world_state.pending_rewards[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be a mapping")
                continue
            settlement_id = entry.get("settlement_id")
            if not isinstance(settlement_id, str) or not settlement_id:
                errors.append(f"{label}.settlement_id must be a non-empty string")
            elif settlement_id in settlement_ids:
                errors.append(f"duplicate pending reward settlement_id: {settlement_id}")
            else:
                settlement_ids.add(settlement_id)
                if settlement_id.startswith("EVR-"):
                    errors.append(f"random-event reward cannot be pending: {settlement_id}")
            if entry.get("status") not in {"pending", "partial"}:
                errors.append(f"{label}.status must be pending or partial")
            components = entry.get("components")
            if not isinstance(components, list):
                errors.append(f"{label}.components must be a list")
            else:
                component_ids: set[str] = set()
                if not components:
                    errors.append(f"{label}.components must not be empty")
                for component_index, component in enumerate(components):
                    component_label = f"{label}.components[{component_index}]"
                    if not isinstance(component, dict):
                        errors.append(f"{component_label} must be a mapping")
                        continue
                    component_id = component.get("component_id")
                    if not isinstance(component_id, str) or not component_id:
                        errors.append(f"{component_label}.component_id must be a non-empty string")
                    elif component_id in component_ids:
                        errors.append(
                            f"duplicate component_id in {settlement_id or label}: {component_id}"
                        )
                    else:
                        component_ids.add(component_id)
                    if component.get("kind") not in component_kinds:
                        errors.append(f"{component_label}.kind is invalid")
                    if component.get("state") not in pending_component_states:
                        errors.append(f"{component_label}.state is invalid for a pending reward")
                    if component.get("legacy_migration"):
                        continue
                    detail = component.get("detail")
                    if not isinstance(detail, dict):
                        errors.append(f"{component_label}.detail must be a mapping")
                        continue
                    kind = component.get("kind")
                    if kind == "gold":
                        amount = detail.get("amount")
                        if not _is_integer(amount) or amount < 1:
                            errors.append(f"{component_label}.detail.amount must be an integer >= 1")
                    elif kind == "item":
                        if not isinstance(detail.get("item_name"), str) or not detail.get("item_name"):
                            errors.append(
                                f"{component_label}.detail.item_name must be a non-empty string"
                            )
                        quantity = detail.get("quantity")
                        if not _is_integer(quantity) or quantity < 1:
                            errors.append(
                                f"{component_label}.detail.quantity must be an integer >= 1"
                            )
                    elif kind in {"right", "service", "favor", "referral", "information"}:
                        delivery_target = detail.get("delivery_target")
                        if delivery_target not in REWARD_EFFECT_TARGETS.get(str(kind), set()):
                            errors.append(f"{component_label}.detail.delivery_target is invalid")
                        elif delivery_target == "world_state.entitlements":
                            for key in ("entitlement_id", "name", "issuer"):
                                if not isinstance(detail.get(key), str) or not detail.get(key):
                                    errors.append(
                                        f"{component_label}.detail.{key} must be a non-empty string"
                                    )
                            if not isinstance(detail.get("scope"), str):
                                errors.append(f"{component_label}.detail.scope must be a string")
                            if not isinstance(detail.get("conditions"), list):
                                errors.append(f"{component_label}.detail.conditions must be a list")
                            uses = detail.get("uses_remaining")
                            if uses is not None and (not _is_integer(uses) or uses < 1):
                                errors.append(
                                    f"{component_label}.detail.uses_remaining must be null or "
                                    "an integer >= 1"
                                )
                            expires = detail.get("expires")
                            if expires is not None and not isinstance(expires, str):
                                errors.append(
                                    f"{component_label}.detail.expires must be null or a string"
                                )
                        elif delivery_target == "session_log":
                            if not isinstance(detail.get("summary"), str) or not detail.get("summary"):
                                errors.append(
                                    f"{component_label}.detail.summary must be a non-empty string"
                                )
                if isinstance(settlement_id, str) and settlement_id:
                    pending_by_settlement[settlement_id] = component_ids
            delivered = entry.get("delivered_component_ids", [])
            if not isinstance(delivered, list) or not all(isinstance(item, str) for item in delivered):
                errors.append(f"{label}.delivered_component_ids must be a list of strings")
            elif len(delivered) != len(set(delivered)):
                errors.append(f"{label}.delivered_component_ids must be unique")
            else:
                delivered_set = set(delivered)
                if delivered_set & pending_by_settlement.get(str(settlement_id), set()):
                    errors.append(f"{label}.delivered_component_ids overlap pending components")
                if isinstance(settlement_id, str) and settlement_id:
                    delivered_mirrors[settlement_id] = delivered_set
            claim_routes = entry.get("claim_routes", [])
            if not isinstance(claim_routes, list) or not all(
                isinstance(item, str) for item in claim_routes
            ):
                errors.append(f"{label}.claim_routes must be a list of strings")

    ledger_by_settlement: dict[str, dict[str, dict]] = {}
    ledger_status: dict[str, str] = {}
    ledger = world_state.get("reward_ledger")
    if ledger is not None and not isinstance(ledger, list):
        errors.append("world_state.reward_ledger must be a list when present")
    elif isinstance(ledger, list):
        settlement_ids: set[str] = set()
        terminal_states = {"delivered", "declined", "forfeited"}
        for index, entry in enumerate(ledger):
            label = f"world_state.reward_ledger[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be a mapping")
                continue
            settlement_id = entry.get("settlement_id")
            if not isinstance(settlement_id, str) or not settlement_id:
                errors.append(f"{label}.settlement_id must be a non-empty string")
                settlement_key = label
            elif settlement_id in settlement_ids:
                errors.append(f"duplicate reward ledger settlement_id: {settlement_id}")
                settlement_key = settlement_id
            else:
                settlement_ids.add(settlement_id)
                settlement_key = settlement_id
            status = entry.get("status")
            if status not in {"partial", "settled", "declined", "forfeited"}:
                errors.append(f"{label}.status is invalid")
            random_event_settlement = isinstance(settlement_id, str) and settlement_id.startswith("EVR-")
            if random_event_settlement:
                source = entry.get("source")
                if not isinstance(source, dict) or source.get("kind") != "random_event":
                    errors.append(f"{label}.source.kind must be random_event for EVR settlements")
                if status == "partial":
                    errors.append(f"{label}.status cannot be partial for an immediate random event")
            components = entry.get("components")
            component_records: dict[str, dict] = {}
            event_estimated_total = 0
            if not isinstance(components, list):
                errors.append(f"{label}.components must be a list")
            else:
                if not components:
                    errors.append(f"{label}.components must not be empty")
                for component_index, component in enumerate(components):
                    component_label = f"{label}.components[{component_index}]"
                    if not isinstance(component, dict):
                        errors.append(f"{component_label} must be a mapping")
                        continue
                    component_id = component.get("component_id")
                    if not isinstance(component_id, str) or not component_id:
                        errors.append(f"{component_label}.component_id must be a non-empty string")
                    elif component_id in component_records:
                        errors.append(
                            f"duplicate ledger component_id in {settlement_id or label}: {component_id}"
                        )
                    else:
                        component_records[component_id] = component
                    kind = component.get("kind")
                    state = component.get("state")
                    if kind not in ledger_component_kinds:
                        errors.append(f"{component_label}.kind is invalid")
                    if state not in terminal_states:
                        errors.append(f"{component_label}.state is invalid for the reward ledger")
                    transaction_id = component.get("transaction_id")
                    if not isinstance(transaction_id, str) or not transaction_id:
                        errors.append(f"{component_label}.transaction_id must be a non-empty string")
                    else:
                        try:
                            safe_id(transaction_id)
                        except RuntimeProblem as exc:
                            errors.append(f"{component_label}.transaction_id: {exc}")
                    if random_event_settlement:
                        estimated_value = component.get("estimated_value_g")
                        if not _is_integer(estimated_value) or not 0 <= estimated_value <= 100:
                            errors.append(
                                f"{component_label}.estimated_value_g must be an integer in 0..100"
                            )
                        else:
                            event_estimated_total += estimated_value
                    effect = component.get("effect")
                    if state == "delivered":
                        if not isinstance(effect, dict):
                            errors.append(f"{component_label}.effect must describe the delivered change")
                        else:
                            target = effect.get("target")
                            if target not in REWARD_EFFECT_TARGETS.get(str(kind), set()):
                                errors.append(f"{component_label}.effect.target is invalid for {kind}")
                            for key in ("before_sha256", "after_sha256"):
                                if not isinstance(effect.get(key), str) or not effect.get(key):
                                    errors.append(f"{component_label}.effect.{key} must be a non-empty string")
                            if kind == "gold" and not component.get("legacy_migration"):
                                amount = effect.get("amount")
                                if not _is_integer(amount) or amount < 1:
                                    errors.append(f"{component_label}.effect.amount must be an integer >= 1")
                            if kind == "item" and not component.get("legacy_migration"):
                                if not isinstance(effect.get("item_name"), str) or not effect.get("item_name"):
                                    errors.append(
                                        f"{component_label}.effect.item_name must be a non-empty string"
                                    )
                                quantity = effect.get("quantity")
                                if not _is_integer(quantity) or quantity < 1:
                                    errors.append(
                                        f"{component_label}.effect.quantity must be an integer >= 1"
                                    )
                            if target == "world_state.entitlements":
                                entitlement_id = effect.get("entitlement_id")
                                if not isinstance(entitlement_id, str) or not entitlement_id:
                                    errors.append(
                                        f"{component_label}.effect.entitlement_id must be a non-empty string"
                                    )
                            if target == "session_log" and not component.get("legacy_migration"):
                                index = effect.get("log_entry_index")
                                if not _is_integer(index) or index < 0:
                                    errors.append(
                                        f"{component_label}.effect.log_entry_index must be an integer >= 0"
                                    )
                                if not isinstance(effect.get("log_entry_sha256"), str) or not effect.get(
                                    "log_entry_sha256"
                                ):
                                    errors.append(
                                        f"{component_label}.effect.log_entry_sha256 must be non-empty"
                                    )
                            if random_event_settlement and kind == "gold":
                                estimated_value = component.get("estimated_value_g")
                                if effect.get("amount") != estimated_value:
                                    errors.append(
                                        f"{component_label}.effect.amount must equal estimated_value_g "
                                        "for a random event"
                                    )
                    elif state in {"declined", "forfeited"} and effect is not None:
                        errors.append(f"{component_label}.effect must be null when nothing is delivered")
                states = {
                    item.get("state") for item in components if isinstance(item, dict)
                }
                if status == "declined" and states != {"declined"}:
                    errors.append(f"{label}.status declined requires only declined components")
                if status == "forfeited" and states != {"forfeited"}:
                    errors.append(f"{label}.status forfeited requires only forfeited components")
                if random_event_settlement and event_estimated_total > 100:
                    errors.append(f"{label} exceeds the 100G-equivalent random-event cap")
            if isinstance(settlement_id, str) and settlement_id and settlement_id not in ledger_by_settlement:
                ledger_by_settlement[settlement_id] = component_records
                if isinstance(status, str):
                    ledger_status[settlement_id] = status

    for settlement_id, pending_ids in pending_by_settlement.items():
        ledger_components = ledger_by_settlement.get(settlement_id, {})
        overlap = pending_ids & set(ledger_components)
        if overlap:
            errors.append(
                f"pending and terminal reward components overlap in {settlement_id}: {sorted(overlap)}"
            )
        pending_entry_status = next(
            (entry.get("status") for entry in pending or []
             if isinstance(entry, dict) and entry.get("settlement_id") == settlement_id),
            None,
        )
        if ledger_components and pending_entry_status != "partial":
            errors.append(f"pending reward {settlement_id} with ledger history must have status partial")
        if not ledger_components and pending_entry_status == "partial":
            errors.append(f"partial pending reward {settlement_id} lacks reward ledger history")
        if ledger_status.get(settlement_id) in {"settled", "declined", "forfeited"}:
            errors.append(f"terminal reward ledger {settlement_id} cannot also be pending")
        for component_id in delivered_mirrors.get(settlement_id, set()):
            record = ledger_components.get(component_id)
            if not record or record.get("state") != "delivered":
                errors.append(
                    f"delivered_component_id {settlement_id}/{component_id} has no delivered ledger record"
                )

    if event_contract_id and event_contract_id in ledger_by_settlement:
        errors.append(
            f"settled event_reward_contract must be cleared: {event_contract_id}"
        )

    entitlement_by_id: dict[str, dict] = {}
    entitlements = world_state.get("entitlements")
    if entitlements is not None and not isinstance(entitlements, list):
        errors.append("world_state.entitlements must be a list when present")
    elif isinstance(entitlements, list):
        entitlement_ids: set[str] = set()
        source_pairs: set[tuple[str, str]] = set()
        entitlement_kinds = {
            "right", "service", "favor", "referral", "information", "discount", "access",
        }
        source_kind_map = {
            "right": "right", "discount": "right", "access": "right",
            "service": "service", "favor": "favor", "referral": "referral",
            "information": "information",
        }
        for index, entry in enumerate(entitlements):
            label = f"world_state.entitlements[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be a mapping")
                continue
            entitlement_id = entry.get("entitlement_id")
            if not isinstance(entitlement_id, str) or not entitlement_id:
                errors.append(f"{label}.entitlement_id must be a non-empty string")
            elif entitlement_id in entitlement_ids:
                errors.append(f"duplicate entitlement_id: {entitlement_id}")
            else:
                entitlement_ids.add(entitlement_id)
                entitlement_by_id[entitlement_id] = entry
            source_settlement_id = entry.get("source_settlement_id")
            source_component_id = entry.get("source_component_id")
            for key, value in (
                ("source_settlement_id", source_settlement_id),
                ("source_component_id", source_component_id),
            ):
                if not isinstance(value, str) or not value:
                    errors.append(f"{label}.{key} must be a non-empty string")
            if isinstance(source_settlement_id, str) and source_settlement_id and isinstance(
                source_component_id, str
            ) and source_component_id:
                source_pair = (source_settlement_id, source_component_id)
                if source_pair in source_pairs:
                    errors.append(
                        f"duplicate entitlement reward source: {source_settlement_id}/{source_component_id}"
                    )
                else:
                    source_pairs.add(source_pair)
                source_record = ledger_by_settlement.get(source_settlement_id, {}).get(
                    source_component_id
                )
                if not source_record or source_record.get("state") != "delivered":
                    errors.append(
                        f"{label} source has no delivered reward ledger component: "
                        f"{source_settlement_id}/{source_component_id}"
                    )
                elif source_record.get("kind") != source_kind_map.get(entry.get("kind")):
                    errors.append(f"{label}.kind does not match its reward ledger component")
                elif not source_record.get("legacy_migration") and (
                    not isinstance(source_record.get("effect"), dict) or
                    source_record["effect"].get("target") != "world_state.entitlements"
                ):
                    errors.append(f"{label} cannot attach an entitlement to an immediate reward effect")
            if entry.get("kind") not in entitlement_kinds:
                errors.append(f"{label}.kind is invalid")
            for key in ("name", "issuer"):
                if not isinstance(entry.get(key), str) or not entry.get(key):
                    errors.append(f"{label}.{key} must be a non-empty string")
            if entry.get("status") not in {"active", "used", "expired", "revoked"}:
                errors.append(f"{label}.status is invalid")
            uses = entry.get("uses_remaining")
            if uses is not None and (not _is_integer(uses) or uses < 0):
                errors.append(f"{label}.uses_remaining must be null or an integer >= 0")
            expires = entry.get("expires")
            if expires is not None and not isinstance(expires, str):
                errors.append(f"{label}.expires must be null or a string")
            if entry.get("status") == "active" and _is_integer(uses) and uses == 0:
                errors.append(f"{label}.status active cannot have zero uses_remaining")
            if entry.get("status") == "used" and _is_integer(uses) and uses != 0:
                errors.append(f"{label}.status used requires uses_remaining 0 when counted")
            conditions = entry.get("conditions", [])
            if not isinstance(conditions, list):
                errors.append(f"{label}.conditions must be a list")

    quest_card = world_state.get("quest_card")
    if quest_card is not None:
        if not isinstance(quest_card, dict):
            errors.append("world_state.quest_card must be null or a mapping")
        else:
            _validate_standard_reward_contract(
                quest_card.get("reward_contract"),
                "world_state.quest_card.reward_contract", errors, entitlement_by_id,
            )
            _validate_active_contract_receipts(
                quest_card.get("reward_contract"), ledger_by_settlement, ledger_status,
                "world_state.quest_card", errors,
            )

    for settlement_id, components in ledger_by_settlement.items():
        for component_id, component in components.items():
            if component.get("legacy_migration"):
                continue
            effect = component.get("effect")
            if not isinstance(effect, dict) or effect.get("target") != "world_state.entitlements":
                continue
            entitlement = entitlement_by_id.get(effect.get("entitlement_id"))
            if not entitlement:
                errors.append(
                    f"reward ledger effect entitlement is missing: {settlement_id}/{component_id}"
                )
            elif (entitlement.get("source_settlement_id"),
                  entitlement.get("source_component_id")) != (settlement_id, component_id):
                errors.append(
                    f"reward ledger effect entitlement source mismatch: {settlement_id}/{component_id}"
                )


def _rank_at_least_c(world_state: Any) -> bool:
    """Recognize explicit C/B/A rank markers; D quest count alone is not promotion."""
    if not isinstance(world_state, dict):
        return False
    for key in ("personal_rank", "quest_access"):
        value = str(world_state.get(key) or "").strip().upper()
        if re.search(r"(?:^|[^A-Z])(?:A|B|C)(?:級|ランク|RANK|$)", value):
            return True
    return False


def _fixed_tape_value(kind: str, cursor: int) -> int | None:
    try:
        data = json.loads((HERE / "dice_tape.json").read_text(encoding="utf-8"))
        if data.get("revision") != TAPE_REVISION:
            return None
        tape = data.get("tapes", {}).get(kind)
        if not isinstance(tape, list) or not 0 <= cursor < len(tape):
            return None
        value = tape[cursor]
        return value if _is_integer(value) else None
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


FRUIT_ITEM_BY_D10 = {
    1: "STRの実", 2: "STRの実",
    3: "DEFの実", 4: "DEFの実",
    5: "SPDの実", 6: "TECの実", 7: "CHMの実",
    8: "INTの実", 9: "LPの実", 10: "選べる能力の実",
}
ABILITY_FRUIT_ITEMS = frozenset({*FRUIT_ITEM_BY_D10.values(), "能力の実"})
MIMIC_FRUIT_SOURCE_ID = "dungeon-8f-special-mimic-001"


def _growth_resolution_item_counts(resolution: Any) -> dict[str, int] | None:
    """Return normalized item counts, or None when the entry is not well formed."""
    if not isinstance(resolution, dict) or not isinstance(resolution.get("items"), list):
        return None
    counts: dict[str, int] = {}
    for item in resolution["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not item["name"] or not _is_integer(item.get("count"))
                or item["count"] < 1):
            return None
        counts[item["name"]] = counts.get(item["name"], 0) + item["count"]
    return counts


def _fruit_counts_from_type_rolls(rolls: Any) -> dict[str, int] | None:
    """Map canonical d10 type rolls to the exact fruit inventory delta."""
    if not isinstance(rolls, list):
        return None
    counts: dict[str, int] = {}
    for roll in rolls:
        if not isinstance(roll, dict) or roll.get("die") != "d10":
            return None
        result = roll.get("result")
        item_name = FRUIT_ITEM_BY_D10.get(result) if _is_integer(result) else None
        if item_name is None:
            return None
        counts[item_name] = counts.get(item_name, 0) + 1
    return counts


def _validate_growth_state(data: dict, world_state: dict, errors: list[str]) -> None:
    growth = world_state.get("growth_state")
    if not isinstance(growth, dict):
        errors.append("world_state.growth_state must be a mapping; migrate older saves first")
        return
    if growth.get("version") != 1:
        errors.append("world_state.growth_state.version must be 1")
    streak = growth.get("boss_fruit_miss_streak")
    if not _is_integer(streak) or not 0 <= streak <= 3:
        errors.append("world_state.growth_state.boss_fruit_miss_streak must be an integer in 0..3")
    status = growth.get("c_rank_choice_fruit_status")
    if status not in {"locked", "pending", "granted"}:
        errors.append("world_state.growth_state.c_rank_choice_fruit_status is invalid")
    rank_c_or_higher = _rank_at_least_c(world_state)
    if rank_c_or_higher and status == "locked":
        errors.append("C-rank or higher save requires pending or granted C-rank fruit status")
    if not rank_c_or_higher and status in {"pending", "granted"}:
        errors.append("C-rank fruit status cannot be pending or granted below C rank")
    grant_transaction = growth.get("c_rank_choice_fruit_transaction_id")
    if not isinstance(grant_transaction, str):
        errors.append("world_state.growth_state.c_rank_choice_fruit_transaction_id must be a string")
    elif status == "granted":
        try:
            safe_id(grant_transaction)
        except RuntimeProblem:
            errors.append(
                "world_state.growth_state.c_rank_choice_fruit_transaction_id "
                "must be a non-empty safe id when granted"
            )
    elif grant_transaction:
        errors.append(
            "world_state.growth_state.c_rank_choice_fruit_transaction_id must be empty before grant"
        )

    resolutions = growth.get("resolutions")
    if not isinstance(resolutions, list):
        errors.append("world_state.growth_state.resolutions must be a list")
        return
    resolution_ids: set[str] = set()
    source_keys: set[tuple[str, str]] = set()
    computed_streak = 0
    legacy_sources = growth.get("boss_fruit_legacy_sources", [])
    if not isinstance(legacy_sources, list) or any(not isinstance(x, str) or not re.fullmatch(r"boss-f[1-9]", x) for x in legacy_sources):
        errors.append("boss_fruit_legacy_sources must contain stable boss-fN keys")
        legacy_sources = []
    acquired_boss_sources = set(legacy_sources)
    c_rank_entries: list[dict] = []
    mimic_entries: list[dict] = []
    current_day = world_state.get("day")
    source_types = {"boss", "strong", "chest", "mimic", "c_rank", "quest", "event"}
    for index, resolution in enumerate(resolutions):
        label = f"world_state.growth_state.resolutions[{index}]"
        if not isinstance(resolution, dict):
            errors.append(f"{label} must be a mapping")
            continue
        resolution_id = resolution.get("resolution_id")
        source_type = resolution.get("source_type")
        source_id = resolution.get("source_id")
        for key, value in (("resolution_id", resolution_id), ("source_id", source_id)):
            if not isinstance(value, str):
                errors.append(f"{label}.{key} must be a safe id")
                continue
            try:
                safe_id(value)
            except RuntimeProblem:
                errors.append(f"{label}.{key} must be a safe id")
        if isinstance(resolution_id, str):
            if resolution_id in resolution_ids:
                errors.append(f"duplicate growth resolution_id: {resolution_id}")
            resolution_ids.add(resolution_id)
        if source_type not in source_types:
            errors.append(f"{label}.source_type is invalid")
        if isinstance(source_type, str) and isinstance(source_id, str):
            source_key = (source_type, source_id)
            if source_key in source_keys:
                errors.append(f"duplicate growth source: {source_type}/{source_id}")
            source_keys.add(source_key)
        outcome = resolution.get("outcome")
        if outcome not in {"miss", "awarded"}:
            errors.append(f"{label}.outcome is invalid")
        items = resolution.get("items")
        valid_items = isinstance(items, list)
        if valid_items:
            for item_index, item in enumerate(items):
                if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                        or not item.get("name") or not _is_integer(item.get("count"))
                        or item["count"] < 1):
                    errors.append(
                        f"{label}.items[{item_index}] requires non-empty name and count >= 1"
                    )
                    valid_items = False
        else:
            errors.append(f"{label}.items must be a list")
        if valid_items and outcome == "miss" and items:
            errors.append(f"{label}.items must be empty for a miss")
        elif valid_items and outcome == "awarded" and not items:
            errors.append(f"{label}.items must not be empty when awarded")
        if valid_items and any(
            item.get("name") not in set(FRUIT_ITEM_BY_D10.values()) for item in items
        ):
            errors.append(f"{label}.items may contain only canonical ability fruits")
        rolls = resolution.get("rolls")
        if not isinstance(rolls, list):
            errors.append(f"{label}.rolls must be a list")
        else:
            roll_cursors: dict[str, list[int]] = {"d6": [], "d10": []}
            for roll_index, roll in enumerate(rolls):
                roll_label = f"{label}.rolls[{roll_index}]"
                if not isinstance(roll, dict):
                    errors.append(f"{roll_label} must be a mapping")
                    continue
                die = roll.get("die")
                purpose = roll.get("purpose")
                cursor = roll.get("cursor")
                result = roll.get("result")
                limit = {"d6": 600, "d10": 500}.get(die)
                faces = {"d6": 6, "d10": 10}.get(die)
                if limit is None:
                    errors.append(f"{roll_label}.die must be d6 or d10")
                    continue
                if not isinstance(purpose, str) or not purpose:
                    errors.append(f"{roll_label}.purpose must be a non-empty string")
                if not _is_integer(cursor) or not 0 <= cursor < limit:
                    errors.append(f"{roll_label}.cursor must be in 0..{limit - 1}")
                    continue
                if not _is_integer(result) or not 1 <= result <= faces:
                    errors.append(f"{roll_label}.result must be in 1..{faces}")
                    continue
                expected = _fixed_tape_value(str(die), cursor)
                if expected is None or result != expected:
                    errors.append(f"{roll_label}.result does not match the fixed dice tape")
                roll_cursors[str(die)].append(cursor)
            for die, cursors in roll_cursors.items():
                limit = 600 if die == "d6" else 500
                if len(cursors) != len(set(cursors)):
                    errors.append(f"{label}.{die} cursors must be unique")
                for previous, current in zip(cursors, cursors[1:]):
                    if current != (previous + 1) % limit:
                        errors.append(f"{label}.{die} cursors must be consecutive and ordered")
        day = resolution.get("day")
        if not _is_integer(day) or day < 1:
            errors.append(f"{label}.day must be an integer >= 1")
        elif _is_integer(current_day) and day > current_day:
            errors.append(f"{label}.day cannot be later than world_state.day")
        if source_type == "boss":
            modern = resolution.get("rule_version") == 2
            source_key = resolution.get("source_key")
            if modern and (not isinstance(source_key, str) or not re.fullmatch(r"boss-f[1-9]", source_key)):
                errors.append(f"{label} requires stable boss-fN source_key")
            repeat = modern and source_key in acquired_boss_sources
            rarity_threshold = 9 if repeat else 8
            pity_due = computed_streak == 3 and not repeat
            if pity_due:
                if outcome != "awarded":
                    errors.append(f"{label} must award one fruit after three boss misses")
                if not isinstance(rolls, list) or len(rolls) != 1:
                    errors.append(
                        f"{label} pity award must consume only one d10 fruit-type roll"
                    )
                type_rolls = rolls if isinstance(rolls, list) and len(rolls) == 1 else None
            else:
                expected_roll_count = 2 if outcome == "awarded" else 1
                if not isinstance(rolls, list) or len(rolls) != expected_roll_count:
                    errors.append(
                        f"{label} normal boss resolution requires one rarity d10"
                        + (" and one fruit-type d10" if outcome == "awarded" else "")
                    )
                    type_rolls = None
                else:
                    rarity = rolls[0]
                    rarity_result = rarity.get("result") if isinstance(rarity, dict) else None
                    if not isinstance(rarity, dict) or rarity.get("die") != "d10":
                        errors.append(f"{label} first roll must be the boss rarity d10")
                    elif outcome == "awarded" and (not _is_integer(rarity_result)
                                                    or rarity_result < rarity_threshold):
                        errors.append(f"{label} boss award requires rarity d10 >= {rarity_threshold}")
                    elif outcome == "miss" and (not _is_integer(rarity_result)
                                                or rarity_result >= rarity_threshold):
                        errors.append(f"{label} boss miss requires rarity d10 < {rarity_threshold}")
                    type_rolls = rolls[1:] if outcome == "awarded" else []
            if outcome == "awarded":
                expected_counts = _fruit_counts_from_type_rolls(type_rolls)
                actual_counts = _growth_resolution_item_counts(resolution)
                if expected_counts is None or actual_counts != expected_counts:
                    errors.append(
                        f"{label} must award exactly the one fruit selected by its type d10"
                    )
                if not repeat:
                    computed_streak = 0
                if modern:
                    acquired_boss_sources.add(source_key)
            elif not pity_due and not repeat:
                computed_streak += 1
        elif source_type == "strong":
            expected_roll_count = 2 if outcome == "awarded" else 1
            type_rolls = None
            if not isinstance(rolls, list) or len(rolls) != expected_roll_count:
                errors.append(
                    f"{label} strong resolution requires one rarity d10"
                    + (" and one fruit-type d10" if outcome == "awarded" else "")
                )
            else:
                rarity = rolls[0]
                rarity_result = rarity.get("result") if isinstance(rarity, dict) else None
                if not isinstance(rarity, dict) or rarity.get("die") != "d10":
                    errors.append(f"{label} first roll must be the strong rarity d10")
                elif outcome == "awarded" and rarity_result != 10:
                    errors.append(f"{label} strong award requires rarity d10 result 10")
                elif outcome == "miss" and rarity_result == 10:
                    errors.append(f"{label} strong d10 result 10 cannot be recorded as a miss")
                type_rolls = rolls[1:] if outcome == "awarded" else []
            if outcome == "awarded":
                expected_counts = _fruit_counts_from_type_rolls(type_rolls)
                actual_counts = _growth_resolution_item_counts(resolution)
                if expected_counts is None or actual_counts != expected_counts:
                    errors.append(
                        f"{label} must award exactly the one fruit selected by its type d10"
                    )
        elif source_type == "mimic":
            mimic_entries.append(resolution)
            if source_id != MIMIC_FRUIT_SOURCE_ID:
                errors.append(
                    f"{label}.source_id must be {MIMIC_FRUIT_SOURCE_ID}"
                )
            if outcome != "awarded":
                errors.append(f"{label} 8F mimic fruit drop is guaranteed")
            if not isinstance(rolls, list) or len(rolls) != 2:
                errors.append(
                    f"{label} mimic award consumes exactly two fruit-type d10 rolls"
                )
            expected_counts = _fruit_counts_from_type_rolls(rolls)
            actual_counts = _growth_resolution_item_counts(resolution)
            if expected_counts is None or actual_counts != expected_counts:
                errors.append(
                    f"{label} must award exactly the two fruits selected by its type d10 rolls"
                )
        elif source_type == "chest":
            if resolution.get("rule_version") == 2:
                floor = resolution.get("floor")
                if not _is_integer(floor) or not 1 <= floor <= 9:
                    errors.append(f"{label} chest requires floor 1..9")
                elif isinstance(rolls, list) and rolls and isinstance(rolls[0], dict):
                    tier = rolls[0].get("result")
                    secondary_due = floor >= 3 and tier in {5, 6}
                    fruit_due = secondary_due and len(rolls) >= 2 and isinstance(rolls[1], dict) and rolls[1].get("result") in {1, 2}
                    expected_award_count = (2 if floor >= 5 and tier == 6 else 1) if fruit_due else 0
                    if (outcome == "awarded") != bool(expected_award_count):
                        errors.append(f"{label} chest outcome must match its floor and secondary roll")
                    expected_rolls = 1 + int(secondary_due) + expected_award_count
                    if len(rolls) != expected_rolls:
                        errors.append(f"{label} chest must consume tier, applicable secondary, and exact fruit-type rolls")
            if outcome == "awarded":
                if not isinstance(rolls, list) or len(rolls) not in {3, 4}:
                    errors.append(
                        f"{label} chest award requires d6, secondary d10, and fruit-type d10 roll(s)"
                    )
                    type_rolls = None
                else:
                    tier_roll, secondary_roll = rolls[0], rolls[1]
                    tier_result = tier_roll.get("result") if isinstance(tier_roll, dict) else None
                    if (not isinstance(tier_roll, dict) or tier_roll.get("die") != "d6"
                            or tier_result not in {5, 6}):
                        errors.append(f"{label} chest award requires a d6 result of 5 or 6")
                    if (not isinstance(secondary_roll, dict)
                            or secondary_roll.get("die") != "d10"
                            or secondary_roll.get("result") not in {1, 2}):
                        errors.append(f"{label} chest fruit secondary d10 must be 1 or 2")
                    if len(rolls) == 4 and tier_result != 6:
                        errors.append(f"{label} two-fruit chest award requires jackpot d6 result 6")
                    type_rolls = rolls[2:]
                expected_counts = _fruit_counts_from_type_rolls(type_rolls)
                actual_counts = _growth_resolution_item_counts(resolution)
                if expected_counts is None or actual_counts != expected_counts:
                    errors.append(
                        f"{label} must award exactly the fruit(s) selected by its type d10 rolls"
                    )
            elif isinstance(rolls, list):
                if len(rolls) not in {1, 2} or not isinstance(rolls[0], dict) \
                        or rolls[0].get("die") != "d6":
                    errors.append(f"{label} chest miss requires its tier d6 and optional secondary d10")
                elif len(rolls) == 2 and (
                    not isinstance(rolls[1], dict) or rolls[1].get("die") != "d10"
                ):
                    errors.append(f"{label} chest secondary roll must be d10")
        elif source_type in {"quest", "event"} and outcome == "awarded":
            if not isinstance(rolls, list) or len(rolls) not in {1, 2}:
                errors.append(
                    f"{label} quest/event award requires one fruit-type d10"
                    " and at most one preceding frequency d10"
                )
                type_rolls = None
            else:
                if len(rolls) == 2 and (
                    not isinstance(rolls[0], dict) or rolls[0].get("die") != "d10"
                    or rolls[0].get("result") != 10
                ):
                    errors.append(f"{label} preceding quest/event frequency d10 must be 10")
                type_rolls = rolls[-1:]
            expected_counts = _fruit_counts_from_type_rolls(type_rolls)
            actual_counts = _growth_resolution_item_counts(resolution)
            if expected_counts is None or actual_counts != expected_counts:
                errors.append(
                    f"{label} must award exactly one fruit selected by its type d10"
                )
        if source_type == "c_rank":
            c_rank_entries.append(resolution)
            if rolls != []:
                errors.append(f"{label}.rolls must be empty for the guaranteed C-rank grant")
            if outcome != "awarded" or items != [{"name": "選べる能力の実", "count": 1}]:
                errors.append(f"{label} must award exactly one 選べる能力の実")
    if _is_integer(streak) and streak != computed_streak:
        errors.append("world_state.growth_state.boss_fruit_miss_streak does not match resolutions")
    if len(c_rank_entries) > 1:
        errors.append("world_state.growth_state may contain at most one C-rank grant")
    if len(mimic_entries) > 1:
        errors.append("world_state.growth_state may contain at most one 8F mimic fruit award")
    if status == "granted" and len(c_rank_entries) != 1:
        errors.append("granted C-rank fruit status requires one c_rank resolution")
    if status in {"locked", "pending"} and c_rank_entries:
        errors.append("ungranted C-rank fruit status cannot have a c_rank resolution")


def _validate_expedition_state(data: dict, world_state: dict, errors: list[str]) -> None:
    expedition = world_state.get("expedition_state")
    if not isinstance(expedition, dict):
        errors.append("world_state.expedition_state must be a mapping; migrate older saves first")
        return
    required = (
        "active", "expedition_id", "kind", "fire_holders", "separated_fire_holders",
        "rebirth_pending", "last_end_reason", "last_ended_expedition_id", "rebirth_receipt",
    )
    for key in required:
        if key not in expedition:
            errors.append(f"world_state.expedition_state.{key} is required; migrate older saves first")
    active = expedition.get("active")
    if not isinstance(active, bool):
        errors.append("world_state.expedition_state.active must be a boolean")
    expedition_id = expedition.get("expedition_id")
    if not isinstance(expedition_id, str):
        errors.append("world_state.expedition_state.expedition_id must be a string")
    kind = expedition.get("kind")
    if kind not in {"none", "dungeon", "quest", "travel", "other"}:
        errors.append("world_state.expedition_state.kind is invalid")
    holders = expedition.get("fire_holders")
    separated = expedition.get("separated_fire_holders")
    rebirth_pending = expedition.get("rebirth_pending")
    if not isinstance(rebirth_pending, bool):
        errors.append("world_state.expedition_state.rebirth_pending must be a boolean")
    for key, values in (("fire_holders", holders), ("separated_fire_holders", separated)):
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in (values or [])
        ) or len(values or []) != len(set(values or [])):
            errors.append(
                f"world_state.expedition_state.{key} must be a unique list of non-empty strings"
            )
    def resolved_reference(value: str) -> tuple[str, object]:
        member = _expedition_member(data, value)
        return ("actor", id(member)) if member is not None else ("unresolved", value)

    if isinstance(holders, list) and isinstance(separated, list):
        holder_refs = {resolved_reference(value) for value in holders if isinstance(value, str)}
        separated_refs = {resolved_reference(value) for value in separated if isinstance(value, str)}
        if not separated_refs <= holder_refs:
            errors.append("expedition_state.separated_fire_holders must be a subset of fire_holders")
        if len(holder_refs) != len(holders):
            errors.append("expedition_state.fire_holders may not name the same actor more than once")
        if len(separated_refs) != len(separated):
            errors.append("expedition_state.separated_fire_holders may not name the same actor more than once")
    fire_state = data.get("fire_state")
    current_holders = fire_state.get("holders") if isinstance(fire_state, dict) else None
    if isinstance(holders, list) and isinstance(current_holders, list):
        if not {resolved_reference(value) for value in holders if isinstance(value, str)} <= {
            resolved_reference(value) for value in current_holders if isinstance(value, str)
        }:
            errors.append("expedition_state.fire_holders must be current fire_state.holders")
    if active is True and isinstance(holders, list):
        holder_meters: list[tuple[int, int] | None] = []
        for holder_name in holders:
            member = _expedition_member(data, holder_name) if isinstance(holder_name, str) else None
            if isinstance(holder_name, str) and member is None:
                errors.append(
                    f"expedition fire_holder must resolve to player or party member: {holder_name}"
                )
            holder_meters.append(_member_meter(member, "lp"))
        all_down = bool(holder_meters) and all(
            meter is not None and meter[0] == 0 for meter in holder_meters
        )
        if isinstance(rebirth_pending, bool) and rebirth_pending != all_down:
            errors.append(
                "active expedition rebirth_pending must be true exactly when all fire holders are LP0"
            )
    end_reason = expedition.get("last_end_reason")
    ended_id = expedition.get("last_ended_expedition_id")
    receipt = expedition.get("rebirth_receipt")
    if end_reason not in {"none", "return", "rebirth", "completed"}:
        errors.append("world_state.expedition_state.last_end_reason is invalid")
    if not isinstance(ended_id, str):
        errors.append("world_state.expedition_state.last_ended_expedition_id must be a string")
    elif end_reason == "none" and ended_id:
        errors.append("last_ended_expedition_id must be empty when last_end_reason is none")
    elif end_reason != "none":
        try:
            safe_id(ended_id)
        except RuntimeProblem:
            errors.append("last_ended_expedition_id must be a safe id after expedition end")
    if end_reason == "rebirth":
        if not isinstance(receipt, dict):
            errors.append("rebirth expedition end requires a rebirth_receipt")
        else:
            receipt_id = receipt.get("expedition_id")
            if receipt_id != ended_id:
                errors.append("rebirth_receipt.expedition_id must match the ended expedition")
            receipt_holders = receipt.get("fire_holders")
            if not isinstance(receipt_holders, list) or not receipt_holders:
                errors.append("rebirth_receipt.fire_holders must be a non-empty list")
            else:
                receipt_refs: list[tuple[str, object]] = []
                for index, member in enumerate(receipt_holders):
                    if (not isinstance(member, dict)
                            or not isinstance(member.get("name"), str)
                            or not member["name"] or not _is_integer(member.get("lp_at_trigger"))
                            or member.get("lp_at_trigger") != 0
                            or ("character_id" in member and (
                                not isinstance(member["character_id"], str) or not member["character_id"]))):
                        errors.append(
                            f"rebirth_receipt.fire_holders[{index}] requires name and lp_at_trigger=0"
                        )
                        continue
                    reference = member.get("character_id") or member["name"]
                    actor = _expedition_member(data, reference)
                    # Historical receipts survive later departures; live actor
                    # resolution is used only when it remains available.
                    receipt_refs.append(("actor", id(actor)) if actor is not None else (
                        "id" if member.get("character_id") else "name", reference))
                if len(receipt_refs) != len(set(receipt_refs)):
                    errors.append("rebirth_receipt fire holder identities must be unique")
    elif receipt is not None:
        errors.append("rebirth_receipt must be null unless last_end_reason is rebirth")
    if active is False:
        expected = {
            "expedition_id": "", "kind": "none", "fire_holders": [],
            "separated_fire_holders": [], "rebirth_pending": False,
        }
        for key, value in expected.items():
            if expedition.get(key) != value:
                errors.append(f"inactive expedition_state requires {key}={value!r}")
    elif active is True:
        try:
            safe_id(expedition_id if isinstance(expedition_id, str) else "")
        except RuntimeProblem:
            errors.append("active expedition_state.expedition_id must be a non-empty safe id")
        if kind == "none":
            errors.append("active expedition_state.kind cannot be none")
        if not isinstance(holders, list) or not holders:
            errors.append("active expedition_state requires at least one fire_holder")
        if end_reason != "none" or ended_id != "":
            errors.append("active expedition_state must clear its last end marker")


def _validate_dungeon_state(data: dict, world_state: dict, errors: list[str]) -> None:
    deepest = world_state.get("deepest_depth_reached")
    if not _is_integer(deepest) or not 0 <= deepest <= 9:
        errors.append("world_state.deepest_depth_reached must be an integer in 0..9")
    defeated = world_state.get("defeated_floor_bosses")
    if not isinstance(defeated, list) or not all(
        _is_integer(floor) and 1 <= floor <= 9 for floor in (defeated or [])
    ):
        errors.append("world_state.defeated_floor_bosses must contain floor integers in 1..9")
        defeated_floors: list[int] = []
    else:
        defeated_floors = defeated
        if len(defeated_floors) != len(set(defeated_floors)):
            errors.append("world_state.defeated_floor_bosses must be unique")
        if _is_integer(deepest) and defeated_floors and max(defeated_floors) > deepest:
            errors.append("defeated floor boss cannot be deeper than deepest_depth_reached")

    records = world_state.get("boss_records")
    record_floors: set[int] = set()
    records_by_floor: dict[int, dict] = {}
    boss_ids: set[str] = set()
    defeat_ids: set[str] = set()
    if not isinstance(records, list):
        errors.append("world_state.boss_records must be a list")
    else:
        for index, record in enumerate(records):
            label = f"world_state.boss_records[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{label} must be a mapping")
                continue
            boss_id = record.get("boss_id")
            last_defeat_id = record.get("last_defeat_id")
            for key, value, seen in (
                ("boss_id", boss_id, boss_ids),
                ("last_defeat_id", last_defeat_id, defeat_ids),
            ):
                if not isinstance(value, str):
                    errors.append(f"{label}.{key} must be a safe id")
                    continue
                try:
                    safe_id(value)
                except RuntimeProblem:
                    errors.append(f"{label}.{key} must be a safe id")
                if value in seen:
                    errors.append(f"duplicate {key}: {value}")
                seen.add(value)
            defeated_expedition_id = record.get("last_defeated_expedition_id")
            if not isinstance(defeated_expedition_id, str):
                errors.append(f"{label}.last_defeated_expedition_id must be a safe id")
            else:
                try:
                    safe_id(defeated_expedition_id)
                except RuntimeProblem:
                    errors.append(f"{label}.last_defeated_expedition_id must be a safe id")
            floor = record.get("floor")
            if not _is_integer(floor) or not 1 <= floor <= 9:
                errors.append(f"{label}.floor must be an integer in 1..9")
                continue
            if floor in record_floors:
                errors.append(f"duplicate boss record floor: {floor}")
            record_floors.add(floor)
            records_by_floor[floor] = record
            first_day = record.get("first_defeated_day")
            last_day = record.get("last_defeated_day")
            if not _is_integer(first_day) or first_day < 1:
                errors.append(f"{label}.first_defeated_day must be an integer >= 1")
            if not _is_integer(last_day) or last_day < 1:
                errors.append(f"{label}.last_defeated_day must be an integer >= 1")
            elif _is_integer(first_day) and last_day < first_day:
                errors.append(f"{label}.last_defeated_day cannot precede first_defeated_day")
            elif _is_integer(world_state.get("day")) and last_day > world_state["day"]:
                errors.append(f"{label}.last_defeated_day cannot be in the future")
            rematch_day = record.get("rematch_available_day")
            if not _is_integer(rematch_day) or rematch_day != last_day:
                errors.append(f"{label}.rematch_available_day must equal last defeat day; reentry revives the boss")
        if set(defeated_floors) != record_floors:
            errors.append("defeated_floor_bosses must match the floors in boss_records")

    run = world_state.get("dungeon_run")
    if not isinstance(run, dict):
        errors.append("world_state.dungeon_run must be a mapping; migrate older saves first")
        return
    required = (
        "active", "run_id", "trash_encounters_used", "danger_zones_resolved",
        "last_scene_kind", "event_due", "used_event_ids", "current_floor",
        "current_floor_scenes", "reward_searches_by_floor", "camp_used",
        "boss_route_found",
    )
    for key in required:
        if key not in run:
            errors.append(f"world_state.dungeon_run.{key} is required; migrate older saves first")
    active = run.get("active")
    if not isinstance(active, bool):
        errors.append("world_state.dungeon_run.active must be a boolean")
    run_id = run.get("run_id")
    if not isinstance(run_id, str):
        errors.append("world_state.dungeon_run.run_id must be a string")
    trash = run.get("trash_encounters_used")
    if not _is_integer(trash) or trash < 0:
        errors.append("world_state.dungeon_run.trash_encounters_used must be nonnegative (no encounter cap)")
    dangers = run.get("danger_zones_resolved")
    if not _is_integer(dangers) or dangers < 0:
        errors.append("world_state.dungeon_run.danger_zones_resolved must be nonnegative")
    scene_kind = run.get("last_scene_kind")
    if scene_kind not in {"none", "exploration", "event", "trash", "boss"}:
        errors.append("world_state.dungeon_run.last_scene_kind is invalid")
    event_due = run.get("event_due")
    if not isinstance(event_due, bool):
        errors.append("world_state.dungeon_run.event_due must be a boolean")
    elif event_due != (scene_kind == "trash"):
        errors.append("world_state.dungeon_run.event_due must be true exactly after a trash scene")
    used_ids = run.get("used_event_ids")
    if not isinstance(used_ids, list) or not all(
        isinstance(item, str) and item for item in (used_ids or [])
    ):
        errors.append("world_state.dungeon_run.used_event_ids must be a list of safe ids")
        used_ids = []
    else:
        if len(used_ids) != len(set(used_ids)):
            errors.append("world_state.dungeon_run.used_event_ids must be unique")
        for event_id in used_ids:
            try:
                safe_id(event_id)
            except RuntimeProblem:
                errors.append("world_state.dungeon_run.used_event_ids must be a list of safe ids")
                break
    current_floor = run.get("current_floor")
    floor_scenes = run.get("current_floor_scenes")
    if not _is_integer(floor_scenes) or floor_scenes < 0:
        errors.append("world_state.dungeon_run.current_floor_scenes must be an integer >= 0")
    if not isinstance(run.get("boss_route_found"), bool):
        errors.append("world_state.dungeon_run.boss_route_found must be a boolean")
    searches = run.get("reward_searches_by_floor")
    if not isinstance(searches, dict):
        errors.append("world_state.dungeon_run.reward_searches_by_floor must be a mapping")
    else:
        for floor, count in searches.items():
            try:
                floor_number = int(floor)
            except (TypeError, ValueError):
                floor_number = 0
            if str(floor_number) != str(floor) and floor_number != floor:
                errors.append("reward_searches_by_floor keys must be floor integers 1..9")
            if not 1 <= floor_number <= 9 or not _is_integer(count) or count < 0:
                errors.append("reward_searches_by_floor requires floor 1..9 and a nonnegative count")
    if not isinstance(run.get("camp_used"), bool):
        errors.append("world_state.dungeon_run.camp_used must be a boolean")
    for deprecated in ("reward_searches_used", "camped_floors", "floor_exhausted"):
        if deprecated in run:
            errors.append(f"world_state.dungeon_run.{deprecated} is retired; run migrate-save")
    if active is False:
        inactive_defaults = {
            "run_id": "", "trash_encounters_used": 0, "danger_zones_resolved": 0,
            "last_scene_kind": "none", "event_due": False, "used_event_ids": [],
            "current_floor": None, "current_floor_scenes": 0,
            "reward_searches_by_floor": {}, "camp_used": False,
            "boss_route_found": False, "resource_days_by_floor": {},
        }
        for key, expected in inactive_defaults.items():
            if run.get(key) != expected:
                errors.append(f"inactive dungeon_run requires {key}={expected!r}")
    elif active is True:
        try:
            safe_id(run_id if isinstance(run_id, str) else "")
        except RuntimeProblem:
            errors.append("active dungeon_run.run_id must be a non-empty safe id")
        if not _is_integer(current_floor) or not 1 <= current_floor <= 9:
            errors.append("active dungeon_run.current_floor must be an integer in 1..9")
        elif _is_integer(deepest) and current_floor > deepest:
            errors.append("active dungeon_run.current_floor cannot exceed deepest_depth_reached")
    expedition = world_state.get("expedition_state")
    if isinstance(expedition, dict):
        if active is True and not (
            expedition.get("active") is True
            and expedition.get("kind") == "dungeon"
            and expedition.get("expedition_id") == run_id
        ):
            errors.append(
                "active dungeon_run requires matching active dungeon expedition_state"
            )
        if active is False and expedition.get("active") is True and expedition.get("kind") == "dungeon":
            errors.append("dungeon expedition_state requires an active dungeon_run")
    from dungeon_exploration import validate_memory
    validate_memory(data, errors)


def _validate_growth_transition(old: dict, new: dict, transaction_id: str) -> list[str]:
    """Keep fruit resolutions append-only and bind the C-rank grant to its item delta."""
    errors: list[str] = []
    old_world = old.get("world_state") if isinstance(old.get("world_state"), dict) else {}
    new_world = new.get("world_state") if isinstance(new.get("world_state"), dict) else {}
    old_growth = old_world.get("growth_state") if isinstance(old_world.get("growth_state"), dict) else {}
    new_growth = new_world.get("growth_state") if isinstance(new_world.get("growth_state"), dict) else {}
    old_resolutions = old_growth.get("resolutions")
    new_resolutions = new_growth.get("resolutions")
    if isinstance(old_resolutions, list) and isinstance(new_resolutions, list):
        if new_resolutions[:len(old_resolutions)] != old_resolutions:
            errors.append("growth_state.resolutions is append-only")
        added = new_resolutions[len(old_resolutions):]
    else:
        added = []
    if old_growth.get("boss_fruit_legacy_sources", []) != new_growth.get("boss_fruit_legacy_sources", []):
        errors.append("legacy boss acquisition projection is immutable during play")
    old_status = old_growth.get("c_rank_choice_fruit_status")
    new_status = new_growth.get("c_rank_choice_fruit_status")
    if old_status == "granted" and (
        new_status != "granted" or
        new_growth.get("c_rank_choice_fruit_transaction_id") !=
        old_growth.get("c_rank_choice_fruit_transaction_id")
    ):
        errors.append("granted C-rank fruit state is immutable")
    if old_status == "pending" and new_status == "locked":
        errors.append("pending C-rank fruit state cannot return to locked")
    if old_status == "locked" and new_status == "pending" and not _rank_at_least_c(new_world):
        errors.append("C-rank fruit cannot become pending before C-rank promotion")
    new_c_rank = [
        item for item in added
        if isinstance(item, dict) and item.get("source_type") == "c_rank"
    ]
    if old_status != "granted" and new_status == "granted":
        if len(new_c_rank) != 1:
            errors.append("new C-rank fruit grant requires one appended c_rank resolution")
        if new_growth.get("c_rank_choice_fruit_transaction_id") != transaction_id:
            errors.append("C-rank fruit grant must use the current transaction_id")
        before = _reward_item_count(old, "選べる能力の実")
        after = _reward_item_count(new, "選べる能力の実")
        if before is None or after is None or after - before != 1:
            errors.append("C-rank fruit grant must add exactly one 選べる能力の実")
    elif new_c_rank:
        errors.append("c_rank resolution may only be appended while granting the C-rank fruit")
    expected_items: dict[str, int] = {}
    rolls_by_die: dict[str, list[dict]] = {"d6": [], "d10": []}
    for resolution in added:
        if not isinstance(resolution, dict):
            continue
        if resolution.get("outcome") == "awarded":
            for item in resolution.get("items", []) if isinstance(resolution.get("items"), list) else []:
                if not isinstance(item, dict):
                    continue
                item_name = item.get("name")
                quantity = item.get("count")
                if isinstance(item_name, str) and _is_integer(quantity):
                    expected_items[item_name] = expected_items.get(item_name, 0) + quantity
        for roll in resolution.get("rolls", []) if isinstance(resolution.get("rolls"), list) else []:
            if isinstance(roll, dict) and roll.get("die") in rolls_by_die:
                rolls_by_die[roll["die"]].append(roll)
    for item_name, quantity in expected_items.items():
        before = _reward_item_count(old, item_name)
        after = _reward_item_count(new, item_name)
        if before is None or after is None or after - before != quantity:
            errors.append(
                f"awarded growth resolutions must add exactly {quantity} x {item_name}"
            )
    for item_name in ABILITY_FRUIT_ITEMS:
        before = _reward_item_count(old, item_name)
        after = _reward_item_count(new, item_name)
        if before is None or after is None:
            continue
        delta = after - before
        expected = expected_items.get(item_name, 0)
        if delta > 0 and delta != expected:
            errors.append(
                f"ability fruit inventory increase requires matching growth resolutions: "
                f"{item_name} delta {delta}, expected {expected}"
            )
    new_dice = new.get("dice_state") if isinstance(new.get("dice_state"), dict) else {}
    for die, rolls in rolls_by_die.items():
        if not rolls:
            continue
        limit = 600 if die == "d6" else 500
        seen_cursors: set[int] = set()
        expected_cursor: int | None = None
        for roll in rolls:
            cursor = roll.get("cursor")
            if not _is_integer(cursor):
                continue
            if cursor in seen_cursors:
                errors.append(f"growth {die} cursor cannot be reused in one commit: {cursor}")
            seen_cursors.add(cursor)
            if expected_cursor is not None and cursor != expected_cursor:
                errors.append(f"growth {die} rolls must consume consecutive cursors in order")
            expected_cursor = (cursor + 1) % limit
        final_cursor = new_dice.get(f"dice_cursor_{die}")
        if expected_cursor is not None and final_cursor != expected_cursor:
            errors.append(
                f"dice_state.dice_cursor_{die} must equal the cursor after growth rolls"
            )
    return errors


def _expedition_member(data: dict, reference: str) -> dict | None:
    """Resolve a stable ID first, then an unambiguous pre-ID display name.

    Never select the first of several equally named actors.  Returning None
    makes the existing validation paths report the unresolved holder instead
    of applying recovery or all-down checks to the wrong person.
    """
    if not isinstance(reference, str) or not reference:
        return None
    actors = [data.get("player"), *(data.get("party") if isinstance(data.get("party"), list) else [])]
    actors = [member for member in actors if isinstance(member, dict)]
    id_matches = [member for member in actors if member.get("character_id") == reference]
    if id_matches:
        return id_matches[0] if len(id_matches) == 1 else None
    name_matches = [member for member in actors if member.get("name") == reference]
    return name_matches[0] if len(name_matches) == 1 else None


def _member_meter(member: dict | None, key: str) -> tuple[int, int] | None:
    if not isinstance(member, dict):
        return None
    meter = member.get(key)
    if not isinstance(meter, dict):
        return None
    current = meter.get("cur", meter.get("current"))
    maximum = meter.get("max")
    if not _is_integer(current) or not _is_integer(maximum):
        return None
    return current, maximum


def _member_recovered_after_rebirth(member: dict | None) -> bool:
    if not isinstance(member, dict):
        return False
    for key in ("lp", "mp"):
        meter = _member_meter(member, key)
        if meter is None or meter[0] != meter[1]:
            return False
    if member.get("ero_status") != []:
        return False
    if "state" in member and member.get("state") not in {"", None}:
        return False
    for key in ("buffs", "temporary_status", "temporary_statuses", "status_effects"):
        if key in member and member.get(key) != []:
            return False
    return True


def _rebirth_fee(world: dict) -> int:
    """Freeze the danger-tier fee from saved floor/quest evidence; never infer upward later."""
    fee = 500
    depth = world.get("depth")
    if not _is_integer(depth):
        run = world.get("dungeon_run")
        depth = run.get("current_floor") if isinstance(run, dict) else None
    if _is_integer(depth):
        if depth >= 7:
            fee = max(fee, 2000)
        elif depth >= 5:
            fee = max(fee, 1500)
        elif depth >= 3:
            fee = max(fee, 1000)
    rank = str(world.get("quest_rank") or "").upper().strip()
    match = re.search(
        r"(?:^|[^A-Z])([A-F])(?:級|[-_ ]?RANK|$)|(?:^|[^A-Z])RANK[-_ ]?([A-F])(?:$|[^A-Z])",
        rank,
    )
    rank_letter = next((group for group in match.groups() if group), "") if match else ""
    fee = max(fee, {"A": 2000, "B": 1500, "C": 1000}.get(rank_letter, 500))
    return fee


def _validate_rebirth_close(
    old: dict, new: dict, old_world: dict, new_world: dict,
    old_expedition: dict, new_expedition: dict,
) -> list[str]:
    errors: list[str] = []
    holders = old_expedition.get("fire_holders")
    receipt = new_expedition.get("rebirth_receipt")
    receipt_members = receipt.get("fire_holders") if isinstance(receipt, dict) else None
    receipt_actors: list[int] = []
    for member in receipt_members if isinstance(receipt_members, list) else []:
        if (not isinstance(member, dict) or not isinstance(member.get("name"), str)
                or not member["name"] or not _is_integer(member.get("lp_at_trigger"))
                or member.get("lp_at_trigger") != 0):
            errors.append("rebirth receipt entries require an identity, name and lp_at_trigger=0")
            continue
        reference = member.get("character_id") or member["name"]
        actor = _expedition_member(old, reference)
        if (actor is None or actor.get("name") != member["name"]
                or (member.get("character_id") is not None
                    and actor.get("character_id") != member["character_id"])):
            errors.append("rebirth receipt identity must resolve unambiguously to its display name")
            continue
        receipt_actors.append(id(actor))
    holder_actors = [_expedition_member(old, reference) for reference in holders] if isinstance(holders, list) else []
    holder_actor_ids = {id(actor) for actor in holder_actors if actor is not None}
    if (not isinstance(holders, list) or not holders or any(actor is None for actor in holder_actors)
            or len(receipt_actors) != len(holders) or len(set(receipt_actors)) != len(receipt_actors)
            or set(receipt_actors) != holder_actor_ids):
        errors.append("rebirth receipt must cover every expedition fire holder exactly once")
    for name in holders if isinstance(holders, list) else []:
        old_member = _expedition_member(old, name)
        new_member = _expedition_member(new, name)
        if not _member_recovered_after_rebirth(new_member):
            errors.append(
                f"rebirth must fully recover LP, MP, temporary states, and ero_status: {name}"
            )
        for meter_name in ("lp", "mp"):
            old_meter = _member_meter(old_member, meter_name)
            new_meter = _member_meter(new_member, meter_name)
            if old_meter is None or new_meter is None or new_meter[1] != old_meter[1]:
                errors.append(
                    f"rebirth must not change {meter_name}.max for fire holder: {name}"
                )
    old_player = old.get("player") if isinstance(old.get("player"), dict) else {}
    new_player = new.get("player") if isinstance(new.get("player"), dict) else {}
    old_debt, new_debt = old_player.get("debt"), new_player.get("debt")
    rebirth_fee = _rebirth_fee(old_world)
    if not (_is_integer(old_debt) and _is_integer(new_debt)
            and new_debt == old_debt + rebirth_fee):
        errors.append(f"rebirth must add exactly {rebirth_fee}G to player.debt for the saved danger tier")
    old_debt_state = old.get("debt_state") if isinstance(old.get("debt_state"), dict) else {}
    new_debt_state = new.get("debt_state") if isinstance(new.get("debt_state"), dict) else {}
    if new_debt_state.get("principal") != new_debt:
        errors.append("rebirth must update debt_state.principal with player.debt atomically")
    debt_allowed = {"principal", "collection_pending", "collection_ledger"}
    if ({key: value for key, value in old_debt_state.items() if key not in debt_allowed}
            != {key: value for key, value in new_debt_state.items() if key not in debt_allowed}):
        errors.append("rebirth may only change debt principal and a newly due collection flag")
    if new_player.get("gold") != old_player.get("gold"):
        errors.append("rebirth must not change player.gold")
    if new.get("items") != old.get("items"):
        errors.append("rebirth must not add, remove, or restore carried items")
    if new.get("equip") != old.get("equip"):
        errors.append("rebirth must not change equipment")
    if new.get("ammo") != old.get("ammo"):
        errors.append("rebirth must not restore or change consumed ammunition")
    for name in holders if isinstance(holders, list) else []:
        old_member = _expedition_member(old, name)
        new_member = _expedition_member(new, name)
        if (isinstance(old_member, dict) and "equipment" in old_member
                and (not isinstance(new_member, dict)
                     or new_member.get("equipment") != old_member.get("equipment"))):
            errors.append(f"rebirth must not change fire-holder equipment: {name}")
    old_day, new_day = old_world.get("day"), new_world.get("day")
    if not (_is_integer(old_day) and _is_integer(new_day) and new_day == old_day + 1):
        errors.append("rebirth must advance world_state.day to the next day")
    next_collection_day = old_debt_state.get("next_collection_day")
    expected_pending = old_debt_state.get("collection_pending") is True or (
        _is_integer(new_day) and _is_integer(next_collection_day)
        and new_day >= next_collection_day
    )
    if new_debt_state.get("collection_pending") is not expected_pending:
        errors.append("rebirth must preserve/set collection_pending when the due day is reached")
    if new_world.get("time_of_day") != "朝":
        errors.append("rebirth must resume in the morning")
    location = new_world.get("location")
    if not isinstance(location, str) or not (
        "ぬれねずみ亭" in location or location in {"宿", "宿屋"}
    ):
        errors.append("rebirth must return to the inn (ぬれねずみ亭)")
    if new_world.get("depth") is not None:
        errors.append("rebirth at the inn requires world_state.depth=null")

    allowed_top = {
        "player", "party", "world_state", "session_log", "runtime_state",
        "debt_state",
        "transaction", "save_revision", "updated_at", "content_manifest_hash",
        "game_version",
    }
    old_other = {key: value for key, value in old.items() if key not in allowed_top}
    new_other = {key: value for key, value in new.items() if key not in allowed_top}
    if new_other != old_other:
        errors.append("rebirth settlement may not change unrelated top-level state")

    allowed_player = {"debt", "lp", "mp", "buffs", "ero_status"}
    if ({key: value for key, value in old_player.items() if key not in allowed_player}
            != {key: value for key, value in new_player.items() if key not in allowed_player}):
        errors.append("rebirth settlement may only change player recovery fields and debt")

    allowed_world = {
        "day", "location", "depth", "time_of_day", "expedition_state", "dungeon_run",
        "place_id", "room_id", "sub_location", "location_kind",
    }
    if new_world.get("place_id") not in {None, "", "INN_DRENCHED_RAT"}:
        errors.append("rebirth place_id must identify the inn or remain unspecified")
    if new_world.get("room_id"):
        try:
            from place_atlas import load as load_place_atlas, RELATIVE_PATH
            inn = next(place for place in load_place_atlas(ROOT / RELATIVE_PATH)["places"]
                       if place["id"] == "INN_DRENCHED_RAT")
            if new_world["room_id"] not in {room["id"] for room in inn["rooms"]}:
                errors.append("rebirth room_id must identify an actual inn room or be cleared")
        except (OSError, ValueError, StopIteration):
            errors.append("rebirth could not verify the inn room in its canonical structure")
    if (old_world.get("place_id") != "INN_DRENCHED_RAT" and old_world.get("sub_location")
            and new_world.get("sub_location") == old_world["sub_location"]):
        errors.append("rebirth must clear or update the previous place's sub_location")
    if "location_kind" in new_world and new_world["location_kind"] != "town":
        errors.append("rebirth location_kind must return to town")
    if ({key: value for key, value in old_world.items() if key not in allowed_world}
            != {key: value for key, value in new_world.items() if key not in allowed_world}):
        errors.append("rebirth settlement may not change unrelated world progress")

    old_log = old.get("session_log")
    new_log = new.get("session_log")
    if isinstance(old_log, dict) and isinstance(new_log, dict):
        old_entries, new_entries = old_log.get("entries"), new_log.get("entries")
        log_append_only = (
            new_log.get("previous") == old_log.get("previous")
            and isinstance(old_entries, list) and isinstance(new_entries, list)
            and new_entries[:len(old_entries)] == old_entries
        )
        if not log_append_only:
            errors.append("rebirth settlement session_log may only append entries")
    elif new_log != old_log:
        errors.append("rebirth settlement may not replace session_log")

    old_party = old.get("party") if isinstance(old.get("party"), list) else []
    new_party = new.get("party") if isinstance(new.get("party"), list) else []
    def party_actor(source: dict, member: dict, party: list) -> dict | None:
        reference = member.get("character_id") or member.get("name")
        actor = _expedition_member(source, reference)
        if (actor is None or not any(actor is candidate for candidate in party)
                or (member.get("character_id") and actor.get("character_id") != member["character_id"])):
            return None
        return actor

    matched_old: set[int] = set()
    for new_member in new_party:
        old_member = party_actor(old, new_member, old_party) if isinstance(new_member, dict) else None
        if old_member is None or id(old_member) in matched_old:
            errors.append("rebirth settlement may not add or ambiguously duplicate party members")
        else:
            matched_old.add(id(old_member))
    allowed_member = {
        "lp", "mp", "state", "ero_status", "buffs",
        "temporary_status", "temporary_statuses", "status_effects",
    }
    for old_member in old_party:
        if not isinstance(old_member, dict):
            continue
        name = old_member.get("character_id") or old_member.get("name")
        if party_actor(old, old_member, old_party) is not old_member:
            errors.append(f"rebirth settlement requires unambiguous party identities: {name}")
            continue
        new_member = party_actor(new, old_member, new_party)
        if id(old_member) in holder_actor_ids:
            if not isinstance(new_member, dict):
                errors.append(f"rebirth settlement must retain fire holder in party: {name}")
            elif ({key: value for key, value in old_member.items() if key not in allowed_member}
                  != {key: value for key, value in new_member.items() if key not in allowed_member}):
                errors.append(f"rebirth settlement changed unrelated fire-holder data: {name}")
        elif new_member is not None and new_member != old_member:
            errors.append(f"rebirth settlement changed non-fire party member data: {name}")
    return errors


def _validate_adventure_transition(old: dict, new: dict) -> list[str]:
    """Protect expedition, delve counters, floor unlocks, and boss rematches across commits."""
    errors: list[str] = []
    old_world = old.get("world_state") if isinstance(old.get("world_state"), dict) else {}
    new_world = new.get("world_state") if isinstance(new.get("world_state"), dict) else {}
    old_expedition = old_world.get("expedition_state")
    new_expedition = new_world.get("expedition_state")
    if isinstance(old_expedition, dict) and isinstance(new_expedition, dict):
        old_expedition_active = old_expedition.get("active") is True
        new_expedition_active = new_expedition.get("active") is True
        if old_expedition_active and new_expedition_active:
            if old_expedition.get("expedition_id") != new_expedition.get("expedition_id"):
                errors.append("active expedition_id cannot be replaced; end the expedition first")
            if old_expedition.get("kind") != new_expedition.get("kind"):
                errors.append("active expedition kind is immutable")
            if old_expedition.get("fire_holders") != new_expedition.get("fire_holders"):
                errors.append("active expedition fire_holders are immutable")
            if old_expedition.get("rebirth_pending") is True:
                errors.append(
                    "a pending rebirth must be settled in the next commit before any other progress"
                )
        elif old_expedition_active and not new_expedition_active:
            if new_expedition.get("last_end_reason") not in {"return", "rebirth", "completed"}:
                errors.append("ending an expedition requires return, rebirth, or completed reason")
            if new_expedition.get("last_ended_expedition_id") != old_expedition.get("expedition_id"):
                errors.append("expedition end marker must name the expedition being closed")
            holder_names = old_expedition.get("fire_holders")
            holder_lp = [
                _member_meter(_expedition_member(old, name), "lp")
                for name in holder_names
            ] if isinstance(holder_names, list) else []
            all_holders_down = bool(holder_lp) and all(
                meter is not None and meter[0] == 0 for meter in holder_lp
            )
            if new_expedition.get("last_end_reason") == "rebirth":
                if old_expedition.get("rebirth_pending") is not True:
                    errors.append("rebirth close requires rebirth_pending=true in the current save")
                if not all_holders_down:
                    errors.append(
                        "rebirth requires every expedition fire holder to be at LP0 in the current save"
                    )
                errors.extend(_validate_rebirth_close(
                    old, new, old_world, new_world, old_expedition, new_expedition,
                ))
            elif old_expedition.get("rebirth_pending") is True or all_holders_down:
                errors.append("an all-fire-holder wipe must close as rebirth, not return/completed")
        elif not old_expedition_active and new_expedition_active:
            if new_expedition.get("expedition_id") == old_expedition.get("last_ended_expedition_id"):
                errors.append("a new expedition cannot reuse the last ended expedition_id")
            if (new_expedition.get("last_end_reason") != "none"
                    or new_expedition.get("last_ended_expedition_id") != ""
                    or new_expedition.get("rebirth_receipt") is not None):
                errors.append("starting an expedition must clear the prior end marker")
        elif (
            new_expedition.get("last_end_reason") != old_expedition.get("last_end_reason")
            or new_expedition.get("last_ended_expedition_id") !=
            old_expedition.get("last_ended_expedition_id")
            or new_expedition.get("rebirth_receipt") != old_expedition.get("rebirth_receipt")
        ):
            errors.append("inactive expedition end marker is immutable until a new expedition starts")

    old_deepest = old_world.get("deepest_depth_reached")
    new_deepest = new_world.get("deepest_depth_reached")
    if _is_integer(old_deepest) and _is_integer(new_deepest) and new_deepest < old_deepest:
        errors.append("deepest_depth_reached cannot decrease")
    old_defeated = old_world.get("defeated_floor_bosses")
    new_defeated = new_world.get("defeated_floor_bosses")
    if isinstance(old_defeated, list) and isinstance(new_defeated, list):
        if new_defeated[:len(old_defeated)] != old_defeated:
            errors.append("defeated_floor_bosses is append-only")
        newly_defeated = new_defeated[len(old_defeated):]
        if len(newly_defeated) > 1:
            errors.append("only one floor boss can be newly defeated in one commit")
    else:
        newly_defeated = []

    from dungeon_exploration import validate_adventure
    errors.extend(validate_adventure(old, new))
    return errors


def _validate_reward_transition(old: dict, new: dict, transaction_id: str) -> list[str]:
    """Keep the terminal reward ledger append-only across a save commit."""
    errors: list[str] = []

    def world(data: dict) -> dict:
        value = data.get("world_state")
        return value if isinstance(value, dict) else {}

    def ledger_map(data: dict) -> dict[str, dict]:
        result: dict[str, dict] = {}
        entries = world(data).get("reward_ledger", [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("settlement_id"), str):
                    result[entry["settlement_id"]] = entry
        return result

    def component_map(entry: dict) -> dict[str, dict]:
        result: dict[str, dict] = {}
        components = entry.get("components", [])
        if isinstance(components, list):
            for component in components:
                if isinstance(component, dict) and isinstance(component.get("component_id"), str):
                    result[component["component_id"]] = component
        return result

    def pending_maps(data: dict) -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
        components: dict[tuple[str, str], dict] = {}
        entries: dict[str, dict] = {}
        raw_entries = world(data).get("pending_rewards", [])
        if not isinstance(raw_entries, list):
            return components, entries
        for entry in raw_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("settlement_id"), str):
                continue
            settlement_id = entry["settlement_id"]
            entries[settlement_id] = entry
            for component in entry.get("components", []):
                if isinstance(component, dict) and isinstance(component.get("component_id"), str):
                    components[(settlement_id, component["component_id"])] = component
        return components, entries

    def standard_contracts(data: dict) -> dict[str, dict]:
        contracts: dict[str, dict] = {}
        quest_card = world(data).get("quest_card")
        active_event = data.get("active_event")
        for card in (quest_card, active_event):
            contract = card.get("reward_contract") if isinstance(card, dict) else None
            settlement_id = contract.get("settlement_id") if isinstance(contract, dict) else None
            if isinstance(settlement_id, str) and settlement_id:
                if settlement_id in contracts:
                    errors.append(
                        "quest_card and active_event reward_contract settlement_id "
                        f"must be unique: {settlement_id}"
                    )
                    continue
                contracts[settlement_id] = contract
        return contracts

    old_ledger = ledger_map(old)
    new_ledger = ledger_map(new)
    old_pending_components, old_pending_entries = pending_maps(old)
    new_pending_components, new_pending_entries = pending_maps(new)
    old_standard_contracts = standard_contracts(old)
    new_standard_contracts = standard_contracts(new)
    standard_reward_pairs = set(old_pending_components)
    for settlement_id, contract in old_standard_contracts.items():
        standard_reward_pairs.update(
            (settlement_id, component.get("component_id"))
            for component in contract.get("components", [])
            if isinstance(component, dict) and isinstance(component.get("component_id"), str)
        )
    authorized_reward_pairs = set(standard_reward_pairs)
    for settlement_id, contract in new_standard_contracts.items():
        old_contract = old_standard_contracts.get(settlement_id)
        if old_contract is None and settlement_id in old_ledger:
            errors.append(f"reward_contract reuses an earlier settlement_id: {settlement_id}")
        old_components = {
            component.get("component_id"): component
            for component in (old_contract.get("components", []) if isinstance(old_contract, dict) else [])
            if isinstance(component, dict) and isinstance(component.get("component_id"), str)
        }
        for component in contract.get("components", []):
            if not isinstance(component, dict) or not component.get("legacy_migration"):
                continue
            component_id = component.get("component_id")
            if component_id not in old_components or not old_components[component_id].get(
                "legacy_migration"
            ):
                errors.append(
                    f"new reward_contract component cannot claim legacy migration: "
                    f"{settlement_id}/{component_id}"
                )

    if world(old).get("reward_state_version") == 2 and world(new).get(
        "reward_state_version"
    ) != 2:
        errors.append("world_state.reward_state_version cannot be removed or downgraded")

    old_event_contract = world(old).get("event_reward_contract")
    new_event_contract = world(new).get("event_reward_contract")
    settling_event_contract = (
        isinstance(old_event_contract, dict) and not isinstance(new_event_contract, dict)
    )
    settled_event_has_gold = False
    settled_event_item_names: set[str] = set()
    declined_event_entitlement_ids: set[str] = set()
    declined_event_log_pairs: set[tuple[str, str]] = set()
    guarded_gold_settlements: set[str] = set()
    if isinstance(old_event_contract, dict) and isinstance(
        old_event_contract.get("settlement_id"), str
    ):
        authorized_reward_pairs.update(
            (old_event_contract["settlement_id"], component.get("component_id"))
            for component in old_event_contract.get("components", [])
            if isinstance(component, dict) and isinstance(component.get("component_id"), str)
        )
    if isinstance(new_event_contract, dict):
        new_event_id = new_event_contract.get("settlement_id")
        if not isinstance(old_event_contract, dict) and new_event_id in old_ledger:
            errors.append(f"event_reward_contract reuses an earlier settlement_id: {new_event_id}")
        old_event_components = {
            component.get("component_id"): component
            for component in (
                old_event_contract.get("components", [])
                if isinstance(old_event_contract, dict) else []
            )
            if isinstance(component, dict) and isinstance(component.get("component_id"), str)
        }
        for component in new_event_contract.get("components", []):
            if not isinstance(component, dict) or not component.get("legacy_migration"):
                continue
            component_id = component.get("component_id")
            if component_id not in old_event_components or not old_event_components[
                component_id
            ].get("legacy_migration"):
                errors.append(
                    f"new event_reward_contract component cannot claim legacy migration: "
                    f"{new_event_id}/{component_id}"
                )

    def bind_terminal_detail(
        settlement_id: str, component_id: str, promised: dict,
        ledger_component: dict, *, newly_terminal: bool,
    ) -> None:
        kind = promised.get("kind")
        if ledger_component.get("kind") != kind:
            errors.append(
                f"reward kind changed during settlement: {settlement_id}/{component_id}"
            )
        state = ledger_component.get("state")
        if promised.get("state") in {"delivered", "declined", "forfeited"} and (
            state != promised.get("state")
        ):
            errors.append(
                f"terminal reward contract state changed: {settlement_id}/{component_id}"
            )
        if promised.get("legacy_migration"):
            return
        detail = promised.get("detail")
        detail = detail if isinstance(detail, dict) else {}
        effect = ledger_component.get("effect")
        if newly_terminal and kind == "gold":
            guarded_gold_settlements.add(settlement_id)
        if newly_terminal and kind == "item" and isinstance(detail.get("item_name"), str):
            settled_event_item_names.add(detail["item_name"])
        if state == "delivered" and isinstance(effect, dict):
            if kind == "gold" and effect.get("amount") != detail.get("amount"):
                errors.append(
                    f"reward gold amount changed during settlement: {settlement_id}/{component_id}"
                )
            if kind == "item" and (
                effect.get("item_name") != detail.get("item_name") or
                effect.get("quantity") != detail.get("quantity")
            ):
                errors.append(
                    f"reward item changed during settlement: {settlement_id}/{component_id}"
                )
            if kind in {"right", "service", "favor", "referral", "information"}:
                delivery_target = detail.get("delivery_target")
                if effect.get("target") != delivery_target:
                    errors.append(
                        "reward noncash delivery target changed during settlement: "
                        f"{settlement_id}/{component_id}"
                    )
                elif delivery_target == "world_state.entitlements":
                    entitlement_id = detail.get("entitlement_id")
                    old_ids = {
                        item.get("entitlement_id")
                        for item in world(old).get("entitlements", []) if isinstance(item, dict)
                    }
                    new_entitlements = {
                        item.get("entitlement_id"): item
                        for item in world(new).get("entitlements", []) if isinstance(item, dict)
                    }
                    entitlement = new_entitlements.get(entitlement_id)
                    if newly_terminal and entitlement_id in old_ids:
                        errors.append(
                            "reward entitlement_id existed before delivery: "
                            f"{settlement_id}/{component_id}"
                        )
                    if not isinstance(entitlement, dict):
                        errors.append(
                            f"reward entitlement is missing: {settlement_id}/{component_id}"
                        )
                    else:
                        expected_fields = {
                            "entitlement_id": entitlement_id, "kind": kind,
                            "name": detail.get("name"), "issuer": detail.get("issuer"),
                            "scope": detail.get("scope"),
                            "conditions": detail.get("conditions"),
                            "uses_remaining": detail.get("uses_remaining"),
                            "expires": detail.get("expires"), "status": "active",
                        }
                        for key, expected in expected_fields.items():
                            if entitlement.get(key) != expected:
                                errors.append(
                                    "reward entitlement differs from its contract: "
                                    f"{settlement_id}/{component_id}.{key}"
                                )
                elif delivery_target == "session_log":
                    entries = _reward_log_entries(new)
                    index = effect.get("log_entry_index")
                    entry = (
                        entries[index] if entries is not None and _is_integer(index)
                        and 0 <= index < len(entries) else None
                    )
                    delivery = entry.get("reward_delivery") if isinstance(entry, dict) else None
                    expected_delivery = {
                        "settlement_id": settlement_id, "component_id": component_id,
                        "kind": kind, "summary": detail.get("summary"),
                    }
                    if delivery != expected_delivery:
                        errors.append(
                            "reward session_log delivery differs from its contract: "
                            f"{settlement_id}/{component_id}"
                        )
        elif newly_terminal and state in {"declined", "forfeited"}:
            target = detail.get("delivery_target")
            if target == "world_state.entitlements" and isinstance(
                detail.get("entitlement_id"), str
            ):
                declined_event_entitlement_ids.add(detail["entitlement_id"])
            if target == "session_log":
                declined_event_log_pairs.add((settlement_id, component_id))
    for settlement_id in set(new_ledger) - set(old_ledger):
        if not settlement_id.startswith("EVR-"):
            continue
        if not (
            isinstance(old_event_contract, dict) and
            old_event_contract.get("offered") is True and
            old_event_contract.get("settlement_id") == settlement_id
        ):
            errors.append(
                "new random-event reward ledger requires the previously offered "
                f"event_reward_contract: {settlement_id}"
            )
    if isinstance(old_event_contract, dict):
        if isinstance(new_event_contract, dict):
            if new_event_contract != old_event_contract:
                errors.append("active event_reward_contract is immutable until settlement")
        elif old_event_contract.get("offered") is True:
            settlement_id = old_event_contract.get("settlement_id")
            contract_components = old_event_contract.get("components")
            ledger_entry = new_ledger.get(settlement_id) if isinstance(settlement_id, str) else None
            ledger_components = component_map(ledger_entry or {})
            expected_ids = {
                component.get("component_id")
                for component in (contract_components or [])
                if isinstance(component, dict) and isinstance(component.get("component_id"), str)
            }
            if not ledger_entry or set(ledger_components) != expected_ids:
                errors.append(
                    "cleared offered event_reward_contract lacks a complete terminal ledger: "
                    f"{settlement_id}"
                )
            elif any(
                component.get("state") not in {"delivered", "declined", "forfeited"}
                for component in ledger_components.values()
            ):
                errors.append(
                    "cleared offered event_reward_contract has a non-terminal component: "
                    f"{settlement_id}"
                )
            else:
                if ledger_entry.get("payer") != old_event_contract.get("payer"):
                    errors.append(
                        "cleared event_reward_contract payer does not match its ledger: "
                        f"{settlement_id}"
                    )
                contract_by_id = {
                    component.get("component_id"): component
                    for component in (contract_components or [])
                    if isinstance(component, dict) and isinstance(component.get("component_id"), str)
                }
                for component_id, contract_component in contract_by_id.items():
                    ledger_component = ledger_components[component_id]
                    contract_kind = contract_component.get("kind")
                    detail = contract_component.get("detail")
                    detail = detail if isinstance(detail, dict) else {}
                    if ledger_component.get("kind") != contract_kind:
                        errors.append(
                            "event reward kind changed during settlement: "
                            f"{settlement_id}/{component_id}"
                        )
                    if contract_component.get("legacy_migration"):
                        continue
                    if contract_kind == "gold":
                        settled_event_has_gold = True
                    if contract_kind == "item" and isinstance(detail.get("item_name"), str):
                        settled_event_item_names.add(detail["item_name"])
                    if ledger_component.get("estimated_value_g") != detail.get("estimated_value_g"):
                        errors.append(
                            "event reward estimated value changed during settlement: "
                            f"{settlement_id}/{component_id}"
                        )
                    effect = ledger_component.get("effect")
                    if ledger_component.get("state") == "delivered" and isinstance(effect, dict):
                        if contract_kind == "gold" and (
                            effect.get("amount") != detail.get("amount")
                        ):
                            errors.append(
                                "event gold amount changed during settlement: "
                                f"{settlement_id}/{component_id}"
                            )
                        if contract_kind == "item" and (
                            effect.get("item_name") != detail.get("item_name") or
                            effect.get("quantity") != detail.get("quantity")
                        ):
                            errors.append(
                                "event item changed during settlement: "
                                f"{settlement_id}/{component_id}"
                            )
                        if contract_kind in {
                            "right", "service", "favor", "referral", "information",
                        }:
                            delivery_target = detail.get("delivery_target")
                            if effect.get("target") != delivery_target:
                                errors.append(
                                    "event noncash delivery target changed during settlement: "
                                    f"{settlement_id}/{component_id}"
                                )
                            elif delivery_target == "world_state.entitlements":
                                entitlement_id = detail.get("entitlement_id")
                                old_entitlement_ids = {
                                    item.get("entitlement_id")
                                    for item in world(old).get("entitlements", [])
                                    if isinstance(item, dict)
                                }
                                new_entitlements = {
                                    item.get("entitlement_id"): item
                                    for item in world(new).get("entitlements", [])
                                    if isinstance(item, dict)
                                }
                                entitlement = new_entitlements.get(entitlement_id)
                                if entitlement_id in old_entitlement_ids:
                                    errors.append(
                                        "event entitlement_id already existed before settlement: "
                                        f"{settlement_id}/{component_id}"
                                    )
                                if not isinstance(entitlement, dict):
                                    errors.append(
                                        "event entitlement is missing during settlement: "
                                        f"{settlement_id}/{component_id}"
                                    )
                                else:
                                    expected_fields = {
                                        "entitlement_id": entitlement_id,
                                        "kind": contract_kind,
                                        "name": detail.get("name"),
                                        "issuer": detail.get("issuer"),
                                        "scope": detail.get("scope"),
                                        "conditions": detail.get("conditions"),
                                        "uses_remaining": detail.get("uses_remaining"),
                                        "expires": detail.get("expires"),
                                        "status": "active",
                                    }
                                    for key, expected in expected_fields.items():
                                        if entitlement.get(key) != expected:
                                            errors.append(
                                                "event entitlement differs from its contract: "
                                                f"{settlement_id}/{component_id}.{key}"
                                            )
                            elif delivery_target == "session_log":
                                entries = _reward_log_entries(new)
                                index = effect.get("log_entry_index")
                                entry = (
                                    entries[index]
                                    if entries is not None and _is_integer(index)
                                    and 0 <= index < len(entries) else None
                                )
                                reward_delivery = (
                                    entry.get("reward_delivery")
                                    if isinstance(entry, dict) else None
                                )
                                expected_delivery = {
                                    "settlement_id": settlement_id,
                                    "component_id": component_id,
                                    "kind": contract_kind,
                                    "summary": detail.get("summary"),
                                }
                                if reward_delivery != expected_delivery:
                                    errors.append(
                                        "event session_log delivery differs from its contract: "
                                        f"{settlement_id}/{component_id}"
                                    )
                    elif ledger_component.get("state") in {"declined", "forfeited"}:
                        delivery_target = detail.get("delivery_target")
                        if delivery_target == "world_state.entitlements" and isinstance(
                            detail.get("entitlement_id"), str
                        ):
                            declined_event_entitlement_ids.add(detail["entitlement_id"])
                        if delivery_target == "session_log":
                            declined_event_log_pairs.add((str(settlement_id), component_id))

    old_ledger_pairs = {
        (settlement_id, component_id)
        for settlement_id, entry in old_ledger.items()
        for component_id in component_map(entry)
    }
    new_ledger_pairs = {
        (settlement_id, component_id)
        for settlement_id, entry in new_ledger.items()
        for component_id in component_map(entry)
    }
    strict_standard_settlement = bool(
        set(old_standard_contracts) - set(new_standard_contracts)
        or ((new_ledger_pairs - old_ledger_pairs) & standard_reward_pairs)
    )

    for pair in set(new_pending_components) - set(old_pending_components):
        if new_pending_components[pair].get("legacy_migration"):
            errors.append(
                f"new pending reward cannot claim legacy migration: {pair[0]}/{pair[1]}"
            )
        promised_contract = old_standard_contracts.get(pair[0])
        promised = next((
            component for component in promised_contract.get("components", [])
            if isinstance(component, dict) and component.get("component_id") == pair[1]
        ), None) if isinstance(promised_contract, dict) else None
        if not isinstance(promised, dict):
            errors.append(f"new pending reward was not previously offered: {pair[0]}/{pair[1]}")
        elif (
            new_pending_components[pair].get("kind") != promised.get("kind") or
            (not promised.get("legacy_migration") and
             new_pending_components[pair].get("detail") != promised.get("detail"))
        ):
            errors.append(f"new pending reward differs from its contract: {pair[0]}/{pair[1]}")
        new_contract = new_standard_contracts.get(pair[0])
        if isinstance(new_contract, dict):
            new_promised = next((
                component for component in new_contract.get("components", [])
                if isinstance(component, dict) and component.get("component_id") == pair[1]
            ), None)
            if not isinstance(new_promised, dict) or new_promised.get("state") != "pending":
                errors.append(
                    f"active reward_contract must mark deferred component pending: "
                    f"{pair[0]}/{pair[1]}"
                )
    for pair in set(old_pending_components) & set(new_pending_components):
        if old_pending_components[pair] != new_pending_components[pair]:
            errors.append(f"pending reward component is immutable: {pair[0]}/{pair[1]}")
    for settlement_id in set(old_pending_entries) & set(new_pending_entries):
        if old_pending_entries[settlement_id].get("payer") != new_pending_entries[
            settlement_id
        ].get("payer"):
            errors.append(f"pending reward payer is immutable: {settlement_id}")

    for settlement_id, contract in old_standard_contracts.items():
        if settlement_id in new_standard_contracts:
            continue
        if contract.get("requires_reconfirmation") is True:
            errors.append(
                f"legacy reward contract must be reconfirmed before closing: {settlement_id}"
            )
            continue
        if contract.get("offered") is not True:
            continue
        promised_components = {
            component.get("component_id"): component
            for component in contract.get("components", [])
            if isinstance(component, dict) and isinstance(component.get("component_id"), str)
        }
        ledger_entry = new_ledger.get(settlement_id)
        ledger_components = component_map(ledger_entry or {})
        pending_entry = new_pending_entries.get(settlement_id)
        pending_components = {
            component_id: component
            for (pending_settlement, component_id), component in new_pending_components.items()
            if pending_settlement == settlement_id
        }
        actual_ids = set(ledger_components) | set(pending_components)
        if set(ledger_components) & set(pending_components):
            errors.append(f"settled and pending contract components overlap: {settlement_id}")
        if actual_ids != set(promised_components):
            errors.append(
                "cleared reward_contract lacks a complete ledger/pending disposition: "
                f"{settlement_id}"
            )
            continue
        if ledger_entry and ledger_entry.get("payer") != contract.get("payer"):
            errors.append(f"reward_contract payer changed in ledger: {settlement_id}")
        if pending_entry and pending_entry.get("payer") != contract.get("payer"):
            errors.append(f"reward_contract payer changed in pending rewards: {settlement_id}")
        for component_id, promised in promised_components.items():
            if component_id in pending_components:
                pending_component = pending_components[component_id]
                if pending_component.get("kind") != promised.get("kind"):
                    errors.append(
                        f"pending reward kind changed: {settlement_id}/{component_id}"
                    )
                if not promised.get("legacy_migration") and (
                    pending_component.get("detail") != promised.get("detail")
                ):
                    errors.append(
                        f"pending reward detail changed: {settlement_id}/{component_id}"
                    )
                continue
            ledger_component = ledger_components[component_id]
            bind_terminal_detail(
                settlement_id, component_id, promised, ledger_component,
                newly_terminal=(settlement_id, component_id) not in old_ledger_pairs,
            )

    removed_pending_components = set(old_pending_components) - set(new_pending_components)
    for settlement_id, component_id in sorted(removed_pending_components):
        promised = old_pending_components[(settlement_id, component_id)]
        ledger_entry = new_ledger.get(settlement_id, {})
        ledger_component = component_map(ledger_entry).get(component_id)
        if not ledger_component:
            continue
        old_pending_entry = old_pending_entries.get(settlement_id, {})
        if ledger_entry.get("payer") != old_pending_entry.get("payer"):
            errors.append(f"pending reward payer changed in ledger: {settlement_id}")
        bind_terminal_detail(
            settlement_id, component_id, promised, ledger_component,
            newly_terminal=(settlement_id, component_id) not in old_ledger_pairs,
        )
    new_gold_amounts: list[int] = []
    new_item_quantities: dict[str, int] = {}
    claimed_entitlement_ids: set[str] = set()
    claimed_log_indices: dict[int, tuple[str, str]] = {}
    old_transaction_ids = {
        component.get("transaction_id")
        for entry in old_ledger.values()
        for component in component_map(entry).values()
        if isinstance(component.get("transaction_id"), str)
    }
    terminal_statuses = {"settled", "declined", "forfeited"}
    for settlement_id, old_entry in old_ledger.items():
        new_entry = new_ledger.get(settlement_id)
        if new_entry is None:
            errors.append(f"reward ledger settlement was removed: {settlement_id}")
            continue
        for key, old_value in old_entry.items():
            if key in {"components", "status"}:
                continue
            if new_entry.get(key) != old_value:
                errors.append(f"reward ledger field is immutable: {settlement_id}.{key}")
        old_status = old_entry.get("status")
        new_status = new_entry.get("status")
        if old_status in terminal_statuses and new_status != old_status:
            errors.append(f"terminal reward ledger status is immutable: {settlement_id}")
        old_components = component_map(old_entry)
        new_components = component_map(new_entry)
        if old_status in terminal_statuses and set(new_components) != set(old_components):
            errors.append(f"terminal reward ledger cannot gain components: {settlement_id}")
        for component_id, old_component in old_components.items():
            if component_id not in new_components:
                errors.append(
                    f"reward ledger component was removed: {settlement_id}/{component_id}"
                )
            elif new_components[component_id] != old_component:
                errors.append(
                    f"reward ledger component is immutable: {settlement_id}/{component_id}"
                )

    for settlement_id, new_entry in new_ledger.items():
        old_components = component_map(old_ledger.get(settlement_id, {}))
        for component_id, component in component_map(new_entry).items():
            if component_id in old_components:
                continue
            if (settlement_id, component_id) not in authorized_reward_pairs:
                errors.append(
                    f"new reward ledger component was not previously offered: "
                    f"{settlement_id}/{component_id}"
                )
            promised_contract = old_standard_contracts.get(settlement_id)
            promised = next((
                item for item in promised_contract.get("components", [])
                if isinstance(item, dict) and item.get("component_id") == component_id
            ), None) if isinstance(promised_contract, dict) else None
            if isinstance(promised, dict):
                if new_entry.get("payer") != promised_contract.get("payer"):
                    errors.append(f"reward_contract payer changed in ledger: {settlement_id}")
                bind_terminal_detail(
                    settlement_id, component_id, promised, component, newly_terminal=True,
                )
                active_contract = new_standard_contracts.get(settlement_id)
                if isinstance(active_contract, dict):
                    active_component = next((
                        item for item in active_contract.get("components", [])
                        if isinstance(item, dict) and item.get("component_id") == component_id
                    ), None)
                    if not isinstance(active_component, dict) or active_component.get(
                        "state"
                    ) != component.get("state"):
                        errors.append(
                            "active reward_contract state does not match its terminal ledger: "
                            f"{settlement_id}/{component_id}"
                        )
            if component.get("transaction_id") != transaction_id:
                errors.append(
                    f"new reward ledger component must use current transaction_id: "
                    f"{settlement_id}/{component_id}"
                )
            if transaction_id in old_transaction_ids:
                errors.append(
                    f"reward transaction_id was already used by an earlier ledger component: "
                    f"{transaction_id}"
                )
            if component.get("legacy_migration"):
                errors.append(
                    f"new reward ledger component cannot claim legacy migration: "
                    f"{settlement_id}/{component_id}"
                )
            if component.get("state") != "delivered":
                continue
            effect = component.get("effect")
            if not isinstance(effect, dict):
                continue
            target = effect.get("target")
            if not isinstance(target, str) or target not in {
                "player.gold", "inventory_bundle", "world_state.entitlements", "session_log",
            }:
                continue
            before_value = _reward_effect_value(old, target)
            after_value = _reward_effect_value(new, target)
            before_hash = _reward_value_hash(before_value)
            after_hash = _reward_value_hash(after_value)
            if effect.get("before_sha256") != before_hash:
                errors.append(
                    f"reward effect before hash does not match {target}: "
                    f"{settlement_id}/{component_id}"
                )
            if effect.get("after_sha256") != after_hash:
                errors.append(
                    f"reward effect after hash does not match {target}: "
                    f"{settlement_id}/{component_id}"
                )
            if before_hash == after_hash:
                errors.append(
                    f"delivered reward did not change {target}: {settlement_id}/{component_id}"
                )
            if component.get("kind") == "gold":
                amount = effect.get("amount")
                if not _is_integer(before_value) or not _is_integer(after_value) or not _is_integer(amount):
                    errors.append(f"gold reward effect is not numeric: {settlement_id}/{component_id}")
                else:
                    new_gold_amounts.append(amount)
            if component.get("kind") == "item":
                item_name = effect.get("item_name")
                quantity = effect.get("quantity")
                if isinstance(item_name, str) and item_name and _is_integer(quantity):
                    new_item_quantities[item_name] = new_item_quantities.get(item_name, 0) + quantity
            if target == "world_state.entitlements":
                entitlement_id = effect.get("entitlement_id")
                if isinstance(entitlement_id, str):
                    claimed_entitlement_ids.add(entitlement_id)
                old_entitlements = {
                    item.get("entitlement_id") for item in (before_value or [])
                    if isinstance(item, dict)
                } if isinstance(before_value, list) else set()
                new_entitlements = {
                    item.get("entitlement_id"): item for item in (after_value or [])
                    if isinstance(item, dict)
                } if isinstance(after_value, list) else {}
                entitlement = new_entitlements.get(entitlement_id)
                if entitlement_id in old_entitlements or not isinstance(entitlement, dict):
                    errors.append(
                        f"reward effect does not add its entitlement: {settlement_id}/{component_id}"
                    )
                elif (entitlement.get("source_settlement_id"),
                      entitlement.get("source_component_id")) != (settlement_id, component_id):
                    errors.append(
                        f"reward entitlement source does not match ledger: {settlement_id}/{component_id}"
                    )
            if target == "session_log":
                old_entries = _reward_log_entries(old)
                new_entries = _reward_log_entries(new)
                index = effect.get("log_entry_index")
                expected_hash = effect.get("log_entry_sha256")
                if old_entries is None or new_entries is None or not _is_integer(index):
                    errors.append(f"reward log effect is invalid: {settlement_id}/{component_id}")
                elif new_entries[:len(old_entries)] != old_entries:
                    errors.append("session_log entries must be append-only during reward delivery")
                elif not len(old_entries) <= index < len(new_entries):
                    errors.append(
                        f"reward log entry is not newly appended: {settlement_id}/{component_id}"
                    )
                elif _reward_value_hash(new_entries[index]) != expected_hash:
                    errors.append(f"reward log entry hash mismatch: {settlement_id}/{component_id}")
                elif index in claimed_log_indices:
                    prior = claimed_log_indices[index]
                    errors.append(
                        f"reward log entry is claimed by multiple components: "
                        f"{prior[0]}/{prior[1]} and {settlement_id}/{component_id}"
                    )
                else:
                    claimed_log_indices[index] = (settlement_id, component_id)

    if new_gold_amounts or settling_event_contract or strict_standard_settlement:
        before_gold = _reward_effect_value(old, "player.gold")
        after_gold = _reward_effect_value(new, "player.gold")
        if (_is_integer(before_gold) and _is_integer(after_gold) and
                after_gold - before_gold != sum(new_gold_amounts)):
            errors.append("total gold reward amount does not match the player.gold delta")
    elif settled_event_has_gold or guarded_gold_settlements:
        before_gold = _reward_effect_value(old, "player.gold")
        after_gold = _reward_effect_value(new, "player.gold")
        if _is_integer(before_gold) and _is_integer(after_gold) and after_gold != before_gold:
            errors.append("declined random-event gold changed player.gold without delivery")

    compared_item_names = set(new_item_quantities) | settled_event_item_names
    if settling_event_contract or strict_standard_settlement:
        before_item_counts = _reward_item_counts(old)
        after_item_counts = _reward_item_counts(new)
        if before_item_counts is None or after_item_counts is None:
            errors.append("random-event settlement requires valid named item stacks")
        else:
            compared_item_names.update(before_item_counts)
            compared_item_names.update(after_item_counts)
    for item_name in sorted(compared_item_names):
        quantity = new_item_quantities.get(item_name, 0)
        before_count = _reward_item_count(old, item_name)
        after_count = _reward_item_count(new, item_name)
        if before_count is None or after_count is None:
            errors.append(f"item reward count is invalid for {item_name}")
        elif after_count - before_count != quantity:
            errors.append(f"item reward quantity does not match inventory delta for {item_name}")

    old_entitlement_ids = {
        item.get("entitlement_id")
        for item in world(old).get("entitlements", [])
        if isinstance(item, dict)
    }
    new_entitlement_ids = {
        item.get("entitlement_id")
        for item in world(new).get("entitlements", [])
        if isinstance(item, dict)
    }
    if settling_event_contract or strict_standard_settlement:
        added_entitlement_ids = new_entitlement_ids - old_entitlement_ids
        if added_entitlement_ids != claimed_entitlement_ids:
            errors.append(
                "reward settlement entitlement additions do not match delivered ledger effects"
            )
    for entitlement_id in declined_event_entitlement_ids:
        if entitlement_id not in old_entitlement_ids and entitlement_id in new_entitlement_ids:
            errors.append(
                f"declined random-event entitlement was still granted: {entitlement_id}"
            )

    if declined_event_log_pairs or settling_event_contract or strict_standard_settlement:
        old_entries = _reward_log_entries(old) or []
        new_entries = _reward_log_entries(new) or []
        appended_entries = (
            new_entries[len(old_entries):]
            if new_entries[:len(old_entries)] == old_entries else []
        )
        for entry in appended_entries:
            delivery = entry.get("reward_delivery") if isinstance(entry, dict) else None
            if not isinstance(delivery, dict):
                continue
            pair = (delivery.get("settlement_id"), delivery.get("component_id"))
            if pair in declined_event_log_pairs:
                errors.append(
                    "declined random-event session_log delivery was still recorded: "
                    f"{pair[0]}/{pair[1]}"
                )
            if (settling_event_contract or strict_standard_settlement) and pair not in set(
                claimed_log_indices.values()
            ):
                errors.append(
                    "reward settlement contains an unclaimed reward_delivery log entry: "
                    f"{pair[0]}/{pair[1]}"
                )

    def pending_pairs(data: dict) -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()
        entries = world(data).get("pending_rewards", [])
        if not isinstance(entries, list):
            return result
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("settlement_id"), str):
                continue
            for component in entry.get("components", []):
                if isinstance(component, dict) and isinstance(component.get("component_id"), str):
                    result.add((entry["settlement_id"], component["component_id"]))
        return result

    removed_pending = pending_pairs(old) - pending_pairs(new)
    for settlement_id, component_id in sorted(removed_pending):
        record = component_map(new_ledger.get(settlement_id, {})).get(component_id)
        if not record or record.get("state") not in {"delivered", "declined", "forfeited"}:
            errors.append(
                f"removed pending reward lacks terminal ledger record: "
                f"{settlement_id}/{component_id}"
            )

    def entitlement_map(data: dict) -> dict[str, dict]:
        result: dict[str, dict] = {}
        entries = world(data).get("entitlements", [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("entitlement_id"), str):
                    result[entry["entitlement_id"]] = entry
        return result

    old_entitlements = entitlement_map(old)
    new_entitlements = entitlement_map(new)
    for entitlement_id, old_entry in old_entitlements.items():
        new_entry = new_entitlements.get(entitlement_id)
        if new_entry is None:
            errors.append(f"entitlement history was removed: {entitlement_id}")
            continue
        for key, old_value in old_entry.items():
            if key in {"status", "uses_remaining"}:
                continue
            if new_entry.get(key) != old_value:
                errors.append(f"entitlement field is immutable: {entitlement_id}.{key}")
        old_status = old_entry.get("status")
        new_status = new_entry.get("status")
        if old_status in {"used", "expired", "revoked"} and new_entry != old_entry:
            errors.append(f"terminal entitlement record is immutable: {entitlement_id}")
        old_uses = old_entry.get("uses_remaining")
        new_uses = new_entry.get("uses_remaining")
        if old_uses is None and new_uses is not None:
            errors.append(f"unlimited entitlement cannot gain a numeric counter: {entitlement_id}")
        elif _is_integer(old_uses) and (
            not _is_integer(new_uses) or new_uses > old_uses
        ):
            errors.append(f"entitlement uses_remaining cannot increase: {entitlement_id}")
    return errors


def _ceil_to_10(value: int) -> int:
    return ((value + 9) // 10) * 10


def _is_rebirth_resolution(old: dict, new: dict) -> bool:
    old_expedition = old.get("world_state", {}).get("expedition_state", {})
    new_expedition = new.get("world_state", {}).get("expedition_state", {})
    return (
        isinstance(old_expedition, dict) and isinstance(new_expedition, dict)
        and old_expedition.get("active") is True
        and old_expedition.get("rebirth_pending") is True
        and new_expedition.get("active") is False
        and new_expedition.get("last_end_reason") == "rebirth"
    )


def _debt_fields_unchanged(old_debt: dict, new_debt: dict, allowed: set[str]) -> bool:
    return (
        {key: value for key, value in old_debt.items() if key not in allowed}
        == {key: value for key, value in new_debt.items() if key not in allowed}
    )


def _validate_renewal_benefit(
    old: dict, new: dict, *, next_cycle: int, day: int, errors: list[str],
) -> None:
    """A full contract grants its single staged option, with no enterprise perk."""
    from debt_contracts import debt_unlocks, expected_benefit
    expected = expected_benefit(next_cycle)
    flags = debt_unlocks(new)
    if expected is not None and flags.get(expected) is not True:
        errors.append("payoff must grant only its canonical staged option")
    old_debt, new_debt = old.get("debt_state", {}), new.get("debt_state", {})
    for key in ("active_benefits", "benefit_selection"):
        if new_debt.get(key) != old_debt.get(key):
            errors.append("debt payoff cannot add or upgrade enterprise benefits")


def _validate_debt_noncollection_event(
    old: dict, new: dict, old_debt: dict, new_debt: dict, entry: dict,
    transaction_id: str, old_day: int, new_day: int,
) -> list[str]:
    errors: list[str] = []
    kind = entry.get("event_kind")
    if entry.get("transaction_id") != transaction_id:
        errors.append("debt event ledger must use the current transaction_id")
    if entry.get("collection_day") != old_day:
        errors.append("debt event ledger must use the current event day")
    if entry.get("contract_id_before") != old_debt.get("contract_id"):
        errors.append("debt event contract_id_before must match the active contract")
    old_player, new_player = old.get("player", {}), new.get("player", {})
    old_principal, old_gold = old_debt.get("principal"), old_player.get("gold")
    if not _is_integer(old_principal) or not _is_integer(old_gold):
        return errors + ["debt event current principal/gold is invalid"]
    if kind in {"payment", "early_payoff"}:
        if old_debt.get("collection_pending") is True:
            errors.append("pending collections must be resolved as event_kind=collection")
        payment = entry.get("payment")
        if not _is_integer(payment) or payment <= 0 or payment > old_gold or payment > old_principal:
            return errors + ["voluntary debt payment must be positive and within gold/principal"]
        if payment % 100 != 0 and payment != old_principal:
            errors.append("voluntary debt payment must use 100G units except exact final remainder")
        if new_player.get("gold") != old_gold - payment:
            errors.append("voluntary debt payment must be the only player.gold delta")
        if kind == "payment":
            if payment == old_principal:
                errors.append("a payoff must use event_kind=early_payoff")
            expected_principal = old_principal - payment
            expected_cycle_paid = old_debt.get("cycle_paid", 0) + payment
            if new_debt.get("principal") != expected_principal or new_player.get("debt") != expected_principal:
                errors.append("voluntary payment must reduce principal/player.debt atomically")
            if new_debt.get("cycle_paid") != expected_cycle_paid:
                errors.append("voluntary payment must accumulate debt_state.cycle_paid")
            if entry.get("contract_id_after") != old_debt.get("contract_id"):
                errors.append("non-payoff payment cannot replace the debt contract")
            if entry.get("principal_before_payment") != old_principal or entry.get(
                "principal_after_resolution"
            ) != expected_principal:
                errors.append("voluntary payment ledger principal before/after is inconsistent")
            if not _debt_fields_unchanged(
                old_debt, new_debt, {"principal", "cycle_paid", "collection_ledger"},
            ):
                errors.append("voluntary payment changed unrelated debt fields")
            return errors
        if payment != old_principal:
            errors.append("early_payoff must pay the complete remaining principal")
        old_cycle = old_debt.get("contract_cycle_index", 0)
        next_cycle = old_cycle + 1
        from debt_contracts import principal_schedule
        next_principal = principal_schedule(next_cycle)
        expected_contract = f"lilith-debt-cycle-{next_cycle}"
        expected = {
            "contract_cycle_index": next_cycle, "contract_id": expected_contract,
            "principal": next_principal, "next_collection_day": old_day + 5,
            "scheduled_due": 500 + 250 * next_cycle, "cycle_paid": 0,
            "collection_pending": False,
        }
        for key, value in expected.items():
            if new_debt.get(key) != value:
                errors.append(f"early payoff renewal requires debt_state.{key}={value!r}")
        for key in (
            "collection_serial", "positive_payment_collections", "full_payment_collections",
            "missed_collections", "last_collection_day",
        ):
            if new_debt.get(key) != old_debt.get(key):
                errors.append(f"early payoff cannot change collection counter {key}")
        if new_player.get("debt") != next_principal:
            errors.append("early payoff renewal must mirror player.debt")
        if entry.get("contract_id_after") != expected_contract:
            errors.append("early payoff ledger must preserve the resulting contract ID")
        if entry.get("principal_before_payment") != old_principal or entry.get(
            "principal_after_resolution"
        ) != next_principal:
            errors.append("early payoff ledger principal before/after is inconsistent")
        _validate_renewal_benefit(
            old, new, next_cycle=next_cycle, day=old_day, errors=errors,
        )
        if old_cycle == 0 and new.get("world_state", {}).get("goals", {}).get("debt_clear") is not True:
            errors.append("first early payoff must set world_state.goals.debt_clear=true")
        return errors
    if kind == "charge":
        amount = entry.get("charge_amount")
        reason = entry.get("reason")
        if not _is_integer(amount) or amount <= 0:
            errors.append("debt charge_amount must be a positive integer")
            return errors
        if reason not in {"inn", "member_shortage", "rebirth", "crime_fine"}:
            errors.append("debt charge reason must be inn, member_shortage, rebirth, or crime_fine")
        if reason == "crime_fine" and amount != 3000:
            errors.append("crime_fine records only the existing fixed 3000G fine")
        if not isinstance(entry.get("source_id"), str) or not entry["source_id"]:
            errors.append("debt charge requires an auditable source_id")
        if entry.get("contract_id_after") != old_debt.get("contract_id"):
            errors.append("a debt charge cannot replace the active contract")
        expected_principal = old_principal + amount
        if new_debt.get("principal") != expected_principal or new_player.get("debt") != expected_principal:
            errors.append("debt charge must increase principal/player.debt atomically")
        if entry.get("principal_before_payment") != old_principal or entry.get(
            "principal_after_resolution"
        ) != expected_principal:
            errors.append("debt charge ledger principal before/after is inconsistent")
        expected_pending = old_debt.get("collection_pending") is True or (
            _is_integer(old_debt.get("next_collection_day"))
            and new_day >= old_debt["next_collection_day"]
        )
        if new_debt.get("collection_pending") is not expected_pending:
            errors.append("debt charge must preserve/set the due collection gate")
        if not _debt_fields_unchanged(
            old_debt, new_debt, {"principal", "collection_pending", "collection_ledger"},
        ):
            errors.append("debt charge changed unrelated debt fields")
        if new_player.get("gold") != old_gold:
            errors.append("debt charge event may not hide a separate gold delta")
        if reason == "rebirth":
            if not _is_rebirth_resolution(old, new) or amount != _rebirth_fee(old.get("world_state", {})):
                errors.append("rebirth debt charge must match the verified saved danger tier")
        return errors
    return [f"unsupported debt event_kind: {kind}"]


def _validate_benefit_use_transition(old: dict, new: dict) -> list[str] | None:
    old_debt, new_debt = old.get("debt_state", {}), new.get("debt_state", {})
    allowed = {"active_benefits", "benefit_selection"}
    if not _debt_fields_unchanged(old_debt, new_debt, allowed):
        return None
    old_benefits = {
        item.get("benefit_id"): item for item in old_debt.get("active_benefits", [])
        if isinstance(item, dict)
    }
    new_benefits = {
        item.get("benefit_id"): item for item in new_debt.get("active_benefits", [])
        if isinstance(item, dict)
    }
    changed = [key for key in set(old_benefits) | set(new_benefits)
               if old_benefits.get(key) != new_benefits.get(key)]
    if not changed:
        return None
    errors: list[str] = []
    if len(changed) != 1 or changed[0] not in old_benefits or changed[0] not in new_benefits:
        return ["one benefit use may update exactly one existing active benefit"]
    benefit_id = changed[0]
    before, after = old_benefits[benefit_id], new_benefits[benefit_id]
    for key in ("benefit_id", "tier", "activated_day", "contract_cycle_index"):
        if after.get(key) != before.get(key):
            errors.append(f"benefit use cannot change {key}")
    day = new.get("world_state", {}).get("day")
    if not _is_integer(day):
        return errors + ["benefit use requires a valid world day"]
    if before.get("next_available_day") is not None and day < before["next_available_day"]:
        errors.append("Lilith investment benefit is still on cooldown")
    if after.get("uses_count") != before.get("uses_count", 0) + 1:
        errors.append("benefit use must increment uses_count exactly once")
    if after.get("last_used_day") != day:
        errors.append("benefit use must record last_used_day")
    expected_next = None if benefit_id == "facility_investment" else day + 10
    if after.get("next_available_day") != expected_next:
        errors.append("benefit next_available_day does not match its one-time/10-day rule")
    if benefit_id == "facility_investment" and before.get("uses_count", 0) > 0:
        errors.append("facility investment activation is one-time")
    selection = new_debt.get("benefit_selection")
    if not isinstance(selection, dict) or selection.get("benefit_id") != benefit_id:
        errors.append("used benefit must be the selected Lilith investment")
    elif selection.get("switch_available") is not False:
        errors.append("using the selected benefit consumes any free default switch")
    old_investments = old.get("enterprise_state", {}).get("lilith_investments", [])
    new_investments = new.get("enterprise_state", {}).get("lilith_investments", [])
    old_match = next((item for item in old_investments if isinstance(item, dict)
                      and item.get("debt_contract_id") == old_debt.get("contract_id")
                      and item.get("benefit_kind") == benefit_id), None)
    new_match = next((item for item in new_investments if isinstance(item, dict)
                      and item.get("investment_id") == (old_match or {}).get("investment_id")), None)
    if not old_match or not new_match:
        errors.append("benefit use requires its bound enterprise investment record")
    else:
        old_uses, new_uses = old_match.get("uses_remaining"), new_match.get("uses_remaining")
        if _is_integer(old_uses) and new_uses != max(0, old_uses - 1):
            errors.append("benefit use must decrement finite investment uses_remaining")
    return errors


def _validate_debt_transition(old: dict, new: dict, transaction_id: str) -> list[str]:
    """Enforce the M93 due gate, deterministic settlement, and atomic renewal."""
    from debt_contracts import validate_transition as validate_staged_contracts
    errors: list[str] = validate_staged_contracts(old, new, transaction_id)
    old_debt, new_debt = old.get("debt_state"), new.get("debt_state")
    if not isinstance(old_debt, dict) or not isinstance(new_debt, dict):
        return errors + ["debt_state must be present in both saves"]
    old_world = old.get("world_state") if isinstance(old.get("world_state"), dict) else {}
    new_world = new.get("world_state") if isinstance(new.get("world_state"), dict) else {}
    old_day, new_day = old_world.get("day"), new_world.get("day")
    old_ledger, new_ledger = old_debt.get("collection_ledger"), new_debt.get("collection_ledger")
    if not isinstance(old_ledger, list) or not isinstance(new_ledger, list):
        return ["debt collection ledgers must be lists"]
    if new_ledger[:len(old_ledger)] != old_ledger:
        errors.append("debt_state.collection_ledger is append-only")
    added = new_ledger[len(old_ledger):]
    if len(added) > 1:
        errors.append("one commit may resolve at most one debt collection")
        return errors
    if not (_is_integer(old_day) and _is_integer(new_day)):
        return errors
    due_day = old_debt.get("next_collection_day")
    if new_day < old_day:
        errors.append("world_state.day cannot decrease")
    if old_debt.get("collection_pending") is True and new_day != old_day:
        errors.append("a pending Lilith collection blocks time advancement")
    if old_debt.get("collection_pending") is not True and _is_integer(due_day) and new_day > due_day:
        errors.append("time advancement must pause exactly on next_collection_day")

    if added:
        entry = added[0]
        if not isinstance(entry, dict):
            return errors + ["new debt collection ledger entry must be a mapping"]
        if entry.get("event_kind") != "collection":
            errors.extend(_validate_debt_noncollection_event(
                old, new, old_debt, new_debt, entry, transaction_id, old_day, new_day,
            ))
            return errors
        if old_debt.get("collection_pending") is not True:
            errors.append("a debt collection may resolve only after collection_pending=true")
        if entry.get("transaction_id") != transaction_id:
            errors.append("debt collection ledger must use the current transaction_id")
        if entry.get("collection_day") != old_day:
            errors.append("debt collection ledger must use the current paused day")
        payment = entry.get("payment")
        old_gold, new_gold = old.get("player", {}).get("gold"), new.get("player", {}).get("gold")
        old_principal = old_debt.get("principal")
        old_cycle_paid, due = old_debt.get("cycle_paid"), old_debt.get("scheduled_due")
        if not all(_is_integer(value) for value in (payment, old_gold, new_gold, old_principal, old_cycle_paid, due)):
            return errors + ["debt collection numeric fields are invalid"]
        if payment < 0 or payment > old_gold or payment > old_principal:
            errors.append("debt payment must be within available gold and current principal")
        if payment % 100 != 0 and payment != old_principal:
            errors.append("debt payment must use 100G units except the exact final remainder")
        if new_gold != old_gold - payment:
            errors.append("debt collection payment must be the only player.gold delta")
        total_paid = old_cycle_paid + payment
        unpaid = max(0, due - min(due, total_paid))
        paid_off = payment == old_principal
        penalty = 0
        if unpaid > 0 and not paid_off:
            penalty = _ceil_to_10(max(50, (unpaid * 20 + 99) // 100))
            if total_paid == 0:
                penalty = max(100, penalty)
        cycle = old_debt.get("contract_cycle_index")
        if not _is_integer(cycle):
            return errors
        next_cycle = cycle + 1 if paid_off else cycle
        from debt_contracts import principal_schedule
        next_principal = principal_schedule(next_cycle) if paid_off else old_principal - payment + penalty
        next_due = (500 + 250 * next_cycle if paid_off else
                    min(2500 + 500 * cycle, due + 250) if total_paid > 0 else due)
        next_day = old_debt.get("next_collection_day") + 5
        expected_entry = {
            "scheduled_due_before": due, "cycle_paid": total_paid, "unpaid_due": unpaid,
            "penalty": penalty, "principal_before_payment": old_principal,
            "principal_after_resolution": next_principal, "next_collection_day_after": next_day,
            "scheduled_due_after": next_due, "contract_cycle_index_before": cycle,
            "contract_cycle_index_after": next_cycle,
        }
        if entry.get("event_kind") != "collection":
            errors.append("scheduled resolution ledger event_kind must be collection")
        if entry.get("contract_id_before") != old_debt.get("contract_id"):
            errors.append("debt ledger contract_id_before must match the active contract")
        expected_contract_after = (
            f"lilith-debt-cycle-{next_cycle}" if paid_off else old_debt.get("contract_id")
        )
        if entry.get("contract_id_after") != expected_contract_after:
            errors.append("debt ledger contract_id_after must match the resulting contract")
        for key, value in expected_entry.items():
            if entry.get(key) != value:
                errors.append(f"debt collection ledger {key} must be {value}")
        expected_state = {
            "principal": next_principal, "contract_cycle_index": next_cycle,
            "next_collection_day": next_day, "scheduled_due": next_due, "cycle_paid": 0,
            "collection_pending": False, "last_collection_day": old_day,
            "collection_serial": old_debt.get("collection_serial", 0) + 1,
            "positive_payment_collections": old_debt.get("positive_payment_collections", 0) + (total_paid > 0),
            "full_payment_collections": old_debt.get("full_payment_collections", 0) + (total_paid >= due),
            "missed_collections": old_debt.get("missed_collections", 0) + (total_paid == 0),
        }
        for key, value in expected_state.items():
            if new_debt.get(key) != value:
                errors.append(f"debt_state.{key} must be {value!r} after collection")
        if new.get("player", {}).get("debt") != next_principal:
            errors.append("player.debt must mirror resolved debt principal")
        if paid_off:
            if new_debt.get("contract_id") != f"lilith-debt-cycle-{next_cycle}":
                errors.append("payoff renewal must create the deterministic next contract_id")
            _validate_renewal_benefit(
                old, new, next_cycle=next_cycle, day=old_day, errors=errors,
            )
            old_goal = old_world.get("goals", {}).get("debt_clear")
            if cycle == 0 and new_world.get("goals", {}).get("debt_clear") is not True:
                errors.append("first cycle payoff must permanently set world_state.goals.debt_clear=true")
            if old_goal is True and new_world.get("goals", {}).get("debt_clear") is not True:
                errors.append("world_state.goals.debt_clear is irreversible")
        else:
            for key in ("contract_id", "active_benefits", "benefit_selection"):
                if new_debt.get(key) != old_debt.get(key):
                    errors.append(f"debt_state.{key} cannot change without payoff renewal")
        return errors

    if _is_rebirth_resolution(old, new):
        return errors
    benefit_errors = _validate_benefit_use_transition(old, new)
    if benefit_errors is not None:
        errors.extend(benefit_errors)
        return errors
    old_fixed = {key: value for key, value in old_debt.items() if key != "collection_pending"}
    new_fixed = {key: value for key, value in new_debt.items() if key != "collection_pending"}
    if new_fixed != old_fixed:
        errors.append("debt state may change only through a due trigger or one collection ledger append")
    expected_pending = old_debt.get("collection_pending") is True or (
        _is_integer(due_day) and new_day >= due_day
    )
    if new_debt.get("collection_pending") is not expected_pending:
        errors.append("collection_pending must become true exactly when the due day is reached")
    if new.get("player", {}).get("debt") != old.get("player", {}).get("debt"):
        errors.append("player.debt changed without a collection or verified rebirth")
    if old_world.get("goals", {}).get("debt_clear") is True and new_world.get("goals", {}).get("debt_clear") is not True:
        errors.append("world_state.goals.debt_clear is irreversible")
    return errors


def _stat_map(value: Any, label: str, errors: list[str], *, nonnegative: bool = False) -> dict[str, int] | None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return None
    if set(value) != set(STAT_KEYS):
        errors.append(f"{label} must contain exactly {', '.join(STAT_KEYS)}")
        return None
    for key in STAT_KEYS:
        entry = value.get(key)
        if not _is_integer(entry) or (nonnegative and entry < 0):
            suffix = " >= 0" if nonnegative else ""
            errors.append(f"{label}.{key} must be an integer{suffix}")
            return None
    return value


def _validate_meter(value: Any, label: str, errors: list[str]) -> dict | None:
    if not isinstance(value, dict) or set(value) != {"cur", "max"}:
        errors.append(f"{label} must contain exactly cur/max")
        return None
    current, maximum = value.get("cur"), value.get("max")
    if not _is_integer(current) or not _is_integer(maximum) or maximum < 0 or not 0 <= current <= maximum:
        errors.append(f"{label} requires integer 0 <= cur <= max")
        return None
    return value


def _validate_character(character: Any, label: str, errors: list[str], *, player: bool = False) -> None:
    if not isinstance(character, dict):
        errors.append(f"{label} must be a mapping")
        return
    required = (
        "character_version", "character_id", "build_complete", "name", "gender", "age",
        "race", "job", "job_profile", "base_stats", "growth_bonus", "equipment_bonus",
        "fire_bonus", "temporary_modifiers", "effective_stats", "base_lp", "job_lp_bonus",
        "fire_lp_bonus", "temporary_lp_bonus", "lp", "mp", "stats", "equipment",
        "statuses", "buffs", "ero_status",
    )
    for key in required:
        if key not in character:
            errors.append(f"{label} missing required key: {key}")
    if character.get("character_version") != 1:
        errors.append(f"{label}.character_version must be 1")
    try:
        safe_id(str(character.get("character_id") or ""))
    except RuntimeProblem as exc:
        errors.append(f"{label}.character_id: {exc}")
    if not isinstance(character.get("build_complete"), bool):
        errors.append(f"{label}.build_complete must be a boolean")
    for key in ("name", "gender", "race", "job"):
        if not isinstance(character.get(key), str):
            errors.append(f"{label}.{key} must be a string")
    age = character.get("age")
    if age is not None and not _is_adult_value(age, character.get("adult_status")):
        errors.append(f"{label}.age must be >=18 or use an explicit canonical adult status")
    profile = character.get("job_profile")
    if not isinstance(profile, dict):
        errors.append(f"{label}.job_profile must be a mapping")
    else:
        if profile.get("combat_role") not in {"frontline", "hybrid", "backline", "noncombat", "unclassified"}:
            errors.append(f"{label}.job_profile.combat_role is invalid")
        if profile.get("magic_role") not in {"noncaster", "hybrid", "caster", "specialist", "unclassified"}:
            errors.append(f"{label}.job_profile.magic_role is invalid")
        if profile.get("solo_suitability") not in {"good", "difficult", "unsuitable", "unclassified"}:
            errors.append(f"{label}.job_profile.solo_suitability is invalid")
        for key in ("expertise_tags", "party_needs"):
            entries = profile.get(key)
            if not isinstance(entries, list) or not all(isinstance(item, str) and item for item in entries or []):
                errors.append(f"{label}.job_profile.{key} must be a list of non-empty strings")
            elif len(entries) != len(set(entries)):
                errors.append(f"{label}.job_profile.{key} must be unique")
    stat_maps: dict[str, dict[str, int] | None] = {}
    for key in ("base_stats", "growth_bonus", "fire_bonus"):
        stat_maps[key] = _stat_map(character.get(key), f"{label}.{key}", errors, nonnegative=True)
    for key in ("equipment_bonus", "temporary_modifiers"):
        stat_maps[key] = _stat_map(character.get(key), f"{label}.{key}", errors)
    effective = _stat_map(character.get("effective_stats"), f"{label}.effective_stats", errors)
    legacy_stats = _stat_map(character.get("stats"), f"{label}.stats", errors)
    if all(stat_maps.values()) and effective is not None:
        expected = {
            stat: sum(int(stat_maps[group][stat]) for group in stat_maps) for stat in STAT_KEYS
        }
        if effective != expected:
            errors.append(f"{label}.effective_stats does not equal base+growth+equipment+fire+temporary")
        if any(value < 0 for value in effective.values()):
            errors.append(f"{label}.effective_stats may not be negative")
    if effective is not None and legacy_stats is not None and legacy_stats != effective:
        errors.append(f"{label}.stats compatibility mirror must equal effective_stats")
    lp = _validate_meter(character.get("lp"), f"{label}.lp", errors)
    mp = _validate_meter(character.get("mp"), f"{label}.mp", errors)
    from resource_math import validate_stat_lp
    validate_stat_lp(character, label, errors)
    lp_parts = [character.get(key) for key in ("base_lp", "job_lp_bonus", "fire_lp_bonus", "temporary_lp_bonus")]
    lp_parts.append(character.get("stat_lp_bonus", 0))
    if not all(_is_integer(value) for value in lp_parts):
        errors.append(f"{label} LP components must be integers")
    elif any(value < 0 for value in (*lp_parts[:3], lp_parts[-1])):
        errors.append(f"{label} base/job/fire LP components must be >= 0")
    elif lp is not None and lp["max"] != sum(lp_parts):
        errors.append(f"{label}.lp.max does not equal LP components")
    if mp is not None and effective is not None and mp["max"] != effective["int"]:
        errors.append(f"{label}.mp.max must equal effective INT")
    if character.get("build_complete") is True:
        if not character.get("job"):
            errors.append(f"{label}.build_complete requires a job")
        if stat_maps.get("base_stats") is not None and sum(stat_maps["base_stats"].values()) < 6:
            errors.append(f"{label}.build_complete requires allocated base stats")
        if character.get("base_lp", 0) < 1:
            errors.append(f"{label}.build_complete requires base_lp >= 1")
    equipment = character.get("equipment")
    if not isinstance(equipment, dict):
        errors.append(f"{label}.equipment must be a mapping")
    else:
        for key in ("weapon_instance_id", "armor_instance_id", "offhand_instance_id"):
            if equipment.get(key) is not None and not isinstance(equipment.get(key), str):
                errors.append(f"{label}.equipment.{key} must be a string or null")
        fixed = equipment.get("fixed")
        if not isinstance(fixed, list) or len(fixed or []) != len(set(fixed or [])):
            errors.append(f"{label}.equipment.fixed must be a unique list")
    for key in ("statuses", "buffs", "ero_status"):
        if not isinstance(character.get(key), list):
            errors.append(f"{label}.{key} must be a list")
    if player:
        for key in ("gold", "debt"):
            if not _is_integer(character.get(key)) or character[key] < 0:
                errors.append(f"{label}.{key} must be an integer >= 0")


def _validate_skill_records(skills: Any, label: str, errors: list[str]) -> None:
    if not isinstance(skills, list):
        errors.append(f"{label} must be a list")
        return
    seen: set[str] = set()
    for index, skill in enumerate(skills):
        item_label = f"{label}[{index}]"
        if not isinstance(skill, dict):
            errors.append(f"{item_label} must be a mapping")
            continue
        for key in (
            "skill_id", "name", "category", "tier", "stage", "state", "uses", "timing",
            "action_cost", "effect", "from", "origin_job", "requirements",
        ):
            if key not in skill:
                errors.append(f"{item_label} missing {key}")
        skill_id = skill.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            errors.append(f"{item_label}.skill_id must be non-empty")
        elif skill_id in seen:
            errors.append(f"duplicate skill_id in {label}: {skill_id}")
        else:
            seen.add(skill_id)
        if skill.get("category") not in {"technique", "passive", "check"}:
            errors.append(f"{item_label}.category is invalid")
        if skill.get("tier") not in {"basic", "advanced", "master"}:
            errors.append(f"{item_label}.tier is invalid")
        if not _is_integer(skill.get("stage")) or not 1 <= skill["stage"] <= 3:
            errors.append(f"{item_label}.stage must be in 1..3")
        if skill.get("state") not in {"set", "reserve", "dormant_by_job"}:
            errors.append(f"{item_label}.state is invalid")
        timing = skill.get("timing")
        action_cost = skill.get("action_cost")
        if timing not in {"action", "attack_replace", "reaction", "free", "battle_start", "always", "check"}:
            errors.append(f"{item_label}.timing is invalid")
        expected_cost = 1 if timing in {"action", "attack_replace"} else 0
        if action_cost != expected_cost:
            errors.append(f"{item_label}.action_cost must be {expected_cost} for {timing}")
        if not isinstance(skill.get("requirements"), list):
            errors.append(f"{item_label}.requirements must be a list")
        if skill.get("from") == "job" and not isinstance(skill.get("origin_job"), str):
            errors.append(f"{item_label}.origin_job is required for job skills")


def _bag_skill_bonus(data: dict) -> int:
    """Derive shared carrying bonus from the highest active accompanying mastery."""
    best_stage = 0
    player = data.get("player")
    skill_lists: list[Any] = [data.get("skills")]
    if isinstance(player, dict):
        skill_lists.append(player.get("skills"))
    for member in data.get("party", []) if isinstance(data.get("party"), list) else []:
        if isinstance(member, dict):
            skill_lists.append(member.get("skills"))
    for skills in skill_lists:
        if not isinstance(skills, list):
            continue
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name") or "")
            skill_id = str(skill.get("skill_id") or "")
            if name != "荷物の心得" and skill_id not in {
                "bag-mastery", "bag_mastery", "SKILL_BAG_MASTERY",
            }:
                continue
            if skill.get("state") not in {None, "set", "active"}:
                continue
            stage = skill.get("stage", 1)
            if _is_integer(stage):
                best_stage = max(best_stage, min(3, max(1, stage)))
    return {0: 0, 1: 2, 2: 3, 3: 4}[best_stage]


def _inventory_used_slots(data: dict) -> int:
    inventory = data.get("inventory", {})
    stacks = inventory.get("carried_stacks", []) if isinstance(inventory, dict) else []
    total = sum(
        int(stack.get("slot_cost", 0)) for stack in stacks
        if isinstance(stack, dict) and _is_integer(stack.get("slot_cost"))
    )
    for instance in data.get("item_instances", []) if isinstance(data.get("item_instances"), list) else []:
        if isinstance(instance, dict) and instance.get("location") == "bag" and _is_integer(instance.get("slot_cost")):
            total += int(instance["slot_cost"])
    return total


def _validate_inventory_v3(data: dict, errors: list[str]) -> None:
    inventory = data.get("inventory")
    if not isinstance(inventory, dict) or inventory.get("version") != 1:
        errors.append("inventory must be a version 1 mapping")
        return
    bag = inventory.get("bag")
    if not isinstance(bag, dict):
        errors.append("inventory.bag must be a mapping")
        return
    upgrades = bag.get("upgrade_count")
    expected_max = 16 + 4 * upgrades if _is_integer(upgrades) else None
    if bag.get("base_slots") != 16 or not _is_integer(upgrades) or not 0 <= upgrades <= 3:
        errors.append("inventory.bag requires base_slots=16 and upgrade_count in 0..3")
    if expected_max is not None and bag.get("max_slots") != expected_max:
        errors.append("inventory.bag.max_slots must equal 16 + 4*upgrade_count")
    expected_skill_bonus = _bag_skill_bonus(data)
    if bag.get("skill_bonus_slots") != expected_skill_bonus:
        errors.append(
            "inventory.bag.skill_bonus_slots must equal the highest accompanying "
            "荷物の心得 bonus"
        )
    expected_effective = expected_max + expected_skill_bonus if expected_max is not None else None
    if expected_effective is not None and bag.get("effective_max_slots") != expected_effective:
        errors.append(
            "inventory.bag.effective_max_slots must equal max_slots + skill_bonus_slots"
        )
    used = _inventory_used_slots(data)
    if bag.get("used_slots") != used:
        errors.append("inventory.bag.used_slots does not match derived carried slot use")
    if _is_integer(bag.get("effective_max_slots")) and used > bag["effective_max_slots"]:
        errors.append("inventory capacity exceeded; resolve keep/exchange/use before commit")
    stack_ids: set[str] = set()
    stack_by_id: dict[str, dict] = {}
    unique_item_refs: dict[str, str] = {}
    for location, stacks in (
        ("carried_stacks", inventory.get("carried_stacks")),
        ("warehouse.stacks", inventory.get("warehouse", {}).get("stacks") if isinstance(inventory.get("warehouse"), dict) else None),
    ):
        if not isinstance(stacks, list):
            errors.append(f"inventory.{location} must be a list")
            continue
        for index, stack in enumerate(stacks):
            label = f"inventory.{location}[{index}]"
            if not isinstance(stack, dict):
                errors.append(f"{label} must be a mapping")
                continue
            stack_id = stack.get("stack_id")
            try:
                safe_id(str(stack_id or ""))
            except RuntimeProblem as exc:
                errors.append(f"{label}.stack_id: {exc}")
                continue
            if stack_id in stack_ids:
                errors.append(f"duplicate stack_id: {stack_id}")
            stack_ids.add(stack_id)
            stack_by_id[stack_id] = stack
            count, cap = stack.get("count"), stack.get("stack_cap")
            if not _is_integer(count) or not _is_integer(cap) or not 1 <= count <= cap <= 10:
                errors.append(f"{label} requires 1 <= count <= stack_cap <= 10")
            if stack.get("slot_cost") not in {0, 1}:
                errors.append(f"{label}.slot_cost must be 0 or 1")
            category = str(stack.get("category") or "").casefold()
            if category in {"key", "document", "quest_key", "鍵", "文書"} and stack.get("slot_cost") != 0:
                errors.append(f"{label} key/document items must use zero bag slots")
            if category in {"standard", "consumable", "material", "標準", "消耗品", "素材"} and cap != 10:
                errors.append(f"{label} standard items must have stack_cap=10")
            if category in {"unique", "unknown", "固有", "未知"}:
                if count != 1 or cap != 1:
                    errors.append(f"{label} unique/unknown items must be one-per-stack")
                definition_ref = str(stack.get("item_def_id") or "")
                if definition_ref in unique_item_refs:
                    errors.append(
                        f"unique/unknown item appears more than once: {definition_ref} "
                        f"({unique_item_refs[definition_ref]}, {stack_id})"
                    )
                unique_item_refs[definition_ref] = str(stack_id)
            reserved = stack.get("reserved_quantity")
            if not _is_integer(reserved) or not _is_integer(count) or not 0 <= reserved <= count:
                errors.append(f"{label}.reserved_quantity must be within the stack count")
            for key in ("item_def_id", "name", "category"):
                if not isinstance(stack.get(key), str) or not stack[key]:
                    errors.append(f"{label}.{key} must be a non-empty string")
    definitions = data.get("item_definitions")
    if not isinstance(definitions, list):
        errors.append("item_definitions must be a list")
        definitions = []
    definition_ids: set[str] = set()
    definition_by_id: dict[str, dict] = {}
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict) or not isinstance(definition.get("item_def_id"), str):
            errors.append(f"item_definitions[{index}] requires item_def_id")
            continue
        definition_id = definition["item_def_id"]
        try:
            safe_id(definition_id)
        except RuntimeProblem as exc:
            errors.append(f"item_definitions[{index}].item_def_id: {exc}")
        if definition_id in definition_ids:
            errors.append(f"duplicate item_def_id: {definition_id}")
        definition_ids.add(definition_id)
        definition_by_id[definition_id] = definition
        for key in ("name", "category", "specification", "provenance", "balance_anchor"):
            if key not in definition:
                errors.append(f"item_definitions[{index}] missing {key}")
        if not isinstance(definition.get("name"), str) or not definition.get("name"):
            errors.append(f"item_definitions[{index}].name must be non-empty")
        for key in ("specification", "provenance", "balance_anchor"):
            if key in definition and not isinstance(definition.get(key), dict):
                errors.append(f"item_definitions[{index}].{key} must be a mapping")
    instances = data.get("item_instances")
    if not isinstance(instances, list):
        errors.append("item_instances must be a list")
        instances = []
    instance_ids: set[str] = set()
    instance_by_id: dict[str, dict] = {}
    for index, instance in enumerate(instances):
        label = f"item_instances[{index}]"
        if not isinstance(instance, dict):
            errors.append(f"{label} must be a mapping")
            continue
        instance_id = instance.get("instance_id")
        try:
            safe_id(str(instance_id or ""))
        except RuntimeProblem as exc:
            errors.append(f"{label}.instance_id: {exc}")
            continue
        if instance_id in instance_ids:
            errors.append(f"duplicate instance_id: {instance_id}")
        instance_ids.add(instance_id)
        instance_by_id[instance_id] = instance
        if instance.get("location") not in {"bag", "warehouse", "equipped", "escrow", "consumed"}:
            errors.append(f"{label}.location is invalid")
        if instance.get("slot_cost") not in {0, 1}:
            errors.append(f"{label}.slot_cost must be 0 or 1")
        if instance.get("location") == "equipped" and instance.get("slot_cost") != 0:
            errors.append(f"{label} equipped items must use zero bag slots")
        for key in ("item_def_id", "name", "specification_snapshot"):
            if key not in instance:
                errors.append(f"{label} missing {key}")
        if not isinstance(instance.get("item_def_id"), str) or not instance.get("item_def_id"):
            errors.append(f"{label}.item_def_id must be non-empty")
        if not isinstance(instance.get("name"), str) or not instance.get("name"):
            errors.append(f"{label}.name must be non-empty")
        if not isinstance(instance.get("specification_snapshot"), dict):
            errors.append(f"{label}.specification_snapshot must be a mapping")
        definition = definition_by_id.get(instance.get("item_def_id"))
        snapshot = instance.get("specification_snapshot")
        snapshot_category = snapshot.get("category") if isinstance(snapshot, dict) else ""
        category = str(
            (definition or {}).get("category")
            or snapshot_category
            or ""
        ).casefold()
        if category in {"key", "document", "quest_key", "鍵", "文書"} and instance.get("slot_cost") != 0:
            errors.append(f"{label} key/document items must use zero bag slots")
        if category in {"unique", "unknown", "固有", "未知"} and instance.get("location") != "consumed":
            definition_ref = str(instance.get("item_def_id") or "")
            if definition_ref in unique_item_refs:
                errors.append(f"unique/unknown item appears more than once: {definition_ref}")
            unique_item_refs[definition_ref] = str(instance_id)
    warehouse = inventory.get("warehouse")
    if not isinstance(warehouse, dict) or not isinstance(warehouse.get("instance_ids"), list):
        errors.append("inventory.warehouse requires stacks and instance_ids lists")
    else:
        if len(warehouse["instance_ids"]) != len(set(warehouse["instance_ids"])):
            errors.append("inventory.warehouse.instance_ids must be unique")
        for instance_id in warehouse["instance_ids"]:
            if instance_id not in instance_by_id or instance_by_id[instance_id].get("location") != "warehouse":
                errors.append(f"warehouse instance reference is invalid: {instance_id}")
        for instance_id, instance in instance_by_id.items():
            if instance.get("location") == "warehouse" and instance_id not in warehouse["instance_ids"]:
                errors.append(f"warehouse item instance is missing from instance_ids: {instance_id}")
    reserved_totals: dict[str, int] = {}
    reservations = inventory.get("reservations")
    if not isinstance(reservations, list):
        errors.append("inventory.reservations must be a list")
        reservations = []
    reservation_ids: set[str] = set()
    for index, reservation in enumerate(reservations):
        label = f"inventory.reservations[{index}]"
        if not isinstance(reservation, dict):
            errors.append(f"{label} must be a mapping")
            continue
        reservation_id = reservation.get("reservation_id")
        if not isinstance(reservation_id, str) or not reservation_id or reservation_id in reservation_ids:
            errors.append(f"{label}.reservation_id must be non-empty and unique")
        reservation_ids.add(str(reservation_id))
        status = reservation.get("status")
        if status not in {"reserved", "consumed", "returned", "lost"}:
            errors.append(f"{label}.status is invalid")
        stack_id, instance_id = reservation.get("stack_id"), reservation.get("instance_id")
        if bool(stack_id) == bool(instance_id):
            errors.append(f"{label} must reference exactly one stack_id or instance_id")
        quantity = reservation.get("quantity")
        if not _is_integer(quantity) or quantity < 1:
            errors.append(f"{label}.quantity must be >= 1")
        source_id = reservation.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"{label}.source_id must be a non-empty string")
        if status == "reserved" and isinstance(stack_id, str) and _is_integer(quantity):
            if stack_id not in stack_by_id:
                errors.append(f"{label} references missing stack_id: {stack_id}")
            reserved_totals[stack_id] = reserved_totals.get(stack_id, 0) + quantity
        if status == "reserved" and isinstance(instance_id, str):
            instance = instance_by_id.get(instance_id)
            if not instance or instance.get("location") not in {"bag", "warehouse"}:
                errors.append(f"{label} active instance reservation requires bag/warehouse location")
            if quantity != 1:
                errors.append(f"{label} an item instance reservation must have quantity=1")
    for stack_id, stack in stack_by_id.items():
        if stack.get("reserved_quantity") != reserved_totals.get(stack_id, 0):
            errors.append(f"stack reserved_quantity does not match active reservations: {stack_id}")
    character_ids = {
        character.get("character_id") for character in [data.get("player"), *(data.get("party") or []), *(data.get("inn_reserve") or [])]
        if isinstance(character, dict)
    }
    equipped_refs: dict[str, tuple[str, str]] = {}
    for character in [data.get("player"), *(data.get("party") or []), *(data.get("inn_reserve") or [])]:
        if not isinstance(character, dict) or not isinstance(character.get("equipment"), dict):
            continue
        for slot in ("weapon_instance_id", "armor_instance_id", "offhand_instance_id"):
            instance_id = character["equipment"].get(slot)
            if instance_id is None:
                continue
            if instance_id in equipped_refs:
                errors.append(f"item instance equipped more than once: {instance_id}")
            equipped_refs[instance_id] = (str(character.get("character_id")), slot)
            instance = instance_by_id.get(instance_id)
            if not instance or instance.get("location") != "equipped" or instance.get("owner_character_id") != character.get("character_id"):
                errors.append(f"equipped instance reference is inconsistent: {instance_id}")
    for instance in instances:
        if isinstance(instance, dict) and instance.get("location") == "equipped":
            if instance.get("instance_id") not in equipped_refs or instance.get("owner_character_id") not in character_ids:
                errors.append(f"orphan equipped instance: {instance.get('instance_id')}")
    active_reserved_instances = [
        reservation.get("instance_id") for reservation in reservations
        if isinstance(reservation, dict) and reservation.get("status") == "reserved"
        and isinstance(reservation.get("instance_id"), str)
    ]
    if len(active_reserved_instances) != len(set(active_reserved_instances)):
        errors.append("an item instance may have at most one active reservation")


def _validate_ammo_v3(data: dict, errors: list[str]) -> None:
    ammo = data.get("ammo")
    if not isinstance(ammo, dict) or set(ammo) != {"pools", "weapon_loads"}:
        errors.append("ammo must contain exactly pools and weapon_loads")
        return
    pool_types: set[str] = set()
    for index, pool in enumerate(ammo["pools"] if isinstance(ammo.get("pools"), list) else []):
        if not isinstance(pool, dict) or not isinstance(pool.get("ammo_type"), str) or not pool["ammo_type"]:
            errors.append(f"ammo.pools[{index}] is invalid")
            continue
        if pool["ammo_type"] in pool_types:
            errors.append(f"duplicate ammo pool: {pool['ammo_type']}")
        pool_types.add(pool["ammo_type"])
        if not _is_integer(pool.get("count")) or pool["count"] < 0:
            errors.append(f"ammo.pools[{index}].count must be >= 0")
    if not isinstance(ammo.get("pools"), list) or not isinstance(ammo.get("weapon_loads"), list):
        errors.append("ammo pools and weapon_loads must be lists")
        return
    instance_ids = {
        item.get("instance_id") for item in data.get("item_instances", []) if isinstance(item, dict)
    }
    seen: set[str] = set()
    for index, load in enumerate(ammo["weapon_loads"]):
        if not isinstance(load, dict):
            errors.append(f"ammo.weapon_loads[{index}] must be a mapping")
            continue
        weapon_id = load.get("weapon_instance_id")
        if not isinstance(weapon_id, str) or weapon_id not in instance_ids or weapon_id in seen:
            errors.append(f"ammo.weapon_loads[{index}].weapon_instance_id is invalid or duplicate")
        seen.add(str(weapon_id))
        loaded, capacity = load.get("loaded"), load.get("capacity")
        if not _is_integer(loaded) or not _is_integer(capacity) or not 0 <= loaded <= capacity:
            errors.append(f"ammo.weapon_loads[{index}] requires 0 <= loaded <= capacity")
        if not isinstance(load.get("ammo_type"), str) or not load["ammo_type"]:
            errors.append(f"ammo.weapon_loads[{index}].ammo_type must be non-empty")


def _quest_contract_immutable(contract: Any) -> Any:
    if not isinstance(contract, dict):
        return contract
    result = {key: copy.deepcopy(value) for key, value in contract.items() if key != "components"}
    result["components"] = []
    for component in contract.get("components", []) if isinstance(contract.get("components"), list) else []:
        if isinstance(component, dict):
            result["components"].append({key: copy.deepcopy(value) for key, value in component.items() if key != "state"})
    return result


def _quest_immutable_payload(card: dict) -> dict:
    payload: dict[str, Any] = {}
    for key, value in card.items():
        if key in QUEST_MUTABLE_KEYS or key == "immutable_hash":
            continue
        payload[key] = _quest_contract_immutable(value) if key == "reward_contract" else copy.deepcopy(value)
    return payload


def _quest_hash(card: dict) -> str:
    raw = json.dumps(_quest_immutable_payload(card), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(raw.encode("utf-8"))


def _validate_quest_card_v3(card: Any, label: str, errors: list[str]) -> None:
    if card is None:
        return
    if not isinstance(card, dict):
        errors.append(f"{label} must be null or a mapping")
        return
    for key in ("quest_id", "immutable_hash", "progress", "amendments", "reward_contract"):
        if key not in card:
            errors.append(f"{label} missing {key}")
    try:
        safe_id(str(card.get("quest_id") or ""))
    except RuntimeProblem as exc:
        errors.append(f"{label}.quest_id: {exc}")
    if not isinstance(card.get("progress"), dict):
        errors.append(f"{label}.progress must be a mapping")
    if not isinstance(card.get("amendments"), list):
        errors.append(f"{label}.amendments must be a list")
    expected = _quest_hash(card)
    if card.get("immutable_hash") != expected:
        errors.append(f"{label}.immutable_hash does not match fixed facts and contract")


def _validate_quest_transition(old: dict, new: dict, transaction_id: str) -> list[str]:
    errors: list[str] = []
    pairs = (
        (
            old.get("world_state", {}).get("quest_card"),
            new.get("world_state", {}).get("quest_card"),
            "world_state.quest_card",
        ),
        (old.get("active_event"), new.get("active_event"), "active_event"),
    )
    for before, after, label in pairs:
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        if before.get("quest_id") != after.get("quest_id"):
            errors.append(f"{label} cannot replace an active quest_id; close it first")
            continue
        old_amendments, new_amendments = before.get("amendments"), after.get("amendments")
        if not isinstance(old_amendments, list) or not isinstance(new_amendments, list):
            continue
        if new_amendments[:len(old_amendments)] != old_amendments:
            errors.append(f"{label}.amendments is append-only")
        immutable_changed = _quest_immutable_payload(before) != _quest_immutable_payload(after)
        added = new_amendments[len(old_amendments):]
        if immutable_changed:
            if len(added) != 1 or not isinstance(added[0], dict):
                errors.append(f"{label} fixed facts/contract require exactly one renegotiation amendment")
                continue
            amendment = added[0]
            if amendment.get("transaction_id") != transaction_id:
                errors.append(f"{label} amendment must use the current transaction_id")
            if amendment.get("before_hash") != before.get("immutable_hash"):
                errors.append(f"{label} amendment before_hash must match the prior quest")
            if amendment.get("after_hash") != after.get("immutable_hash"):
                errors.append(f"{label} amendment after_hash must match the renegotiated quest")
            if not isinstance(amendment.get("reason"), str) or not amendment["reason"]:
                errors.append(f"{label} amendment requires a non-empty reason")
        elif added:
            errors.append(f"{label} cannot append an amendment without changing fixed terms")
    return errors


def _validate_debt_state(data: dict, errors: list[str]) -> None:
    from debt_contracts import validate_state as validate_staged_contracts
    validate_staged_contracts(data, errors)
    debt = data.get("debt_state")
    if not isinstance(debt, dict) or debt.get("version") != 1:
        errors.append("debt_state must be a version 1 mapping")
        return
    integer_fields = (
        "contract_cycle_index", "principal", "next_collection_day", "scheduled_due", "cycle_paid",
        "collection_serial", "positive_payment_collections", "full_payment_collections", "missed_collections",
    )
    for key in integer_fields:
        if not _is_integer(debt.get(key)) or debt[key] < 0:
            errors.append(f"debt_state.{key} must be an integer >= 0")
    if _is_integer(debt.get("principal")) and debt["principal"] < 1:
        errors.append("debt_state.principal must remain >= 1 because payoff renews atomically")
    if _is_integer(debt.get("next_collection_day")) and debt["next_collection_day"] < 1:
        errors.append("debt_state.next_collection_day must be >= 1")
    if debt.get("interval_days") != 5:
        errors.append("debt_state.interval_days must be 5")
    cycle = debt.get("contract_cycle_index") if _is_integer(debt.get("contract_cycle_index")) else 0
    due_cap = 2500 + 500 * cycle
    if _is_integer(debt.get("scheduled_due")) and not 500 <= debt["scheduled_due"] <= due_cap:
        errors.append(f"debt_state.scheduled_due must be within 500..{due_cap} for this cycle")
    if not isinstance(debt.get("collection_pending"), bool):
        errors.append("debt_state.collection_pending must be a boolean")
    if not isinstance(debt.get("contract_id"), str) or not debt["contract_id"]:
        errors.append("debt_state.contract_id must be non-empty")
    if debt.get("last_collection_day") is not None and (
        not _is_integer(debt.get("last_collection_day")) or debt["last_collection_day"] < 1
    ):
        errors.append("debt_state.last_collection_day must be null or an integer >= 1")
    if not isinstance(debt.get("collection_ledger"), list):
        errors.append("debt_state.collection_ledger must be a list")
    else:
        ids = [entry.get("collection_id") for entry in debt["collection_ledger"] if isinstance(entry, dict)]
        if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
            errors.append("debt_state collection ledger IDs must be non-empty and unique")
        if len(ids) != len(debt["collection_ledger"]):
            errors.append("every debt collection ledger entry must be a mapping with collection_id")
        collection_count = sum(
            1 for entry in debt["collection_ledger"]
            if isinstance(entry, dict) and entry.get("event_kind") == "collection"
        )
        if (_is_integer(debt.get("collection_serial"))
                and debt["collection_serial"] != collection_count):
            errors.append("debt_state.collection_serial must equal scheduled collection count")
        transaction_ids: set[str] = set()
        for index, entry in enumerate(debt["collection_ledger"]):
            if not isinstance(entry, dict):
                continue
            transaction_id = entry.get("transaction_id")
            if not isinstance(transaction_id, str) or not transaction_id:
                errors.append(f"debt_state.collection_ledger[{index}].transaction_id is required")
            elif transaction_id in transaction_ids:
                errors.append(f"duplicate debt collection transaction_id: {transaction_id}")
            transaction_ids.add(str(transaction_id))
            event_kind = entry.get("event_kind")
            if event_kind not in {"collection", "payment", "early_payoff", "charge"}:
                errors.append(f"debt_state.collection_ledger[{index}].event_kind is invalid")
            for key in ("contract_id_before", "contract_id_after"):
                if not isinstance(entry.get(key), str) or not entry[key]:
                    errors.append(f"debt_state.collection_ledger[{index}].{key} is required")
            common_numeric = ("collection_day", "principal_before_payment", "principal_after_resolution")
            collection_numeric = (
                "scheduled_due_before", "cycle_paid", "payment", "unpaid_due", "penalty",
                "next_collection_day_after", "scheduled_due_after",
                "contract_cycle_index_before", "contract_cycle_index_after",
            ) if event_kind == "collection" else ()
            payment_numeric = ("payment",) if event_kind in {"payment", "early_payoff"} else ()
            charge_numeric = ("charge_amount",) if event_kind == "charge" else ()
            for key in common_numeric + collection_numeric + payment_numeric + charge_numeric:
                if not _is_integer(entry.get(key)) or entry[key] < 0:
                    errors.append(f"debt_state.collection_ledger[{index}].{key} must be >= 0")
    if not isinstance(debt.get("active_benefits"), list) or not isinstance(debt.get("benefit_selection"), dict):
        errors.append("debt_state benefits must be structured lists/mappings")
    else:
        benefit_ids: set[str] = set()
        for index, benefit in enumerate(debt["active_benefits"]):
            if not isinstance(benefit, dict):
                errors.append(f"debt_state.active_benefits[{index}] must be a mapping")
                continue
            benefit_id = benefit.get("benefit_id")
            if benefit_id not in {
                "facility_investment", "procurement_network", "expedition_guarantee",
            }:
                errors.append(f"debt_state.active_benefits[{index}].benefit_id is invalid")
            if benefit_id in benefit_ids:
                errors.append(f"duplicate active debt benefit: {benefit_id}")
            benefit_ids.add(str(benefit_id))
            if not _is_integer(benefit.get("tier")) or benefit["tier"] < 1:
                errors.append(f"debt_state.active_benefits[{index}].tier must be >= 1")
            if not _is_integer(benefit.get("uses_count")) or benefit["uses_count"] < 0:
                errors.append(f"debt_state.active_benefits[{index}].uses_count must be >= 0")
            last_used = benefit.get("last_used_day")
            next_available = benefit.get("next_available_day")
            for key, value in (("last_used_day", last_used), ("next_available_day", next_available)):
                if value is not None and (not _is_integer(value) or value < 1):
                    errors.append(f"debt_state.active_benefits[{index}].{key} must be null or >= 1")
            if _is_integer(last_used) and _is_integer(next_available) and next_available < last_used:
                errors.append(f"debt_state.active_benefits[{index}] cooldown cannot precede last use")
            if benefit_id == "facility_investment":
                if benefit.get("uses_count", 0) > 1 or next_available is not None:
                    errors.append(f"debt_state.active_benefits[{index}] facility use is one-time")
            elif benefit.get("uses_count", 0) > 0:
                if not _is_integer(last_used) or next_available != last_used + 10:
                    errors.append(
                        f"debt_state.active_benefits[{index}] recurring benefit requires a 10-day cooldown"
                    )
        selection = debt["benefit_selection"]
        if selection.get("benefit_id") not in {
            "", "facility_investment", "procurement_network", "expedition_guarantee",
        }:
            errors.append("debt_state.benefit_selection.benefit_id is invalid")
        if selection.get("source") not in {"player", "default"}:
            errors.append("debt_state.benefit_selection.source must be player or default")
        if not isinstance(selection.get("switch_available"), bool):
            errors.append("debt_state.benefit_selection.switch_available must be boolean")
        if selection.get("activated_day") is not None and (
            not _is_integer(selection.get("activated_day")) or selection["activated_day"] < 1
        ):
            errors.append("debt_state.benefit_selection.activated_day must be null or >= 1")
        if selection.get("benefit_id") and selection.get("benefit_id") not in benefit_ids:
            errors.append("debt_state.benefit_selection must reference an active benefit")
        investments = data.get("enterprise_state", {}).get("lilith_investments", [])
        if isinstance(investments, list):
            investment_kinds = {
                item.get("benefit_kind") for item in investments if isinstance(item, dict)
            }
            for benefit_id in benefit_ids:
                if benefit_id not in investment_kinds:
                    errors.append(f"active debt benefit lacks Lilith investment: {benefit_id}")
    player = data.get("player")
    if isinstance(player, dict) and debt.get("principal") != player.get("debt"):
        errors.append("debt_state.principal must equal player.debt")
    world = data.get("world_state")
    goals = world.get("goals") if isinstance(world, dict) else None
    if cycle > 0 and (
        not isinstance(goals, dict) or goals.get("debt_clear") is not True
    ):
        errors.append(
            "world_state.goals.debt_clear must remain true after the first debt payoff"
        )
    day = world.get("day") if isinstance(world, dict) else None
    due_day = debt.get("next_collection_day")
    if _is_integer(day) and _is_integer(due_day):
        if day >= due_day and debt.get("collection_pending") is not True:
            errors.append("debt collection is due; collection_pending must block further time advancement")
        if debt.get("collection_pending") is True and day < due_day:
            errors.append("debt collection cannot be pending before next_collection_day")


def _validate_enterprise_state(data: dict, errors: list[str]) -> None:
    state = data.get("enterprise_state")
    required = (
        "businesses", "discoveries", "research_projects", "recipes", "order_book",
        "commerce_ledger", "reputation_ledger", "lilith_investments",
        "community_threads", "aftermath_seeds",
    )
    if not isinstance(state, dict) or state.get("version") != 1:
        errors.append("enterprise_state must be a version 1 mapping")
        return
    for key in required:
        if not isinstance(state.get(key), list):
            errors.append(f"enterprise_state.{key} must be a list")
    id_fields = {
        "businesses": "business_id", "discoveries": "discovery_id", "research_projects": "project_id",
        "recipes": "recipe_id", "order_book": "order_id", "commerce_ledger": "transaction_id",
        "reputation_ledger": "reputation_tx_id", "lilith_investments": "investment_id",
        "community_threads": "thread_id", "aftermath_seeds": "seed_id",
    }
    for collection, id_field in id_fields.items():
        entries = state.get(collection)
        if not isinstance(entries, list):
            continue
        ids = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get(id_field), str) or not entry[id_field]:
                errors.append(f"enterprise_state.{collection}[{index}] requires {id_field}")
            else:
                ids.append(entry[id_field])
        if len(ids) != len(set(ids)):
            errors.append(f"enterprise_state.{collection} IDs must be unique")
    reservation_ids = {
        entry.get("reservation_id") for entry in data.get("inventory", {}).get("reservations", [])
        if isinstance(entry, dict) and isinstance(entry.get("reservation_id"), str)
    } if isinstance(data.get("inventory"), dict) else set()
    reservations_by_id = {
        entry.get("reservation_id"): entry
        for entry in data.get("inventory", {}).get("reservations", [])
        if isinstance(entry, dict) and isinstance(entry.get("reservation_id"), str)
    } if isinstance(data.get("inventory"), dict) else {}
    instance_by_id = {
        entry.get("instance_id"): entry for entry in data.get("item_instances", [])
        if isinstance(entry, dict) and isinstance(entry.get("instance_id"), str)
    }
    definition_by_id = {
        entry.get("item_def_id"): entry for entry in data.get("item_definitions", [])
        if isinstance(entry, dict) and isinstance(entry.get("item_def_id"), str)
    }
    discovery_ids = {
        entry.get("discovery_id") for entry in state.get("discoveries", [])
        if isinstance(entry, dict) and isinstance(entry.get("discovery_id"), str)
    }
    for index, discovery in enumerate(state.get("discoveries", [])):
        if not isinstance(discovery, dict):
            continue
        references = discovery.get("item_instance_ids")
        if not isinstance(references, list) or not references:
            errors.append(f"enterprise_state.discoveries[{index}].item_instance_ids must be non-empty")
            continue
        for instance_id in references:
            instance = instance_by_id.get(instance_id)
            if not instance or instance.get("location") not in {"bag", "warehouse"}:
                errors.append(f"discovery references missing/unowned item instance: {instance_id}")
                continue
            provenance = instance.get("provenance")
            if not isinstance(provenance, dict) or provenance.get("discovery_id") != discovery.get("discovery_id"):
                errors.append(f"discovery item instance provenance mismatch: {instance_id}")
    for definition in definition_by_id.values():
        provenance = definition.get("provenance")
        if isinstance(provenance, dict) and provenance.get("discovery_id") is not None:
            if provenance.get("discovery_id") not in discovery_ids:
                errors.append(f"item definition references missing discovery: {definition.get('item_def_id')}")
    project_ids = {
        entry.get("project_id") for entry in state.get("research_projects", [])
        if isinstance(entry, dict) and isinstance(entry.get("project_id"), str)
    }
    for index, project in enumerate(state.get("research_projects", [])):
        if not isinstance(project, dict):
            continue
        discovery_id = project.get("discovery_id")
        if discovery_id is not None and discovery_id not in discovery_ids:
            errors.append(f"research project references missing discovery: {discovery_id}")
        refs = project.get("reservation_ids", [])
        if not isinstance(refs, list):
            errors.append(f"enterprise_state.research_projects[{index}].reservation_ids must be a list")
            continue
        for reservation_id in refs:
            reservation = reservations_by_id.get(reservation_id)
            if not reservation or reservation.get("source_id") != project.get("project_id"):
                errors.append(f"research project reservation source mismatch: {reservation_id}")
    for recipe in state.get("recipes", []):
        if not isinstance(recipe, dict):
            continue
        if recipe.get("source_project_id") is not None and recipe["source_project_id"] not in project_ids:
            errors.append(f"recipe references missing research project: {recipe['source_project_id']}")
        if recipe.get("source_discovery_id") is not None and recipe["source_discovery_id"] not in discovery_ids:
            errors.append(f"recipe references missing discovery: {recipe['source_discovery_id']}")
    for index, order in enumerate(state.get("order_book", [])):
        if not isinstance(order, dict):
            continue
        references = order.get("reservation_ids", [])
        if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
            errors.append(f"enterprise_state.order_book[{index}].reservation_ids must be a string list")
        else:
            for reservation_id in references:
                if reservation_id not in reservation_ids:
                    errors.append(
                        f"enterprise_state.order_book[{index}] references missing reservation: "
                        f"{reservation_id}"
                    )
    order_by_id = {
        entry.get("order_id"): entry for entry in state.get("order_book", [])
        if isinstance(entry, dict) and isinstance(entry.get("order_id"), str)
    }
    for index, business in enumerate(state.get("businesses", [])):
        if not isinstance(business, dict):
            continue
        if business.get("warehouse_ref") != "inventory.warehouse":
            errors.append(f"enterprise_state.businesses[{index}].warehouse_ref must be inventory.warehouse")
        active_order_id = business.get("active_order_id")
        if active_order_id is not None:
            order = order_by_id.get(active_order_id)
            if (not order or order.get("business_id") != business.get("business_id")
                    or order.get("status") != "active"):
                errors.append(f"business active_order_id is missing or owned elsewhere: {active_order_id}")
    business_by_id = {
        entry.get("business_id"): entry for entry in state.get("businesses", [])
        if isinstance(entry, dict) and isinstance(entry.get("business_id"), str)
    }
    for order_id, order in order_by_id.items():
        business_id = order.get("business_id")
        if order.get("status") == "active" and business_id is not None:
            business = business_by_id.get(business_id)
            if not business or business.get("active_order_id") != order_id:
                errors.append(f"active order is not the business canonical active_order_id: {order_id}")
    quest_cards = []
    world = data.get("world_state")
    if isinstance(world, dict):
        quest_cards.append(world.get("quest_card"))
    quest_cards.append(data.get("active_event"))
    for card in quest_cards:
        if not isinstance(card, dict) or not isinstance(card.get("commission"), dict):
            continue
        order_id = card["commission"].get("order_id")
        if order_id is not None and order_id not in order_by_id:
            errors.append(f"quest commission references missing canonical order: {order_id}")
    debt_contract_ids = {
        str(data.get("debt_state", {}).get("contract_id") or ""),
        *{
            str(entry.get("contract_id_after") or "")
            for entry in data.get("debt_state", {}).get("collection_ledger", [])
            if isinstance(entry, dict)
        },
        *{
            str(entry.get("contract_id_before") or "")
            for entry in data.get("debt_state", {}).get("collection_ledger", [])
            if isinstance(entry, dict)
        },
    } if isinstance(data.get("debt_state"), dict) else set()
    for index, investment in enumerate(state.get("lilith_investments", [])):
        if not isinstance(investment, dict):
            continue
        if investment.get("benefit_kind") not in {
            "facility_investment", "procurement_network", "expedition_guarantee",
        }:
            errors.append(f"enterprise_state.lilith_investments[{index}].benefit_kind is invalid")
        if investment.get("status") not in {"active", "exhausted", "revoked"}:
            errors.append(f"enterprise_state.lilith_investments[{index}].status is invalid")
        if investment.get("debt_contract_id") not in debt_contract_ids:
            errors.append(
                f"enterprise_state.lilith_investments[{index}] references unknown debt contract"
            )
        for key in ("investment_id", "asset_or_entitlement_id", "description"):
            if not isinstance(investment.get(key), str) or not investment[key]:
                errors.append(f"enterprise_state.lilith_investments[{index}].{key} is required")
        uses = investment.get("uses_remaining")
        if uses is not None and (not _is_integer(uses) or uses < 0):
            errors.append(
                f"enterprise_state.lilith_investments[{index}].uses_remaining must be null or >= 0"
            )
    for index, seed in enumerate(state.get("aftermath_seeds", [])):
        if not isinstance(seed, dict):
            continue
        if seed.get("status") not in {"dormant", "used", "retired"}:
            errors.append(f"enterprise_state.aftermath_seeds[{index}].status is invalid")
        if seed.get("forbidden_unresolved_mystery") is not True:
            errors.append(
                f"enterprise_state.aftermath_seeds[{index}].forbidden_unresolved_mystery must be true"
            )
        if not _is_integer(seed.get("eligible_after_day")) or seed["eligible_after_day"] < 1:
            errors.append(f"enterprise_state.aftermath_seeds[{index}].eligible_after_day must be >= 1")


def _validate_inventory_enterprise_transition(old: dict, new: dict) -> list[str]:
    errors: list[str] = []

    def by_id(entries: Any, key: str) -> dict[str, dict]:
        return {
            item[key]: item for item in entries if isinstance(item, dict) and isinstance(item.get(key), str)
        } if isinstance(entries, list) else {}

    old_defs = by_id(old.get("item_definitions"), "item_def_id")
    new_defs = by_id(new.get("item_definitions"), "item_def_id")
    for item_id, definition in old_defs.items():
        if new_defs.get(item_id) != definition:
            errors.append(f"item definition is immutable and cannot be removed/changed: {item_id}")
    old_instances = by_id(old.get("item_instances"), "instance_id")
    new_instances = by_id(new.get("item_instances"), "instance_id")
    reservations_old = by_id(old.get("inventory", {}).get("reservations"), "reservation_id")
    reservations_new = by_id(new.get("inventory", {}).get("reservations"), "reservation_id")
    active_reserved_instances = {
        item.get("instance_id") for item in reservations_old.values()
        if item.get("status") == "reserved" and isinstance(item.get("instance_id"), str)
    }
    for instance_id, before in old_instances.items():
        after = new_instances.get(instance_id)
        if after is None:
            errors.append(f"item instance history cannot be removed: {instance_id}")
            continue
        immutable_keys = set(before) - {"location", "owner_character_id"}
        if any(after.get(key) != before.get(key) for key in immutable_keys):
            errors.append(f"item instance specification is immutable: {instance_id}")
        if before.get("location") == "consumed" and after != before:
            errors.append(f"consumed item instance is terminal: {instance_id}")
        if instance_id in active_reserved_instances and (
            after.get("location") != before.get("location")
            or after.get("owner_character_id") != before.get("owner_character_id")
        ):
            errors.append(f"reserved item instance cannot be used/sold/moved: {instance_id}")
    for reservation_id, before in reservations_old.items():
        after = reservations_new.get(reservation_id)
        if after is None:
            errors.append(f"inventory reservation history cannot be removed: {reservation_id}")
            continue
        for key in ("reservation_id", "source_id", "stack_id", "instance_id", "quantity"):
            if after.get(key) != before.get(key):
                errors.append(f"inventory reservation field is immutable: {reservation_id}.{key}")
        if before.get("status") in {"consumed", "returned", "lost"} and after != before:
            errors.append(f"terminal inventory reservation is immutable: {reservation_id}")
    old_stacks = by_id(
        list(old.get("inventory", {}).get("carried_stacks", []))
        + list(old.get("inventory", {}).get("warehouse", {}).get("stacks", [])), "stack_id",
    )
    new_stacks = by_id(
        list(new.get("inventory", {}).get("carried_stacks", []))
        + list(new.get("inventory", {}).get("warehouse", {}).get("stacks", [])), "stack_id",
    )
    active_reserved_stacks = {
        item.get("stack_id") for item in reservations_old.values()
        if item.get("status") == "reserved" and isinstance(item.get("stack_id"), str)
    }
    for stack_id in active_reserved_stacks:
        if stack_id not in new_stacks:
            errors.append(f"reserved item stack cannot be removed: {stack_id}")

    old_enterprise = old.get("enterprise_state", {})
    new_enterprise = new.get("enterprise_state", {})
    for key in ("commerce_ledger", "reputation_ledger"):
        before, after = old_enterprise.get(key), new_enterprise.get(key)
        if isinstance(before, list) and isinstance(after, list) and after[:len(before)] != before:
            errors.append(f"enterprise_state.{key} is append-only")
    old_orders = by_id(old_enterprise.get("order_book"), "order_id")
    new_orders = by_id(new_enterprise.get("order_book"), "order_id")
    mutable_order = {"stage", "status", "reservation_ids", "aftermath_seed_ids", "progress", "checks_used", "result"}
    for order_id, before in old_orders.items():
        after = new_orders.get(order_id)
        if after is None:
            errors.append(f"canonical order history cannot be removed: {order_id}")
            continue
        for key, value in before.items():
            if key not in mutable_order and after.get(key) != value:
                errors.append(f"order fixed field is immutable: {order_id}.{key}")
    old_investments = by_id(old_enterprise.get("lilith_investments"), "investment_id")
    new_investments = by_id(new_enterprise.get("lilith_investments"), "investment_id")
    for investment_id, before in old_investments.items():
        after = new_investments.get(investment_id)
        if after is None:
            errors.append(f"Lilith investment history cannot be removed: {investment_id}")
            continue
        for key, value in before.items():
            if key not in {"uses_remaining", "status"} and after.get(key) != value:
                errors.append(f"Lilith investment fixed field is immutable: {investment_id}.{key}")
    return errors


def validate_save_data(data: Any) -> tuple[list[str], list[str]]:
    """Validate save v3 semantics without relying on an optional jsonschema package."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["save root must be a mapping"], warnings
    if "runtime_cast_rules" in data:
        errors.append("runtime_cast_rules is a derived display-only view, not a save field")
    if data.get("schema") != CURRENT_SCHEMA:
        errors.append(f"schema must be {CURRENT_SCHEMA}; got {data.get('schema')!r}")
    if data.get("schema_version") != CURRENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {CURRENT_SCHEMA_VERSION}")
    for key in SAVE_REQUIRED_KEYS:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if not isinstance(data.get("game_version"), str) or not data.get("game_version"):
        errors.append("game_version must be a non-empty string")
    campaign_id = data.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id:
        errors.append("campaign_id must be a non-empty string")
    else:
        try:
            safe_id(campaign_id)
        except RuntimeProblem as exc:
            errors.append(str(exc))
    for key in ("created_at", "updated_at"):
        if not _valid_iso(data.get(key)):
            errors.append(f"{key} must be a non-empty ISO 8601 timestamp")
    revision = data.get("save_revision")
    if not _is_integer(revision) or revision < 0:
        errors.append("save_revision must be an integer >= 0")
    if not isinstance(data.get("content_manifest_hash"), str):
        errors.append("content_manifest_hash must be a string")
    if not isinstance(data.get("save_format_origin"), str):
        errors.append("save_format_origin must be a string")

    transaction = _require_mapping(data, "transaction", errors)
    if transaction is not None:
        for key in ("last_transaction_id", "previous_revision_hash", "last_candidate_hash"):
            if not isinstance(transaction.get(key), str):
                errors.append(f"transaction.{key} must be a string")
        turn = transaction.get("last_committed_turn")
        if not _is_integer(turn) or turn < 0:
            errors.append("transaction.last_committed_turn must be an integer >= 0")
        applied_ids = transaction.get("applied_transaction_ids")
        if not isinstance(applied_ids, list) or not all(
            isinstance(item, str) and item for item in (applied_ids or [])
        ):
            errors.append("transaction.applied_transaction_ids must be a list of non-empty strings")
        elif len(applied_ids) != len(set(applied_ids)):
            errors.append("transaction.applied_transaction_ids must be unique")
        else:
            for item in applied_ids:
                try:
                    safe_id(item)
                except RuntimeProblem as exc:
                    errors.append(f"transaction.applied_transaction_ids: {exc}")
    hearing = _require_mapping(data, "hearing_progress", errors)
    if hearing is not None:
        hearing_status = hearing.get("status")
        if hearing_status not in {"pending", "in_progress", "complete"}:
            errors.append("hearing_progress.status is invalid")
        step = hearing.get("current_step")
        if not _is_integer(step) or not 1 <= step <= 7:
            errors.append("hearing_progress.current_step must be an integer in 1..7")
        completed = hearing.get("completed_steps")
        if not isinstance(completed, list) or len({str(item) for item in completed or []}) != len(completed or []):
            errors.append("hearing_progress.completed_steps must be a unique list")
        else:
            ordered_steps = ["playmode", "profile", "body_profile", "desire", "partner", "style"]
            if completed != ordered_steps[:len(completed)]:
                errors.append("hearing_progress.completed_steps must be an ordered prefix")
            expected_step = len(completed) + 1
            if _is_integer(step) and step != expected_step:
                errors.append(
                    f"hearing_progress.current_step must be {expected_step} for completed_steps"
                )
            if hearing_status == "pending" and completed:
                errors.append("pending hearing cannot have completed steps")
            if hearing_status == "complete" and completed != ordered_steps:
                errors.append("complete hearing requires all six completed steps")
            if completed == ordered_steps and hearing_status != "complete":
                errors.append("all six hearing steps require status=complete")
            if completed and completed != ordered_steps and hearing_status != "in_progress":
                errors.append("partially completed hearing requires status=in_progress")
        for key in ("widget_ids", "widget_state_versions"):
            if not isinstance(hearing.get(key), dict):
                errors.append(f"hearing_progress.{key} must be a mapping")
    script = _require_mapping(data, "active_script", errors)
    if script is not None:
        if not isinstance(script.get("id"), str) or not isinstance(script.get("checkpoint"), str):
            errors.append("active_script.id and checkpoint must be strings")
        if script.get("status") not in {"idle", "in_progress", "complete"}:
            errors.append("active_script.status is invalid")
        if not _is_integer(script.get("cursor")) or script["cursor"] < 0:
            errors.append("active_script.cursor must be an integer >= 0")
    state = _require_mapping(data, "runtime_state", errors)
    if state is not None:
        for key in ("active_scene", "scene_id", "context_pack_hash", "last_validation_at", "last_error"):
            if not isinstance(state.get(key), str):
                errors.append(f"runtime_state.{key} must be a string")
        if not state.get("active_scene"):
            errors.append("runtime_state.active_scene must not be empty")
        if "ero_scene" in state and not isinstance(state["ero_scene"], bool):
            errors.append("runtime_state.ero_scene must be a boolean")
        if "style_conditions" in state:
            values = state["style_conditions"]
            if not isinstance(values, list) or any(value != "yuri" for value in values) or len(values) != len(set(values)):
                errors.append("runtime_state.style_conditions must be a unique list of supported style conditions")
            elif state.get("ero_scene") is False and values:
                errors.append("inactive prose scene must clear style_conditions")
    dice = _require_mapping(data, "dice_state", errors)
    if dice is not None:
        if dice.get("tape_revision") != TAPE_REVISION:
            errors.append(f"dice_state.tape_revision must be {TAPE_REVISION}")
        for key, limit in (("dice_cursor_d6", 600), ("dice_cursor_d10", 500)):
            value = dice.get(key)
            if not _is_integer(value) or not 0 <= value < limit:
                errors.append(f"dice_state.{key} must be an integer in 0..{limit - 1}")
    if not isinstance(data.get("world_state"), dict):
        errors.append("world_state must be a mapping")
    else:
        world_day = data["world_state"].get("day")
        if not _is_integer(world_day) or world_day < 1:
            errors.append("world_state.day must be an integer >= 1")
        if not isinstance(data["world_state"].get("location"), str):
            errors.append("world_state.location must be a string")
        for position_key in ("place_id", "room_id", "sub_location"):
            if position_key in data["world_state"]:
                position_value = data["world_state"][position_key]
                if not isinstance(position_value, str) or len(position_value) > 300:
                    errors.append(f"world_state.{position_key} must be a string of at most 300 characters")
        _validate_quest_card_v3(
            data["world_state"].get("quest_card"), "world_state.quest_card", errors,
        )
        _validate_reward_state(data["world_state"], errors)
        _validate_growth_state(data, data["world_state"], errors)
        _validate_expedition_state(data, data["world_state"], errors)
        _validate_dungeon_state(data, data["world_state"], errors)
    player = _require_mapping(data, "player", errors)
    if player is not None:
        _validate_character(player, "player", errors, player=True)
        for key in ("name", "gender"):
            if not isinstance(player.get(key), str):
                errors.append(f"player.{key} must be a string")
        age = player.get("age")
        if age is not None and (not _is_integer(age) or age < 18):
            errors.append("player.age must be a numeric integer >= 18 when set")
        if not _is_integer(player.get("gold")) or player["gold"] < 0:
            errors.append("player.gold must be an integer >= 0")
        debt = player.get("debt")
        if not _is_integer(debt) or debt < 0:
            errors.append("player.debt must be an integer >= 0")
    if "player_state" in data:
        errors.append("legacy player_state is not allowed; run migrate-save")
    if "runtime" in data:
        warnings.append("legacy runtime metadata remains; run migrate-save to normalize it")
    for key in ("party", "items", "skills", "skill_dormancy", "custom_abilities", "spells",
                "captured_girls", "ng", "inn_reserve", "npc_relationship", "design_applied"):
        value = data.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")
    _validate_skill_records(data.get("skills"), "skills", errors)
    for key in ("fire_state", "ammo", "shop_records", "partner_pref", "hearing_check", "equip"):
        if not isinstance(data.get(key), dict):
            errors.append(f"{key} must be a mapping")
    for key in ("play_mode", "ero_style", "player_body", "desire", "yuri"):
        if not isinstance(data.get(key), str):
            errors.append(f"{key} must be a string")
    if data.get("play_mode") not in {"", "RP", "GOD"}:
        errors.append("play_mode must be empty, RP or GOD")
    if data.get("ero_style") not in {"", "machadan", "rabilabi"}:
        errors.append("ero_style must be empty, machadan or rabilabi")
    partner = data.get("partner_pref")
    if isinstance(partner, dict):
        if not isinstance(partner.get("asked"), bool):
            errors.append("partner_pref.asked must be a boolean")
        for key in (
            "personalities", "sub_personalities", "body_height",
            "body_build", "body_bust", "call",
        ):
            value = partner.get(key)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value or []):
                errors.append(f"partner_pref.{key} must be a list of strings")
    if hearing is not None and isinstance(hearing.get("completed_steps"), list):
        completed_set = set(hearing["completed_steps"])
        if "playmode" in completed_set and data.get("play_mode") not in {"RP", "GOD"}:
            errors.append("completed playmode requires canonical play_mode")
        if "profile" in completed_set and (not isinstance(data.get("player"), dict) or
                                             data["player"].get("age") is None):
            errors.append("completed profile requires player.age")
        if "body_profile" in completed_set and not data.get("player_body"):
            errors.append("completed body_profile requires player_body")
        if "partner" in completed_set and (not isinstance(partner, dict) or
                                             partner.get("asked") is not True):
            errors.append("completed partner step requires partner_pref.asked=true")
        if "style" in completed_set and data.get("ero_style") not in {"machadan", "rabilabi"}:
            errors.append("completed style step requires a canonical ero_style")
    if data.get("active_event") is not None and not isinstance(data.get("active_event"), dict):
        errors.append("active_event must be a mapping or null")
    elif isinstance(data.get("active_event"), dict):
        _validate_quest_card_v3(data["active_event"], "active_event", errors)
        world = data.get("world_state")
        entitlement_map = {
            item.get("entitlement_id"): item
            for item in (world.get("entitlements", []) if isinstance(world, dict) else [])
            if isinstance(item, dict) and isinstance(item.get("entitlement_id"), str)
        }
        _validate_standard_reward_contract(
            data["active_event"].get("reward_contract"),
            "active_event.reward_contract", errors, entitlement_map,
        )
        raw_ledger = world.get("reward_ledger", []) if isinstance(world, dict) else []
        active_ledger_components: dict[str, dict[str, dict]] = {}
        active_ledger_status: dict[str, str] = {}
        for entry in raw_ledger if isinstance(raw_ledger, list) else []:
            if not isinstance(entry, dict) or not isinstance(entry.get("settlement_id"), str):
                continue
            active_ledger_status[entry["settlement_id"]] = str(entry.get("status") or "")
            active_ledger_components[entry["settlement_id"]] = {
                component.get("component_id"): component
                for component in entry.get("components", [])
                if isinstance(component, dict) and isinstance(component.get("component_id"), str)
            }
        _validate_active_contract_receipts(
            data["active_event"].get("reward_contract"), active_ledger_components,
            active_ledger_status, "active_event", errors,
        )
    world_for_contract_ids = data.get("world_state")
    quest_for_contract_id = (
        world_for_contract_ids.get("quest_card")
        if isinstance(world_for_contract_ids, dict) else None
    )
    quest_contract_for_id = (
        quest_for_contract_id.get("reward_contract")
        if isinstance(quest_for_contract_id, dict) else None
    )
    event_contract_for_id = (
        data["active_event"].get("reward_contract")
        if isinstance(data.get("active_event"), dict) else None
    )
    quest_settlement_id = (
        quest_contract_for_id.get("settlement_id")
        if isinstance(quest_contract_for_id, dict) else None
    )
    event_settlement_id = (
        event_contract_for_id.get("settlement_id")
        if isinstance(event_contract_for_id, dict) else None
    )
    if (isinstance(quest_settlement_id, str) and quest_settlement_id
            and quest_settlement_id == event_settlement_id):
        errors.append(
            "quest_card and active_event reward_contract settlement_id must be unique: "
            f"{quest_settlement_id}"
        )
    session_log = data.get("session_log")
    if not isinstance(session_log, dict):
        errors.append("session_log must be a mapping")
    else:
        if not isinstance(session_log.get("previous"), str):
            errors.append("session_log.previous must be a string")
        if not isinstance(session_log.get("entries"), list):
            errors.append("session_log.entries must be a list")
    memory_log = data.get("memory_log")
    if not isinstance(memory_log, dict):
        errors.append("memory_log must be a mapping")
    else:
        for key in ("encounters", "battles", "ero", "turning_points"):
            if not isinstance(memory_log.get(key), list):
                errors.append(f"memory_log.{key} must be a list")
    all_character_ids: set[str] = set()
    if isinstance(player, dict) and isinstance(player.get("character_id"), str):
        all_character_ids.add(player["character_id"])
    for collection in ("party", "inn_reserve", "captured_girls"):
        members = data.get(collection)
        if not isinstance(members, list):
            continue
        if collection == "party" and len(members) > 2:
            errors.append("party may contain at most 2 members; use inn_reserve")
        for index, member in enumerate(members):
            if not isinstance(member, dict):
                errors.append(f"{collection}[{index}] must be a mapping")
            elif not _is_adult_value(member.get("age"), member.get("adult_status")):
                errors.append(
                    f"{collection}[{index}] must have age >= 18 or explicit canonical adult status"
                )
            if collection in {"party", "inn_reserve"} and isinstance(member, dict):
                _validate_character(member, f"{collection}[{index}]", errors)
                if "skills" in member:
                    _validate_skill_records(
                        member.get("skills"), f"{collection}[{index}].skills", errors,
                    )
                character_id = member.get("character_id")
                if isinstance(character_id, str):
                    if character_id in all_character_ids:
                        errors.append(f"duplicate character_id: {character_id}")
                    all_character_ids.add(character_id)
    if data.get("items") != []:
        errors.append("items is a retired v2 mirror and must be empty; use inventory")
    _validate_inventory_v3(data, errors)
    _validate_ammo_v3(data, errors)
    _validate_debt_state(data, errors)
    _validate_enterprise_state(data, errors)
    from onboarding import validate_onboarding
    validate_onboarding(data, errors)
    from allocation_widget import validate_state as validate_allocation_state
    validate_allocation_state(data, errors)
    from encumbrance import validate_state as validate_encumbrance_state
    validate_encumbrance_state(data, errors)
    from appearance_customization import validate_state as validate_appearance_state
    validate_appearance_state(SimpleNamespace(**globals()), data, errors)
    try:
        current_version = package_version()
    except RuntimeProblem:
        current_version = ""
    if current_version and data.get("game_version") != current_version:
        warnings.append(
            f"save game_version {data.get('game_version')!r} differs from runtime {current_version!r}; "
            "run migrate-save before continuing"
        )
    current_manifest = manifest_digest()
    saved_manifest = data.get("content_manifest_hash")
    if current_manifest and saved_manifest != current_manifest:
        warnings.append(
            "save content_manifest_hash is missing or differs from installed runtime; "
            "run migrate-save before continuing"
        )
    return errors, warnings


def ensure_runtime_metadata(data: dict, campaign_id: str | None = None, new: bool = False) -> dict:
    """Fill v2 top-level metadata without changing story state."""
    result = copy.deepcopy(data)
    result["schema"] = CURRENT_SCHEMA
    result["schema_version"] = CURRENT_SCHEMA_VERSION
    if campaign_id:
        result["campaign_id"] = safe_id(campaign_id)
    elif not result.get("campaign_id"):
        result["campaign_id"] = (
            "campaign-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        )
    timestamp = now_iso()
    if new or not result.get("created_at"):
        result["created_at"] = timestamp
    result["updated_at"] = timestamp
    result["game_version"] = package_version()
    result.setdefault("save_revision", 0)
    current_manifest = manifest_digest()
    if current_manifest:
        result["content_manifest_hash"] = current_manifest
    else:
        result.setdefault("content_manifest_hash", "")
    return result


def manifest_digest() -> str:
    for path in (ROOT.parent / "RUNTIME_MANIFEST.json", ROOT / "RUNTIME_MANIFEST.json"):
        if path.is_file():
            return sha256_bytes(path.read_bytes())
    return ""


def _add_missing_defaults(target: dict, template: dict, prefix: str, changes: list[str]) -> None:
    for key, default in template.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if key not in target:
            target[key] = copy.deepcopy(default)
            changes.append(f"added {dotted}")
        elif isinstance(default, dict) and isinstance(target.get(key), dict):
            _add_missing_defaults(target[key], default, dotted, changes)


def _normalize_hearing_for_migration(result: dict, changes: list[str]) -> None:
    """Convert older hearing order/state into the current safe ordered prefix."""
    hearing = result.get("hearing_progress")
    if not isinstance(hearing, dict):
        return
    raw_completed = hearing.get("completed_steps")
    raw_set = {str(item) for item in raw_completed} if isinstance(raw_completed, list) else set()
    ordered = ["playmode", "profile", "body_profile", "desire", "partner", "style"]
    partner = result.get("partner_pref")
    player = result.get("player")
    completion_valid = {
        "playmode": result.get("play_mode") in {"RP", "GOD"},
        "profile": isinstance(player, dict) and _is_integer(player.get("age")) and player["age"] >= 18,
        "body_profile": isinstance(result.get("player_body"), str) and bool(result.get("player_body")),
        "desire": True,
        "partner": isinstance(partner, dict) and partner.get("asked") is True,
        "style": result.get("ero_style") in {"machadan", "rabilabi"},
    }
    normalized: list[str] = []
    for step_id in ordered:
        if step_id not in raw_set or not completion_valid[step_id]:
            break
        normalized.append(step_id)
    normalized_status = (
        "pending" if not normalized else "complete" if normalized == ordered else "in_progress"
    )
    normalized_step = len(normalized) + 1
    if (hearing.get("completed_steps") != normalized or
            hearing.get("status") != normalized_status or
            hearing.get("current_step") != normalized_step):
        hearing["completed_steps"] = normalized
        hearing["status"] = normalized_status
        hearing["current_step"] = normalized_step
        changes.append("hearing_progress normalized to current six-step order")


def _migrate_legacy_reward_state(
    result: dict, changes: list[str], allow_legacy_backfill: bool,
) -> None:
    """Backfill the pre-ledger M83 reward fields without losing received benefits."""
    if not allow_legacy_backfill:
        return
    world = result.get("world_state")
    if not isinstance(world, dict):
        return
    ledger = world.get("reward_ledger")
    entitlements = world.get("entitlements")
    pending = world.get("pending_rewards")
    if not isinstance(ledger, list) or not isinstance(entitlements, list):
        return
    detail_keys = (
        "estimated_value_g", "amount", "item_name", "quantity", "delivery_target",
        "entitlement_id", "name", "issuer", "scope", "conditions",
        "uses_remaining", "expires", "summary",
    )

    def preserve_legacy_component(component: Any, *, estimated: bool = False) -> None:
        if not isinstance(component, dict):
            return
        detail = component.get("detail")
        if not isinstance(detail, dict):
            detail = {
                key: copy.deepcopy(component[key]) for key in detail_keys if key in component
            }
            component["detail"] = detail
        if not _reward_detail_complete(component.get("kind"), detail, estimated=estimated):
            component["legacy_migration"] = True

    if isinstance(pending, list):
        for pending_entry in pending:
            if not isinstance(pending_entry, dict):
                continue
            for component in pending_entry.get("components", []):
                preserve_legacy_component(component)
    quest_card = world.get("quest_card")
    if isinstance(quest_card, dict):
        if not isinstance(quest_card.get("reward_contract"), dict):
            legacy_id = "legacy-quest-" + _reward_value_hash(quest_card)[:16]
            quest_card["reward_contract"] = {
                "settlement_id": legacy_id, "offered": False,
                "payer": "legacy-unknown", "components": [],
                "requires_reconfirmation": True,
            }
            changes.append("legacy quest_card reward contract requires reconfirmation")
        else:
            for component in quest_card["reward_contract"].get("components", []):
                preserve_legacy_component(component)
    active_event = result.get("active_event")
    if isinstance(active_event, dict):
        if not isinstance(active_event.get("reward_contract"), dict):
            legacy_id = "legacy-event-" + _reward_value_hash(active_event)[:16]
            active_event["reward_contract"] = {
                "settlement_id": legacy_id, "offered": False,
                "payer": "legacy-unknown", "components": [],
                "requires_reconfirmation": True,
            }
            changes.append("legacy active_event reward contract requires reconfirmation")
        else:
            for component in active_event["reward_contract"].get("components", []):
                preserve_legacy_component(component)
    event_contract = world.get("event_reward_contract")
    if isinstance(event_contract, dict):
        for component in event_contract.get("components", []):
            preserve_legacy_component(component, estimated=True)
    pending_ids = {
        entry.get("settlement_id") for entry in pending or []
        if isinstance(entry, dict) and isinstance(entry.get("settlement_id"), str)
    } if isinstance(pending, list) else set()
    ledger_by_settlement = {
        entry.get("settlement_id"): entry for entry in ledger
        if isinstance(entry, dict) and isinstance(entry.get("settlement_id"), str)
    }

    def legacy_id(prefix: str, value: Any, used: set[str]) -> str:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-") or "record"
        candidate = f"{prefix}-{stem}"[:80]
        suffix = 2
        while candidate in used:
            tail = f"-{suffix}"
            candidate = f"{prefix}-{stem}"[:80 - len(tail)] + tail
            suffix += 1
        used.add(candidate)
        return candidate

    used_settlements = set(ledger_by_settlement)
    used_pairs = {
        (entry.get("settlement_id"), component.get("component_id"))
        for entry in ledger if isinstance(entry, dict)
        for component in entry.get("components", []) if isinstance(component, dict)
    }
    for index, entitlement in enumerate(entitlements):
        if not isinstance(entitlement, dict):
            continue
        entitlement_id = entitlement.get("entitlement_id")
        if not isinstance(entitlement_id, str) or not entitlement_id:
            continue
        settlement_id = entitlement.get("source_settlement_id")
        if not isinstance(settlement_id, str) or not settlement_id:
            settlement_id = legacy_id("legacy-settlement", entitlement_id, used_settlements)
            entitlement["source_settlement_id"] = settlement_id
            changes.append(f"world_state.entitlements[{index}].source_settlement_id backfilled")
        component_id = entitlement.get("source_component_id")
        if not isinstance(component_id, str) or not component_id:
            used_components = {pair[1] for pair in used_pairs if pair[0] == settlement_id}
            component_id = legacy_id("legacy-component", entitlement_id, used_components)
            entitlement["source_component_id"] = component_id
            changes.append(f"world_state.entitlements[{index}].source_component_id backfilled")
        existing = ledger_by_settlement.get(settlement_id)
        if existing and existing.get("status") in {"settled", "declined", "forfeited"} and (
            settlement_id, component_id
        ) not in used_pairs:
            entitlement["legacy_source_settlement_id"] = settlement_id
            settlement_id = legacy_id("legacy-settlement", entitlement_id, used_settlements)
            entitlement["source_settlement_id"] = settlement_id
            component_id = legacy_id("legacy-component", entitlement_id, set())
            entitlement["source_component_id"] = component_id
            changes.append(f"world_state.entitlements[{index}] moved to a synthetic legacy settlement")
        used_pairs.add((settlement_id, component_id))

    legacy_log_hash = _reward_value_hash(_reward_effect_value(result, "session_log"))
    if isinstance(pending, list):
        for index, pending_entry in enumerate(pending):
            if not isinstance(pending_entry, dict) or pending_entry.get("status") != "partial":
                continue
            settlement_id = pending_entry.get("settlement_id")
            delivered_ids = pending_entry.get("delivered_component_ids", [])
            if not isinstance(settlement_id, str) or not settlement_id:
                continue
            if not isinstance(delivered_ids, list) or not delivered_ids:
                pending_entry["status"] = "pending"
                changes.append(f"world_state.pending_rewards[{index}].status normalized to pending")
                continue
            entry = ledger_by_settlement.get(settlement_id)
            if entry is None:
                entry = {
                    "settlement_id": settlement_id,
                    "source": {"kind": "legacy_migration"},
                    "payer": str(pending_entry.get("payer") or "legacy-unknown"),
                    "components": [],
                    "status": "partial",
                }
                ledger.append(entry)
                ledger_by_settlement[settlement_id] = entry
            if entry.get("status") not in {"settled", "declined", "forfeited"}:
                entry["status"] = "partial"
            component_map = {
                component.get("component_id"): component
                for component in entry.get("components", []) if isinstance(component, dict)
            }
            for component_id in delivered_ids:
                if not isinstance(component_id, str) or not component_id or component_id in component_map:
                    continue
                entry.setdefault("components", []).append({
                    "component_id": component_id,
                    "kind": "legacy",
                    "state": "delivered",
                    "transaction_id": "migration-m83",
                    "effect": {
                        "target": "session_log",
                        "before_sha256": "legacy-unavailable",
                        "after_sha256": legacy_log_hash,
                        "summary": "pre-ledger delivered component preserved during migration",
                    },
                    "legacy_migration": True,
                })
                changes.append(
                    f"reward ledger backfilled for pending delivery {settlement_id}/{component_id}"
                )

    entitlements_hash = _reward_value_hash(entitlements)
    reverse_kinds = {
        "right": "right", "discount": "right", "access": "right",
        "service": "service", "favor": "favor", "referral": "referral",
        "information": "information",
    }
    for entitlement in entitlements:
        if not isinstance(entitlement, dict):
            continue
        entitlement_id = entitlement.get("entitlement_id")
        settlement_id = entitlement.get("source_settlement_id")
        component_id = entitlement.get("source_component_id")
        if not all(isinstance(value, str) and value for value in (
            entitlement_id, settlement_id, component_id,
        )):
            continue
        entry = ledger_by_settlement.get(settlement_id)
        components = entry.get("components", []) if isinstance(entry, dict) else []
        present = next((item for item in components if isinstance(item, dict) and
                        item.get("component_id") == component_id), None)
        if present is None:
            if entry is None:
                entry = {
                    "settlement_id": settlement_id,
                    "source": {"kind": "legacy_migration"},
                    "payer": "legacy-unknown",
                    "components": [],
                    "status": "partial" if settlement_id in pending_ids else "settled",
                }
                ledger.append(entry)
                ledger_by_settlement[settlement_id] = entry
            entry.setdefault("components", []).append({
                "component_id": component_id,
                "kind": reverse_kinds.get(entitlement.get("kind"), "right"),
                "state": "delivered",
                "transaction_id": "migration-m83",
                "effect": {
                    "target": "world_state.entitlements",
                    "before_sha256": "legacy-unavailable",
                    "after_sha256": entitlements_hash,
                    "entitlement_id": entitlement_id,
                    "summary": "pre-ledger entitlement preserved during migration",
                },
                "legacy_migration": True,
            })
            changes.append(f"reward ledger backfilled for entitlement {entitlement_id}")

    for entry in ledger:
        if not isinstance(entry, dict):
            continue
        for component in entry.get("components", []):
            effect = component.get("effect") if isinstance(component, dict) else None
            if isinstance(effect, dict) and effect.get("target") == "items":
                effect["target"] = "inventory_bundle"
                effect["before_sha256"] = "legacy-unavailable"
                effect["after_sha256"] = _reward_value_hash(
                    _reward_effect_value(result, "inventory_bundle")
                )
                component["legacy_migration"] = True
                changes.append("legacy reward item effect migrated to inventory_bundle")
    current_hashes = {
        target: _reward_value_hash(_reward_effect_value(result, target))
        for target in ("player.gold", "inventory_bundle", "world_state.entitlements", "session_log")
    }
    for entry in ledger:
        if not isinstance(entry, dict):
            continue
        settlement_id = entry.get("settlement_id")
        for component in entry.get("components", []):
            if not isinstance(component, dict) or "effect" in component:
                continue
            if component.get("state") != "delivered":
                component["effect"] = None
                component["legacy_migration"] = True
                changes.append(f"legacy reward effect backfilled for {settlement_id}")
                continue
            kind = component.get("kind")
            target = {
                "gold": "player.gold", "item": "inventory_bundle", "right": "world_state.entitlements",
            }.get(kind, "session_log")
            effect = {
                "target": target,
                "before_sha256": "legacy-unavailable",
                "after_sha256": current_hashes[target],
                "summary": "pre-effect reward ledger component preserved during migration",
            }
            if target == "world_state.entitlements":
                match = next((item for item in entitlements if isinstance(item, dict) and
                              item.get("source_settlement_id") == settlement_id and
                              item.get("source_component_id") == component.get("component_id")), None)
                effect["entitlement_id"] = (
                    match.get("entitlement_id") if isinstance(match, dict) else "legacy-unresolved"
                )
            component["effect"] = effect
            component["legacy_migration"] = True
            changes.append(f"legacy reward effect backfilled for {settlement_id}")


def _migrate_legacy_adventure_state(
    result: dict, changes: list[str], *, legacy_growth: bool, legacy_dungeon: bool,
) -> None:
    world = result.get("world_state")
    if not isinstance(world, dict):
        return
    growth = world.get("growth_state")
    if legacy_growth and isinstance(growth, dict):
        target_status = "pending" if _rank_at_least_c(world) else "locked"
        if growth.get("c_rank_choice_fruit_status") != target_status:
            growth["c_rank_choice_fruit_status"] = target_status
            changes.append(
                "legacy C-rank fruit guarantee marked pending"
                if target_status == "pending"
                else "legacy C-rank fruit guarantee initialized locked"
            )
        growth["c_rank_choice_fruit_transaction_id"] = ""
        growth.setdefault("resolutions", [])

    if not legacy_dungeon:
        return
    depth = world.get("depth")
    inferred_depth = depth if _is_integer(depth) and 1 <= depth <= 9 else 0
    goals = world.get("goals")
    if isinstance(goals, dict) and goals.get("dungeon_clear") is True:
        inferred_depth = 9
    current_deepest = world.get("deepest_depth_reached")
    if _is_integer(current_deepest):
        inferred_depth = max(inferred_depth, current_deepest)
    world["deepest_depth_reached"] = inferred_depth
    changes.append("legacy dungeon/expedition state initialized inactive")


def _zero_stats() -> dict[str, int]:
    return {key: 0 for key in STAT_KEYS}


def _legacy_character_stats(character: dict) -> tuple[dict[str, int], dict[str, int]]:
    """Return best-effort base/equipment maps while preserving the old effective total."""
    raw = character.get("stats")
    base = _zero_stats()
    equipment = _zero_stats()
    if not isinstance(raw, dict):
        return base, equipment
    if set(raw) == set(STAT_KEYS) and all(_is_integer(raw.get(key)) for key in STAT_KEYS):
        return {key: int(raw[key]) for key in STAT_KEYS}, equipment
    for stat in STAT_KEYS:
        value = raw.get(stat.upper(), raw.get(stat))
        if isinstance(value, dict):
            raw_base = value.get("base", 0)
            raw_equipment = value.get("equip", value.get("equipment", 0))
            base[stat] = int(raw_base) if _is_integer(raw_base) else 0
            equipment[stat] = int(raw_equipment) if _is_integer(raw_equipment) else 0
        elif _is_integer(value):
            base[stat] = int(value)
    return base, equipment


def _normalized_meter(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"cur": 0, "max": 0}
    current = value.get("cur", value.get("current", 0))
    maximum = value.get("max", 0)
    maximum = max(0, int(maximum)) if _is_integer(maximum) else 0
    current = max(0, min(maximum, int(current))) if _is_integer(current) else 0
    return {"cur": current, "max": maximum}


def _stable_legacy_id(prefix: str, *parts: Any) -> str:
    digest = _reward_value_hash([str(part) for part in parts])[:16]
    return f"{prefix}-{digest}"


def _normalize_character_v3(
    character: dict, *, character_id: str, legacy: bool, changes: list[str], label: str,
) -> dict[str, str]:
    """Normalize a player/companion and return its legacy named equipment."""
    old_equipment = copy.deepcopy(character.get("equipment"))
    if legacy:
        base, equipment_bonus = _legacy_character_stats(character)
        fire = _zero_stats()
        growth = _zero_stats()
        temporary = _zero_stats()
        effective = {
            stat: base[stat] + equipment_bonus[stat] for stat in STAT_KEYS
        }
        character.update({
            "character_version": 1,
            "character_id": character_id,
            "gender": str(character.get("gender") or ""),
            "race": str(character.get("race") or ""),
            "job": str(character.get("job") or ""),
            "job_profile": {
                "combat_role": "unclassified", "magic_role": "unclassified",
                "expertise_tags": [], "solo_suitability": "unclassified", "party_needs": [],
            },
            "base_stats": base,
            "growth_bonus": growth,
            "equipment_bonus": equipment_bonus,
            "fire_bonus": fire,
            "temporary_modifiers": temporary,
            "effective_stats": effective,
            "stats": copy.deepcopy(effective),
        })
        lp = _normalized_meter(character.get("lp"))
        mp = _normalized_meter(character.get("mp"))
        character["base_lp"] = lp["max"]
        character["job_lp_bonus"] = 0
        character["fire_lp_bonus"] = 0
        character["temporary_lp_bonus"] = 0
        character["lp"] = lp
        mp["max"] = max(0, effective["int"])
        mp["cur"] = min(mp["cur"], mp["max"])
        character["mp"] = mp
        character["build_complete"] = bool(
            character.get("job") and sum(base.values()) > 0 and lp["max"] > 0
        )
        old_state = character.get("state")
        character["statuses"] = (
            [str(old_state)] if isinstance(old_state, str) and old_state else []
        )
        if not isinstance(character.get("buffs"), list):
            character["buffs"] = []
        if not isinstance(character.get("ero_status"), list):
            character["ero_status"] = []
        changes.append(f"{label} migrated to common Character v1")
    else:
        character["character_id"] = character_id
    fixed: list[str] = []
    legacy_names: dict[str, str] = {}
    if isinstance(old_equipment, dict):
        for source, target in (
            ("weapon", "weapon_instance_id"),
            ("armor", "armor_instance_id"),
            ("offhand", "offhand_instance_id"),
        ):
            value = old_equipment.get(source)
            if isinstance(value, str) and value:
                legacy_names[target] = value
        raw_fixed = old_equipment.get("fixed", [])
        if isinstance(raw_fixed, str) and raw_fixed:
            fixed = [raw_fixed]
        elif isinstance(raw_fixed, list):
            fixed = [str(item) for item in raw_fixed if str(item)]
    current_equipment = character.get("equipment")
    if legacy or not isinstance(current_equipment, dict):
        character["equipment"] = {
            "weapon_instance_id": None, "armor_instance_id": None,
            "offhand_instance_id": None, "fixed": list(dict.fromkeys(fixed)),
        }
    return legacy_names


def _ensure_migrated_item_definition(
    result: dict, *, item_def_id: str, name: str, category: str, source: str,
) -> None:
    definitions = result.setdefault("item_definitions", [])
    if any(isinstance(item, dict) and item.get("item_def_id") == item_def_id for item in definitions):
        return
    definitions.append({
        "item_def_id": item_def_id,
        "name": name,
        "category": category,
        "specification": {"legacy_name": name, "category": category},
        "provenance": {"source_kind": "migration", "source": source},
        "balance_anchor": {"kind": "legacy_preserved", "requires_review": True},
    })


def _migrate_named_equipment(
    result: dict, character: dict, names: dict[str, str], changes: list[str], label: str,
) -> None:
    if not names:
        return
    owner = str(character.get("character_id") or "player")
    instances = result.setdefault("item_instances", [])
    for slot, name in names.items():
        item_def_id = _stable_legacy_id("legacy-equip-def", slot, name)
        instance_id = _stable_legacy_id("legacy-equip", owner, slot, name)
        _ensure_migrated_item_definition(
            result, item_def_id=item_def_id, name=name, category="equipment", source=label,
        )
        if not any(isinstance(item, dict) and item.get("instance_id") == instance_id for item in instances):
            instances.append({
                "instance_id": instance_id, "item_def_id": item_def_id, "name": name,
                "location": "equipped", "slot_cost": 0, "owner_character_id": owner,
                "specification_snapshot": {"category": "equipment", "slot": slot},
            })
        character["equipment"][slot] = instance_id
    changes.append(f"{label} named equipment migrated to stable item instances")


def _migrate_legacy_items(result: dict, changes: list[str]) -> None:
    legacy_items = result.get("items")
    if not isinstance(legacy_items, list):
        raise RuntimeProblem("legacy items must be a list")
    inventory = result.get("inventory")
    if not isinstance(inventory, dict):
        raise RuntimeProblem("inventory defaults are missing during migration")
    carried = inventory.setdefault("carried_stacks", [])
    warehouse = inventory.setdefault("warehouse", {}).setdefault("stacks", [])
    if carried or warehouse:
        result["items"] = []
        return
    prepared: list[dict] = []
    for index, item in enumerate(legacy_items):
        if not isinstance(item, dict):
            raise RuntimeProblem(f"legacy items[{index}] must be a mapping")
        name = item.get("name")
        count = item.get("count", 1)
        if not isinstance(name, str) or not name or not _is_integer(count) or count < 0:
            raise RuntimeProblem(f"legacy items[{index}] has invalid name/count")
        if count == 0:
            continue
        category = str(item.get("category") or "standard")
        category_folded = category.casefold()
        unique = category_folded in {"unique", "unknown", "固有", "未知"}
        cap = 1 if unique else 10
        slot_cost = 0 if category_folded in {"key", "document", "quest_key", "鍵", "文書"} else 1
        item_def_id = str(item.get("item_def_id") or _stable_legacy_id("legacy-item-def", name, category))
        _ensure_migrated_item_definition(
            result, item_def_id=item_def_id, name=name, category=category, source=f"items[{index}]",
        )
        remaining = count
        chunk = 0
        while remaining:
            amount = min(cap, remaining)
            prepared.append({
                "stack_id": _stable_legacy_id("legacy-stack", index, chunk, name),
                "item_def_id": item_def_id, "name": name, "category": category,
                "count": amount, "stack_cap": cap, "slot_cost": slot_cost,
                "reserved_quantity": 0,
            })
            remaining -= amount
            chunk += 1
    slot_total = sum(stack["slot_cost"] for stack in prepared)
    bag = inventory["bag"]
    bonus = _bag_skill_bonus(result)
    needed_physical = max(16, min(28, slot_total - bonus))
    upgrades = min(3, max(0, (needed_physical - 16 + 3) // 4))
    bag.update({
        "base_slots": 16, "upgrade_count": upgrades, "max_slots": 16 + 4 * upgrades,
        "skill_bonus_slots": bonus, "effective_max_slots": 16 + 4 * upgrades + bonus,
    })
    remaining_capacity = bag["effective_max_slots"]
    for stack in prepared:
        if stack["slot_cost"] <= remaining_capacity:
            carried.append(stack)
            remaining_capacity -= stack["slot_cost"]
        else:
            warehouse.append(stack)
    bag["used_slots"] = sum(stack["slot_cost"] for stack in carried)
    if legacy_items:
        result.setdefault("migration_legacy", {})["items_v2"] = copy.deepcopy(legacy_items)
        changes.append("legacy items migrated to carried stacks/warehouse without discarding overflow")
    result["items"] = []


def _migrate_legacy_ammo(result: dict, changes: list[str]) -> None:
    ammo = result.get("ammo")
    if not isinstance(ammo, dict):
        return
    if set(ammo) == {"pools", "weapon_loads"}:
        return
    cartridges = ammo.get("cartridges", 0)
    loaded = ammo.get("loaded", {})
    count = int(cartridges) if _is_integer(cartridges) and cartridges >= 0 else 0
    pools = [{"ammo_type": "cartridge", "count": count}]
    loads: list[dict] = []
    if isinstance(loaded, dict):
        instances = result.setdefault("item_instances", [])
        player = result.get("player") if isinstance(result.get("player"), dict) else {}
        for weapon_name, raw_loaded in loaded.items():
            if not isinstance(weapon_name, str) or not weapon_name or not _is_integer(raw_loaded) or raw_loaded < 0:
                continue
            instance = next(
                (item for item in instances if isinstance(item, dict) and item.get("name") == weapon_name
                 and item.get("owner_character_id") == player.get("character_id")), None,
            )
            if instance is None:
                item_def_id = _stable_legacy_id("legacy-equip-def", "weapon", weapon_name)
                instance_id = _stable_legacy_id("legacy-loaded-weapon", weapon_name)
                _ensure_migrated_item_definition(
                    result, item_def_id=item_def_id, name=weapon_name,
                    category="equipment", source="ammo.loaded",
                )
                instance = {
                    "instance_id": instance_id, "item_def_id": item_def_id, "name": weapon_name,
                    "location": "bag", "slot_cost": 1, "owner_character_id": None,
                    "specification_snapshot": {"category": "equipment", "slot": "weapon"},
                }
                instances.append(instance)
            loads.append({
                "weapon_instance_id": instance["instance_id"], "ammo_type": "cartridge",
                "loaded": int(raw_loaded), "capacity": max(1, int(raw_loaded)),
            })
    result["ammo"] = {"pools": pools, "weapon_loads": loads}
    changes.append("legacy name-keyed ammunition migrated to weapon instance loads")


def _migrate_quest_metadata(card: Any, *, prefix: str, changes: list[str]) -> None:
    if not isinstance(card, dict):
        return
    if not isinstance(card.get("quest_id"), str) or not card.get("quest_id"):
        card["quest_id"] = _stable_legacy_id(prefix, _quest_immutable_payload(card))
        changes.append(f"{prefix} stable quest_id backfilled")
    if not isinstance(card.get("progress"), dict):
        card["progress"] = {"status": "active", "completed_beats": []}
    if not isinstance(card.get("amendments"), list):
        card["amendments"] = []
    card["immutable_hash"] = _quest_hash(card)


def _migrate_debt_v3(result: dict, changes: list[str], *, legacy: bool) -> None:
    if not legacy:
        return
    player = result.get("player")
    world = result.get("world_state")
    if not isinstance(player, dict):
        return
    principal = player.get("debt") if _is_integer(player.get("debt")) else 10000
    day = world.get("day", 1) if isinstance(world, dict) else 1
    day = int(day) if _is_integer(day) and day >= 1 else 1
    cycle = 0
    benefits: list[dict] = []
    selection = {"benefit_id": "", "source": "default", "switch_available": False, "activated_day": None}
    if principal <= 0:
        # A legacy zero balance is not a campaign-bound payoff receipt. Renew
        # its principal without fabricating romance, appearance or business perks.
        from debt_contracts import principal_schedule
        cycle = 1
        principal = principal_schedule(cycle)
        changes.append("legacy zero debt renewed without synthesising staged unlocks")
    result["debt_state"] = {
        "version": 1, "contract_cycle_index": cycle,
        "contract_id": f"lilith-debt-cycle-{cycle}", "principal": principal,
        "interval_days": 5, "next_collection_day": day + 5,
        "scheduled_due": 500 + 250 * cycle, "cycle_paid": 0,
        "collection_pending": False, "last_collection_day": None,
        "collection_serial": 0, "positive_payment_collections": 0,
        "full_payment_collections": 0, "missed_collections": 0,
        "collection_ledger": [], "active_benefits": benefits,
        "benefit_selection": selection,
    }
    player["debt"] = principal
    changes.append("legacy debt migrated to five-day Lilith collection schedule")


def _normalize_legacy_skills(skills: Any, *, job: str, label: str, changes: list[str]) -> None:
    if not isinstance(skills, list):
        return
    changed = False
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("name") or f"legacy-skill-{index}")
        category = skill.get("category")
        if category not in {"technique", "passive", "check"}:
            category = "check" if "心得" in name else "technique"
            skill["category"] = category
        defaults = {
            "skill_id": _stable_legacy_id("legacy-skill", label, index, name),
            "tier": "basic", "stage": 1, "state": "set",
            "uses": None if category != "technique" else 1,
            "timing": "check" if category == "check" else "always" if category == "passive" else "action",
            "action_cost": 1 if category == "technique" else 0,
            "effect": str(skill.get("effect") or "legacy definition; review required"),
            "from": str(skill.get("from") or "job"),
            "origin_job": job,
            "requirements": [],
        }
        for key, value in defaults.items():
            if key not in skill:
                skill[key] = value
                changed = True
    if changed:
        changes.append(f"{label} legacy skill records normalized to M96 fields")


def _migrate_v3_models(result: dict, changes: list[str], *, legacy: bool) -> None:
    player = result.get("player")
    if isinstance(player, dict):
        player_names = _normalize_character_v3(
            player, character_id="player", legacy=legacy, changes=changes, label="player",
        )
        if legacy:
            top_equip = result.get("equip")
            if isinstance(top_equip, dict):
                for source, target in (
                    ("weapon", "weapon_instance_id"), ("armor", "armor_instance_id"),
                    ("offhand", "offhand_instance_id"),
                ):
                    if isinstance(top_equip.get(source), str) and top_equip[source]:
                        player_names[target] = top_equip[source]
        _migrate_named_equipment(result, player, player_names, changes, "player")
        if legacy:
            _normalize_legacy_skills(
                result.get("skills"), job=str(player.get("job") or ""),
                label="skills", changes=changes,
            )
    for collection in ("party", "inn_reserve"):
        members = result.get(collection)
        if not isinstance(members, list):
            continue
        for index, member in enumerate(members):
            if not isinstance(member, dict):
                continue
            source_id = member.get("character_id") or member.get("char_id")
            if isinstance(source_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", source_id):
                character_id = source_id
            else:
                character_id = _stable_legacy_id("character", collection, index, member.get("name", ""))
            names = _normalize_character_v3(
                member, character_id=character_id, legacy=legacy,
                changes=changes, label=f"{collection}[{index}]",
            )
            _migrate_named_equipment(result, member, names, changes, f"{collection}[{index}]")
            if legacy:
                _normalize_legacy_skills(
                    member.get("skills"), job=str(member.get("job") or ""),
                    label=f"{collection}[{index}].skills", changes=changes,
                )
    if legacy:
        _migrate_legacy_items(result, changes)
        _migrate_legacy_ammo(result, changes)
    inventory = result.get("inventory")
    if isinstance(inventory, dict) and isinstance(inventory.get("bag"), dict):
        bag = inventory["bag"]
        upgrades = bag.get("upgrade_count", 0)
        upgrades = min(3, max(0, int(upgrades))) if _is_integer(upgrades) else 0
        physical = 16 + 4 * upgrades
        bonus = _bag_skill_bonus(result)
        bag.update({
            "base_slots": 16, "upgrade_count": upgrades, "max_slots": physical,
            "skill_bonus_slots": bonus, "effective_max_slots": physical + bonus,
            "used_slots": _inventory_used_slots(result),
        })
    world = result.get("world_state")
    if isinstance(world, dict):
        run = world.get("dungeon_run")
        if isinstance(run, dict):
            if "reward_searches_used" in run:
                old_count = run.pop("reward_searches_used")
                current_floor = run.get("current_floor")
                if (_is_integer(old_count) and old_count > 0 and _is_integer(current_floor)
                        and 1 <= current_floor <= 9):
                    run.setdefault("reward_searches_by_floor", {})[current_floor] = min(2, old_count)
                changes.append("dungeon reward search count migrated to per-floor map")
            if "camped_floors" in run:
                camped = run.pop("camped_floors")
                run["camp_used"] = bool(camped)
                changes.append("dungeon camp history migrated to once-per-delve flag")
            if "floor_exhausted" in run:
                run.pop("floor_exhausted")
                changes.append("retired dungeon floor_exhausted cache removed")
        _migrate_quest_metadata(world.get("quest_card"), prefix="legacy-quest", changes=changes)
    _migrate_quest_metadata(result.get("active_event"), prefix="legacy-event", changes=changes)
    _migrate_debt_v3(result, changes, legacy=legacy)
    from dungeon_exploration import migrate as migrate_dungeon_memory
    migrate_dungeon_memory(result, changes)
    for boss_record in result.get("world_state", {}).get("boss_records", []):
        boss_record["rematch_available_day"] = boss_record["last_defeated_day"]


def migrate_data(data: dict) -> tuple[dict, list[str]]:
    result = copy.deepcopy(data)
    changes: list[str] = []
    source_schema = result.get("schema", "unknown")
    original_world = result.get("world_state")
    original_reward_version = (
        original_world.get("reward_state_version")
        if isinstance(original_world, dict) else None
    )
    original_partner = result.get("partner_pref")
    legacy_partner_preferences = (
        isinstance(original_partner, dict) and "sub_personalities" not in original_partner
    )
    legacy_growth_state = (
        not isinstance(original_world, dict)
        or not isinstance(original_world.get("growth_state"), dict)
        or "c_rank_choice_fruit_status" not in original_world["growth_state"]
    )
    legacy_dungeon_memory = not isinstance(original_world, dict) or "dungeon_memory" not in original_world
    legacy_dungeon_state = (
        not isinstance(original_world, dict)
        or not isinstance(original_world.get("dungeon_run"), dict)
    )
    # Version 1 is an explicit legacy marker.  Saves from before the reward
    # ledger existed have none of the ledger-era keys and are also safe to
    # backfill.  A v2-shaped save with only its marker removed is ambiguous:
    # restore defaults, but never bless an incomplete or forged ledger as
    # legacy data merely because one field disappeared.
    ledger_era_keys = {
        "event_reward_contract", "pending_rewards", "reward_ledger", "entitlements",
    }
    legacy_reward_state = (
        not isinstance(original_world, dict)
        or original_reward_version == 1
        or (
            original_reward_version is None
            and not any(key in original_world for key in ledger_era_keys)
        )
    )
    runtime = result.pop("runtime", None)
    if isinstance(runtime, dict):
        for old_key, new_key in {
            "campaign_id": "campaign_id", "created_at": "created_at", "updated_at": "updated_at",
            "game_version": "game_version", "turn_index": "save_revision",
        }.items():
            if old_key in runtime and new_key not in result:
                result[new_key] = runtime[old_key]
        transaction = result.setdefault("transaction", {})
        transaction.setdefault("last_transaction_id", str(runtime.get("last_commit_id") or ""))
        transaction.setdefault("last_committed_turn", int(runtime.get("turn_index") or 0))
        transaction.setdefault("previous_revision_hash", "")
        transaction.setdefault("last_candidate_hash", "")
        state = result.setdefault("runtime_state", {})
        state.setdefault("context_pack_hash", str(runtime.get("last_context_sha256") or ""))
        result.setdefault("migration_legacy", {})["runtime"] = runtime
        changes.append("legacy runtime metadata migrated to v2 top-level fields")
    legacy = result.pop("player_state", None)
    if isinstance(legacy, dict):
        player = result.setdefault("player", {})
        mapping = {
            "Name": "name", "name": "name", "Sex": "gender", "sex": "gender",
            "Age": "age", "age": "age", "Job": "job", "job": "job",
            "Gold": "gold", "gold": "gold", "Debt": "debt", "debt": "debt",
        }
        for old, new_key in mapping.items():
            if old in legacy and new_key not in player:
                player[new_key] = legacy[old]
        result.setdefault("migration_legacy", {})["player_state"] = legacy
        changes.append("player_state migrated to player")
    dice = result.setdefault("dice_state", {})
    if not isinstance(dice, dict):
        dice = {}
        result["dice_state"] = dice
        changes.append("replaced invalid dice_state with v2 defaults")
    for old, new_key in {"cursor_d6": "dice_cursor_d6", "cursor_d10": "dice_cursor_d10"}.items():
        if old in dice and new_key not in dice:
            dice[new_key] = dice.pop(old)
            changes.append(f"dice_state.{old} renamed")
    template = load_yaml(SAVE_TEMPLATE)
    if not isinstance(template, dict):
        raise RuntimeProblem("save template root must be a mapping")
    # New campaigns adopt the current allocation rule from the template.  Old
    # campaigns without a rule tag keep their original allocation contract;
    # filling defaults must not silently reinterpret their ALL5+15 allocation
    # or an existing recorded allocation as the newer ALL3+15 budget.
    prior_world = result.get("world_state")
    prior_onboarding = prior_world.get("onboarding") if isinstance(prior_world, dict) else None
    had_allocation_rule = isinstance(prior_onboarding, dict) and "allocation_rule" in prior_onboarding
    _add_missing_defaults(result, template, "", changes)
    if not had_allocation_rule:
        migrated_world = result.get("world_state")
        migrated_onboarding = migrated_world.get("onboarding") if isinstance(migrated_world, dict) else None
        if isinstance(migrated_onboarding, dict):
            migrated_onboarding.pop("allocation_rule", None)
        changes[:] = [item for item in changes if item != "added world_state.onboarding.allocation_rule"]
    if legacy_dungeon_memory:
        result["world_state"].pop("dungeon_memory", None)
    from dungeon_exploration import migrate as migrate_dungeon_memory
    migrate_dungeon_memory(result, changes)
    for boss_record in result["world_state"].get("boss_records", []):
        if boss_record.get("rematch_available_day") != boss_record.get("last_defeated_day"):
            boss_record["rematch_available_day"] = boss_record.get("last_defeated_day")
            changes.append("boss revival moved to reentry; daily loot memory remains separate")
    _migrate_legacy_adventure_state(
        result, changes, legacy_growth=legacy_growth_state,
        legacy_dungeon=legacy_dungeon_state,
    )
    if legacy_partner_preferences:
        partner = result.get("partner_pref")
        heights = partner.get("body_height") if isinstance(partner, dict) else None
        if isinstance(heights, list) and "長身" in heights and "とても長身" not in heights:
            expanded: list[Any] = []
            for item in heights:
                if item not in expanded:
                    expanded.append(item)
                if item == "長身" and "とても長身" not in expanded:
                    expanded.append("とても長身")
            partner["body_height"] = expanded
            changes.append(
                "legacy partner_pref.body_height 長身 expanded to preserve 160cm以上"
            )
    transaction = result.get("transaction")
    if isinstance(transaction, dict):
        applied_ids = transaction.get("applied_transaction_ids")
        last_transaction_id = transaction.get("last_transaction_id")
        if (isinstance(applied_ids, list) and isinstance(last_transaction_id, str)
                and last_transaction_id and last_transaction_id not in applied_ids):
            applied_ids.append(last_transaction_id)
            changes.append("transaction.applied_transaction_ids backfilled")
    _migrate_legacy_reward_state(result, changes, legacy_reward_state)
    migrated_world = result.get("world_state")
    if isinstance(migrated_world, dict) and migrated_world.get("reward_state_version") != 2:
        migrated_world["reward_state_version"] = 2
        changes.append("world_state.reward_state_version migrated to 2")
    _normalize_hearing_for_migration(result, changes)
    _migrate_v3_models(
        result, changes,
        legacy=(source_schema != CURRENT_SCHEMA or result.get("schema_version") != CURRENT_SCHEMA_VERSION),
    )
    if result.get("schema") != CURRENT_SCHEMA or result.get("schema_version") != CURRENT_SCHEMA_VERSION:
        result["schema"] = CURRENT_SCHEMA
        result["schema_version"] = CURRENT_SCHEMA_VERSION
        changes.append(f"schema migrated from {source_schema!r} to {CURRENT_SCHEMA}")
    previous_manifest = str(result.get("content_manifest_hash") or "")
    current_manifest = manifest_digest()
    if current_manifest and previous_manifest != current_manifest:
        if previous_manifest:
            result.setdefault("migration_legacy", {}).setdefault("provenance", {})[
                "previous_content_manifest_hash"
            ] = previous_manifest
        changes.append("content manifest provenance updated")
    try:
        current_game_version = package_version()
    except RuntimeProblem:
        current_game_version = ""
    if current_game_version and result.get("game_version") != current_game_version:
        changes.append(f"game_version updated to {current_game_version}")
    if changes:
        result = ensure_runtime_metadata(result)
    else:
        # A current valid save migration is byte-stable; do not touch updated_at.
        result = copy.deepcopy(data)
    return result, changes


def load_control() -> tuple[dict, dict, dict]:
    registry = load_yaml(REGISTRY_PATH)
    routes = load_yaml(ROUTES_PATH)
    if not isinstance(registry, dict) or registry.get("schema") != "machadan-canonical-registry-v1":
        raise RuntimeProblem("unsupported or missing canonical registry")
    if not isinstance(routes, dict) or routes.get("schema") != "machadan-routing-v1":
        raise RuntimeProblem("unsupported or missing routing table")
    resources = registry.get("resources")
    if not isinstance(resources, dict):
        raise RuntimeProblem("registry.resources must be a mapping")
    return registry, routes, resources


def load_anchors() -> dict:
    try:
        data = json.loads(ANCHORS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeProblem("anchors.json missing or invalid; run check_knowledge.py --anchors") from exc
    if data.get("schema_version") != 2:
        raise RuntimeProblem("anchors.json is legacy; run check_knowledge.py --anchors")
    return data


def resolve_scene(routes: dict, requested: str) -> str:
    if requested in routes.get("scene_packs", {}):
        return requested
    folded = requested.casefold()
    for scene_id, pack in routes.get("scene_packs", {}).items():
        for alias in pack.get("aliases", []):
            if str(alias).casefold() == folded:
                return scene_id
    raise RuntimeProblem(f"unknown scene {requested!r}; choose one of {sorted(routes.get('scene_packs', {}))}")


def resource_path(resources: dict, resource_id: str) -> Path:
    item = resources.get(resource_id)
    if not isinstance(item, dict):
        raise RuntimeProblem(f"unknown resource id: {resource_id}")
    relative = item.get("path")
    if not relative:
        raise RuntimeProblem(f"resource {resource_id} has no active path")
    path = (ROOT / str(relative)).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RuntimeProblem(f"resource escapes runtime root: {resource_id}") from exc
    if not path.is_file() and item.get("mutable") is True and item.get("initialize_from"):
        initialize_inventories({resource_id})
    if not path.is_file():
        raise RuntimeProblem(f"required resource missing: {resource_id} -> {relative}")
    return path


def anchor_for_selector(index: dict, relative: str, selector: dict) -> dict:
    info = index.get("files", {}).get(relative)
    if not info:
        raise RuntimeProblem(f"file is not indexed: {relative}")
    anchors = info.get("anchors", [])
    selector_id = str(selector.get("id") or "")
    if selector_id:
        exact = [item for item in anchors if item.get("id") == selector_id]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise RuntimeProblem(f"selector {relative}#{selector_id} is ambiguous")
    match = str(selector.get("match") or "")
    if not match:
        raise RuntimeProblem(f"selector lacks id and match for {relative}")
    title_matches = [item for item in anchors if match.casefold() in str(item.get("title", "")).casefold()]
    if len(title_matches) == 1:
        return title_matches[0]
    lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
    hit_lines = [number for number, line in enumerate(lines, 1) if match.casefold() in line.casefold()]
    containing = []
    for item in anchors:
        if any(item["start"] <= number <= item["end"] for number in hit_lines):
            containing.append(item)
    if containing:
        containing.sort(key=lambda item: (item["line_count"], -item["start"]))
        smallest = containing[0]
        if len(containing) == 1 or smallest["line_count"] < containing[1]["line_count"]:
            return smallest
    raise RuntimeProblem(f"selector not uniquely resolved: {relative} {selector_id}/{match}")


def section_text(path: Path, anchor: dict) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[anchor["start"] - 1:anchor["end"]])


def persona_paths(routes: dict, requested: list[str], save: dict | None) -> list[Path]:
    mapping = routes.get("persona_files", {})
    resolved: list[Path] = []

    def resolve(value: str, explicit: bool) -> Path | None:
        relative = mapping.get(value)
        if relative:
            path = ROOT / relative
            if not path.is_file():
                raise RuntimeProblem(f"mapped character persona is missing: {value!r} -> {relative}")
            return path
        candidates = list((ROOT / "人格").glob(f"{value}.md"))
        if not candidates:
            for path in (ROOT / "人格").glob("*.md"):
                text = path.read_text(encoding="utf-8")
                if re.search(rf"CHAR_ID:\s*{re.escape(value)}\b", text) or path.stem.casefold() == value.casefold():
                    candidates.append(path)
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1 and explicit:
            raise RuntimeProblem(f"character {value!r} has ambiguous packaged personas")
        return None

    for value in requested:
        path = resolve(str(value), explicit=True)
        if path is not None and path not in resolved:
            resolved.append(path)
    if save:
        for member in save.get("party", []) if isinstance(save.get("party"), list) else []:
            if isinstance(member, dict):
                values = [str(member[key]) for key in ("character_id", "char_id", "name") if member.get(key)]
                for value in values:
                    path = resolve(value, explicit=False)
                    if path is not None:
                        if path not in resolved:
                            resolved.append(path)
                        break
    return resolved


def _entry_list(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _prepare_context_locked(args: argparse.Namespace) -> dict:
    from context_loader import build_context
    return build_context(args, SimpleNamespace(**globals()))


def prepare_context(args: argparse.Namespace) -> dict:
    locks: list[Path] = []
    if args.save:
        locks.append(save_lock_path(Path(args.save).expanduser()))
    if getattr(args, "candidate_save_output", None):
        locks.append(save_lock_path(Path(args.candidate_save_output).expanduser()))
    if not locks:
        return _prepare_context_locked(args)
    with file_locks(locks):
        return _prepare_context_locked(args)


def _is_early_route_event(value: object) -> bool:
    """Canonical EV-D10, including generation-scoped validated stock copies."""
    return isinstance(value, str) and (value == "EV-D10" or value.endswith("-EV-D10"))


def default_inventory(kind: str) -> dict:
    limits = {
        "mobs": {"town": 12, "companions": 12, "brothel": 12, "travelers": 12, "students": 12},
        "events": {"town": 15, "road": 15, "dungeon": 15},
    }[kind]
    return {"schema": "machadan-inventory-v1", "kind": kind, "limits": limits,
            "entries": [], "applied_runs": [], "use_receipts": {}, "updated_at": now_iso()}


INVENTORY_CATEGORIES = {
    "mobs": {"街の住人": "town", "仲間候補": "companions", "娼館キャスト": "brothel",
             "旅人": "travelers", "学院生徒": "students"},
    "events": {"街": "town", "道中": "road", "ダンジョン": "dungeon"},
}


def _seed_timestamp(text: str) -> str:
    match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text[:500])
    return (match.group(0) + "T00:00:00+00:00") if match else "1970-01-01T00:00:00+00:00"


def inventory_from_markdown(path: Path, kind: str, source_id: str) -> dict:
    """Deterministically migrate the bundled Markdown seed into mutable YAML."""
    text = path.read_text(encoding="utf-8")
    categories = INVENTORY_CATEGORIES[kind]
    state = default_inventory(kind)
    state["entries"] = []
    state["updated_at"] = _seed_timestamp(text)
    state["seed"] = {"resource": source_id, "path": path.relative_to(ROOT).as_posix(),
                     "sha256": sha256_bytes(text.encode("utf-8"))}
    current_category: str | None = None
    current: dict | None = None
    current_field: str | None = None

    def finish() -> None:
        nonlocal current
        if current is None:
            return
        fields = current.get("fields", {})
        raw_status = str(fields.get("状態", "未使用"))
        current["status"] = "unused" if "未使用" in raw_status else "used"
        if kind == "mobs":
            metadata = str(current.pop("metadata", ""))
            age = re.search(r"(\d+)歳", metadata)
            if age:
                current["age"] = int(age.group(1))
            else:
                current["age"] = None
                current["adult_status"] = "canonical_adult"
            pieces = [piece.strip() for piece in metadata.split("・")]
            if len(pieces) > 1:
                current["gender"] = pieces[1]
            if len(pieces) > 2:
                current["role"] = "・".join(pieces[2:])
        state["entries"].append(current)
        current = None

    entry_re = re.compile(r"^###\s+([A-Z]+-[A-Z]{0,2}\d+)\s+(.+?)(?:\s+\((.+)\))?\s*$")
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            finish()
            title = re.sub(r"\s*\([^)]*\)\s*$", "", line[3:].strip())
            current_category = next((value for label, value in categories.items() if title == label), None)
            current_field = None
            continue
        match = entry_re.match(line)
        if match:
            finish()
            if current_category is None:
                raise RuntimeProblem(f"inventory entry outside a recognized category: {line}")
            current = {"id": match.group(1), "category": current_category, "fields": {}}
            if kind == "mobs":
                current["name"] = match.group(2).strip()
                current["metadata"] = (match.group(3) or "").strip()
            else:
                current["title"] = match.group(2).strip()
                if match.group(3):
                    current["type"] = match.group(3).strip()
            current_field = None
            continue
        if current is None:
            continue
        bullet = re.match(r"^-\s*([^:]+):\s*(.*)$", line)
        if bullet:
            current_field = bullet.group(1).strip()
            current["fields"][current_field] = bullet.group(2).strip()
        elif current_field and line.strip() and not line.startswith("#"):
            current["fields"][current_field] += " " + line.strip()
    finish()
    return state


def validate_inventory_state(data: Any, kind: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return [f"{kind} inventory root must be a mapping"], warnings
    if data.get("schema") != "machadan-inventory-v1" or data.get("kind") != kind:
        errors.append(f"{kind} inventory schema/kind mismatch")
    limits = data.get("limits")
    entries = data.get("entries")
    if not isinstance(limits, dict) or not isinstance(entries, list):
        return errors + [f"invalid {kind} inventory structure"], warnings
    expected_categories = set(INVENTORY_CATEGORIES[kind].values())
    if set(limits) != expected_categories:
        errors.append(f"{kind} inventory categories must be {sorted(expected_categories)}")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{kind} entries[{index}] must be a mapping")
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id or entry_id in seen_ids:
            errors.append(f"{kind} entries[{index}] has missing/duplicate id {entry_id!r}")
        seen_ids.add(entry_id)
        category = entry.get("category")
        if category not in limits:
            errors.append(f"{kind} entry {entry_id} has unknown category {category!r}")
        if entry.get("status", "unused") not in {"unused", "used"}:
            errors.append(f"{kind} entry {entry_id} has invalid status")
        if kind == "mobs":
            name = str(entry.get("name") or "")
            if not name or name.casefold() in seen_names:
                errors.append(f"mob entry {entry_id} has missing/duplicate name {name!r}")
            seen_names.add(name.casefold())
            if not _is_adult_value(entry.get("age"), entry.get("adult_status")):
                errors.append(f"mob entry {entry_id} must have age >= 18 or canonical_adult status")
        else:
            if not (entry.get("title") or entry.get("name")):
                errors.append(f"event entry {entry_id} has no title")
            fields = entry.get("fields")
            if not ((isinstance(fields, dict) and fields) or entry.get("description") or
                    entry.get("content") or entry.get("introduction")):
                errors.append(f"event entry {entry_id} has no content")
    if not isinstance(data.get("applied_runs", []), list):
        errors.append(f"{kind}.applied_runs must be a list")
    if not isinstance(data.get("use_receipts", {}), dict):
        errors.append(f"{kind}.use_receipts must be a mapping")
    if not errors:
        summary = inventory_summary(data)
        for category, values in summary.items():
            if values["unused"] > values["limit"]:
                errors.append(f"{kind}/{category} has {values['unused']} unused entries; limit is {values['limit']}")
    return errors, warnings


def _initialize_inventories_unlocked(only: set[str] | None = None, force: bool = False) -> dict:
    from inventory_lifecycle import initialize_unlocked
    return initialize_unlocked(SimpleNamespace(**globals()), only, force)


def initialize_inventories(only: set[str] | None = None, force: bool = False) -> dict:
    from inventory_lifecycle import initialize
    return initialize(SimpleNamespace(**globals()), only, force)


INVENTORY_MUTABLE_ENTRY_KEYS = {
    "status", "used_by", "used_turn", "used_at", "use_transaction_id",
}


def _sync_inventory_seed_unlocked(resource_id: str, kind: str, keep: int = 50) -> dict:
    """Refresh bundled seed content without discarding mutable campaign state."""
    registry, _, resources = load_control()
    del registry
    resource = resources.get(resource_id)
    if not isinstance(resource, dict):
        raise RuntimeProblem(f"missing mutable inventory resource {resource_id}")
    target = (ROOT / str(resource.get("path") or "")).resolve()
    relative_target = target.relative_to(ROOT).as_posix()
    if not target.is_file():
        return {"kind": kind, "path": relative_target, "status": "absent",
                "updated": [], "missing": [], "preserved_extra": [], "backup": None}

    existing = load_yaml(target)
    existing_errors, _ = validate_inventory_state(existing, kind)
    if existing_errors:
        raise RuntimeProblem(
            f"cannot synchronize invalid {kind} inventory: " + "; ".join(existing_errors)
        )
    seed_id = str(resource.get("initialize_from") or "")
    seed = resources.get(seed_id)
    if not isinstance(seed, dict) or not seed.get("path"):
        raise RuntimeProblem(f"{resource_id} has invalid initialize_from {seed_id!r}")
    seed_path = (ROOT / str(seed["path"])).resolve()
    if not seed_path.is_file():
        raise RuntimeProblem(f"inventory seed missing: {seed_id} -> {seed.get('path')}")
    canonical = inventory_from_markdown(seed_path, kind, seed_id)
    canonical_errors, _ = validate_inventory_state(canonical, kind)
    if canonical_errors:
        raise RuntimeProblem("inventory seed migration failed: " + "; ".join(canonical_errors))

    canonical_by_id = {
        str(entry.get("id")): entry for entry in canonical["entries"]
        if isinstance(entry, dict) and entry.get("id")
    }
    old_ids = {
        str(entry.get("id")) for entry in existing["entries"]
        if isinstance(entry, dict) and entry.get("id")
    }
    updated: list[str] = []
    merged_entries: list[dict] = []
    for old_entry in existing["entries"]:
        entry_id = str(old_entry.get("id"))
        seed_entry = canonical_by_id.get(entry_id)
        if seed_entry is None:
            merged_entries.append(copy.deepcopy(old_entry))
            continue
        merged_entry = copy.deepcopy(seed_entry)
        for key in INVENTORY_MUTABLE_ENTRY_KEYS:
            if key in old_entry:
                merged_entry[key] = copy.deepcopy(old_entry[key])
        # inventory-use mirrors operational status into the human-readable field.
        if old_entry.get("status") == "used" and isinstance(old_entry.get("fields"), dict):
            old_status = old_entry["fields"].get("状態")
            if old_status is not None and isinstance(merged_entry.get("fields"), dict):
                merged_entry["fields"]["状態"] = copy.deepcopy(old_status)
        if merged_entry != old_entry:
            updated.append(entry_id)
        merged_entries.append(merged_entry)

    missing = sorted(set(canonical_by_id) - old_ids)
    for seed_entry in canonical["entries"]:
        if isinstance(seed_entry, dict) and str(seed_entry.get("id")) in missing:
            merged_entries.append(copy.deepcopy(seed_entry))
    preserved_extra = [
        str(entry.get("id")) for entry in existing["entries"]
        if isinstance(entry, dict) and str(entry.get("id")) not in canonical_by_id
    ]
    merged = copy.deepcopy(existing)
    for key in ("schema", "kind", "limits", "seed"):
        merged[key] = copy.deepcopy(canonical[key])
    merged["entries"] = merged_entries
    merged["applied_runs"] = copy.deepcopy(existing.get("applied_runs", []))
    merged["use_receipts"] = copy.deepcopy(existing.get("use_receipts", {}))

    comparable = copy.deepcopy(merged)
    comparable["updated_at"] = existing.get("updated_at")
    changed = comparable != existing
    backup = None
    if changed:
        merged["updated_at"] = now_iso()
        merged_errors, _ = validate_inventory_state(merged, kind)
        if merged_errors:
            raise RuntimeProblem(
                f"synchronized {kind} inventory would be invalid: " + "; ".join(merged_errors)
            )
        backup = _inventory_backup(target, kind, "seed-sync", keep)
        atomic_write(target, dump_yaml(merged))
    return {
        "kind": kind, "path": relative_target,
        "status": "updated" if changed else "unchanged",
        "updated": updated, "missing": missing, "preserved_extra": preserved_extra,
        "backup": backup.relative_to(ROOT).as_posix() if backup else None,
    }


def sync_inventory_seeds(only_kinds: set[str] | None = None, keep: int = 50) -> dict:
    """Synchronize only inventories that already exist; never initialize missing state."""
    if keep < 1:
        raise RuntimeProblem("--keep must be >= 1")
    mapping = {"EVENT_INVENTORY_STATE": "events", "MOB_INVENTORY_STATE": "mobs"}
    requested = [
        (resource_id, kind) for resource_id, kind in mapping.items()
        if only_kinds is None or kind in only_kinds
    ]
    _, _, resources = load_control()
    selected: list[tuple[str, str]] = []
    absent: list[dict] = []
    for resource_id, kind in requested:
        resource = resources.get(resource_id)
        if not isinstance(resource, dict):
            raise RuntimeProblem(f"missing mutable inventory resource {resource_id}")
        target = (ROOT / str(resource.get("path") or "")).resolve()
        if target.is_file():
            selected.append((resource_id, kind))
        else:
            absent.append({
                "kind": kind, "path": target.relative_to(ROOT).as_posix(), "status": "absent",
                "updated": [], "missing": [], "preserved_extra": [], "backup": None,
            })
    with file_locks([inventory_lock_path(kind) for _, kind in selected]):
        results = [
            _sync_inventory_seed_unlocked(resource_id, kind, keep)
            for resource_id, kind in selected
        ]
    by_kind = {item["kind"]: item for item in results + absent}
    results = [by_kind[kind] for _, kind in requested]
    return {"inventories": results,
            "changed": [item["kind"] for item in results if item["status"] == "updated"]}


def load_inventory(path: Path, kind: str) -> dict:
    if not path.exists():
        resource_id = "MOB_INVENTORY_STATE" if kind == "mobs" else "EVENT_INVENTORY_STATE"
        initialize_inventories({resource_id})
    data = load_yaml(path)
    errors, _ = validate_inventory_state(data, kind)
    if errors:
        raise RuntimeProblem(f"invalid {kind} inventory: " + "; ".join(errors))
    data.setdefault("applied_runs", [])
    return data


def inventory_summary(data: dict) -> dict:
    result = {}
    for category, limit in data["limits"].items():
        entries = [item for item in data["entries"] if isinstance(item, dict) and item.get("category") == category]
        unused = sum(1 for item in entries if item.get("status", "unused") == "unused")
        result[category] = {"limit": int(limit), "total": len(entries), "unused": unused,
                            "open": max(0, int(limit) - unused)}
    return result


def validate_inventory_entry(entry: Any, kind: str, limits: dict) -> None:
    if not isinstance(entry, dict):
        raise RuntimeProblem(f"{kind} inventory entry must be an object")
    for key in ("id", "category", "status"):
        if not entry.get(key):
            raise RuntimeProblem(f"{kind} inventory entry missing {key}")
    if entry["category"] not in limits:
        raise RuntimeProblem(f"unknown {kind} category: {entry['category']}")
    if entry.get("status", "unused") != "unused":
        raise RuntimeProblem("new inventory entries must have status=unused")
    if kind == "mobs":
        if not entry.get("name"):
            raise RuntimeProblem("mob entry missing name")
        age = entry.get("age")
        if not (_is_integer(age) and age >= 18):
            raise RuntimeProblem("newly generated mob append requires a numeric age >= 18")
    else:
        if not entry.get("title"):
            raise RuntimeProblem("event entry missing title")
        fields = entry.get("fields")
        if not ((isinstance(fields, dict) and fields) or entry.get("description") or
                entry.get("content") or entry.get("introduction")):
            raise RuntimeProblem("event entry must include non-empty fields, description, content or introduction")


def _cmd_new_save_locked(args: argparse.Namespace) -> dict:
    data = load_yaml(SAVE_TEMPLATE)
    if not isinstance(data, dict):
        raise RuntimeProblem("save template root must be a mapping")
    data = ensure_runtime_metadata(data, args.campaign_id, new=True)
    errors, warnings = validate_save_data(data)
    if errors:
        raise RuntimeProblem("save template validation failed: " + "; ".join(errors))
    output = Path(args.output).expanduser()
    if output.exists() and not args.force:
        raise RuntimeProblem(f"refusing to overwrite existing save: {output}")
    atomic_write(output, dump_yaml(data))
    return {"ok": True, "output": str(output), "campaign_id": data["campaign_id"],
            "warnings": warnings}


def cmd_new_save(args: argparse.Namespace) -> dict:
    output = Path(args.output).expanduser()
    with file_locks([save_lock_path(output)]):
        return _cmd_new_save_locked(args)


def cmd_validate_save(args: argparse.Namespace) -> tuple[int, dict]:
    data = load_yaml(Path(args.path).expanduser())
    errors, warnings = validate_save_data(data)
    return (0 if not errors else 1), {"ok": not errors, "path": args.path,
                                     "errors": errors, "warnings": warnings}


def _validated_status_save(path: Path) -> tuple[dict, list[str]]:
    data = load_yaml(path)
    errors, warnings = validate_save_data(data)
    if errors:
        raise RuntimeProblem("status source save is invalid: " + "; ".join(errors))
    return data, warnings


def _finance_forecast(data: dict) -> dict:
    """Read-only view of the existing lodging and collection rules."""
    debt = data.get("debt_state", {})
    paid, due = debt.get("cycle_paid", 0), debt.get("scheduled_due", 0)
    unpaid = max(0, due - min(due, paid))
    penalty = _ceil_to_10(max(50, (unpaid * 20 + 99) // 100)) if unpaid else 0
    if unpaid and paid == 0:
        penalty = max(100, penalty)
    lodging, unknown = 200, []
    for member in data.get("party", []):
        share = member.get("inn_share")
        if share == "leader":
            lodging += 200
        elif share == "self":
            lodging += max(0, 200 - member.get("gold", 0))
        else:
            unknown.append(member.get("name") or "仲間")
    needed = min(debt.get("principal", 0), unpaid)
    shortage = max(0, needed - data.get("player", {}).get("gold", 0))
    lines = [f"通常の部屋に泊まる場合：借金+{lodging}G（追加の部屋代を除く）",
             f"次回取立て：Day {debt.get('next_collection_day')}・残り{needed}G",
             f"これ以上払わずに迎える場合：借金+{penalty}G"]
    if shortage:
        lines.append(f"今の手持ちでは{shortage}G不足。一部払い・今回は払わない、も選べます")
    if unknown:
        lines.append("宿代の分担を確認：" + "、".join(unknown))
    return {"remaining_due": needed, "no_further_payment_penalty": penalty,
            "standard_room_debt": lodging, "lodging_share_unconfirmed": unknown,
            "cash_shortage": shortage, "lines": lines}


def _status_snapshot(data: dict) -> dict:
    instances = {
        item.get("instance_id"): item for item in data.get("item_instances", [])
        if isinstance(item, dict) and isinstance(item.get("instance_id"), str)
    }
    active_reservations = {
        item.get("instance_id") for item in data.get("inventory", {}).get("reservations", [])
        if isinstance(item, dict) and item.get("status") == "reserved"
        and isinstance(item.get("instance_id"), str)
    }

    def character_view(character: dict) -> dict:
        value = copy.deepcopy(character)
        state = data.get("runtime_state", {})
        value["ero_scene"] = state.get("ero_scene", state.get("active_scene") in {"ero", "style"})
        value["ero_style"] = data.get("ero_style")
        equipment = value.get("equipment")
        if isinstance(equipment, dict):
            for slot in ("weapon", "armor", "offhand"):
                instance_id = equipment.get(f"{slot}_instance_id")
                instance = instances.get(instance_id)
                equipment[f"{slot}_name"] = (
                    instance.get("name") if isinstance(instance, dict) else None
                )
        return value

    inventory = copy.deepcopy(data.get("inventory", {}))
    inventory["carried_instances"] = []
    warehouse = inventory.get("warehouse")
    if isinstance(warehouse, dict):
        warehouse["instances"] = [
            copy.deepcopy(instances[instance_id]) for instance_id in warehouse.get("instance_ids", [])
            if instance_id in instances
        ]
    for instance in data.get("item_instances", []):
        if not isinstance(instance, dict) or instance.get("location") != "bag":
            continue
        value = copy.deepcopy(instance)
        value["reserved"] = value.get("instance_id") in active_reservations
        definition = next(
            (item for item in data.get("item_definitions", []) if isinstance(item, dict)
             and item.get("item_def_id") == value.get("item_def_id")), None,
        )
        value["category"] = (
            definition.get("category") if isinstance(definition, dict) else
            value.get("specification_snapshot", {}).get("category", "")
            if isinstance(value.get("specification_snapshot"), dict) else ""
        )
        inventory["carried_instances"].append(value)
    transaction = data.get("transaction", {})
    world = data.get("world_state", {})
    debt = data.get("debt_state", {})
    return {
        "schema": "machadan-status-snapshot-v1",
        "title": "冒険者ステータス",
        "header": {
            "day": world.get("day"),
            "turn": transaction.get("last_committed_turn"),
            "revision": data.get("save_revision"),
            "gold": data.get("player", {}).get("gold"),
            "debt": {
                key: debt.get(key) for key in (
                    "principal", "scheduled_due", "next_collection_day", "collection_pending",
                )
            },
        },
        "characters": [
            character_view(character) for character in [data.get("player"), *data.get("party", [])]
            if isinstance(character, dict)
        ],
        "inventory": inventory,
        "finance_forecast": _finance_forecast(data),
    }


def _status_text(snapshot: dict, mode: str = "compact", character_id: str | None = None) -> str:
    header = snapshot["header"]
    debt = header["debt"]
    lines = [
        f"{header['day']}日目 / Turn {header['turn']} / Rev {header['revision']} / {header.get('gold', 0)}G",
        (
            f"借金 {debt['principal']}G / 次回 {debt['next_collection_day']}日目 "
            f"({'取立て待ち' if debt['collection_pending'] else '予定 '+str(debt['scheduled_due'])+'G'})"
        ),
    ]
    lines.extend(snapshot.get("finance_forecast", {}).get("lines", []))
    characters = [
        character for character in snapshot["characters"]
        if character_id is None or character.get("character_id") == character_id
    ]
    for character in characters:
        lp, mp = character.get("lp", {}), character.get("mp", {})
        lines.append(
            f"{character.get('name') or '名前未設定'} [{character.get('job') or '無職'}] "
            f"LP {lp.get('cur', 0)}/{lp.get('max', 0)}  MP {mp.get('cur', 0)}/{mp.get('max', 0)}"
        )
        if mode == "character":
            stats = character.get("effective_stats", {})
            lines.append("  " + " ".join(f"{key.upper()} {stats.get(key, 0)}" for key in STAT_KEYS))
            profile = character.get("job_profile", {})
            lines.append(
                f"  役割 {profile.get('combat_role', '未分類')} / "
                f"ソロ {profile.get('solo_suitability', '未分類')}"
            )
        if mode == "equipment":
            equipment = character.get("equipment", {})
            lines.append(
                "  装備 " + " / ".join(str(equipment.get(key) or "なし") for key in (
                    "weapon_name", "armor_name", "offhand_name",
                ))
            )
    inventory = snapshot["inventory"]
    bag = inventory.get("bag", {})
    physical = bag.get("max_slots", 0)
    bonus = bag.get("skill_bonus_slots", 0)
    effective = bag.get("effective_max_slots", physical)
    lines.append(
        f"遠征袋 {bag.get('used_slots', 0)}/{effective}枠 "
        f"(物理{physical}+ 心得{bonus})"
    )
    if mode == "compact":
        return "\n".join(lines)
    for stack in inventory.get("carried_stacks", []) if mode == "inventory" else []:
        if not isinstance(stack, dict):
            continue
        count = stack.get("count", 0)
        reserved = stack.get("reserved_quantity", 0)
        lines.append(
            f"- {stack.get('name', stack.get('item_def_id'))} ×{count} "
            f"(使用可 {count - reserved}・予約 {reserved})"
        )
    for instance in inventory.get("carried_instances", []) if mode == "inventory" else []:
        if isinstance(instance, dict):
            lines.append(
                f"- {instance.get('name', instance.get('instance_id'))} ×1"
                + (" (予約中)" if instance.get("reserved") else "")
            )
    warehouse = inventory.get("warehouse", {})
    warehouse_count = sum(
        item.get("count", 0) for item in warehouse.get("stacks", []) if isinstance(item, dict)
    ) + len(warehouse.get("instance_ids", []))
    lines.append(f"倉庫 {warehouse_count}点")
    if mode == "warehouse":
        for stack in warehouse.get("stacks", []):
            if isinstance(stack, dict):
                lines.append(f"- {stack.get('name', stack.get('item_def_id'))} ×{stack.get('count', 0)}")
        for instance in warehouse.get("instances", []):
            if isinstance(instance, dict):
                lines.append(f"- {instance.get('name', instance.get('instance_id'))} ×1")
    return "\n".join(lines)


def cmd_status_view(args: argparse.Namespace) -> dict:
    data, warnings = _validated_status_save(Path(args.path).expanduser())
    snapshot = _status_snapshot(data)
    if args.character_id and not any(
        item.get("character_id") == args.character_id for item in snapshot["characters"]
    ):
        raise RuntimeProblem(f"unknown active character_id: {args.character_id}")
    return {
        "ok": True, "mode": args.mode,
        "text": _status_text(snapshot, args.mode, args.character_id),
        "snapshot": snapshot, "warnings": warnings,
    }


def cmd_render_status_widget(args: argparse.Namespace) -> dict:
    data, warnings = _validated_status_save(Path(args.path).expanduser())
    return _write_status_widget(_status_snapshot(data), warnings, args.output, args.force)


def _write_status_widget(snapshot: dict, warnings: list, output_path: str, force: bool) -> dict:
    if not HUD_TEMPLATE.is_file():
        raise RuntimeProblem(f"status dashboard template is missing: {HUD_TEMPLATE}")
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = HUD_TEMPLATE.read_text(encoding="utf-8")
    if template.count("__STATUS_SNAPSHOT_JSON__") != 1:
        raise RuntimeProblem("status dashboard template has an invalid snapshot token")
    rendered = template.replace("__STATUS_SNAPSHOT_JSON__", payload)
    output = Path(output_path).expanduser()
    if output.exists() and not force:
        if output.read_text(encoding="utf-8") == rendered:
            return {"ok": True, "idempotent": True, "output": str(output), "warnings": warnings}
        raise RuntimeProblem(f"refusing to overwrite existing status widget: {output}")
    atomic_write(output, rendered)
    return {
        "ok": True, "idempotent": False, "output": str(output),
        "snapshot_schema": snapshot["schema"], "warnings": warnings,
    }


def _activate_renewal_benefit(
    data: dict, benefit_id: str | None, *, day: int, player_choice: bool,
) -> str | None:
    """Compatibility entry point: new contracts never select enterprise perks."""
    from debt_contracts import apply_payoff_unlock, expected_benefit
    stage = data["debt_state"]["contract_cycle_index"]
    if benefit_id is not None and benefit_id != expected_benefit(stage):
        raise RuntimeProblem("payoff benefits are fixed by the completed contract stage")
    return apply_payoff_unlock(data, stage, day=day)


def cmd_resolve_debt_collection(args: argparse.Namespace) -> dict:
    from debt_contracts import candidate_path, committed_retry, write_candidate, debt_unlocks
    source = Path(args.save).expanduser()
    if source.is_symlink():
        raise RuntimeProblem("debt source must not be a symbolic link")
    source = source.resolve()
    data, warnings = _validated_status_save(source)
    transaction_id = safe_id(args.transaction_id)
    output = candidate_path(SimpleNamespace(**globals()), source, args.output)
    if committed_retry(SimpleNamespace(**globals()), data, output, transaction_id):
        entry = next(item for item in data["debt_state"]["collection_ledger"]
                     if item.get("transaction_id") == transaction_id)
        if entry.get("event_kind") != "collection" or entry.get("payment") != args.payment:
            raise RuntimeProblem("debt transaction retry changed its collection/payment")
        return {"ok": True, "idempotent": True, "output": str(output), "transaction_id": transaction_id}
    candidate = copy.deepcopy(data)
    debt = candidate["debt_state"]
    player = candidate["player"]
    day = candidate["world_state"]["day"]
    if debt.get("collection_pending") is not True or day < debt.get("next_collection_day", day + 1):
        raise RuntimeProblem("no pending Lilith collection to resolve")
    payment = args.payment
    if payment < 0 or payment > player["gold"] or payment > debt["principal"]:
        raise RuntimeProblem("--payment exceeds available gold or debt principal")
    if payment % 100 != 0 and payment != debt["principal"]:
        raise RuntimeProblem("--payment must use 100G units except the exact final remainder")
    transaction_id = safe_id(args.transaction_id)
    before_principal = debt["principal"]
    due_before = debt["scheduled_due"]
    total_paid = debt["cycle_paid"] + payment
    unpaid = max(0, due_before - min(due_before, total_paid))
    paid_off = payment == before_principal
    penalty = 0
    if unpaid > 0 and not paid_off:
        penalty = _ceil_to_10(max(50, (unpaid * 20 + 99) // 100))
        if total_paid == 0:
            penalty = max(100, penalty)
    cycle_before = debt["contract_cycle_index"]
    player["gold"] -= payment
    if paid_off:
        debt["contract_cycle_index"] += 1
        debt["contract_id"] = f"lilith-debt-cycle-{debt['contract_cycle_index']}"
        from debt_contracts import principal_schedule
        debt["principal"] = principal_schedule(debt["contract_cycle_index"])
        debt["scheduled_due"] = 500 + 250 * debt["contract_cycle_index"]
        candidate["world_state"]["goals"]["debt_clear"] = True
        _activate_renewal_benefit(
            candidate, getattr(args, "benefit", None), day=day, player_choice=getattr(args, "benefit", None) is not None,
        )
    else:
        debt["principal"] = before_principal - payment + penalty
        if total_paid > 0:
            debt["scheduled_due"] = min(
                2500 + 500 * cycle_before, due_before + 250,
            )
    debt["next_collection_day"] += 5
    debt["cycle_paid"] = 0
    debt["collection_pending"] = False
    debt["last_collection_day"] = day
    debt["collection_serial"] += 1
    debt["positive_payment_collections"] += int(total_paid > 0)
    debt["full_payment_collections"] += int(total_paid >= due_before)
    debt["missed_collections"] += int(total_paid == 0)
    player["debt"] = debt["principal"]
    debt["collection_ledger"].append({
        "collection_id": f"debt-event-{debt['collection_serial']}-{transaction_id}"[:80],
        "transaction_id": transaction_id, "event_kind": "collection",
        "collection_day": day,
        "contract_id_before": data["debt_state"]["contract_id"],
        "contract_id_after": debt["contract_id"],
        "scheduled_due_before": due_before, "cycle_paid": total_paid,
        "payment": payment, "unpaid_due": unpaid, "penalty": penalty,
        "principal_before_payment": before_principal,
        "principal_after_resolution": debt["principal"],
        "next_collection_day_after": debt["next_collection_day"],
        "scheduled_due_after": debt["scheduled_due"],
        "contract_cycle_index_before": cycle_before,
        "contract_cycle_index_after": debt["contract_cycle_index"],
    })
    if paid_off:
        from debt_contracts import payoff_metadata
        debt["collection_ledger"][-1].update(payoff_metadata(data, debt["contract_cycle_index"]))
    identical, candidate_warnings = write_candidate(
        SimpleNamespace(**globals()), data, candidate, output, transaction_id,
        force=getattr(args, "force", False),
    )
    return {
        "ok": True, "idempotent": identical, "output": str(output), "transaction_id": transaction_id,
        "payment": payment, "penalty": penalty, "renewed": paid_off,
        "principal": debt["principal"], "next_collection_day": debt["next_collection_day"],
        "unlocks": debt_unlocks(candidate), "warnings": warnings + candidate_warnings,
    }


def cmd_reward_effect(args: argparse.Namespace) -> dict:
    current_path = Path(args.current).expanduser()
    candidate_path = Path(args.candidate).expanduser()
    with file_locks([save_lock_path(current_path), save_lock_path(candidate_path)]):
        current = load_yaml(current_path)
        candidate = load_yaml(candidate_path)
    if not isinstance(current, dict) or not isinstance(candidate, dict):
        raise RuntimeProblem("both reward-effect saves must be mappings")
    if current.get("campaign_id") != candidate.get("campaign_id"):
        raise RuntimeProblem("reward-effect saves must have the same campaign_id")
    target = str(args.target)
    allowed = {item for values in REWARD_EFFECT_TARGETS.values() for item in values}
    if target not in allowed:
        raise RuntimeProblem(f"unsupported reward effect target: {target}")
    before_value = _reward_effect_value(current, target)
    after_value = _reward_effect_value(candidate, target)
    payload = {
        "ok": True,
        "target": target,
        "before_sha256": _reward_value_hash(before_value),
        "after_sha256": _reward_value_hash(after_value),
        "changed": before_value != after_value,
    }
    if target == "player.gold" and _is_integer(before_value) and _is_integer(after_value):
        payload["amount"] = after_value - before_value
    elif target == "inventory_bundle":
        before_counts = _reward_item_counts(current)
        after_counts = _reward_item_counts(candidate)
        if before_counts is None or after_counts is None:
            raise RuntimeProblem("reward-effect requires valid named item stacks")
        names = sorted(set(before_counts) | set(after_counts))
        payload["added_items"] = [
            {"item_name": name, "quantity": after_counts.get(name, 0) - before_counts.get(name, 0)}
            for name in names
            if after_counts.get(name, 0) > before_counts.get(name, 0)
        ]
        payload["removed_items"] = [
            {"item_name": name, "quantity": before_counts.get(name, 0) - after_counts.get(name, 0)}
            for name in names
            if after_counts.get(name, 0) < before_counts.get(name, 0)
        ]
    elif target == "world_state.entitlements":
        before_entries = before_value if isinstance(before_value, list) else []
        after_entries = after_value if isinstance(after_value, list) else []
        before_ids = {
            item.get("entitlement_id") for item in before_entries
            if isinstance(item, dict) and isinstance(item.get("entitlement_id"), str)
        }
        payload["added_entitlements"] = [
            {"entitlement_id": item["entitlement_id"]}
            for item in after_entries
            if isinstance(item, dict) and isinstance(item.get("entitlement_id"), str)
            and item["entitlement_id"] not in before_ids
        ]
    elif target == "session_log":
        before_entries = _reward_log_entries(current)
        after_entries = _reward_log_entries(candidate)
        if before_entries is None or after_entries is None:
            raise RuntimeProblem("reward-effect requires session_log.entries lists")
        append_only = (
            len(after_entries) >= len(before_entries) and
            after_entries[:len(before_entries)] == before_entries
        )
        payload["append_only"] = append_only
        payload["appended_log_entries"] = [
            {
                "log_entry_index": index,
                "log_entry_sha256": _reward_value_hash(after_entries[index]),
            }
            for index in range(len(before_entries), len(after_entries))
        ] if append_only else []
    return payload


def _widget_state(raw: Any) -> tuple[dict, str | None]:
    wrapper_id = None
    if isinstance(raw, dict) and raw.get("schema") != "machadan.hearing.widget.v2" and isinstance(raw.get("state"), dict):
        wrapper_id = str(raw.get("widget_id") or raw.get("id") or "") or None
        raw = raw["state"]
    if not isinstance(raw, dict):
        raise RuntimeProblem("widget state root must be a JSON object")
    if raw.get("schema") != "machadan.hearing.widget.v2" or raw.get("schema_version") != 2:
        raise RuntimeProblem("unsupported widget state schema")
    step_id = raw.get("step_id")
    expected_steps = {
        "playmode": 1, "profile": 2, "body_female": 3, "body_male": 3,
        "desire": 4, "partner_preferences": 5,
    }
    if step_id not in expected_steps or raw.get("step") != expected_steps[step_id]:
        raise RuntimeProblem("widget step/step_id mismatch")
    revision = raw.get("revision")
    if not _is_integer(revision) or revision < 0:
        raise RuntimeProblem("widget revision must be an integer >= 0")
    if raw.get("valid") is not True or raw.get("complete") is not True:
        raise RuntimeProblem("widget state must have valid=true and complete=true")
    validation = raw.get("validation")
    if not isinstance(validation, dict) or not isinstance(validation.get("errors"), list):
        raise RuntimeProblem("widget validation.errors must be a list")
    if validation["errors"]:
        raise RuntimeProblem("completed widget state still contains validation errors")
    if not isinstance(raw.get("answers"), dict):
        raise RuntimeProblem("widget answers must be an object")
    return raw, wrapper_id


def _single_answer(value: Any, label: str, required: bool = False) -> str:
    if not isinstance(value, dict):
        if required:
            raise RuntimeProblem(f"{label} answer must be an object")
        return ""
    choice = str(value.get("choice") or "").strip()
    free = str(value.get("free_text") or "").strip()
    result = free or choice
    if required and not result:
        raise RuntimeProblem(f"{label} answer is required")
    return re.sub(r"\s+", " ", result)


def _multi_answer(value: Any, label: str) -> str:
    if not isinstance(value, dict):
        raise RuntimeProblem(f"{label} answer must be an object")
    choices = value.get("choices", [])
    if not isinstance(choices, list) or any(not isinstance(item, str) for item in choices):
        raise RuntimeProblem(f"{label}.choices must be a string list")
    parts = [re.sub(r"\s+", " ", item.strip()) for item in choices if item.strip()]
    free = re.sub(r"\s+", " ", str(value.get("free_text") or "").strip())
    if free:
        parts.append(free)
    return "・".join(parts)


def _multi_list_answer(value: Any, label: str) -> list[str]:
    """Normalize a multi-select answer for a list-valued save field."""
    if not isinstance(value, dict):
        raise RuntimeProblem(f"{label} answer must be an object")
    choices = value.get("choices")
    free_text = value.get("free_text")
    if not isinstance(choices, list) or any(not isinstance(item, str) for item in choices):
        raise RuntimeProblem(f"{label}.choices must be a string list")
    if not isinstance(free_text, str):
        raise RuntimeProblem(f"{label}.free_text must be a string")
    normalized: list[str] = []
    for item in [*choices, free_text]:
        item = re.sub(r"\s+", " ", item.strip())
        if not item or item.startswith("おまかせ") or item.casefold() in {
            "random", "ランダム", "未指定", "なし", "特になし",
        }:
            continue
        if item not in normalized:
            normalized.append(item)
    return normalized


def _partner_height_answer(value: Any, *, legacy_plain_long: bool = False) -> list[str]:
    """Normalize display labels while preserving the old 長身=160cm以上 meaning."""
    aliases = {
        "とても小柄（139cm以下）": "とても小柄",
        "とても小柄(139cm以下)": "とても小柄",
        "小柄（140cm台）": "小柄",
        "小柄(140cm台)": "小柄",
        "標準（150cm台）": "標準",
        "標準(150cm台)": "標準",
        "長身（160cm台）": "長身",
        "長身(160cm台)": "長身",
        "とても長身（170cm以上）": "とても長身",
        "とても長身(170cm以上)": "とても長身",
    }
    normalized: list[str] = []

    def append(item: str) -> None:
        if item not in normalized:
            normalized.append(item)

    for item in _multi_list_answer(value, "body_height"):
        if item in {"長身（160cm以上）", "長身(160cm以上)"}:
            append("長身")
            append("とても長身")
            continue
        canonical = aliases.get(item, item)
        append(canonical)
        if legacy_plain_long and item == "長身":
            append("とても長身")
    return normalized


def _body_line(step_id: str, answers: dict) -> str:
    if step_id == "body_female":
        fields = (("身長", "height", False), ("体つき", "build", True),
                  ("胸", "bust", False), ("ふたなり", "futanari", False))
        prefix = "女性体型"
    else:
        fields = (("身長", "height", False), ("筋肉", "muscle", True), ("サイズ", "size", False))
        prefix = "男性体型"
    rendered = []
    for label, key, multi in fields:
        value = _multi_answer(answers.get(key), key) if multi else _single_answer(answers.get(key), key)
        rendered.append(f"{label}={value or 'おまかせ'}")
    return prefix + ": " + " / ".join(rendered)


def _apply_widget_mapping(save: dict, state: dict) -> list[str]:
    answers = state["answers"]
    step_id = state["step_id"]
    changed: list[str] = []

    def assign(key: str, value: Any) -> None:
        if save.get(key) != value:
            save[key] = value
            changed.append(key)

    if step_id == "playmode":
        raw = _single_answer(answers.get("playmode"), "playmode", required=True)
        folded = raw.casefold()
        if raw in {"A", "RP"} or "主人公として" in raw or folded == "rp":
            assign("play_mode", "RP")
        elif raw in {"B", "GOD"} or "物語の神様" in raw or folded == "god":
            assign("play_mode", "GOD")
        else:
            raise RuntimeProblem("playmode must resolve to canonical RP or GOD")
    elif step_id == "profile":
        name = str(answers.get("name") or "").strip()
        gender = _single_answer(answers.get("gender"), "gender", required=True)
        age = answers.get("age")
        if not _is_integer(age) or age < 18:
            raise RuntimeProblem("profile age must be a numeric integer >= 18")
        player = save.setdefault("player", {})
        for key, value in (("name", name), ("gender", gender), ("age", age)):
            if player.get(key) != value:
                player[key] = value
                changed.append(f"player.{key}")
    elif step_id in {"body_female", "body_male"}:
        assign("player_body", _body_line(step_id, answers))
    elif step_id == "desire":
        assign("desire", _multi_answer(answers.get("desire"), "desire"))
        tachi = _multi_answer(answers.get("yuri_tachi"), "yuri_tachi")
        neko = _multi_answer(answers.get("yuri_neko"), "yuri_neko")
        assign("yuri", f"タチ: {tachi or 'おまかせ・特になし'} / ネコ: {neko or 'おまかせ・特になし'}")
        ng_text = re.sub(r"\s+", " ", str(answers.get("ng") or "").strip())
        assign("ng", [] if ng_text.casefold() in {"", "なし", "特になし", "none"} else [ng_text])
    elif step_id == "partner_preferences":
        partner = save.get("partner_pref")
        if not isinstance(partner, dict):
            raise RuntimeProblem("partner_pref must be a mapping")
        if partner.get("asked") is not True:
            partner["asked"] = True
            changed.append("partner_pref.asked")
        legacy_partner_state = "sub_personalities" not in answers
        for key in (
            "personalities", "sub_personalities", "body_height",
            "body_build", "body_bust", "call",
        ):
            if key == "sub_personalities" and legacy_partner_state:
                continue
            value = (
                _partner_height_answer(
                    answers.get(key), legacy_plain_long=legacy_partner_state,
                )
                if key == "body_height" else _multi_list_answer(answers.get(key), key)
            )
            if partner.get(key) != value:
                partner[key] = value
                changed.append(f"partner_pref.{key}")
    return changed


def _cmd_apply_hearing_state_locked(args: argparse.Namespace) -> dict:
    source = Path(args.save).expanduser()
    output = Path(args.output).expanduser()
    if output.resolve() == source.resolve():
        raise RuntimeProblem("--output must be different from --save; commit the candidate with commit-save")
    save = load_yaml(source)
    if not isinstance(save, dict):
        raise RuntimeProblem("save root must be a mapping")
    errors, _ = validate_save_data(save)
    if errors:
        raise RuntimeProblem("candidate save is invalid: " + "; ".join(errors))
    try:
        raw = json.loads(Path(args.state).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProblem(f"invalid widget state JSON: {exc}") from exc
    state, wrapper_id = _widget_state(raw)
    step_id = str(state["step_id"])
    revision = int(state["revision"])
    progress = save.setdefault("hearing_progress", {})
    versions = progress.setdefault("widget_state_versions", {})
    widget_ids = progress.setdefault("widget_ids", {})
    prior_revision = versions.get(step_id)
    if prior_revision is not None and (not _is_integer(prior_revision) or prior_revision > revision):
        raise RuntimeProblem(f"stale widget revision for {step_id}: {revision} < {prior_revision}")
    completion_id = (
        "body_profile" if step_id.startswith("body_") else
        "partner" if step_id == "partner_preferences" else step_id
    )
    completed = progress.setdefault("completed_steps", [])
    prerequisites = {
        "playmode": [],
        "profile": ["playmode"],
        "body_female": ["playmode", "profile"],
        "body_male": ["playmode", "profile"],
        "desire": ["playmode", "profile", "body_profile"],
        "partner_preferences": ["playmode", "profile", "body_profile", "desire"],
    }[step_id]
    already_completed = completion_id in completed
    if already_completed:
        legacy_partner_adoption = (
            step_id == "partner_preferences" and prior_revision is None and
            isinstance(save.get("partner_pref"), dict) and
            save["partner_pref"].get("asked") is True
        )
        if prior_revision is None and not legacy_partner_adoption:
            raise RuntimeProblem(f"completed step {step_id} has no widget revision audit record")
    else:
        missing = [item for item in prerequisites if item not in completed]
        if missing:
            raise RuntimeProblem(f"cannot apply {step_id} before completed steps: {', '.join(missing)}")
        if progress.get("current_step") != state["step"]:
            raise RuntimeProblem(
                f"hearing step mismatch: save expects {progress.get('current_step')}, widget is {state['step']}"
            )
    before = copy.deepcopy(save)
    changed = _apply_widget_mapping(save, state)
    if not already_completed:
        completed.append(completion_id)
        changed.append("hearing_progress.completed_steps")
    next_step = {
        "playmode": 2, "profile": 3, "body_female": 4, "body_male": 4,
        "desire": 5, "partner_preferences": 6,
    }[step_id]
    if not already_completed and progress.get("current_step") != next_step:
        progress["current_step"] = next_step
        changed.append("hearing_progress.current_step")
    if not already_completed and progress.get("status") != "in_progress":
        progress["status"] = "in_progress"
        changed.append("hearing_progress.status")
    widget_id = args.widget_id or wrapper_id or step_id
    if widget_ids.get(step_id) != widget_id:
        widget_ids[step_id] = widget_id
        changed.append(f"hearing_progress.widget_ids.{step_id}")
    if prior_revision == revision and save != before:
        raise RuntimeProblem(f"widget revision {revision} conflicts with already-applied {step_id} state")
    if versions.get(step_id) != revision:
        versions[step_id] = revision
        changed.append(f"hearing_progress.widget_state_versions.{step_id}")
    idempotent = save == before
    final_errors, warnings = validate_save_data(save)
    if final_errors:
        raise RuntimeProblem("widget mapping produced invalid save: " + "; ".join(final_errors))
    serialized = dump_yaml(save)
    output_already_matches = output.is_file() and output.read_text(encoding="utf-8") == serialized
    if output.exists() and not output_already_matches and not args.force:
        raise RuntimeProblem(f"refusing to overwrite existing output: {output}")
    if not output_already_matches:
        atomic_write(output, serialized)
    idempotent = idempotent or output_already_matches
    return {"ok": True, "idempotent": idempotent, "output": str(output), "step_id": step_id,
            "revision": revision, "completed_step": completion_id, "next_step": next_step,
            "changed": changed, "warnings": warnings}


def cmd_apply_hearing_state(args: argparse.Namespace) -> dict:
    source = Path(args.save).expanduser()
    output = Path(args.output).expanduser()
    with file_locks([save_lock_path(source), save_lock_path(output)]):
        return _cmd_apply_hearing_state_locked(args)


def _cmd_migrate_save_locked(args: argparse.Namespace) -> dict:
    source = Path(args.path).expanduser()
    data = load_yaml(source)
    if not isinstance(data, dict):
        raise RuntimeProblem("save root must be a mapping")
    migrated, changes = migrate_data(data)
    errors, warnings = validate_save_data(migrated)
    if errors:
        raise RuntimeProblem("migrated save is invalid: " + "; ".join(errors))
    output = source if args.in_place else Path(args.output).expanduser() if args.output else source.with_suffix(".migrated.yaml")
    if args.in_place and source.exists():
        history = source.parent / "_history" / source.stem
        history.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, history / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".pre-migration.yaml"))
    atomic_write(output, dump_yaml(migrated))
    return {"ok": True, "output": str(output), "changes": changes, "warnings": warnings}


def cmd_migrate_save(args: argparse.Namespace) -> dict:
    source = Path(args.path).expanduser()
    output = source if args.in_place else Path(args.output).expanduser() if args.output else source.with_suffix(".migrated.yaml")
    with file_locks([save_lock_path(source), save_lock_path(output)]):
        return _cmd_migrate_save_locked(args)


def _cmd_commit_save_locked(args: argparse.Namespace) -> dict:
    current = Path(args.current).expanduser()
    candidate = Path(args.candidate).expanduser()
    if args.keep < 1:
        raise RuntimeProblem("--keep must be >= 1")
    old_bytes = current.read_bytes()
    old = load_yaml(current)
    new = load_yaml(candidate)
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise RuntimeProblem("both saves must be mappings")
    old_errors, _ = validate_save_data(old)
    new_errors, warnings = validate_save_data(new)
    if old_errors:
        raise RuntimeProblem("current save is invalid; migrate/repair before commit: " + "; ".join(old_errors))
    if new_errors:
        raise RuntimeProblem("candidate save is invalid: " + "; ".join(new_errors))
    old_id = old.get("campaign_id")
    new_id = new.get("campaign_id")
    if old_id != new_id:
        raise RuntimeProblem("candidate campaign_id does not match current save")
    candidate_hash = sha256_bytes(dump_yaml(new).encode("utf-8"))
    transaction_id = safe_id(args.transaction_id) if args.transaction_id else ("txn-" + candidate_hash[:24])
    old_transaction = old.get("transaction", {})
    applied_transaction_ids = old_transaction.get("applied_transaction_ids", [])
    if transaction_id in applied_transaction_ids:
        if old_transaction.get("last_transaction_id") == transaction_id:
            if old_transaction.get("last_candidate_hash") != candidate_hash:
                raise RuntimeProblem("transaction-id was reused with different candidate content")
            return {"ok": True, "idempotent": True, "current": str(current),
                    "save_revision": old.get("save_revision"), "transaction_id": transaction_id,
                    "candidate_hash": candidate_hash, "warnings": warnings}
        raise RuntimeProblem(f"transaction-id was already applied: {transaction_id}")
    from onboarding import validate_transition
    onboarding_errors = validate_transition(SimpleNamespace(**globals()), old, new, transaction_id)
    if onboarding_errors:
        raise RuntimeProblem("invalid onboarding transition: " + "; ".join(onboarding_errors))
    from allocation_widget import validate_transition as validate_allocation_transition
    allocation_errors = validate_allocation_transition(SimpleNamespace(**globals()), old, new, transaction_id)
    if allocation_errors:
        raise RuntimeProblem("invalid allocation transition: " + "; ".join(allocation_errors))
    from appearance_customization import validate_transition as validate_appearance_transition
    appearance_errors = validate_appearance_transition(SimpleNamespace(**globals()), old, new, transaction_id)
    if appearance_errors:
        raise RuntimeProblem("invalid appearance transition: " + "; ".join(appearance_errors))
    reward_transition_errors = _validate_reward_transition(old, new, transaction_id)
    if reward_transition_errors:
        raise RuntimeProblem("invalid reward settlement transition: " + "; ".join(
            reward_transition_errors
        ))
    debt_transition_errors = _validate_debt_transition(old, new, transaction_id)
    if debt_transition_errors:
        raise RuntimeProblem("invalid debt transition: " + "; ".join(debt_transition_errors))
    quest_transition_errors = _validate_quest_transition(old, new, transaction_id)
    if quest_transition_errors:
        raise RuntimeProblem("invalid quest transition: " + "; ".join(quest_transition_errors))
    inventory_enterprise_errors = _validate_inventory_enterprise_transition(old, new)
    if inventory_enterprise_errors:
        raise RuntimeProblem(
            "invalid inventory/enterprise transition: " + "; ".join(inventory_enterprise_errors)
        )
    growth_transition_errors = _validate_growth_transition(old, new, transaction_id)
    if growth_transition_errors:
        raise RuntimeProblem("invalid growth transition: " + "; ".join(
            growth_transition_errors
        ))
    adventure_transition_errors = _validate_adventure_transition(old, new)
    if adventure_transition_errors:
        raise RuntimeProblem("invalid adventure transition: " + "; ".join(
            adventure_transition_errors
        ))
    old_run = old.get("world_state", {}).get("dungeon_run", {})
    new_run = new.get("world_state", {}).get("dungeon_run", {})
    if (isinstance(old_run, dict) and isinstance(new_run, dict)
            and old_run.get("active") is True and new_run.get("active") is True
            and old_run.get("run_id") == new_run.get("run_id")):
        old_event_ids = old_run.get("used_event_ids")
        new_event_ids = new_run.get("used_event_ids")
        if (isinstance(old_event_ids, list) and isinstance(new_event_ids, list)
                and new_event_ids[:len(old_event_ids)] == old_event_ids):
            appended_event_ids = new_event_ids[len(old_event_ids):]
            authorized_event_ids = getattr(args, "dungeon_event_ids", None)
            if appended_event_ids and authorized_event_ids is None:
                raise RuntimeProblem(
                    "dungeon used_event_ids must be committed with commit-turn inventory operations"
                )
            if authorized_event_ids is not None and appended_event_ids != authorized_event_ids:
                raise RuntimeProblem(
                    "authorized dungeon inventory events do not match candidate used_event_ids"
                )
    old_revision = int(old.get("save_revision", 0))
    if new.get("save_revision") != old_revision:
        raise RuntimeProblem(
            f"stale candidate: save_revision must equal current revision {old_revision} before commit"
        )
    if new.get("created_at") != old.get("created_at"):
        raise RuntimeProblem("candidate must not change created_at")
    new = ensure_runtime_metadata(new, str(old_id))
    new["created_at"] = old["created_at"]
    new["save_revision"] = old_revision + 1
    old_turn = int(old.get("transaction", {}).get("last_committed_turn", 0))
    committed_turn = args.turn if args.turn is not None else old_turn + 1
    if committed_turn < 0 or committed_turn < old_turn:
        raise RuntimeProblem("--turn must be non-negative and cannot move backwards")
    new["transaction"] = {
        "last_transaction_id": transaction_id,
        "last_committed_turn": committed_turn,
        "previous_revision_hash": sha256_bytes(old_bytes),
        "last_candidate_hash": candidate_hash,
        "applied_transaction_ids": [*applied_transaction_ids, transaction_id],
    }
    state = new.setdefault("runtime_state", {})
    state["last_validation_at"] = now_iso()
    state["last_error"] = ""
    current_manifest = manifest_digest()
    if current_manifest:
        new["content_manifest_hash"] = current_manifest
    final_errors, warnings = validate_save_data(new)
    if final_errors:
        raise RuntimeProblem("candidate became invalid during commit: " + "; ".join(final_errors))
    history = current.parent / "_history" / current.stem
    history.mkdir(parents=True, exist_ok=True)
    backup = history / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
        f"-rev{old_revision}-{sha256_bytes(old_bytes)[:8]}.yaml")
    shutil.copy2(current, backup)
    atomic_write(current, dump_yaml(new))
    # Keep bounded history without touching any other campaign.
    backups = sorted(history.glob("*.yaml"))
    for stale in backups[:-max(1, args.keep)]:
        stale.unlink()
    return {"ok": True, "idempotent": False, "current": str(current), "backup": str(backup),
            "save_revision": new["save_revision"], "committed_turn": committed_turn,
            "transaction_id": transaction_id, "candidate_hash": candidate_hash,
            "warnings": warnings}


def cmd_commit_save(args: argparse.Namespace) -> dict:
    current = Path(args.current).expanduser()
    candidate = Path(args.candidate).expanduser()
    with file_locks([save_lock_path(current), save_lock_path(candidate)]):
        return _cmd_commit_save_locked(args)


def _preflight_inventory_use(state: dict, args: argparse.Namespace) -> bool:
    """Validate a use operation without mutation; return whether already applied."""
    campaign_id = safe_id(args.campaign_id)
    transaction_id = safe_id(args.transaction_id)
    entry_id = safe_id(str(args.id))
    if args.turn < 0:
        raise RuntimeProblem("--turn must be an integer >= 0")
    intended = {"kind": args.kind, "id": entry_id, "campaign_id": campaign_id, "turn": args.turn}
    receipts = state.get("use_receipts", {})
    if not isinstance(receipts, dict):
        raise RuntimeProblem(f"invalid {args.kind}.use_receipts")
    if transaction_id in receipts:
        prior = receipts[transaction_id]
        if not isinstance(prior, dict) or any(prior.get(key) != value for key, value in intended.items()):
            raise RuntimeProblem("transaction-id was already used for a different inventory operation")
        return True
    matches = [entry for entry in state["entries"]
               if isinstance(entry, dict) and str(entry.get("id")) == entry_id]
    if len(matches) != 1:
        raise RuntimeProblem(f"inventory id must resolve exactly once: {args.kind}/{entry_id}")
    if matches[0].get("campaign_id") not in (None, campaign_id):
        raise RuntimeProblem("inventory entry belongs to another campaign")
    if matches[0].get("status", "unused") != "unused":
        raise RuntimeProblem(f"inventory entry is already used: {args.kind}/{entry_id}")
    return False


def _turn_inventory_operations(args: argparse.Namespace, transaction_id: str) -> list[dict]:
    raw = list(getattr(args, "inventory_use", None) or [])
    legacy_kind = getattr(args, "inventory_kind", None)
    legacy_id = getattr(args, "inventory_id", None)
    if bool(legacy_kind) != bool(legacy_id):
        raise RuntimeProblem("--inventory-kind and --inventory-id must be supplied together")
    if legacy_kind:
        raw.append(f"{legacy_kind}:{legacy_id}")
    if not raw:
        raise RuntimeProblem("commit-turn requires at least one --inventory-use KIND:ID")
    if len(raw) > 16:
        raise RuntimeProblem("commit-turn accepts at most 16 inventory operations")
    operations: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for position, token in enumerate(raw, 1):
        if ":" not in token:
            raise RuntimeProblem(f"invalid --inventory-use {token!r}; expected mobs:ID or events:ID")
        kind, entry_id = token.split(":", 1)
        if kind not in {"mobs", "events"}:
            raise RuntimeProblem(f"invalid inventory kind {kind!r}")
        entry_id = safe_id(entry_id)
        key = (kind, entry_id)
        if key in seen:
            raise RuntimeProblem(f"duplicate inventory operation: {kind}:{entry_id}")
        seen.add(key)
        receipt_seed = f"{transaction_id}\0{position}\0{kind}\0{entry_id}"
        receipt_id = "turnop-" + sha256_bytes(receipt_seed.encode("utf-8"))[:32]
        operations.append({"kind": kind, "id": entry_id, "receipt_id": receipt_id})
    return operations


def _inventory_entry_category(state: dict, entry_id: str) -> str | None:
    matches = [
        entry for entry in state.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("id")) == entry_id
    ]
    if len(matches) != 1:
        return None
    category = matches[0].get("category")
    return category if isinstance(category, str) else None


def _validate_dungeon_event_operations(
    old: dict, new: dict, operations: list[dict], states: dict[str, dict],
) -> None:
    old_world = old.get("world_state") if isinstance(old.get("world_state"), dict) else {}
    new_world = new.get("world_state") if isinstance(new.get("world_state"), dict) else {}
    old_run = old_world.get("dungeon_run") if isinstance(old_world.get("dungeon_run"), dict) else {}
    new_run = new_world.get("dungeon_run") if isinstance(new_world.get("dungeon_run"), dict) else {}
    event_operations = [item for item in operations if item.get("kind") == "events"]
    categorized: list[tuple[str, str | None]] = []
    if event_operations:
        event_state = states.get("events")
        if not isinstance(event_state, dict):
            raise RuntimeProblem("events inventory state is unavailable")
        categorized = [
            (item["id"], _inventory_entry_category(event_state, item["id"]))
            for item in event_operations
        ]
        from event_connections import companion_ids, unmet
        for operation in event_operations:
            entry = next((item for item in event_state.get("entries", [])
                          if item.get("id") == operation["id"]), None)
            if entry is None:
                continue  # The existing stock preflight reports a missing ID.
            # Dungeon actions happen in the old active floor. Arrival events
            # in town may belong to the destination recorded by this turn.
            event_world = old_world if entry.get("category") == "dungeon" else new_world
            event_run = event_world.get("dungeon_run") or {}
            missing = unmet(entry, {"location": event_world.get("location"),
                                   "current_floor": event_run.get("current_floor") or event_world.get("depth"),
                                   "companion_ids": companion_ids(old)})
            if missing:
                raise RuntimeProblem("event conditions not met at consumption: " + ", ".join(missing))
    old_active = old_run.get("active") is True
    new_active = new_run.get("active") is True
    same_run = old_active and new_active and old_run.get("run_id") == new_run.get("run_id")
    if old_active or new_active:
        non_dungeon = [entry_id for entry_id, category in categorized if category != "dungeon"]
        if non_dungeon:
            raise RuntimeProblem(
                "active dungeon turns may only consume dungeon-category events: "
                + ", ".join(non_dungeon)
            )
    dungeon_operation_ids = [
        entry_id for entry_id, category in categorized if category == "dungeon"
    ]
    if dungeon_operation_ids and not same_run:
        raise RuntimeProblem(
            "dungeon events must be consumed while preserving the same active dungeon_run"
        )
    old_ids = old_run.get("used_event_ids")
    new_ids = new_run.get("used_event_ids")
    appended_ids = (
        new_ids[len(old_ids):]
        if isinstance(old_ids, list) and isinstance(new_ids, list)
        and new_ids[:len(old_ids)] == old_ids else None
    )
    if same_run and appended_ids != dungeon_operation_ids:
        raise RuntimeProblem(
            "dungeon inventory operations must exactly match appended dungeon_run.used_event_ids"
        )


def cmd_commit_turn(args: argparse.Namespace) -> dict:
    """Commit a save and one or more inventory uses as one retryable transaction."""
    current = Path(args.current).expanduser().resolve()
    candidate = Path(args.candidate).expanduser().resolve()
    if current == candidate:
        raise RuntimeProblem("current and candidate must be distinct files")
    transaction_id = safe_id(args.transaction_id)
    operations = _turn_inventory_operations(args, transaction_id)
    kinds = sorted({item["kind"] for item in operations})
    resource_ids = {"MOB_INVENTORY_STATE" if kind == "mobs" else "EVENT_INVENTORY_STATE"
                    for kind in kinds}
    initialize_inventories(resource_ids)
    inventory_paths = {"mobs": MOBS_PATH, "events": EVENTS_PATH}
    lock_paths = [save_lock_path(current), save_lock_path(candidate),
                  *(inventory_lock_path(kind) for kind in kinds)]
    with file_locks(lock_paths):
        current_data = load_yaml(current)
        if not isinstance(current_data, dict):
            raise RuntimeProblem("current save root must be a mapping")
        campaign_id = safe_id(str(current_data.get("campaign_id") or ""))
        prior_tx = current_data.get("transaction", {}).get("last_transaction_id")
        if prior_tx == transaction_id:
            committed_turn = int(current_data.get("transaction", {}).get("last_committed_turn", 0))
        else:
            previous_turn = int(current_data.get("transaction", {}).get("last_committed_turn", 0))
            committed_turn = args.turn if args.turn is not None else previous_turn + 1
        commit_args = argparse.Namespace(
            current=str(current), candidate=str(candidate), keep=args.keep,
            transaction_id=transaction_id, turn=committed_turn,
        )
        use_args: list[argparse.Namespace] = []
        states = {kind: load_inventory(inventory_paths[kind], kind) for kind in kinds}
        for operation in operations:
            operation_args = argparse.Namespace(
                kind=operation["kind"], id=operation["id"], campaign_id=campaign_id,
                turn=committed_turn, transaction_id=operation["receipt_id"], keep=args.keep,
            )
            _preflight_inventory_use(states[operation["kind"]], operation_args)
            use_args.append(operation_args)
        old_save_bytes = current.read_bytes()
        old_inventory_bytes = {kind: inventory_paths[kind].read_bytes() for kind in kinds}
        journal_path = current.parent / "_transactions" / f"{transaction_id}.json"
        prior_journal = None
        if journal_path.is_file():
            try:
                prior_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeProblem(f"transaction journal is corrupt: {journal_path}") from exc
        candidate_data = load_yaml(candidate)
        if not isinstance(candidate_data, dict):
            raise RuntimeProblem("candidate save root must be a mapping")
        if prior_tx != transaction_id:
            _validate_dungeon_event_operations(
                current_data, candidate_data, operations, states,
            )
        event_state = states.get("events")
        commit_args.dungeon_event_ids = [
            operation["id"] for operation in operations
            if operation.get("kind") == "events"
            and isinstance(event_state, dict)
            and _inventory_entry_category(event_state, operation["id"]) == "dungeon"
        ]
        candidate_hash = sha256_bytes(dump_yaml(candidate_data).encode("utf-8"))
        journal_operations = [dict(item) for item in operations]
        journal = {
            "schema": "machadan-turn-transaction-v1", "transaction_id": transaction_id,
            "state": "pending", "campaign_id": campaign_id, "turn": committed_turn,
            "current_path": str(current), "candidate_path": str(candidate), "keep": args.keep,
            "candidate_hash": candidate_hash, "inventory_operations": journal_operations,
            "created_at": (prior_journal or {}).get("created_at", now_iso()),
            "updated_at": now_iso(),
        }
        if prior_journal:
            identity_keys = ("campaign_id", "turn", "current_path", "candidate_path",
                             "keep", "candidate_hash", "inventory_operations")
            if any(prior_journal.get(key) != journal[key] for key in identity_keys):
                raise RuntimeProblem("transaction journal identity does not match retry")
        atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
        try:
            save_result = _cmd_commit_save_locked(commit_args)
            inventory_results = [_cmd_inventory_use_locked(operation_args)
                                 for operation_args in use_args]
        except Exception as exc:
            atomic_write(current, old_save_bytes.decode("utf-8"))
            for kind in kinds:
                atomic_write(inventory_paths[kind], old_inventory_bytes[kind].decode("utf-8"))
            prior_state = (prior_journal or {}).get("state")
            journal["state"] = prior_state if prior_state in {"pending", "committed"} else "rolled_back"
            journal["last_error"] = str(exc)
            journal["updated_at"] = now_iso()
            atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
            raise
        journal["state"] = "committed"
        journal.pop("last_error", None)
        journal["updated_at"] = now_iso()
        journal["save_revision"] = save_result["save_revision"]
        atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
        return {
            "ok": True,
            "idempotent": bool(save_result.get("idempotent") and
                               all(item.get("idempotent") for item in inventory_results)),
            "transaction_id": transaction_id, "turn": committed_turn,
            "save": save_result, "inventory": inventory_results, "journal": str(journal_path),
        }


def cmd_inventory_init(args: argparse.Namespace) -> dict:
    result = initialize_inventories(force=False)
    return {"ok": True, **result}


def cmd_inventory_sync_seed(args: argparse.Namespace) -> dict:
    return {"ok": True, "changed": [], "inventories": [],
            "status": "retired", "contract": "machadan-refill-cli-v2",
            "notice": "見本在庫の同期は廃止しました。更新は空に再作成し、確定セーブから補充します"}


def _inventory_backup(path: Path, kind: str, label: str, keep: int = 50) -> Path:
    history = path.parent / "_history" / kind
    history.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(path.read_bytes())[:8]
    backup = history / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{label}-{digest}.yaml"
    )
    shutil.copy2(path, backup)
    backups = sorted(history.glob("*.yaml"))
    for stale in backups[:-max(1, keep)]:
        stale.unlink()
    return backup


def _cmd_inventory_use_locked(args: argparse.Namespace) -> dict:
    args.id = safe_id(str(args.id))
    if args.turn < 0:
        raise RuntimeProblem("--turn must be an integer >= 0")
    if args.keep < 1:
        raise RuntimeProblem("--keep must be >= 1")
    campaign_id = safe_id(args.campaign_id)
    transaction_id = safe_id(args.transaction_id)
    path = MOBS_PATH if args.kind == "mobs" else EVENTS_PATH
    state = load_inventory(path, args.kind)
    _preflight_inventory_use(state, args)
    receipts = state.setdefault("use_receipts", {})
    if not isinstance(receipts, dict):
        raise RuntimeProblem(f"invalid {args.kind}.use_receipts")
    intended = {"kind": args.kind, "id": args.id, "campaign_id": campaign_id, "turn": args.turn}
    if transaction_id in receipts:
        prior = receipts[transaction_id]
        if not isinstance(prior, dict) or any(prior.get(key) != value for key, value in intended.items()):
            raise RuntimeProblem("transaction-id was already used for a different inventory operation")
        return {"ok": True, "idempotent": True, "transaction_id": transaction_id,
                "kind": args.kind, "id": args.id, "status": "used"}
    matches = [entry for entry in state["entries"]
               if isinstance(entry, dict) and str(entry.get("id")) == args.id]
    if len(matches) != 1:
        raise RuntimeProblem(f"inventory id must resolve exactly once: {args.kind}/{args.id}")
    entry = matches[0]
    if entry.get("status", "unused") != "unused":
        raise RuntimeProblem(f"inventory entry is already used: {args.kind}/{args.id}")
    used_at = now_iso()
    entry.update({"status": "used", "used_by": campaign_id, "used_turn": args.turn,
                  "used_at": used_at, "use_transaction_id": transaction_id})
    if isinstance(entry.get("fields"), dict):
        entry["fields"]["状態"] = f"使用済み ({campaign_id}, turn {args.turn})"
    receipts[transaction_id] = {**intended, "used_at": used_at}
    state["updated_at"] = used_at
    errors, warnings = validate_inventory_state(state, args.kind)
    if errors:
        raise RuntimeProblem("inventory validation failed before use commit: " + "; ".join(errors))
    backup = _inventory_backup(path, args.kind, f"use-{args.id}", args.keep)
    atomic_write(path, dump_yaml(state))
    return {"ok": True, "idempotent": False, "transaction_id": transaction_id,
            "kind": args.kind, "id": args.id, "status": "used", "backup": str(backup),
            "summary": inventory_summary(state), "warnings": warnings}


def cmd_inventory_use(args: argparse.Namespace) -> dict:
    resource_id = "MOB_INVENTORY_STATE" if args.kind == "mobs" else "EVENT_INVENTORY_STATE"
    initialize_inventories({resource_id})
    with file_locks([inventory_lock_path(args.kind)]):
        return _cmd_inventory_use_locked(args)


def cmd_inventory_status(args: argparse.Namespace) -> dict:
    from inventory_lifecycle import status
    return status(SimpleNamespace(**globals()), args)


def cmd_inventory_template(args: argparse.Namespace) -> dict:
    from inventory_lifecycle import template
    return template(SimpleNamespace(**globals()), args)


def _inventory_append_hash(value: Any) -> str:
    """Return a stable hash for an append payload or normalized inventory state."""
    if isinstance(value, dict) and value.get("schema") == "machadan-inventory-append-v1":
        serialized = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
    else:
        serialized = dump_yaml(value)
    return sha256_bytes(serialized.encode("utf-8"))


def _inventory_append_journal_path(run_id: str) -> Path:
    if MOBS_PATH.parent.resolve() != EVENTS_PATH.parent.resolve():
        raise RuntimeProblem("inventory files must share one state directory")
    return MOBS_PATH.parent / "_transactions" / f"{run_id}.json"


def _load_inventory_append_journal(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProblem(f"inventory append journal is corrupt: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeProblem(f"inventory append journal is not an object: {path}")
    return value


def _cmd_inventory_append_locked(args: argparse.Namespace) -> dict:
    if not 1 <= args.max <= 8:
        raise RuntimeProblem("--max must be in 1..8")
    payload_path = Path(args.input).expanduser()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeProblem("inventory input must be a JSON object")
    if payload.get("schema") != "machadan-inventory-append-v1":
        raise RuntimeProblem("inventory input schema must be machadan-inventory-append-v1; run inventory-template")
    allowed_payload_keys = {"schema", "run_id", "capacity_snapshot", "rules", "mobs", "events", "context"}
    unknown_payload_keys = sorted(set(payload) - allowed_payload_keys)
    if unknown_payload_keys:
        raise RuntimeProblem("unknown inventory payload keys: " + ", ".join(unknown_payload_keys))
    for key in ("mobs", "events"):
        if key not in payload:
            raise RuntimeProblem(f"inventory input missing {key}")
    for key in ("capacity_snapshot", "rules"):
        if key in payload and not isinstance(payload[key], dict):
            raise RuntimeProblem(f"inventory input {key} must be an object")
    run_id = safe_id(str(payload.get("run_id") or ""))
    if run_id == "refill-REPLACE-ME":
        raise RuntimeProblem("replace the inventory template run_id with a stable unique id")
    additions = {"mobs": payload.get("mobs", []), "events": payload.get("events", [])}
    total = sum(len(value) for value in additions.values() if isinstance(value, list))
    if total < 1 or total > args.max:
        raise RuntimeProblem(f"inventory append must contain 1..{args.max} total entries")
    states = {"mobs": load_inventory(MOBS_PATH, "mobs"),
              "events": load_inventory(EVENTS_PATH, "events")}
    seen_run = {kind: run_id in state.get("applied_runs", [])
                for kind, state in states.items()}
    payload_hash = _inventory_append_hash(payload)
    journal_path = _inventory_append_journal_path(run_id)
    prior_journal = _load_inventory_append_journal(journal_path)
    if prior_journal:
        if prior_journal.get("schema") != "machadan-inventory-append-transaction-v1":
            raise RuntimeProblem("unsupported inventory append journal schema")
        identity = {
            "run_id": run_id,
            "payload_hash": payload_hash,
            "max_entries": args.max,
        }
        if any(prior_journal.get(key) != value for key, value in identity.items()):
            raise RuntimeProblem("inventory append journal identity does not match retry")
        if prior_journal.get("state") not in {"pending", "rolled_back", "committed"}:
            raise RuntimeProblem("inventory append journal has an invalid state")
    if all(seen_run.values()):
        # A pre-journal runtime may already have recorded the run in both files.
        if prior_journal is None:
            return {"ok": True, "idempotent": True, "run_id": run_id, "added": 0,
                    "legacy_receipt": True}
        if prior_journal["state"] == "committed":
            return {"ok": True, "idempotent": True, "run_id": run_id, "added": 0,
                    "journal": str(journal_path)}
        if prior_journal["state"] != "pending":
            raise RuntimeProblem("inventory states conflict with a rolled-back append journal")
        target_hashes = prior_journal.get("target_hashes")
        if not isinstance(target_hashes, dict) or any(
            target_hashes.get(kind) != _inventory_append_hash(states[kind])
            for kind in ("mobs", "events")
        ):
            raise RuntimeProblem(
                "pending inventory append reached both files but their content no longer matches; "
                "inspect before retry"
            )
        recovered = copy.deepcopy(prior_journal)
        recovered["state"] = "committed"
        recovered["updated_at"] = now_iso()
        recovered["recovered_after_interruption"] = True
        recovered.pop("last_error", None)
        atomic_write(journal_path, json.dumps(recovered, ensure_ascii=False, indent=2) + "\n")
        return {"ok": True, "idempotent": True, "recovered": True,
                "run_id": run_id, "added": 0, "journal": str(journal_path)}
    if any(seen_run.values()):
        if prior_journal is None or prior_journal.get("state") != "pending":
            raise RuntimeProblem(
                "inventory states disagree about run_id without a matching pending journal; "
                "inspect before retry"
            )
    elif prior_journal and prior_journal.get("state") == "committed":
        raise RuntimeProblem("committed inventory append receipt is missing from inventory state")

    from inventory_lifecycle import append_guard
    append_guard(SimpleNamespace(**globals()), payload, states)

    operation_time = (
        str(prior_journal.get("operation_time"))
        if prior_journal and prior_journal.get("operation_time")
        else now_iso()
    )
    target_states = copy.deepcopy(states)
    for kind, entries in additions.items():
        if not isinstance(entries, list):
            raise RuntimeProblem(f"{kind} must be a list")
        state = target_states[kind]
        existing_ids = ({str(item.get("id")) for item in state["entries"]
                         if isinstance(item, dict)} if not seen_run[kind] else set())
        existing_names = ({str(item.get("name")).casefold() for item in state["entries"]
                           if isinstance(item, dict) and item.get("name")}
                          if not seen_run[kind] else set())
        payload_ids: set[str] = set()
        payload_names: set[str] = set()
        pending_counts: dict[str, int] = {}
        for entry in entries:
            validate_inventory_entry(entry, kind, state["limits"])
            entry_id = str(entry["id"])
            if entry_id in payload_ids:
                raise RuntimeProblem(f"duplicate inventory id in payload: {entry_id}")
            payload_ids.add(entry_id)
            if entry_id in existing_ids:
                raise RuntimeProblem(f"duplicate inventory id: {entry['id']}")
            existing_ids.add(entry_id)
            if kind == "mobs":
                folded = str(entry["name"]).casefold()
                if folded in payload_names:
                    raise RuntimeProblem(f"duplicate mob name in payload: {entry['name']}")
                payload_names.add(folded)
                if folded in existing_names:
                    raise RuntimeProblem(f"duplicate mob name: {entry['name']}")
                existing_names.add(folded)
            category = str(entry["category"])
            pending_counts[category] = pending_counts.get(category, 0) + 1
        if seen_run[kind]:
            continue
        summary = inventory_summary(state)
        for category, count in pending_counts.items():
            if count > summary[category]["open"]:
                raise RuntimeProblem(f"{kind}/{category} exceeds open capacity")
        state["entries"].extend(copy.deepcopy(entries))
        state["applied_runs"].append(run_id)
        state["updated_at"] = operation_time
        validation_errors, _ = validate_inventory_state(state, kind)
        if validation_errors:
            raise RuntimeProblem(f"{kind} inventory validation failed: " + "; ".join(validation_errors))

    before_hashes = {kind: _inventory_append_hash(states[kind])
                     for kind in ("mobs", "events")}
    target_hashes = {kind: _inventory_append_hash(target_states[kind])
                     for kind in ("mobs", "events")}
    if prior_journal:
        expected_before = prior_journal.get("before_hashes")
        expected_targets = prior_journal.get("target_hashes")
        if not isinstance(expected_before, dict) or not isinstance(expected_targets, dict):
            raise RuntimeProblem("inventory append journal is missing state hashes")
        for kind in ("mobs", "events"):
            expected = expected_targets.get(kind) if seen_run[kind] else expected_before.get(kind)
            actual = before_hashes[kind]
            if actual != expected:
                raise RuntimeProblem(
                    f"{kind} inventory changed after the pending append; inspect before retry"
                )
            if target_hashes[kind] != expected_targets.get(kind):
                raise RuntimeProblem("inventory append retry would produce different target content")

    journal = {
        "schema": "machadan-inventory-append-transaction-v1",
        "run_id": run_id,
        "state": "pending",
        "payload_hash": payload_hash,
        "max_entries": args.max,
        "input_path": str(payload_path.resolve()),
        "entry_ids": {kind: [str(item["id"]) for item in additions[kind]]
                      for kind in ("mobs", "events")},
        "total_entries": total,
        "before_hashes": ((prior_journal or {}).get("before_hashes") or before_hashes),
        "target_hashes": ((prior_journal or {}).get("target_hashes") or target_hashes),
        "operation_time": operation_time,
        "created_at": (prior_journal or {}).get("created_at", now_iso()),
        "updated_at": now_iso(),
        "attempts": int((prior_journal or {}).get("attempts", 0)) + 1,
    }
    atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
    MOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    paths = {"mobs": MOBS_PATH, "events": EVENTS_PATH}
    write_kinds = [kind for kind in ("mobs", "events") if not seen_run[kind]]
    backups = {kind: _inventory_backup(paths[kind], kind, f"append-{run_id}")
               for kind in write_kinds}
    old_bytes = {kind: paths[kind].read_bytes() for kind in write_kinds}
    try:
        for kind in write_kinds:
            atomic_write(paths[kind], dump_yaml(target_states[kind]))
    except Exception as exc:
        for kind, content in old_bytes.items():
            atomic_write(paths[kind], content.decode("utf-8"))
        journal["state"] = "pending" if any(seen_run.values()) else "rolled_back"
        journal["last_error"] = str(exc)
        journal["updated_at"] = now_iso()
        atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
        raise
    journal["state"] = "committed"
    journal["updated_at"] = now_iso()
    journal.pop("last_error", None)
    atomic_write(journal_path, json.dumps(journal, ensure_ascii=False, indent=2) + "\n")
    return {"ok": True, "idempotent": False, "run_id": run_id, "added": total,
            "backups": {key: str(value) for key, value in backups.items()},
            "journal": str(journal_path), "recovered": any(seen_run.values())}


def cmd_inventory_append(args: argparse.Namespace) -> dict:
    initialize_inventories()
    with file_locks([inventory_lock_path("events"), inventory_lock_path("mobs")]):
        return _cmd_inventory_append_locked(args)


def cmd_read_save(args: argparse.Namespace) -> dict:
    from save_changes import read_pointer
    path = Path(args.save).expanduser()
    with file_locks([save_lock_path(path)]):
        data = load_yaml(path)
        errors, _ = validate_save_data(data)
        if errors:
            raise RuntimeProblem("save validation failed: " + "; ".join(errors))
        return {"ok": True, "save_revision": data["save_revision"],
                "save_sha256": sha256_bytes(path.read_bytes()),
                "pointer": args.pointer, "value": read_pointer(data, args.pointer)}


def cmd_apply_changes(args: argparse.Namespace) -> dict:
    from save_changes import apply_operations
    current = Path(args.current).expanduser()
    prepared = Path(args.prepared).expanduser()
    output = Path(args.output).expanduser()
    if len({current.resolve(), prepared.resolve(), output.resolve()}) != 3:
        raise RuntimeProblem("current, prepared and output must be different paths")
    with file_locks([save_lock_path(current), save_lock_path(prepared), save_lock_path(output)]):
        old = load_yaml(current)
        base = load_yaml(prepared)
        payload = json.loads(Path(args.changes).expanduser().read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != "machadan-save-changes-v1":
            raise RuntimeProblem("changes schema must be machadan-save-changes-v1")
        for data in (old, base):
            errors, _ = validate_save_data(data)
            if errors:
                raise RuntimeProblem("source save validation failed: " + "; ".join(errors))
        if payload.get("save_revision") != old["save_revision"] or payload.get("save_sha256") != sha256_bytes(current.read_bytes()):
            raise RuntimeProblem("元のセーブが更新されています。現行セーブから変更を組み直してください")
        expected = copy.deepcopy(old)
        for key in ("active_scene", "scene_id", "context_pack_hash", "ero_scene", "style_conditions"):
            if key in base["runtime_state"]:
                expected["runtime_state"][key] = base["runtime_state"][key]
        if expected != base or not base["runtime_state"].get("context_pack_hash"):
            raise RuntimeProblem("prepared must be an unedited prepare-context candidate for the current save")
        candidate = apply_operations(base, payload.get("operations"))
        # Point allocation starts a typed M30 record. Ordinary equipment,
        # STR/SPD growth and temporary changes must refresh that derived value
        # before validation rather than leave the widget's weight snapshot stale.
        from encumbrance import recalculate as recalculate_weight, EncumbranceError
        previous_actors = {actor.get("character_id") for actor in
                           [old.get("player"), *old.get("party", []), *old.get("inn_reserve", [])]
                           if isinstance(actor, dict)}
        previous_stat_lp = {actor.get("character_id") for actor in
                            [old.get("player"), *old.get("party", []), *old.get("inn_reserve", [])]
                            if isinstance(actor, dict) and "stat_lp_bonus" in actor}
        for actor in [candidate.get("player"), *candidate.get("party", []), *candidate.get("inn_reserve", [])]:
            if not isinstance(actor, dict):
                continue
            tracked = "encumbrance" in actor
            if tracked or actor.get("character_id") not in previous_actors:
                try:
                    recalculate_weight(candidate, actor.get("character_id"), require_weights=tracked)
                except (EncumbranceError, TypeError) as exc:
                    raise RuntimeProblem("cannot recalculate equipped weight: " + str(exc)) from exc
            from resource_math import recalculate as recalculate_resources
            if ("stat_lp_bonus" in actor or actor.get("character_id") in previous_stat_lp
                    or actor.get("character_id") not in previous_actors):
                try:
                    recalculate_resources(actor, track=True)
                except (ValueError, TypeError) as exc:
                    raise RuntimeProblem("cannot recalculate LP/MP: " + str(exc)) from exc
        errors, warnings = validate_save_data(candidate)
        if errors and not getattr(args, "draft", False):
            raise RuntimeProblem("changes produce an invalid candidate: " + "; ".join(errors))
        text = dump_yaml(candidate)
        same = output.is_file() and output.read_text(encoding="utf-8") == text
        if output.exists() and not same:
            raise RuntimeProblem("refusing to overwrite a different candidate: " + str(output))
        if not same:
            atomic_write(output, text)
        return {"ok": True, "idempotent": same, "output": str(output),
                "save_revision": candidate["save_revision"], "operations": len(payload["operations"]),
                "context_pack_hash": candidate["runtime_state"]["context_pack_hash"],
                "warnings": warnings, "draft": bool(getattr(args, "draft", False)),
                "validation_errors": errors,
                "notice": "候補を作成しました。まだ現行セーブには確定していません。draftは計算補助用で、確定には再検証が必要です"}


def cmd_begin_turn(args: argparse.Namespace) -> dict:
    from turn_flow import begin
    return begin(SimpleNamespace(**globals()), args)


def cmd_finish_turn(args: argparse.Namespace) -> dict:
    from turn_flow import finish
    return finish(SimpleNamespace(**globals()), args)


def cmd_inventory_reset(args: argparse.Namespace) -> dict:
    from inventory_lifecycle import reset
    return reset(SimpleNamespace(**globals()), args)


def cmd_onboarding_status(args: argparse.Namespace) -> dict:
    from onboarding import status
    result = status(SimpleNamespace(**globals()), args)
    return result if result.get("ok") else (1, result)


def cmd_grant_fire(args: argparse.Namespace) -> dict:
    from onboarding import grant
    return grant(SimpleNamespace(**globals()), args)


def cmd_allocation_widget(args: argparse.Namespace) -> dict:
    from allocation_widget import render
    return render(SimpleNamespace(**globals()), args)


def cmd_allocation_resolve(args: argparse.Namespace) -> dict:
    from allocation_widget import resolve
    return resolve(SimpleNamespace(**globals()), args)


def cmd_appearance_preview(args: argparse.Namespace) -> dict:
    from appearance_customization import preview
    return preview(SimpleNamespace(**globals()), args)


def cmd_apply_appearance(args: argparse.Namespace) -> dict:
    from appearance_customization import resolve
    return resolve(SimpleNamespace(**globals()), args)


def cmd_resolve_debt_payment(args: argparse.Namespace) -> dict:
    from debt_contracts import resolve_payment
    return resolve_payment(SimpleNamespace(**globals()), args)


def cmd_world_calendar(args: argparse.Namespace) -> dict:
    from regional_world import calendar
    return calendar(SimpleNamespace(**globals()), args)


def cmd_travel_plan(args: argparse.Namespace) -> dict:
    from regional_world import travel
    return travel(SimpleNamespace(**globals()), args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new-save")
    new.add_argument("--output", required=True)
    new.add_argument("--campaign-id")
    new.add_argument("--force", action="store_true")
    new.set_defaults(handler=cmd_new_save)
    world_calendar = sub.add_parser("world-calendar", help="show the calendar derived from Day without changing a save")
    date_source = world_calendar.add_mutually_exclusive_group(required=True)
    date_source.add_argument("--save")
    date_source.add_argument("--day", type=int)
    world_calendar.set_defaults(handler=cmd_world_calendar)
    journey = sub.add_parser("travel-plan", help="estimate an existing journey without moving actors or advancing time")
    journey.add_argument("--from", dest="from_place", required=True)
    journey.add_argument("--to", dest="to_place", required=True)
    journey.add_argument("--mode", choices=("foot", "cart"), default="foot")
    journey.add_argument("--save", help="optional current save for due-collection warnings")
    journey.set_defaults(handler=cmd_travel_plan)
    appearance_preview = sub.add_parser("appearance-preview", help="preview a named character cosmetic change without applying it")
    appearance_preview.add_argument("--save", required=True)
    appearance_preview.add_argument("--character-id", required=True)
    appearance_preview.add_argument("--changes", help="JSON object of appearance fields; omit with --restore")
    appearance_preview.add_argument("--output", required=True)
    appearance_preview.add_argument("--request-id")
    appearance_preview.add_argument("--restore", action="store_true")
    appearance_preview.set_defaults(handler=cmd_appearance_preview)
    appearance_apply = sub.add_parser("apply-appearance", help="build a separate cosmetic candidate after chat confirmation")
    appearance_apply.add_argument("--save", required=True)
    appearance_apply.add_argument("--request-id", required=True)
    appearance_apply.add_argument("--confirmation", required=True)
    appearance_apply.add_argument("--output", required=True)
    appearance_apply.add_argument("--transaction-id", required=True)
    appearance_apply.set_defaults(handler=cmd_apply_appearance)
    debt_payment = sub.add_parser("resolve-debt-payment", help="build a voluntary payment or early payoff candidate")
    debt_payment.add_argument("--save", required=True)
    debt_payment.add_argument("--payment", required=True, type=int)
    debt_payment.add_argument("--output", required=True)
    debt_payment.add_argument("--transaction-id", required=True)
    debt_payment.set_defaults(handler=cmd_resolve_debt_payment)
    opening = sub.add_parser("onboarding-status", help="read the next mandatory opening stage without changing a save")
    opening.add_argument("--save", required=True)
    opening.set_defaults(handler=cmd_onboarding_status)
    fire = sub.add_parser("grant-fire", help="prepare one initial Lilith-fire grant/explanation; commit the returned candidate")
    fire.add_argument("--save", required=True)
    fire.add_argument("--output", required=True)
    fire.add_argument("--transaction-id", required=True)
    fire.set_defaults(handler=cmd_grant_fire)
    allocation = sub.add_parser("allocation-widget", help="render a point-allocation draft; chat confirmation is required to apply")
    allocation.add_argument("--save", required=True)
    allocation.add_argument("--mode", required=True, choices=("initial", "fruit", "respec"))
    allocation.add_argument("--output", required=True)
    allocation.add_argument("--actor-id")
    allocation.add_argument("--stack-id")
    allocation.add_argument("--quantity", type=int, default=1)
    allocation.add_argument("--request-id")
    allocation.add_argument("--widget-state", help="optional saved draft JSON for reopening the same request")
    allocation.set_defaults(handler=cmd_allocation_widget)
    allocation_apply = sub.add_parser("allocation-resolve", help="validate a confirmed allocation draft into a separate save candidate")
    allocation_apply.add_argument("--save", required=True)
    allocation_apply.add_argument("--widget-state", required=True)
    allocation_apply.add_argument("--confirmation", required=True)
    allocation_apply.add_argument("--output", required=True)
    allocation_apply.add_argument("--transaction-id", required=True)
    allocation_apply.set_defaults(handler=cmd_allocation_resolve)
    validate = sub.add_parser("validate-save")
    validate.add_argument("path")
    validate.set_defaults(handler=cmd_validate_save)
    status_view = sub.add_parser(
        "status-view", help="print a validated read-only status/inventory snapshot and text fallback",
    )
    status_view.add_argument("path", help="current or candidate v3 save")
    status_view.add_argument(
        "--mode", choices=("compact", "character", "inventory", "equipment", "warehouse"),
        default="compact",
    )
    status_view.add_argument("--character-id", help="filter character/equipment output")
    status_view.set_defaults(handler=cmd_status_view)
    status_widget = sub.add_parser(
        "render-status-widget", help="render the read-only MUSE expandable status dashboard",
    )
    status_widget.add_argument("path", help="current or candidate v3 save")
    status_widget.add_argument("--output", required=True)
    status_widget.add_argument("--force", action="store_true")
    status_widget.set_defaults(handler=cmd_render_status_widget)
    debt_collection = sub.add_parser(
        "resolve-debt-collection",
        help="build a deterministic candidate for one pending five-day Lilith collection",
    )
    debt_collection.add_argument("--save", required=True)
    debt_collection.add_argument("--output", required=True)
    debt_collection.add_argument("--transaction-id", required=True)
    debt_collection.add_argument("--payment", type=int, default=0)
    debt_collection.add_argument("--force", action="store_true")
    debt_collection.set_defaults(handler=cmd_resolve_debt_collection)
    reward_effect = sub.add_parser(
        "reward-effect",
        help="hash one reward target before/after a candidate for an auditable ledger effect",
    )
    reward_effect.add_argument("--current", required=True)
    reward_effect.add_argument("--candidate", required=True)
    reward_effect.add_argument(
        "--target", required=True,
        choices=("player.gold", "inventory_bundle", "world_state.entitlements", "session_log"),
    )
    reward_effect.set_defaults(handler=cmd_reward_effect)
    hearing = sub.add_parser("apply-hearing-state",
                             help="validate a completed widget state and apply it to an explicit candidate save")
    hearing.add_argument("--save", required=True, help="source save; this file is never modified")
    hearing.add_argument("--state", required=True, help="completed widget state JSON")
    hearing.add_argument("--output", required=True, help="new candidate path; must differ from --save")
    hearing.add_argument("--widget-id", help="MUSE widget instance id for the audit record")
    hearing.add_argument("--force", action="store_true", help="overwrite an existing separate --output")
    hearing.set_defaults(handler=cmd_apply_hearing_state)
    migrate = sub.add_parser("migrate-save")
    migrate.add_argument("path")
    migrate.add_argument("--output")
    migrate.add_argument("--in-place", action="store_true")
    migrate.set_defaults(handler=cmd_migrate_save)
    commit = sub.add_parser("commit-save")
    commit.add_argument("--current", required=True)
    commit.add_argument("--candidate", required=True)
    commit.add_argument("--keep", type=int, default=50)
    commit.add_argument("--transaction-id", help="stable caller-supplied id for idempotent retry")
    commit.add_argument("--turn", type=int, help="committed game-turn number (default: previous + 1)")
    commit.set_defaults(handler=cmd_commit_save)
    commit_turn = sub.add_parser(
        "commit-turn",
        help="atomically/retryably commit a save plus one or more inventory consumptions",
    )
    commit_turn.add_argument("--current", required=True)
    commit_turn.add_argument("--candidate", required=True)
    commit_turn.add_argument("--transaction-id", required=True)
    commit_turn.add_argument("--turn", type=int)
    commit_turn.add_argument(
        "--inventory-use", action="append", metavar="KIND:ID",
        help="inventory operation; repeatable (KIND is mobs or events)",
    )
    commit_turn.add_argument(
        "--inventory-kind", choices=("mobs", "events"),
        help="legacy single-operation form; use together with --inventory-id",
    )
    commit_turn.add_argument(
        "--inventory-id", help="legacy single-operation form; use with --inventory-kind",
    )
    commit_turn.add_argument("--keep", type=int, default=50)
    commit_turn.set_defaults(handler=cmd_commit_turn)
    context = sub.add_parser("prepare-context")
    context.add_argument("--scene", required=True)
    context.add_argument("--include-scene", action="append",
                         help="union another scene pack; repeatable, primary scene remains --scene")
    context.add_argument("--save")
    context.add_argument("--character", action="append")
    context.add_argument("--term", action="append")
    for subject in ("location", "enemy", "item", "topic"):
        context.add_argument("--" + subject, action="append", help="search only the matching resource category")
    context.add_argument("--room", action="append", help="optional exact room id or room name scoped to the selected place")
    context.add_argument("--world-topic", action="append", choices=("calendar", "travel", "trade", "governance", "culture", "death"),
                         help="load the complete relevant regional chapter; repeatable")
    context.add_argument("--world-city", action="append",
                         help="reference a regional city without changing the selected physical stage; repeatable")
    context.add_argument("--opening-step", help="specific SCRIPT_OPENING_* id for the current opening step")
    context.add_argument("--intimate-scene", choices=("auto", "on", "off"), default="auto",
                         help="record an explicit prose-scene transition; auto retains the saved reading profile")
    context.add_argument("--condition", action="append")
    context.add_argument("--output")
    context.add_argument("--candidate-save-output",
                         help="write a candidate save with the context hash/scene patch; never mutates --save")
    context.add_argument("--force-candidate", action="store_true")
    context.add_argument("--phase", choices=("auto", "create", "offer", "advance", "settle", "probe"), default="auto")
    context.add_argument("--location-kind", choices=("town", "road", "dungeon"))
    context.add_argument("--movement-style", choices=("normal", "direct", "stroll", "wander", "idle"),
                         help="M51 movement style; wander is destination-free, idle is the existing nonmoving pastime")
    context.add_argument("--movement-urgency", choices=("none", "player_rush", "quest_time_pressure", "medical_emergency"), default="none")
    context.add_argument("--event-type", type=int, choices=range(1, 12),
                         help="filter event stock after the occurrence/type is determined")
    context.set_defaults(handler=prepare_context)
    begin = sub.add_parser("begin-turn", parents=[context], add_help=False,
                           help="prepare current context and verify only this turn's sources/save")
    begin.set_defaults(handler=cmd_begin_turn)
    finish = sub.add_parser("finish-turn", help="apply changes, atomically commit, and build the status display")
    for argument in ("current", "prepared", "changes", "output", "transaction-id"):
        finish.add_argument("--" + argument, required=True)
    finish.add_argument("--turn", type=int)
    finish.add_argument("--keep", type=int, default=50)
    finish.add_argument("--inventory-use", action="append")
    finish.add_argument("--status-output")
    finish.set_defaults(handler=cmd_finish_turn)
    response_check = sub.add_parser("check-response", help="check an unsent reply's length and choices without changing a save")
    response_check.add_argument("--save", required=True)
    response_check.add_argument("--before-save")
    response_check.add_argument("--response", required=True)
    def check_response(args):
        from response_contract import check
        return check(sys.modules[__name__], args)
    response_check.set_defaults(handler=check_response)
    read_save = sub.add_parser("read-save", help="read an exact field omitted from the bounded state view")
    read_save.add_argument("--save", required=True)
    read_save.add_argument("--pointer", default="")
    read_save.set_defaults(handler=cmd_read_save)
    changes = sub.add_parser("apply-changes", help="apply a bounded change list to a complete prepared candidate")
    changes.add_argument("--current", required=True)
    changes.add_argument("--prepared", required=True)
    changes.add_argument("--changes", required=True)
    changes.add_argument("--output", required=True)
    changes.add_argument("--draft", action="store_true", help="write an uncommitted calculation draft; final save/transition validation remains mandatory")
    changes.set_defaults(handler=cmd_apply_changes)
    init = sub.add_parser("inventory-init", help="initialize missing empty inventory containers; preserve existing state")
    init.set_defaults(handler=cmd_inventory_init)
    reset = sub.add_parser("inventory-reset", help="reset stock once per successful package generation")
    reset.add_argument("--reason", required=True, choices=("package-upgrade",))
    reset.add_argument("--generation", required=True)
    reset.set_defaults(handler=cmd_inventory_reset)
    sync_seed = sub.add_parser(
        "inventory-sync-seed",
        help="refresh existing seed-owned inventory content while preserving usage state",
    )
    sync_seed.add_argument("--kind", action="append", choices=("mobs", "events"),
                           help="inventory kind to synchronize; repeatable (default: both)")
    sync_seed.add_argument("--keep", type=int, default=50,
                           help="number of pre-sync inventory backups to retain")
    sync_seed.set_defaults(handler=cmd_inventory_sync_seed)
    use = sub.add_parser("inventory-use", help="atomically mark one stock entry as used")
    use.add_argument("--kind", required=True, choices=("mobs", "events"))
    use.add_argument("--id", required=True, help="inventory entry id")
    use.add_argument("--campaign-id", required=True)
    use.add_argument("--turn", required=True, type=int)
    use.add_argument("--transaction-id", required=True,
                     help="stable id; retrying the same operation is idempotent")
    use.add_argument("--keep", type=int, default=50, help="number of inventory backups to retain")
    use.set_defaults(handler=cmd_inventory_use)
    status = sub.add_parser("inventory-status")
    status.set_defaults(handler=cmd_inventory_status)
    template = sub.add_parser(
        "inventory-template",
        help="write a deterministic refill payload skeleton (schema: schemas/inventory_append.schema.json)",
    )
    template.add_argument("--output", required=True)
    template.add_argument("--max", type=int, default=8, help="total additions allowed, 1..8")
    template.add_argument("--force", action="store_true")
    template.add_argument("--save", help="explicit committed campaign under saves/; omission returns needs_campaign")
    template.add_argument("--location-kind", choices=("town", "road", "dungeon"))
    template.add_argument("--event-seed", help="copy one eligible canonical event into the contextual refill payload")
    template.set_defaults(handler=cmd_inventory_template)
    append = sub.add_parser(
        "inventory-append",
        help="validate and append a refill payload; start with inventory-template and its JSON schema",
    )
    append.add_argument("--input", required=True)
    append.add_argument("--max", type=int, default=8, help="total additions allowed, 1..8")
    append.set_defaults(handler=cmd_inventory_append)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"validate-save", "status-view", "render-status-widget", "read-save", "inventory-status", "onboarding-status", "world-calendar", "travel-plan", "check-response"}:
            result = args.handler(args)
        else:
            with workspace_gate():
                result = args.handler(args)
        if isinstance(result, tuple):
            code, payload = result
        else:
            code, payload = 0, result
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return code
    except (RuntimeProblem, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
