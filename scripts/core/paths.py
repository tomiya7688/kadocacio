from __future__ import annotations

import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_runtime_roots(
    project_root: Path = PROJECT_ROOT,
    *,
    frozen: bool | None = None,
    executable: Path | None = None,
    bundle_root: Path | None = None,
) -> tuple[Path, Path]:
    """Return the user-facing app root and read-only bundled-data root."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    project_root = Path(project_root).resolve()
    if not is_frozen:
        return project_root, project_root

    executable_path = Path(executable or sys.executable).resolve()
    app_root = executable_path.parent
    internal_root = Path(
        bundle_root or getattr(sys, "_MEIPASS", app_root / "_internal")
    ).resolve()
    return app_root, internal_root


APP_ROOT, INTERNAL_ROOT = resolve_runtime_roots()
USER_DATA_ROOT = APP_ROOT / "user_data"
USER_CONFIG_DIR = USER_DATA_ROOT / "config"
USER_SAVE_DIR = USER_DATA_ROOT / "saves"
USER_EXPORT_DIR = USER_DATA_ROOT / "exports"
USER_LOG_DIR = USER_DATA_ROOT / "logs"

# User-created/edited teams live here. Bundled defaults stay read-only in
# _internal/teams for packaged builds and in the repository's teams/ for dev.
TEAMS_DIR = USER_DATA_ROOT / "teams"
DEFAULT_TEAMS_DIR = INTERNAL_ROOT / "teams"

ASSETS_DIR = INTERNAL_ROOT / "assets"
TEMPLATE_DIR = INTERNAL_ROOT / "teameditor_templete"
LEAGUE_SAVE_DIR = USER_SAVE_DIR
LEAGUE_TEMPLATE_DIR = USER_CONFIG_DIR / "league_templates"
LEAGUES_PATH = USER_CONFIG_DIR / "leagues.json"
LEAGUE_STATE_PATH = USER_SAVE_DIR / "league_state.json"
PERFORMANCE_SETTINGS_PATH = USER_CONFIG_DIR / "performance_settings.json"

DEFAULT_LEAGUES_PATH = INTERNAL_ROOT / "leagues.json"
DEFAULT_LEAGUE_STATE_PATH = INTERNAL_ROOT / "league_state.json"
DEFAULT_PERFORMANCE_SETTINGS_PATH = INTERNAL_ROOT / "performance_settings.json"

# Developer-only outputs keep their existing repository locations. They are not
# part of the player-facing packaged game.
AI_EVALUATION_DIR = PROJECT_ROOT / "ai_evaluation"
PERFORMANCE_LOG_DIR = PROJECT_ROOT / "performance_logs"
DEVELOPMENT_EVALUATION_DIR = PROJECT_ROOT / "development_evaluation"
UNIFORMS_DIR = PROJECT_ROOT / "uniforms"

USER_DATA_DIRS = (
    TEAMS_DIR,
    USER_SAVE_DIR,
    USER_CONFIG_DIR,
    USER_EXPORT_DIR,
    USER_LOG_DIR,
    LEAGUE_TEMPLATE_DIR,
)
DEFAULT_USER_FILES = (
    (DEFAULT_PERFORMANCE_SETTINGS_PATH, PERFORMANCE_SETTINGS_PATH),
    (DEFAULT_LEAGUES_PATH, LEAGUES_PATH),
    (DEFAULT_LEAGUE_STATE_PATH, LEAGUE_STATE_PATH),
)


def team_search_dirs() -> tuple[Path, ...]:
    """Return team roots in override order: user data first, defaults second."""
    roots = [TEAMS_DIR]
    if DEFAULT_TEAMS_DIR.resolve() != TEAMS_DIR.resolve():
        roots.append(DEFAULT_TEAMS_DIR)
    return tuple(roots)


def ensure_user_data_layout() -> None:
    """Create writable runtime directories and seed missing editable JSON."""
    for directory in USER_DATA_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
    for source, target in DEFAULT_USER_FILES:
        if target.exists() or not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
