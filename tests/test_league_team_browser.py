import unittest

from league_rendering import build_team_folder_rows
from team_data import discover_team_choices


class LeagueTeamBrowserTests(unittest.TestCase):
    def test_rows_group_every_team_by_source_folder_without_omissions(self):
        teams = discover_team_choices()
        rows = build_team_folder_rows(teams)
        headers = [row["folder"] for row in rows if row["kind"] == "folder"]
        displayed_ids = [
            team["id"]
            for row in rows if row["kind"] == "teams"
            for team in row["teams"]
        ]
        self.assertIn("kadoka_original_A", headers)
        self.assertIn("kadoka_original_B", headers)
        self.assertIn("カルチョビット", headers)
        self.assertEqual(len(displayed_ids), len(teams))
        self.assertEqual(set(displayed_ids), {team["id"] for team in teams})

    def test_each_display_row_contains_at_most_two_teams(self):
        rows = build_team_folder_rows(discover_team_choices())
        self.assertTrue(all(len(row["teams"]) <= 2 for row in rows if row["kind"] == "teams"))


if __name__ == "__main__":
    unittest.main()
