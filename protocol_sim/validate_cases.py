#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R33: structural validation for protocol_sim JSON cases (no jsonschema dep).

Community/CI practice: catch broken hand-edited cases before TCP sim
(OctoPrint/firmware suites similarly validate config/scripts offline).

Exit:
  0 all OK
  1 one or more structural errors
  2 no cases found when expected
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
RESULTS = ROOT / "results"

EXPECT_OK = frozenset({"error", "alarm", "ok", "status", "any"})
DIRS = ("fail", "golden", "status", "inject")


def _err(path: Path, msg: str) -> str:
    try:
        rel = path.relative_to(ROOT.parent)
    except ValueError:
        rel = path
    return f"{rel.as_posix()}: {msg}"


def validate_step(step: Any, path: Path, idx: int) -> List[str]:
    out: List[str] = []
    if not isinstance(step, dict):
        return [_err(path, f"steps[{idx}] must be object")]
    if "send" not in step or not str(step.get("send", "")).strip():
        out.append(_err(path, f"steps[{idx}] missing non-empty send"))
    exp = str(step.get("expect", "error")).lower()
    if exp not in EXPECT_OK:
        out.append(_err(path, f"steps[{idx}] bad expect={exp!r} need {sorted(EXPECT_OK)}"))
    if "code" in step and step["code"] is not None:
        if not isinstance(step["code"], (str, int)):
            out.append(_err(path, f"steps[{idx}].code must be str|int"))
    if "codes" in step and step["codes"] is not None:
        if not isinstance(step["codes"], list) or not step["codes"]:
            out.append(_err(path, f"steps[{idx}].codes must be non-empty list"))
        else:
            for c in step["codes"]:
                if not isinstance(c, (str, int)):
                    out.append(_err(path, f"steps[{idx}].codes item type"))
                    break
    if "wait" in step and step["wait"] is not None:
        try:
            float(step["wait"])
        except (TypeError, ValueError):
            out.append(_err(path, f"steps[{idx}].wait must be number"))
    for key in ("contains", "contains_any"):
        if key in step and step[key] is not None:
            v = step[key]
            if not isinstance(v, (str, list)):
                out.append(_err(path, f"steps[{idx}].{key} must be str|list"))
    return out


def validate_case_file(path: Path, kind: str) -> List[str]:
    errors: List[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [_err(path, f"JSON: {exc}")]
    except OSError as exc:
        return [_err(path, f"read: {exc}")]

    if not isinstance(data, dict):
        return [_err(path, "root must be object")]

    name = data.get("name")
    if name is not None and not isinstance(name, str):
        errors.append(_err(path, "name must be string"))

    setup = data.get("setup")
    if setup is not None:
        if not isinstance(setup, list):
            errors.append(_err(path, "setup must be list of strings"))
        else:
            for i, s in enumerate(setup):
                if not isinstance(s, str):
                    errors.append(_err(path, f"setup[{i}] must be string"))

    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 1:
        errors.append(_err(path, "steps must be non-empty list"))
    else:
        for i, st in enumerate(steps):
            errors.extend(validate_step(st, path, i))

    # inject packs should look like "false green" (often expect ok wrongly)
    # no hard rule — structure only

    return errors


def collect_json_cases() -> List[Tuple[str, Path]]:
    found: List[Tuple[str, Path]] = []
    for d in DIRS:
        p = CASES / d
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.json")):
            found.append((d, f))
    return found


def validate_all() -> Tuple[int, List[str], Dict[str, Any]]:
    items = collect_json_cases()
    errors: List[str] = []
    by_dir: Dict[str, int] = {}
    for kind, path in items:
        by_dir[kind] = by_dir.get(kind, 0) + 1
        errors.extend(validate_case_file(path, kind))
    rep = {
        "suite": "protocol_case_schema",
        "passed": len(errors) == 0 and len(items) > 0,
        "n_files": len(items),
        "by_dir": by_dir,
        "n_errors": len(errors),
        "errors": errors[:50],
    }
    if not items:
        return 2, ["no JSON cases under protocol_sim/cases/{fail,golden,status,inject}"], rep
    return (0 if not errors else 1), errors, rep


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R33 validate protocol JSON cases")
    ap.add_argument("--json-out", type=Path, default=RESULTS / "case_schema_last.json")
    args = ap.parse_args(list(argv) if argv is not None else None)

    code, errors, rep = validate_all()
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"case_schema files={rep['n_files']} errors={rep['n_errors']} by_dir={rep['by_dir']}")
    for e in errors[:30]:
        print(f"  ERR {e}")
    if len(errors) > 30:
        print(f"  ... +{len(errors) - 30} more")
    print(f"wrote {args.json_out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
