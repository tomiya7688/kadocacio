import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.league.league_simulation_session import LeagueSimulationSession
from scripts.league.league_simulation_workers import _run_synchronized_match_batch


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


class _FakeMatch:
    def __init__(self, _home, _away, _venue, *, ai_rethink_multiplier=1.0) -> None:
        self.rng = random.Random()
        self.state = "PLAYING"
        self.simulation_elapsed = 0.0
        self.game_time = 0.0
        self.home = SimpleNamespace(score=0, shots=1, possession=0.5)
        self.away = SimpleNamespace(score=0, shots=1, possession=0.5)
        self.goal_scorers = []

    def start_new(self) -> None:
        return None


def _advance_fake_match(match: _FakeMatch) -> None:
    match.simulation_elapsed += 0.05
    match.game_time += 0.5
    if match.game_time >= 120.0:
        match.state = "FULLTIME"


class LeagueSimulationSessionTests(unittest.TestCase):
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
