"""Actual-reference ball fixtures and native runner safety gates, not UI parity."""

from copy import deepcopy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from scripts.core.match_trace_comparison import compare_traces
from scripts.core.settings import GOAL_HEIGHT
from scripts.tools import godot_ball_fixture as fixture, godot_runner as runner
from scripts.tools.match_contract_input import restore_contract_input


# {
#   責務: [GodotBallPhysicsTests: ボール参照の検査範囲・再現性・入力保護と実行入口の失敗伝播を確認します]
#   フィールド: [document: 全ケースと参照を持つfixture; hashes: 元チームの指紋; cases: ケース名から検査入力への索引]
# }
class GodotBallPhysicsTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: 一時領域で生成した実Python参照を検査クラスへ保持します]
    #   処理: [1: 一時フォルダでfixtureと元チーム指紋を生成します; 2: JSONをメモリへ読みます; 3: ケース名の索引を作ります]
    #   引数: []
    #   戻り値: [None: 一時フォルダは終了時に削除し、保持した参照だけを各検査で使用します]
    # }
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path, cls.hashes = fixture.write_ball_fixture(Path(directory))
            cls.document = json.loads(path.read_text(encoding="utf-8"))
        cls.cases = {case["name"]: case for case in cls.document["cases"]}

    # {
    #   責務: [test_real_rule_oracle_has_trajectories_bounds_and_contact_gates: 参照が実弾道・境界・接触可否を含むことを確認します]
    #   処理: [1: 自己比較と元チーム指紋を確認します; 2: 減速・浮き・反射と両ゴール境界を検査します; 3: 接触優先・高さ・GKの手の規則を検査します]
    #   引数: []
    #   戻り値: [None: 必要なケースや幾何規則が欠ければ失敗します。接触成功率は認定しません]
    # }
    def test_real_rule_oracle_has_trajectories_bounds_and_contact_gates(self):
        # ケース数だけでなく、代表値の意味を確認して空の参照を通しません。
        trace = self.document["reference"]
        self.assertTrue(compare_traces(trace, trace)["same_observations"])
        self.assertEqual(len(self.hashes), 2)
        self.assertGreaterEqual(len(self.cases), 50)
        self.assertEqual(self.cases["slow_roll"]["frames"][-1]["ball"]["velocity"], [0.0, 0.0, 0.0])
        self.assertGreater(max(frame["ball"]["position"][2] for frame in self.cases["lofted"]["frames"]), 80)
        self.assertGreater(self.cases["hard_bounce"]["frames"][0]["ball"]["velocity"][2], 0)
        self.assertEqual(self.cases["soft_bounce"]["frames"][0]["ball"]["velocity"][2], 0)
        for side in ("left", "right"):
            self.assertEqual(self.cases[side + "_bar_exact"]["frames"][0]["boundary"]["kind"], "GOAL")
            self.assertEqual(self.cases[side + "_bar_over"]["frames"][0]["boundary"]["kind"], "GOAL_KICK")
            self.assertEqual(self.cases[side + "_post"]["frames"][0]["ball"]["flight_type"], "ポスト跳ね返り")
            self.assertGreater(self.cases[side + "_bar_over"]["frames"][0]["ball"]["position"][2], GOAL_HEIGHT)
        self.assertIsNone(self.cases["line_exact"]["frames"][0]["boundary"])
        # 同じ位置でも、回収優先・ロック・高さによって候補が変わることを確認します。
        self.assertEqual(self.cases["corner_priority"]["frames"][0]["boundary"]["kind"], "THROW_IN")
        for name, expected in (("contact_order", "HOME:1"), ("contact_recovery", "AWAY:1"), ("contact_lock", "AWAY:1"), ("contact_air_high", "HOME:1")):
            self.assertEqual(self.cases[name]["frames"][0]["contact"]["player"], expected)
        for name in ("contact_sent_off", "contact_too_high", "contact_air_low"):
            self.assertIsNone(self.cases[name]["frames"][0]["contact"])
        for name in ("keeper_hands", "keeper_opponent_touch", "keeper_self_touch", "keeper_box_edge", "keeper_air_reach"):
            self.assertTrue(self.cases[name]["frames"][0]["contact"]["hands_legal"])
        for name in ("keeper_backpass_feet", "keeper_outside_feet"):
            self.assertFalse(self.cases[name]["frames"][0]["contact"]["hands_legal"])
        for name in ("keeper_backpass_high", "keeper_air_too_high", "keeper_fast_shot_skip"):
            self.assertIsNone(self.cases[name]["frames"][0]["contact"])

    # {
    #   責務: [test_possession_metadata_and_reproducible_isolated_capture: 所有変更の参照とケース再現性を確認します]
    #   処理: [1: 各ケースを再実行して初期状態と時点列を比較します; 2: グローバル乱数が変わらないことを確認します; 3: 保持・解放・回収時間と差分検出を確認します]
    #   引数: []
    #   戻り値: [None: 不一致や乱数汚染、差分の見逃しがあれば失敗します]
    # }
    def test_possession_metadata_and_reproducible_isolated_capture(self):
        # 独立ケースを同じ入力から再生成し、前回の実行結果を再利用しません。
        for name in ("held", "claim", "claim_default", "spill_tackle", "spill_plain", "spill_non_owner", "metadata_expiry"):
            with self.subTest(name=name):
                case = self.cases[name]
                home, away, _, _ = restore_contract_input(self.document["input"])
                before = random.getstate()
                initial, frames = fixture.capture_case(home, away, case)
                self.assertEqual((initial, frames), (case["initial"], case["frames"]))
                self.assertEqual(random.getstate(), before)
        held = self.cases["held"]
        # 保持中の不変と、実際のノックバック解放・回収優先時間の失効を別々に確認します。
        self.assertTrue(all(frame["ball"] == held["initial"]["ball"] for frame in held["frames"]))
        self.assertIsNone(self.cases["spill_tackle"]["frames"][0]["ball"]["owner"])
        self.assertEqual(self.cases["spill_tackle"]["frames"][0]["ball"]["recovery_team"], "AWAY")
        self.assertEqual(self.cases["spill_non_owner"]["frames"][0]["ball"]["owner"], "AWAY:1")
        self.assertIsNone(self.cases["metadata_expiry"]["frames"][-1]["ball"]["recovery_team"])
        self.assertEqual(self.cases["claim"]["frames"][0]["ball"]["control_offset"], [8.0, -3.0])
        copied = deepcopy(self.document["reference"])
        # 自己比較の成功だけでなく、物理値を変えた場合の失敗も必要です。
        copied["entries"][0]["snapshot"]["ball"]["velocity"][0] += 0.1
        self.assertFalse(compare_traces(self.document["reference"], copied)["same_observations"])

    # {
    #   責務: [test_cli_and_original_hash_guard_on_failure: CLIの出力指定と例外時の元データ保護を確認します]
    #   処理: [1: 一時出力先でCLIを実行します; 2: ケース生成を失敗させます; 3: 元チームの指紋検証が必ず呼ばれることを確認します]
    #   引数: []
    #   戻り値: [None: 例外の握りつぶしや指紋検査の省略があれば失敗します]
    # }
    def test_cli_and_original_hash_guard_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            with patch.object(fixture, "write_ball_fixture", return_value=(path, self.hashes)):
                self.assertEqual(fixture.main(["--output", directory]), 0)
            with patch.object(fixture, "capture_case", side_effect=RuntimeError("fixture failure")), patch.object(fixture, "assert_sources_unchanged") as guard:
                with self.assertRaises(RuntimeError):
                    fixture.write_ball_fixture(Path(directory))
                guard.assert_called_once()

    # {
    #   責務: [test_runner_actual_ball_stage_and_fail_closed: 正式入口のボール検査と失敗時停止を確認します]
    #   処理: [1: 生成fixtureが実ボール検査へ渡ることを確認します; 2: ボール検査を失敗させます; 3: 後続検査が呼ばれず失敗を返すことを確認します]
    #   引数: []
    #   戻り値: [None: ボール実行の省略や失敗の上書きがあれば失敗します]
    # }
    def test_runner_actual_ball_stage_and_fail_closed(self):
        # 外部実行自体は実機検査が担当し、この試験は経路と終了コードを検査します。
        with patch.object(fixture, "write_ball_fixture", return_value=(Path("fixture.json"), {})), patch.object(runner, "run_native_trace_check", return_value=0) as checked:
            self.assertEqual(runner.run_ball_checks(Path("engine"), Path("project"), 60), 0)
            self.assertEqual(checked.call_args.args[-2:], ("ball_physics_tests.gd", "KADOCALCIO_BALL_TESTS:"))
        with patch.object(runner, "check_scripts", return_value=0), patch.object(runner, "run_ui_checks", return_value=0), patch.object(runner, "run_team_checks", return_value=0), patch.object(runner, "run_match_checks", return_value=0), patch.object(runner, "run_kernel_checks", return_value=0), patch.object(runner, "run_ball_checks", return_value=1), patch.object(runner, "check_error_detection") as checked:
            self.assertEqual(runner.execute("test", Path("engine"), Path("project"), 60, True), 1)
            checked.assert_not_called()
