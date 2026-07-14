#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R24: check soft_divergence.json against cases/soft/allowlist.yaml.

Exit:
  0  all high_divergence entries are allowlisted (or none)
  1  unknown high_divergence / over max_err_ratio
  2  missing inputs when --require-div
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

FZ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALLOW = FZ_ROOT / "protocol_sim" / "cases" / "soft" / "allowlist.yaml"
DEFAULT_DIV = FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json"
OUT_PATH = FZ_ROOT / "protocol_sim" / "results" / "soft_allowlist_last.json"


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return data
    # minimal fallback: no PyYAML — parse simple key lists via JSON-like subset
    # Prefer shipping without dependency: allowlist also loadable as JSON if .json
    raise RuntimeError("PyYAML required for allowlist.yaml (pip install pyyaml) or use --allowlist *.json")


def load_allowlist(path: Path) -> dict:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if yaml is None:
        # strip comments and use a tiny parser for our fixed schema
        return _parse_allowlist_lite(path.read_text(encoding="utf-8"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("allowlist root must be mapping")
    return data


def _parse_allowlist_lite(text: str) -> dict:
    """
    Minimal YAML subset for allowlist when PyYAML missing:
    version, high_ratio_threshold, entries with match/max_err_ratio only.
    """
    entries: List[dict] = []
    version = 1
    thr = 0.5
    cur: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("version:"):
            version = int(line.split(":", 1)[1].strip())
        elif line.startswith("high_ratio_threshold:"):
            thr = float(line.split(":", 1)[1].strip())
        elif re.match(r"\s+-\s+match:", line):
            if cur:
                entries.append(cur)
            m = re.search(r"match:\s*(\S+)", line)
            cur = {"match": m.group(1) if m else "", "max_err_ratio": 1.0}
        elif cur is not None and "max_err_ratio:" in line:
            cur["max_err_ratio"] = float(line.split(":", 1)[1].strip())
        elif cur is not None and "notes:" in line:
            cur["notes"] = line.split(":", 1)[1].strip().strip('"')
    if cur:
        entries.append(cur)
    return {"version": version, "high_ratio_threshold": thr, "entries": entries}


def _norm_name(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("soft:"):
        n = n[5:]
    return n.replace("\\", "/")


def _find_entry(name: str, entries: List[dict]) -> Optional[dict]:
    n = _norm_name(name)
    for e in entries:
        m = str(e.get("match") or "").lower()
        if not m:
            continue
        if m in n or n in m or Path(n).stem == m:
            return e
    return None


def _ratio(ok: int, err: int) -> float:
    t = ok + err
    if t <= 0:
        return 0.0
    return err / t


def check_divergence(div: dict, allow: dict) -> Dict[str, Any]:
    entries = list(allow.get("entries") or [])
    files = list(div.get("files") or [])
    high = list(div.get("high_divergence") or [])
    # also treat any file with ratio>=threshold as high if not listed in high
    thr = float(allow.get("high_ratio_threshold") or 0.5)

    unknown: List[dict] = []
    allowed: List[dict] = []
    over: List[dict] = []
    ok_files: List[dict] = []

    high_set = {_norm_name(h) for h in high}
    for f in files:
        name = str(f.get("name") or "")
        n_ok = int(f.get("ok_lines") or 0)
        n_err = int(f.get("err_lines") or 0)
        r = _ratio(n_ok, n_err)
        is_high = _norm_name(name) in high_set or r >= thr
        entry = _find_entry(name, entries)
        rec = {
            "name": name,
            "ok_lines": n_ok,
            "err_lines": n_err,
            "err_ratio": round(r, 4),
            "is_high": is_high,
            "allow_match": (entry or {}).get("match"),
        }
        if not is_high:
            ok_files.append(rec)
            continue
        if entry is None:
            unknown.append(rec)
            continue
        max_r = float(entry.get("max_err_ratio") or 1.0)
        if r > max_r + 1e-9:
            rec["max_err_ratio"] = max_r
            over.append(rec)
        else:
            allowed.append(rec)

    # high names with no file row
    for h in high:
        if not any(_norm_name(h) == _norm_name(x.get("name") or "") for x in files):
            entry = _find_entry(h, entries)
            rec = {"name": h, "ok_lines": 0, "err_lines": 0, "err_ratio": 1.0, "is_high": True}
            if entry is None:
                unknown.append(rec)
            else:
                allowed.append({**rec, "allow_match": entry.get("match")})

    passed = len(unknown) == 0 and len(over) == 0
    return {
        "suite": "soft_allowlist",
        "passed": passed,
        "unknown_high": unknown,
        "over_ratio": over,
        "allowed_high": allowed,
        "ok_files": ok_files,
        "n_high": len(unknown) + len(over) + len(allowed),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R24 soft allowlist check")
    ap.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOW)
    ap.add_argument("--divergence", type=Path, default=DEFAULT_DIV)
    ap.add_argument("--json-out", type=Path, default=OUT_PATH)
    ap.add_argument(
        "--require-div",
        action="store_true",
        help="exit 2 if soft_divergence.json missing",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on unknown high (default true behavior)",
    )
    # default is strict on unknown; --lenient always 0 if file readable
    ap.add_argument(
        "--lenient",
        action="store_true",
        help="always exit 0 after writing report (warn only)",
    )
    args = ap.parse_args(argv)

    if not args.allowlist.is_file():
        print(f"ERROR: allowlist not found: {args.allowlist}", file=sys.stderr)
        return 2
    if not args.divergence.is_file():
        msg = f"soft_divergence missing: {args.divergence}"
        if args.require_div:
            print(f"ERROR: {msg}", file=sys.stderr)
            return 2
        print(f"WARN: {msg} — nothing to check", flush=True)
        rep = {"suite": "soft_allowlist", "passed": True, "detail": "no_divergence_file"}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        return 0

    allow = load_allowlist(args.allowlist)
    div = json.loads(args.divergence.read_text(encoding="utf-8"))
    rep = check_divergence(div, allow)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"soft_allowlist passed={rep['passed']} "
          f"unknown={len(rep['unknown_high'])} over={len(rep['over_ratio'])} "
          f"allowed={len(rep['allowed_high'])}")
    for u in rep["unknown_high"]:
        print(f"  UNKNOWN_HIGH: {u['name']} ratio={u.get('err_ratio')}")
    for u in rep["over_ratio"]:
        print(f"  OVER_RATIO: {u['name']} ratio={u.get('err_ratio')} max={u.get('max_err_ratio')}")
    if args.lenient:
        return 0
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
