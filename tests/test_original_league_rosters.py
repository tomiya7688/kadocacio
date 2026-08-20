import json
import unittest
from pathlib import Path

from team_editor_config import load_tuner_options
from team_editor_data import load_editor_payload
from team_tuner import category_mean_values


ROOT = Path(__file__).resolve().parents[1]


class OriginalLeagueRosterTests(unittest.TestCase):
    def _scores(self, folder_name):
        categories = tuple(load_tuner_options()["categories"])
        scores = []
        for path in (ROOT / "teams" / folder_name).glob("*.json"):
            payload, issues = load_editor_payload(path)
            self.assertFalse(issues, f"{path}: {issues}")
            means = category_mean_values(payload, categories)
            scores.append(sum(means.values()) / len(means))
        return scores

    def test_a_and_b_have_twenty_valid_teams_with_clear_strength_gap(self):
        a_scores = self._scores("kadoka_original_A")
        b_scores = self._scores("kadoka_original_B")
        self.assertEqual(len(a_scores), 20)
        self.assertEqual(len(b_scores), 20)
        self.assertGreater(min(a_scores), max(b_scores))

    def test_league_definitions_place_a_above_b(self):
        payload = json.loads((ROOT / "leagues.json").read_text(encoding="utf-8-sig"))
        definitions = {entry["リーグ名"]: entry for entry in payload["リーグ一覧"]}
        self.assertEqual(len(definitions["Aリーグ"]["所属チーム"]), 20)
        self.assertEqual(len(definitions["Bリーグ"]["所属チーム"]), 20)
        self.assertEqual(definitions["Aリーグ"]["上位リーグ"], "")
        self.assertEqual(definitions["Bリーグ"]["上位リーグ"], "Aリーグ")


if __name__ == "__main__":
    unittest.main()
