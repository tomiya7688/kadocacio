import random
import time
import unittest
from unittest.mock import patch

from settings import MATCH_SECONDS
from team_tuner import (
    TeamTunerSession,
    _simulate_tuner_job,
    automatic_opponent_priority,
    category_mean_values,
    mutate_payload_distribution,
)


class TeamTunerOptimizerTests(unittest.TestCase):
    def test_reachable_stronger_opponent_gets_more_priority_than_easy_win(self):
        reachable, reachable_label, _ = automatic_opponent_priority({
            "得点": 1, "失点": 2, "シュート": 8, "被シュート": 9, "支配率": 48,
        })
        easy, easy_label, _ = automatic_opponent_priority({
            "得点": 5, "失点": 0, "シュート": 15, "被シュート": 2, "支配率": 68,
        })
        self.assertEqual(reachable_label, "勝てそうな格上")
        self.assertEqual(easy_label, "大幅優勢")
        self.assertGreater(reachable, easy)

    def test_close_win_has_own_class_and_remains_high_priority(self):
        close_win, label, _ = automatic_opponent_priority({
            "得点": 2, "失点": 1, "シュート": 9, "被シュート": 8, "支配率": 52,
        })
        easy, _, _ = automatic_opponent_priority({
            "得点": 5, "失点": 0, "シュート": 15, "被シュート": 2, "支配率": 68,
        })
        self.assertEqual(label, "僅差で勝っている")
        self.assertGreater(close_win, easy)

    def test_scouting_normalizes_weights_and_locks_readable_classes(self):
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": "close"}, {"id": "easy"}]
        session.opponent_names = {"close": "接戦相手", "easy": "大勝相手"}
        session.opponent_weights = {"close": 1.0, "easy": 1.0}
        session.opponent_classes = {"close": "偵察前", "easy": "偵察前"}
        session.opponent_signals = {"close": 0.0, "easy": 0.0}
        session.opponent_weights_ready = False
        close = {"得点": 1, "失点": 2, "シュート": 8, "被シュート": 9, "支配率": 48}
        easy = {"得点": 5, "失点": 0, "シュート": 15, "被シュート": 2, "支配率": 68}
        session._calibrate_opponent_weights([
            {"opponent_key": "close", "metrics": close},
            {"opponent_key": "close", "metrics": close},
            {"opponent_key": "easy", "metrics": easy},
            {"opponent_key": "easy", "metrics": easy},
        ])
        self.assertTrue(session.opponent_weights_ready)
        self.assertAlmostEqual(sum(session.opponent_weights.values()), 2.0, places=6)
        self.assertGreater(session.opponent_weights["close"], session.opponent_weights["easy"])
        self.assertEqual(session.opponent_classes["close"], "勝てそうな格上")

    def test_scouting_keeps_only_highest_priority_opponents_for_later_trials(self):
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": f"team-{index}"} for index in range(7)]
        session.opponent_names = {f"team-{index}": f"相手{index}" for index in range(7)}
        session.opponent_weights = {key: 1.0 for key in session.opponent_names}
        session.opponent_classes = {key: "偵察前" for key in session.opponent_names}
        session.opponent_signals = {key: 0.0 for key in session.opponent_names}
        session.opponent_weights_ready = False
        session.adaptive_opponent_limit = 3
        session.evaluation_mode = "speed"
        results = []
        for index in range(7):
            metrics = {
                "得点": 1, "失点": 2 if index < 3 else 0,
                "シュート": 8, "被シュート": 9 if index < 3 else 3,
                "支配率": 48 if index < 3 else 65,
            }
            results.extend([
                {"opponent_key": f"team-{index}", "metrics": metrics},
                {"opponent_key": f"team-{index}", "metrics": metrics},
            ])
        session._calibrate_opponent_weights(results)
        self.assertEqual(len(session.active_opponent_keys), 3)
        self.assertEqual(session.active_opponent_keys, {"team-0", "team-1", "team-2"})

    def test_accuracy_mode_keeps_every_scouted_opponent(self):
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": f"team-{index}"} for index in range(7)]
        session.opponent_names = {f"team-{index}": f"相手{index}" for index in range(7)}
        session.opponent_weights = {key: 1.0 for key in session.opponent_names}
        session.opponent_classes = {key: "偵察前" for key in session.opponent_names}
        session.opponent_signals = {key: 0.0 for key in session.opponent_names}
        session.opponent_weights_ready = False
        session.adaptive_opponent_limit = 3
        session.evaluation_mode = "accuracy"
        results = []
        for index in range(7):
            metrics = {"得点": index % 3, "失点": 1, "シュート": 7, "被シュート": 8, "支配率": 49}
            results.extend([
                {"opponent_key": f"team-{index}", "metrics": metrics},
                {"opponent_key": f"team-{index}", "metrics": metrics},
            ])
        session._calibrate_opponent_weights(results)
        self.assertEqual(session.active_opponent_keys, set(session.opponent_names))

    def test_local_mutation_redistributes_fields_without_changing_category_mean(self):
        category = {
            "id": "kick",
            "fields": ["シュート力", "シュート精度", "パス精度", "パス力"],
        }
        payload = {
            "選手一覧": [{
                "名前": "配分テスト", "ポジション": "FW", "プレイヤータイプ": "ストライカー",
                "シュート力": "1100", "シュート精度": "700", "パス精度": "900", "パス力": "900",
            }]
        }
        before = category_mean_values(payload, [category])["kick"]
        original = tuple(payload["選手一覧"][0][field] for field in category["fields"])

        mutate_payload_distribution(
            payload, [category], include_hidden=True, rng=random.Random(17), strength=0.12,
        )

        after = category_mean_values(payload, [category])["kick"]
        changed = tuple(payload["選手一覧"][0][field] for field in category["fields"])
        self.assertEqual(after, before)
        self.assertNotEqual(changed, original)
        self.assertEqual(sum(map(int, changed)), 3600)

    def test_repeated_mutation_can_discover_uneven_allocations(self):
        category = {"id": "kick", "fields": ["シュート力", "シュート精度", "パス精度", "パス力"]}
        payload = {"選手一覧": [{
            "ポジション": "FW", "プレイヤータイプ": "ストライカー",
            **{field: "900" for field in category["fields"]},
        }]}
        rng = random.Random(23)
        for _ in range(30):
            mutate_payload_distribution(payload, [category], include_hidden=True, rng=rng, strength=0.10)
        values = [int(payload["選手一覧"][0][field]) for field in category["fields"]]
        self.assertEqual(sum(values), 3600)
        self.assertGreater(max(values) - min(values), 100)

    def test_candidate_job_evaluates_every_opponent_home_and_away(self):
        calls = []

        class FakeCommand:
            value = "ウォーク"

        class FakePlayer:
            stamina_ratio = 0.8
            action_command = FakeCommand()

        class FakeTeam:
            def __init__(self):
                self.players = [FakePlayer()]
                self.score = 0
                self.shots = 1
                self.possession = 1.0

        class FakeMatch:
            def __init__(self, home, away, venue):
                calls.append((home.get("id"), away.get("id")))
                self.home = FakeTeam()
                self.away = FakeTeam()
                self.rng = random.Random()
                self.state = "READY"
                self.game_time = 0.0

            def update_step(self, dt):
                self.game_time = MATCH_SECONDS
                self.state = "FULLTIME"

        job = {
            "candidate": {"チーム名": "候補", "略称": "候"},
            "opponents": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}],
            "fixture_seeds": [1, 2, 3, 4],
            "clock_acceleration": 10.0,
            "wall_time_limit": 1.0,
        }
        memory_choice = {"id": "memory:tuner-worker", "name": "候補", "short": "候"}
        with patch("team_tuner.team_choice_from_payload", return_value=memory_choice), patch("team_tuner.Match", FakeMatch):
            result = _simulate_tuner_job(job)

        self.assertEqual(result["fixture_count"], 4)
        self.assertEqual(result["completed_matches"], 4)
        self.assertEqual(len(calls), 4)
        self.assertTrue(any(home == "memory:tuner-worker" for home, _ in calls))
        self.assertTrue(any(away == "memory:tuner-worker" for _, away in calls))

    def test_speed_job_completes_at_short_evaluation_target_without_clock_skip(self):
        class FakeCommand:
            value = "ウォーク"

        class FakePlayer:
            stamina_ratio = 0.8
            action_command = FakeCommand()

        class FakeTeam:
            def __init__(self):
                self.players = [FakePlayer()]
                self.score = 0
                self.shots = 1
                self.possession = 1.0

        class FakeMatch:
            def __init__(self, home, away, venue):
                self.home = FakeTeam()
                self.away = FakeTeam()
                self.rng = random.Random()
                self.state = "READY"
                self.game_time = 0.0
                self.steps = []

            def update_step(self, dt):
                self.steps.append(dt)
                self.game_time += 60.0

        job = {
            "candidate": {"チーム名": "候補", "略称": "候"},
            "opponents": [{"id": "A", "name": "A"}],
            "venues": [True],
            "fixture_seeds": [1],
            "clock_acceleration": 1.0,
            "wall_time_limit": 1.0,
            "target_game_time": 600.0,
        }
        memory_choice = {"id": "memory:tuner-worker", "name": "候補", "short": "候"}
        with patch("team_tuner.team_choice_from_payload", return_value=memory_choice), patch("team_tuner.Match", FakeMatch):
            result = _simulate_tuner_job(job)

        self.assertEqual(result["completed_matches"], 1)
        self.assertEqual(result["evaluation_target"], 600.0)
        self.assertEqual(result["metrics"]["進行率"], 600.0 / MATCH_SECONDS * 100.0)

    def test_partial_matches_cannot_be_accepted_or_report_convergence(self):
        class FinishedFuture:
            def done(self):
                return True

            def result(self):
                return {
                    "score": 999.0, "completed_matches": 0,
                    "metrics": {"進行率": 80.0},
                }

            def cancel(self):
                return None

        class FakeExecutor:
            def shutdown(self, **kwargs):
                return None

        session = TeamTunerSession.__new__(TeamTunerSession)
        future = FinishedFuture()
        session.pending_trials = {future: 0}
        session.active_parallel_candidate = {"選手一覧": []}
        session.active_parallel_results = []
        session.active_parallel_expected = 1
        session.parallel_failures = 0
        session.parallel_worker_count = 1
        session.completed_matches = 0
        session.last_score = 0.0
        session.last_metrics = {}
        session.best_score = float("-inf")
        session.best_payload = {"元": True}
        session.accepted_trials = 0
        session.stagnant_trials = 99
        session.stagnant_limit = 1
        session.trials = 3
        session.opponents = [{"name": "相手"}]
        session.deadline = time.perf_counter() - 0.1
        session.executor = FakeExecutor()
        session.finished = False
        session.finish_reason = ""
        session.parallel_enabled = True

        session._step_parallel()

        self.assertEqual(session.accepted_trials, 0)
        self.assertEqual(session.best_payload, {"元": True})
        self.assertEqual(session.completed_matches, 0)
        self.assertEqual(session.finish_reason, "時間上限に到達（完走試合なし）")


if __name__ == "__main__":
    unittest.main()
