"""The AI evaluator must seed construction and report the requested team's metrics."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.core.simulation_limits import SimulationLimits
from scripts.team.team_data import discover_team_choices
from scripts.tools.ai_evaluator import _run_evaluation_job


# {
#   責務: [AiEvaluationJobTests: AI評価ジョブの構築引数・対象側の集計・終了状態を検査する]
#   フィールド: []
# }
class AiEvaluationJobTests(unittest.TestCase):
    # {
    #   責務: [job: 評価ジョブに必要な試験専用条件を作る]
    #   処理: [1: seed=0・短い目標時刻・集計対象側を独立した辞書へ設定する]
    #   引数: [target_is_home: 評価対象をホーム側に置くか]
    #   戻り値: [dict: 模擬チームの条件。実試合の試験ではチームだけ差し替える]
    # }
    def job(self, target_is_home):
        # valueは評価条件のラベルであり、この窓口で能力を書き換える値ではない。
        return {
            "target": {"name": "target"},
            "opponent": {"name": "opponent"},
            "target_is_home": target_is_home,
            "seed": 0,
            "value": 2500,
            "wall_time_limit": 10.0,
            "target_game_time": 0.5,
            "cpu_duty_cycle": 0.6,
        }

    # {
    #   責務: [test_constructor_limits_and_target_metrics: 構築seed・演算条件・対象側の集計が正しく接続されることを確認する]
    #   処理: [1: 両側と保持量ゼロのケースを模擬する; 2: 評価入口を呼ぶ; 3: 構築引数・上限・集計対象と部分終了を照合する]
    #   引数: []
    #   戻り値: [None: seed省略・対象側の逆転・未完走の誤認は試験失敗。AIや物理の試験ではない]
    # }
    def test_constructor_limits_and_target_metrics(self):
        # 集計値に左右差を付け、ホームの値を常に返す退行を検出する。
        for at_home, possession, share in ((True, (45, 15), 0.75), (False, (45, 15), 0.25), (True, (0, 0), 0.5)):
            with self.subTest(at_home=at_home, possession=possession):
                home = SimpleNamespace(
                    score=2,
                    shots=7,
                    possession=possession[0],
                    players=[SimpleNamespace(stamina_ratio=0.8), SimpleNamespace(stamina_ratio=0.6)],
                )
                away = SimpleNamespace(
                    score=1,
                    shots=3,
                    possession=possession[1],
                    players=[SimpleNamespace(stamina_ratio=0.3), SimpleNamespace(stamina_ratio=0.1)],
                )
                match = SimpleNamespace(home=home, away=away, state="READY")
                result = SimpleNamespace(
                    reason="target_game_time", steps=1, elapsed_seconds=0.25, game_time=0.5, fulltime=False
                )
                job = self.job(at_home)
                with (
                    patch("scripts.tools.ai_evaluator.Match", return_value=match) as construct,
                    patch("scripts.tools.ai_evaluator.MatchTelemetry") as observe,
                    patch("scripts.tools.ai_evaluator.run_headless_match", return_value=result) as run,
                ):
                    observe.return_value.team_metrics.return_value = {"takeaways": 9}
                    row = _run_evaluation_job(job)
                ordered = (job["target"], job["opponent"]) if at_home else (job["opponent"], job["target"])
                construct.assert_called_once_with(*ordered, "NEUTRAL", seed=0)
                observe.assert_called_once_with(match)
                target, opponent = (home, away) if at_home else (away, home)
                observe.return_value.team_metrics.assert_called_once_with(target)
                run.assert_called_once_with(
                    match,
                    SimulationLimits(
                        wall_time_limit=10.0,
                        target_game_time=0.5,
                        sample_every_steps=18,
                        cpu_duty_cycle=0.6,
                    ),
                    observe.return_value,
                )
                self.assertEqual(match.state, "PLAYING")
                self.assertEqual((row["seed"], row["value"], row["target_is_home"]), (0, 2500, at_home))
                self.assertEqual(row["simulation"], vars(result))
                self.assertEqual(row["metrics"]["goals_for"], target.score)
                self.assertEqual(row["metrics"]["goals_against"], opponent.score)
                self.assertEqual(row["metrics"]["shots_for"], target.shots)
                self.assertEqual(row["metrics"]["shots_against"], opponent.shots)
                self.assertEqual(row["metrics"]["takeaways"], 9)
                self.assertEqual(row["metrics"]["possession_share"], share)
                self.assertAlmostEqual(row["metrics"]["remaining_stamina"], 0.7 if at_home else 0.2)

    # {
    #   責務: [test_real_partial_evaluations_repeat_without_wall_timing: 実Matchの短い評価が同条件で同じ指標・終了状態になることを確認する]
    #   処理: [1: 有効な両チームとCPU待機なしの条件を準備する; 2: 両側それぞれで同条件を二度実行する; 3: 実測秒数を除く結果を照合する]
    #   引数: []
    #   戻り値: [None: 条件再現や部分終了の退行は試験失敗。90分・実時間上限までの再現・実子プロセスは検証しない]
    # }
    def test_real_partial_evaluations_repeat_without_wall_timing(self):
        # 実試合を使うが目標到達前の実時間上限終了を許容せず、計時値だけを比較から外す。
        target, opponent = discover_team_choices()[:2]
        for at_home in (True, False):
            with self.subTest(at_home=at_home):
                job = {**self.job(at_home), "target": target, "opponent": opponent, "cpu_duty_cycle": 1.0}
                first = _run_evaluation_job(job)
                second = _run_evaluation_job(job)
                for row in (first, second):
                    self.assertEqual(row["simulation"]["reason"], "target_game_time")
                    self.assertFalse(row["simulation"]["fulltime"])
                    row["simulation"].pop("elapsed_seconds")
                self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
