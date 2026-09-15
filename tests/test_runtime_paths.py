import json
from pathlib import Path

from scripts.core import paths
from scripts.team import team_data
from scripts.team.team_editor_data import create_team_template


def test_resolve_runtime_roots_uses_project_root_for_source(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    app_root, internal_root = paths.resolve_runtime_roots(project, frozen=False)

    assert app_root == project.resolve()
    assert internal_root == project.resolve()


def test_resolve_runtime_roots_separates_executable_and_internal_data(tmp_path):
    app = tmp_path / "Kadocacio"
    internal = app / "_internal"
    executable = app / "Kadocacio.exe"
    internal.mkdir(parents=True)

    app_root, internal_root = paths.resolve_runtime_roots(
        tmp_path / "source",
        frozen=True,
        executable=executable,
        bundle_root=internal,
    )

    assert app_root == app.resolve()
    assert internal_root == internal.resolve()


def test_ensure_user_data_layout_seeds_missing_files_without_overwrite(monkeypatch, tmp_path):
    source = tmp_path / "defaults.json"
    target = tmp_path / "user_data" / "config" / "defaults.json"
    missing_source = tmp_path / "missing.json"
    missing_target = tmp_path / "user_data" / "config" / "missing.json"
    source.write_text('{"version": 1}', encoding="utf-8")

    monkeypatch.setattr(paths, "USER_DATA_DIRS", (target.parent, tmp_path / "user_data" / "logs"))
    monkeypatch.setattr(
        paths,
        "DEFAULT_USER_FILES",
        ((source, target), (missing_source, missing_target)),
    )

    paths.ensure_user_data_layout()
    assert target.read_text(encoding="utf-8") == '{"version": 1}'
    assert (tmp_path / "user_data" / "logs").is_dir()
    assert not missing_target.exists()

    target.write_text('{"version": 99}', encoding="utf-8")
    source.write_text('{"version": 2}', encoding="utf-8")
    paths.ensure_user_data_layout()

    assert target.read_text(encoding="utf-8") == '{"version": 99}'


def _write_team(root: Path, relative: str, name: str) -> None:
    payload = create_team_template("initial")
    payload["チーム情報"]["チーム名"] = name
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_user_team_overrides_bundled_team_with_same_relative_id(monkeypatch, tmp_path):
    user_root = tmp_path / "user_data" / "teams"
    default_root = tmp_path / "_internal" / "teams"
    _write_team(default_root, "league/sample.json", "標準チーム")
    _write_team(user_root, "league/sample.json", "ユーザー編集チーム")

    monkeypatch.setattr(team_data, "TEAMS_DIR", user_root)
    monkeypatch.setattr(team_data, "DEFAULT_TEAMS_DIR", default_root)

    choices = team_data.discover_team_choices()

    assert [choice["id"] for choice in choices] == ["json:league/sample.json"]
    assert choices[0]["name"] == "ユーザー編集チーム"


def test_invalid_user_override_falls_back_to_bundled_team(monkeypatch, tmp_path):
    user_root = tmp_path / "user_data" / "teams"
    default_root = tmp_path / "_internal" / "teams"
    _write_team(default_root, "sample.json", "標準チーム")
    user_root.mkdir(parents=True)
    (user_root / "sample.json").write_text("{broken", encoding="utf-8")

    monkeypatch.setattr(team_data, "TEAMS_DIR", user_root)
    monkeypatch.setattr(team_data, "DEFAULT_TEAMS_DIR", default_root)

    choices = team_data.discover_team_choices()

    assert [choice["id"] for choice in choices] == ["json:sample.json"]
    assert choices[0]["name"] == "標準チーム"
