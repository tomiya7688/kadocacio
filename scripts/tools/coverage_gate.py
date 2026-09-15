"""Summarize branch coverage separately for game code and developer tools."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


GAME_PREFIXES = (
    "scripts/app/",
    "scripts/core/",
    "scripts/league/",
    "scripts/match/",
    "scripts/team/",
)
TOOLS_PREFIXES = ("scripts/tools/",)


@dataclass(frozen=True)
class BranchCoverage:
    label: str
    covered: int
    total: int

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 100.0
        return self.covered * 100.0 / self.total


def summarize_group(
    files: dict[str, dict],
    *,
    label: str,
    prefixes: Iterable[str],
) -> BranchCoverage:
    prefixes = tuple(prefixes)
    covered = 0
    total = 0
    for path, payload in files.items():
        normalized = path.replace("\\", "/")
        if not normalized.startswith(prefixes):
            continue
        summary = payload.get("summary", {})
        covered += int(summary.get("covered_branches", 0))
        total += int(summary.get("num_branches", 0))
    return BranchCoverage(label=label, covered=covered, total=total)


def load_report(path: Path) -> tuple[BranchCoverage, BranchCoverage]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage JSON does not contain a files mapping")
    return (
        summarize_group(files, label="game", prefixes=GAME_PREFIXES),
        summarize_group(files, label="developer-tools", prefixes=TOOLS_PREFIXES),
    )


def check_minimum(metric: BranchCoverage, minimum: float | None) -> bool:
    return minimum is None or metric.percent >= minimum


def run(
    report: Path,
    *,
    min_game: float | None = None,
    min_tools: float | None = None,
) -> int:
    game, tools = load_report(report)
    print(
        f"game branch coverage: {game.percent:.1f}% "
        f"({game.covered}/{game.total})"
    )
    print(
        f"developer-tools branch coverage: {tools.percent:.1f}% "
        f"({tools.covered}/{tools.total})"
    )

    failed: list[str] = []
    if not check_minimum(game, min_game):
        failed.append(f"game {game.percent:.1f}% < {min_game:.1f}%")
    if not check_minimum(tools, min_tools):
        failed.append(f"developer-tools {tools.percent:.1f}% < {min_tools:.1f}%")

    if failed:
        print("BRANCH COVERAGE: FAIL")
        for item in failed:
            print(f"- {item}")
        return 1

    print("BRANCH COVERAGE: PASS")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?", default=Path("coverage.json"))
    parser.add_argument("--min-game", type=float)
    parser.add_argument("--min-tools", type=float)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run(
        args.report,
        min_game=args.min_game,
        min_tools=args.min_tools,
    )


if __name__ == "__main__":
    raise SystemExit(main())
