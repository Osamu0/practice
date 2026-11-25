"""Short ordinary-turn entry points; every final commit keeps runtime safeguards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def begin(api, args):
    if not args.save or not args.candidate_save_output:
        raise api.RuntimeProblem("begin-turn requires --save and --candidate-save-output")
    from onboarding import status
    opening = status(api, SimpleNamespace(save=args.save))
    if opening.get("ok") is not True:
        raise api.RuntimeProblem("火の所有者を一意に確認できません: " +
                                 json.dumps(opening.get("identity_errors", []), ensure_ascii=False))
    original_scene = args.scene
    save = api.load_yaml(Path(args.save).expanduser())
    expedition = save.get("world_state", {}).get("expedition_state", {})
    if (opening["next_stage"] not in {"hearing", "complete"}
            and not expedition.get("active") and args.scene not in {"start", "new"}):
        args = SimpleNamespace(**vars(args))
        args.scene, args.include_scene, args.phase = "start", [], "auto"
    result = api.prepare_context(args)
    from check_knowledge import parse_args, run
    report = run(parse_args(["--root", str(api.ROOT), "--turn", "--save", args.save,
                             "--receipt", result["receipt"], "--json"])).payload()
    if not report.get("ok"):
        raise api.RuntimeProblem("今回のセーブ・参照資料の検証に失敗しました: " +
                                 json.dumps(report.get("errors", []), ensure_ascii=False)[:1800])
    from inventory_lifecycle import refill_request
    result["turn_check"] = {"ok": True, "checks": report.get("checks", {})}
    result["refill_request"] = refill_request(api, Path(args.save).expanduser())
    result["onboarding"] = opening
    if args.scene != original_scene:
        result["deferred_scene"] = original_scene
        result["notice"] = "開始に必要な説明・配分・火の授与を先に完了します。元の入力を保持してください"
    result.setdefault("notice", "contextの本文を最後まで読み、必要な追加資料を取得してから進行してください")
    return result


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish(api, args):
    """Stage changes once, retry the same commit, then render from the committed save."""
    tx = api.safe_id(args.transaction_id)
    current = Path(args.current).expanduser().resolve()
    prepared = Path(args.prepared).expanduser().resolve()
    changes = Path(args.changes).expanduser().resolve()
    candidate = Path(args.output).expanduser().resolve()
    if len({current, prepared, changes, candidate}) != 4:
        raise api.RuntimeProblem("current/prepared/changes/output must be distinct paths")
    changes_bytes = changes.read_bytes()
    payload = json.loads(changes_bytes)
    reply = payload.get("response") if isinstance(payload, dict) else None
    identity = {"current": str(current), "prepared": str(prepared),
                "changes": str(changes), "candidate": str(candidate),
                "prepared_hash": _digest(prepared), "changes_hash": hashlib.sha256(changes_bytes).hexdigest(),
                "turn": args.turn, "inventory_use": args.inventory_use or [], "keep": args.keep}
    journal = api.RUNTIME_DIR / "turn-flow" / (tx + ".json")
    with api.file_locks([api.save_lock_path(current)]):
        if journal.exists():
            record = json.loads(journal.read_text(encoding="utf-8"))
            if record.get("identity") != identity:
                raise api.RuntimeProblem("finish-turn retry identity differs; keep the same files and transaction ID")
        else:
            record = {"schema": "machadan-turn-flow-v1", "transaction_id": tx,
                      "identity": identity, "state": "prepared"}
        data = api.load_yaml(current)
        already_committed = data.get("transaction", {}).get("last_transaction_id") == tx
    if reply is None and not already_committed:
        raise api.RuntimeProblem("changes.responseに未送信の本文・システム表示・行動候補を入れてください。本文字数と選択肢を保存前に確認します")
    if already_committed:
        if not candidate.is_file() or record.get("candidate_hash") != _digest(candidate):
            raise api.RuntimeProblem("committed finish-turn candidate is missing or differs from the recorded operation")
    else:
        api.cmd_apply_changes(SimpleNamespace(current=str(current), prepared=str(prepared),
                              changes=str(changes), output=str(candidate), draft=False))
        record["candidate_hash"] = _digest(candidate)
    if reply is not None:
        from response_contract import validate
        checked_reply = validate(api, reply, api.load_yaml(candidate), api.load_yaml(prepared))
        movement = checked_reply.get("movement_check")
        if movement and movement["occurred"] and not movement["inventory_events_allowed"] and any(
                value.startswith("events:") for value in args.inventory_use or []):
            raise api.RuntimeProblem("移動イベントはM51/C-7の素材から生成し、EV在庫を消費しません")
        # No prose is echoed into the tool result. The author already has the
        # draft; return only the compact check and the exact action footer.
        reply_summary = {key: value for key, value in checked_reply.items()
                         if key not in {"body_text", "choices_text", "review_scope", "schema"}}
        record["response_check"] = reply_summary
    else:
        # An already committed v4.13.1 transaction may be retried for recovery.
        # Do not require editing its hash-bound historical changes or replay it.
        checked_reply = None
        reply_summary = {"ok": True, "legacy_committed_retry": True}
    if (_digest(changes) != identity["changes_hash"] or _digest(prepared) != identity["prepared_hash"]
            or _digest(candidate) != record.get("candidate_hash")):
        raise api.RuntimeProblem("turn files changed during response validation; keep the original draft and retry")
    api.atomic_write(journal, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    commit_args = SimpleNamespace(current=str(current), candidate=str(candidate),
                                 transaction_id=tx, turn=args.turn, keep=args.keep,
                                 inventory_use=args.inventory_use,
                                 inventory_kind=None, inventory_id=None)
    if args.inventory_use:
        committed = api.cmd_commit_turn(commit_args)
    else:
        committed = api.cmd_commit_save(commit_args)
    record["state"] = "committed"
    api.atomic_write(journal, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    # One read/validation supplies both the widget and its plain-text fallback.
    data, warnings = api._validated_status_save(current)
    snapshot = api._status_snapshot(data)
    result = {"ok": True, "committed": True, "transaction_id": tx,
              "commit": committed, "status_text": api._status_text(snapshot, "compact", None),
              "warnings": warnings, "response_check": reply_summary}
    if checked_reply is not None:
        result["choices_text"] = checked_reply["choices_text"]
    if args.status_output:
        try:
            result["widget"] = api._write_status_widget(snapshot, warnings, args.status_output, False)
        except (api.RuntimeProblem, OSError) as exc:
            result["display_warning"] = str(exc)
    from inventory_lifecycle import refill_request
    result["refill_request"] = refill_request(api, current)
    return result
