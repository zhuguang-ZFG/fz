#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R23: record golden contracts from last host-SIL report or existing fail/status JSON.

Examples:
  # From last_report pass streams (full line list → expect ok)
  python scripts/golden_record.py --from-last --kinds pass --only smoke_ok --dry-run

  # Promote existing fail case file into golden/
  python scripts/golden_record.py --from-case protocol_sim/cases/fail/undefined_feed.json

  # From last_report fail rows (uses matching cases/fail/*.json for setup when possible)
  python scripts/golden_record.py --from-last --kinds fail --only undefined_feed

Never records soft cases. Writes protocol_sim/cases/golden/*.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FZ_ROOT = Path(__file__).resolve().parent.parent
LAST = FZ_ROOT / "protocol_sim" / "results" / "last_report.json"
GOLDEN_DIR = FZ_ROOT / "protocol_sim" / "cases" / "golden"
FAIL_DIR = FZ_ROOT / "protocol_sim" / "cases" / "fail"
STATUS_DIR = FZ_ROOT / "protocol_sim" / "cases" / "status"
ERROR_RE = re.compile(r"error:(\d+)", re.I)
ALARM_RE = re.compile(r"ALARM:(\d+)", re.I)


def _slug(name: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", name.strip())
    s = s.replace(".nc", "").replace(".json", "")
    if not s.startswith("golden_"):
        s = "golden_" + s
    return s[:80]


def _name_match(name: str, filters: Sequence[str]) -> bool:
    if not filters:
        return True
    n = name.lower()
    stem = Path(name).stem.lower()
    for f in filters:
        f = f.lower()
        if f in n or f in stem or stem == f:
            return True
    return False


def _expect_from_responses(responses: List[str]) -> Dict[str, Any]:
    joined = "\n".join(responses or [])
    codes = ERROR_RE.findall(joined)
    if codes:
        uniq = list(dict.fromkeys(codes))
        step: Dict[str, Any] = {"expect": "error", "wait": 2.0}
        if len(uniq) == 1:
            step["code"] = uniq[0]
        else:
            step["codes"] = uniq
        return step
    acodes = ALARM_RE.findall(joined)
    if acodes:
        return {"expect": "alarm", "code": acodes[0], "wait": 2.0}
    # status-like
    if any(x in joined for x in ("VER:", "MPos:", "WPos:", "<Idle", "<Run", "[GC:")):
        return {"expect": "status", "wait": 2.0}
    return {"expect": "ok", "wait": 2.0}


def golden_from_pass_case(case: dict) -> dict:
    name = str(case.get("name") or "pass")
    steps = []
    for lr in case.get("lines") or []:
        line = str(lr.get("line") or "").strip()
        if not line:
            continue
        exp = _expect_from_responses(list(lr.get("responses") or []))
        steps.append({"send": line, **exp})
    return {
        "name": _slug(name).replace("golden_", "golden_pass_"),
        "notes": f"R23 recorded from last_report pass case {name}",
        "setup": [],
        "steps": steps,
    }


def _find_source_json(case_name: str) -> Optional[Path]:
    stem = Path(str(case_name)).stem.lower()
    for d in (FAIL_DIR, STATUS_DIR, GOLDEN_DIR):
        if not d.is_dir():
            continue
        for p in d.glob("*.json"):
            if p.stem.lower() in stem or stem in p.stem.lower():
                return p
            try:
                jn = json.loads(p.read_text(encoding="utf-8")).get("name") or ""
            except (OSError, json.JSONDecodeError):
                jn = ""
            if str(jn).lower() in stem or stem in str(jn).lower():
                return p
    return None


def golden_from_fail_or_status(case: dict) -> dict:
    """Prefer source JSON (keeps setup); else synthesize from last_report lines only."""
    name = str(case.get("name") or "case")
    src = _find_source_json(name)
    if src is not None:
        data = json.loads(src.read_text(encoding="utf-8"))
        data = dict(data)
        data["name"] = _slug(str(data.get("name") or src.stem))
        data["notes"] = (
            f"R23 promoted from {src.relative_to(FZ_ROOT).as_posix()} "
            f"(last_report case {name})"
        )
        return data
    steps = []
    for lr in case.get("lines") or []:
        line = str(lr.get("line") or "").strip()
        if not line:
            continue
        exp = _expect_from_responses(list(lr.get("responses") or []))
        steps.append({"send": line, **exp})
    return {
        "name": _slug(name),
        "notes": (
            f"R23 from last_report only (no source JSON for setup) — "
            f"review setup before promoting. case={name}"
        ),
        "setup": [],
        "steps": steps,
    }


def golden_from_case_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = dict(data)
    data["name"] = _slug(str(data.get("name") or path.stem))
    data["notes"] = f"R23 recorded from {path.as_posix()}"
    return data


def write_golden(data: dict, out_dir: Path, dry_run: bool, force: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = _slug(str(data.get("name") or "case")) + ".json"
    # avoid clobbering hand-authored goldens without --force
    path = out_dir / fname
    if path.is_file() and not force and not dry_run:
        # secondary name
        path = out_dir / (path.stem + "_rec.json")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if dry_run:
        print(f"DRY {path}:\n{text[:500]}...")
    else:
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R23 golden recorder")
    ap.add_argument("--from-last", action="store_true", help="read last_report.json")
    ap.add_argument("--from-case", type=Path, action="append", default=[], help="source JSON")
    ap.add_argument(
        "--kinds",
        default="fail,pass",
        help="comma: pass,fail,golden,status (default fail,pass)",
    )
    ap.add_argument("--only", default="", help="comma name filters")
    ap.add_argument("--out-dir", type=Path, default=GOLDEN_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite same filename")
    ap.add_argument("--report", type=Path, default=LAST)
    args = ap.parse_args(list(argv) if argv is not None else None)

    kinds = {k.strip().lower() for k in args.kinds.split(",") if k.strip()}
    only = [x.strip() for x in args.only.split(",") if x.strip()]
    written: List[Path] = []

    for cf in args.from_case:
        if not cf.is_file():
            print(f"ERROR: not found {cf}", file=sys.stderr)
            return 2
        g = golden_from_case_file(cf)
        if only and not _name_match(str(g.get("name")), only) and not _name_match(cf.name, only):
            continue
        written.append(write_golden(g, args.out_dir, args.dry_run, args.force))

    if args.from_last:
        if not args.report.is_file():
            print(f"ERROR: missing {args.report} — run protocol suite first", file=sys.stderr)
            return 2
        cases = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(cases, list):
            print("ERROR: last_report must be a list", file=sys.stderr)
            return 2
        for case in cases:
            if not isinstance(case, dict) or not case.get("passed"):
                continue
            kind = str(case.get("kind") or "").lower()
            name = str(case.get("name") or "")
            if kind == "soft":
                continue
            if kind not in kinds and not (
                kind == "pass" and "pass" in kinds
            ):
                # map status stored as kind pass
                if kind == "pass" and "status" in kinds and name.lower().startswith("status"):
                    pass
                elif kind not in kinds:
                    continue
            if not _name_match(name, only):
                continue
            if kind == "pass" and not name.lower().startswith("status"):
                if "pass" not in kinds:
                    continue
                g = golden_from_pass_case(case)
            else:
                if kind in ("fail", "golden") or "fail" in kinds or "golden" in kinds:
                    if kind == "fail" and "fail" not in kinds:
                        continue
                    g = golden_from_fail_or_status(case)
                else:
                    continue
            written.append(write_golden(g, args.out_dir, args.dry_run, args.force))

    if not written and not args.from_case and not args.from_last:
        ap.print_help()
        return 3
    if not written:
        print("No cases matched filters")
        return 1
    print(f"golden_record: {len(written)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
