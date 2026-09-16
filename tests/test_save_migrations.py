import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.league.league_manager import LeagueManager
from scripts.league.save_migrations import (
    CURRENT_FORMAT_VERSION,
    SaveFormatError,
    detect_format_version,
    migrate_save_payload,
    validate_current_save_payload,
)
from scripts.team.team_data import discover_team_choices


class SaveMigrationUnitTests(unittest.TestCase):
    def test_detect_format_version_handles_legacy_current_and_invalid_values(self) -> None:
        self.assertEqual(detect_format_version({}), 0)
        self.assertEqual(detect_format_version({"format_version": 1}), 1)
        for value in (True, -1, "1", 1.5):
            with self.subTest(value=value), self.assertRaises(SaveFormatError):
                detect_format_version({"format_version": value})

    def test_legacy_payload_migrates_to_v1_without_mutating_source(self) -> None:
        original = {"save_name": "legacy", "fixtures": [], "league_memberships": {}}
        migrated, source_version = migrate_save_payload(original)

        self.assertEqual(source_version, 0)
        self.assertEqual(migrated["format_version"], CURRENT_FORMAT_VERSION)
        self.assertNotIn("format_version", original)

    def test_current_payload_is_accepted_without_version_change(self) -> None:
        original = {"format_version": CURRENT_FORMAT_VERSION, "fixtures": []}
        migrated, source_version = migrate_save_payload(original)

        self.assertEqual(source_version, CURRENT_FORMAT_VERSION)
        self.assertEqual(migrated, original)
        self.assertIsNot(migrated, original)

    def test_future_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(SaveFormatError, "未来format_version"):
            migrate_save_payload({"format_version": CURRENT_FORMAT_VERSION + 1})

    def test_current_schema_rejects_invalid_collection_shapes(self) -> None:
        valid = {
            "format_version": CURRENT_FORMAT_VERSION,
            "fixtures": [],
            "last_results": [],
            "history": [],
            "league_memberships": {},
            "league_participations": {},
            "team_signature": {},
            "チームスナップショット": {},
        }
        validate_current_save_payload(valid)

        bad_list = deepcopy(valid)
        bad_list["fixtures"] = {}
        with self.assertRaisesRegex(SaveFormatError, "fixtures"):
            validate_current_save_payload(bad_list)

        bad_dict = deepcopy(valid)
        bad_dict["league_memberships"] = []
        with self.assertRaisesRegex(SaveFormatError, "league_memberships"):
            validate_current_save_payload(bad_dict)

        wrong_version = deepcopy(valid)
        wrong_version["format_version"] = 0
        with self.assertRaisesRegex(SaveFormatError, "現行format_version"):
            validate_current_save_payload(wrong_version)


class SaveMigrationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.save_dir = root / "league_save"
        self.state_patch = patch(
            "scripts.league.league_manager.LEAGUE_STATE_PATH",
            root / "league_state.json",
        )
        self.save_dir_patch = patch(
            "scripts.league.league_manager.LEAGUE_SAVE_DIR",
            self.save_dir,
        )
        self.state_patch.start()
        self.save_dir_patch.start()

    def tearDown(self) -> None:
        self.save_dir_patch.stop()
        self.state_patch.stop()
        self.temp_dir.cleanup()

    def test_new_saves_write_format_version(self) -> None:
        manager = LeagueManager(discover_team_choices())
        payload = json.loads(manager.save_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["format_version"], CURRENT_FORMAT_VERSION)

    def test_legacy_save_is_backed_up_then_rewritten_as_current(self) -> None:
        manager = LeagueManager(discover_team_choices())
        legacy_path = self.save_dir / "legacy.json"
        legacy = manager._state_payload()
        legacy.pop("format_version")
        legacy["save_name"] = "legacy"
        legacy["day"] = 77
        original_text = json.dumps(legacy, ensure_ascii=False, indent=2)
        legacy_path.write_text(original_text, encoding="utf-8")

        self.assertEqual(manager.load_save(legacy_path.name), [])

        backup = self.save_dir / "legacy.json.v0.bak"
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_text(encoding="utf-8"), original_text)
        rewritten = json.loads(legacy_path.read_text(encoding="utf-8"))
        self.assertEqual(rewritten["format_version"], CURRENT_FORMAT_VERSION)
        self.assertEqual(manager.day, 77)

    def test_future_save_is_rejected_without_modifying_source(self) -> None:
        manager = LeagueManager(discover_team_choices())
        future_path = self.save_dir / "future.json"
        payload = manager._state_payload()
        payload["format_version"] = CURRENT_FORMAT_VERSION + 1
        original_text = json.dumps(payload, ensure_ascii=False, indent=2)
        future_path.write_text(original_text, encoding="utf-8")

        errors = manager.load_save(future_path.name)

        self.assertTrue(any("未来format_version" in error for error in errors))
        self.assertEqual(future_path.read_text(encoding="utf-8"), original_text)
        self.assertFalse((self.save_dir / "future.json.v2.bak").exists())


if __name__ == "__main__":
    unittest.main()
