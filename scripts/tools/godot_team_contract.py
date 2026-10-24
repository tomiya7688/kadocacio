"""Export/check the Godot data contract from the Python reference (no team writes)."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Sequence

from scripts.core import stat_scale
from scripts.core.paths import PROJECT_ROOT
from scripts.core.settings import HOME_RED, TACTIC_NAMES
from scripts.match.player_style_system import LEGACY_TYPE_MAP, PLAYER_TYPES, STYLE_FIELDS, TYPE_PREFERENCES
from scripts.match.skill_system import ALL_SKILLS, LEGACY_SKILL_ALIASES
from scripts.team.team_data import PLAYER_KEY_ALIASES, PLAYER_STAT_CANONICAL_KEYS
from scripts.team.uniform_data import UNIFORM_PART_SIZES, UNIFORM_VERSION


CONTRACT_PATH = PROJECT_ROOT / "godot" / "data" / "team_contract.json"


def stat_fallbacks() -> dict[str, str]:
    """Extract constant player_stat calls, rather than duplicate their grouping."""
    tree = ast.parse((PROJECT_ROOT / "scripts" / "match" / "player.py").read_text(encoding="utf-8"))
    result = {key: "Kick" for key in PLAYER_STAT_CANONICAL_KEYS}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "player_stat":
            continue
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
            continue
        key = node.args[1].value
        if not isinstance(key, str):
            continue
        for keyword in node.keywords:
            if keyword.arg == "legacy_key" and isinstance(keyword.value, ast.Constant):
                result[key] = keyword.value.value
    result.update({key: key for key in STYLE_FIELDS.values()})
    return result


def build_contract() -> dict:
    return {
        "contract_version": 1,
        "scale": {
            "current": stat_scale.current_scale_metadata(),
            "legacy_min": stat_scale.LEGACY_PLAYER_STAT_MIN,
            "legacy_max": stat_scale.LEGACY_PLAYER_STAT_MAX,
            "metadata_key": stat_scale.STAT_SCALE_METADATA_KEY,
            "player_default": stat_scale.PLAYER_STAT_DEFAULT,
            "manager_activity_default": stat_scale.MANAGER_ACTIVITY_DEFAULT,
            "manager_intelligence_default": stat_scale.MANAGER_INTELLIGENCE_DEFAULT,
            "grades": stat_scale.PLAYER_GRADE_THRESHOLDS,
        },
        "player_aliases": PLAYER_KEY_ALIASES,
        "stat_keys": PLAYER_STAT_CANONICAL_KEYS,
        "stat_fallbacks": stat_fallbacks(),
        "tactics": TACTIC_NAMES,
        "default_color": HOME_RED,
        "player_types": PLAYER_TYPES,
        "type_aliases": LEGACY_TYPE_MAP,
        "type_preferences": TYPE_PREFERENCES,
        "style_fields": STYLE_FIELDS,
        "skills": ALL_SKILLS,
        "skill_aliases": LEGACY_SKILL_ALIASES,
        "uniform": {"version": UNIFORM_VERSION, "parts": UNIFORM_PART_SIZES},
    }


def contract_text() -> str:
    return json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n"


def check_contract(path: Path = CONTRACT_PATH) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == contract_text()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Explicitly regenerate only the derived Godot contract")
    args = parser.parse_args(argv)
    if args.write:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(contract_text(), encoding="utf-8")
        print(f"GODOT CONTRACT: GENERATED {CONTRACT_PATH}")
        return 0
    if check_contract():
        print("GODOT CONTRACT: PASS")
        return 0
    print("GODOT CONTRACT: STALE; run python -m scripts.tools.godot_team_contract --write")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
