import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.core.match_seed import league_fixture_seed
from scripts.league.league_simulation_session import LeagueSimulationSession
from scripts.league.league_simulation_workers import _run_headless_league_match, _run_synchronized_match_batch
from scripts.match.match_result import MatchResult


class _SharedValue:
    def __init__(self, value: float) -> None:
        self.value = value


class _Queue:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def put(self, payload: dict) -> None:
        self.messages.append(dict(payload))


class _Event:
    def is_set(self) -> bool:
        return False


# {
#   責務: [_FakeMatch: ワーカーの配線・通知試験に使う短い模擬試合状態を保持する]
#   フィールド: [
#     rng: 構築時seedで作る専用乱数器
#     state・game_time・simulation_elapsed: 模擬更新の終了状態と二種類の時計
#     home・away・goal_scorers: 結果組立てに使う固定集計
#     restart_type・restart_elapsed・restart_counts: 再開処理を模擬しないことを表す空の観測値
#   ]
# }
class _FakeMatch:
    # {
    #   責務: [__init__: 構築時seedとワーカー結果に必要な最小の模擬値を準備する]
    #   処理: [1: seed指定の乱数器を作る; 2: 時計・固定集計・空の再開情報を設定する]
    #   引数: [_home・_away・_venue・ai_rethink_multiplier: 実Match互換の未使用引数; seed: ワーカーが構築前から指定する値]
    #   戻り値: [None: 試験専用状態を初期化する。選手AI・物理・再開処理の再現ではない]
    # }
    def __init__(self, _home, _away, _venue, *, ai_rethink_multiplier=1.0, seed=None) -> None:
        # 後からseedを設定する実装へ退行しても見落とさないよう、構築引数を受ける。
        self.rng = random.Random(seed)
        self.state = "PLAYING"
        self.simulation_elapsed = 0.0
        self.game_time = 0.0
        self.home = SimpleNamespace(score=0, shots=1, possession=0.5)
        self.away = SimpleNamespace(score=0, shots=1, possession=0.5)
        self.goal_scorers = []
        self.restart_type = ""
        self.restart_elapsed = 0.0
        self.restart_counts = {}

    # {
    #   責務: [start_new: 実Matchと同じ開始呼出し口を模擬する]
    #   処理: [1: 構築済みの初期値を変更せず返る]
    #   引数: []
    #   戻り値: [None: 新たな抽選や初期選手の生成は模擬しない]
    # }
    def start_new(self) -> None:
        # この二重化オブジェクトは構築時からPLAYINGであり、実試合の開始処理とは異なる。
        return None

    # {
    #   責務: [final_result: 模擬完走状態から実際の結果型を組み立てる]
    #   処理: [1: 模擬試合の完走を確認する; 2: 固定集計と時計からMatchResultを作る]
    #   引数: []
    #   戻り値: [MatchResult: 模擬値の結果。未完走を完走扱いで呼ぶとRuntimeError]
    # }
    def final_result(self) -> MatchResult:
        # ワーカーが途中状態を完走結果として扱う配線の誤りを検出する。
        if self.state != "FULLTIME":
            raise RuntimeError("not finished")
        return MatchResult(
            self.home.score, self.away.score,
            self.home.shots, self.away.shots,
            self.home.possession, self.away.possession,
            tuple(self.goal_scorers), self.game_time,
        )


def _advance_fake_match(match: _FakeMatch) -> None:
    match.simulation_elapsed += 0.05
    match.game_time += 0.5
    if match.game_time >= 120.0:
        match.state = "FULLTIME"


