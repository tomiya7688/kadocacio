import json
from pathlib import Path
from types import SimpleNamespace

import main as game_entry
from scripts.core import paths
from scripts.team import team_data
from scripts.team.team_editor_data import create_team_template


def test_resolve_runtime_roots_uses_project_root_for_source(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()

    app_root, internal_root = paths.resolve_runtime_roots(project, frozen=False)

    assert app_root == project.resolve()
    assert internal_root == project.resolve()


def test_source_mode_keeps_developer_team_root_in_repository():
    assert paths.IS_FROZEN is False
    assert paths.TEAMS_DIR == paths.PROJECT_ROOT / "teams"
    assert paths.USER_TEAMS_DIR == paths.PROJECT_ROOT / "user_data" / "teams"


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


def test_resolve_runtime_roots_defaults_frozen_internal_dir_beside_exe(tmp_path):
    app = tmp_path / "Kadocacio"
    executable = app / "Kadocacio.exe"
    app.mkdir()

    app_root, internal_root = paths.resolve_runtime_roots(
        tmp_path / "source",
        frozen=True,
        executable=executable,
    )

    assert app_root == app.resolve()
    assert internal_root == (app / "_internal").resolve()


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


def test_bind_runtime_paths_updates_legacy_league_globals(monkeypatch, tmp_path):
    leagues = tmp_path / "user_data" / "config" / "leagues.json"
    state = tmp_path / "user_data" / "saves" / "league_state.json"
    saves = tmp_path / "user_data" / "saves"
    module = SimpleNamespace(
        LEAGUES_PATH=Path("old-leagues.json"),
        LEAGUE_STATE_PATH=Path("old-state.json"),
        LEAGUE_SAVE_DIR=Path("old-save"),
    )
    monkeypatch.setattr(game_entry, "LEAGUES_PATH", leagues)
    monkeypatch.setattr(game_entry, "LEAGUE_STATE_PATH", state)
    monkeypatch.setattr(game_entry, "LEAGUE_SAVE_DIR", saves)

    game_entry._bind_runtime_paths(module)

    assert module.LEAGUES_PATH == leagues
    assert module.LEAGUE_STATE_PATH == state
    assert module.LEAGUE_SAVE_DIR == saves


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
