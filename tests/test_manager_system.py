import copy
import unittest

import pygame

from scripts.match.manager_system import manager_stat
from scripts.match.match_engine import Match
from scripts.core.settings import FIELD
from scripts.core.stat_scale import legacy_player_stat
from scripts.team.team_data import discover_team_choices


class ManagerSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.choices = discover_team_choices()

    def choice(self, text):
        return next(choice for choice in self.choices if text in choice["name"])

    def test_named_team_manager_parameters_are_loaded(self):
        choice = self.choice("夕張kadoka")
        default_activity = round(legacy_player_stat(500))
        default_intelligence = round(legacy_player_stat(700))
        self.assertAlmostEqual(choice["manager_tactic_aggression"], manager_stat(round(legacy_player_stat(50)), default_activity))
        self.assertAlmostEqual(choice["manager_substitution_aggression"], manager_stat(round(legacy_player_stat(500)), default_activity))
        self.assertAlmostEqual(choice["manager_intelligence"], manager_stat(round(legacy_player_stat(1100)), default_intelligence))

    def test_tactic_decision_waits_for_next_set_piece(self):
        match = Match(self.choice("夕張kadoka"), self.choices[1], "NEUTRAL")
        match.start_new()
        team, opponent = match.home, match.away
        team.tactic = "ULTRA_DEFEND"
        team.manager_tactic_aggression = 1.0
        team.manager_intelligence = 1.0
        team.manager_last_change = -9999.0
        team.score, opponent.score = 0, 3
        team.shots, opponent.shots = 1, 8
        match.game_time = 4800.0
        match.ball.pos.x = FIELD.left + 100
        match.review_manager_team(team)
        self.assertIn(team.pending_tactic, ("ATTACK", "ULTRA_ATTACK"))
        self.assertEqual(team.tactic, "ULTRA_DEFEND")
        expected = team.pending_tactic
        match.start_set_piece("FREE_KICK", team, pygame.Vector2(FIELD.center))
        self.assertEqual(team.tactic, expected)
        self.assertIsNone(team.pending_tactic)

    def test_substitution_is_applied_at_throw_in(self):
        bench_choice = self.choice("トップロード成田")
        opponent_choice = next(choice for choice in self.choices if choice is not bench_choice)
        match = Match(bench_choice, opponent_choice, "NEUTRAL")
        match.start_new()
        team = match.home
        outgoing = next(player for player in team.players if not player.is_keeper)
        outgoing.stamina = 0.0
        team.manager = team.manager or "TEST監督"
        team.manager_substitution_aggression = 1.0
        team.manager_intelligence = 1.0
        match.game_time = 3600.0
        match.review_manager_team(team)
        self.assertIsNotNone(team.pending_substitution)
        reserve_name = team.pending_substitution[1]["name"]
        old_names = {player.name for player in team.players}
        match.ball.last_touch = match.away.players[0]
        match.ball.pos.update(FIELD.centerx, FIELD.top - 4)
        match.start_throw_in()
        self.assertEqual(team.substitutions_used, 1)
        self.assertIn(reserve_name, {player.name for player in team.players})
        self.assertNotEqual(old_names, {player.name for player in team.players})

    def test_fourth_substitution_is_rejected_and_new_match_restores_roster(self):
        bench_choice = self.choice("トップロード成田")
        opponent_choice = next(choice for choice in self.choices if choice is not bench_choice)
        match = Match(bench_choice, opponent_choice, "NEUTRAL")
        match.start_new()
        team = match.home
        original_names = [player.name for player in team.players]
        source = copy.deepcopy(team.bench[0])
        for index in range(3):
            reserve = copy.deepcopy(source)
            reserve["name"] = f"交代要員{index}"
            reserve["number"] = 90 + index
            reserve["raw"]["Name"] = reserve["name"]
            reserve["raw"]["JerseyNumber"] = reserve["number"]
            team.bench.append(reserve)
        for index in range(3):
            self.assertTrue(match.execute_substitution(team, team.players[index], team.bench[0]))
        self.assertEqual(team.substitutions_used, 3)
        self.assertFalse(match.execute_substitution(team, team.players[3], team.bench[0]))
        match.start_new()
        self.assertEqual([player.name for player in team.players], original_names)
        self.assertEqual(team.substitutions_used, 0)


if __name__ == "__main__":
    unittest.main()
