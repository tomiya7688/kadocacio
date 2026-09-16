import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.team.team_identity import (
    TEAM_ID_ALIASES_KEY,
    TEAM_ID_KEY,
    deterministic_team_id,
    ensure_team_identity,
    legacy_team_id,
)
from scripts.tools import migrate_team_ids as migration
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

    def test_format_preserving_helpers_cover_bom_empty_and_unchanged_paths(self) -> None:
        text, bom = migration._decode_json_bytes(b"\xef\xbb\xbf{}")
        self.assertEqual(text, "{}")
        self.assertEqual(bom, b"\xef\xbb\xbf")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload_path = root / "payload.json"
            payload_path.write_text("{}", encoding="utf-8")
            before = payload_path.read_bytes()
            migration._append_root_fields(payload_path, [])
            self.assertEqual(payload_path.read_bytes(), before)

            migration._append_root_fields(payload_path, [("first", 1), ("second", 2)])
            self.assertEqual(
                json.loads(payload_path.read_text(encoding="utf-8")),
                {"first": 1, "second": 2},
            )

            unchanged = root / "unchanged.json"
            unchanged.write_text('{"team": "other"}', encoding="utf-8")
            before = unchanged.read_bytes()
            migration._replace_reference_ids(unchanged, {"json:missing.json": "team:new"})
            self.assertEqual(unchanged.read_bytes(), before)

    def test_default_reference_paths_include_existing_modern_and_legacy_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            modern_templates = root / "user_data" / "config" / "templates"
            modern_saves = root / "user_data" / "saves"
            legacy_templates = root / "league_templates"
            legacy_saves = root / "league_save"
            modern_templates.mkdir(parents=True)
            legacy_templates.mkdir()
            modern_template = modern_templates / "modern.json"
            legacy_template = legacy_templates / "legacy.json"
            modern_template.write_text("{}", encoding="utf-8")
            legacy_template.write_text("{}", encoding="utf-8")

            with patch.object(migration, "PROJECT_ROOT", root), patch.object(
                migration, "LEAGUES_PATH", root / "user_data" / "config" / "leagues.json"
            ), patch.object(
                migration, "LEAGUE_STATE_PATH", root / "user_data" / "saves" / "league_state.json"
            ), patch.object(
                migration, "LEAGUE_TEMPLATE_DIR", modern_templates
            ), patch.object(
                migration, "LEAGUE_SAVE_DIR", modern_saves
            ):
                references = migration.default_reference_paths()

            self.assertIn(modern_template, references)
            self.assertIn(legacy_template, references)
            self.assertIn(root / "leagues.json", references)
            self.assertIn(root / "league_state.json", references)
            self.assertFalse(legacy_saves.is_dir())

    def test_cli_supports_reference_updates_and_explicit_no_reference_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            teams = Path(temporary) / "teams"
            teams.mkdir()

            with patch.object(
                sys, "argv", ["migrate_team_ids", "--teams-root", str(teams), "--no-reference-update"]
            ), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(migration.main(), 0)
            self.assertIn("Migrated 0 team IDs", output.getvalue())

            with patch.object(
                sys, "argv", ["migrate_team_ids", "--teams-root", str(teams)]
            ), patch.object(
                migration, "default_reference_paths", return_value=[]
            ) as references, redirect_stdout(io.StringIO()):
                self.assertEqual(migration.main(), 0)
            references.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
