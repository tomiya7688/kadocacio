import random
import unittest

from scripts.match.intelligence_system import choose_utility_action, strategic_possession_risk
from scripts.match.skill_system import activation_probability


class IntelligenceScalingTests(unittest.TestCase):
    @staticmethod
    def _correct_choice_rate(intelligence: float, gap: float, trials: int = 12000) -> float:
        rng = random.Random(123)
        choices = {
            "正解": 0.5 + gap,
            "不正解": 0.5,
        }
        correct = sum(
            choose_utility_action(choices, intelligence, rng) == "正解"
            for _ in range(trials)
        )
        return correct / trials

    def test_higher_intelligence_makes_close_utility_choices_more_reliable(self):
        low = self._correct_choice_rate(0.0, 0.08)
        middle = self._correct_choice_rate(0.5, 0.08)
        high = self._correct_choice_rate(1.0, 0.08)

        self.assertLess(low, middle)
        self.assertLess(middle, high)
        self.assertGreater(high - low, 0.25)

    def test_even_low_intelligence_usually_recognizes_a_clear_advantage(self):
        low = self._correct_choice_rate(0.0, 0.20)
        high = self._correct_choice_rate(1.0, 0.20)

        self.assertGreater(low, 0.78)
        self.assertGreater(high, 0.98)

    def test_high_intelligence_uses_skills_more_selectively(self):
        low_good = activation_probability(0.0, 0.8, 0.8)
        high_good = activation_probability(1.0, 0.8, 0.8)
        low_bad = activation_probability(0.0, 0.2, 0.8)
        high_bad = activation_probability(1.0, 0.2, 0.8)

        self.assertGreater(high_good, low_good * 4.0)
        self.assertLess(high_bad, low_bad)
        self.assertGreater(high_good / high_bad, low_good / low_bad * 4.0)

    def test_intelligence_protects_possession_more_near_own_goal(self):
        low_pass, low_dribble = strategic_possession_risk(0.1, 0.12, 0.9, 0.35, 0.75)
        high_pass, high_dribble = strategic_possession_risk(1.0, 0.12, 0.9, 0.35, 0.75)
        attacking_pass, attacking_dribble = strategic_possession_risk(1.0, 0.88, 0.9, 0.35, 0.75)

        self.assertGreater(high_pass, low_pass)
        self.assertGreater(high_dribble, low_dribble)
        self.assertGreater(high_pass, attacking_pass)
        self.assertGreater(high_dribble, attacking_dribble)

    def test_dribble_technique_preserves_the_escape_option(self):
        _, weak_dribble = strategic_possession_risk(1.0, 0.18, 0.9, 0.1, 0.2)
        _, strong_dribble = strategic_possession_risk(1.0, 0.18, 0.9, 0.95, 0.2)
        self.assertGreater(weak_dribble, strong_dribble)


if __name__ == "__main__":
    unittest.main()
