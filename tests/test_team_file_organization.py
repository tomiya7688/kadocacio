import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from team_editor_data import create_team_template, save_editor_payload, scan_team_files, team_id_for_path
from team_data import discover_team_choices


class TeamFileOrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.teams = self.root / "teams"
        self.patches = [
            patch("team_editor_data.TEAMS_DIR", self.teams),
            patch("team_data.TEAMS_DIR", self.teams),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_save_creates_real_subfolders_and_recursive_discovery_finds_team(self):
        payload = create_team_template("initial")
        payload["チーム情報"]["チーム名"] = "東京サンプル"

        path = save_editor_payload(payload, folder_name="関東/一部")

        self.assertEqual(path.relative_to(self.teams).as_posix(), "関東/一部/東京サンプル.json")
        self.assertTrue(path.exists())
        self.assertEqual(scan_team_files()[0][0], path)
        choices = discover_team_choices()
        self.assertEqual(choices[0]["id"], "json:関東/一部/東京サンプル.json")

    def test_team_name_renames_file_and_updates_all_json_references(self):
        payload = create_team_template("initial")
        payload["チーム情報"]["チーム名"] = "旧チーム"
        old_path = save_editor_payload(payload)
        old_id = team_id_for_path(old_path)
        league_payload = {"リーグ一覧": [{"リーグ名": "A", "所属チーム": [old_id]}]}
        (self.root / "leagues.json").write_text(json.dumps(league_payload, ensure_ascii=False), encoding="utf-8")
        save_dir = self.root / "league_save"
        save_dir.mkdir()
        (save_dir / "season.json").write_text(json.dumps({"league_memberships": {old_id: "A"}}, ensure_ascii=False), encoding="utf-8")

        payload["チーム情報"]["チーム名"] = "新チーム"
        new_path = save_editor_payload(payload, old_path, "九州")
        new_id = team_id_for_path(new_path)

        self.assertFalse(old_path.exists())
        self.assertEqual(new_path.relative_to(self.teams).as_posix(), "九州/新チーム.json")
        self.assertIn(new_id, (self.root / "leagues.json").read_text(encoding="utf-8"))
        save_text = (save_dir / "season.json").read_text(encoding="utf-8")
        self.assertIn(new_id, save_text)
        self.assertNotIn(old_id, save_text)

    def test_duplicate_target_name_gets_a_non_destructive_suffix(self):
        first = create_team_template("initial")
        first["チーム情報"]["チーム名"] = "同名"
        second = create_team_template("initial")
        second["チーム情報"]["チーム名"] = "同名"

        first_path = save_editor_payload(first, folder_name="保管")
        second_path = save_editor_payload(second, folder_name="保管")

        self.assertEqual(first_path.name, "同名.json")
        self.assertEqual(second_path.name, "同名 (2).json")
        self.assertTrue(first_path.exists())
        self.assertTrue(second_path.exists())

    def test_parent_directory_escape_is_rejected(self):
        payload = create_team_template("initial")
        with self.assertRaisesRegex(ValueError, "使用できません"):
            save_editor_payload(payload, folder_name="../outside")


if __name__ == "__main__":
    unittest.main()
