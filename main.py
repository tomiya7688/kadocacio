"""カドカルチョの起動エントリーポイント。"""

from scripts.core.paths import (
    LEAGUE_SAVE_DIR,
    LEAGUE_STATE_PATH,
    LEAGUES_PATH,
    ensure_user_data_layout,
)


def _bind_runtime_paths(league_module) -> None:
    """Point legacy league module globals at the writable runtime layout."""
    league_module.LEAGUES_PATH = LEAGUES_PATH
    league_module.LEAGUE_STATE_PATH = LEAGUE_STATE_PATH
    league_module.LEAGUE_SAVE_DIR = LEAGUE_SAVE_DIR


def main() -> None:
    ensure_user_data_layout()

    from scripts.league import league_manager
    _bind_runtime_paths(league_manager)

    from scripts.app.game_app import Game
    Game().run()


if __name__ == "__main__":
    main()
