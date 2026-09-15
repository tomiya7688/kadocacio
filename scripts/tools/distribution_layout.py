"""Stage and validate the user-facing layout of a Windows distribution build."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
USER_DATA_DIRS = (
    Path("user_data/teams"),
    Path("user_data/saves"),
    Path("user_data/config"),
    Path("user_data/exports"),
    Path("user_data/logs"),
)
SEEDED_USER_FILES = (
    (Path("performance_settings.json"), Path("user_data/config/performance_settings.json")),
    (Path("leagues.json"), Path("user_data/config/leagues.json")),
    (Path("league_state.json"), Path("user_data/saves/league_state.json")),
)
REQUIRED_INTERNAL_DIRS = (
    Path("_internal/assets"),
    Path("_internal/teams"),
    Path("_internal/teameditor_templete"),
)
REQUIRED_INTERNAL_FILES = (
    Path("_internal/performance_settings.json"),
    Path("_internal/leagues.json"),
    Path("_internal/league_state.json"),
)
ALLOWED_ROOT_ENTRIES = {"Kadocacio.exe", "_internal", "user_data"}


def stage_user_data(build_root: Path, source_root: Path = ROOT) -> None:
    """Create user-owned directories and seed editable configuration files."""
    build_root = Path(build_root)
    source_root = Path(source_root)
    if not build_root.is_dir():
        raise FileNotFoundError(f"distribution root does not exist: {build_root}")

    for relative in USER_DATA_DIRS:
        (build_root / relative).mkdir(parents=True, exist_ok=True)

    for source_relative, target_relative in SEEDED_USER_FILES:
        source = source_root / source_relative
        if not source.is_file():
            raise FileNotFoundError(f"required source file is missing: {source}")
        target = build_root / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def _validate_json(path: Path, label: str, errors: list[str]) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON: {label}: {exc}")


def validate_distribution(build_root: Path) -> list[str]:
    """Return human-readable errors for an invalid distribution layout."""
    build_root = Path(build_root)
    errors: list[str] = []

    if not build_root.is_dir():
        return [f"distribution root does not exist: {build_root}"]

    executable = build_root / "Kadocacio.exe"
    if not executable.is_file():
        errors.append("missing Kadocacio.exe")

    for relative in USER_DATA_DIRS:
        if not (build_root / relative).is_dir():
            errors.append(f"missing directory: {relative.as_posix()}")

    for _, target_relative in SEEDED_USER_FILES:
        target = build_root / target_relative
        if not target.is_file():
            errors.append(f"missing user data file: {target_relative.as_posix()}")
            continue
        _validate_json(target, target_relative.as_posix(), errors)

    for relative in REQUIRED_INTERNAL_DIRS:
        directory = build_root / relative
        if not directory.is_dir():
            errors.append(f"missing internal directory: {relative.as_posix()}")
        elif not _has_files(directory):
            errors.append(f"internal directory is empty: {relative.as_posix()}")

    for relative in REQUIRED_INTERNAL_FILES:
        path = build_root / relative
        if not path.is_file():
            errors.append(f"missing internal file: {relative.as_posix()}")
            continue
        _validate_json(path, relative.as_posix(), errors)

    unexpected = sorted(
        entry.name for entry in build_root.iterdir()
        if entry.name not in ALLOWED_ROOT_ENTRIES
    )
    if unexpected:
        errors.append("unexpected distribution root entries: " + ", ".join(unexpected))

    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage = subparsers.add_parser("stage", help="create user_data in an existing build")
    stage.add_argument("build_root", type=Path)
    stage.add_argument("--source-root", type=Path, default=ROOT)

    validate = subparsers.add_parser("validate", help="validate a staged distribution")
    validate.add_argument("build_root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "stage":
        stage_user_data(args.build_root, args.source_root)
        print(f"staged user data: {args.build_root / 'user_data'}")
        return 0

    errors = validate_distribution(args.build_root)
    if errors:
        print("DISTRIBUTION LAYOUT: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("DISTRIBUTION LAYOUT: PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
