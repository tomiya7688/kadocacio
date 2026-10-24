"""Export/check the Match boundary specification for the native Godot consumer."""

import argparse
import json
from pathlib import Path

from scripts.core.match_protocol import protocol_definition
from scripts.core.paths import PROJECT_ROOT
from scripts.match.player_command import PlayerCommand
from scripts.core.settings import FIELD, GAME_CLOCK_RATE, MATCH_SECONDS
from scripts.match.stamina_system import stamina_capacity

CONTRACT_PATH = PROJECT_ROOT / "godot/data/match_contract.json"


# {
#   責務: [contract_text: 規約とプレイヤーコマンドの正本から配布定義を生成する]
#   処理: [1: 定数とenumを統合; 2: 再生成を比較できる整形JSONへ変換]
#   引数: []
#   戻り値: [str: 改行終端付きの定義JSON]
# }
def contract_text() -> str:
    return json.dumps({**protocol_definition(), "player_commands": {command.name: command.value for command in PlayerCommand},
                       "kernel": {"field": [FIELD.left, FIELD.top, FIELD.width, FIELD.height],
                                  "clock_rate": GAME_CLOCK_RATE, "match_seconds": MATCH_SECONDS,
                                  "stamina_base": stamina_capacity(0.0), "stamina_span": stamina_capacity(1.0) - stamina_capacity(0.0)}}, ensure_ascii=False, indent=2) + "\n"


# {
#   責務: [check_contract: 保存済み定義がPython正本と一致するか確認する]
#   処理: [1: ファイル存在と生成テキストへの完全一致を確認]
#   引数: [path: 確認する定義ファイル]
#   戻り値: [bool: 最新定義ならTrue]
# }
def check_contract(path: Path = CONTRACT_PATH) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8") == contract_text()


# {
#   責務: [main: 明示生成または読取検証を開発CLIとして提供する]
#   処理: [1: 引数を解析; 2: write指定時だけ定義を保存; 3: 通常時は一致確認結果を表示]
#   引数: [argv: CLI引数。Noneなら実行プロセスの引数]
#   戻り値: [int: 成功0、古い定義1]
# }
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(contract_text(), encoding="utf-8")
        print("GODOT MATCH CONTRACT: GENERATED")
        return 0
    valid = check_contract()
    print("GODOT MATCH CONTRACT: PASS" if valid else "GODOT MATCH CONTRACT: STALE")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
