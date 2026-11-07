#!/usr/bin/env python3
"""Build a stable, content-hashed navigation index for the Muse runtime.

Markdown-looking comments inside fenced examples are not headings. Bracket
markers such as [TEMPLATE_SAVE] inside fenced templates remain addressable.
Authors may add explicit ranges with HTML comments: anchor: ID and /anchor.

Usage:
  python3 extract_anchors.py [ROOT] [--out PATH]
  python3 extract_anchors.py [ROOT] --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent
DEFAULT_OUT = HERE / "anchors.json"
TEXT_SUFFIXES = {".md", ".txt"}
EXCLUDED_PARTS = {"saves", "state", "runtime", "_history", "__pycache__", "_vendor"}
EXCLUDED_RELATIVE = {"運用/設計変更リスト.md", "クエストカード_サンプル集.md"}

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(\`\`\`+|~~~+)")
MARKER_RE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+)?\[([A-Z][A-Z0-9_-]{2,})\](?:[ \t]+(.*))?$")
EXPLICIT_START_RE = re.compile(r"^[ \t]*<!--[ \t]*anchor:[ \t]*([A-Za-z][A-Za-z0-9_.:-]*)[ \t]*-->[ \t]*$")
EXPLICIT_END_RE = re.compile(r"^[ \t]*<!--[ \t]*/anchor[ \t]*-->[ \t]*$")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_heading_id(relative_path: str, title: str, occurrence: int = 1) -> str:
    key = f"{relative_path}\0{' '.join(title.split()).casefold()}\0{occurrence}"
    return "H_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16].upper()


def iter_sources(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.as_posix() in EXCLUDED_RELATIVE:
            continue
        yield path


def _fence_map(lines: list[str]) -> tuple[list[bool], dict[int, int]]:
    in_fence = False
    fence_char = ""
    fence_len = 0
    start = 0
    inside: list[bool] = []
    ends: dict[int, int] = {}
    for line_no, line in enumerate(lines, 1):
        match = FENCE_RE.match(line)
        if not in_fence:
            inside.append(False)
            if match:
                token = match.group(1)
                in_fence = True
                fence_char, fence_len, start = token[0], len(token), line_no
        else:
            inside.append(True)
            if match and match.group(1)[0] == fence_char and len(match.group(1)) >= fence_len:
                ends[start] = line_no
                in_fence = False
                fence_char = ""
                fence_len = 0
    if in_fence:
        ends[start] = len(lines)
    return inside, ends


def extract_file(path: Path, relative_path: str) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    total = len(lines)
    inside, fence_ends = _fence_map(lines)
    anchors: list[dict] = []
    heading_counts: dict[str, int] = {}
    explicit_open: tuple[str, int] | None = None
    current_fence_start: int | None = None

    for i, line in enumerate(lines, 1):
        fence_match = FENCE_RE.match(line)
        if fence_match and not inside[i - 1]:
            current_fence_start = i
        elif fence_match and inside[i - 1]:
            current_fence_start = None

        start_match = EXPLICIT_START_RE.match(line)
        if start_match:
            if explicit_open:
                raise ValueError(f"{relative_path}:{i}: nested explicit anchor")
            explicit_open = (start_match.group(1), i)
            continue
        if EXPLICIT_END_RE.match(line):
            if not explicit_open:
                raise ValueError(f"{relative_path}:{i}: explicit anchor end without start")
            anchor_id, start = explicit_open
            anchors.append({"id": anchor_id, "type": "explicit", "level": 0,
                            "start": start + 1, "end": max(start + 1, i - 1),
                            "title": anchor_id})
            explicit_open = None
            continue

        if not inside[i - 1]:
            heading_match = HEADING_RE.match(line)
            if heading_match:
                title = heading_match.group(2).strip()
                level = len(heading_match.group(1))
                previous_blank = i == 1 or not lines[i - 2].strip()
                next_blank = i == total or not lines[i].strip()
                # The imported corpus uses single-# shell-style explanatory
                # comments outside code fences. Only a bracket section marker
                # or a standalone level-1 line is a real Markdown heading.
                if level == 1 and not title.startswith("[") and not (
                        previous_blank and next_blank):
                    continue
                marker = re.match(r"^\[([A-Z][A-Z0-9_-]{2,})\](?:\s+.*)?$", title)
                normalized_title = " ".join(title.split()).casefold()
                heading_counts[normalized_title] = heading_counts.get(normalized_title, 0) + 1
                anchors.append({
                    "id": marker.group(1) if marker else stable_heading_id(
                        relative_path, title, heading_counts[normalized_title]),
                    "type": "heading",
                    "level": level,
                    "start": i,
                    "end": total,
                    "title": title,
                })
            continue

        marker_match = MARKER_RE.match(line)
        if marker_match:
            anchors.append({
                "id": marker_match.group(1),
                "type": "marker",
                "level": 0,
                "start": i,
                "end": fence_ends.get(current_fence_start or 0, total),
                "title": f"[{marker_match.group(1)}]" + (
                    f" {marker_match.group(2)}" if marker_match.group(2) else ""),
                "block_end": fence_ends.get(current_fence_start or 0, total),
            })

    if explicit_open:
        anchor_id, start = explicit_open
        raise ValueError(f"{relative_path}:{start}: unclosed explicit anchor {anchor_id}")

    for idx, anchor in enumerate(anchors):
        if anchor["type"] == "explicit":
            continue
        if anchor["type"] == "heading":
            end = total
            for nxt in anchors[idx + 1:]:
                if nxt["start"] <= anchor["start"]:
                    continue
                if nxt["type"] == "heading" and nxt["level"] <= anchor["level"]:
                    end = nxt["start"] - 1
                    break
            anchor["end"] = max(anchor["start"], end)
        else:
            end = anchor.pop("block_end")
            for nxt in anchors[idx + 1:]:
                if nxt["start"] > end:
                    break
                if nxt["type"] == "marker":
                    end = nxt["start"] - 1
                    break
            anchor["end"] = max(anchor["start"], end)

    seen: set[str] = set()
    for anchor in anchors:
        if anchor["id"] in seen:
            raise ValueError(f"{relative_path}: duplicate anchor id {anchor['id']}")
        seen.add(anchor["id"])
        section = "\n".join(lines[anchor["start"] - 1:anchor["end"]])
        anchor["line_count"] = anchor["end"] - anchor["start"] + 1
        anchor["sha256"] = sha256_text(section)

    return {"total_lines": total, "sha256": sha256_text(text), "anchors": anchors}


def build_index(root: Path) -> dict:
    files: dict[str, dict] = {}
    id_locations: dict[str, list[str]] = {}
    for path in iter_sources(root):
        rel = path.relative_to(root).as_posix()
        info = extract_file(path, rel)
        for anchor in info["anchors"]:
            anchor_id = anchor["id"]
            anchor["qualified_id"] = f"{rel}#{anchor_id}"
            id_locations.setdefault(anchor_id, []).append(rel)
        files[rel] = info
    return {
        "schema_version": 2,
        "root": ".",
        "total_anchors": sum(len(value["anchors"]) for value in files.values()),
        "id_locations": id_locations,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=str(DEFAULT_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    try:
        data = build_index(root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"NG: {exc}", file=sys.stderr)
        return 2
    if args.check:
        if not out.exists():
            print(f"NG: anchor index is missing: {out}", file=sys.stderr)
            return 1
        try:
            saved = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"NG: cannot read anchor index: {exc}", file=sys.stderr)
            return 1
        if saved != data:
            print("NG: anchors.json is stale; run extract_anchors.py", file=sys.stderr)
            return 1
        if not args.quiet:
            print(json.dumps({"ok": True, "files": len(data["files"]),
                              "anchors": data["total_anchors"]}, ensure_ascii=False))
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(json.dumps({"ok": True, "saved": str(out), "files": len(data["files"]),
                          "anchors": data["total_anchors"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
