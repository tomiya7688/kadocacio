import json
import unittest
from pathlib import Path

from settings import PROJECT_NAME
from skill_system import ALL_SKILLS, LEGACY_SKILL_ALIASES, normalized_skills
from team_editor_data import normalize_editor_payload


ROOT = Path(__file__).resolve().parents[1]


class SkillNameMigrationTests(unittest.TestCase):
    def test_project_and_new_skill_names_are_unique(self):
        self.assertEqual(PROJECT_NAME, "カドカルチョ")
        self.assertEqual(len(ALL_SKILLS), 40)
        self.assertEqual(len(set(ALL_SKILLS)), 40)
        self.assertFalse(set(ALL_SKILLS) & set(LEGACY_SKILL_ALIASES))

    def test_legacy_skill_names_are_normalized_for_matches_and_editor(self):
        old_name = "バナナシュート"
        new_name = LEGACY_SKILL_ALIASES[old_name]
        self.assertEqual(normalized_skills([old_name]), frozenset({new_name}))
        payload = normalize_editor_payload({"選手一覧": [{"スキル": [old_name]}], "チーム情報": {}})
        self.assertEqual(payload["選手一覧"][0]["スキル"], [new_name])

    def test_bundled_team_json_uses_only_new_skill_names(self):
        for path in (ROOT / "teams").rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            for player in payload.get("選手一覧", []):
                skills = player.get("スキル", [])
                self.assertFalse(set(skills) & set(LEGACY_SKILL_ALIASES), str(path))


if __name__ == "__main__":
    unittest.main()
