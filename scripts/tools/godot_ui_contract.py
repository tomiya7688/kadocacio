"""Export/check UI preference choices from the unchanged Python reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from scripts.core.paths import PROJECT_ROOT
from scripts.core.performance_settings import CPU_LIMIT_OPTIONS, DEFAULT_CPU_LIMIT_PERCENT, DEFAULT_LEAGUE_SIMULATION_MODE, LEAGUE_SIMULATION_MODES, normalize_cpu_limit
from scripts.core.settings import WINDOW_SIZE_OPTIONS


CONTRACT_PATH = PROJECT_ROOT / "godot/data/ui_contract.json"


def contract_text() -> str:
    return json.dumps({
        "cpu_options": CPU_LIMIT_OPTIONS,
        "cpu_min": normalize_cpu_limit(-1), "cpu_max": normalize_cpu_limit(1000),
        "cpu_default": DEFAULT_CPU_LIMIT_PERCENT,
        "mode_default": DEFAULT_LEAGUE_SIMULATION_MODE, "modes": LEAGUE_SIMULATION_MODES,
        "window_sizes": WINDOW_SIZE_OPTIONS,
    }, ensure_ascii=False, indent=2) + "\n"


def check_contract(path: Path = CONTRACT_PATH) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == contract_text()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(contract_text(), encoding="utf-8")
        print("GODOT UI CONTRACT: GENERATED")
        return 0
    valid = check_contract()
    print("GODOT UI CONTRACT: PASS" if valid else "GODOT UI CONTRACT: STALE; regenerate with --write")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
