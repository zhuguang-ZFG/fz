"""硬件报告三态口径；兼容旧报告中明确写出的跳过标记。"""


def case_status(case: dict) -> str:
    if case.get("skipped") is True:
        return "skip"
    detail = str(case.get("detail") or "").lower()
    if (detail.startswith("skipped (") or case.get("name") == "session_meta_skipped"):
        return "skip"
    return "pass" if case.get("passed") is True else "fail"


def case_counts(cases) -> dict:
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for case in cases:
        status = case_status(case)
        counts[{"pass": "passed", "fail": "failed", "skip": "skipped"}[status]] += 1
    counts["executed"] = counts["passed"] + counts["failed"]
    counts["total"] = counts["executed"] + counts["skipped"]
    return counts
