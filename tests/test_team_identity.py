import json
import tempfile
import unittest
from pathlib import Path

from scripts.team.team_identity import (
    TEAM_ID_ALIASES_KEY,
    TEAM_ID_KEY,
    deterministic_team_id,
    ensure_team_identity,
    legacy_team_id,
)
from scripts.tools.migrate_team_ids import migrate_team_tree


class TeamIdentityTests(unittest.TestCase):
    def test_new_identity_is_path_independent_and_remembers_legacy_alias(self) -> None:
        payload = {}
        old_id = legacy_team_id("関東/東京.json")

        team_id = ensure_team_identity(payload, legacy_id=old_id)
        ensure_team_identity(payload, legacy_id="json:移動後/東京.json")

        self.assertTrue(team_id.startswith("team:"))
        self.assertEqual(payload[TEAM_ID_KEY], team_id)
        self.assertEqual(
            payload[TEAM_ID_ALIASES_KEY],
            [old_id, "json:移動後/東京.json"],
        )

    def test_repository_migration_is_deterministic_and_updates_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            teams = root / "teams"
            teams.mkdir()
            team_path = teams / "旧パス.json"
            team_path.write_text(
                json.dumps({"選手一覧": [], "チーム情報": {"チーム名": "固定ID"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            old_id = legacy_team_id("旧パス.json")
            reference = root / "leagues.json"
            reference.write_text(
                json.dumps({"所属チーム": [old_id]}, ensure_ascii=False),
                encoding="utf-8",
            )

            first = migrate_team_tree(teams, [reference])
            second = migrate_team_tree(teams, [reference])
            payload = json.loads(team_path.read_text(encoding="utf-8"))
            league = json.loads(reference.read_text(encoding="utf-8"))

        expected = deterministic_team_id(old_id)
        self.assertEqual(first[old_id], expected)
        self.assertEqual(second[old_id], expected)
        self.assertEqual(payload[TEAM_ID_KEY], expected)
        self.assertIn(old_id, payload[TEAM_ID_ALIASES_KEY])
        self.assertEqual(league["所属チーム"], [expected])

    def test_duplicate_persistent_ids_are_rejected_by_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            teams = Path(temporary) / "teams"
            teams.mkdir()
            duplicate = "team:duplicate"
            for name in ("a.json", "b.json"):
                (teams / name).write_text(
                    json.dumps({TEAM_ID_KEY: duplicate, "選手一覧": [], "チーム情報": {}}, ensure_ascii=False),
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(ValueError, "重複"):
                migrate_team_tree(teams)


if __name__ == "__main__":
    unittest.main()
