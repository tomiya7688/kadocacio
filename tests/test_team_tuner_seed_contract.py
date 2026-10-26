"""チューナーの構築seed・対象側・固定更新入口の配線を隔離して確認する。"""

import random
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.team.team_tuner import TeamTunerSession, _simulate_tuner_job


# {
#   責務: [TeamTunerSeedContractTests: 候補比較のseedとホーム/アウェーの対象側が両経路で維持されることを検査する]
#   フィールド: []
# }
class TeamTunerSeedContractTests(unittest.TestCase):
    # {
    #   責務: [make_team: 候補と相手を集計値で区別できる模擬チームを作る]
    #   処理: [1: メモリ候補かを判定し独立した集計用状態を返す]
    #   引数: [choice: Match構築時のチーム情報]
    #   戻り値: [SimpleNamespace: 候補は得点3・保持量3、相手は得点1・保持量1の試験値]
    # }
    def make_team(self, choice):
        # 実チームデータを読まず、側を取り違えると集計値が反転するようにする。
        target = choice.get("kind") == "MEMORY"
        player = SimpleNamespace(stamina_ratio=0.8 if target else 0.2, action_command="ドリブル" if target else "待機")
        return SimpleNamespace(
            players=[player], score=3 if target else 1, shots=7 if target else 2, possession=3 if target else 1
        )

    # {
    #   責務: [make_match: 構築seedを独立乱数器へ適用する模擬Matchを返す]
    #   処理: [1: 両側の試験状態とseedを保存する]
    #   引数: [home・away: 開始入力; venue: 会場; seed: 構築時に渡されたseed]
    #   戻り値: [SimpleNamespace: 初期状態の模擬試合。実物理や子プロセスは起動しない]
    # }
    def make_match(self, home, away, venue, *, seed=None):
        # rng.seedの後付けを必要としない構築契約を模擬する。
        return SimpleNamespace(
            home=self.make_team(home),
            away=self.make_team(away),
            seed=seed,
            rng=random.Random(seed),
            state="READY",
            game_time=0.0,
        )

    # {
    #   責務: [advance_fixture: 模擬試合を採取周期が通る一定量だけ進める]
    #   処理: [1: 模擬時計を3秒進める]
    #   引数: [match: 模擬試合]
    #   戻り値: [None: 模擬時計のみ更新。実エンジンの時計早送りを実装するものではない]
    # }
    def advance_fixture(self, match):
        # 60秒目標まで20回進み、18更新目の行動採取を一度通す。
        match.game_time += 3.0

    # {
    #   責務: [test_worker_preserves_seed_order_and_candidate_metrics: 相手順・会場順のseedと候補基準の集計を確認する]
    #   処理: [1: 明示seed・不足時の連番・アウェーだけの条件を準備する; 2: 模擬ジョブを実行する; 3: 構築引数・巡回更新・実集計を照合する]
    #   引数: []
    #   戻り値: [None: seed=0の欠落、対象側の反転、更新省略、入力書換えは試験失敗]
    # }
    def test_worker_preserves_seed_order_and_candidate_metrics(self):
        # 各条件の期限は決定的に制御し、不具合でも無限待ちにならないようにする。
        for seeds, venues, expected in (
            ([0, 81, "92", 5], [True, False], [0, 81, 92, 5]),
            ([0], [True, False], [0, 1, 2, 3]),
            ([0, 81], [False], [0, 81]),
        ):
            with self.subTest(seeds=seeds, venues=venues):
                job = {
                    "candidate": {"チーム名": "候補", "選手一覧": []},
                    "opponents": [{"id": "A"}, {"id": "B"}],
                    "fixture_seeds": seeds,
                    "venues": venues,
                    "wall_time_limit": 1,
                    "target_game_time": 60,
                }
                original = deepcopy(job)
                choice = {"name": "候補"}
                with (
                    patch("scripts.team.team_tuner.team_choice_from_payload", return_value=choice),
                    patch("scripts.team.team_tuner.Match", side_effect=self.make_match) as constructor,
                    patch("scripts.team.team_tuner.advance_match_fixed", side_effect=self.advance_fixture) as advance,
                    patch("scripts.team.team_tuner.CpuUsageLimiter"),
                    patch("scripts.team.team_tuner.time.perf_counter", side_effect=[0.0] * 500 + [2.0] * 20),
                ):
                    result = _simulate_tuner_job(job)
                # 構築前からseedを渡し、相手ごとの会場順も維持する。
                self.assertEqual([call.kwargs["seed"] for call in constructor.call_args_list], expected)
                expected_sides = [(opponent, side) for opponent in ("A", "B") for side in venues]
                for call, (opponent, is_home) in zip(constructor.call_args_list, expected_sides):
                    self.assertEqual(call.args[2], "HOME")
                    self.assertEqual(call.args[1 if is_home else 0]["id"], opponent)
                    self.assertEqual(call.args[0 if is_home else 1]["kind"], "MEMORY")
                updates = [call.args[0] for call in advance.call_args_list]
                self.assertEqual(len(updates), len(expected) * 20)
                self.assertEqual([id(match) for match in updates], [id(match) for match in updates[: len(expected)]] * 20)
                # 実スコア集計を使い、アウェーでも候補の行動・体力・保持率になることを確認する。
                self.assertEqual(result["completed_matches"], len(expected))
                self.assertEqual(result["fixture_count"], len(expected))
                for metric, value in (
                    ("得点", 3),
                    ("失点", 1),
                    ("支配率", 75),
                    ("残スタミナ", 80),
                    ("行動種類", 1),
                    ("活動率", 100),
                ):
                    self.assertAlmostEqual(result["metrics"][metric], value)
                self.assertEqual(job, original)

    # {
    #   責務: [test_serial_trials_reuse_fixture_seeds_and_reset_samples: 逐次対戦の循環seedと対象側・採取リセットを確認する]
    #   処理: [1: 固定乱数の逐次セッションを作る; 2: 4対戦と次周期の初戦を構築する; 3: seed・対象側・入力の独立性を照合する]
    #   引数: []
    #   戻り値: [None: seedの再抽選、候補側反転、集計持越し、入力変更、グローバル乱数変更は試験失敗]
    # }
    def test_serial_trials_reuse_fixture_seeds_and_reset_samples(self):
        # workerを使わない構成で、通常の初期化から逐次入口へ到達する。
        payload = {"チーム名": "候補", "選手一覧": []}
        original = deepcopy(payload)
        global_state = random.getstate()
        expected_rng = random.Random(17)
        expected_seeds = tuple(expected_rng.randrange(0, 2**31) for _ in range(4))
        with (
            patch("scripts.team.team_tuner.team_choice_from_payload", return_value={"name": "候補"}),
            patch("scripts.team.team_tuner.Match", side_effect=self.make_match),
        ):
            session = TeamTunerSession(
                payload,
                [{"id": "A"}, {"id": "B"}],
                {},
                (),
                time_limit=1,
                include_hidden=True,
                worker_count=1,
                max_workers=1,
                rng=random.Random(17),
            )
            for trial in range(5):
                with self.subTest(trial=trial):
                    session.trials = trial
                    session.command_counts["待機"] = 9
                    session.sample_counter = session.active_samples = session.total_player_samples = 9
                    session._begin_trial()
                    self.assertEqual(session.current_match.seed, expected_seeds[trial % 4])
                    target = session.current_match.home if trial % 2 == 0 else session.current_match.away
                    self.assertIs(session.current_target_team, target)
                    self.assertEqual(session.current_opponent["id"], "A" if trial % 4 < 2 else "B")
                    self.assertEqual(session.command_counts, {})
                    self.assertEqual((session.sample_counter, session.active_samples, session.total_player_samples), (0, 0, 0))
                    self.assertIsNot(session.current_candidate, payload)
                    self.assertEqual(session.current_match.state, "PLAYING")
        self.assertEqual(session.fixture_seeds, expected_seeds)
        self.assertEqual(payload, original)
        self.assertEqual(random.getstate(), global_state)

    # {
    #   責務: [test_parallel_jobs_keep_original_fixture_seeds_after_filtering: 並列ジョブの分割後も対戦固有seedを維持することを確認する]
    #   処理: [1: 模擬executorで全4対戦を投入する; 2: Bだけを残して次候補を投入する; 3: 元対戦番号のseedと会場を照合する]
    #   引数: []
    #   戻り値: [None: 絞込後のseed再採番・会場反転・ジョブ入口変更は試験失敗。実IPCは検証しない]
    # }
    def test_parallel_jobs_keep_original_fixture_seeds_after_filtering(self):
        # 実プロセスを作らず、executorへ渡すpickle可能なジョブだけを確認する。
        executor = Mock()
        executor.submit.side_effect = [object() for _ in range(6)]
        with (
            patch("scripts.team.team_tuner.os.cpu_count", return_value=4),
            patch("scripts.team.team_tuner.ProcessPoolExecutor", return_value=executor),
        ):
            session = TeamTunerSession(
                {"選手一覧": []},
                [{"id": "A"}, {"id": "B"}],
                {},
                (),
                time_limit=60,
                include_hidden=True,
                worker_count=2,
                max_workers=2,
                rng=random.Random(17),
            )
            session.opponent_weights_ready = True
            session.active_opponent_keys = {"B"}
            session.active_parallel_candidate = None
            session.pending_trials.clear()
            session.trials = 1
            session._submit_parallel_trials()
        # 絞込前の0,1,2,3と、絞込後の2,3が同じ比較seedを使う。
        self.assertEqual(executor.submit.call_count, 6)
        for call, index in zip(executor.submit.call_args_list, (0, 1, 2, 3, 2, 3)):
            self.assertIs(call.args[0], _simulate_tuner_job)
            job = call.args[1]
            self.assertEqual(job["fixture_seeds"], [session.fixture_seeds[index]])
            self.assertEqual(job["venues"], [index % 2 == 0])
            self.assertEqual(job["opponents"][0]["id"], "A" if index < 2 else "B")


if __name__ == "__main__":
    unittest.main()
