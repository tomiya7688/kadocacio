import tempfile
import unittest
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.league.league_manager import LeagueManager, recommended_worker_count
from scripts.team.team_data import discover_team_choices, team_choice_from_snapshot


class LeagueScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_patch = patch(
            "scripts.league.league_manager.LEAGUE_STATE_PATH",
            Path(self.temp_dir.name) / "league_state.json",
        )
        self.state_patch.start()
        self.save_dir_patch = patch(
            "scripts.league.league_manager.LEAGUE_SAVE_DIR",
            Path(self.temp_dir.name) / "league_save",
        )
        self.save_dir_patch.start()

    def tearDown(self):
        self.save_dir_patch.stop()
        self.state_patch.stop()
        self.temp_dir.cleanup()

    def test_worker_count_uses_physical_core_estimate_and_hard_cap(self):
        abundant_memory = 64 * 1024**3
        with patch("scripts.league.league_worker_budget.os.cpu_count", return_value=8), patch(
            "scripts.league.league_manager.available_memory_bytes", return_value=abundant_memory,
        ):
            self.assertEqual(recommended_worker_count(20), 3)
            self.assertEqual(recommended_worker_count(20, reserve_for_ui=False), 4)
            self.assertEqual(recommended_worker_count(20, cpu_limit_percent=50), 2)
            self.assertEqual(recommended_worker_count(20, cpu_limit_percent=25), 1)
        with patch("scripts.league.league_worker_budget.os.cpu_count", return_value=64), patch(
            "scripts.league.league_manager.available_memory_bytes", return_value=abundant_memory,
        ):
            self.assertEqual(recommended_worker_count(100), 8)
            self.assertEqual(recommended_worker_count(100, cpu_limit_percent=25), 2)

    def test_worker_count_still_respects_task_and_memory_limits(self):
        two_worker_memory = 1536 * 1024**2 + 2 * 320 * 1024**2
        with patch("scripts.league.league_worker_budget.os.cpu_count", return_value=16), patch(
            "scripts.league.league_manager.available_memory_bytes", return_value=two_worker_memory,
        ):
            self.assertEqual(recommended_worker_count(20), 2)
            self.assertEqual(recommended_worker_count(1), 1)

    def test_double_round_robin_has_one_home_and_one_away_game(self):
        choices = discover_team_choices()
        manager = LeagueManager(choices)
        a_teams = manager.teams_in_league("Aリーグ")
        fixtures = [fixture for fixture in manager.fixtures if fixture["league"] == "Aリーグ"]

        self.assertEqual(len(fixtures), len(a_teams) * (len(a_teams) - 1))
        directed_pairs = Counter((fixture["home_id"], fixture["away_id"]) for fixture in fixtures)
        for first in a_teams:
            for second in a_teams:
                if first is second:
                    continue
                self.assertEqual(directed_pairs[(first["id"], second["id"])], 1)
        for round_number in {fixture["round"] for fixture in fixtures}:
            self.assertEqual(len({fixture["day"] for fixture in fixtures if fixture["round"] == round_number}), 1)
        match_days = sorted({fixture["day"] for fixture in fixtures})
        self.assertEqual(match_days[0], 14)
        self.assertEqual(match_days[-1], 330)
        self.assertGreater(min(second - first for first, second in zip(match_days, match_days[1:])), 0)

    def test_skip_moves_to_next_match_without_using_random_result(self):
        manager = LeagueManager(discover_team_choices())
        self.assertEqual(manager.next_matchday(), 14)
        watched = manager.advance_to_next_matchday()
        self.assertIsNone(watched)
        self.assertEqual(manager.day, 14)
        self.assertTrue(manager.fixtures_on_day(14, unplayed_only=True))

    def test_new_league_is_saved_to_json_definition(self):
        definitions_path = Path(self.temp_dir.name) / "leagues.json"
        with patch("scripts.league.league_manager.LEAGUES_PATH", definitions_path):
            manager = LeagueManager(discover_team_choices())
            added = manager.add_league("Fリーグ")
        self.assertEqual(added, "Fリーグ")
        self.assertIn("Fリーグ", definitions_path.read_text(encoding="utf-8"))

    def test_points_and_goal_difference_sort_standings(self):
        manager = LeagueManager(discover_team_choices())
        fixtures = [fixture for fixture in manager.fixtures if fixture["league"] == "Aリーグ"]
        manager.record_result(fixtures[0], 3, 0, watched=False)
        manager.record_result(fixtures[1], 1, 1, watched=False)
        table = manager.standings("Aリーグ")

        self.assertEqual(table[0]["points"], 3)
        self.assertEqual(table[0]["gd"], 3)
        self.assertEqual(sum(row["points"] for row in table), 5)

    def test_watched_match_finishes_all_selected_leagues_on_same_day(self):
        choices = [deepcopy(choice) for choice in discover_team_choices()[:4]]
        for index, choice in enumerate(choices):
            choice["league"] = "Aリーグ" if index < 2 else "Bリーグ"
        manager = LeagueManager(choices)
        manager.selected_leagues = {"Aリーグ", "Bリーグ"}
        first_day = min(fixture["day"] for fixture in manager.fixtures)
        manager.day = first_day - 1
        due = manager.fixtures_on_day(first_day, unplayed_only=True)
        self.assertEqual({fixture["league"] for fixture in due}, {"Aリーグ", "Bリーグ"})

        watched = due[0]
        manager.toggle_watch(watched["id"])
        returned = manager.advance_day()
        self.assertEqual(returned["id"], watched["id"])
        self.assertFalse(any(fixture["played"] for fixture in due))

        remaining = manager.complete_watched_fixture(watched["id"], 2, 1)
        manager.apply_headless_results([
            {"fixture_id": fixture["id"], "home_score": 1, "away_score": 0, "engine_steps": 10800}
            for fixture in remaining
        ])
        self.assertTrue(all(fixture["played"] for fixture in due))
        self.assertEqual(len(manager.last_results), 2)
        self.assertEqual({result["league"] for result in manager.last_results}, {"Aリーグ", "Bリーグ"})

    def test_incomplete_headless_result_does_not_enter_standings(self):
        manager = LeagueManager(discover_team_choices())
        fixture = next(fixture for fixture in manager.fixtures if not fixture.get("played"))

        manager.apply_headless_results([{
            "fixture_id": fixture["id"],
            "home_score": 9,
            "away_score": 9,
            "fulltime": False,
            "finish_reason": "step_limit",
        }])

        self.assertFalse(fixture["played"])
        self.assertEqual(manager.last_results, [])

    def test_multiple_json_saves_can_be_created_loaded_and_deleted(self):
        manager = LeagueManager(discover_team_choices())
        first = manager.create_new_save("テストリーグ")
        manager.day = 77
        manager.save()
        second = manager.create_new_save("テストリーグ")
        self.assertNotEqual(first, second)
        self.assertEqual(len(manager.list_saves()), 3)  # 自動セーブ + 2つの名前付きセーブ

        errors = manager.load_save(first.name)
        self.assertEqual(errors, [])
        self.assertEqual(manager.day, 77)
        self.assertEqual(manager.delete_save(second.name), "")
        self.assertFalse(second.exists())

    def test_new_save_keeps_participant_abilities_independent_from_teams_files(self):
        source = discover_team_choices()
        manager = LeagueManager(source)
        save_path = manager.create_new_save("能力固定リーグ")
        fixture = manager.fixtures[0]
        team_id = str(fixture["home_id"])
        original_power = manager.choices_by_id[team_id]["starters"][0]["raw"]["ShotPower"]

        edited_source = deepcopy(source)
        edited_team = next(choice for choice in edited_source if str(choice["id"]) == team_id)
        edited_team["starters"][0]["raw"]["ShotPower"] = 0 if original_power else 5500
        manager.refresh_teams(edited_source)

        self.assertEqual(
            manager.choices_by_id[team_id]["starters"][0]["raw"]["ShotPower"],
            original_power,
        )
        saved = json.loads(save_path.read_text(encoding="utf-8"))
        self.assertIn(team_id, saved["チームスナップショット"])

        # Future player-mode growth/editing can change this save's runtime team
        # without changing the initial value stored under teams/.
        save_local_power = (int(original_power) + 777) % 5501
        manager.choices_by_id[team_id]["starters"][0]["raw"]["ShotPower"] = save_local_power
        manager.save()
        saved = json.loads(save_path.read_text(encoding="utf-8"))
        saved_choice = team_choice_from_snapshot(saved["チームスナップショット"][team_id])
        self.assertEqual(saved_choice["starters"][0]["raw"]["ShotPower"], save_local_power)

        reloaded = LeagueManager(edited_source, load_state=False)
        self.assertEqual(reloaded.load_save(save_path.name), [])
        self.assertEqual(
            reloaded.choices_by_id[team_id]["starters"][0]["raw"]["ShotPower"],
            save_local_power,
        )

    def test_snapshot_save_loads_even_if_participant_source_file_is_missing(self):
        source = discover_team_choices()
        manager = LeagueManager(source)
        save_path = manager.create_new_save("削除耐性リーグ")
        team_id = str(manager.fixtures[0]["home_id"])

        without_team = [choice for choice in source if str(choice["id"]) != team_id]
        reloaded = LeagueManager(without_team, load_state=False)

        self.assertEqual(reloaded.load_save(save_path.name), [])
        self.assertIn(team_id, reloaded.choices_by_id)

    def test_broken_and_missing_team_saves_report_errors(self):
        manager = LeagueManager(discover_team_choices())
        save_dir = Path(self.temp_dir.name) / "league_save"
        (save_dir / "broken.json").write_text("{broken", encoding="utf-8")
        payload = manager._state_payload()
        payload["save_name"] = "missing"
        payload["fixtures"][0]["home_id"] = "deleted-team-id"
        (save_dir / "missing.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        saves = {entry["name"]: entry for entry in manager.list_saves()}
        self.assertFalse(saves["broken"]["loadable"])
        self.assertTrue(any("JSON" in error for error in saves["broken"]["errors"]))
        self.assertFalse(saves["missing"]["loadable"])
        self.assertTrue(any("チームが見つかりません" in error for error in saves["missing"]["errors"]))

    def test_completed_year_keeps_full_historical_standings_and_results(self):
        manager = LeagueManager(discover_team_choices())
        league = "Aリーグ"
        fixture = next(item for item in manager.fixtures if item["league"] == league)
        manager.record_result(fixture, 2, 1, watched=False)
        old_table = manager.standings(league)
        manager._start_next_year()

        self.assertEqual(manager.standings_for_year(league, 1), old_table)
        results = manager.results_for_year(league, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual((results[0]["home_score"], results[0]["away_score"]), (2, 1))

    def test_save_keeps_more_than_fifty_completed_years(self):
        choices = discover_team_choices()
        manager = LeagueManager(choices)
        save_path = manager.create_new_save("長期履歴リーグ")
        manager.history = [
            {"year": year, "leagues": {}, "results": []}
            for year in range(1, 76)
        ]
        manager.year = 76
        manager.save()

        reloaded = LeagueManager(choices, load_state=False)
        self.assertEqual(reloaded.load_save(save_path.name), [])

        self.assertEqual(len(reloaded.history), 75)
        self.assertEqual(reloaded.history[0]["year"], 1)
        self.assertEqual(reloaded.history[-1]["year"], 75)

    def test_team_history_has_yearly_rank_and_team_scoped_results(self):
        manager = LeagueManager(discover_team_choices())
        league = "Aリーグ"
        fixture = next(item for item in manager.fixtures if item["league"] == league)
        home_id = str(fixture["home_id"])
        away_id = str(fixture["away_id"])
        manager.record_result(fixture, 3, 1, watched=False)
        manager._start_next_year()

        home_rank = manager.team_standings_for_year(home_id, 1)
        home_results = manager.team_results_for_year(home_id, 1)
        away_results = manager.team_results_for_year(away_id, 1)

        self.assertEqual(len(home_rank), 1)
        self.assertEqual(home_rank[0]["league"], league)
        self.assertGreaterEqual(home_rank[0]["rank"], 1)
        self.assertEqual(len(home_results), 1)
        self.assertEqual(home_results[0]["team_side"], "home")
        self.assertEqual(away_results[0]["team_side"], "away")
        self.assertEqual(home_results[0]["home_id"], home_id)
        self.assertEqual(home_results[0]["away_id"], away_id)
        self.assertEqual(home_results[0]["year"], 1)

    def test_version_two_history_results_remain_readable_by_team(self):
        manager = LeagueManager(discover_team_choices())
        league = "Aリーグ"
        fixture = next(item for item in manager.fixtures if item["league"] == league)
        team_id = str(fixture["home_id"])
        team_name = str(fixture["home_name"])
        standings = manager.standings(league)
        legacy_result = {
            "fixture_id": "legacy-1",
            "league": league,
            "round": 1,
            "day": 14,
            "home_name": team_name,
            "away_name": str(fixture["away_name"]),
            "home_score": 2,
            "away_score": 0,
        }
        manager.history = [{
            "year": 1,
            "leagues": {league: {"standings": standings, "results": [legacy_result]}},
            "promotion_playoffs": [],
        }]
        manager.year = 2

        results = manager.team_results_for_year(team_id, 1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["fixture_id"], "legacy-1")
        self.assertEqual(results[0]["team_side"], "home")

    def test_promotion_playoffs_are_created_on_second_saturday_of_december(self):
        source = discover_team_choices()
        choices = []
        for index in range(8):
            choice = deepcopy(source[index % len(source)])
            choice["id"] = f"promotion-team-{index}"
            choice["name"] = f"昇降格チーム{index}"
            choice["league"] = "Aリーグ" if index < 4 else "Bリーグ"
            choices.append(choice)
        manager = LeagueManager(choices)
        for fixture in manager.fixtures:
            if fixture["league"] in ("Aリーグ", "Bリーグ"):
                manager.record_result(fixture, 1, 0, watched=False)

        playoffs = manager.ensure_promotion_playoffs()
        self.assertEqual(len(playoffs), 2)
        self.assertTrue(all(item["fixture_type"] == "PLAYOFF" for item in playoffs))
        self.assertTrue(all(item["day"] == manager.promotion_playoff_day(1) for item in playoffs))
        self.assertEqual(manager.promotion_playoff_day(1), 342)

    def test_lower_team_is_promoted_only_when_it_wins_playoff(self):
        source = discover_team_choices()
        choices = []
        for index in range(8):
            choice = deepcopy(source[index % len(source)])
            choice["id"] = f"swap-team-{index}"
            choice["name"] = f"入替チーム{index}"
            choice["league"] = "Aリーグ" if index < 4 else "Bリーグ"
            choices.append(choice)
        manager = LeagueManager(choices)
        for fixture in manager.fixtures:
            if fixture["league"] in ("Aリーグ", "Bリーグ"):
                manager.record_result(fixture, 1, 0, watched=False)
        playoff = manager.ensure_promotion_playoffs()[0]
        upper_id, lower_id = playoff["home_id"], playoff["away_id"]

        manager.record_result(playoff, 0, 1, watched=False)
        manager._resolve_promotion_playoff(playoff)
        self.assertEqual(manager.league_memberships[lower_id], "Aリーグ")
        self.assertEqual(manager.league_memberships[upper_id], "Bリーグ")
        self.assertTrue(manager.promotion_events[-1]["promoted"])

    def test_league_definitions_own_team_membership(self):
        choices = discover_team_choices()
        self.assertTrue(all("league" not in choice for choice in choices))
        manager = LeagueManager(choices)
        expected = set(manager.league_definition("Aリーグ").get("所属チーム", []))
        actual = {team["id"] for team in manager.teams_in_league("Aリーグ")}
        self.assertEqual(actual, expected)

    def test_editor_can_assign_teams_and_rebuild_schedule(self):
        manager = LeagueManager(discover_team_choices())
        definitions_path = Path(self.temp_dir.name) / "leagues-editor.json"
        existing_b = {team["id"] for team in manager.teams_in_league("Bリーグ")}
        candidates = [team for team in manager.team_choices if team["id"] not in existing_b][:2]
        self.assertEqual(len(candidates), 2)
        with patch("scripts.league.league_manager.LEAGUES_PATH", definitions_path):
            self.assertEqual(manager.assign_team_to_league(candidates[0]["id"], "Bリーグ"), "")
            self.assertEqual(manager.assign_team_to_league(candidates[1]["id"], "Bリーグ"), "")
        expected_ids = existing_b | {candidates[0]["id"], candidates[1]["id"]}
        self.assertEqual({team["id"] for team in manager.teams_in_league("Bリーグ")}, expected_ids)
        expected_fixture_count = len(expected_ids) * (len(expected_ids) - 1)
        self.assertEqual(
            len([item for item in manager.fixtures if item["league"] == "Bリーグ"]),
            expected_fixture_count,
        )
        saved = json.loads(definitions_path.read_text(encoding="utf-8"))
        b_league = next(item for item in saved["リーグ一覧"] if item["リーグ名"] == "Bリーグ")
        self.assertEqual(set(b_league["所属チーム"]), expected_ids)

    def test_generated_fixture_day_can_be_edited_before_playing(self):
        manager = LeagueManager(discover_team_choices())
        fixture = next(item for item in manager.fixtures if item["league"] == "Aリーグ")
        original = fixture["day"]
        self.assertEqual(manager.set_fixture_day(fixture["id"], original + 7), "")
        self.assertEqual(fixture["day"], original + 7)
        manager.record_result(fixture, 1, 0, watched=False)
        self.assertIn("終了済み", manager.set_fixture_day(fixture["id"], original + 8))

    def test_editor_can_add_rename_and_delete_a_league(self):
        manager = LeagueManager(discover_team_choices())
        definitions_path = Path(self.temp_dir.name) / "league-structure.json"
        with patch("scripts.league.league_manager.LEAGUES_PATH", definitions_path):
            added = manager.add_league("新リーグ")
            self.assertEqual(added, "新リーグ")
            self.assertEqual(manager.rename_league("新リーグ", "改名リーグ"), "")
            self.assertIn("改名リーグ", manager.league_names)
            self.assertEqual(manager.delete_league("改名リーグ"), "")
        self.assertNotIn("改名リーグ", manager.league_names)


if __name__ == "__main__":
    unittest.main()
