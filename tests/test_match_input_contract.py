"""The match domain receives teams; it does not discover or load them."""

import unittest

from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices


class MatchInputContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = discover_team_choices()

    def test_preloaded_teams_create_match(self):
        match = Match(self.choices[0], self.choices[1], "NEUTRAL")
        self.assertEqual(match.home.name, self.choices[0]["name"])
        self.assertEqual(match.away.name, self.choices[1]["name"])

    def test_missing_team_is_rejected_without_discovery(self):
        with self.assertRaisesRegex(ValueError, "two preloaded team choices"):
            Match(None, self.choices[0])
        with self.assertRaisesRegex(ValueError, "two preloaded team choices"):
            Match(self.choices[0], None)


if __name__ == "__main__":
    unittest.main()
