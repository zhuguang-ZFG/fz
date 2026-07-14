#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge JSON g3/g4 item patches from HIL scripts into a YAML evidence file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _load_items_from_yaml_text(text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    cur: Dict[str, str] | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        s = raw.strip()
        if s.startswith("- id:"):
            if cur:
                items.append(cur)
            cur = {"id": s.split(":", 1)[1].strip().strip('"').strip("'")}
            continue
        if cur is not None and raw.startswith("  ") and ":" in s:
            k, _, v = s.partition(":")
            cur[k.strip()] = v.strip().strip('"').strip("'")
    if cur:
        items.append(cur)
    return items


def merge(template: Path, patches: List[Dict[str, str]], out: Path) -> None:
    text = template.read_text(encoding="utf-8")
    # Update result/note/evidence lines for matching ids (simple line rewrite)
    by_id = {p["id"]: p for p in patches if "id" in p}
    lines = text.splitlines()
    out_lines: List[str] = []
    current_id = None
    for line in lines:
        m = re.match(r"^(\s*)-\s*id:\s*(\S+)\s*$", line)
        if m:
            current_id = m.group(2).strip().strip('"').strip("'")
            out_lines.append(line)
            continue
        if current_id and current_id in by_id:
            p = by_id[current_id]
            for key in ("result", "note", "evidence"):
                if key in p and re.match(rf"^(\s*){key}:\s*", line):
                    indent = re.match(r"^(\s*)", line).group(1)
                    val = str(p[key]).replace("\n", " ")[:400]
                    line = f"{indent}{key}: \"{val}\""
                    break
        if re.match(r"^\s*-\s*id:", line):
            current_id = None
        out_lines.append(line)
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--patch-json", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    patches: List[Dict[str, str]] = []
    for pj in args.patch_json:
        data = json.loads(pj.read_text(encoding="utf-8"))
        key = "g3_item_patches" if "g3_item_patches" in data else "g4_item_patches"
        for p in data.get(key) or []:
            patches.append(p)
    merge(args.template, patches, args.out)
    print(f"wrote {args.out} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
