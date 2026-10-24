"""Command-line coordination for the developer match reproduction checker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from scripts.core.simulation_runtime import MAX_FULL_MATCH_STEPS
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_files import read_input_json, write_new_json, write_reproduction_report
from scripts.tools.match_repro_input import create_input_record, restore_input_record


# {
#   責務: [build_parser: 再現入力の条件と検査・保存オプションを定義する]
#   処理: [1: 引数解析器を作る; 2: チーム・計算条件と保存先・描画間隔・部分許可を登録する]
#   引数: []
#   戻り値: [ArgumentParser: 未解析の引数定義。ファイルや試合へ触れない]
# }
def build_parser() -> argparse.ArgumentParser:
    # 保存入力の条件は既定値をNoneにし、再読込時の明示上書きを検出できるようにする。
    parser = argparse.ArgumentParser(description="Compare seeded headless and Pygame-rendered match state")
    parser.add_argument("--home", help="home team ID or exact name; defaults to the first team")
    parser.add_argument("--away", help="away team ID or exact name; defaults to the second team")
    parser.add_argument("--seed", type=int, help="default: 12345")
    parser.add_argument("--max-steps", type=int, help=f"default: {MAX_FULL_MATCH_STEPS}")
    parser.add_argument("--venue", choices=("HOME", "AWAY", "NEUTRAL"), help="default: HOME")
    parser.add_argument("--ai-rethink-multiplier", type=float, help="0.5..3.0; default: 1.0")
    parser.add_argument("--save-input", type=Path, help="save a new UTF-8 input record before running; never overwrite")
    parser.add_argument("--load-input", type=Path, help="use saved teams and settings without discovering team files")
    parser.add_argument("--save-report", type=Path, help="save inputs, comparison and both full event logs to a new JSON file")
    parser.add_argument("--render-every", type=int, default=60)
    parser.add_argument("--allow-partial", action="store_true", help="accept a matching run before full time")
    return parser


# {
#   責務: [choose_team: 既定の順番または完全一致のID・名前から一チームを選ぶ]
#   処理: [1: 指定なしなら既定indexで選ぶ; 2: ID文字列または名前と完全一致する候補を探す]
#   引数: [choices: 読込済み候補; query: IDまたは名前。Noneは既定選択; fallback_index: 呼出し元が存在を確認した既定index]
#   戻り値: [dict: 選んだ候補の参照。指定が見つからない時はValueError]
# }
def choose_team(choices: list[dict], query: str | None, fallback_index: int) -> dict:
    # 部分一致や似た名前へ黙って置き換えず、再現条件を明確にする。
    if query is None:
        return choices[fallback_index]
    for choice in choices:
        if query in (str(choice.get("id")), choice.get("name")):
            return choice
    raise ValueError(f"team not found: {query}")


# {
#   責務: [resolve_input: 保存入力の読込か現行チームからの記録作成の一方を指揮する]
#   処理: [1: load時は条件上書きを拒否してJSON読込へ渡す; 2: 新規時だけチームを探索し選択する; 3: 既定条件または明示条件で入力作成へ渡す]
#   引数: [args: 解析済みCLI設定]
#   戻り値: [object: 保存入力は未検証JSON値、新規入力は検証済み辞書。競合・候補不足はValueError、読込失敗はOSError]
# }
def resolve_input(args: argparse.Namespace) -> object:
    # 保存した開始値を使う時は、現在のチームファイルを探索しない。
    if args.load_input:
        overrides = (args.home, args.away, args.seed, args.max_steps, args.venue, args.ai_rethink_multiplier)
        if any(value is not None for value in overrides):
            raise ValueError("--load-input cannot be combined with team or simulation input overrides")
        return read_input_json(args.load_input)
    # 新規入力にだけ既定値を適用し、明示されたseed=0を維持する。
    choices = discover_team_choices()
    if len(choices) < 2:
        raise ValueError("at least two valid teams are required")
    home = choose_team(choices, args.home, 0)
    away = choose_team(choices, args.away, 1)
    return create_input_record(
        home, away,
        seed=12345 if args.seed is None else args.seed,
        max_steps=MAX_FULL_MATCH_STEPS if args.max_steps is None else args.max_steps,
        venue_mode=args.venue or "HOME",
        ai_rethink_multiplier=1.0 if args.ai_rethink_multiplier is None else args.ai_rethink_multiplier,
    )


# {
#   責務: [print_summary: 比較結果から全ログ本文を除いたJSON要約を標準出力へ表示する]
#   処理: [1: event_history以外の項目で要約を作る; 2: 日本語を保持したJSONを出力する]
#   引数: [report: 元の比較結果。全ログ付きでも変更しない]
#   戻り値: [None: 標準出力へ要約と改行を出力する]
# }
def print_summary(report: dict) -> None:
    # 全ログは保存ファイルに残し、標準出力の読みやすさとサイズを維持する。
    summary = {key: value for key, value in report.items() if key != "event_history"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


# {
#   責務: [MatchReproductionCli: 再現性検査コマンドの実行順とCLI終了診断を所有する]
#   フィールド: [_parser: 引数定義と入力エラー表示の解析器; _compare: 両経路の比較を担当する注入関数]
# }
class MatchReproductionCli:
    # {
    #   責務: [__init__: 比較処理と引数解析器をコマンドへ接続する]
    #   処理: [1: 比較関数を保持する; 2: 解析器の定義を作る]
    #   引数: [compare: 両チーム・設定から比較結果を返す関数]
    #   戻り値: [None: 入出力や試合計算はまだ開始しない]
    # }
    def __init__(self, compare: Callable[..., dict]) -> None:
        # 比較層をimportし直さず、既存入口が持つ比較関数を明示的に受け取る。
        self._compare = compare
        self._parser = build_parser()

    # {
    #   責務: [run: 引数解析から比較・出力・CLI終了診断までの呼出し順を指揮する]
    #   処理: [1: 引数を解析する; 2: 比較パイプラインを呼び入力・保存失敗を診断する; 3: 要約表示を依頼し一致と完走条件から終了する]
    #   引数: [argv: CLI引数列。Noneはプロセス引数]
    #   戻り値: [int: 一致かつ完走または部分許可なら0、それ以外は1。不正引数・入力・保存失敗はSystemExitのコード2]
    # }
    def run(self, argv: list[str] | None = None) -> int:
        # エラーは解析器にまとめ、保存・比較の例外を成功結果へ置き換えない。
        args = self._parser.parse_args(argv)
        try:
            report = self._run_comparison(args)
        except (ValueError, OSError) as error:
            self._parser.error(str(error))
        # 部分実行の許可は完走条件だけを緩め、不一致を成功扱いにしない。
        print_summary(report)
        return 0 if report["same_state"] and (report["fulltime"] or args.allow_partial) else 1

    # {
    #   責務: [_run_comparison: 入力準備・任意保存・比較・レポート保存の呼出し順を指揮する]
    #   処理: [1: 入力を解決し復元へ渡す; 2: 要求時だけ比較前の入力保存を依頼する; 3: 同条件の比較を依頼する; 4: 要求時だけ全ログ付き保存を依頼する]
    #   引数: [args: 解析済みCLI設定]
    #   戻り値: [dict: 比較結果。入力・保存・比較の失敗はrunへ伝える]
    # }
    def _run_comparison(self, args: argparse.Namespace) -> dict:
        # 検証・JSON入出力・試合計算は各担当へ渡し、ここでは実行順だけを持つ。
        record = resolve_input(args)
        home, away, settings = restore_input_record(record)
        if args.save_input:
            write_new_json(args.save_input, record)
        report = self._compare(
            home, away, render_every=args.render_every, include_events=args.save_report is not None, **settings,
        )
        # 不一致や未完走も調査できるよう、終了判定より前に結果保存を依頼する。
        if args.save_report:
            write_reproduction_report(args.save_report, record, report)
        return report
