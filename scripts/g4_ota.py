#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G4 OTA evidence validation for release_gate (Memfault/RainMaker-style checklist).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VALID_RESULTS = frozenset({"pass", "fail", "skip", "na"})

REQUIRED_WHEN_OTA = (
    "ota.enabled_in_product",
    "ota.old_to_new_success",
    "ota.version_matches_artifact",
    "ota.failure_recovery_documented",
    "ota.usb_fallback_ok",
)


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
            if key == "items":
                continue
            root[key] = v.strip().strip('"').strip("'")
    if cur:
        root["items"].append(cur)
    return root


def _item_map(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for it in data.get("items") or []:
        if isinstance(it, dict) and it.get("id"):
            out[str(it["id"])] = it
    return out


def validate_g4_evidence(
    path: Path,
    features: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (status, report). status: pass|fail|unknown.
    Caller skips when features.ota is false.
    """
    features = features or {}
    if not path.is_file():
        return "unknown", {"error": f"missing file {path}"}

    data = _load_yaml(path)
    items = _item_map(data)
    if not items:
        return "fail", {"error": "no items[] in evidence file"}

    errors: List[str] = []
    if features.get("ota"):
        for rid in REQUIRED_WHEN_OTA:
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
            if res == "skip" and "waive" not in str(it.get("note", "")).lower():
                errors.append(f"{rid}: skip requires note containing 'waive' when ota in scope")
            if res in ("skip", "na") and not str(it.get("note", "")).strip():
                errors.append(f"{rid}: skip/na requires note")

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
        "item_count": len(items),
        "required": list(REQUIRED_WHEN_OTA) if features.get("ota") else [],
        "errors": errors,
    }
    if errors:
        return "fail", report
    return "pass", report


def main() -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="Validate G4 OTA evidence YAML")
    ap.add_argument("evidence", type=Path)
    ap.add_argument("--ota", action="store_true")
    args = ap.parse_args()
    st, rep = validate_g4_evidence(args.evidence, {"ota": args.ota})
    print(json.dumps({"status": st, **rep}, indent=2, ensure_ascii=False))
    return 0 if st == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
