"""Compact reports for the unified pre-commit check runner."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


COUNT_NAMES = ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")


def _terminal_counts(output: str) -> dict[str, int]:
    counts = {name: 0 for name in COUNT_NAMES}
    for amount, name in re.findall(
        r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)\b",
        output,
        flags=re.IGNORECASE,
    ):
        key = "errors" if name.lower().startswith("error") else name.lower()
        counts[key] += int(amount)
    return counts


def summarize_pytest(junit_path: Path, output: str) -> dict:
    counts = _terminal_counts(output)
    failures: list[dict[str, str]] = []
    duration = 0.0

    if junit_path.is_file():
        root = ET.parse(junit_path).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is not None:
            duration = float(suite.attrib.get("time", 0.0) or 0.0)
            if not any(counts.values()):
                total = int(suite.attrib.get("tests", 0) or 0)
                failed = int(suite.attrib.get("failures", 0) or 0)
                errors = int(suite.attrib.get("errors", 0) or 0)
                skipped = int(suite.attrib.get("skipped", 0) or 0)
                counts.update(
                    passed=max(0, total - failed - errors - skipped),
                    failed=failed,
                    errors=errors,
                    skipped=skipped,
                )
            for case in suite.iter("testcase"):
                nodeid = "::".join(
                    part
                    for part in (case.attrib.get("classname", ""), case.attrib.get("name", ""))
                    if part
                )
                problem = case.find("failure")
                kind = "failure"
                if problem is None:
                    problem = case.find("error")
                    kind = "error"
                if problem is None:
                    continue
                failures.append(
                    {
                        "test": nodeid,
                        "file": case.attrib.get("file", ""),
                        "kind": kind,
                        "type": problem.attrib.get("type", ""),
                        "message": problem.attrib.get("message", ""),
                    }
                )

    total = sum(counts.values())
    return {
        "total": total,
        **counts,
        "duration_seconds": round(duration, 3),
        "failures": failures,
    }


def summarize_flake8(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    count = 0
    if lines and lines[-1].strip().isdigit():
        count = int(lines[-1].strip())
    elif lines:
        count = sum(
            1
            for line in lines
            if re.search(r":\d+:\d+:\s+[A-Z]\d+\s+", line)
        )
    return {"violations": count}


def write_reports(
    results: Iterable[dict],
    report_dir: Path,
    *,
    pytest_summary: dict | None = None,
    flake8_summary: dict | None = None,
) -> tuple[Path, Path]:
    items = list(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "precommit_summary.json"
    md_path = report_dir / "precommit_summary.md"
    overall = "PASS" if all(item["returncode"] == 0 for item in items) else "FAIL"

    payload = {
        "status": overall,
        "checks": items,
        "pytest": pytest_summary,
        "flake8": flake8_summary,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = ["# Pre-commit summary", "", f"**STATUS: {overall}**", ""]
    for item in items:
        status = "PASS" if item["returncode"] == 0 else "FAIL"
        lines.append(
            f"- {item['name']}: {status} "
            f"(exit {item['returncode']}, {item['duration_seconds']:.2f}s)"
        )

    if flake8_summary is not None:
        lines.extend(["", f"Lint violations: {flake8_summary['violations']}"])

    if pytest_summary is not None:
        lines.extend(
            [
                "",
                "## Pytest",
                f"- total: {pytest_summary['total']}",
                f"- passed: {pytest_summary['passed']}",
                f"- failed: {pytest_summary['failed']}",
                f"- errors: {pytest_summary['errors']}",
                f"- skipped: {pytest_summary['skipped']}",
                f"- xfailed: {pytest_summary['xfailed']}",
                f"- xpassed: {pytest_summary['xpassed']}",
                f"- duration: {pytest_summary['duration_seconds']:.2f}s",
            ]
        )
        if pytest_summary["failures"]:
            lines.extend(["", "### Failures"])
            for failure in pytest_summary["failures"]:
                detail = failure["type"] or failure["kind"]
                lines.append(f"- {failure['test']} [{detail}]")

    failed_items = [item for item in items if item["returncode"] != 0]
    if failed_items:
        lines.extend(["", "## Detail logs"])
        for item in failed_items:
            lines.append(
                f"- {item['name']}: "
                f"`{item['stdout_log']}`, `{item['stderr_log']}`"
            )

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, md_path
