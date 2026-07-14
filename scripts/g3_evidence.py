#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse/validate G3 HIL evidence YAML for release_gate.

Community practice: silicon evidence is checklist + operator (Golioth HIL /
product ACCEPTANCE_CHECKLIST), not grblHAL_sim green.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


VALID_RESULTS = frozenset({"pass", "fail", "skip", "na"})

# Required item id prefixes when feature enabled
PAPER_IDS = (
    "paper.1.1",
    "paper.1.2",
    "paper.1.2b",
    "paper.1.2c",
    "paper.1.3",
    "paper.1.4",
)
KEY_IDS = ("key.2.1", "key.2.2", "key.2.3", "key.2.4")
SEG_IDS = ("seg.3.1", "seg.3.2", "seg.3.3")
G3A_IDS = ("g3a.flash", "g3a.boot", "g3a.ident", "g3a.motion", "g3a.reset")


def _load_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _parse_simple(text)


def _parse_simple(text: str) -> Dict[str, Any]:
    """Minimal parser for template-shaped evidence files."""
    root: Dict[str, Any] = {"items": []}
    cur: Optional[Dict[str, Any]] = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        s = raw.strip()
        if s.startswith("- id:"):
            if cur:
                root["items"].append(cur)
            cur = {"id": s.split(":", 1)[1].strip().strip('"').strip("'")}
            continue
        if cur is not None and raw.startswith("  "):
            if ":" in s:
                k, _, v = s.partition(":")
                cur[k.strip()] = v.strip().strip('"').strip("'")
            continue
        if cur is not None and not raw.startswith(" "):
            root["items"].append(cur)
            cur = None
        if ":" in s and not s.startswith("-"):
            k, _, v = s.partition(":")
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            if key == "items":
                continue
            if key == "round":
                try:
                    root[key] = int(val)
                except ValueError:
                    root[key] = val
            else:
                root[key] = val
    if cur:
        root["items"].append(cur)
    return root


def _item_map(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for it in data.get("items") or []:
        if isinstance(it, dict) and it.get("id"):
            out[str(it["id"])] = it
    return out


def validate_g3_evidence(
    path: Path,
    features: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (status, report) where status is pass|fail|unknown.
    """
    features = features or {}
    if not path.is_file():
        return "unknown", {"error": f"missing file {path}"}

    data = _load_yaml(path)
    items = _item_map(data)
    if not items:
        return "fail", {"error": "no items[] in evidence file"}

    errors: List[str] = []
    required: List[str] = list(G3A_IDS)
    if features.get("paper_path"):
        required.extend(PAPER_IDS)
        required.extend(KEY_IDS)
        required.extend(SEG_IDS)
    elif features.get("bluetooth"):
        required.extend(KEY_IDS)
        required.extend(SEG_IDS)

    for rid in required:
        it = items.get(rid)
        if not it:
            errors.append(f"missing required item {rid}")
            continue
        res = str(it.get("result", "")).lower().strip()
        if res not in VALID_RESULTS:
            errors.append(f"{rid}: invalid result {res!r}")
            continue
        if res == "fail":
            errors.append(f"{rid}: FAIL — {it.get('note', '')}")
        if res in ("skip", "na") and not str(it.get("note", "")).strip():
            errors.append(f"{rid}: skip/na requires note")
        # product features: skip on paper items is not OK for ship
        if features.get("paper_path") and rid.startswith("paper.") and res in ("skip", "na"):
            errors.append(f"{rid}: paper_path in scope — cannot skip without scope change")
        if features.get("paper_path") and rid.startswith("key.") and res in ("skip", "na"):
            errors.append(f"{rid}: paper/bt product — key test cannot skip without note+waiver")
            # allow if note contains waive? keep strict: skip fails validation
        if features.get("bluetooth") and rid.startswith("key.") and res == "skip":
            if "waive" not in str(it.get("note", "")).lower():
                errors.append(f"{rid}: bluetooth in scope — key skip needs note containing 'waive' or pass")

    # any explicit fail anywhere
    for iid, it in items.items():
        if str(it.get("result", "")).lower() == "fail":
            msg = f"{iid}: FAIL"
            if msg not in errors:
                errors.append(msg)

    report = {
        "file": str(path),
        "version": data.get("version"),
        "operator": data.get("operator"),
        "date": data.get("date"),
        "round": data.get("round"),
        "machine": data.get("machine"),
        "item_count": len(items),
        "required": required,
        "errors": errors,
    }
    if errors:
        return "fail", report
    return "pass", report


def main() -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="Validate G3 evidence YAML")
    ap.add_argument("evidence", type=Path)
    ap.add_argument("--paper", action="store_true")
    ap.add_argument("--bluetooth", action="store_true")
    args = ap.parse_args()
    feats = {"paper_path": args.paper, "bluetooth": args.bluetooth}
    status, report = validate_g3_evidence(args.evidence, feats)
    print(json.dumps({"status": status, **report}, indent=2, ensure_ascii=False))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
