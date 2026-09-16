from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.core.paths import (
    LEAGUES_PATH,
    LEAGUE_SAVE_DIR,
    LEAGUE_STATE_PATH,
    LEAGUE_TEMPLATE_DIR,
    PROJECT_ROOT,
    TEAMS_DIR,
)
from scripts.team.team_identity import ensure_team_identity, legacy_team_id


def _replace_identifiers(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {
            replacements.get(str(key), key): _replace_identifiers(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_identifiers(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def migrate_team_tree(
    teams_root: Path,
    reference_paths: list[Path] | tuple[Path, ...] = (),
) -> dict[str, str]:
    """Persist permanent IDs and migrate JSON references from legacy path IDs."""
    teams_root = Path(teams_root).resolve()
    replacements: dict[str, str] = {}
    team_id_sources: dict[str, Path] = {}

    for path in sorted(teams_root.rglob("*.json")):
        with path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise ValueError(f"チームJSONの最上位がオブジェクトではありません: {path}")
        relative = path.relative_to(teams_root).as_posix()
        old_id = legacy_team_id(relative)
        before = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        team_id = ensure_team_identity(payload, legacy_id=old_id, deterministic=True)
        previous = team_id_sources.get(team_id)
        if previous is not None and previous != path:
            raise ValueError(f"チームIDが重複しています: {team_id}: {previous} / {path}")
        team_id_sources[team_id] = path
        replacements[old_id] = team_id
        after = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if before != after:
            _write_json(path, payload)

    for reference in dict.fromkeys(Path(path) for path in reference_paths):
        if not reference.is_file():
            continue
        with reference.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
        replaced = _replace_identifiers(payload, replacements)
        if replaced != payload:
            _write_json(reference, replaced)
    return replacements


def default_reference_paths() -> list[Path]:
    root = PROJECT_ROOT
    paths = [
        LEAGUES_PATH,
        LEAGUE_STATE_PATH,
        root / "leagues.json",
        root / "league_state.json",
    ]
    for directory in (
        LEAGUE_TEMPLATE_DIR,
        LEAGUE_SAVE_DIR,
        root / "league_templates",
        root / "league_save",
    ):
        if directory.is_dir():
            paths.extend(directory.glob("*.json"))
    return list(dict.fromkeys(Path(path) for path in paths))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate path-based team IDs to permanent IDs")
    parser.add_argument("--teams-root", type=Path, default=TEAMS_DIR)
    parser.add_argument("--no-reference-update", action="store_true")
    args = parser.parse_args()
    references = [] if args.no_reference_update else default_reference_paths()
    replacements = migrate_team_tree(args.teams_root, references)
    print(f"Migrated {len(replacements)} team IDs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
