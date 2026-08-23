"""カドカルチョの起動エントリーポイント。"""

from scripts.app.game_app import Game


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
