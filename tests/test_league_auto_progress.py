import random
import unittest
from types import SimpleNamespace

from scripts.app.game_app import Game
from scripts.league.league_auto_progress import (
    LeagueAutoProgressConfig,
    WATCH_FOCUS,
    WATCH_NONE,
    WATCH_RANDOM,
    choose_auto_watch_fixture,
)


FIXTURES = [
    {"id": "m1", "day": 14, "home_id": "a", "away_id": "b", "played": False},
    {"id": "m2", "day": 14, "home_id": "c", "away_id": "d", "played": False},
]


class FakeLeagueManager:
    def __init__(self) -> None:
        self.selected_leagues = {"Aリーグ"}
        self.selected_tournaments = set()
        self.fixtures = [dict(fixture) for fixture in FIXTURES]
        self.team_choices = [
            {"id": team_id, "name": f"チーム{team_id.upper()}"}
            for team_id in ("a", "b", "c", "d")
        ]
        self.day = 1
        self.year = 1
        self.watch_fixture_id = ""
        self.last_results = []

    def _fixture_selected(self, fixture: dict) -> bool:
        return True

    def fixtures_on_day(self, day: int, *, unplayed_only: bool = False) -> list[dict]:
        return [
            fixture for fixture in self.fixtures
            if fixture["day"] == day and (not unplayed_only or not fixture["played"])
        ]

    def next_matchday(self) -> int | None:
        days = [fixture["day"] for fixture in self.fixtures if not fixture["played"] and fixture["day"] > self.day]
        return min(days) if days else None

    def advance_to_next_matchday(self) -> dict | None:
        self.day = self.next_matchday()
        return next(
            (fixture for fixture in self.fixtures if fixture["id"] == self.watch_fixture_id),
            None,
        )

    def save(self) -> None:
        return None


class LeagueAutoProgressTests(unittest.TestCase):
    def test_defaults_are_normal_speed_and_random_watch(self) -> None:
        config = LeagueAutoProgressConfig()
        self.assertEqual(config.speed_multiplier, 1)
        self.assertEqual(config.watch_mode, WATCH_RANDOM)
        self.assertIn(choose_auto_watch_fixture(FIXTURES, config, random.Random(1)), FIXTURES)

    def test_no_watch_is_headless_and_focus_only_selects_that_team(self) -> None:
        none_config = LeagueAutoProgressConfig(watch_mode=WATCH_NONE)
        self.assertIsNone(choose_auto_watch_fixture(FIXTURES, none_config, random.Random(1)))

        focus_config = LeagueAutoProgressConfig(watch_mode=WATCH_FOCUS, focus_team_id="c")
        self.assertEqual(choose_auto_watch_fixture(FIXTURES, focus_config, random.Random(1))["id"], "m2")
        focus_config.focus_team_id = "missing"
        self.assertIsNone(choose_auto_watch_fixture(FIXTURES, focus_config, random.Random(1)))

    def _game(self, config: LeagueAutoProgressConfig) -> Game:
        game = Game.__new__(Game)
        game.league_manager = FakeLeagueManager()
        game.league_auto_config = config
        game.league_auto_config_open = True
        game.league_auto_running = False
        game.league_auto_rng = random.Random(4)
        game.league_auto_result_delay = 0.0
        game.league_auto_matchdays = 0
        game.league_simulation_session = None
        game.active_league_fixture_id = ""
        game.league_save_message = ""
        game.match = SimpleNamespace(speed_multiplier=1)
        game.started_fixture = None
        game.headless_fixtures = []

        def start_fixture(fixture: dict) -> None:
            game.started_fixture = fixture
            game.active_league_fixture_id = fixture["id"]

        game.start_league_fixture = start_fixture
        game.start_league_simulations = lambda fixtures: setattr(game, "headless_fixtures", list(fixtures))
        return game

    def test_watch_none_starts_every_due_match_headlessly(self) -> None:
        game = self._game(LeagueAutoProgressConfig(watch_mode=WATCH_NONE))
        game.start_league_auto_progress()

        self.assertTrue(game.league_auto_running)
        self.assertIsNone(game.started_fixture)
        self.assertEqual([fixture["id"] for fixture in game.headless_fixtures], ["m1", "m2"])
        self.assertEqual(game.league_manager.day, 14)

    def test_focus_watch_applies_selected_visible_speed(self) -> None:
        config = LeagueAutoProgressConfig(watch_mode=WATCH_FOCUS, focus_team_id="c", speed_multiplier=10)
        game = self._game(config)
        game.start_league_auto_progress()

        self.assertEqual(game.started_fixture["id"], "m2")
        self.assertEqual(game.match.speed_multiplier, 10)
        self.assertEqual(game.headless_fixtures, [])


if __name__ == "__main__":
    unittest.main()
