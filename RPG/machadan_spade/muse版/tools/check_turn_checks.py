#!/usr/bin/env python3
"""Exercise turn verification in a disposable runtime, never in a live save."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(source: Path, timing_full: bool = False) -> dict:
    sys.path.insert(0, str(source / "tools/_vendor"))
    import yaml

    cases: list[str] = []
    with tempfile.TemporaryDirectory(prefix="machadan-turn-check-") as temporary:
        temporary = Path(temporary)
        game = temporary / "machadan_spade"
        root = game / "muse版"
        shutil.copytree(source, root, ignore=shutil.ignore_patterns("saves", "state", "runtime", "__pycache__", "*.pyc"))
        shutil.copy2(source.parent / "VERSION.txt", game / "VERSION.txt")
        original_manifest = json.loads((source.parent / "RUNTIME_MANIFEST.json").read_text())
        current_version = re.search(r"(?im)^version:\s*(\S.*)$", (game / "VERSION.txt").read_text())
        if current_version:
            original_manifest["version"] = current_version.group(1).strip()
        # This is a private fixture manifest.  Live/package manifests are never
        # rewritten to hide damage.  Include the files actually under test.
        original_manifest["files"] = [
            {"path": path.relative_to(game).as_posix(), "size": path.stat().st_size, "sha256": digest(path)}
            for path in sorted(game.rglob("*")) if path.is_file()
        ]
        (game / "RUNTIME_MANIFEST.json").write_text(json.dumps(original_manifest, ensure_ascii=False, indent=2) + "\n")
        tool = root / "tools/machadan_runtime.py"
        doctor = root / "tools/check_knowledge.py"
        env = {**os.environ, "MACHADAN_ROOT": str(root), "PYTHONDONTWRITEBYTECODE": "1"}

        def run(command: list, expected: bool = True, code: str | None = None) -> tuple[dict, float]:
            started = time.perf_counter()
            process = subprocess.run([sys.executable, "-B", *map(str, command)], text=True,
                                     capture_output=True, env=env)
            elapsed = time.perf_counter() - started
            try:
                result = json.loads(process.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"non-JSON test response: {process.stderr[-1200:]}") from exc
            if (process.returncode == 0) != expected or result.get("ok") != expected:
                raise RuntimeError(f"unexpected test result: {result}")
            if code and not any(row.get("code") == code for row in result.get("errors", [])):
                raise RuntimeError(f"expected error {code}: {result}")
            return result, elapsed

        save = root / "saves/turn-probe.yaml"
        context = root / "state/runtime/turn-probe/context.md"
        receipt = context.with_suffix(".md.receipt.json")
        run([tool, "new-save", "--campaign-id", "turn-probe", "--output", save])
        run([tool, "prepare-context", "--save", save, "--scene", "turn", "--output", context])
        command = [doctor, "--root", root, "--turn", "--save", save, "--receipt", receipt, "--json"]
        before = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}
        healthy, elapsed = run(command)
        after = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}
        if before != after or list(root.rglob("*.pyc")):
            raise RuntimeError("turn verifier modified the runtime or left bytecode")
        if "context_routes" in healthy.get("checks", {}):
            raise RuntimeError("turn verifier unexpectedly ran the full scene suite")
        cases += ["healthy_read_only", "no_full_scene_rebuild"]
        receipt_bytes, context_bytes, save_bytes = receipt.read_bytes(), context.read_bytes(), save.read_bytes()
        rows = json.loads(receipt_bytes)["sources"]
        source_row = next(row for row in rows if row["resource"] == "TURN_CONTRACT")
        selected_file = root / source_row["source"].partition("#")[0]
        selected_bytes = selected_file.read_bytes()
        selected_file.write_bytes(selected_bytes + b"\n")
        run(command, False, "turn_source_changed")
        selected_file.write_bytes(selected_bytes)
        cases.append("changed_selected_canonical")
        data = json.loads(receipt_bytes)
        data["save_revision"] += 1
        receipt.write_text(json.dumps(data))
        run(command, False, "turn_save_changed")
        receipt.write_bytes(receipt_bytes)
        cases.append("stale_save_revision")
        context.write_bytes(context_bytes + b"changed context")
        run(command, False, "turn_context_changed")
        context.write_bytes(context_bytes)
        cases.append("changed_context")
        # Even if someone updates the receipt hash, source text must still match.
        changed = context_bytes.decode().replace("### SOURCE: " + source_row["source"] + "\n\n",
                                                 "### SOURCE: " + source_row["source"] + "\n\nchanged source\n", 1)
        context.write_text(changed)
        data = json.loads(receipt_bytes)
        data["context_sha256"] = digest(context)
        receipt.write_text(json.dumps(data))
        run(command, False, "turn_context_changed")
        context.write_bytes(context_bytes)
        receipt.write_bytes(receipt_bytes)
        cases.append("changed_body_with_rehashed_receipt")
        # Removing just one common style section leaves the resource present;
        # per-section coverage, rather than a resource-name check, must catch it.
        data = json.loads(receipt_bytes)
        style_row = next(row for row in data["sources"] if row["resource"] == "STYLE_CARD" and row["mode"] == "section")
        data["sources"].remove(style_row)
        text = context_bytes.decode()
        pattern = re.compile(r"(?ms)^### SOURCE: " + re.escape(style_row["source"]) + r"\n\n.*?(?=^### SOURCE: |\Z)")
        changed, number = pattern.subn("", text, count=1)
        if number != 1:
            raise RuntimeError("could not locate test style section")
        context.write_text(changed)
        data["context_sha256"] = digest(context)
        receipt.write_text(json.dumps(data))
        run(command, False, "turn_style")
        context.write_bytes(context_bytes)
        receipt.write_bytes(receipt_bytes)
        cases.append("missing_common_style_section")
        journals = save.parent / "_transactions"
        journals.mkdir()
        pending = journals / "pending-probe.json"
        pending.write_text(json.dumps({"state": "pending", "current_path": str(save), "campaign_id": "turn-probe"}))
        run(command, False, "turn_transaction_pending")
        pending.unlink()
        cases.append("pending_current_transaction")
        # A pending transaction for another campaign does not stop this one.
        pending.write_text(json.dumps({"state": "pending", "current_path": str(save.with_name("other.yaml")), "campaign_id": "other"}))
        run(command)
        pending.unlink()
        cases.append("unrelated_campaign_does_not_block")
        stock_journals = root / "state/inventory/_transactions"
        stock_journals.mkdir(parents=True, exist_ok=True)
        stock_pending = stock_journals / "stock-pending.json"
        stock_pending.write_text(json.dumps({"state": "pending", "run_id": "stock-pending"}))
        run(command, False, "turn_transaction_pending")
        stock_pending.unlink()
        cases.append("pending_shared_inventory")
        save.write_bytes(save_bytes.replace(b"save_revision: 0", b"save_revision: 1", 1))
        run(command, False, "turn_save_changed")
        save.write_bytes(save_bytes)
        cases.append("changed_committed_save")
        style_context = context.with_name("dedicated.md")
        style_receipt = style_context.with_suffix(".md.receipt.json")
        run([tool, "prepare-context", "--save", save, "--scene", "style", "--output", style_context])
        run([doctor, "--root", root, "--turn", "--save", save, "--receipt", style_receipt, "--json"])
        cases.append("dedicated_style_full_sources")
        # The bounded view must preserve an old fact about a requested person,
        # even when it is elsewhere and more than eight newer facts exist.
        lore_save = yaml.safe_load(save_bytes)
        lore = {"old-harbor-person": {"npc_id": "OldHarborMerchant", "location": "別の港", "fact": "以前会った人物"}}
        lore.update({"recent-" + str(i): {"fact": "別の出来事"} for i in range(15)})
        lore_save["world_state"]["campaign_lore"] = lore
        save.write_text(yaml.safe_dump(lore_save, allow_unicode=True, sort_keys=False, width=120))
        lore_context = context.with_name("old-person.md")
        lore_receipt = lore_context.with_suffix(".md.receipt.json")
        run([tool, "prepare-context", "--save", save, "--scene", "turn", "--character", "OldHarborMerchant", "--output", lore_context])
        if "old-harbor-person" not in lore_context.read_text():
            raise RuntimeError("requested person's old fact was omitted")
        lore_command = [doctor, "--root", root, "--turn", "--save", save, "--receipt", lore_receipt, "--json"]
        run(lore_command)
        cases.append("old_requested_person_lore")
        # Omitting the projection selectors must now reveal the inconsistent
        # view, rather than accepting a different bounded projection silently.
        bad_lore_receipt = json.loads(lore_receipt.read_text())
        bad_lore_receipt["view_subjects"] = []
        lore_receipt.write_text(json.dumps(bad_lore_receipt))
        run(lore_command, False, "turn_context_changed")
        cases.append("changed_view_subjects_rejected")
        save.write_bytes(save_bytes)
        # Muse may invoke Python directly; the checker's own bootstrap must
        # suppress bytecode even if neither -B nor the environment flag is used.
        direct_env = {k: v for k, v in env.items() if k not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}}
        direct = subprocess.run([sys.executable, *map(str, command)], text=True,
                                capture_output=True, env=direct_env)
        if direct.returncode or list(root.rglob("*.pyc")):
            raise RuntimeError("bare Python checker failed or left bytecode")
        cases.append("bare_python_does_not_write_bytecode")
        result = {"ok": True, "cases": len(cases), "case_ids": cases,
                  "local_turn_check_seconds": round(elapsed, 4), "source_unchanged": True}
        if timing_full:
            skills = source.parent.parent / "workspace/skills"
            if not skills.is_dir():
                skills = source.parent.parent / "skills"
            if skills.is_dir():
                shutil.copytree(skills, temporary / "skills")
            _, full_elapsed = run([doctor, "--root", root, "--strict", "--anchors", "--json"])
            result["local_full_check_seconds"] = round(full_elapsed, 4)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--timing-full", action="store_true",
                        help="also time the full installed-runtime checks in the same private copy")
    args = parser.parse_args()
    try:
        result = check(args.root.resolve(), args.timing_full)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