# {
#   責務: [LeagueSimulationSessionTests: 途中経過・終了順・バッチ配線を制御した二重化オブジェクトで検査する]
#   フィールド: []
# }
class LeagueSimulationSessionTests(unittest.TestCase):
    # {
    #   責務: [test_both_workers_pass_each_fixture_seed_to_constructor: 単独と同期バッチの両経路が各対戦seedを構築引数で渡すことを確認する]
    #   処理: [1: IDだけが異なる二対戦を準備する; 2: 両ワーカー入口を模擬Matchと3固定更新で呼ぶ; 3: 呼出し順・構築seed・未完走の区別を照合する]
    #   引数: []
    #   戻り値: [None: 共通seedの未指定・対戦間の使い回し・終了状態の誤認は試験失敗。実プロセス間通信の試験ではない]
    # }
    def test_both_workers_pass_each_fixture_seed_to_constructor(self) -> None:
        # 名前が同じ対戦でも、fixture IDごとのseedを各構築へ渡す必要がある。
        jobs = [{"fixture": {"id": fixture_id}, "home_choice": {"name": "home"},
                 "away_choice": {"name": "away"}, "max_match_steps": 3}
                for fixture_id in ("fixture-second", "fixture-first")]
        for mode in ("headless", "synchronized"):
            with self.subTest(mode=mode):
                with patch("scripts.league.league_simulation_workers.Match", side_effect=_FakeMatch) as construct:
                    with patch("scripts.league.league_simulation_workers.advance_match_fixed",
                               side_effect=_advance_fake_match):
                        if mode == "headless":
                            results = [_run_headless_league_match(job) for job in jobs]
                        else:
                            results = _run_synchronized_match_batch(jobs, _SharedValue(-1.0), _Queue(), _Event())
                self.assertEqual(construct.call_count, len(jobs))
                self.assertEqual(len(results), len(jobs))
                for call, job, result in zip(construct.call_args_list, jobs, results):
                    self.assertEqual(call.kwargs["seed"], league_fixture_seed(job["fixture"]["id"], "home", "away"))
                    self.assertEqual(result["fixture_id"], job["fixture"]["id"])
                    self.assertEqual(result["engine_steps"], 3)
                    self.assertFalse(result["fulltime"])
                    self.assertEqual(result["finish_reason"], "step_limit")

    def test_display_progress_counts_finished_matches_inside_worker_batches(self) -> None:
        session = LeagueSimulationSession.__new__(LeagueSimulationSession)
        session.total = 3
        session.completed = 0
        session.live_status = {
            "a": {"state": "FULLTIME", "game_time": 5400.0},
            "b": {"state": "PLAYING", "game_time": 2700.0},
            "c": {"state": "FULLTIME", "game_time": 5400.0},
        }

        self.assertEqual(session.display_completed, 2)
        self.assertEqual(session.display_average_minute, 75)
        self.assertAlmostEqual(session.progress, 2 / 3)

    def test_fast_finish_keeps_fixed_steps_and_reduces_ipc_reports(self) -> None:
        queue = _Queue()
        batch_size = 30  # One worker's share when 90 matches use three workers.
        jobs = [
            {
                "fixture": {"id": f"fixture-{index}"},
                "home_choice": {"name": f"home-{index}"},
                "away_choice": {"name": f"away-{index}"},
                "cpu_duty_cycle": 1.0,
                "simulation_mode": "PRECISE",
                "ai_rethink_multiplier": 1.0,
            }
            for index in range(batch_size)
        ]
        with patch("scripts.league.league_simulation_workers.Match", _FakeMatch), patch(
            "scripts.league.league_simulation_workers.advance_match_fixed",
            side_effect=_advance_fake_match,
        ) as advance:
            results = _run_synchronized_match_batch(
                jobs,
                _SharedValue(-1.0),
                queue,
                _Event(),
            )

        self.assertEqual(len(results), batch_size)
        self.assertTrue(all(result["engine_steps"] == 240 for result in results))
        self.assertEqual(advance.call_count, 240 * batch_size)
        self.assertLessEqual(len(queue.messages), 4 * batch_size)
        self.assertEqual(queue.messages[-1]["state"], "FULLTIME")

    def test_normal_shutdown_reaps_workers_before_manager(self) -> None:
        events: list[object] = []

        class Executor:
            def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
                events.append(("executor", wait, cancel_futures))

        class Manager:
            def shutdown(self) -> None:
                events.append("manager")

        session = LeagueSimulationSession.__new__(LeagueSimulationSession)
        session.executor = Executor()
        session.process_manager = Manager()
        session.progress_queue = object()
        session.sync_clock = object()
        session.cancel_event = object()
        session._drain_progress = lambda: events.append("drain")

        session._shutdown()

        self.assertEqual(events, [("executor", True, False), "drain", "manager"])
        self.assertIsNone(session.executor)
        self.assertIsNone(session.process_manager)
        self.assertIsNone(session.progress_queue)
        self.assertIsNone(session.sync_clock)
        self.assertIsNone(session.cancel_event)


if __name__ == "__main__":
    unittest.main()
