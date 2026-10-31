"""カドカルチョの起動エントリーポイント。"""

import sys

from scripts.core.paths import (
    LEAGUE_SAVE_DIR,
    LEAGUE_STATE_PATH,
    LEAGUES_PATH,
    ensure_user_data_layout,
)


# {
#   責務: [_bind_runtime_paths: 旧リーグAPIへ書込可能な保存先を接続する]
#   処理: [1: 三つの旧モジュール変数へ実行時の保存先を設定する]
#   引数: [league_module: 接続対象のリーグモジュール]
#   戻り値: [None: 指定モジュールの保存先を変更する]
# }
def _bind_runtime_paths(league_module) -> None:
    """Point legacy league module globals at the writable runtime layout."""
    league_module.LEAGUES_PATH = LEAGUES_PATH
    league_module.LEAGUE_STATE_PATH = LEAGUE_STATE_PATH
    league_module.LEAGUE_SAVE_DIR = LEAGUE_SAVE_DIR


# {
#   責務: [main: 必要な実行時データを準備して通常のゲームを起動する]
#   処理: [1: 保存領域を準備する; 2: 旧APIへ保存先を接続する; 3: ゲームループを開始する]
#   引数: []
#   戻り値: [None: ゲーム終了時に戻る。起動失敗は呼出し元へ伝える]
# }
def main() -> None:
    # 診断専用入口はこの初期化へ入らず、利用者のデータを作らない。
    ensure_user_data_layout()

    from scripts.league import league_manager

    _bind_runtime_paths(league_manager)

    from scripts.app.game_app import Game

    Game().run()


if __name__ == "__main__":
    # 配布物の実ランタイムを検査できるよう、GUI生成より前に分岐する。
    if sys.argv[1:2] == ["--check-python-trust"]:
        from scripts.tools.python_trust_check import main as check_python_trust

        raise SystemExit(check_python_trust(sys.argv[2:]))
    main()
