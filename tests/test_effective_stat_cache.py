import unittest

from scripts.match.match_engine import Match
from scripts.match.player_commands import PlayerCommand
from scripts.team.team_data import discover_team_choices


class EffectiveStatCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        choices = discover_team_choices()
        cls.match = Match(choices[0], choices[1], "NEUTRAL")

    def setUp(self):
        self.player = self.match.home.players[0]
        self.player.reset_match_state()
        self.player.venue_role = "NEUTRAL"
        self.player.steel_heart_timer = 0.0

    def test_direct_stamina_change_invalidates_effective_stat(self):
        fresh = self.player.effective_stat(self.player.dash_speed)
        self.player.stamina = 0.0
        exhausted = self.player.effective_stat(self.player.dash_speed)
        self.assertLess(exhausted, fresh)

    def test_spending_stamina_updates_cached_factor(self):
        before = self.player.effective_stat(self.player.dash_speed)
        self.player.stamina = 0.05
        self.player.spend_stamina(PlayerCommand.DASH, scale=2.0)
        after = self.player.effective_stat(self.player.dash_speed)
        self.assertLessEqual(after, before)

    def test_venue_and_steel_heart_update_intelligence_without_stamina(self):
        self.player.mental = 0.05
        self.player.venue_role = "AWAY"
        away = self.player.effective_intelligence
        self.player.steel_heart_timer = 1.0
        protected = self.player.effective_intelligence
        self.assertLess(away, protected)
        self.assertAlmostEqual(protected, self.player.intelligence, places=7)


if __name__ == "__main__":
    unittest.main()
