import json
import random
import unittest
from pathlib import Path

from scripts.team.team_data import (
    team_choice_from_payload,
    team_choice_from_snapshot,
    team_snapshot_from_choice,
)
from scripts.team.team_editor_data import create_team_template, validate_payload
from scripts.tools.migrate_team_metadata import ABBREVIATIONS, TARGET_FOLDERS


ROOT = Path(__file__).resolve().parents[1]


class TeamMetadataTests(unittest.TestCase):
    def test_new_team_template_has_long_description_field(self):
        payload = create_team_template("initial", rng=random.Random(12))

        self.assertIn("チーム紹介", payload["チーム情報"])
        payload["チーム情報"]["チーム紹介"] = "地域とともに歩むクラブです。\n長い歴史があります。"
        choice = team_choice_from_payload(payload)

        self.assertEqual(choice["description"], "地域とともに歩むクラブです。\n長い歴史があります。")

    def test_old_team_without_description_remains_valid(self):
        payload = create_team_template("initial", rng=random.Random(13))
        payload["チーム情報"].pop("チーム紹介")

        self.assertFalse(validate_payload(payload))
        self.assertEqual(team_choice_from_payload(payload)["description"], "")

    def test_league_snapshot_round_trips_description_and_manager_stats(self):
        payload = create_team_template("initial", rng=random.Random(14))
        payload["チーム情報"]["チーム紹介"] = "このセーブだけで育っていくクラブです。"
        payload["チーム情報"]["インテリジェンス"] = 4321
        choice = team_choice_from_payload(payload, "teams/example.json")
        choice["id"] = "json:example.json"

        restored = team_choice_from_snapshot(team_snapshot_from_choice(choice))

        self.assertIsNotNone(restored)
        self.assertEqual(restored["id"], choice["id"])
        self.assertEqual(restored["description"], choice["description"])
        self.assertAlmostEqual(restored["manager_intelligence"], choice["manager_intelligence"], places=3)
        self.assertEqual(restored["starters"][0]["raw"]["ShotPower"], choice["starters"][0]["raw"]["ShotPower"])

    def test_original_teams_have_regional_abbreviations_and_introductions(self):
        found = set()
        for folder_name in TARGET_FOLDERS:
            for path in (ROOT / "teams" / folder_name).glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                info = payload["チーム情報"]
                name = str(info["チーム名"])
                found.add(name)
                self.assertEqual(info["チームの略称"], ABBREVIATIONS[name], path)
                self.assertTrue(str(info.get("チーム紹介", "")).strip(), path)

        self.assertEqual(found, set(ABBREVIATIONS))
        self.assertEqual(ABBREVIATIONS["私立蜜柑山学園"], "蜜柑山")
        self.assertEqual(ABBREVIATIONS["名古屋シャチホコ"], "名古屋")
        self.assertEqual(ABBREVIATIONS["相模原スターズ"], "相模原")


if __name__ == "__main__":
    unittest.main()
