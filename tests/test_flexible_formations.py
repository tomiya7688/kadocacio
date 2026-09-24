import random
import unittest

from scripts.match.match_engine import Match
from scripts.team.team_data import team_choice_from_payload
from scripts.team.team_editor_data import add_default_player, create_team_template, validate_payload


class FlexibleFormationTests(unittest.TestCase):
    @staticmethod
    def formation(starters: int = 11, keepers: int = 1) -> dict:
        payload = create_team_template("initial", rng=random.Random(7))
        players = payload["選手一覧"]
        for index, player in enumerate(players):
            if index >= starters:
                player["ポジションX"] = "0"
                player["ポジションY"] = "0"
                player["ポジション"] = "控え"
            elif index < keepers:
                player["ポジションX"] = "8"
                player["ポジションY"] = "11"
                player["ポジション"] = "GK"
            else:
                # Deliberately permit an extreme 10-0-0 all-defender formation.
                player["ポジションX"] = str(index + 1)
                player["ポジションY"] = "8"
                player["ポジション"] = "DF"
        return payload

    def test_ten_zero_zero_is_valid(self):
        payload = self.formation(11, 1)
        self.assertFalse(validate_payload(payload))
        choice = team_choice_from_payload(payload)
        self.assertEqual(len(choice["starters"]), 11)
        self.assertEqual(sum(player["position_y"] == 11 for player in choice["starters"]), 1)

    def test_seven_players_and_multiple_goalkeepers_are_valid(self):
        payload = self.formation(7, 2)
        self.assertFalse(validate_payload(payload))
        self.assertEqual(len(team_choice_from_payload(payload)["starters"]), 7)

    def test_all_goalkeeper_lineup_can_start_restart_and_substitute(self):
        payload = self.formation(7, 7)
        self.assertFalse(validate_payload(payload))
        choice = team_choice_from_payload(payload)
        opponent = team_choice_from_payload(self.formation(11, 1))
        match = Match(choice, opponent, "NEUTRAL")
        team = match.home
        self.assertTrue(all(player.is_keeper and player.zone_rank == 0.0 for player in team.players))

        match.start_new()
        match.update(0.05)
        self.assertTrue(all(player.is_keeper and player.zone_rank == 0.0 for player in team.players))
        self.assertTrue(match.execute_substitution(team, team.players[0], team.bench[0]))
        match.update(0.05)
        self.assertTrue(all(player.is_keeper and player.zone_rank == 0.0 for player in team.players))

        match.start_new()
        self.assertTrue(all(player.is_keeper and player.zone_rank == 0.0 for player in team.players))

    def test_outfield_zone_ranks_preserve_extremes(self):
        payload = self.formation(11, 1)
        payload["選手一覧"][1]["ポジションY"] = "3"
        payload["選手一覧"][2]["ポジションY"] = "10"
        choice = team_choice_from_payload(payload)
        match = Match(choice, choice, "NEUTRAL")
        outfield = [player for player in match.home.players if not player.is_keeper]
        self.assertEqual(min(player.zone_rank for player in outfield), 0.0)
        self.assertEqual(max(player.zone_rank for player in outfield), 1.0)

    def test_fewer_than_seven_is_invalid(self):
        issues = validate_payload(self.formation(6, 1))
        self.assertTrue(any(issue.path == "フォーメーション" and "7〜11人" in issue.message for issue in issues))

    def test_more_than_eleven_is_invalid(self):
        payload = self.formation(11, 1)
        index = add_default_player(payload, random.Random(9))
        extra = payload["選手一覧"][index]
        extra["ポジションX"] = "15"
        extra["ポジションY"] = "2"
        extra["ポジション"] = "FW"
        issues = validate_payload(payload)
        self.assertTrue(any(issue.path == "フォーメーション" and "7〜11人" in issue.message for issue in issues))

    def test_goalkeeper_is_required_but_forward_is_not(self):
        payload = self.formation(7, 0)
        issues = validate_payload(payload)
        self.assertTrue(any(issue.path == "フォーメーション" and "GKは1人以上" in issue.message for issue in issues))
        self.assertFalse(any("FWが" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
