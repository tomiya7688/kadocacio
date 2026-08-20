import json
import random
import unittest
from pathlib import Path

from team_data import discover_team_choices
from team_editor_config import load_tuner_options
from team_tuner import TeamTunerSession, category_mean_values


ROOT = Path(__file__).resolve().parents[1]


class TeamTunerMeanLockTests(unittest.TestCase):
    def setUp(self):
        team_path = next((ROOT / "teams").rglob("負けチーム.json"))
        self.payload = json.loads(team_path.read_text(encoding="utf-8-sig"))
        self.categories = tuple(load_tuner_options()["categories"])

    def test_simulation_does_not_replace_current_means_with_configured_targets(self):
        before = category_mean_values(self.payload, self.categories)
        targets = {category_id: 1250 for category_id in before}
        opponent = discover_team_choices()[0]
        session = TeamTunerSession(
            self.payload, [opponent], targets, self.categories,
            time_limit=0.2, include_hidden=True,
            worker_count=1, max_workers=1, rng=random.Random(7),
        )
        try:
            after = category_mean_values(session.best_payload, self.categories)
            for category_id, original in before.items():
                self.assertAlmostEqual(after[category_id], original, delta=0.01)
        finally:
            session.cancel()

    def test_every_mutated_candidate_stays_within_ten_points(self):
        before = category_mean_values(self.payload, self.categories)
        opponent = discover_team_choices()[0]
        session = TeamTunerSession(
            self.payload, [opponent], {key: 1250 for key in before}, self.categories,
            time_limit=0.2, include_hidden=True,
            worker_count=1, max_workers=1, rng=random.Random(11),
        )
        try:
            for trial in range(1, 8):
                candidate = session._make_parallel_candidate(trial)
                means = category_mean_values(candidate, self.categories)
                for category_id, original in before.items():
                    self.assertLessEqual(abs(means[category_id] - original), 10.0)
        finally:
            session.cancel()

    def test_single_core_partial_match_is_not_accepted(self):
        before = json.loads(json.dumps(self.payload, ensure_ascii=False))
        opponent = discover_team_choices()[0]
        session = TeamTunerSession(
            self.payload, [opponent], category_mean_values(self.payload, self.categories), self.categories,
            time_limit=0.001, include_hidden=True,
            worker_count=1, max_workers=1, rng=random.Random(19),
        )
        while not session.finished:
            session.step(1.0)
        self.assertEqual(session.completed_matches, 0)
        self.assertEqual(session.accepted_trials, 0)
        self.assertEqual(session.best_payload, before)
        self.assertEqual(session.finish_reason, "時間上限に到達（完走試合なし）")

    def test_convergence_mode_has_no_deadline_and_uses_stagnation_progress(self):
        opponent = discover_team_choices()[0]
        session = TeamTunerSession(
            self.payload, [opponent], category_mean_values(self.payload, self.categories), self.categories,
            time_limit=None, include_hidden=True, stagnant_limit=6,
            worker_count=1, max_workers=1, worker_match_time_limit=8.0,
            rng=random.Random(29),
        )
        try:
            self.assertTrue(session.convergence_only)
            self.assertEqual(session.deadline, float("inf"))
            self.assertEqual(session.worker_match_time_limit, 8.0)
            session.stagnant_trials = session.stagnant_limit // 2
            self.assertAlmostEqual(session.progress, 0.5)
            self.assertIn("収束まで", session.status_text())
        finally:
            session.cancel()


if __name__ == "__main__":
    unittest.main()
