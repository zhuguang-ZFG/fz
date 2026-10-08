"""发布输入严格解析；不把损坏的YAML回落为更宽松的文本猜测。"""
import json
import re
from datetime import date, datetime
from pathlib import Path


def load_mapping(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("文件为空")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复字段：{key}")
            result[key] = value
        return result
    if text.lstrip().startswith(("{", "[")):
        data = json.loads(text, object_pairs_hook=unique)
    else:
        try:
            import yaml
        except ImportError:
            raise ValueError("解析YAML需要安装requirements-validation.txt；也可提供JSON") from None
        class Loader(yaml.SafeLoader):
            pass
        def mapping(loader, node):
            return unique([(loader.construct_object(key), loader.construct_object(value))
                           for key, value in node.value])
        Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        try:
            data = yaml.load(text, Loader=Loader)
        except yaml.YAMLError as error:
            raise ValueError("YAML结构错误") from error
    if not isinstance(data, dict):
        raise ValueError("顶层必须是对象")
    return data


def load_scope(path: Path) -> dict:
    data = load_mapping(path)
    features = data.get("features")
    if not isinstance(features, dict):
        raise ValueError("scope缺少features对象")
    for name in ("paper_path", "bluetooth", "ota"):
        if type(features.get(name)) is not bool:
            raise ValueError(f"features.{name}必须显式为布尔值")
    for key in ("fz_git_sha", "grbl_git_sha"):
        if key in data and (not isinstance(data[key], str) or not re.fullmatch(r"[0-9a-fA-F]{7,40}", data[key])):
            raise ValueError(f"scope.{key}必须为有效源码SHA")
    return data


def _filled(value) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and value.strip().lower() not in {"n/a", "na", "none", "unknown", "-"}
            and not re.search(r"\b(todo|tbd|sample|template)\b|YYYYMMDD|<[^>]+>", value, re.I))


def validate_signoff_evidence(path: Path, features: dict, kind: str, root: Path, expected_sha: str):
    """复用G3/G4必测项；签核另检查身份和可读取的逐项证据。"""
    errors = []
    try:
        data = load_mapping(path)
        if kind == "g3":
            from g3_evidence import validate_g3_evidence
            status, report = validate_g3_evidence(path, features)
        else:
            from g4_ota import validate_g4_evidence
            status, report = validate_g4_evidence(path, features)
        if status != "pass":
            errors.extend(report.get("errors") or [report.get("error", "必测项未通过")])
        required_fields = ["version", "operator", "grbl_git_sha"]
        required_fields += ["board", "machine", "firmware_banner"] if kind == "g3" else ["from_version", "to_version", "artifact_sha256_16"]
        for key in required_fields:
            if not _filled(data.get(key)):
                errors.append(f"{key}缺失或仍为模板/示例")
        try:
            recorded_date = data.get("date")
            if isinstance(recorded_date, datetime):
                recorded_date = recorded_date.date()
            elif not isinstance(recorded_date, date):
                recorded_date = date.fromisoformat(str(recorded_date))
            if recorded_date > date.today():
                raise ValueError("未来日期")
        except (ValueError, TypeError):
            errors.append("date须为已经发生的有效日期")
        sha = data.get("grbl_git_sha")
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{7,40}", sha)
                and isinstance(expected_sha, str) and len(expected_sha) == 40
                and expected_sha.lower().startswith(sha.lower())):
            errors.append("证据grbl_git_sha与门禁产品源码不符")
        if kind == "g4" and not re.fullmatch(r"[0-9a-fA-F]{16,64}", str(data.get("artifact_sha256_16", ""))):
            errors.append("artifact_sha256_16缺失或格式错误")
        rows = data.get("items")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("items必须为对象列表")
        ids = [row.get("id") for row in rows]
        if any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("验收项id缺失或重复")
        by_id = {row["id"]: row for row in rows}
        for key in report.get("required", []):
            item = by_id.get(key, {})
            if item.get("result") != "pass":
                errors.append(f"{key}尚未通过，不能声明HIL完成")
                continue
            ref = item.get("evidence")
            if not _filled(ref):
                errors.append(f"{key}缺少证据文件")
                continue
            candidate = Path(ref)
            candidates = [candidate] if candidate.is_absolute() else [path.parent / candidate, root / candidate]
            matches = {value.resolve() for value in candidates if value.is_file()}
            if len(matches) != 1:
                errors.append(f"{key}证据缺失或路径歧义")
                continue
            actual = matches.pop()
            if actual == path.resolve() or not actual.read_bytes().strip():
                errors.append(f"{key}证据为空或自引用")
        return not errors, {"status": "fail" if errors else "pass", "errors": errors, "required": report.get("required", [])}
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, ImportError) as error:
        return False, {"status": "fail", "errors": [f"{type(error).__name__}: {error}"]}
