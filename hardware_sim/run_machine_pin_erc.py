#!/usr/bin/env python3
"""EDA-style electrical-rule checking for the product machine pin map."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

HERE = Path(__file__).resolve().parent
FZ_ROOT = HERE.parent
RESULTS = HERE / "results"
DEFAULT_CONTRACT = HERE / "machine_pin_contract.json"
DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+([^\s/]+)", re.MULTILINE)
GPIO = re.compile(r"GPIO_NUM_(\d+)$")
I2SO = re.compile(r"I2SO\((\d+)\)$")
INPUT_ONLY = set(range(34, 40))
DAC = {25, 26}
STRAPPING = {0, 2, 5, 12, 15}
VALID_GPIO = set(range(0, 20)) | {21, 22, 23, 25, 26, 27} | set(range(32, 40))
FLASH_GPIO = set(range(6, 12))
ENDPOINT = re.compile(r"(?:GPIO\d+|I2SO\d+)$")
DIRECTIONS = {"input", "output", "dac_output"}
REMEDIATION = {
    "alias_drift": "Restore the declared alias chain or update the reviewed contract with the firmware change.",
    "contract_schema": "Fix machine_pin_contract.json before relying on this ERC result.",
    "input_only_output": "Move the output to an output-capable GPIO or change the role direction if it is truly input-only.",
    "invalid_dac_pin": "Use ESP32 DAC GPIO25/GPIO26 or change the role from dac_output.",
    "invalid_gpio": "Use a bonded ESP32 GPIO; GPIO20/24/28-31 and values above GPIO39 are unavailable.",
    "flash_reserved_gpio": "Move the signal off GPIO6-GPIO11, which are normally reserved for module flash wiring.",
    "i2so_out_of_range": "Use an I2SO index within the configured expander width.",
    "pin_collision": "Assign unique physical endpoints unless the relationship is an explicit alias.",
    "pin_drift": "Review the firmware pin change and update the contract only with matching hardware evidence.",
    "stale_strapping_waiver": "Remove or refresh the waiver so it matches a current strapping-pin output role and endpoint.",
    "strapping_output": "Add an endpoint-bound waiver with a concrete reason only after boot-state electrical review.",
    "uncontracted_pin_macro": "Classify the new pin macro as a role or alias; unknown physical nets fail closed.",
    "unresolved_alias": "Restore the alias target chain or remove the stale alias contract entry.",
    "unresolved_pin": "Restore the machine pin macro or remove the stale role after review.",
}


def parse_defines(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    conflicts: set[str] = set()
    for name, value in DEFINE.findall(text):
        if name in values and values[name] != value:
            conflicts.add(name)
        values[name] = value
    if conflicts:
        raise ValueError(f"conflicting macro definitions: {sorted(conflicts)}")
    return values


def resolve(name: str, defines: Mapping[str, str], stack: Optional[List[str]] = None) -> str:
    stack = list(stack or [])
    if name in stack:
        raise ValueError(f"macro alias cycle: {stack + [name]}")
    token = defines.get(name)
    if token is None:
        raise ValueError(f"missing pin macro: {name}")
    gpio = GPIO.fullmatch(token)
    if gpio:
        return f"GPIO{int(gpio.group(1))}"
    i2so = I2SO.fullmatch(token)
    if i2so:
        return f"I2SO{int(i2so.group(1))}"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
        return resolve(token, defines, stack + [name])
    raise ValueError(f"unsupported pin expression for {name}: {token}")


def load_contract(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 2 or not isinstance(data.get("roles"), dict):
        raise ValueError("machine pin ERC contract version must be 2 with roles object")
    return data


def _contract_schema_errors(contract: Mapping[str, Any]) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    roles = contract.get("roles", {})
    aliases = contract.get("aliases", {})
    waivers = contract.get("strapping_output_waivers", {})
    if not isinstance(contract.get("machine"), str) or not str(contract.get("machine", "")).strip():
        errors.append({"kind": "contract_schema", "detail": "machine must be a non-empty relative path"})
    if not isinstance(contract.get("i2so_width"), int) or int(contract.get("i2so_width", 0)) <= 0:
        errors.append({"kind": "contract_schema", "detail": "i2so_width must be a positive integer"})
    if not isinstance(aliases, dict) or not isinstance(waivers, dict):
        return [{"kind": "contract_schema", "detail": "aliases and strapping_output_waivers must be objects"}]
    overlap = sorted(set(roles) & set(aliases))
    if overlap:
        errors.append({"kind": "contract_schema", "detail": "roles and aliases overlap", "names": overlap})
    for name, rule in roles.items():
        if not isinstance(rule, dict) or not ENDPOINT.fullmatch(str(rule.get("endpoint", ""))) or rule.get("direction") not in DIRECTIONS:
            errors.append({"kind": "contract_schema", "role": name, "detail": "role requires GPIO/I2SO endpoint and input/output/dac_output direction"})
    for role, waiver in waivers.items():
        if not isinstance(waiver, dict) or not ENDPOINT.fullmatch(str(waiver.get("endpoint", ""))) or not str(waiver.get("reason", "")).strip():
            errors.append({"kind": "contract_schema", "role": role, "detail": "strapping waiver requires endpoint and non-empty reason"})
    return errors


def validate_contract(contract: Mapping[str, Any], grbl_root: Path) -> Dict[str, Any]:
    root = grbl_root.resolve()
    machine = (root / str(contract["machine"])).resolve()
    if machine != root and root not in machine.parents:
        raise ValueError(f"machine path escapes GRBL_ROOT: {contract['machine']}")
    defines = parse_defines(machine.read_text(encoding="utf-8", errors="replace"))
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    observed: Dict[str, str] = {}
    endpoint_roles: Dict[str, List[str]] = {}
    errors.extend(_contract_schema_errors(contract))
    aliases = contract.get("aliases", {}) if isinstance(contract.get("aliases"), dict) else {}
    strapping_waivers = contract.get("strapping_output_waivers", {}) if isinstance(contract.get("strapping_output_waivers"), dict) else {}
    width = contract.get("i2so_width", 0) if isinstance(contract.get("i2so_width"), int) else 0
    for name, rule in contract["roles"].items():
        if not isinstance(rule, dict):
            continue
        try:
            endpoint = resolve(name, defines)
        except ValueError as exc:
            errors.append({"kind": "unresolved_pin", "role": name, "detail": str(exc)})
            continue
        observed[name] = endpoint
        endpoint_roles.setdefault(endpoint, []).append(name)
        if endpoint != rule.get("endpoint"):
            errors.append({"kind": "pin_drift", "role": name, "expected": rule.get("endpoint"), "actual": endpoint})
        direction = rule.get("direction")
        if endpoint.startswith("GPIO"):
            number = int(endpoint[4:])
            if number not in VALID_GPIO:
                errors.append({"kind": "invalid_gpio", "role": name, "endpoint": endpoint})
            if number in FLASH_GPIO:
                errors.append({"kind": "flash_reserved_gpio", "role": name, "endpoint": endpoint})
            if direction in {"output", "dac_output"} and number in INPUT_ONLY:
                errors.append({"kind": "input_only_output", "role": name, "endpoint": endpoint})
            if direction == "dac_output" and number not in DAC:
                errors.append({"kind": "invalid_dac_pin", "role": name, "endpoint": endpoint})
            if direction in {"output", "dac_output"} and number in STRAPPING:
                waiver = strapping_waivers.get(name)
                reviewed = isinstance(waiver, dict) and waiver.get("endpoint") == endpoint
                finding = {"kind": "strapping_output", "role": name, "endpoint": endpoint, "reviewed": reviewed}
                if reviewed:
                    finding["reason"] = waiver["reason"]
                (warnings if reviewed else errors).append(finding)
        elif endpoint.startswith("I2SO") and int(endpoint[4:]) >= width:
            errors.append({"kind": "i2so_out_of_range", "role": name, "endpoint": endpoint, "width": width})
    for endpoint, names in endpoint_roles.items():
        if len(names) > 1:
            errors.append({"kind": "pin_collision", "endpoint": endpoint, "roles": names})
    observed_aliases: Dict[str, str] = {}
    for alias, target in aliases.items():
        try:
            alias_endpoint = resolve(alias, defines)
            target_endpoint = resolve(str(target), defines)
            observed_aliases[alias] = alias_endpoint
            if alias_endpoint != target_endpoint:
                errors.append({"kind": "alias_drift", "alias": alias, "target": target, "alias_endpoint": alias_endpoint, "target_endpoint": target_endpoint})
        except ValueError as exc:
            errors.append({"kind": "unresolved_alias", "alias": alias, "detail": str(exc)})
    declared = set(contract["roles"]) | set(aliases)
    resolvable: Dict[str, str] = {}
    for name in defines:
        try:
            resolvable[name] = resolve(name, defines)
        except ValueError:
            pass
    uncontracted = {name: resolvable[name] for name in sorted(set(resolvable) - declared)}
    if uncontracted:
        errors.append({"kind": "uncontracted_pin_macro", "macros": uncontracted})
    for role, waiver in strapping_waivers.items():
        rule = contract["roles"].get(role)
        endpoint = observed.get(role)
        is_current = (
            isinstance(waiver, dict)
            and
            isinstance(rule, dict)
            and rule.get("direction") in {"output", "dac_output"}
            and endpoint == waiver.get("endpoint")
            and endpoint is not None
            and endpoint.startswith("GPIO")
            and int(endpoint[4:]) in STRAPPING
        )
        if not is_current:
            errors.append({"kind": "stale_strapping_waiver", "role": role, "waived_endpoint": waiver.get("endpoint") if isinstance(waiver, dict) else None, "actual_endpoint": endpoint})
    actions = [REMEDIATION[kind] for kind in sorted({item["kind"] for item in errors}) if kind in REMEDIATION]
    coverage_total = len(resolvable)
    return {
        "suite": "machine_pin_erc",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not errors else "fail",
        "machine": str(machine.resolve()),
        "observed_roles": observed,
        "observed_aliases": observed_aliases,
        "errors": errors,
        "warnings": warnings,
        "waivers": [{"kind": "reviewed_strapping_output", "role": item["role"], "endpoint": item["endpoint"], "reason": item["reason"]} for item in warnings],
        "coverage": {
            "resolvable_pin_macros": coverage_total,
            "contracted_pin_macros": coverage_total - len(uncontracted),
            "uncontracted_pin_macros": len(uncontracted),
            "percent": round(100.0 * (coverage_total - len(uncontracted)) / coverage_total, 2) if coverage_total else 100.0,
        },
        "next_actions": actions,
        "evidence_boundary": contract.get("evidence_boundary"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EDA-style machine pin ERC")
    parser.add_argument("--grbl-root", type=Path, default=Path("D:/Users/Grbl_Esp32"))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = validate_contract(load_contract(args.contract), args.grbl_root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"suite": "machine_pin_erc", "timestamp": datetime.now(timezone.utc).isoformat(), "status": "fail", "errors": [{"kind": "invalid_contract", "detail": str(exc)}], "warnings": []}
    path = args.json_out or RESULTS / "machine_pin_erc.json"
    if not path.is_absolute():
        path = FZ_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
