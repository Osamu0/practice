#!/usr/bin/env python3
"""Delivery-time checks for lightweight reply validation; no model calls."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True


def check(root):
    sys.path.insert(0, str(root / "tools"))
    import response_contract as rc
    api = SimpleNamespace(RuntimeProblem=ValueError)
    cases = []
    save = {"runtime_state": {"scene_id": "turn", "ero_scene": False},
            "world_state": {"location": "通り", "day": 1, "time_of_day": "朝"},
            "player": {"gold": 0}}

    def draft(length=650, **extra):
        return {"schema": rc.SCHEMA, "main_text": "検" * length,
                "system_blocks": [], "choices": ["その場を調べる", "仲間と話す"], **extra}

    def good(label, reply, state=None, before=None):
        result = rc.validate(api, reply, state or save, before)
        assert result["ok"]
        cases.append(label)
        return result

    def bad(label, reply, state=None, before=None):
        try:
            rc.validate(api, reply, state or save, before)
        except ValueError:
            cases.append(label)
        else:
            raise AssertionError("invalid reply accepted: " + label)

    for scene, kind, low, high in (("turn", "town", 600, 800), ("dungeon", "travel", 650, 850),
                                   ("combat", "combat", 550, 750), ("quest", "quest", 550, 750)):
        state = copy.deepcopy(save)
        state["runtime_state"]["scene_id"] = scene
        assert good(kind + "-minimum", draft(low), state)["profile"] == kind
        good(kind + "-maximum", draft(high), state)
        bad(kind + "-too-short", draft(low - 1), state)
        bad(kind + "-too-long", draft(high + 1), state)
    style = (root / "文章/文体ルールカード.md").read_text()
    for fragment in ("650〜850字", "600〜800字", "550〜750字", "## (p) 冒険シーンの文量と被覆"):
        assert fragment in style
    cases.append("limits-match-existing-prose-source")
    assert rc.count_main_text("**雨**が降る。\n 「寒い」 [道](https://example.test) \t") == len("雨が降る。「寒い」道")
    cases.append("count-excludes-whitespace-and-markdown")
    bad("system-text-does-not-fill-prose", draft(30, system_blocks=["数値" * 1000]))
    bad("choices-do-not-fill-prose", draft(30, choices=["行動" * 400, "待つ"]))
    bad("missing-choices", draft(650, choices=[]))
    bad("one-choice-is-not-an-action-menu", draft(650, choices=["待つ"]))
    bad("duplicate-choices", draft(650, choices=["待つ", "待つ"]))
    bad("blank-choice", draft(650, choices=[" ", "待つ"]))
    result = good("exact-numbered-footer", draft())
    assert result["choices_text"] == "1. その場を調べる\n2. 仲間と話す\n\n自由入力もできます。"
    short = draft(12, prose_kind="explanation", short_reason="player_question")
    good("short-player-question-without-gameplay", short, save, save)
    changed = copy.deepcopy(save)
    changed["player"]["gold"] += 1
    bad("substantive-change-cannot-claim-short-exemption", short, changed, save)
    bad("short-exemption-requires-known-reason", {**short, "short_reason": "because short"}, save, save)
    moved = copy.deepcopy(save)
    moved["world_state"]["location"] = "ギルド"
    bad("movement-in-turn-scene-uses-travel-minimum", draft(600), moved, save)
    good("movement-in-turn-scene-accepted", draft(700), moved, save)
    procedural = copy.deepcopy(save)
    procedural["runtime_state"]["scene_id"] = "manage"
    good("procedure-not-padded-to-novel-length", draft(10), procedural)
    bad("procedure-still-keeps-action-menu", draft(10, choices=[]), procedural)
    allocated = copy.deepcopy(save)
    allocated['world_state']['allocation_state'] = {'resolutions': [{'mode': 'fruit'}]}
    assert good("allocation-confirmation-does-not-pad-a-procedure", draft(10), allocated, save)['profile'] == 'procedure'
    hearing = copy.deepcopy(save)
    hearing["runtime_state"]["scene_id"] = "start"
    live_widget = {"type": "widget", "widget_id": "live-widget-42", "instruction": "回答後、チャットに『確定』と入力してください。"}
    good("hearing-widget-is-current-choice-surface", draft(0, choices=[], interaction=live_widget), hearing)
    bad("ordinary-turn-cannot-use-widget-exemption", draft(650, choices=[], interaction=live_widget))
    bad("placeholder-widget-does-not-bypass-menu", draft(0, choices=[], interaction={**live_widget, "widget_id": "<widget-id>"}), hearing)
    dedicated = copy.deepcopy(save)
    dedicated["runtime_state"]["ero_scene"] = True
    skip_choices = [f"選択肢{n}" for n in range(1, 6)] + ["Hスキップ"]
    good("existing-dedicated-minimum-and-sixth-skip", draft(600, choices=skip_choices), dedicated)
    bad("dedicated-minimum-cannot-be-called-brief", draft(599, choices=skip_choices, prose_kind="brief", short_reason="brief_acknowledgement"), dedicated, dedicated)
    bad("skip-must-be-sixth", draft(600, choices=list(reversed(skip_choices))), dedicated)
    original = copy.deepcopy(save)
    reply = draft()
    started = time.perf_counter()
    for _ in range(500):
        rc.validate(api, reply, save)
    elapsed_ms = (time.perf_counter() - started) * 1000 / 500
    assert save == original
    cases.append("validator-is-read-only-and-uses-no-model-or-tools")
    return {"ok": True, "cases": len(cases), "checked": cases,
            "validation_average_ms": round(elapsed_ms, 4),
            "benchmark_scope": "500 in-memory checks of a 650-character synthetic reply; excludes game-save I/O"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    try:
        result = check(p.parse_args().root)
    except Exception as exc:
        result = {"ok": False, "error": repr(exc)}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
