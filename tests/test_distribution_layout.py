import json
from pathlib import Path

import pytest

from scripts.tools import distribution_layout


def make_source(root: Path) -> None:
    (root / "performance_settings.json").write_text(
        json.dumps({"CPU使用率上限": 100}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "leagues.json").write_text(
        json.dumps({"リーグ一覧": []}, ensure_ascii=False),
        encoding="utf-8",
    )


def make_internal(root: Path) -> None:
    for relative in distribution_layout.REQUIRED_INTERNAL_DIRS:
        directory = root / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sample.dat").write_text("x", encoding="utf-8")
    for relative in distribution_layout.REQUIRED_INTERNAL_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ok": True}), encoding="utf-8")


def make_complete_build(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    build = tmp_path / "Kadocacio"
    source.mkdir()
    build.mkdir()
    make_source(source)
    (build / "Kadocacio.exe").write_bytes(b"MZ")
    make_internal(build)
    distribution_layout.stage_user_data(build, source)
    return source, build


def test_stage_user_data_creates_expected_directories_and_seed_files(tmp_path):
    source = tmp_path / "source"
    build = tmp_path / "dist" / "Kadocacio"
    source.mkdir()
    build.mkdir(parents=True)
    make_source(source)

    distribution_layout.stage_user_data(build, source)

    for relative in distribution_layout.USER_DATA_DIRS:
        assert (build / relative).is_dir()
    for source_relative, target_relative in distribution_layout.SEEDED_USER_FILES:
        assert (build / target_relative).read_text(encoding="utf-8") == (
            source / source_relative
        ).read_text(encoding="utf-8")


def test_stage_user_data_rejects_missing_build_or_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    make_source(source)

    with pytest.raises(FileNotFoundError, match="distribution root"):
        distribution_layout.stage_user_data(tmp_path / "missing-build", source)

    build = tmp_path / "Kadocacio"
    build.mkdir()
    (source / "leagues.json").unlink()
    with pytest.raises(FileNotFoundError, match="required source file"):
        distribution_layout.stage_user_data(build, source)


def test_validate_distribution_accepts_expected_layout(tmp_path):
    _, build = make_complete_build(tmp_path)

    assert distribution_layout.validate_distribution(build) == []


def test_validate_distribution_rejects_missing_root(tmp_path):
    errors = distribution_layout.validate_distribution(tmp_path / "missing")

    assert errors == [f"distribution root does not exist: {tmp_path / 'missing'}"]


def test_validate_distribution_reports_all_structural_failures(tmp_path):
    _, build = make_complete_build(tmp_path)
    (build / "Kadocacio.exe").unlink()
    (build / "user_data/logs").rmdir()
    (build / "user_data/config/leagues.json").unlink()

    empty_internal = build / distribution_layout.REQUIRED_INTERNAL_DIRS[0]
    for item in empty_internal.rglob("*"):
        if item.is_file():
            item.unlink()

    missing_internal_file = build / distribution_layout.REQUIRED_INTERNAL_FILES[0]
    missing_internal_file.unlink()
    (build / "debug.log").write_text("should not ship at root", encoding="utf-8")

    errors = distribution_layout.validate_distribution(build)

    assert "missing Kadocacio.exe" in errors
    assert "missing directory: user_data/logs" in errors
    assert "missing user data file: user_data/config/leagues.json" in errors
    assert any("internal directory is empty" in error for error in errors)
    assert any("missing internal file" in error for error in errors)
    assert "unexpected distribution root entries: debug.log" in errors


def test_validate_distribution_reports_missing_internal_directory(tmp_path):
    _, build = make_complete_build(tmp_path)
    target = build / distribution_layout.REQUIRED_INTERNAL_DIRS[1]
    for item in target.rglob("*"):
        if item.is_file():
            item.unlink()
    target.rmdir()

    errors = distribution_layout.validate_distribution(build)

    assert any("missing internal directory" in error for error in errors)


def test_validate_distribution_rejects_broken_json(tmp_path):
    _, build = make_complete_build(tmp_path)
    (build / "user_data/config/leagues.json").write_text("{broken", encoding="utf-8")
    (build / distribution_layout.REQUIRED_INTERNAL_FILES[1]).write_text(
        "{broken",
        encoding="utf-8",
    )

    errors = distribution_layout.validate_distribution(build)

    assert any("invalid JSON: user_data/config/leagues.json" in error for error in errors)
    assert any("invalid JSON: _internal/leagues.json" in error for error in errors)


def test_cli_stage_and_validate_paths(tmp_path, capsys):
    source = tmp_path / "source"
    build = tmp_path / "Kadocacio"
    source.mkdir()
    build.mkdir()
    make_source(source)
    (build / "Kadocacio.exe").write_bytes(b"MZ")
    make_internal(build)

    assert distribution_layout.main(
        ["stage", str(build), "--source-root", str(source)]
    ) == 0
    assert "staged user data" in capsys.readouterr().out

    assert distribution_layout.main(["validate", str(build)]) == 0
    assert "DISTRIBUTION LAYOUT: PASS" in capsys.readouterr().out

    (build / "Kadocacio.exe").unlink()
    assert distribution_layout.main(["validate", str(build)]) == 1
    assert "DISTRIBUTION LAYOUT: FAIL" in capsys.readouterr().out
