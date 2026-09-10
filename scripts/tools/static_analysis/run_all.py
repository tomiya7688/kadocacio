"""Run the repository's pre-commit static checks from one entry point."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]


def default_checks(python: str = sys.executable) -> tuple[Check, ...]:
    """Return checks shared with GitHub Actions, in execution order."""
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
        Check("pytest", (python, "-m", "pytest", "-q")),
    )


def run_check(check: Check) -> int:
    print(f"\n== {check.name} ==")
    print("$ " + " ".join(check.command))
    completed = subprocess.run(check.command, cwd=ROOT, check=False)
    return completed.returncode


def run_all(checks: Sequence[Check], *, keep_going: bool = False) -> int:
    failures: list[tuple[str, int]] = []
    for check in checks:
        code = run_check(check)
        if code:
            failures.append((check.name, code))
            if not keep_going:
                break

    print("\n== summary ==")
    if not failures:
        print("STATIC ANALYSIS: PASS")
        return 0

    print("STATIC ANALYSIS: FAIL")
    for name, code in failures:
        print(f"- {name}: exit {code}")
    return 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="run remaining checks after a failure",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_all(default_checks(), keep_going=args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main())
