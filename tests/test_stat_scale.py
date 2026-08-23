import json
from copy import deepcopy
import unittest
from pathlib import Path

from scripts.core.stat_scale import (
    PLAYER_GRADE_THRESHOLDS,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    current_scale_metadata,
    legacy_player_stat,
    normalize_player_stat,
)
from scripts.team.team_editor_data import STAT_FIELDS
from scripts.team.team_data import team_choice_from_payload
from scripts.team.team_rating import rank_for_average


ROOT = Path(__file__).resolve().parents[1]


class PlayerStatScaleTests(unittest.TestCase):
    def test_legacy_endpoints_and_midpoint_map_to_current_scale(self):
        self.assertEqual(legacy_player_stat(50), 0)
        self.assertEqual(legacy_player_stat(650), 2750)
        self.assertEqual(legacy_player_stat(1250), 5500)

    def test_migrated_values_keep_normalized_gameplay_strength(self):
        for legacy in (50, 100, 500, 650, 700, 1100, 1250):
            migrated = round(legacy_player_stat(legacy))
            old_unit = (legacy - 50) / 1200
            self.assertAlmostEqual(normalize_player_stat(migrated, 0), old_unit, delta=1 / 5500)

    def test_requested_grade_boundaries_are_exact(self):
        cases = {
            5500: "S", 5000: "S", 4999: "A+", 4500: "A+",
            4499: "A-", 4000: "A-", 3999: "B+", 3500: "B+",
            3499: "B-", 3000: "B-", 2999: "C+", 2500: "C+",
            2499: "C-", 2000: "C-", 1999: "D+", 1500: "D+",
            1499: "D", 1000: "D", 999: "E+", 500: "E+", 499: "E-", 0: "E-",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(rank_for_average(value, PLAYER_GRADE_THRESHOLDS), expected)

    def test_all_bundled_team_stats_use_current_scale(self):
        metadata = current_scale_metadata()
        manager_fields = ("戦術変更への積極性", "選手交代への積極性", "インテリジェンス")
        for path in (ROOT / "teams").rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertEqual(payload.get("能力値スケール"), metadata, path)
            for player in payload.get("選手一覧", []):
                for field in STAT_FIELDS:
                    value = float(player[field])
                    self.assertGreaterEqual(value, PLAYER_STAT_MIN, (path, field))
                    self.assertLessEqual(value, PLAYER_STAT_MAX, (path, field))
            info = payload.get("チーム情報", {})
            for field in manager_fields:
                if field in info:
                    value = float(info[field])
                    self.assertGreaterEqual(value, PLAYER_STAT_MIN, (path, field))
                    self.assertLessEqual(value, PLAYER_STAT_MAX, (path, field))
            targets = payload.get("チームチューナー", {}).get("基準値ステータス", {})
            for field, raw in targets.items():
                value = float(raw)
                self.assertGreaterEqual(value, PLAYER_STAT_MIN, (path, field))
                self.assertLessEqual(value, PLAYER_STAT_MAX, (path, field))

    def test_metadata_free_custom_team_is_loaded_as_legacy_scale(self):
        path = next((ROOT / "teams").rglob("*.json"))
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        legacy = deepcopy(payload)
        legacy.pop("能力値スケール", None)
        for player in legacy["選手一覧"]:
            for field in STAT_FIELDS:
                player[field] = "650"
        choice = team_choice_from_payload(legacy, "legacy-custom.json")
        self.assertEqual(choice["starters"][0]["raw"]["ShotPower"], 2750)


if __name__ == "__main__":
    unittest.main()
