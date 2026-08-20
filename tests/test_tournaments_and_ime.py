import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_app import Game
from league_manager import LeagueManager, MAX_LEAGUES
from team_data import discover_team_choices


class TournamentAndImeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.patches = [
            patch("league_manager.LEAGUES_PATH", root / "leagues.json"),
            patch("league_manager.LEAGUE_STATE_PATH", root / "league_state.json"),
            patch("league_manager.LEAGUE_SAVE_DIR", root / "league_save"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_league_limit_is_999(self):
        manager = LeagueManager(discover_team_choices())
        manager.definitions = [{"リーグ名": f"L{i}", "所属チーム": []} for i in range(MAX_LEAGUES)]
        with self.assertRaisesRegex(ValueError, "最大999個"):
            manager.add_league("too many")

    def test_tournament_avoids_regular_matchdays_and_advances_winners(self):
        manager = LeagueManager(discover_team_choices())
        for choice in manager.team_choices[:6]:
            manager.assign_team_to_league(str(choice["id"]), "Aリーグ")
        name = manager.add_tournament("KADOKA杯")
        regular_days = {fixture["day"] for fixture in manager.fixtures if fixture["fixture_type"] == "REGULAR"}
        first_round = [fixture for fixture in manager.fixtures if fixture.get("tournament") == name]
        self.assertTrue(first_round)
        self.assertTrue(all(fixture["day"] not in regular_days for fixture in first_round))

        for fixture in list(first_round):
            manager.record_result(fixture, 1, 0, watched=False)
        second_round = [fixture for fixture in manager.fixtures if fixture.get("tournament") == name and fixture["round"] == 2]
        self.assertTrue(second_round)
        self.assertTrue(all(fixture["day"] not in regular_days for fixture in second_round))

    def test_previous_rank_mode_limits_participants(self):
        manager = LeagueManager(discover_team_choices())
        for choice in manager.team_choices[:6]:
            manager.assign_team_to_league(str(choice["id"]), "Aリーグ")
        name = manager.add_tournament("上位杯")
        manager.configure_tournament(name, participation="前年順位", rank_limit=3)
        definition = manager.tournament_definition(name)
        self.assertEqual(len(manager._tournament_participants(definition)), 3)

    def test_team_can_enter_multiple_leagues_and_choose_priority(self):
        manager = LeagueManager(discover_team_choices())
        teams = manager.team_choices[:5]
        for choice in teams[:3]:
            manager.assign_team_to_league(str(choice["id"]), "Aリーグ")
        for choice in teams[2:]:
            manager.assign_team_to_league(str(choice["id"]), "Bリーグ")
        shared_id = str(teams[2]["id"])

        self.assertTrue(manager.team_in_league(shared_id, "Aリーグ"))
        self.assertTrue(manager.team_in_league(shared_id, "Bリーグ"))
        self.assertEqual(manager.set_priority_league(shared_id, "Bリーグ"), "")
        self.assertEqual(manager.league_memberships[shared_id], "Bリーグ")
        shared_days = [fixture["day"] for fixture in manager.fixtures if shared_id in (fixture["home_id"], fixture["away_id"])]
        self.assertEqual(len(shared_days), len(set(shared_days)))

    def test_tournament_accepts_multiple_source_leagues_and_moves_rounds_quickly(self):
        manager = LeagueManager(discover_team_choices())
        teams = manager.team_choices[:8]
        for choice in teams[:4]:
            manager.assign_team_to_league(str(choice["id"]), "Aリーグ")
        for choice in teams[4:]:
            manager.assign_team_to_league(str(choice["id"]), "Bリーグ")
        name = manager.add_tournament("連戦杯")
        self.assertEqual(manager.toggle_tournament_source(name, "Bリーグ"), "")
        definition = manager.tournament_definition(name)
        self.assertEqual(set(definition["対象リーグ一覧"]), {"Aリーグ", "Bリーグ"})
        self.assertEqual(len(manager._tournament_participants(definition)), 8)

        first_round = [fixture for fixture in manager.fixtures if fixture.get("tournament") == name and fixture["round"] == 1]
        first_day = first_round[0]["day"]
        for fixture in list(first_round):
            manager.record_result(fixture, 1, 0, watched=False)
        second_round = [fixture for fixture in manager.fixtures if fixture.get("tournament") == name and fixture["round"] == 2]
        self.assertTrue(second_round)
        self.assertGreater(second_round[0]["day"], first_day)
        self.assertLess(second_round[0]["day"], first_day + 7)

    def test_blank_competition_names_report_that_the_field_is_empty(self):
        manager = LeagueManager(discover_team_choices())
        with self.assertRaisesRegex(ValueError, "リーグ名が空です"):
            manager.add_league("")
        with self.assertRaisesRegex(ValueError, "トーナメント名が空です"):
            manager.add_tournament("")

    def test_definitions_json_keeps_leagues_and_tournaments(self):
        manager = LeagueManager(discover_team_choices())
        manager.add_tournament("保存杯")
        payload = json.loads(Path(self.temp_dir.name, "leagues.json").read_text(encoding="utf-8"))
        self.assertIn("リーグ一覧", payload)
        self.assertEqual(payload["トーナメント一覧"][0]["トーナメント名"], "保存杯")

    def test_textinput_commits_japanese_and_composition_is_separate(self):
        game = Game.__new__(Game)
        game.league_save_select_open = False
        game.league_save_input_active = False
        game.league_tab = "structure"
        game.league_editor_input_active = True
        game.league_editor_name = "新"
        game.ime_composition = "リーグ"

        game.handle_league_text_input("日本杯")

        self.assertEqual(game.league_editor_name, "新日本杯")
        self.assertEqual(game.ime_composition, "")


if __name__ == "__main__":
    unittest.main()
