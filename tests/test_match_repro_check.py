"""Rendering should not change a seeded match's simulation state."""

import os
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import compare_matches, main


# {
#   責務: [MatchReproCheckTests: 描画有無の固定更新比較と差分診断・CLI成功条件を検査する]
#   フィールド: [home・away: 比較試験の開始入力となる読込済みチーム]
# }
class MatchReproCheckTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: 比較試験で共有する二チームを準備する]
    #   処理: [1: 有効候補の先頭二件を読み込む]
    #   引数: []
    #   戻り値: [None: クラスの入力を保持する。チームファイルは変更しない]
    # }
    @classmethod
    def setUpClass(cls):
        # 短い実試合と差分報告のモック試験で同じ開始入力を使う。
        cls.home, cls.away = discover_team_choices()[:2]

    # {
    #   責務: [test_real_pygame_draw_matches_headless_fixed_steps: 実描画を挟んでも固定更新40回の試合状態が一致することを確認する]
    #   処理: [1: 同seedで10更新ごとに描画する比較を実行する; 2: 状態・更新数・フレーム数と未完走を確認する]
    #   引数: []
    #   戻り値: [None: 描画による演算差や途中一致の完走扱いは試験失敗。ダミーSDLでの試験]
    # }
    def test_real_pygame_draw_matches_headless_fixed_steps(self):
        # 通常のdraw()を実行するが、実ウィンドウの入力E2Eとは区別する。
        report = compare_matches(self.home, self.away, seed=917, max_steps=40, render_every=10)
        self.assertTrue(report["same_state"], report)
        self.assertEqual(report["different_fields"], [])
        self.assertEqual((report["headless_steps"], report["rendered_steps"]), (40, 40))
        self.assertGreaterEqual(report["rendered_frames"], 5)
        self.assertFalse(report["fulltime"])

    # {
    #   責務: [test_invalid_step_limits_are_rejected: ゼロの更新上限を比較開始前に拒否することを確認する]
    #   処理: [1: max_steps=0で比較を要求する; 2: 正数条件を示すValueErrorを確認する]
    #   引数: []
    #   戻り値: [None: 無効な比較の受入や診断の欠落は試験失敗]
    # }
    def test_invalid_step_limits_are_rejected(self):
        # 時計だけを進めた空の成功結果を生成しない。
        with self.assertRaisesRegex(ValueError, "positive"):
            compare_matches(self.home, self.away, seed=1, max_steps=0, render_every=10)

    # {
    #   責務: [test_rendered_partial_frame_matches_headless: 描画間隔で割り切れない更新数でも末尾を描画して一致することを確認する]
    #   処理: [1: 41更新を12更新ごとの描画で比較する; 2: 状態一致と末尾を含む5フレームを確認する]
    #   引数: []
    #   戻り値: [None: 余りの更新や最終描画が抜けると試験失敗]
    # }
    def test_rendered_partial_frame_matches_headless(self):
        # 最初の描画、定期間隔の描画、端数の最終描画を含める。
        report = compare_matches(self.home, self.away, seed=918, max_steps=41, render_every=12)
        self.assertTrue(report["same_state"], report)
        self.assertEqual(report["rendered_frames"], 5)

    # {
    #   責務: [test_step_mismatch_is_reported: 同じ観測値でも更新回数の差を不一致として報告することを確認する]
    #   処理: [1: 状態は同じで更新回数だけ異なる両経路を模擬する; 2: stepsが最初の差分となることを確認する]
    #   引数: []
    #   戻り値: [None: 更新回数の不整合を成功へ隠すと試験失敗]
    # }
    def test_step_mismatch_is_reported(self):
        # この試験は報告ロジックだけを検査し、実演算の比較とは分ける。
        state = {"state": "PLAYING", "game_time": 1.0, "event_history": []}
        with patch("scripts.tools.match_repro_check.run_headless", return_value=(state, 2)):
            with patch("scripts.tools.match_repro_check.run_rendered", return_value=(state, 3, 1)):
                report = compare_matches(self.home, self.away, seed=1, max_steps=3, render_every=1)
        self.assertFalse(report["same_state"])
        self.assertEqual(report["different_fields"], ["steps"])

    # {
    #   責務: [test_detects_an_early_event_difference_missing_from_the_last_eight: 画面用の末尾ログに残らない初期イベント差を検出することを確認する]
    #   処理: [1: 12件の履歴で先頭だけ異なる観測を用意する; 2: 両経路を模擬して比較する; 3: 全履歴の差分位置・指紋と本文省略を確認する]
    #   引数: []
    #   戻り値: [None: 末尾8件だけの比較へ退行すると試験失敗]
    # }
    def test_detects_an_early_event_difference_missing_from_the_last_eight(self):
        # 画面用eventsが同じでも、全event_historyの先頭差は残す。
        history = [{"sequence": index + 1, "text": f"event {index}"} for index in range(12)]
        left = {"state": "PLAYING", "game_time": 1.0, "events": history[-8:], "event_history": history}
        right = deepcopy(left)
        right["event_history"][0]["text"] = "different early event"
        with patch("scripts.tools.match_repro_check.run_headless", return_value=(left, 20)):
            with patch("scripts.tools.match_repro_check.run_rendered", return_value=(right, 20, 3)):
                report = compare_matches(self.home, self.away, seed=1, max_steps=20, render_every=10)
        self.assertFalse(report["same_state"])
        self.assertEqual(report["different_fields"], ["event_history"])
        self.assertEqual(report["first_event_difference"]["index"], 0)
        self.assertNotEqual(report["headless_event_digest"], report["rendered_event_digest"])
        self.assertNotIn("event_history", report)

    # {
    #   責務: [test_reports_a_missing_event_at_the_end: 片側の末尾イベント欠落を差分と全ログに残すことを確認する]
    #   処理: [1: 一件の履歴と空履歴を模擬する; 2: 全ログ付き比較を実行する; 3: 欠落側のNoneと存在側の値を確認する]
    #   引数: []
    #   戻り値: [None: 件数差の見落としや報告値の取り違えは試験失敗]
    # }
    def test_reports_a_missing_event_at_the_end(self):
        # 通常のzipでは落ちる片側だけの要素も比較対象にする。
        left = {"state": "PLAYING", "game_time": 1.0, "event_history": [{"sequence": 1, "text": "kickoff"}]}
        right = {**left, "event_history": []}
        with patch("scripts.tools.match_repro_check.run_headless", return_value=(left, 20)):
            with patch("scripts.tools.match_repro_check.run_rendered", return_value=(right, 20, 3)):
                report = compare_matches(
                    self.home,
                    self.away,
                    seed=1,
                    max_steps=20,
                    render_every=10,
                    include_events=True,
                )
        self.assertEqual(report["first_event_difference"]["headless"], left["event_history"][0])
        self.assertIsNone(report["first_event_difference"]["rendered"])
        self.assertEqual(report["event_history"]["headless"], left["event_history"])

    # {
    #   責務: [test_cli_accepts_explicit_teams_and_partial_result: ID・名前による明示選択と未完走の一致の許可をCLIから渡せることを確認する]
    #   処理: [1: チーム探索と比較結果を模擬する; 2: IDと名前・上限・部分許可を指定する; 3: 成功コードと比較へ渡った更新上限を確認する]
    #   引数: []
    #   戻り値: [None: 引数の伝達や許可された途中一致の判定が異なると試験失敗]
    # }
    def test_cli_accepts_explicit_teams_and_partial_result(self):
        # CLI配線の確認であり、ここで短い模擬結果を完走の証拠にはしない。
        report = {"same_state": True, "fulltime": False}
        with patch("scripts.tools.match_repro_cli.discover_team_choices", return_value=[self.home, self.away]):
            with patch("scripts.tools.match_repro_check.compare_matches", return_value=report) as compare:
                with redirect_stdout(StringIO()):
                    result = main(
                        [
                            "--home",
                            str(self.home["id"]),
                            "--away",
                            self.away["name"],
                            "--allow-partial",
                            "--max-steps",
                            "3",
                        ]
                    )
        self.assertEqual(result, 0)
        self.assertEqual(compare.call_args.kwargs["max_steps"], 3)

    # {
    #   責務: [test_cli_rejects_incomplete_and_mismatching_results: 未許可の未完走と許可しても不一致の結果をCLI失敗にすることを確認する]
    #   処理: [1: 一致する未完走と不一致の完走を順に模擬する; 2: 部分許可なし・ありの双方で失敗コードを確認する]
    #   引数: []
    #   戻り値: [None: 未完走や不一致を誤って成功扱いすると試験失敗]
    # }
    def test_cli_rejects_incomplete_and_mismatching_results(self):
        # allow-partialは完走条件だけを緩め、状態不一致を許可しない。
        with patch("scripts.tools.match_repro_cli.discover_team_choices", return_value=[self.home, self.away]):
            with patch("scripts.tools.match_repro_check.compare_matches") as compare:
                with redirect_stdout(StringIO()):
                    compare.return_value = {"same_state": True, "fulltime": False}
                    self.assertEqual(main([]), 1)
                    compare.return_value = {"same_state": False, "fulltime": True}
                    self.assertEqual(main(["--allow-partial"]), 1)

    # {
    #   責務: [test_cli_rejects_unknown_or_insufficient_teams: 候補不足と存在しないチーム指定をCLI入力エラーにすることを確認する]
    #   処理: [1: 一チームしかない探索結果で失敗を確認する; 2: 二チームでも未知のIDを指定すると失敗することを確認する]
    #   引数: []
    #   戻り値: [None: 誤った既定選択で比較を続けると試験失敗]
    # }
    def test_cli_rejects_unknown_or_insufficient_teams(self):
        # 不足時に同一候補を流用したり、未知の名前を無視したりしない。
        with patch("scripts.tools.match_repro_cli.discover_team_choices", return_value=[self.home]):
            with self.assertRaises(SystemExit):
                main([])
        with patch("scripts.tools.match_repro_cli.discover_team_choices", return_value=[self.home, self.away]):
            with self.assertRaises(SystemExit):
                main(["--home", "missing-team"])


if __name__ == "__main__":
    unittest.main()
