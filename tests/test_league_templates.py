import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.league.league_manager import LeagueManager


class LeagueTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.default_path = self.root / "leagues.json"
        self.template_dir = self.root / "league_templates"
        self.save_dir = self.root / "league_save"
        self.default_path.write_text(
            json.dumps({
                "リーグ一覧": [{
                    "リーグ名": "標準リーグ",
                    "表示色": "#4C83D1",
                    "開幕日": 14,
                    "最終節日": 330,
                    "上位リーグ": "",
                    "所属チーム": [],
                }],
                "トーナメント一覧": [],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        self.patches = [
            patch("scripts.league.league_manager.LEAGUES_PATH", self.default_path),
            patch("scripts.league.league_manager.LEAGUE_TEMPLATE_DIR", self.template_dir),
            patch("scripts.league.league_manager.LEAGUE_SAVE_DIR", self.save_dir),
            patch("scripts.league.league_manager.LEAGUE_STATE_PATH", self.root / "league_state.json"),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary.cleanup()

    def test_templates_can_be_duplicated_renamed_selected_and_deleted(self) -> None:
        standard = LeagueManager([], load_state=False)
        template_id = standard.duplicate_template("別構成")

        entries = LeagueManager.template_entries()
        self.assertEqual([entry["name"] for entry in entries], ["標準テンプレート", "別構成"])
        copied = LeagueManager([], template_id=template_id, load_state=False)
        self.assertEqual(copied.league_names, ["標準リーグ"])

        copied.rename_template("カップ併設構成")
        self.assertEqual(LeagueManager.template_entries()[1]["name"], "カップ併設構成")
        copied.delete_template()
        self.assertEqual([entry["id"] for entry in LeagueManager.template_entries()], ["default"])

    def test_league_save_keeps_its_starting_template_snapshot(self) -> None:
        standard = LeagueManager([], load_state=False)
        template_id = standard.duplicate_template("保存用構成")
        selected = LeagueManager([], template_id=template_id, load_state=False)
        selected.add_league("追加リーグ")
        save_path = selected.create_new_save("テンプレート保持")

        selected.definitions = selected.definitions[:1]
        selected._save_definitions()

        loaded = LeagueManager([], load_state=False)
        self.assertEqual(loaded.load_save(save_path.name), [])
        self.assertEqual(loaded.template_id, template_id)
        self.assertEqual(loaded.template_name, "保存用構成")
        self.assertIn("追加リーグ", loaded.league_names)


if __name__ == "__main__":
    unittest.main()
