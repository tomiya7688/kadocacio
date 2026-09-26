"""Completed match results are detached from mutable simulation state."""

import json
import unittest
from dataclasses import FrozenInstanceError

from scripts.league.league_simulation_workers import _match_output
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices


class MatchResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = discover_team_choices()

    def new_match(self) -> Match:
        return Match(self.choices[0], self.choices[1], "NEUTRAL")

    def test_result_is_unavailable_before_full_time(self):
        match = self.new_match()
        with self.assertRaisesRegex(RuntimeError, "full time"):
            match.final_result()
        self.assertEqual(_match_output(match)["home_score"], 0)

    def test_result_is_immutable_and_serializable(self):
        match = self.new_match()
        match.home.score, match.away.score = 2, 1
        match.home.shots, match.away.shots = 6, 4
        match.home.possession, match.away.possession = 0.55, 0.45
        match.goal_scorers.append((25, "選手A"))
        match.game_time = 5400.0
        match.state = "FULLTIME"

        result = match.final_result()
        payload = result.to_payload()
        self.assertEqual(result.winner, "HOME")
        self.assertEqual(payload, _match_output(match))
        self.assertEqual(json.loads(json.dumps(payload))["goal_scorers"], [[25, "選手A"]])
        with self.assertRaises(FrozenInstanceError):
            result.home_score = 9

        match.home.score = 9
        match.goal_scorers.clear()
        payload["goal_scorers"].clear()
        self.assertEqual(result.home_score, 2)
        self.assertEqual(result.goal_scorers, ((25, "選手A"),))


if __name__ == "__main__":
    unittest.main()
