#!/usr/bin/env python3
"""マチャダン スペード Muse版: 固定ダイステープ (machadan-tape-r1) の生成・検証・消費。

設計方針 (2026-11-01 作者決定):
- 判定の出目は GM (LLM) が作らない。すべての 1d6 / 1d10 はこのテープから
  順番に消費する。テープは各面がちょうど同数ずつ入った固定列で、シードから
  誰でも再生成して同一性を確認できる。
- 消費位置 (cursor) はセーブに記録する。引き直しや飛ばし読みは、cursor の
  不連続として必ず跡が残る。
- d6 テープ: 600件 (各面100件)。対抗判定は2件消費する (攻撃側→守備側の順)。
- d10 テープ: 500件 (各面50件)。割合判定 (毒30%等) や百分率に使う。

使い方:
  python3 dice.py generate [--out PATH]
      テープを生成して dice_tape.json に保存し、分布を検証する。
  python3 dice.py verify [--tape PATH]
      保存済みテープが仕様どおりか検証する。
  python3 dice.py draw d6 <cursor> [count]
  python3 dice.py draw d10 <cursor> [count]
      cursor 位置から count 件を引き、消費後の新 cursor を JSON で返す。
      末尾を超えたら 0 に戻る (ラップを draws の index で明示する)。
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TAPE = HERE / "dice_tape.json"
REVISION = "machadan-tape-r1"

# テープの正本シード。この2値と生成手順がテープの同一性を保証する。
SEED_D6 = 104857412273853
SEED_D10 = 116150331381085

SPECS = {
    "d6": {"faces": 6, "per_face": 100, "seed": SEED_D6},
    "d10": {"faces": 10, "per_face": 50, "seed": SEED_D10},
}


def build_tape(kind: str) -> list[int]:
    spec = SPECS[kind]
    values = []
    for face in range(1, spec["faces"] + 1):
        values.extend([face] * spec["per_face"])
    random.Random(spec["seed"]).shuffle(values)
    return values


def build_all() -> dict:
    return {"revision": REVISION, "tapes": {k: build_tape(k) for k in SPECS}}


def verify(data: dict) -> dict:
    problems = []
    if not isinstance(data, dict):
        return {"ok": False, "problems": ["テープJSONのルートがobjectではない"]}
    if data.get("revision") != REVISION:
        problems.append(f"revision が {data.get('revision')} (期待値 {REVISION})")
    tapes = data.get("tapes")
    if not isinstance(tapes, dict):
        return {"ok": False, "problems": problems + ["tapes がobjectではない"]}
    for kind, spec in SPECS.items():
        tape = tapes.get(kind)
        if tape is None:
            problems.append(f"{kind} テープが無い")
            continue
        if not isinstance(tape, list):
            problems.append(f"{kind} テープがlistではない")
            continue
        expected_len = spec["faces"] * spec["per_face"]
        if len(tape) != expected_len:
            problems.append(f"{kind} 件数が {len(tape)} (期待値 {expected_len})")
        dist = Counter(tape)
        for face in range(1, spec["faces"] + 1):
            if dist.get(face, 0) != spec["per_face"]:
                problems.append(f"{kind} の {face} が {dist.get(face, 0)} 件 (期待値 {spec['per_face']})")
        if tape != build_tape(kind):
            problems.append(f"{kind} テープがシードからの再生成と一致しない")
    return {"ok": not problems, "problems": problems}


def load_or_build(tape_path: Path) -> dict:
    if tape_path.exists():
        return json.loads(tape_path.read_text(encoding="utf-8"))
    data = build_all()
    tape_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def cmd_generate(args) -> int:
    data = build_all()
    result = verify(data)
    if not result["ok"]:
        raise SystemExit(f"検証失敗: {result['problems']}")
    out = Path(args.out)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    counts = {k: len(v) for k, v in data["tapes"].items()}
    print(json.dumps({"saved": str(out), "revision": REVISION, "counts": counts, "verify": result}, ensure_ascii=False))
    return 0


def cmd_verify(args) -> int:
    try:
        data = json.loads(Path(args.tape).read_text(encoding="utf-8"))
        result = verify(data)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"ok": False, "problems": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


def cmd_draw(args) -> int:
    if args.kind not in SPECS:
        raise SystemExit(f"kind は {list(SPECS)} のいずれか")
    data = load_or_build(Path(args.tape))
    validation = verify(data)
    if not validation["ok"]:
        raise SystemExit(f"テープ検証失敗: {validation['problems']}")
    tape = data["tapes"][args.kind]
    n = len(tape)
    if not (0 <= args.cursor < n):
        raise SystemExit(f"cursor は 0..{n - 1}: {args.cursor}")
    if args.count < 1:
        raise SystemExit("count は 1以上")
    draws = []
    cursor = args.cursor
    for _ in range(args.count):
        draws.append({"index": cursor, "value": tape[cursor]})
        cursor = (cursor + 1) % n
    print(json.dumps({"kind": args.kind, "from_cursor": args.cursor,
                      "draws": draws, "next_cursor": cursor}, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="マチャダン固定ダイステープの生成・検証・消費")
    sub = p.add_subparsers(dest="cmd", required=True)
    pg = sub.add_parser("generate")
    pg.add_argument("--out", default=str(DEFAULT_TAPE))
    pg.set_defaults(func=cmd_generate)
    pv = sub.add_parser("verify")
    pv.add_argument("--tape", default=str(DEFAULT_TAPE))
    pv.set_defaults(func=cmd_verify)
    pd = sub.add_parser("draw")
    pd.add_argument("kind")
    pd.add_argument("cursor", type=int)
    pd.add_argument("count", type=int, nargs="?", default=1)
    pd.add_argument("--tape", default=str(DEFAULT_TAPE))
    pd.set_defaults(func=cmd_draw)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
