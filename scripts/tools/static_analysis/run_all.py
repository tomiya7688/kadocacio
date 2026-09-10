"""Run the repository's pre-commit static checks from one entry point."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .reporting import CheckResult, write_reports


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_DIR = ROOT / "static_analysis" / "reports"


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]


def default_checks(python: str = sys.executable) -> tuple[Check, ...]:
    """Return checks shared with GitHub Actions, in execution order."""
    junit = DEFAULT_REPORT_DIR / "pytest_junit.xml"
    return (
        Check(
            "flake8",
            (
                python,
                "-m",
                "flake8",
                ".",
                "--count",
                "--select=E9,F63,F7,F82",
                "--show-source",
                "--statistics",
            ),
        ),
        Check("compileall", (python, "-m", "compileall", "-q", "main.py", "scripts")),
        Check(
            "pytest",
            (python, "-m", "pytest", "-q", f"--junitxml={junit}"),
        ),
    )


def run_check(check: Check) -> CheckResult:
    print(f"\n== {check.name} ==")
    print("$ " + " ".join(check.command))
    started = time.perf_counter()
    completed = subprocess.run(
        check.command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    duration = time.perf_counter() - started

    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")

    return CheckResult(
        name=check.name,
        command=check.command,
        returncode=completed.returncode,
        duration_seconds=duration,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_all(
    checks: Sequence[Check],
    *,
    keep_going: bool = False,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> int:
    results: list[CheckResult] = []
    for check in checks:
        result = run_check(check)
        results.append(result)
        if result.returncode and not keep_going:
            break

    json_path, md_path = write_reports(results, report_dir)
    failures = [item for item in results if item.returncode]

    print("\n== summary ==")
    if not failures:
        print("STATIC ANALYSIS: PASS")
    else:
        print("STATIC ANALYSIS: FAIL")
        for item in failures:
            print(f"- {item.name}: exit {item.returncode}")
    print(f"JSON report: {json_path.relative_to(ROOT)}")
    print(f"Markdown report: {md_path.relative_to(ROOT)}")
    return 1 if failures else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="run remaining checks after a failure",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="directory for JSON/Markdown/JUnit reports",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_all(
        default_checks(),
        keep_going=args.keep_going,
        report_dir=args.report_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
