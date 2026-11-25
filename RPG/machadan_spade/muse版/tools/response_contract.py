"""Validate the unsent reply, separately from game state, before committing.

Only text length and action presence are checked here. Literary quality follows
the existing prose source. Neither validation nor rendering writes a campaign save.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata

SCHEMA = "machadan-response-v1"
MAX_BYTES = 262144
LIMITS = {"town": (600, 800), "travel": (650, 850), "combat": (550, 750),
          "quest": (550, 750), "intimate": (600, None), "procedure": (0, None),
          "brief": (0, None), "explanation": (0, None), "passage": (1, 850)}
PROCEDURES = {"start", "hearing", "manage", "status", "chekyun"}
SHORT_REASONS = {"player_question", "brief_acknowledgement"}
FREE_INPUT = "自由入力もできます。"


def load(api, raw_path):
    path = Path(raw_path).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise api.RuntimeProblem("response draft must be a regular JSON file of at most 256 KiB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate response key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise api.RuntimeProblem("invalid response draft: " + str(exc)) from exc


def count_main_text(text):
    """Visible Unicode characters; whitespace and Markdown syntax are excluded."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[([^\]\n]+)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|>\s?|[-+*]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"[*_`~]", "", text)
    return len(re.sub(r"\s", "", text))


def _scene(save):
    runtime = save.get("runtime_state", {})
    return runtime.get("scene_id") or runtime.get("active_scene") or "turn"


def _changed_place(before, after):
    a, b = before.get("world_state", {}), after.get("world_state", {})
    return any(a.get(key) != b.get(key) for key in ("location", "place_id", "room_id", "sub_location", "depth"))


def _allocation_confirmation(before, after):
    if before is None:
        return False
    old_state = before.get("world_state", {}).get("allocation_state") or {}
    new_state = after.get("world_state", {}).get("allocation_state") or {}
    if not isinstance(old_state, dict) or not isinstance(new_state, dict):
        return False
    old, new = old_state.get("resolutions", []), new_state.get("resolutions", [])
    return (isinstance(old, list) and isinstance(new, list) and len(new) == len(old) + 1
            and new[:-1] == old and isinstance(new[-1], dict)
            and new[-1].get("mode") in {"initial", "fruit", "respec"})


def _no_gameplay_change(before, after):
    if before is None:
        return False
    ignored = {"game_version", "content_manifest_hash", "created_at", "updated_at", "save_revision",
               "transaction", "migration_legacy", "runtime_state", "session_log", "memory_log"}
    return ({k: v for k, v in before.items() if k not in ignored} ==
            {k: v for k, v in after.items() if k not in ignored})


def profile(api, draft, save, before=None, movement=None):
    scene = _scene(save)
    requested = draft.get("prose_kind", "auto")
    if requested not in {"auto", "travel", "brief", "explanation"}:
        raise api.RuntimeProblem("response prose_kind must be auto, travel, brief or explanation")
    if save.get("runtime_state", {}).get("ero_scene") is True:
        # The dedicated scene's existing minimum cannot be bypassed by calling
        # it a short acknowledgement or procedural explanation.
        return "intimate"
    if requested in {"brief", "explanation"}:
        if (draft.get("short_reason") not in SHORT_REASONS or
                not _no_gameplay_change(before, save)):
            raise api.RuntimeProblem("short reply requires a player question/brief acknowledgement and no gameplay change")
        return requested
    if scene in PROCEDURES:
        return "procedure"
    if scene == "combat":
        return "combat"
    if (movement and not movement["occurred"] and movement["style"] != "idle"
            and movement["location_kind"] != "dungeon"):
        # A quiet walk is 2-3 lines, not a mandatory 650-character padding task.
        if draft["movement"].get("arrival_scene") is not True:
            return "passage"
        if scene != "quest":
            return "town"
    if scene == "quest":
        return "quest"
    if requested == "travel" or scene in {"travel", "dungeon"} or before is not None and _changed_place(before, save):
        return "travel"
    if _allocation_confirmation(before, save):
        return "procedure"
    return "town"


def validate(api, draft, save, before=None):
    if not isinstance(draft, dict) or draft.get("schema") != SCHEMA:
        raise api.RuntimeProblem("response draft requires schema " + SCHEMA)
    text = draft.get("main_text")
    if not isinstance(text, str) or "```" in text or "~~~" in text:
        raise api.RuntimeProblem("main_text must be a string outside code fences")
    blocks = draft.get("system_blocks", [])
    if not isinstance(blocks, list) or any(not isinstance(item, str) for item in blocks):
        raise api.RuntimeProblem("system_blocks must be strings, separate from main_text")
    from movement_events import validate as validate_movement
    movement = validate_movement(api, draft, save, before)
    kind = profile(api, draft, save, before, movement)
    count = count_main_text(text)
    minimum, maximum = LIMITS[kind]
    if count < minimum or maximum is not None and count > maximum:
        target = str(minimum) + ("以上" if maximum is None else "〜" + str(maximum))
        raise api.RuntimeProblem(f"本文字数が基準外です: {kind} {count}字（基準 {target}字）。数値表示や選択肢で埋めず本文を修正してください")
    choices = draft.get("choices", [])
    if (not isinstance(choices, list) or
            any(not isinstance(item, str) or not item.strip() or "\n" in item or "\r" in item for item in choices)):
        raise api.RuntimeProblem("choices must be single-line, nonempty action strings")
    choices = [item.strip() for item in choices]
    if len(set(choices)) != len(choices):
        raise api.RuntimeProblem("choices must not repeat the same action")
    interaction = draft.get("interaction")
    widget = False
    if interaction is not None:
        if not isinstance(interaction, dict) or interaction.get("type") != "widget":
            raise api.RuntimeProblem("interaction only supports a live hearing/allocation widget")
        widget_id = interaction.get("widget_id")
        from onboarding import status_data
        stage = status_data(save).get("next_stage")
        if (kind != "procedure" or _scene(save) not in {"start", "hearing"} or stage not in {"hearing", "bonus"}
                or not isinstance(widget_id, str) or not widget_id.strip() or any(c in widget_id for c in "<>\n\r")
                or not isinstance(interaction.get("instruction"), str) or not interaction["instruction"].strip()):
            raise api.RuntimeProblem("widget alternative requires the actual widget_id and current hearing/allocation instruction")
        widget = True
    if not widget and len(choices) < 2:
        raise api.RuntimeProblem("毎回の行動候補が不足しています: 現在の場面に沿う選択肢を2つ以上と自由入力を表示してください")
    if kind == "intimate" and (len(choices) < 6 or "Hスキップ" not in choices[5]):
        raise api.RuntimeProblem("既存規則どおり6番目にHスキップが必要です")
    body = "\n\n".join(part.strip() for part in [text, *blocks] if part.strip())
    if widget:
        body = "\n\n".join(part for part in (body, interaction["instruction"].strip()) if part)
    choices_text = "\n".join(f"{index}. {choice}" for index, choice in enumerate(choices, 1))
    choices_text = "\n\n".join(part for part in (choices_text, FREE_INPUT) if part)
    return {"ok": True, "schema": SCHEMA, "profile": kind, "main_text_characters": count,
            "minimum": minimum, "maximum": maximum, "choice_count": len(choices),
            "widget_alternative": widget,
            **({"movement_check": movement} if movement else {}),
            "body_text": body, "choices_text": choices_text,
            "draft_sha256": hashlib.sha256(json.dumps(draft, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "review_scope": "length and choice presence only; prose quality follows the existing style guide"}


def check(api, args):
    save = api.load_yaml(Path(args.save).expanduser())
    before = api.load_yaml(Path(args.before_save).expanduser()) if getattr(args, "before_save", None) else None
    result = validate(api, load(api, args.response), save, before)
    return {key: value for key, value in result.items() if key != "body_text"}
