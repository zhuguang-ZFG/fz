#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC-side protocol regression against grblHAL Simulator (or any TCP Grbl-like endpoint).

Official sim: https://github.com/grblHAL/Simulator
Web Builder:  https://svn.io-engineering.com:8443/?driver=Simulator

This does NOT run Grbl_Esp32 firmware. It checks generic Grbl/grblHAL ok/error/ALARM
behavior for G-code programs on a desktop simulator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# shared host-SIL client / sim discovery
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim_common.find_sim import find_sim, find_validator, VENDOR_SIM  # noqa: E402
from sim_common.grbl_tcp import (  # noqa: E402
    GrblTcp,
    ERROR_RE,
    ALARM_RE,
    OK_RE,
    classify_responses,
    DEFAULT_TIMEOUT,
)
from sim_common.ports import find_free_port  # noqa: E402


ROOT = Path(__file__).resolve().parent
FZ_ROOT = ROOT.parent
CASES = ROOT / "cases"
PASS_DIR = CASES / "pass"
FAIL_DIR = CASES / "fail"
SOFT_DIR = CASES / "soft"
STATUS_DIR = CASES / "status"
GOLDEN_DIR = CASES / "golden"
INJECT_DIR = CASES / "inject"
RESULTS_DIR = ROOT / "results"
# Optional product firmware tree (env GRBL_ROOT) for soft repo tests
_GRBL = os.environ.get("GRBL_ROOT", "")
REPO_ROOT = Path(_GRBL) if _GRBL else FZ_ROOT
REPO_TESTS = (
    Path(_GRBL) / "Grbl_Esp32" / "src" / "tests"
    if _GRBL
    else FZ_ROOT / "fixtures" / "grbl_tests"
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7681
BOOT_WAIT = 0.55


@dataclass
class LineResult:
    line: str
    responses: List[str]
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    name: str
    kind: str  # pass | fail | soft | golden | inject
    passed: bool
    detail: str = ""
    lines: List[LineResult] = field(default_factory=list)


# find_sim / find_validator / GrblTcp / classify_responses: sim_common
GrblTcpClient = GrblTcp  # backward-compatible name


def is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith(";") or s.startswith("(")


def run_pass_file(client: GrblTcpClient, path: Path) -> CaseResult:
    name = path.name
    results: List[LineResult] = []
    client.soft_reset()
    client.unlock_if_needed()
    failed = False
    detail = ""
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        if is_comment_or_blank(raw):
            continue
        # Skip pure settings reset noise if present
        line = raw.strip()
        # Motion/spindle lines may take longer if sim runs at realtime (-t 1).
        wait = 6.0 if re.match(r"(?i)^[GM]\d", line) else 1.5
        resp = client.send_line(line, wait=wait)
        kind, code = classify_responses(resp)
        ok = kind == "ok"
        if kind in ("error", "alarm"):
            ok = False
            failed = True
            detail = f"unexpected {kind}:{code} on: {line}"
        elif kind != "ok":
            failed = True
            detail = f"no ok for: {line} (got {kind} {resp})"
            ok = False
        lr = LineResult(line=line, responses=list(resp), ok=ok, detail="" if ok else detail)
        results.append(lr)
        if failed:
            break
    return CaseResult(name=name, kind="pass", passed=not failed, detail=detail, lines=results)


def run_fail_script(client: GrblTcpClient, path: Path) -> CaseResult:
    """
    JSON schema:
    {
      "name": "optional",
      "setup": ["$X", "G21"],          # optional, expect ok
      "steps": [
        {"send": "G1 X1", "expect": "error", "code": "22"},
        {"send": "G999", "expect": "error"},
        {"send": "?", "expect": "status"}
      ]
    }
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("name") or path.stem
    results: List[LineResult] = []
    client.soft_reset()
    client.unlock_if_needed()
    for s in data.get("setup") or []:
        client.send_line(str(s), wait=1.0)

    failed = False
    detail = ""
    for step in data.get("steps") or []:
        send = str(step["send"])
        expect = str(step.get("expect", "error")).lower()
        code = step.get("code")
        codes = step.get("codes")
        allowed: Optional[List[str]] = None
        if codes is not None:
            allowed = [str(c) for c in codes]
        elif code is not None:
            allowed = [str(code)]
        resp = client.send_line(send, wait=float(step.get("wait", 2.0)))
        kind, got_code = classify_responses(resp)
        ok = False
        if expect == "error":
            ok = kind == "error" and (allowed is None or got_code in allowed)
        elif expect == "alarm":
            ok = kind == "alarm" and (allowed is None or got_code in allowed)
        elif expect == "ok":
            ok = kind == "ok"
        elif expect == "status":
            ok = kind in ("status", "ok")
        elif expect == "any":
            ok = True
        else:
            ok = False
            detail = f"unknown expect={expect}"
        joined = "\n".join(resp)
        contains = step.get("contains")
        if contains is not None and ok:
            need = contains if isinstance(contains, list) else [contains]
            ok = all(str(c) in joined for c in need)
            if not ok:
                detail = f"step {send!r}: missing contains {need} in {resp}"
        contains_any = step.get("contains_any")
        if contains_any is not None and ok:
            opts = contains_any if isinstance(contains_any, list) else [contains_any]
            ok = any(str(c) in joined for c in opts)
            if not ok:
                detail = f"step {send!r}: none of contains_any {opts} in {resp}"
        if not ok and not detail:
            want = f"{expect}:{allowed}" if allowed else expect
            detail = f"step {send!r}: want {want}, got {kind}:{got_code} resp={resp}"
        results.append(
            LineResult(line=send, responses=list(resp), ok=ok, detail="" if ok else detail)
        )
        if not ok:
            failed = True
            break
    return CaseResult(name=name, kind="fail", passed=not failed, detail=detail, lines=results)


def run_validator(path: Path, validator: Path) -> Tuple[bool, str]:
    """
    Feed file contents on stdin. Some Windows builds hang when given a path
    argument alone; stdin is the reliable path for grblHAL_validator.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        proc = subprocess.run(
            [str(validator)],
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return False, "validator not found"
    except subprocess.TimeoutExpired:
        return False, "validator timeout"
    out = (proc.stdout or "") + (proc.stderr or "")
    # Return code: 0 success, else line number of first error (upstream help).
    ok = proc.returncode == 0 and not ERROR_RE.search(out)
    return ok, (out.strip()[:2000] or f"exit={proc.returncode}")


def collect_pass_files() -> List[Path]:
    if not PASS_DIR.is_dir():
        return []
    return sorted(PASS_DIR.glob("*.nc"))


def collect_fail_files() -> List[Path]:
    if not FAIL_DIR.is_dir():
        return []
    return sorted(FAIL_DIR.glob("*.json"))


def collect_soft_files() -> List[Path]:
    if not SOFT_DIR.is_dir():
        return []
    return sorted(SOFT_DIR.glob("*.nc"))


def collect_status_files() -> List[Path]:
    if not STATUS_DIR.is_dir():
        return []
    return sorted(STATUS_DIR.glob("*.json"))


def collect_golden_files() -> List[Path]:
    if not GOLDEN_DIR.is_dir():
        return []
    return sorted(GOLDEN_DIR.glob("*.json"))


def collect_inject_files() -> List[Path]:
    """Fault-injection packs: expected to FAIL when run as normal cases."""
    if not INJECT_DIR.is_dir():
        return []
    return sorted(INJECT_DIR.glob("*.json"))


def _only_filters(raw: str) -> List[str]:
    return [x.strip().lower() for x in (raw or "").split(",") if x.strip()]


def _name_matches(name: str, filters: Sequence[str]) -> bool:
    if not filters:
        return True
    n = name.lower()
    stem = Path(name).stem.lower() if "." in name else n
    for f in filters:
        if f in n or f in stem or n.endswith(f) or stem == f:
            return True
        # allow soft:foo.nc vs foo
        if n.startswith("soft:") and f in n[5:]:
            return True
        if n.startswith("status_") and f in n:
            return True
    return False


def run_soft_file(client: GrblTcpClient, path: Path) -> CaseResult:
    """
    Soft stream: record ok/error per line but never fail the hard suite.
    Used for product-tree samples that may diverge from grblHAL.
    """
    name = f"soft:{path.name}"
    results: List[LineResult] = []
    client.soft_reset()
    client.unlock_if_needed()
    n_err = 0
    n_ok = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        if is_comment_or_blank(raw):
            continue
        line = raw.strip()
        # skip product ESP commands
        if line.upper().startswith("[ESP"):
            continue
        wait = 4.0 if re.match(r"(?i)^[GM]\d", line) else 1.2
        resp = client.send_line(line, wait=wait)
        kind, code = classify_responses(resp)
        line_ok = kind == "ok"
        if kind in ("error", "alarm"):
            n_err += 1
            line_ok = False
        elif kind == "ok":
            n_ok += 1
        results.append(
            LineResult(
                line=line,
                responses=list(resp),
                ok=line_ok,
                detail="" if line_ok else f"{kind}:{code}",
            )
        )
        # cap soft files to avoid long hangs
        if len(results) >= 80:
            break
    err_samples = [lr for lr in results if not lr.ok][:5]
    sample_s = "; ".join(f"{lr.line!r}->{lr.detail}" for lr in err_samples)
    detail = f"ok_lines={n_ok} err_lines={n_err} streamed={len(results)}"
    if sample_s:
        detail += f" | first_errs: {sample_s}"
    # soft always passed=True for gate; detail carries divergence signal
    return CaseResult(name=name, kind="soft", passed=True, detail=detail, lines=results)


def print_report(cases: Sequence[CaseResult]) -> int:
    hard = [c for c in cases if c.kind != "soft"]
    soft = [c for c in cases if c.kind == "soft"]
    failed = [c for c in hard if not c.passed]
    print("")
    print("=== sim_regression report ===")
    for c in cases:
        mark = "PASS" if c.passed else "FAIL"
        show_detail = c.detail and (not c.passed or c.kind == "soft")
        print(f"  [{mark}] ({c.kind}) {c.name}" + (f" — {c.detail}" if show_detail else ""))
    print(f"hard: {len(hard) - len(failed)}/{len(hard)} passed; soft: {len(soft)}")
    if failed:
        print("FAILED cases:")
        for c in failed:
            print(f"  - {c.name}: {c.detail}")
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grbl protocol regression via grblHAL sim TCP")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--validator-only",
        action="store_true",
        help="Only run grblHAL_validator on pass/*.nc (no TCP)",
    )
    ap.add_argument(
        "--include-repo-tests",
        action="store_true",
        help="Stream GRBL_ROOT Grbl_Esp32/src/tests samples as soft (never hard-fail)",
    )
    ap.add_argument(
        "--start-sim",
        action="store_true",
        help="Spawn GRBLHAL_SIM -p PORT in background for this run",
    )
    ap.add_argument(
        "--with-validator",
        action="store_true",
        help="Also run grblHAL_validator on pass/*.nc after TCP cases",
    )
    ap.add_argument(
        "--only",
        default="",
        help="Comma-separated case name/stem filters (pass/fail/status/soft/golden)",
    )
    ap.add_argument(
        "--list-cases",
        action="store_true",
        help="List case names and exit",
    )
    ap.add_argument(
        "--golden",
        action="store_true",
        help="Run only cases/golden/*.json (hard gold contracts)",
    )
    ap.add_argument(
        "--skip-golden",
        action="store_true",
        help="Skip golden pack (default includes golden with full suite)",
    )
    ap.add_argument(
        "--integrity-inject",
        action="store_true",
        help=(
            "R19: run cases/inject only; exit 0 iff every inject case FAILS "
            "(proves harness catches false-green expectations)"
        ),
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    only_f = _only_filters(getattr(args, "only", "") or "")
    if getattr(args, "list_cases", False):
        for label, paths in (
            ("pass", collect_pass_files()),
            ("fail", collect_fail_files()),
            ("status", collect_status_files()),
            ("golden", collect_golden_files()),
            ("inject", collect_inject_files()),
            ("soft", collect_soft_files()),
        ):
            for path in paths:
                print(f"{label}	{path.stem}	{path.name}")
        return 0
    cases: List[CaseResult] = []
    sim_proc: Optional[subprocess.Popen] = None
    golden_only = bool(getattr(args, "golden", False))
    skip_golden = bool(getattr(args, "skip_golden", False))
    integrity_inject = bool(getattr(args, "integrity_inject", False))
    if integrity_inject and golden_only:
        print("ERROR: use either --golden or --integrity-inject, not both", file=sys.stderr)
        return 3

    validator = find_validator()
    if args.validator_only:
        if not validator:
            print(
                "ERROR: grblHAL_validator not found. Set GRBLHAL_VALIDATOR or install from Web Builder.",
                file=sys.stderr,
            )
            print("  https://svn.io-engineering.com:8443/?driver=Simulator", file=sys.stderr)
            return 2
        for nc in collect_pass_files():
            ok, out = run_validator(nc, validator)
            cases.append(
                CaseResult(
                    name=f"validator:{nc.name}",
                    kind="pass",
                    passed=ok,
                    detail="" if ok else out[:300],
                )
            )
        code = print_report(cases)
        (RESULTS_DIR / "last_report.json").write_text(
            json.dumps([asdict(c) for c in cases], indent=2), encoding="utf-8"
        )
        return code

    if args.start_sim:
        sim = find_sim()
        if not sim:
            print(
                "ERROR: grblHAL_sim not found. Set GRBLHAL_SIM or install from Web Builder.",
                file=sys.stderr,
            )
            return 2
        # Avoid bind clash if previous sim left port open
        args.port = find_free_port(args.port, host=args.host)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        sim_err = RESULTS_DIR / "sim_stderr_last.log"
        # -n: no comment prefixes; -t 0: as fast as possible (official sim flag)
        err_f = open(sim_err, "w", encoding="utf-8", errors="replace")
        sim_proc = subprocess.Popen(
            [str(sim), "-n", "-t", "0", "-p", str(args.port)],
            stdout=subprocess.DEVNULL,
            stderr=err_f,
            cwd=str(sim.parent),
        )
        # Do NOT TCP-probe before the real client: grblHAL_sim is effectively
        # single-session; a wait_port connect can race/steal the accept.
        time.sleep(0.9)
        if sim_proc.poll() is not None:
            print(
                f"ERROR: sim exited early code={sim_proc.returncode} log={sim_err}",
                file=sys.stderr,
            )
            try:
                err_f.close()
            except OSError:
                pass
            return 2

    client = GrblTcpClient(args.host, args.port, timeout=args.timeout, boot_wait=BOOT_WAIT)
    try:
        last_exc: Optional[OSError] = None
        for attempt in range(8):
            try:
                client.connect()
                last_exc = None
                break
            except OSError as exc:
                last_exc = exc
                time.sleep(0.35 + 0.1 * attempt)
        if last_exc is not None:
            print(
                f"ERROR: cannot connect to {args.host}:{args.port} ({last_exc}).\n"
                f"Start sim first, e.g. grblHAL_sim -p {args.port}\n"
                f"Web Builder: https://svn.io-engineering.com:8443/?driver=Simulator",
                file=sys.stderr,
            )
            return 2

        if integrity_inject:
            # Fault packs must FAIL as normal expectations → integrity pass if all red
            injects = collect_inject_files()
            if not injects:
                print("ERROR: no cases/inject/*.json for --integrity-inject", file=sys.stderr)
                return 2
            for inj in injects:
                if only_f and not (
                    _name_matches(inj.stem, only_f) or _name_matches(inj.name, only_f)
                ):
                    continue
                print(f"running inject (expect RED): {inj.name} ...")
                cr = run_fail_script(client, inj)
                cr.kind = "inject"
                cases.append(cr)
        else:
            if not golden_only:
                for nc in collect_pass_files():
                    if not _name_matches(nc.name, only_f) and not _name_matches(
                        nc.stem, only_f
                    ):
                        continue
                    print(f"running pass: {nc.name} ...")
                    cases.append(run_pass_file(client, nc))

                for js in collect_fail_files():
                    if not _name_matches(js.stem, only_f) and not _name_matches(
                        js.name, only_f
                    ):
                        continue
                    print(f"running fail: {js.name} ...")
                    cases.append(run_fail_script(client, js))

                for st in collect_status_files():
                    # status JSON has "name" field; match stem too
                    if not _name_matches(st.stem, only_f) and not _name_matches(
                        st.name, only_f
                    ):
                        try:
                            jn = json.loads(st.read_text(encoding="utf-8")).get("name") or ""
                        except Exception:
                            jn = ""
                        if not _name_matches(str(jn), only_f):
                            continue
                    print(f"running status: {st.name} ...")
                    cr = run_fail_script(client, st)
                    cr.kind = "pass"  # hard status assertions
                    cases.append(cr)

            # R19 golden pack: hard contracts (default full suite unless --skip-golden)
            if golden_only or not skip_golden:
                for gf in collect_golden_files():
                    if not _name_matches(gf.stem, only_f) and not _name_matches(
                        gf.name, only_f
                    ):
                        try:
                            jn = json.loads(gf.read_text(encoding="utf-8")).get("name") or ""
                        except Exception:
                            jn = ""
                        if not _name_matches(str(jn), only_f):
                            continue
                    print(f"running golden: {gf.name} ...")
                    cr = run_fail_script(client, gf)
                    cr.kind = "golden"
                    cases.append(cr)

            if not golden_only:
                for sf in collect_soft_files():
                    if not _name_matches(sf.name, only_f) and not _name_matches(
                        f"soft:{sf.name}", only_f
                    ):
                        continue
                    print(f"running soft: {sf.name} ...")
                    cases.append(run_soft_file(client, sf))

                if args.include_repo_tests and REPO_TESTS.is_dir():
                    for name in (
                        "parsetest.nc",
                        "spindle_testing.nc",
                        "user_io.nc",
                    ):
                        p = REPO_TESTS / name
                        if p.is_file():
                            print(f"soft repo test: {name} ...")
                            cases.append(run_soft_file(client, p))

                if args.with_validator and validator:
                    for nc in collect_pass_files():
                        ok, out = run_validator(nc, validator)
                        cases.append(
                            CaseResult(
                                name=f"validator:{nc.name}",
                                kind="pass",
                                passed=ok,
                                detail="" if ok else out[:300],
                            )
                        )
    finally:
        client.close()
        if sim_proc is not None:
            sim_proc.terminate()
            try:
                sim_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                sim_proc.kill()

    report_path = RESULTS_DIR / "last_report.json"
    report_path.write_text(json.dumps([asdict(c) for c in cases], indent=2), encoding="utf-8")
    print(f"wrote {report_path}")

    if integrity_inject:
        # Invert: inject cases are "false green" scripts — each must fail (passed=False)
        if not cases:
            print("INTEGRITY_INJECT: no cases ran", file=sys.stderr)
            return 1
        leaked = [c for c in cases if c.passed]
        red = [c for c in cases if not c.passed]
        integ = {
            "suite": "integrity_inject",
            "passed": len(leaked) == 0 and len(red) > 0,
            "n": len(cases),
            "n_red_as_expected": len(red),
            "n_leaked_false_green": len(leaked),
            "cases": [
                {
                    "name": c.name,
                    "case_passed_as_normal": c.passed,
                    "detail": c.detail,
                    "integrity": "LEAK" if c.passed else "RED_OK",
                }
                for c in cases
            ],
        }
        integ_path = RESULTS_DIR / "integrity_inject_last.json"
        integ_path.write_text(
            json.dumps(integ, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {integ_path}")
        print(
            f"INTEGRITY_INJECT: red={len(red)}/{len(cases)} "
            f"leaked_false_green={len(leaked)}"
        )
        if leaked:
            print("INTEGRITY_FAIL: harness accepted false-green cases:")
            for c in leaked:
                print(f"  - {c.name}")
            return 1
        print("INTEGRITY_PASS: all inject packs failed as required")
        return 0

    code = print_report(cases)

    # R19 golden summary (hard; already in exit code via print_report)
    golden_cases = [c for c in cases if c.kind == "golden"]
    if golden_cases:
        gold_rep = {
            "suite": "golden",
            "passed": all(c.passed for c in golden_cases),
            "n": len(golden_cases),
            "n_fail": sum(1 for c in golden_cases if not c.passed),
            "cases": [
                {"name": c.name, "passed": c.passed, "detail": c.detail} for c in golden_cases
            ],
        }
        gold_path = RESULTS_DIR / "golden_last.json"
        gold_path.write_text(
            json.dumps(gold_rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {gold_path} (fail={gold_rep['n_fail']}/{gold_rep['n']})")

    # soft divergence summary for agents (never affects exit code)
    soft_cases = [c for c in cases if c.kind == "soft"]
    div = {
        "suite": "soft_divergence",
        "files": [],
        "total_err_lines": 0,
        "high_divergence": [],
    }
    for c in soft_cases:
        n_ok, n_err = 0, 0
        import re as _re
        m = _re.search(r"ok_lines=(\d+)\s+err_lines=(\d+)", c.detail or "")
        if m:
            n_ok, n_err = int(m.group(1)), int(m.group(2))
        entry = {
            "name": c.name,
            "ok_lines": n_ok,
            "err_lines": n_err,
            "detail": c.detail,
        }
        div["files"].append(entry)
        div["total_err_lines"] += n_err
        if n_err > 0 and (n_ok + n_err) > 0 and n_err / (n_ok + n_err) >= 0.5:
            div["high_divergence"].append(c.name)
    soft_path = RESULTS_DIR / "soft_divergence.json"
    soft_path.write_text(
        json.dumps(div, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {soft_path} (err_lines={div['total_err_lines']})")
    if div["high_divergence"]:
        print("SOFT_HIGH_DIVERGENCE:", ", ".join(div["high_divergence"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
