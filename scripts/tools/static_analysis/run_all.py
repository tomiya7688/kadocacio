"""Run the repository's pre-commit static checks from one entry point."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from scripts.tools.static_analysis.reporting import (
    summarize_flake8,
    summarize_pytest,
    write_reports,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_DIR = ROOT / "static_analysis" / "reports"


def default_checks(
    python: str = sys.executable,
    *,
    report_dir: Path | None = None,
) -> tuple[dict, ...]:
    pytest_command = [python, "-m", "pytest", "-q"]
    if report_dir is not None:
        pytest_command.append(f"--junitxml={report_dir / 'pytest_junit.xml'}")
    return (
        {
            "name": "flake8",
            "command": (
                python,
                "-m",
                "flake8",
                ".",
                "--count",
                "--select=E9,F63,F7,F82",
                "--show-source",
                "--statistics",
            ),
        },
        {
            "name": "compileall",
            "command": (python, "-m", "compileall", "-q", "main.py", "scripts"),
        },
        {
            "name": "architecture-boundary",
            "command": (python, "-m", "scripts.tools.static_analysis.architecture_boundary"),
        },
        {
            "name": "upd-commander",
            "command": (python, "-m", "scripts.tools.static_analysis.upd_checker"),
        },
        {"name": "pytest", "command": tuple(pytest_command)},
    )


def run_check(check: dict, report_dir: Path | None = None) -> dict:
    name = str(check["name"])
    command = tuple(check["command"])
    print(f"\n== {name} ==")
    print("$ " + " ".join(command))
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    duration = time.perf_counter() - started
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")

    stdout_log = ""
    stderr_log = ""
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = report_dir / f"{name}.stdout.log"
        stderr_path = report_dir / f"{name}.stderr.log"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        stdout_log = str(stdout_path.relative_to(ROOT))
        stderr_log = str(stderr_path.relative_to(ROOT))

    return {
        "name": name,
        "command": list(command),
        "returncode": completed.returncode,
        "duration_seconds": round(duration, 3),
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "_stdout": completed.stdout,
        "_stderr": completed.stderr,
    }


def run_all(
    checks: Sequence[dict],
    *,
    keep_going: bool = False,
    report_dir: Path | None = DEFAULT_REPORT_DIR,
) -> int:
    results: list[dict] = []
    for check in checks:
        result = run_check(check, report_dir)
        results.append(result)
        if result["returncode"] and not keep_going:
            break

    pytest_summary = None
    flake8_summary = None
    for item in results:
        output = item["_stdout"] + "\n" + item["_stderr"]
        if item["name"] == "flake8":
            flake8_summary = summarize_flake8(output)
        elif item["name"] == "pytest" and report_dir is not None:
            pytest_summary = summarize_pytest(report_dir / "pytest_junit.xml", output)

    public_results = [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in results
    ]
    print("\n== summary ==")
    failed = [item for item in public_results if item["returncode"] != 0]
    if not failed:
        print("STATIC ANALYSIS: PASS")
    else:
        print("STATIC ANALYSIS: FAIL")
        for item in failed:
            print(f"- {item['name']}: exit {item['returncode']}")

    if report_dir is not None:
        json_path, md_path = write_reports(
            public_results,
            report_dir,
            pytest_summary=pytest_summary,
            flake8_summary=flake8_summary,
        )
        print(f"Summary JSON: {json_path.relative_to(ROOT)}")
        print(f"Summary Markdown: {md_path.relative_to(ROOT)}")

    return 0 if not failed else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="directory for JSON/Markdown/JUnit/log reports",
    )
    parser.add_argument(
        "--no-reports",
        action="store_true",
        help="disable generated reports",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report_dir = None if args.no_reports else args.report_dir
    return run_all(
        default_checks(report_dir=report_dir),
        keep_going=args.keep_going,
        report_dir=report_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
