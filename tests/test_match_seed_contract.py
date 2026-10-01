"""A match seed must cover initialization as well as fixed-step play."""

import hashlib
import random
import unittest
from types import SimpleNamespace

from scripts.app.game_app import Game
from scripts.core.match_seed import league_fixture_seed
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.league.league_simulation_workers import _match_output, _run_headless_league_match
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices


class MatchSeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home_choice, cls.away_choice = discover_team_choices()[:2]

    def new_match(self, seed: int) -> Match:
        return Match(self.home_choice, self.away_choice, "HOME", seed=seed)

    def test_seeded_matches_reproduce_initial_state_and_fixed_steps(self):
        global_state = random.getstate()
        first = self.new_match(7103)
        second = self.new_match(7103)
        self.assertEqual(random.getstate(), global_state)
        self.assertEqual(first.seed, 7103)
        self.assertEqual(first.rng.getstate(), second.rng.getstate())
        self.assertEqual(
            [(player.skill, player.roam_timer) for team in first.teams for player in team.players],
            [(player.skill, player.roam_timer) for team in second.teams for player in team.players],
        )

        first.start_new()
        second.start_new()
        for _ in range(80):
            advance_match_fixed(first)
            advance_match_fixed(second)

        self.assertEqual(first.rng.getstate(), second.rng.getstate())
        self.assertEqual((first.game_time, first.home.score, first.away.score),
                         (second.game_time, second.home.score, second.away.score))
        self.assertEqual(tuple(first.events), tuple(second.events))
        self.assertEqual((first.ball.pos.x, first.ball.pos.y, first.ball.z),
                         (second.ball.pos.x, second.ball.pos.y, second.ball.z))
        self.assertEqual(
            [(player.pos.x, player.pos.y, player.stamina) for team in first.teams for player in team.players],
            [(player.pos.x, player.pos.y, player.stamina) for team in second.teams for player in team.players],
        )

    def test_distinct_seeds_change_pre_kickoff_player_state(self):
        first = self.new_match(1)
        second = self.new_match(2)
        self.assertNotEqual(first.home.players[0].skill, second.home.players[0].skill)

    def test_league_fixture_seed_keeps_existing_background_formula(self):
        expected = int.from_bytes(hashlib.sha256(b"round-1:Home:Away").digest()[:8], "big")
        self.assertEqual(league_fixture_seed("round-1", "Home", "Away"), expected)
        self.assertEqual(league_fixture_seed("round-1", "Home", "Away"), expected)
        self.assertNotEqual(league_fixture_seed("round-2", "Home", "Away"), expected)

    def test_watched_league_fixture_uses_shared_seed(self):
        fixture = {
            "id": "round-1",
            "home_id": self.home_choice["id"],
            "away_id": self.away_choice["id"],
        }
        game = Game.__new__(Game)
        game.league_manager = SimpleNamespace(
            day=1,
            choices_by_id={fixture["home_id"]: self.home_choice, fixture["away_id"]: self.away_choice},
            fixtures_on_day=lambda _day, *, unplayed_only: [fixture],
        )
        game.start_league_simulations = lambda _fixtures, *, live_updates: None
        game.visible_simulation = SimpleNamespace(reset=lambda _match: None)
        game.roll_stadium_guests = lambda: None
        game.reset_camera = lambda: None

        Game.start_league_fixture(game, fixture)

        self.assertEqual(
            game.match.seed,
            league_fixture_seed(fixture["id"], self.home_choice["name"], self.away_choice["name"]),
        )
        for _ in range(80):
            advance_match_fixed(game.match)
        headless = _run_headless_league_match({
            "fixture": fixture,
            "home_choice": self.home_choice,
            "away_choice": self.away_choice,
            "max_match_steps": 80,
        })
        self.assertEqual(headless["engine_steps"], 80)
        self.assertEqual(
            {key: headless[key] for key in _match_output(game.match)},
            _match_output(game.match),
        )


if __name__ == "__main__":
    unittest.main()
