"""カドカルチョの起動エントリーポイント。"""

from scripts.core.paths import ensure_user_data_layout


def main() -> None:
    ensure_user_data_layout()
    from scripts.app.game_app import Game

    Game().run()


if __name__ == "__main__":
    main()
