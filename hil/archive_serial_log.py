#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R36: archive HIL serial transcripts for evidence (community: log-as-evidence).

Writes timestamped logs under results/hil_logs/ and a small index JSON/MD.
Does not claim paper/BT pass by itself — only stores what the board said.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FZ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = FZ_ROOT / "results" / "hil_logs"


def _slug(s: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", (s or "hil").strip())
    return s[:48] or "hil"


def archive_text(
    text: str,
    *,
    kind: str,
    port: str = "",
    results_dir: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write .log + return metadata with paths."""
    root = results_dir or DEFAULT_DIR
    if not root.is_absolute():
        root = FZ_ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{ts}_{_slug(kind)}_{_slug(port or 'noport')}"
    log_path = root / f"{base}.log"
    meta_path = root / f"{base}.meta.json"
    body = text if text.endswith("\n") else text + "\n"
    log_path.write_text(body, encoding="utf-8", errors="replace")
    meta: Dict[str, Any] = {
        "suite": "hil_serial_archive",
        "kind": kind,
        "port": port,
        "utc": ts,
        "log_path": str(log_path),
        "bytes": len(body.encode("utf-8", errors="replace")),
        "lines": body.count("\n"),
    }
    if extra:
        meta["extra"] = extra
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return meta


def write_session_index(
    entries: List[Dict[str, Any]],
    *,
    out_md: Optional[Path] = None,
    out_json: Optional[Path] = None,
) -> None:
    """One-page index for the latest HIL session (agent/operator read)."""
    results = FZ_ROOT / "results"
    results.mkdir(parents=True, exist_ok=True)
    md_path = out_md or (results / "hil_log_index.md")
    js_path = out_json or (results / "hil_log_index.json")
    payload = {
        "suite": "hil_log_index",
        "entries": entries,
        "note": "HIL serial archives only — not host SIL; not full paper/BT acceptance",
    }
    js_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# HIL serial log index (R36)",
        "",
        "_Real board transcripts. Host SIL triage is `results/triage_last.md`._",
        "",
    ]
    if not entries:
        lines.append("- (no archives this session)")
    for e in entries:
        lines.append(
            f"- **{e.get('kind')}** port=`{e.get('port')}` bytes={e.get('bytes')} → `{e.get('log_path')}`"
        )
    lines.append("")
    lines.append("## g3 evidence tip")
    lines.append(
        "Paste log path into `g3_evidence` item `evidence:` fields or attach in PR notes."
    )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R36 archive HIL serial text")
    ap.add_argument("--text-file", type=Path, help="read transcript from file")
    ap.add_argument("--kind", default="manual")
    ap.add_argument("--port", default="")
    ap.add_argument("--results-dir", type=Path, default=DEFAULT_DIR)
    args = ap.parse_args(argv)
    if not args.text_file or not args.text_file.is_file():
        print("usage: --text-file path (or call archive_text from hil scripts)")
        return 2
    text = args.text_file.read_text(encoding="utf-8", errors="replace")
    meta = archive_text(
        text, kind=args.kind, port=args.port, results_dir=args.results_dir
    )
    write_session_index([meta])
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
