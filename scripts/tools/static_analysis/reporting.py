"""Helpers for compact human- and machine-readable check reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""

    @property
    def status(self) -> str:
        return "PASS" if self.returncode == 0 else "FAIL"


def write_reports(results: Iterable[CheckResult], report_dir: Path) -> tuple[Path, Path]:
    """Write compact JSON and Markdown summaries and return their paths."""
    result_list = list(results)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "check_summary.json"
    md_path = report_dir / "check_summary.md"

    overall = "PASS" if all(item.returncode == 0 for item in result_list) else "FAIL"
    payload = {
        "status": overall,
        "checks": [
            {
                **asdict(item),
                "status": item.status,
                "command": list(item.command),
            }
            for item in result_list
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = ["# Pre-commit check summary", "", f"**STATUS: {overall}**", ""]
    for item in result_list:
        lines.extend(
            [
                f"## {item.name}: {item.status}",
                f"- exit code: {item.returncode}",
                f"- duration: {item.duration_seconds:.2f}s",
                f"- command: `{' '.join(item.command)}`",
                "",
            ]
        )
        output = (item.stdout + ("\n" if item.stdout and item.stderr else "") + item.stderr).strip()
        if output and item.returncode != 0:
            lines.extend(["```text", output[-4000:], "```", ""])

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, md_path
