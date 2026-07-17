#!/usr/bin/env python3
"""Offline structural validation for native protocol scenarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scenario_contract import SCENARIO_DIR, validate_scenario, write_json

RESULTS = Path(__file__).resolve().parent / "results"


def validate_all() -> Dict[str, Any]:
    paths = sorted(SCENARIO_DIR.glob("*.json"))
    errors: List[str] = []
    names: List[str] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.as_posix()}: {exc}")
            continue
        errors.extend(validate_scenario(data, path.as_posix()))
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            names.append(data["name"])
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        errors.append(f"duplicate scenario names: {duplicates}")
    return {"suite": "protocol_scenario_schema", "status": "pass" if paths and not errors else "fail", "files": len(paths), "errors": errors}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="validate native protocol scenario JSON")
    parser.add_argument("--json-out", type=Path, default=RESULTS / "protocol_scenario_schema.json")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_all()
    write_json(args.json_out, report)
    print(f"protocol_scenario_schema files={report['files']} errors={len(report['errors'])}")
    for error in report["errors"]:
        print(f"  ERR {error}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
