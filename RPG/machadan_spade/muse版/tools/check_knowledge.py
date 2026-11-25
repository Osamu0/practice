#!/usr/bin/env python3
"""Validate the installed Machadan Muse knowledge tree.

The normal invocation is read-only.  ``--anchors`` enables a byte-for-byte
rebuild comparison of the anchor index; with ``--fix`` the rebuilt index is
written atomically.  ``--fix`` may also ask the runtime helper to initialise
missing mutable inventories, but never rewrites story/canonical documents.

Examples:
  python3 check_knowledge.py --json
  python3 check_knowledge.py --root ~/workspace/machadan_spade/muse版 --strict --anchors
  python3 check_knowledge.py --anchors --fix --json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

# Diagnostics must not leave bytecode inside a hash-checked distribution.
# This also applies when Muse starts the checker without Python's -B flag.
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
VENDOR_DIR = HERE / "_vendor"
sys.path.insert(0, str(VENDOR_DIR))

try:
    import yaml
except ImportError:  # handled as a useful validation error in main
    yaml = None


DEFAULT_ROOT = HERE.parent
REGISTRY_REL = Path("運用/正本レジストリ.yaml")
ROUTES_REL = Path("運用/ルーティング表.yaml")
DECISIONS_REL = Path("運用/決定台帳.yaml")
ANCHORS_REL = Path("tools/anchors.json")
SAVE_TEMPLATE_REL = Path("セーブ雛形.yaml")
SAVE_SCHEMA_REL = Path("schemas/save_v3.schema.json")
LEGACY_SAVE_SCHEMA_REL = Path("schemas/save_v2.schema.json")
WIDGET_SCHEMA_REL = Path("schemas/hearing_widget_state.schema.json")
INVENTORY_APPEND_SCHEMA_REL = Path("schemas/inventory_append.schema.json")
STATUS_WIDGET_TEMPLATE_REL = Path("tools/status_dashboard_template.html")

ALLOWED_LOADS = {
    "full", "section", "sections", "never", "on_conflict", "on_route",
    "on_doctor", "on_new_campaign", "on_init", "dynamic",
}
ALLOWED_ROLES = {
    "canonical", "supporting", "generated_view", "superseded",
    "seed_template", "mutable_state", "author_only",
}
REQUIRED_SCENES = {
    "start", "resume", "turn", "combat", "dungeon", "shop", "quest", "event",
    "generation", "style", "chekyun", "magic", "skills", "status", "enterprise",
    "debt", "manage",
}
REQUIRED_ROUTE_CONDITIONS = {
    ("combat", "firearm_action"): {"FIREARMS"},
    ("combat", "capture"): {"CAPTURE_RULES"},
    ("event", "festival"): {"FESTIVALS"},
    ("status", "inventory"): {"ITEMS"},
    ("status", "equipment"): {"ITEMS"},
    ("quest", "professional_case"): {"ENTERPRISE", "WORLD"},
    ("quest", "discovery"): {"ENTERPRISE", "DROPS"},
    ("quest", "research"): {"ENTERPRISE", "MAGITECH"},
    ("enterprise", "professional_case"): {"WORLD", "QUEST_PARTS"},
    ("enterprise", "discovery"): {"DROPS"},
    ("enterprise", "research"): {"SKILLS", "MAGIC"},
    ("debt", "debt_collection"): {"OPERATIONS"},
}
REQUIRED_COMMAND_SELECTORS = {
    "start": "Command S",
    "resume": "Command A",
    "status": "Command V",
    "enterprise": "Command O",
    "debt": "Command R",
}
REQUIRED_DECISIONS = {
    "M90": "COMBAT",
    "M91": "SAVE_TEMPLATE",
    "M92": "ENTERPRISE",
    "M93": "OPERATIONS",
    "M94": "SAVE_TEMPLATE",
    "M95": "ROUTES",
    "M96": "SKILLS",
}
FORBIDDEN_NAMES = {
    "INDEX.md", "アンカー索引.md", "build_restructure.py",
    "クエストカード_サンプル集.md", "設計変更リスト.md",
}
AUTHOR_ONLY_TEXTS = {
    "運用/設計変更リスト.md",
    "運用/クエストカード_サンプル集.md",
    "クエストカード_サンプル集.md",
}
LEGACY_REFERENCE_PATTERNS = {
    "legacy_source_reference": re.compile(
        r"(?:~?/)?(?:workspace/)?machadan_spade/source(?:/|\b)"),
    "legacy_anchor_reference": re.compile(
        r"(?:~?/)?(?:workspace/)?machadan_spade/アンカー索引\.md"),
    "legacy_builder_reference": re.compile(r"\bbuild_restructure\.py\b"),
}
PATH_SUFFIXES = (".md", ".txt", ".yaml", ".yml", ".json", ".py", ".html")


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    path: str = ""
    fixable: bool = False


class Report:
    def __init__(self, root: Path, strict: bool) -> None:
        self.root = root
        self.strict = strict
        self.issues: list[Issue] = []
        self.fixes: list[str] = []
        self.checks: dict[str, Any] = {}

    def add(self, severity: str, code: str, message: str,
            path: str | Path = "", fixable: bool = False) -> None:
        shown = str(path)
        if isinstance(path, Path):
            try:
                shown = path.resolve().relative_to(self.root).as_posix()
            except (OSError, ValueError):
                shown = str(path)
        issue = Issue(severity, code, message, shown, fixable)
        if issue not in self.issues:
            self.issues.append(issue)

    def error(self, code: str, message: str, path: str | Path = "",
              fixable: bool = False) -> None:
        self.add("error", code, message, path, fixable)

    def warning(self, code: str, message: str, path: str | Path = "",
                fixable: bool = False) -> None:
        self.add("warning", code, message, path, fixable)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def payload(self) -> dict[str, Any]:
        return {
            "ok": not self.errors,
            "root": str(self.root),
            "strict": self.strict,
            "checks": self.checks,
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
            "fixes": self.fixes,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "fixes": len(self.fixes),
            },
        }


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_bundled_yaml(report: Report) -> None:
    target_vendor = report.root / "tools/_vendor"
    if not (target_vendor / "yaml/__init__.py").is_file():
        report.error("bundled_yaml", "tools/_vendor/yaml is missing", target_vendor)
    if yaml is None:
        report.error("bundled_yaml", "bundled PyYAML could not be imported", VENDOR_DIR)
        return
    module_path = Path(getattr(yaml, "__file__", "")).resolve()
    bundled = module_path.is_relative_to(VENDOR_DIR.resolve())
    version = str(getattr(yaml, "__version__", "unknown"))
    report.checks["yaml"] = {
        "version": version,
        "path": str(module_path),
        "bundled": bundled,
    }
    if not bundled:
        report.error("bundled_yaml",
                     "external PyYAML was loaded instead of tools/_vendor", module_path)
    if version != "6.0.3":
        report.error("bundled_yaml", f"expected PyYAML 6.0.3; loaded {version}", module_path)


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_yaml(path: Path, report: Report, code: str) -> Any:
    if yaml is None:
        report.error("dependency_missing", "PyYAML is required", path)
        return None
    if not path.is_file():
        report.error(code, "required YAML file is missing", path)
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        report.error(code, f"invalid YAML: {exc}", path)
        return None


def load_json(path: Path, report: Report, code: str) -> Any:
    if not path.is_file():
        report.error(code, "required JSON file is missing", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.error(code, f"invalid JSON: {exc}", path)
        return None


def safe_child(root: Path, relative: Any, report: Report, code: str,
               owner: str | Path = "") -> Path | None:
    if not isinstance(relative, str) or not relative.strip():
        report.error(code, "path must be a non-empty relative string", owner)
        return None
    value = Path(relative)
    if value.is_absolute():
        report.error(code, f"absolute runtime path is not allowed: {relative}", owner)
        return None
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        report.error(code, f"path escapes runtime root: {relative}", owner)
        return None
    return resolved


def import_extractor(root: Path, report: Report):
    path = root / "tools/extract_anchors.py"
    if not path.is_file():
        report.error("extractor_missing", "extract_anchors.py is missing", path)
        return None
    try:
        spec = importlib.util.spec_from_file_location("machadan_extract_anchors", path)
        if spec is None or spec.loader is None:
            raise ImportError("could not construct import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # extractor failure must become a doctor result
        report.error("extractor_invalid", f"cannot load anchor extractor: {exc}", path)
        return None


def basic_anchor_freshness(root: Path, saved: Any, report: Report) -> None:
    if not isinstance(saved, dict) or saved.get("schema_version") != 2:
        report.error("anchors_schema", "anchors.json must use schema_version 2",
                     root / ANCHORS_REL, True)
        return
    indexed = saved.get("files")
    if not isinstance(indexed, dict):
        report.error("anchors_schema", "anchors.json files must be an object",
                     root / ANCHORS_REL, True)
        return
    actual: dict[str, Path] = {}
    excluded = {"saves", "state", "runtime", "_history", "__pycache__", "_vendor"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        if rel.as_posix() in AUTHOR_ONLY_TEXTS:
            continue
        actual[rel.as_posix()] = path
    for relative, path in actual.items():
        info = indexed.get(relative)
        if not isinstance(info, dict):
            report.error("anchors_missing_file", "text file is not indexed", relative, True)
            continue
        text = path.read_text(encoding="utf-8")
        if info.get("sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            report.error("anchors_stale", "indexed content hash is stale", relative, True)
        if info.get("total_lines") != len(text.splitlines()):
            report.error("anchors_stale", "indexed line count is stale", relative, True)
    for relative in sorted(set(indexed) - set(actual)):
        report.error("anchors_ghost", "index refers to a missing/excluded file", relative, True)
    report.checks["anchor_files"] = len(actual)


def check_anchors(root: Path, report: Report, deep: bool, fix: bool) -> dict | None:
    anchor_path = root / ANCHORS_REL
    saved = load_json(anchor_path, report, "anchors_missing")
    basic_anchor_freshness(root, saved, report)
    actual = None
    if deep:
        extractor = import_extractor(root, report)
        if extractor is not None:
            try:
                actual = extractor.build_index(root)
            except (OSError, UnicodeError, ValueError) as exc:
                report.error("anchor_extraction", str(exc), anchor_path)
            else:
                if fix and saved != actual:
                    atomic_json(anchor_path, actual)
                    saved = actual
                    report.fixes.append("regenerated tools/anchors.json")
                    repaired = {
                        "anchors_missing", "anchors_schema", "anchors_missing_file",
                        "anchors_stale", "anchors_ghost", "anchors_deep_stale",
                    }
                    report.issues = [
                        issue for issue in report.issues
                        if issue.code not in repaired
                    ]
                elif saved != actual:
                    report.error("anchors_deep_stale",
                                 "anchor structure differs from a deterministic rebuild",
                                 anchor_path, True)
    index = actual if actual is not None else saved
    if isinstance(index, dict):
        report.checks["anchors"] = index.get("total_anchors", 0)
    return index if isinstance(index, dict) else None


def inventory_state_check(path: Path, kind: str, report: Report) -> None:
    data = load_yaml(path, report, "inventory_invalid")
    if data is None:
        return
    if not isinstance(data, dict) or data.get("schema") != "machadan-inventory-v1":
        report.error("inventory_schema", "expected machadan-inventory-v1", path)
        return
    if data.get("kind") != kind:
        report.error("inventory_kind", f"expected kind={kind}", path)
    limits = data.get("limits")
    entries = data.get("entries")
    if not isinstance(limits, dict) or not all(
            isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for key, value in limits.items()):
        report.error("inventory_limits", "limits must map categories to non-negative integers", path)
        return
    expected_categories = {
        "mobs": {"town", "companions", "brothel", "travelers", "students"},
        "events": {"town", "road", "dungeon"},
    }[kind]
    if set(limits) != expected_categories:
        report.error("inventory_limits",
                     f"categories must be {sorted(expected_categories)}", path)
    if not isinstance(entries, list):
        report.error("inventory_entries", "entries must be a list", path)
        return
    seen: set[str] = set()
    seen_names: set[str] = set()
    unused: dict[str, int] = {key: 0 for key in limits}
    for position, entry in enumerate(entries):
        label = f"{path.name}:entries[{position}]"
        if not isinstance(entry, dict):
            report.error("inventory_entry", "entry must be an object", label)
            continue
        entry_id = entry.get("id")
        category = entry.get("category")
        if not isinstance(entry_id, str) or not entry_id:
            report.error("inventory_entry", "entry id is missing", label)
        elif entry_id in seen:
            report.error("inventory_duplicate", f"duplicate id {entry_id}", label)
        else:
            seen.add(entry_id)
        if category not in limits:
            report.error("inventory_category", f"unknown category {category!r}", label)
        elif entry.get("status", "unused") == "unused":
            unused[category] += 1
        if entry.get("status", "unused") not in {"unused", "used"}:
            report.error("inventory_status", "status must be unused or used", label)
        if kind == "mobs":
            name = str(entry.get("name") or "")
            if not name or name.casefold() in seen_names:
                report.error("inventory_name", "mob name is missing or duplicated", label)
            seen_names.add(name.casefold())
            age = entry.get("age")
            allowed_adult = {
                "成人", "不詳(成人)", "年齢不詳(成人)", "canonical_adult",
                "confirmed_adult", "adult", "unknown(adult)",
            }
            canonical_adult = any(
                re.sub(r"\s+", "", str(value)).casefold() in allowed_adult
                for value in (age, entry.get("adult_status")) if value is not None
            )
            if not canonical_adult and (
                    not isinstance(age, int) or isinstance(age, bool) or age < 18):
                report.error(
                    "inventory_adult",
                    "mob requires numeric age >=18 or an explicit canonical adult status",
                    label,
                )
        else:
            if not (entry.get("title") or entry.get("name")):
                report.error("inventory_title", "event title is missing", label)
            fields = entry.get("fields")
            if not ((isinstance(fields, dict) and fields) or entry.get("description") or
                    entry.get("content") or entry.get("introduction")):
                report.error("inventory_content", "event content is empty", label)
    for category, count in unused.items():
        if count > limits[category]:
            report.error("inventory_capacity",
                         f"{category} has {count} unused entries; limit is {limits[category]}", path)
    if not isinstance(data.get("applied_runs", []), list):
        report.error("inventory_runs", "applied_runs must be a list", path)
    if not isinstance(data.get("use_receipts", {}), dict):
        report.error("inventory_receipts", "use_receipts must be a mapping", path)


def initialise_inventories(root: Path, resources: dict, report: Report) -> None:
    missing = []
    for resource_id, item in resources.items():
        if not isinstance(item, dict) or item.get("role") != "mutable_state":
            continue
        path = safe_child(root, item.get("path"), report, "inventory_path", REGISTRY_REL)
        if path is not None and not path.exists() and item.get("initialize_from"):
            missing.append(resource_id)
    if not missing:
        return
    runtime = root / "tools/machadan_runtime.py"
    if not runtime.is_file():
        report.error("inventory_fix_unavailable",
                     "missing inventory can be initialized, but runtime helper is absent",
                     runtime)
        return
    result = subprocess.run(
        [sys.executable, str(runtime), "inventory-init"],
        cwd=root, text=True, capture_output=True,
        env={**os.environ, "MACHADAN_ROOT": str(root)},
    )
    if result.returncode:
        detail = ((result.stdout or "") + (result.stderr or "")).strip()[-1000:]
        report.error("inventory_fix_failed", f"inventory-init failed: {detail}", runtime)
        return
    report.fixes.append("initialized mutable inventories: " + ", ".join(sorted(missing)))


def check_registry(root: Path, report: Report) -> tuple[dict, dict]:
    registry_path = root / REGISTRY_REL
    registry = load_yaml(registry_path, report, "registry_missing")
    if not isinstance(registry, dict):
        return {}, {}
    if registry.get("schema") != "machadan-canonical-registry-v1":
        report.error("registry_schema", "unsupported canonical registry schema", registry_path)
    for key in ("version", "runtime_root", "generated_views", "precedence",
                "hard_invariants", "resources", "domains", "reconciliation"):
        if key not in registry:
            report.error("registry_required", f"missing top-level key: {key}", registry_path)
    precedence = registry.get("precedence")
    if (not isinstance(precedence, list) or not precedence or
            precedence[0] != "hard_invariants" or
            len(set(str(value) for value in precedence)) != len(precedence)):
        report.error("registry_precedence",
                     "precedence must be a unique list beginning with hard_invariants",
                     registry_path)
    generated_views = registry.get("generated_views")
    if not isinstance(generated_views, list) or not all(
            isinstance(value, str) and value for value in generated_views):
        report.error("generated_views", "generated_views must be a list of paths",
                     registry_path)
    resources = registry.get("resources")
    if not isinstance(resources, dict):
        report.error("registry_resources", "resources must be a mapping", registry_path)
        return registry, {}
    alias_owners: dict[str, str] = {}
    path_owners: dict[str, str] = {}
    for resource_id, item in resources.items():
        owner = f"{REGISTRY_REL.as_posix()}:{resource_id}"
        if not isinstance(resource_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]+", resource_id):
            report.error("resource_id", f"invalid resource id {resource_id!r}", owner)
        if not isinstance(item, dict):
            report.error("resource_entry", "resource entry must be a mapping", owner)
            continue
        role = item.get("role")
        load = item.get("load")
        if role not in ALLOWED_ROLES:
            report.error("resource_role", f"unsupported role {role!r}", owner)
        if load not in ALLOWED_LOADS:
            report.error("resource_load", f"unsupported load mode {load!r}", owner)
        aliases = item.get("aliases")
        if aliases is not None and (not isinstance(aliases, list) or not all(
                isinstance(value, str) and value for value in aliases)):
            report.error("resource_aliases", "aliases must be a list of strings", owner)
        elif isinstance(aliases, list):
            for alias in aliases:
                folded = alias.casefold()
                previous = alias_owners.get(folded)
                if previous is not None and previous != resource_id:
                    report.error("resource_aliases",
                                 f"alias {alias!r} is shared by {previous} and {resource_id}", owner)
                alias_owners[folded] = resource_id
        replacement = item.get("replaced_by")
        if replacement is not None and replacement not in resources:
            report.error("resource_replacement", f"unknown replacement {replacement!r}", owner)
        relative = item.get("path")
        if relative is None:
            if role != "superseded" and item.get("present") is not False:
                report.error("resource_path", "active resource has no path", owner)
            continue
        path = safe_child(root, relative, report, "resource_path", owner)
        if path is None:
            continue
        normalized = Path(relative).as_posix()
        previous_path = path_owners.get(normalized)
        if previous_path is not None and previous_path != resource_id:
            report.error("resource_path",
                         f"path is shared by {previous_path} and {resource_id}", owner)
        path_owners[normalized] = resource_id
        if not path.is_file():
            initializer = item.get("initialize_from")
            if role == "mutable_state" and (initializer in resources or item.get("initialize_mode") == "empty"):
                report.checks.setdefault("deferred_mutable_state", []).append(resource_id)
            else:
                report.error("resource_missing", f"resource file is missing: {relative}", owner)
        if role == "mutable_state":
            if item.get("mutable") is not True:
                report.error("mutable_flag", "mutable_state requires mutable: true", owner)
            initializer = item.get("initialize_from")
            seed = resources.get(initializer)
            initialize_mode = item.get("initialize_mode", "seed")
            if initialize_mode not in {"empty", "seed"}:
                report.error("inventory_initializer", "initialize_mode must be empty or seed", owner)
            elif initialize_mode == "empty":
                # Empty means ready-for-personalised-refill, not a missing seed.
                # initialize_from may remain as a reference/example for old tools.
                pass
            elif not isinstance(seed, dict):
                report.error("inventory_initializer", f"unknown initializer {initializer!r}", owner)
            elif seed.get("role") != "seed_template" or seed.get("load") != "on_init":
                report.error("inventory_initializer",
                             "initializer must be a seed_template with load=on_init", owner)
            if path.is_file():
                kind = "mobs" if "mob" in resource_id.casefold() else "events"
                inventory_state_check(path, kind, report)
    domains = registry.get("domains")
    if not isinstance(domains, dict):
        report.error("registry_domains", "domains must be a mapping", registry_path)
    else:
        for domain_id, domain in domains.items():
            owner = f"{REGISTRY_REL.as_posix()}:domains.{domain_id}"
            if not isinstance(domain, dict) or not domain.get("revision"):
                report.error("domain_entry", "domain requires a revision", owner)
                continue
            for category in ("canonical", "supporting", "superseded"):
                values = domain.get(category)
                if not isinstance(values, list):
                    report.error("domain_entry", f"{category} must be a list", owner)
                    continue
                for resource_id in values:
                    if resource_id not in resources:
                        report.error("domain_resource",
                                     f"unknown resource {resource_id!r}", owner)
    for relative in generated_views if isinstance(generated_views, list) else []:
        path = safe_child(root, relative, report, "generated_view_path", registry_path)
        if path is not None and not path.is_file():
            report.error("generated_view_missing", f"generated view is missing: {relative}", path)
    invariant_text = "\n".join(
        str(item.get("rule", "")) for item in registry.get("hard_invariants", [])
        if isinstance(item, dict)
    )
    if "18" not in invariant_text or "プレイヤー" not in invariant_text:
        report.error("adult_invariant", "hard invariants must preserve numeric player age >=18",
                     registry_path)
    invariants = registry.get("hard_invariants")
    if not isinstance(invariants, list):
        report.error("hard_invariants", "hard_invariants must be a list", registry_path)
    else:
        invariant_ids = [item.get("id") for item in invariants if isinstance(item, dict)]
        if (len(invariant_ids) != len(invariants) or any(not value for value in invariant_ids)
                or len(set(invariant_ids)) != len(invariant_ids)):
            report.error("hard_invariants", "hard invariant IDs must be present and unique",
                         registry_path)
    report.checks["resources"] = len(resources)
    report.checks["domains"] = len(domains) if isinstance(domains, dict) else 0
    return registry, resources


def check_decisions(root: Path, registry: dict, resources: dict, report: Report) -> dict:
    path = root / DECISIONS_REL
    decisions = load_yaml(path, report, "decisions_missing")
    if not isinstance(decisions, dict):
        return {}
    if decisions.get("schema") != "machadan-decision-registry-v1":
        report.error("decisions_schema", "unsupported decision registry schema", path)
    active = decisions.get("active")
    superseded = decisions.get("superseded")
    if not isinstance(active, list) or not isinstance(superseded, list):
        report.error("decisions_structure", "active and superseded must be lists", path)
        return decisions
    active_by_id: dict[str, dict] = {}
    subjects: set[str] = set()
    for position, entry in enumerate(active):
        owner = f"{DECISIONS_REL.as_posix()}:active[{position}]"
        if not isinstance(entry, dict):
            report.error("decision_entry", "active decision must be a mapping", owner)
            continue
        decision_id = entry.get("id")
        subject = entry.get("subject")
        canonical = entry.get("canonical")
        if not isinstance(decision_id, str) or not decision_id:
            report.error("decision_entry", "active decision requires id", owner)
            continue
        if decision_id in active_by_id:
            report.error("decision_duplicate", f"duplicate active decision {decision_id}", owner)
        active_by_id[decision_id] = entry
        if not isinstance(subject, str) or not subject:
            report.error("decision_entry", f"{decision_id} requires subject", owner)
        elif subject in subjects:
            report.error("decision_duplicate", f"duplicate active subject {subject}", owner)
        else:
            subjects.add(subject)
        if canonical not in resources:
            report.error("decision_canonical", f"{decision_id} has unknown canonical {canonical!r}", owner)
        if not isinstance(entry.get("rule"), str) or not entry["rule"].strip():
            report.error("decision_entry", f"{decision_id} requires a non-empty rule", owner)
    superseded_ids: set[str] = set()
    for position, entry in enumerate(superseded):
        owner = f"{DECISIONS_REL.as_posix()}:superseded[{position}]"
        if not isinstance(entry, dict):
            report.error("decision_entry", "superseded decision must be a mapping", owner)
            continue
        decision_id = entry.get("id")
        replacement = entry.get("replaced_by")
        if not isinstance(decision_id, str) or not decision_id:
            report.error("decision_entry", "superseded decision requires id", owner)
            continue
        if decision_id in superseded_ids:
            report.error("decision_duplicate", f"duplicate superseded decision {decision_id}", owner)
        superseded_ids.add(decision_id)
        if decision_id in active_by_id:
            report.error(
                "decision_conflict", f"decision {decision_id} is both active and superseded", owner,
            )
        if replacement not in active_by_id:
            report.error(
                "decision_replacement", f"{decision_id} has non-active replacement {replacement!r}", owner,
            )
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            report.error("decision_entry", f"{decision_id} requires a supersession reason", owner)
    for decision_id, canonical in REQUIRED_DECISIONS.items():
        entry = active_by_id.get(decision_id)
        if not isinstance(entry, dict):
            report.error("decision_required", f"required active decision is missing: {decision_id}", path)
        elif entry.get("canonical") != canonical:
            report.error(
                "decision_required",
                f"{decision_id} canonical must be {canonical}, got {entry.get('canonical')!r}",
                path,
            )
    domains = registry.get("domains") if isinstance(registry, dict) else None
    if isinstance(domains, dict):
        for domain_id, domain in domains.items():
            revision = domain.get("revision") if isinstance(domain, dict) else None
            if revision not in active_by_id:
                report.error(
                    "domain_revision",
                    f"domain {domain_id} points to non-active decision {revision!r}",
                    root / REGISTRY_REL,
                )
    report.checks["decisions"] = {
        "active": len(active_by_id), "superseded": len(superseded_ids),
    }
    return decisions


def anchor_for_selector(root: Path, index: dict, relative: str,
                        selector: dict) -> tuple[dict | None, str]:
    info = index.get("files", {}).get(relative)
    if not isinstance(info, dict):
        return None, "resource is absent from anchors.json"
    anchors = info.get("anchors")
    if not isinstance(anchors, list):
        return None, "file has no anchor list"
    selector_id = str(selector.get("id") or "")
    if selector_id:
        exact = [item for item in anchors if item.get("id") == selector_id]
        if len(exact) == 1:
            return exact[0], ""
        if len(exact) > 1:
            return None, f"id {selector_id} is ambiguous"
    match = str(selector.get("match") or "")
    if not match:
        return None, f"id {selector_id!r} was not found and match is empty"
    folded = match.casefold()
    title_matches = [item for item in anchors if folded in str(item.get("title", "")).casefold()]
    if len(title_matches) == 1:
        return title_matches[0], ""
    path = root / relative
    if not path.is_file():
        return None, "resource file is missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [number for number, line in enumerate(lines, 1) if folded in line.casefold()]
    containing = [item for item in anchors if any(
        isinstance(item.get("start"), int) and isinstance(item.get("end"), int)
        and item["start"] <= number <= item["end"] for number in hits)]
    containing.sort(key=lambda item: (item.get("line_count", 10**9), -item.get("start", 0)))
    if containing and (len(containing) == 1 or
                       containing[0].get("line_count") < containing[1].get("line_count")):
        return containing[0], ""
    return None, f"selector {selector_id or match!r} does not resolve uniquely"


def iter_route_entries(routes: dict) -> Iterable[tuple[str, dict]]:
    for condition, entries in routes.get("global_conditions", {}).items():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    yield f"global_conditions.{condition}", entry
    base = routes.get("base_pack")
    if isinstance(base, dict):
        for group in ("required", "verify_after_turn"):
            for entry in base.get(group, []) if isinstance(base.get(group), list) else []:
                if isinstance(entry, dict):
                    yield f"base_pack.{group}", entry
    scenes = routes.get("scene_packs")
    if isinstance(scenes, dict):
        for scene_id, scene in scenes.items():
            if not isinstance(scene, dict):
                continue
            for group in ("required", "conditional", "dynamic", "after"):
                for entry in scene.get(group, []) if isinstance(scene.get(group), list) else []:
                    if isinstance(entry, dict):
                        yield f"scene_packs.{scene_id}.{group}", entry


def check_routes(root: Path, resources: dict, index: dict | None,
                 report: Report) -> dict:
    route_path = root / ROUTES_REL
    routes = load_yaml(route_path, report, "routes_missing")
    if not isinstance(routes, dict):
        return {}
    if routes.get("schema") != "machadan-routing-v1":
        report.error("routes_schema", "unsupported routing schema", route_path)
    for key in ("version", "registry", "generated_context", "rules",
                "base_pack", "scene_packs", "persona_files"):
        if key not in routes:
            report.error("routes_required", f"missing top-level key: {key}", route_path)
    registry_ref = safe_child(root, routes.get("registry"), report, "routes_registry", route_path)
    if registry_ref is not None and registry_ref != (root / REGISTRY_REL).resolve():
        report.error("routes_registry", "route registry must point at the canonical registry", route_path)
    context_ref = safe_child(root, routes.get("generated_context"), report,
                             "routes_context", route_path)
    if context_ref is not None and "runtime" not in context_ref.parts:
        report.error("routes_context", "generated context must live under a runtime directory", route_path)
    scenes = routes.get("scene_packs")
    if not isinstance(scenes, dict):
        report.error("routes_scenes", "scene_packs must be a mapping", route_path)
        scenes = {}
    missing_scenes = sorted(REQUIRED_SCENES - set(scenes))
    if missing_scenes:
        report.error("routes_scenes", "missing required scenes: " + ", ".join(missing_scenes), route_path)
    aliases: dict[str, str] = {}
    for scene_id, scene in scenes.items():
        if not isinstance(scene, dict):
            report.error("scene_entry", f"scene {scene_id} must be a mapping", route_path)
            continue
        scene_aliases = scene.get("aliases")
        if not isinstance(scene_aliases, list) or not all(
                isinstance(alias, str) and alias.strip() for alias in scene_aliases):
            report.error("scene_alias", f"scene {scene_id} aliases must be non-empty strings", route_path)
            scene_aliases = []
        for alias in scene_aliases:
            folded = str(alias).casefold()
            previous = aliases.get(folded)
            if previous is not None and previous != scene_id:
                report.error("scene_alias", f"alias {alias!r} is shared by {previous} and {scene_id}", route_path)
            aliases[folded] = str(scene_id)
    for (scene_id, condition), expected_resources in REQUIRED_ROUTE_CONDITIONS.items():
        scene = scenes.get(scene_id)
        entries = scene.get("conditional") if isinstance(scene, dict) else None
        matches = [
            entry for entry in entries if isinstance(entry, dict) and entry.get("when") == condition
        ] if isinstance(entries, list) else []
        if len(matches) != 1:
            report.error(
                "route_required_condition",
                f"scene {scene_id} must define condition {condition!r} exactly once",
                route_path,
            )
            continue
        actual_resources: set[str] = set()
        resource = matches[0].get("resource")
        if isinstance(resource, str):
            actual_resources.add(resource)
        resources_list = matches[0].get("resources")
        if isinstance(resources_list, list):
            actual_resources.update(value for value in resources_list if isinstance(value, str))
        missing = sorted(expected_resources - actual_resources)
        if missing:
            report.error(
                "route_required_condition",
                f"scene {scene_id} condition {condition!r} misses: {', '.join(missing)}",
                route_path,
            )
    for scene_id, expected_match in REQUIRED_COMMAND_SELECTORS.items():
        scene = scenes.get(scene_id)
        entries = scene.get("required") if isinstance(scene, dict) else None
        selectors = []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("resource") == "COMMANDS":
                    values = entry.get("selectors")
                    if isinstance(values, list):
                        selectors.extend(value for value in values if isinstance(value, dict))
        if not any(selector.get("match") == expected_match for selector in selectors):
            report.error(
                "route_command_selector",
                f"scene {scene_id} must select {expected_match!r} from COMMANDS",
                route_path,
            )
    selectors_checked = 0
    reachable_resources: set[str] = set()
    for location, entry in iter_route_entries(routes):
        owner = f"{ROUTES_REL.as_posix()}:{location}"
        mode = entry.get("mode")
        if mode not in {"full", "section", "sections", None}:
            report.error("route_mode", f"unsupported route mode {mode!r}", owner)
        ids: list[Any] = []
        if "resource" in entry:
            ids.append(entry.get("resource"))
        if "resources" in entry:
            if not isinstance(entry.get("resources"), list):
                report.error("route_resources", "resources must be a list", owner)
            else:
                ids.extend(entry["resources"])
        for resource_id in ids:
            if resource_id not in resources:
                report.error("route_resource", f"unknown resource {resource_id!r}", owner)
            elif isinstance(resource_id, str):
                reachable_resources.add(resource_id)
        if ".conditional" in location:
            condition = entry.get("when")
            if not isinstance(condition, str) or re.fullmatch(r"[a-z][a-z0-9_]*", condition) is None:
                report.error("route_condition", f"invalid or missing condition {condition!r}", owner)
        if entry.get("path") is not None:
            path = safe_child(root, entry.get("path"), report, "route_path", owner)
            if path is not None and not path.is_file():
                report.error("route_path", f"dynamic path is missing: {entry.get('path')}", owner)
        if entry.get("directory") is not None:
            directory = safe_child(root, entry.get("directory"), report, "route_directory", owner)
            if directory is not None and not directory.is_dir():
                report.error("route_directory",
                             f"dynamic directory is missing: {entry.get('directory')}", owner)
        initializer = entry.get("initialize_from")
        if initializer is not None and initializer not in resources:
            report.error("route_initializer", f"unknown initializer {initializer!r}", owner)
        selectors = entry.get("selectors")
        if selectors is None:
            continue
        if not isinstance(selectors, list):
            report.error("route_selectors", "selectors must be a list", owner)
            continue
        resource_id = entry.get("resource")
        item = resources.get(resource_id)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            report.error("route_selectors", "selectors require a path-backed resource", owner)
            continue
        relative = Path(item["path"]).as_posix()
        for position, selector in enumerate(selectors):
            selectors_checked += 1
            if not isinstance(selector, dict):
                report.error("route_selector", f"selector {position} must be an object", owner)
                continue
            if index is None:
                continue
            anchor, reason = anchor_for_selector(root, index, relative, selector)
            if anchor is None:
                report.error("route_selector", reason, f"{owner}:selectors[{position}]")
            elif not isinstance(anchor.get("line_count"), int) or anchor["line_count"] < 1:
                report.error("route_selector", "selector resolved to an empty section", owner)
    persona_files = routes.get("persona_files")
    found_ids: dict[str, str] = {}
    if not isinstance(persona_files, dict):
        report.error("persona_map", "persona_files must be a mapping", route_path)
        persona_files = {}
    for char_id, relative in persona_files.items():
        path = safe_child(root, relative, report, "persona_path", route_path)
        if path is None or not path.is_file():
            report.error("persona_path", f"persona file is missing: {relative}", route_path)
            continue
        text = path.read_text(encoding="utf-8")
        ids = re.findall(r"CHAR_ID:\s*([A-Za-z][A-Za-z0-9_-]*_\d+)", text)
        if len(ids) != 1 or ids[0] != char_id:
            report.error("persona_id",
                         f"mapped id {char_id!r} does not match file ids {ids!r}", path)
        for value in ids:
            if value in found_ids and found_ids[value] != relative:
                report.error("persona_duplicate", f"CHAR_ID {value} occurs in multiple files", path)
            found_ids[value] = relative
    persona_dir = root / "人格"
    if persona_dir.is_dir():
        for path in sorted(persona_dir.glob("*.md")):
            ids = re.findall(r"CHAR_ID:\s*([A-Za-z][A-Za-z0-9_-]*_\d+)",
                             path.read_text(encoding="utf-8"))
            for char_id in ids:
                if char_id not in persona_files:
                    report.error("persona_unrouted", f"CHAR_ID {char_id} is not in persona_files", path)
    report.checks["scenes"] = len(scenes)
    report.checks["selectors"] = selectors_checked
    report.checks["personas"] = len(persona_files)
    deferred_resources: list[str] = []
    required_route_resources: list[str] = []
    for resource_id, item in resources.items():
        if not isinstance(item, dict):
            continue
        if item.get("role") not in {"canonical", "supporting"}:
            continue
        if item.get("load") not in {"full", "section", "sections"}:
            continue
        if item.get("present", True) is False or not isinstance(item.get("path"), str):
            continue
        coverage = item.get("route_coverage")
        if isinstance(coverage, dict) and coverage.get("deferred") is True:
            reason = coverage.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                report.error("route_coverage_deferred",
                             f"{resource_id} is deferred without a reason", route_path)
            deferred_resources.append(resource_id)
            continue
        required_route_resources.append(resource_id)
        if resource_id not in reachable_resources:
            report.error("route_coverage",
                         f"canonical/supporting resource {resource_id} is unreachable from every scene",
                         route_path)
    report.checks["route_coverage"] = {
        "required": len(required_route_resources),
        "reachable": len(set(required_route_resources) & reachable_resources),
        "deferred": sorted(deferred_resources),
    }
    return routes


def check_sentinels(root: Path, index: dict | None, report: Report) -> None:
    if index is None:
        return
    sentinels = {
        ("運用/System_Templates.md", "TEMPLATE_SAVE"): 8,
        ("運用/System_Templates.md", "SCRIPT_OPENING_AWAKENING"): 3,
        ("運用/System_Templates.md", "SCRIPT_OPENING_PLAY_MODE"): 3,
    }
    for (relative, anchor_id), minimum in sentinels.items():
        anchors = index.get("files", {}).get(relative, {}).get("anchors", [])
        matches = [item for item in anchors if item.get("id") == anchor_id]
        if len(matches) != 1:
            report.error("sentinel_anchor",
                         f"expected exactly one {anchor_id}; found {len(matches)}", relative)
        elif matches[0].get("line_count", 0) < minimum:
            report.error("sentinel_anchor",
                         f"{anchor_id} is truncated ({matches[0].get('line_count')} lines)", relative)


def json_schema_errors(
    value: Any, schema: Any, path: str = "$", _root: Any | None = None,
) -> list[str]:
    """Validate the small JSON-Schema subset used by the bundled save schema."""
    if not isinstance(schema, dict):
        return [f"{path}: schema node is not an object"]
    if _root is None:
        _root = schema
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        resolved = _root
        for part in reference[2:].split("/"):
            if not isinstance(resolved, dict) or part not in resolved:
                return [f"{path}: unresolved schema reference {reference}"]
            resolved = resolved[part]
        return json_schema_errors(value, resolved, path, _root)
    errors: list[str] = []
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for child in all_of:
            errors.extend(json_schema_errors(value, child, path, _root))
    condition = schema.get("if")
    if isinstance(condition, dict):
        condition_matches = not json_schema_errors(value, condition, path, _root)
        branch = schema.get("then") if condition_matches else schema.get("else")
        if isinstance(branch, dict):
            errors.extend(json_schema_errors(value, branch, path, _root))
    if "oneOf" in schema:
        candidates = [json_schema_errors(value, option, path, _root) for option in schema["oneOf"]]
        if sum(not candidate for candidate in candidates) != 1:
            errors.append(f"{path}: value must match exactly one oneOf branch")
    if "anyOf" in schema:
        candidates = [json_schema_errors(value, option, path, _root) for option in schema["anyOf"]]
        if not any(not candidate for candidate in candidates):
            errors.append(f"{path}: value must match at least one anyOf branch")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not in enum")
    expected = schema.get("type")
    def type_matches(kind: Any) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(kind, True)
    type_ok = any(type_matches(item) for item in expected) if isinstance(expected, list) else type_matches(expected)
    if expected is not None and not type_ok:
        return errors + [f"{path}: expected {expected}"]
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required if isinstance(required, list) else []:
            if key not in value:
                errors.append(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child in properties.items():
                if key in value:
                    errors.extend(json_schema_errors(value[key], child, f"{path}.{key}", _root))
            if schema.get("additionalProperties") is False:
                for key in set(value) - set(properties):
                    errors.append(f"{path}: unexpected property {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                for key in set(value) - set(properties):
                    errors.extend(json_schema_errors(value[key], schema["additionalProperties"], f"{path}.{key}", _root))
        if isinstance(schema.get("propertyNames"), dict):
            for key in value:
                errors.extend(json_schema_errors(key, schema["propertyNames"], f"{path}.<key>", _root))
        if len(value) < schema.get("minProperties", 0):
            errors.append(f"{path}: object has fewer than minProperties")
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            errors.append(f"{path}: object has more than maxProperties")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for position, item in enumerate(value):
            errors.extend(json_schema_errors(item, schema["items"], f"{path}[{position}]", _root))
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{path}: array items must be unique")
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: array has fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: array has more than maxItems")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{path}: string is shorter than minLength")
    if isinstance(value, str) and "maxLength" in schema and len(value) > schema["maxLength"]:
        errors.append(f"{path}: string is longer than maxLength")
    if isinstance(value, str) and isinstance(schema.get("pattern"), str):
        if re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: string does not match pattern")
    if isinstance(value, str) and schema.get("format") == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{path}: string is not an ISO 8601 date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        import math
        if isinstance(value, float) and not math.isfinite(value):
            return errors + [f"{path}: number must be finite"]
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value is above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: value is not above exclusiveMinimum")
    return errors


def check_save_schema_contract(save_schema: dict, report: Report) -> None:
    """Keep the v3 schema from silently dropping cross-system state."""
    path = report.root / SAVE_SCHEMA_REL
    expected_top = {
        "player", "party", "inn_reserve", "inventory", "item_definitions",
        "item_instances", "active_event", "debt_state", "enterprise_state",
    }
    definitions = save_schema.get("$defs")
    required = save_schema.get("required")
    actual_top = set(required) if isinstance(required, list) else set()
    if not expected_top.issubset(actual_top):
        missing = sorted(expected_top - actual_top)
        report.error(
            "save_schema_contract", "v3 top-level required misses: " + ", ".join(missing), path,
        )
    expected_defs = {
        "character": {
            "character_version", "character_id", "build_complete", "name", "gender", "age",
            "race", "job", "job_profile", "base_stats", "growth_bonus", "equipment_bonus",
            "fire_bonus", "temporary_modifiers", "effective_stats", "base_lp", "job_lp_bonus",
            "fire_lp_bonus", "temporary_lp_bonus", "lp", "mp", "stats", "equipment",
            "statuses", "buffs", "ero_status",
        },
        "inventory": {"version", "bag", "carried_stacks", "warehouse", "reservations"},
        "questCard": {"quest_id", "immutable_hash", "progress", "amendments", "reward_contract"},
        "debtState": {
            "version", "contract_cycle_index", "contract_id", "principal", "interval_days",
            "next_collection_day", "scheduled_due", "cycle_paid", "collection_pending",
            "last_collection_day", "collection_serial", "positive_payment_collections",
            "full_payment_collections", "missed_collections", "collection_ledger",
            "active_benefits", "benefit_selection",
        },
    }
    if not isinstance(definitions, dict):
        report.error("save_schema_contract", "v3 schema must define $defs", path)
        return
    for definition, expected in expected_defs.items():
        node = definitions.get(definition)
        actual = set(node.get("required", [])) if isinstance(node, dict) else set()
        missing = sorted(expected - actual)
        if missing:
            report.error(
                "save_schema_contract",
                f"$defs.{definition}.required misses: {', '.join(missing)}",
                path,
            )
    inventory = definitions.get("inventory")
    bag = inventory.get("properties", {}).get("bag") if isinstance(inventory, dict) else None
    bag_required = set(bag.get("required", [])) if isinstance(bag, dict) else set()
    expected_bag = {
        "base_slots", "upgrade_count", "max_slots", "skill_bonus_slots",
        "effective_max_slots", "used_slots",
    }
    if not expected_bag.issubset(bag_required):
        report.error(
            "save_schema_contract",
            "inventory bag required misses: " + ", ".join(sorted(expected_bag - bag_required)),
            path,
        )
    debt = definitions.get("debtState")
    interval = debt.get("properties", {}).get("interval_days") if isinstance(debt, dict) else None
    if not isinstance(interval, dict) or interval.get("const") != 5:
        report.error("save_schema_contract", "debtState.interval_days must be const 5", path)


def runtime_validate_save(root: Path, path: Path, report: Report, code: str) -> None:
    runtime = root / "tools/machadan_runtime.py"
    if not runtime.is_file():
        report.error(code, "runtime semantic validator is missing", runtime)
        return
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(runtime), "validate-save", str(path)],
            cwd=root, text=True, capture_output=True,
            env={**os.environ, "MACHADAN_ROOT": str(root),
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report.error(code, f"runtime semantic validation failed to run: {exc}", path)
        return
    raw = (result.stdout or result.stderr or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        report.error(code, f"runtime semantic validator returned non-JSON: {raw[-500:]}", path)
        return
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if result.returncode or payload.get("ok") is not True:
        values = errors or [payload.get("error") or "unknown error"]
        detail = "; ".join(str(value) for value in values)
        report.error(code, detail[:2000], path)
    warnings = payload.get("warnings") if isinstance(payload, dict) else None
    if isinstance(warnings, list) and path.parent == root / "saves":
        for warning in warnings:
            report.warning("save_semantic_warning", str(warning), path)


def check_status_runtime(root: Path, save_path: Path, output_path: Path, report: Report) -> None:
    runtime = root / "tools/machadan_runtime.py"
    before_hash = sha256_path(save_path)
    commands = (
        ("status-view", ["status-view", str(save_path)]),
        ("render-status-widget", [
            "render-status-widget", str(save_path), "--output", str(output_path),
        ]),
    )
    payloads: dict[str, dict] = {}
    for command_id, arguments in commands:
        try:
            result = subprocess.run(
                [sys.executable, str(runtime), *arguments], cwd=root, text=True,
                capture_output=True,
                env={**os.environ, "MACHADAN_ROOT": str(root)},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report.error("status_runtime", f"{command_id} failed to run: {exc}", runtime)
            continue
        raw = (result.stdout or result.stderr or "").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            report.error(
                "status_runtime", f"{command_id} returned non-JSON: {raw[-500:]}", runtime,
            )
            continue
        if result.returncode or payload.get("ok") is not True:
            report.error("status_runtime", f"{command_id} failed: {payload}", runtime)
            continue
        payloads[command_id] = payload
    view = payloads.get("status-view")
    snapshot = view.get("snapshot") if isinstance(view, dict) else None
    if isinstance(snapshot, dict):
        header = snapshot.get("header")
        expected_header = {"day": 1, "turn": 0, "revision": 0}
        if snapshot.get("schema") != "machadan-status-snapshot-v1":
            report.error("status_snapshot", "unexpected status snapshot schema", runtime)
        if not isinstance(header, dict) or any(
                header.get(key) != value for key, value in expected_header.items()):
            report.error(
                "status_snapshot",
                "snapshot must preserve Day 1 / last_committed_turn 0 / save_revision 0",
                runtime,
            )
        if not isinstance(view.get("text"), str) or not view["text"].strip():
            report.error("status_snapshot", "status-view text fallback is empty", runtime)
    elif view is not None:
        report.error("status_snapshot", "status-view did not return a snapshot", runtime)
    if "render-status-widget" in payloads:
        if not output_path.is_file():
            report.error("status_runtime", "render-status-widget did not create its output", output_path)
        elif "__STATUS_SNAPSHOT_JSON__" in output_path.read_text(encoding="utf-8"):
            report.error("status_runtime", "rendered widget retained its snapshot token", output_path)
    if sha256_path(save_path) != before_hash:
        report.error("status_runtime", "read-only status commands modified the source save", save_path)
    report.checks["status_runtime_commands"] = len(payloads)


def check_runtime_save_semantics(root: Path, template: Any, report: Report) -> None:
    checked = 0
    if isinstance(template, dict) and yaml is not None:
        instantiated = json.loads(json.dumps(template, ensure_ascii=False))
        instantiated["campaign_id"] = "template-semantic-check"
        instantiated["created_at"] = "2000-01-01T00:00:00+00:00"
        instantiated["updated_at"] = "2000-01-01T00:00:00+00:00"
        with tempfile.TemporaryDirectory(prefix="machadan-save-check-") as directory:
            path = Path(directory) / "template.yaml"
            path.write_text(
                yaml.safe_dump(instantiated, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            runtime_validate_save(root, path, report, "save_template_semantics")
            check_status_runtime(root, path, Path(directory) / "status.html", report)
            checked += 1
    saves = root / "saves"
    if saves.is_dir():
        for path in sorted(saves.glob("*.yaml")):
            runtime_validate_save(root, path, report, "save_semantics")
            checked += 1
    report.checks["semantic_saves"] = checked


def check_status_widget_template(root: Path, report: Report) -> None:
    path = root / STATUS_WIDGET_TEMPLATE_REL
    if not path.is_file():
        report.error("status_widget_template", "MUSE status dashboard template is missing", path)
        return
    text_value = path.read_text(encoding="utf-8")
    required_tokens = {
        "snapshot placeholder": "__STATUS_SNAPSHOT_JSON__",
        "read-only snapshot script": 'id="status-snapshot"',
        "day snapshot": "header.day",
        "turn snapshot": "header.turn",
        "revision snapshot": "header.revision",
        "inventory use": "bag.used_slots",
        "effective inventory capacity": "bag.effective_max_slots",
    }
    for label, token in required_tokens.items():
        if token not in text_value:
            report.error("status_widget_template", f"template misses {label}: {token}", path)
    expandable_tokens = {
        "tap-to-expand container": ("<details", 'node("details"'),
        "tap target": ("<summary", 'node("summary"'),
    }
    for label, alternatives in expandable_tokens.items():
        if not any(token in text_value for token in alternatives):
            report.error(
                "status_widget_template",
                f"template misses {label}: {' or '.join(alternatives)}",
                path,
            )
    forbidden = {"network request": "fetch(", "editable form": "<form", "direct input": "<input"}
    for label, token in forbidden.items():
        if token in text_value:
            report.error("status_widget_read_only", f"template contains {label}: {token}", path)
    report.checks["status_widget_template"] = True


def check_schemas(root: Path, report: Report) -> None:
    save_schema = load_json(root / SAVE_SCHEMA_REL, report, "save_schema_missing")
    legacy_save_schema = load_json(
        root / LEGACY_SAVE_SCHEMA_REL, report, "legacy_save_schema_missing"
    )
    widget_schema = load_json(root / WIDGET_SCHEMA_REL, report, "widget_schema_missing")
    inventory_schema = load_json(
        root / INVENTORY_APPEND_SCHEMA_REL, report, "inventory_append_schema_missing"
    )
    if isinstance(save_schema, dict):
        if save_schema.get("$id") != "MachaDun_Save_Muse_v3":
            report.error("save_schema_id", "save schema $id must be MachaDun_Save_Muse_v3",
                         root / SAVE_SCHEMA_REL)
        check_save_schema_contract(save_schema, report)
        template = load_yaml(root / SAVE_TEMPLATE_REL, report, "save_template_missing")
        if template is not None:
            for placeholder in ("campaign_id", "created_at", "updated_at"):
                if template.get(placeholder) != "":
                    report.error(
                        "save_template_placeholder",
                        f"template {placeholder} must stay empty for new-save materialization",
                        root / SAVE_TEMPLATE_REL,
                    )
            # The bundled file is a creation template: setup/new-save fills
            # its identity and timestamps before it becomes a real save.
            instantiated = json.loads(json.dumps(template, ensure_ascii=False))
            instantiated["campaign_id"] = instantiated.get("campaign_id") or "template-check"
            instantiated["created_at"] = instantiated.get("created_at") or "2000-01-01T00:00:00+00:00"
            instantiated["updated_at"] = instantiated.get("updated_at") or "2000-01-01T00:00:00+00:00"
            for message in json_schema_errors(instantiated, save_schema):
                report.error("save_template_schema", message, root / SAVE_TEMPLATE_REL)
        check_runtime_save_semantics(root, template, report)
    if isinstance(legacy_save_schema, dict):
        if legacy_save_schema.get("$id") != "MachaDun_Save_Muse_v2":
            report.error("legacy_save_schema_id",
                         "legacy migration schema $id must be MachaDun_Save_Muse_v2",
                         root / LEGACY_SAVE_SCHEMA_REL)
    if isinstance(widget_schema, dict):
        if widget_schema.get("$id") != "machadan.hearing.widget.v2":
            report.error("widget_schema_id", "unexpected hearing widget schema id",
                         root / WIDGET_SCHEMA_REL)
        required = set(widget_schema.get("required", []))
        expected = {"schema", "schema_version", "step", "step_id", "next_step",
                    "revision", "valid", "complete", "answers", "validation"}
        if not expected.issubset(required):
            report.error("widget_schema_required",
                         "hearing widget schema is missing runtime state fields",
                         root / WIDGET_SCHEMA_REL)
        def profile_state(complete: bool, age: Any, valid: bool = True) -> dict:
            return {
                "schema": "machadan.hearing.widget.v2", "schema_version": 2,
                "step": 2, "step_id": "profile", "next_step": "body_female",
                "revision": 0, "valid": valid, "complete": complete,
                "answers": {
                    "name": "", "gender": {"choice": "", "free_text": ""},
                    "age": age,
                },
                "validation": {"errors": []},
            }
        semantic_cases = (
            ("incomplete_null_age", profile_state(False, None, False), True),
            ("complete_null_age", profile_state(True, None), False),
            ("complete_age_17", profile_state(True, 17), False),
            ("complete_age_18", profile_state(True, 18), True),
        )
        for case_id, state, should_pass in semantic_cases:
            passed = not json_schema_errors(state, widget_schema)
            if passed != should_pass:
                report.error(
                    "widget_schema_semantics",
                    f"profile condition case {case_id} expected pass={should_pass}, got {passed}",
                    root / WIDGET_SCHEMA_REL,
                )
        report.checks["widget_schema_cases"] = len(semantic_cases)
    if isinstance(inventory_schema, dict):
        if inventory_schema.get("$id") != "machadan-inventory-append-v1":
            report.error("inventory_schema_id", "unexpected inventory append schema id",
                         root / INVENTORY_APPEND_SCHEMA_REL)
        required = set(inventory_schema.get("required", []))
        if not {"schema", "run_id", "mobs", "events"}.issubset(required):
            report.error("inventory_schema_required", "inventory append schema misses required fields",
                         root / INVENTORY_APPEND_SCHEMA_REL)
    check_status_widget_template(root, report)
    report.checks["schemas"] = 4


def find_skill_root(root: Path) -> Path | None:
    candidates = [root.parent.parent / "skills", root.parent.parent / "workspace" / "skills"]
    workspace_env = os.environ.get("MACHADAN_WORKSPACE")
    if workspace_env:
        candidates.append(Path(workspace_env).expanduser() / "skills")
    for candidate in candidates:
        if (candidate / "machadan-gm/SKILL.md").is_file():
            return candidate
    return None


def resolve_doc_reference(root: Path, base: Path, token: str) -> Path | None:
    # Preserve the leading dots of a legitimate sibling-skill reference.
    value = token.strip().lstrip('([{').rstrip('.,;:)]}')
    if not value or any(char in value for char in "<>|") or "://" in value:
        return None
    if value.startswith("~/workspace/machadan_spade/muse版/"):
        return root / value.split("muse版/", 1)[1]
    if "machadan_spade/muse版/" in value:
        return root / value.split("machadan_spade/muse版/", 1)[1]
    if value.startswith("references/"):
        return base / value
    if value.startswith("../"):
        skill_root = find_skill_root(root)
        candidate = (base / value).resolve()
        if skill_root is not None and candidate.is_relative_to(skill_root.resolve()):
            return candidate
        return None
    if "workspace/skills/" in value or "/skills/machadan-" in value:
        skill_root = find_skill_root(root)
        marker = "workspace/skills/" if "workspace/skills/" in value else "/skills/"
        relative = value.split(marker, 1)[1]
        if skill_root is not None:
            candidate = (skill_root / relative).resolve()
            if candidate.is_relative_to(skill_root.resolve()):
                return candidate
        return None
    prefixes = ("運用/", "文章/", "世界/", "生成/", "人格/", "チェキュン/",
                "tools/", "schemas/", "state/", "saves/")
    if value.startswith(prefixes):
        if value.startswith(("state/", "saves/")) and "*" in value:
            return None
        return root / value
    return None


def check_references_and_legacy(root: Path, registry: dict, resources: dict,
                                routes: dict, report: Report) -> None:
    def is_mutable_runtime_path(relative: Path) -> bool:
        """Keep distribution-hygiene rules out of user-owned runtime data."""
        return (
            bool(relative.parts)
            and (
                relative.parts[0] in {"saves", "state"}
                or relative.parts[:2] == ("tools", "runtime")
            )
        )

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if is_mutable_runtime_path(rel):
            continue
        if "source" in rel.parts and (path.is_file() or path.is_dir()):
            report.error("forbidden_source", "author source material must not be distributed", rel)
        if path.is_file() and path.name in FORBIDDEN_NAMES:
            report.error("forbidden_legacy_file", "legacy/build-only file must not be distributed", rel)
    for resource_id, item in resources.items():
        if not isinstance(item, dict):
            continue
        historical = item.get("historical_name")
        if item.get("present") is False and isinstance(historical, str):
            matches = [
                path for path in root.rglob(historical)
                if not is_mutable_runtime_path(path.relative_to(root))
            ]
            for path in matches:
                report.error("superseded_present",
                             f"superseded resource {resource_id} is still distributed", path)
    active_scan: list[Path] = []
    excluded_ids = {"DESIGN_HISTORY", "DECISIONS", "CANONICAL_REGISTRY"}
    for resource_id, item in resources.items():
        if resource_id in excluded_ids or not isinstance(item, dict):
            continue
        if item.get("role") not in {"canonical", "supporting"} or item.get("load") == "never":
            continue
        relative = item.get("path")
        if isinstance(relative, str):
            path = root / relative
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                active_scan.append(path)
    for path in active_scan:
        text = path.read_text(encoding="utf-8")
        for code, pattern in LEGACY_REFERENCE_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                report.error(code, f"runtime document references a removed author path (line {line})", path)
    docs = [root / "README.md", root / "構成マップ.md",
            root / "ナレッジ索引.md", root / "運用/ルーティング表.md"]
    skill_root = find_skill_root(root)
    if skill_root is None:
        report.error("skills_missing", "current workspace skills were not found")
    else:
        for skill in ("machadan-gm", "machadan-doctor"):
            path = skill_root / skill / "SKILL.md"
            if not path.is_file():
                report.error("skill_missing", f"{skill} SKILL.md is missing", path)
            else:
                docs.append(path)
                docs.extend(sorted((path.parent / "references").glob("*.md")))
        report.checks["skill_root"] = str(skill_root)
    for document in docs:
        if not document.is_file():
            report.error("control_doc_missing", "control/skill document is missing", document)
            continue
        text = document.read_text(encoding="utf-8")
        for token in re.findall(r"`([^`\n]+)`", text):
            if not token.lower().endswith(PATH_SUFFIXES):
                continue
            candidate = resolve_doc_reference(root, document.parent, token)
            if candidate is None:
                continue
            if "*" in candidate.name:
                if not list(candidate.parent.glob(candidate.name)):
                    report.error("reference_missing", f"reference has no matches: {token}", document)
            elif not candidate.exists():
                # Mutable state and generated context are legitimately absent before first run.
                resolved = candidate.resolve()
                relative = resolved.relative_to(root) if resolved.is_relative_to(root) else None
                if relative and (relative.parts[:2] == ("state", "inventory") or
                                 relative.as_posix() in {"tools/runtime/current_context.md", "state/runtime/current_context.md"}):
                    continue
                report.error("reference_missing", f"referenced path is missing: {token}", document)
    # Generated human views must at least enumerate every active immutable resource.
    index_path = root / "ナレッジ索引.md"
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        for resource_id, item in resources.items():
            if (not isinstance(item, dict) or
                    item.get("role") in {"mutable_state", "superseded", "generated_view"}):
                continue
            relative = item.get("path")
            if isinstance(relative, str) and Path(relative).name not in text:
                report.error("knowledge_index_stale",
                             f"active resource {resource_id} is absent from the human index",
                             index_path)
    route_view = root / "運用/ルーティング表.md"
    if route_view.is_file() and isinstance(routes, dict):
        text = route_view.read_text(encoding="utf-8")
        for scene_id in routes.get("scene_packs", {}) if isinstance(
                routes.get("scene_packs"), dict) else {}:
            if f"`{scene_id}`" not in text:
                report.error("routing_view_stale",
                             f"scene {scene_id!r} is absent from the human routing view",
                             route_view)
        for char_id in routes.get("persona_files", {}) if isinstance(
                routes.get("persona_files"), dict) else {}:
            if f"`{char_id}`" not in text:
                report.error("routing_view_stale",
                             f"persona {char_id!r} is absent from the human routing view",
                             route_view)


def check_python_and_dice(root: Path, report: Report) -> None:
    count = 0
    for path in sorted((root / "tools").glob("*.py")):
        count += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            report.error("python_syntax", str(exc), path)
    dice = root / "tools/dice.py"
    tape = root / "tools/dice_tape.json"
    if dice.is_file() and tape.is_file():
        result = subprocess.run(
            [sys.executable, str(dice), "verify", "--tape", str(tape)],
            text=True, capture_output=True,
        )
        try:
            payload = json.loads((result.stdout or "").strip())
        except json.JSONDecodeError:
            payload = {"ok": False, "problems": [((result.stdout or "") + (result.stderr or ""))[-500:]]}
        if result.returncode or not payload.get("ok"):
            report.error("dice_tape", f"fixed dice tape failed verification: {payload.get('problems')}", tape)
    else:
        report.error("dice_missing", "dice.py or dice_tape.json is missing", root / "tools")
    report.checks["python_files"] = count


def find_manifest(root: Path) -> Path | None:
    candidate = root.parent / "RUNTIME_MANIFEST.json"
    if candidate.is_file():
        return candidate
    return None


def check_manifest(root: Path, report: Report) -> None:
    manifest_path = find_manifest(root)
    if manifest_path is None:
        report.checks["manifest"] = "not_present"
        if (root.parent / "VERSION.txt").is_file():
            report.error("manifest_missing",
                         "installed runtime RUNTIME_MANIFEST.json is missing",
                         root.parent / "RUNTIME_MANIFEST.json")
        return
    data = load_json(manifest_path, report, "manifest_invalid")
    if not isinstance(data, dict):
        return
    if (data.get("schema") != "machadan-runtime-manifest-v1" or
            data.get("base") != "machadan_spade" or
            not isinstance(data.get("version"), str) or not data.get("version") or
            not isinstance(data.get("files"), list)):
        report.error("manifest_schema", "unsupported runtime manifest", manifest_path)
        return
    version_path = manifest_path.parent / "VERSION.txt"
    if not version_path.is_file():
        report.error("manifest_version", "installed VERSION.txt is missing", version_path)
    else:
        match = re.search(r"^version:\s*(\S.*?)\s*$",
                          version_path.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
        if match is None or match.group(1) != data.get("version"):
            report.error("manifest_version",
                         "runtime manifest version does not match VERSION.txt", manifest_path)
    prefix = root.relative_to(manifest_path.parent).as_posix().rstrip("/") + "/"
    rows: dict[str, dict] = {}
    for position, row in enumerate(data["files"]):
        if not isinstance(row, dict) or not all(key in row for key in ("path", "size", "sha256")):
            report.error("manifest_row", f"invalid manifest row {position}", manifest_path)
            continue
        packaged = row.get("path")
        if not isinstance(packaged, str) or not packaged:
            report.error("manifest_row", f"invalid path in manifest row {position}", manifest_path)
            continue
        posix = Path(packaged)
        if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
            report.error("manifest_row", f"unsafe manifest path: {packaged}", manifest_path)
            continue
        if packaged in rows:
            report.error("manifest_duplicate", f"duplicate manifest path: {packaged}", manifest_path)
        rows[packaged] = row
    verified = 0
    expected = 0
    for packaged, row in rows.items():
        if not isinstance(packaged, str) or not packaged.startswith(prefix):
            continue
        relative = packaged[len(prefix):]
        rel_path = Path(relative)
        if any(part in {"saves", "state", "runtime", "_history"} for part in rel_path.parts):
            report.error("manifest_mutable",
                         "runtime manifest must not hash mutable/generated state", packaged)
            continue
        expected += 1
        path = root / rel_path
        if not path.is_file():
            report.error("manifest_missing", "manifest-listed immutable file is missing", relative)
            continue
        if (not isinstance(row.get("size"), int) or isinstance(row.get("size"), bool) or
                row["size"] < 0 or not isinstance(row.get("sha256"), str) or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            report.error("manifest_row", "invalid size or SHA-256", packaged)
            continue
        if row["size"] != path.stat().st_size or row["sha256"] != sha256_path(path):
            report.error("manifest_hash", "manifest hash/size mismatch", relative)
        else:
            verified += 1
    local_count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if (any(part in {"saves", "state", "runtime", "_history", "__pycache__"}
                for part in relative.parts) or path.suffix in {".pyc", ".pyo"}):
            continue
        local_count += 1
        packaged = prefix + relative.as_posix()
        if packaged not in rows:
            report.error("manifest_unlisted", "immutable runtime file is absent from manifest", relative)
    if expected == 0:
        report.error("manifest_scope", "manifest has no rows for the Muse runtime", manifest_path)
    if verified != expected or expected != local_count:
        report.error(
            "manifest_incomplete",
            f"immutable verification is incomplete: verified={verified}, "
            f"manifest_rows={expected}, local_files={local_count}",
            manifest_path,
        )
    report.checks["manifest"] = {
        "path": str(manifest_path), "prefix": prefix,
        "version": data.get("version"), "base": data.get("base"),
        "verified": verified, "manifest_rows": expected,
        "local_immutable_files": local_count,
    }


def check_transaction_journals(root: Path, report: Report) -> None:
    turn_journals = list((root / "saves").glob("**/_transactions/*.json"))
    inventory_journals = list((root / "state" / "inventory" / "_transactions").glob("*.json"))
    pending = 0
    rolled_back = 0
    for path in sorted(turn_journals):
        data = load_json(path, report, "transaction_journal_invalid")
        if not isinstance(data, dict) or data.get("schema") != "machadan-turn-transaction-v1":
            report.error("transaction_journal_invalid", "unsupported turn transaction journal", path)
            continue
        state = data.get("state")
        if state == "pending":
            pending += 1
            report.error(
                "transaction_pending",
                "save/inventory transaction is pending; retry the exact commit-turn command and transaction-id",
                path,
            )
        elif state == "rolled_back":
            rolled_back += 1
            report.warning("transaction_rolled_back", "a turn transaction was rolled back", path)
        elif state != "committed":
            report.error("transaction_journal_invalid", f"unknown journal state {state!r}", path)
    inventory_pending = 0
    inventory_rolled_back = 0
    digest_pattern = re.compile(r"[0-9a-f]{64}")
    for path in sorted(inventory_journals):
        data = load_json(path, report, "transaction_journal_invalid")
        if not isinstance(data, dict) or data.get("schema") != "machadan-inventory-append-transaction-v1":
            report.error(
                "transaction_journal_invalid", "unsupported inventory append journal", path
            )
            continue
        invalid_fields: list[str] = []
        run_id = data.get("run_id")
        if not isinstance(run_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id) is None:
            invalid_fields.append("run_id")
        if not isinstance(data.get("payload_hash"), str) or digest_pattern.fullmatch(data["payload_hash"]) is None:
            invalid_fields.append("payload_hash")
        if not isinstance(data.get("max_entries"), int) or not 1 <= data["max_entries"] <= 8:
            invalid_fields.append("max_entries")
        for hash_group in ("before_hashes", "target_hashes"):
            hashes = data.get(hash_group)
            if not isinstance(hashes, dict) or any(
                not isinstance(hashes.get(kind), str)
                or digest_pattern.fullmatch(hashes[kind]) is None
                for kind in ("mobs", "events")
            ):
                invalid_fields.append(hash_group)
        if invalid_fields:
            report.error(
                "transaction_journal_invalid",
                "invalid inventory append journal fields: " + ", ".join(invalid_fields),
                path,
            )
            continue
        state = data.get("state")
        if state == "pending":
            pending += 1
            inventory_pending += 1
            input_path = data.get("input_path")
            retry = (
                f"retry inventory-append --input {input_path} --max {data['max_entries']} "
                f"with the unchanged payload/run_id {run_id}"
            )
            report.error("inventory_append_pending", retry, path)
        elif state == "rolled_back":
            rolled_back += 1
            inventory_rolled_back += 1
            report.warning(
                "transaction_rolled_back",
                f"inventory append {run_id} was rolled back; the same payload may be retried",
                path,
            )
        elif state != "committed":
            report.error("transaction_journal_invalid", f"unknown journal state {state!r}", path)
    report.checks["transaction_journals"] = {
        "total": len(turn_journals) + len(inventory_journals),
        "turn_total": len(turn_journals),
        "inventory_total": len(inventory_journals),
        "pending": pending,
        "inventory_pending": inventory_pending,
        "rolled_back": rolled_back,
        "inventory_rolled_back": inventory_rolled_back,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=os.environ.get("MACHADAN_ROOT", str(DEFAULT_ROOT)),
        help="Muse runtime root (default: MACHADAN_ROOT or this tool's parent)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="also validate distribution hygiene, skills, generated views, Python and dice",
    )
    parser.add_argument(
        "--anchors", action="store_true",
        help="compare anchors.json with a full deterministic rebuild",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="build-stage deterministic fixes only; signed installed runtimes refuse rewrites",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--turn", action="store_true",
                        help="read-only checks for the current save and prepared context only")
    parser.add_argument("--save", type=Path,
                        help="current committed save required with --turn")
    parser.add_argument("--receipt", type=Path,
                        help="prepare-context .receipt.json required with --turn")
    return parser.parse_args(argv)


def check_skill_reading_contracts(root: Path, report: Report) -> None:
    skill_root = find_skill_root(root)
    if skill_root is None:
        return  # reported by the ordinary skill inventory check
    contracts = [
        ("machadan-gm", "references/runtime-contract.md"),
        ("machadan-gm", "references/widget-flow.md"),
        ("machadan-gm", "references/allocation-flow.md"),
        ("machadan-gm", "references/canonical-recheck.md"),
        ("machadan-gm", "../machadan-doctor/SKILL.md"),
        ("machadan-doctor", "references/repair-policy.md"),
        ("machadan-doctor", "../machadan-gm/references/canonical-recheck.md"),
    ]
    checked = []
    for skill, target in contracts:
        source = skill_root / skill / "SKILL.md"
        if not source.is_file():
            report.error("skill_read_contract", "skill body is missing", source)
            continue
        text = source.read_text(encoding="utf-8")
        pattern = re.escape("`" + target + "`") + r"\s*(?:を|も)(?:全文)?読む"
        if not re.search(pattern, text):
            report.error("skill_read_contract", f"explicit reading instruction is missing: {target}", source)
            continue
        resolved = resolve_doc_reference(root, source.parent, target)
        if resolved is None or not resolved.is_file() or not resolved.read_text(encoding="utf-8").strip():
            report.error("skill_read_contract", f"reading target is missing or empty: {target}", source)
            continue
        checked.append({"skill": skill, "reference": target})
    report.checks["skill_reading_contracts"] = {"skills": 2, "required_links": len(contracts),
                                                "verified_links": len(checked), "links": checked}


def check_context_routes(root: Path, report: Report) -> None:
    tool = root / "tools/check_context_routes.py"
    try:
        result = subprocess.run([sys.executable, str(tool), "--root", str(root)],
                                text=True, capture_output=True,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        data = json.loads(result.stdout)
        if result.returncode or data.get("ok") is not True or data.get("scenes") != len(REQUIRED_SCENES):
            report.error("context_routes", str(data), tool)
        else:
            report.checks["context_routes"] = data
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report.error("context_routes", f"context smoke check failed: {exc}", tool)


def check_runtime_workflows(root: Path, report: Report) -> None:
    """Installation-only regression checks; never used by --turn."""
    cases = {}
    for script in ("check_turn_flow.py", "check_inventory_lifecycle.py", "check_turn_checks.py", "check_onboarding.py", "check_fire_identity.py", "check_allocation_widget.py", "check_encumbrance.py", "check_resource_math.py", "check_debt_contracts.py", "check_appearance_customization.py", "check_place_atlas.py", "check_regional_world.py", "check_dungeon_exploration.py", "check_balance_data.py", "check_response_contract.py", "check_movement_events.py"):
        tool = root / "tools" / script
        try:
            result = subprocess.run([sys.executable, "-B", str(tool), "--root", str(root)],
                                    text=True, capture_output=True,
                                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                data = {"ok": False, "error": ((result.stdout or "") + (result.stderr or ""))[-2200:]}
            if result.returncode or data.get("ok") is not True:
                report.error("workflow_regression", str(data), tool)
            else:
                cases[script] = data.get("cases", 0)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            report.error("workflow_regression", str(exc), tool)
    report.checks["runtime_workflows"] = cases


def place_atlas_module(root: Path):
    specification = importlib.util.spec_from_file_location("machadan_checked_place_atlas", root / "tools/place_atlas.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def check_place_atlas(root: Path, report: Report) -> None:
    path = root / "世界/舞台構造.json"
    data = load_json(path, report, "place_atlas")
    if data is None:
        return
    try:
        module = place_atlas_module(root)
        errors = module.validate(data)
        for error in errors:
            report.error("place_atlas_graph", error, path)
        if errors:
            return
        book = root / "世界/舞台資料集.md"
        if not book.is_file() or book.read_text(encoding="utf-8") != module.renderer(data):
            report.error("place_atlas_book", "browsable stage book differs from the canonical atlas; regenerate it", book)
        report.checks["place_atlas"] = {"places": len(data["places"]),
            "rooms": sum(len(place["rooms"]) for place in data["places"]),
            "connections": sum(len(place["connections"]) for place in data["places"]),
            "book_matches": not any(issue.code == "place_atlas_book" for issue in report.issues)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report.error("place_atlas", str(exc), path)


def regional_world_module(root: Path):
    specification = importlib.util.spec_from_file_location("machadan_checked_regional_world", root / "tools/regional_world.py")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def check_regional_world(root: Path, report: Report) -> None:
    path = root / "世界/地方世界設定.json"
    data = load_json(path, report, "regional_world")
    if data is None:
        return
    try:
        module = regional_world_module(root)
        atlas = place_atlas_module(root).load(root / "世界/舞台構造.json")
        errors = module.validate(data, atlas)
        for error in errors:
            report.error("regional_world_setting", error, path)
        if errors:
            return
        book = root / module.BOOK_PATH
        if not book.is_file() or book.read_text(encoding="utf-8") != module.renderer(data):
            report.error("regional_world_book", "regional book differs from the canonical setting; regenerate it", book)
        routes = load_yaml(root / ROUTES_REL, report, "regional_personas")
        people = routes.get("persona_files", {}) if isinstance(routes, dict) else {}
        for value in data.get("city_personas", {}).values():
            for person in ([value] if isinstance(value, str) else value):
                if person not in people:
                    report.error("regional_world_persona", "regional ruler lacks a registered persona: " + person, path)
        report.checks["regional_world"] = {"cities":len(data["cities"]),"routes":len(data.get("routes",[])),
            "book_matches":not any(issue.code == "regional_world_book" for issue in report.issues)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report.error("regional_world", str(exc), path)


def check_turn(root: Path, args: argparse.Namespace, report: Report) -> None:
    """Check a prepared turn without rebuilding unrelated scenes or touching state.

    The manifest is bound to the committed save, control files and executable
    helpers are hashed, and every selected document is checked against that
    manifest.  Context bodies are compared with their declared source sections.
    This is deliberately not a replacement for installation's complete doctor.
    """
    report.checks["mode"] = "turn"
    if args.fix or args.strict or args.anchors:
        report.error("turn_options", "--turn cannot be combined with --fix/--strict/--anchors")
        return
    if args.save is None or args.receipt is None:
        report.error("turn_options", "--turn requires --save and --receipt")
        return
    save_path = args.save.expanduser().resolve()
    receipt_path = args.receipt.expanduser().resolve()
    if not receipt_path.name.endswith(".receipt.json"):
        report.error("turn_receipt", "expected prepare-context's .receipt.json", receipt_path)
        return
    context_path = receipt_path.with_name(receipt_path.name[:-len(".receipt.json")])
    check_bundled_yaml(report)
    manifest_path = find_manifest(root)
    if manifest_path is None:
        report.error("turn_manifest", "installed runtime manifest is missing", root.parent)
        return
    manifest = load_json(manifest_path, report, "turn_manifest")
    save = load_yaml(save_path, report, "turn_save")
    receipt = load_json(receipt_path, report, "turn_receipt")
    if not isinstance(manifest, dict) or not isinstance(save, dict) or not isinstance(receipt, dict):
        report.error("turn_structure", "manifest, save and receipt must be mappings")
        return
    if (manifest.get("schema") != "machadan-runtime-manifest-v1"
            or manifest.get("base") != "machadan_spade"
            or not isinstance(manifest.get("version"), str) or not manifest.get("version")
            or not isinstance(manifest.get("files"), list)):
        report.error("turn_manifest", "unsupported runtime manifest", manifest_path)
        return
    if save.get("content_manifest_hash") != sha256_path(manifest_path):
        report.error("turn_manifest", "save belongs to a different runtime; migrate it before preparing a turn", save_path)
    if save.get("game_version") != manifest.get("version"):
        report.error("turn_manifest", "save and installed version differ; migrate the save", save_path)
    rows: dict[str, dict] = {}
    digest_re = re.compile(r"[0-9a-f]{64}")
    for entry in manifest["files"]:
        rel = entry.get("path") if isinstance(entry, dict) else None
        if (not isinstance(rel, str) or not rel or Path(rel).is_absolute()
                or "\\" in rel or any(p in {"", ".", ".."} for p in Path(rel).parts)
                or rel in rows or not isinstance(entry.get("size"), int)
                or isinstance(entry.get("size"), bool) or entry["size"] < 0
                or not isinstance(entry.get("sha256"), str)
                or digest_re.fullmatch(entry["sha256"]) is None):
            report.error("turn_manifest", "invalid or duplicate manifest row", manifest_path)
            continue
        rows[rel] = entry
    if report.errors:
        return
    version_file = root.parent / "VERSION.txt"
    version_row = rows.get("VERSION.txt")
    if (version_row is None or not version_file.is_file() or version_file.is_symlink()
            or version_file.stat().st_size != version_row["size"]
            or sha256_path(version_file) != version_row["sha256"]):
        report.error("turn_manifest", "installed version file differs from the manifest", version_file)
        return
    verified: dict[str, str] = {}

    def verify_file(relative: str) -> str | None:
        """Hash only executable/control/selected inputs, with no mtime cache."""
        packaged = "muse版/" + relative
        entry = rows.get(packaged)
        path = root / relative
        if entry is None:
            report.error("turn_source_unlisted", "selected immutable input is not in the manifest", path)
            return None
        if relative in verified:
            return verified[relative]
        if (not path.is_file() or path.is_symlink()
                or not path.resolve().is_relative_to(root)
                or path.stat().st_size != entry["size"]):
            report.error("turn_source_changed", "selected immutable input is missing or changed", path)
            return None
        digest = sha256_path(path)
        if digest != entry["sha256"]:
            report.error("turn_source_changed", "selected immutable input hash differs from the manifest", path)
            return None
        verified[relative] = digest
        return digest

    # The save validator and source projection execute these helpers.  Hashing
    # them is inexpensive and avoids executing an unchecked validator/module.
    critical = {REGISTRY_REL.as_posix(), ROUTES_REL.as_posix(), ANCHORS_REL.as_posix()}
    for packaged in rows:
        if packaged.startswith("muse版/"):
            relative = packaged[len("muse版/"):]
            if (relative.startswith("tools/") and relative.endswith(".py")
                    or relative.startswith("schemas/") and relative.endswith(".json")
                    or relative == "tools/dice_tape.json"):
                critical.add(relative)
    for relative in sorted(critical):
        verify_file(relative)
    if report.errors:
        return
    registry = load_yaml(root / REGISTRY_REL, report, "turn_registry")
    routes = load_yaml(root / ROUTES_REL, report, "turn_routes")
    anchors = load_json(root / ANCHORS_REL, report, "turn_anchors")
    if not all(isinstance(v, dict) for v in (registry, routes, anchors)):
        report.error("turn_controls", "control files must be mappings")
        return
    resources = registry.get("resources", {})
    if not isinstance(resources, dict):
        report.error("turn_registry", "resource table is invalid", root / REGISTRY_REL)
        return
    if receipt.get("schema") != "machadan-context-receipt-v1":
        report.error("turn_receipt", "unsupported context receipt schema", receipt_path)
    primary_scene = receipt.get("primary_scene", receipt.get("scene"))
    included_scenes = receipt.get("included_scenes", [])
    effective_conditions = receipt.get("conditions", [])
    view_subjects = receipt.get("view_subjects", [])
    if (not isinstance(primary_scene, str) or not primary_scene
            or not isinstance(included_scenes, list)
            or not all(isinstance(s, str) and s for s in included_scenes)
            or not isinstance(effective_conditions, list)
            or not all(isinstance(s, str) and s for s in effective_conditions)
            or not isinstance(view_subjects, list)
            or not all(isinstance(s, str) and s for s in view_subjects)):
        report.error("turn_receipt", "scene and condition fields are invalid", receipt_path)
        return
    controls = receipt.get("control")
    if not isinstance(controls, list):
        report.error("turn_receipt", "control fingerprints are missing", receipt_path)
        controls = []
    control_map = {row.get("source"): row.get("sha256") for row in controls
                   if isinstance(row, dict) and isinstance(row.get("source"), str)}
    for relative in (REGISTRY_REL.as_posix(), ROUTES_REL.as_posix(), ANCHORS_REL.as_posix()):
        if control_map.get(relative) != verified.get(relative):
            report.error("turn_controls", "context was prepared with different control files", relative)
    if (receipt.get("save_sha256") != sha256_path(save_path)
            or receipt.get("save_revision") != save.get("save_revision")):
        report.error("turn_save_changed", "save changed after context preparation; prepare the turn again", save_path)
    if not context_path.is_file() or receipt.get("context_sha256") != sha256_path(context_path):
        report.error("turn_context_changed", "prepared context is missing or its hash differs", context_path)
        return
    context = context_path.read_text(encoding="utf-8")
    markers = list(re.finditer(r"(?m)^### SOURCE: (.+)\n\n", context))
    blocks: dict[str, str] = {}
    for i, marker in enumerate(markers):
        label = marker.group(1)
        if label in blocks:
            report.error("turn_context_changed", "duplicate source block in context", label)
        blocks[label] = context[marker.end():markers[i + 1].start() if i + 1 < len(markers) else len(context)].rstrip()
    selected = receipt.get("sources")
    if not isinstance(selected, list) or not selected:
        report.error("turn_receipt", "selected sources are missing", receipt_path)
        return
    selected_by_resource: dict[str, list[dict]] = {}
    active_save_rows = 0
    place_atlas_rows = 0
    regional_world_rows = 0
    selected_labels: set[str] = set()
    source_keys: set[str] = set()
    for row in selected:
        if (not isinstance(row, dict) or not isinstance(row.get("source"), str)
                or not isinstance(row.get("resource"), str)
                or not isinstance(row.get("file_sha256"), str)
                or digest_re.fullmatch(row["file_sha256"]) is None):
            report.error("turn_receipt", "invalid selected source row", receipt_path)
            continue
        if row["source"] in source_keys:
            report.error("turn_receipt", "duplicate selected source row", row["source"])
        source_keys.add(row["source"])
        resource_id = row.get("resource")
        selected_by_resource.setdefault(str(resource_id), []).append(row)
        if resource_id == "ACTIVE_SAVE":
            active_save_rows += 1
            if (Path(row["source"]).expanduser().resolve() != save_path
                    or row.get("file_sha256") != receipt.get("save_sha256")
                    or row.get("mode") != "view"):
                report.error("turn_save_changed", "active save source does not match the committed save", save_path)
            labels = [label for label in blocks if label.startswith("ACTIVE_SAVE_VIEW")]
            if len(labels) != 1:
                report.error("turn_context_changed", "active save view is missing or duplicated", context_path)
            else:
                selected_labels.add(labels[0])
                body = blocks[labels[0]]
                if not body.startswith("~~~yaml\n") or not body.endswith("\n~~~"):
                    report.error("turn_context_changed", "active save view has an invalid wrapper", context_path)
                else:
                    try:
                        view = yaml.safe_load(body[len("~~~yaml\n"):-len("\n~~~")])
                        spec = importlib.util.spec_from_file_location("machadan_turn_save_view", root / "tools/save_changes.py")
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        scenes = [primary_scene, *included_scenes]
                        expected_view, _ = module.state_view(save, scenes, subjects=view_subjects)
                        if view != expected_view:
                            report.error("turn_context_changed", "active save view differs from the committed save", context_path)
                    except (ValueError, TypeError, yaml.YAMLError) as exc:
                        report.error("turn_context_changed", f"invalid active save view: {exc}", context_path)
            continue
        source, _, _anchor_id = row["source"].partition("#")
        rel_path = Path(source)
        if (rel_path.is_absolute() or "\\" in source
                or any(part in {"", ".", ".."} for part in rel_path.parts)):
            report.error("turn_source_path", "selected source must be relative to the runtime", source)
            continue
        resource = resources.get(resource_id)
        if resource_id == "PERSONA" and not source.startswith("人格/"):
            report.error("turn_source_path", "persona source must belong to the persona directory", source)
            continue
        if resource_id != "PERSONA" and (not isinstance(resource, dict) or resource.get("path") != source):
            report.error("turn_source_path", "resource and selected source path differ", source)
            continue
        path = root / rel_path
        mutable = isinstance(resource, dict) and resource.get("role") == "mutable_state"
        if mutable:
            digest = sha256_path(path) if path.is_file() and path.resolve().is_relative_to(root) else None
        else:
            digest = verify_file(source)
        if digest is None or digest != row.get("file_sha256"):
            report.error("turn_source_changed", "source changed after context preparation", source)
            continue
        label = row["source"]
        selected_labels.add(label)
        body = blocks.get(label)
        if body is None:
            report.error("turn_context_changed", "selected source body is missing", label)
            continue
        if resource_id == "PLACE_ATLAS":
            place_atlas_rows += 1
            request = receipt.get("place_request")
            valid_request = (isinstance(request, dict) and set(request) == {"locations", "rooms", "saved_place_id", "source_place_id", "source_location", "dungeon_interior"}
                and all(isinstance(request.get(key), list) and all(isinstance(value, str) and value.strip() for value in request[key]) for key in ("locations", "rooms"))
                and (request.get("saved_place_id") is None or isinstance(request.get("saved_place_id"), str))
                and all(request.get(key) is None or isinstance(request.get(key), str) for key in ("source_place_id", "source_location"))
                and isinstance(request.get("dungeon_interior"), bool))
            if not valid_request or row.get("mode") != "place_view" or label != "世界/舞台構造.json#PLACE_ATLAS_VIEW":
                report.error("turn_place_atlas", "place atlas request or projection mode is invalid", label)
                continue
            try:
                module = place_atlas_module(root)
                atlas = module.load(path)
                expected = module.render_view(module.project(atlas, request))
                if hashlib.sha256(expected.encode()).hexdigest() != row.get("sha256") or body != expected.rstrip():
                    report.error("turn_context_changed", "place projection differs from its canonical source and declared target", label)
                if request.get("saved_place_id") is not None and request["saved_place_id"] != save.get("world_state", {}).get("place_id"):
                    report.error("turn_place_atlas", "saved place id differs from the committed save", label)
                for request_key, save_key in (("source_place_id", "place_id"), ("source_location", "location")):
                    if request.get(request_key) != save.get("world_state", {}).get(save_key):
                        report.error("turn_place_atlas", "source location context differs from the committed save", label)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                report.error("turn_place_atlas", str(exc), label)
        elif resource_id == "REGIONAL_WORLD":
            regional_world_rows += 1
            request = receipt.get("regional_request")
            valid_request = (isinstance(request,dict) and set(request) in ({"day","city_ids","topics"},{"day","city_ids","topics","reference_city_ids"})
                and isinstance(request.get("day"),int) and not isinstance(request.get("day"),bool) and request["day"]>=1
                and all(isinstance(request.get(key),list) and all(isinstance(v,str) for v in request[key]) for key in ("city_ids","topics"))
                and ("reference_city_ids" not in request or isinstance(request["reference_city_ids"],list)
                     and bool(request["reference_city_ids"]) and all(isinstance(v,str) for v in request["reference_city_ids"])))
            if not valid_request or row.get("mode")!="regional_view" or label!="世界/地方世界設定.json#REGIONAL_WORLD_VIEW":
                report.error("turn_regional_world", "regional request or projection mode is invalid", label)
                continue
            try:
                module = regional_world_module(root)
                data = module.load(path)
                atlas_module = place_atlas_module(root)
                atlas = atlas_module.load(root / "世界/舞台構造.json")
                places = atlas_module.project(atlas, receipt.get("place_request", {}))
                expected_request = module.request_from(SimpleNamespace(world_topic=request["topics"],world_city=request.get("reference_city_ids")),save,places,atlas,data)
                if request != expected_request:
                    report.error("turn_regional_world", "regional date or selected cities differ from the current save and place request", label)
                expected = module.render_view(module.project(data, expected_request))
                if hashlib.sha256(expected.encode()).hexdigest()!=row.get("sha256") or body!=expected.rstrip():
                    report.error("turn_context_changed", "regional projection differs from its declared canonical setting", label)
            except (OSError,ValueError,TypeError,KeyError) as exc:
                report.error("turn_regional_world", str(exc), label)
        elif row.get("mode") in {"full", "section"}:
            text = path.read_text(encoding="utf-8")
            if row.get("mode") == "section":
                start, end = row.get("start"), row.get("end")
                lines = text.splitlines()
                if (not isinstance(start, int) or isinstance(start, bool)
                        or not isinstance(end, int) or isinstance(end, bool)
                        or not 1 <= start <= end <= len(lines)):
                    report.error("turn_context_changed", "selected section bounds are invalid", label)
                    continue
                text = "\n".join(lines[start - 1:end])
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != row.get("sha256") or body != text.rstrip():
                report.error("turn_context_changed", "context body differs from its declared source section", label)
        elif mutable and row.get("mode") == "view":
            projected = load_yaml(path, report, "turn_inventory")
            try:
                shown = yaml.safe_load(body)
                originals = {item.get("id"): item for item in projected.get("entries", []) if isinstance(item, dict)}
                entries = shown.get("entries") if isinstance(shown, dict) else None
                if (not isinstance(entries, list) or shown.get("schema") != projected.get("schema")
                        or shown.get("kind") != projected.get("kind")
                        or any(not isinstance(item, dict) or originals.get(item.get("id")) != item for item in entries)):
                    report.error("turn_context_changed", "inventory view differs from stored entries", label)
            except (AttributeError, TypeError, yaml.YAMLError) as exc:
                report.error("turn_context_changed", f"invalid inventory view: {exc}", label)
        else:
            report.error("turn_receipt", "unsupported source view mode", label)
    if active_save_rows != 1:
        report.error("turn_save_changed", "exactly one committed save source is required", receipt_path)
    if "PLACE_ATLAS" in resources and place_atlas_rows != 1:
        report.error("turn_place_atlas", "exactly one targeted place atlas projection is required", receipt_path)
    if "REGIONAL_WORLD" in resources and regional_world_rows != 1:
        report.error("turn_regional_world", "exactly one targeted regional projection is required", receipt_path)
    if set(blocks) != selected_labels:
        report.error("turn_context_changed", "context source blocks and receipt differ", context_path)
    if report.errors:
        return
    scenes = [primary_scene, *included_scenes]
    packs = routes.get("scene_packs", {})
    required = list(routes.get("base_pack", {}).get("required", []))
    required += list(routes.get("base_pack", {}).get("verify_after_turn", []))
    conditions = set(effective_conditions)
    for scene in scenes:
        if scene not in packs:
            report.error("turn_receipt", "unknown scene in receipt", str(scene))
            continue
        pack = packs[scene]
        required += pack.get("required", [])
        for group in ("conditional", "after"):
            for item in pack.get(group, []):
                if item.get("when") in conditions:
                    required += [{**item, "resource": rid} for rid in
                                 ([item["resource"]] if item.get("resource") else []) + item.get("resources", [])]
    for condition in conditions:
        required += routes.get("global_conditions", {}).get(condition, [])
    for item in required:
        rid = item.get("resource")
        if rid and (item.get("mode") == "full" or item.get("selectors")) and rid not in selected_by_resource:
            report.error("turn_required_source", "required resource is missing from the prepared context", rid)
    style_rows = selected_by_resource.get("STYLE_CARD", [])
    full_style = any(row.get("mode") == "full" for row in style_rows)
    if not full_style:
        for item in routes.get("base_pack", {}).get("required", []):
            if item.get("resource") != "STYLE_CARD":
                continue
            for selector in item.get("selectors", []):
                relative = resources["STYLE_CARD"]["path"]
                anchor, reason = anchor_for_selector(root, anchors, relative, selector)
                if anchor is None or not any(row.get("mode") == "section"
                        and row.get("start", 10**9) <= anchor["start"]
                        and row.get("end", -1) >= anchor["end"] for row in style_rows):
                    report.error("turn_style", "a required common prose section is missing: " + str(selector.get("match") or reason))
    if receipt.get("ero_scene") is True:
        for rid in ("STYLE_CARD", "INTIMATE_RULES", "STYLE_DICTIONARY"):
            if not any(row.get("mode") == "full" for row in selected_by_resource.get(rid, [])):
                report.error("turn_style", "dedicated prose scene requires the complete source", rid)
    if report.errors:
        return
    runtime_validate_save(root, save_path, report, "turn_save_invalid")
    # Historical committed/rolled-back journals are not revalidated every turn;
    # unresolved operations affecting this save or shared stock still block use.
    journal_total = pending = 0
    journal_paths = [(path, False) for path in (save_path.parent / "_transactions").glob("*.json")]
    journal_paths += [(path, True) for path in (root / "state/inventory/_transactions").glob("*.json")]
    for path, inventory in journal_paths:
        data = load_json(path, report, "turn_transaction")
        if not isinstance(data, dict):
            report.error("turn_transaction", "transaction journal must be a mapping", path)
            continue
        if not inventory:
            current = data.get("current_path")
            if isinstance(current, str) and Path(current).expanduser().resolve() != save_path:
                continue
            if current is None and data.get("campaign_id") != save.get("campaign_id"):
                continue
        journal_total += 1
        if data.get("state") == "pending":
            pending += 1
            report.error("turn_transaction_pending", "retry the recorded unchanged transaction before continuing", path)
        elif data.get("state") not in {"committed", "rolled_back"}:
            report.error("turn_transaction", "transaction journal has an invalid state", path)
    report.checks["turn"] = {"selected_sources": len(selected), "immutable_inputs_verified": len(verified),
                             "save_revision": save.get("save_revision"), "scenes": scenes,
                             "context_characters": len(context), "relevant_journals": journal_total,
                             "pending": pending, "read_only": True}


def run(args: argparse.Namespace) -> Report:
    root = Path(args.root).expanduser().resolve()
    report = Report(root, args.strict)
    if not root.is_dir():
        report.error("root_missing", "runtime root is not a directory", root)
        return report
    if args.turn:
        check_turn(root, args, report)
        return report
    if args.save is not None or args.receipt is not None:
        report.error("turn_options", "--save/--receipt are only used with --turn")
        return report
    effective_fix = bool(args.fix)
    signed_manifest = find_manifest(root)
    if effective_fix and signed_manifest is not None:
        report.error(
            "fix_signed_runtime",
            "refusing to rewrite a signed runtime; restore immutable files by rerunning "
            "the verified package setup (saves/state are preserved)",
            signed_manifest,
        )
        effective_fix = False
    check_bundled_yaml(report)
    registry, resources = check_registry(root, report)
    check_decisions(root, registry, resources, report)
    if effective_fix and resources:
        initialise_inventories(root, resources, report)
        # Recheck newly created state; registry errors already de-duplicate.
        for resource_id, item in resources.items():
            if isinstance(item, dict) and item.get("role") == "mutable_state":
                path = root / str(item.get("path", ""))
                if path.is_file():
                    inventory_state_check(
                        path, "mobs" if "mob" in resource_id.casefold() else "events", report)
        still_missing = [
            resource_id for resource_id, item in resources.items()
            if (isinstance(item, dict) and item.get("role") == "mutable_state" and
                not (root / str(item.get("path", ""))).is_file())
        ]
        if still_missing:
            report.checks["deferred_mutable_state"] = still_missing
        else:
            report.checks.pop("deferred_mutable_state", None)
    index = check_anchors(root, report, args.anchors, effective_fix)
    routes = check_routes(root, resources, index, report)
    check_sentinels(root, index, report)
    check_schemas(root, report)
    check_place_atlas(root, report)
    if "REGIONAL_WORLD" in resources:
        check_regional_world(root, report)
    check_manifest(root, report)
    check_transaction_journals(root, report)
    if args.strict:
        check_references_and_legacy(root, registry, resources, routes, report)
        check_skill_reading_contracts(root, report)
        check_python_and_dice(root, report)
        check_context_routes(root, report)
        check_runtime_workflows(root, report)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run(args)
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        root = Path(args.root).expanduser().resolve()
        report = Report(root, args.strict)
        report.error("doctor_crash", str(exc))
    payload = report.payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        prefix = "OK" if payload["ok"] else "NG"
        summary = payload["summary"]
        print(f"{prefix}: {summary['errors']} error(s), {summary['warnings']} warning(s), "
              f"{summary['fixes']} fix(es)")
        for issue in report.issues:
            location = f" {issue.path}:" if issue.path else ""
            print(f" - {issue.severity.upper()} [{issue.code}]{location} {issue.message}")
        for fix in report.fixes:
            print(f" - FIXED: {fix}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
