import json
from pathlib import Path

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


def test_validate_distribution_accepts_expected_layout(tmp_path):
    source = tmp_path / "source"
    build = tmp_path / "Kadocacio"
    source.mkdir()
    build.mkdir()
    make_source(source)
    (build / "Kadocacio.exe").write_bytes(b"MZ")
    make_internal(build)
    distribution_layout.stage_user_data(build, source)

    assert distribution_layout.validate_distribution(build) == []


def test_validate_distribution_rejects_missing_or_dirty_layout(tmp_path):
    source = tmp_path / "source"
    build = tmp_path / "Kadocacio"
    source.mkdir()
    build.mkdir()
    make_source(source)
    distribution_layout.stage_user_data(build, source)
    (build / "debug.log").write_text("should not ship at root", encoding="utf-8")

    errors = distribution_layout.validate_distribution(build)

    assert "missing Kadocacio.exe" in errors
    assert any("missing internal directory" in error for error in errors)
    assert any("unexpected distribution root entries: debug.log" in error for error in errors)


def test_validate_distribution_rejects_broken_seed_json(tmp_path):
    source = tmp_path / "source"
    build = tmp_path / "Kadocacio"
    source.mkdir()
    build.mkdir()
    make_source(source)
    (build / "Kadocacio.exe").write_bytes(b"MZ")
    make_internal(build)
    distribution_layout.stage_user_data(build, source)
    (build / "user_data/config/leagues.json").write_text("{broken", encoding="utf-8")

    errors = distribution_layout.validate_distribution(build)

    assert any("invalid JSON: user_data/config/leagues.json" in error for error in errors)
