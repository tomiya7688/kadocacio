"""Export/check the Match boundary specification for the native Godot consumer."""

import argparse
import json
from pathlib import Path

from scripts.core.match_protocol import protocol_definition
from scripts.core.paths import PROJECT_ROOT
from scripts.match.player_command import PlayerCommand
from scripts.core.settings import FIELD, GAME_CLOCK_RATE, MATCH_SECONDS
from scripts.match.stamina_system import stamina_capacity

CONTRACT_PATH = PROJECT_ROOT / "godot/data/match_contract.json"


def contract_text() -> str:
    return json.dumps({**protocol_definition(), "player_commands": {command.name: command.value for command in PlayerCommand},
                       "kernel": {"field": [FIELD.left, FIELD.top, FIELD.width, FIELD.height],
                                  "clock_rate": GAME_CLOCK_RATE, "match_seconds": MATCH_SECONDS,
                                  "stamina_base": stamina_capacity(0.0), "stamina_span": stamina_capacity(1.0) - stamina_capacity(0.0)}}, ensure_ascii=False, indent=2) + "\n"


def check_contract(path: Path = CONTRACT_PATH) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == contract_text()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(contract_text(), encoding="utf-8")
        print("GODOT MATCH CONTRACT: GENERATED")
        return 0
    valid = check_contract()
    print("GODOT MATCH CONTRACT: PASS" if valid else "GODOT MATCH CONTRACT: STALE")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
