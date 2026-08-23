import unittest

from scripts.match.match_engine import Match
from scripts.match.prediction_system import percentage_triplet
from scripts.team.team_data import discover_team_choices


class PredictionSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = discover_team_choices()

    def choice(self, text):
        return next(choice for choice in self.choices if text in choice["name"])

    def test_probabilities_are_normalized_and_percentages_total_100(self):
        match = Match(self.choice("夕張kadoka"), self.choice("私立蜜柑山"), "NEUTRAL")
        probabilities = match.predicted_probabilities()
        self.assertAlmostEqual(sum(probabilities), 1.0, places=10)
        self.assertEqual(sum(percentage_triplet(probabilities)), 100)

    def test_identical_neutral_teams_have_equal_win_probability(self):
        choice = self.choice("私立蜜柑山")
        match = Match(choice, choice, "NEUTRAL")
        home, draw, away = match.predicted_probabilities()
        self.assertAlmostEqual(home, away, places=10)
        self.assertGreater(draw, 0.10)

    def test_home_venue_improves_identical_team_forecast(self):
        choice = self.choice("私立蜜柑山")
        match = Match(choice, choice, "HOME")
        home, _, away = match.predicted_probabilities()
        self.assertGreater(home, away)

    def test_stronger_team_is_favored_without_virtual_match(self):
        match = Match(self.choice("夕張kadoka"), self.choice("負けチーム"), "NEUTRAL")
        home, draw, away = match.predicted_probabilities()
        self.assertGreater(home, draw)
        self.assertGreater(home, away)

    def test_text_uses_team_draw_team_percentage_format(self):
        match = Match(self.choice("夕張kadoka"), self.choice("私立蜜柑山"), "NEUTRAL")
        text = match.predicted_result_text()
        self.assertIn("夕張kadoka japan", text)
        self.assertIn("引き分け", text)
        self.assertIn("私立蜜柑山学園", text)
        self.assertEqual(text.count("%"), 3)

    def test_kickoff_preview_keeps_clock_at_zero(self):
        match = Match(self.choice("夕張kadoka"), self.choice("私立蜜柑山"), "NEUTRAL")
        match.start_new()
        match.update_step(0.05)
        self.assertEqual(match.game_time, 0.0)
        match.banner_timer = 0.0
        match.update_step(0.05)
        self.assertGreater(match.game_time, 0.0)


if __name__ == "__main__":
    unittest.main()
