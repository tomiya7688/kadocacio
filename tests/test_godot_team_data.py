from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.core.stat_scale import current_scale_metadata, normalize_player_stat
from scripts.tools import godot_team_contract as contract
from scripts.tools import godot_team_oracle as oracle


def team_payload() -> dict:
    return {
        "能力値スケール": current_scale_metadata(),
        "チーム情報": {"チーム名": "テスト", "戦術への忠実さ": 30},
        "選手一覧": [
            {"名前": f"選手{i}", "ポジションX": i + 1, "ポジションY": 11 if i == 0 else 8}
            for i in range(7)
        ],
    }


class GodotTeamDataTests(unittest.TestCase):
    def test_derived_contract_matches_python_reference(self):
        self.assertTrue(contract.check_contract())
        data = contract.build_contract()
        self.assertEqual(data["scale"]["current"], current_scale_metadata())
        self.assertEqual(set(data["stat_keys"]), set(data["stat_fallbacks"]))
        self.assertEqual(data["stat_fallbacks"]["DashSpeed"], "Speed")
        self.assertEqual(data["stat_fallbacks"]["Intelligence"], "Mental")
        self.assertEqual(data["stat_fallbacks"]["ZoneMarking"], "ZoneMarking")
        self.assertEqual(data["stat_fallbacks"]["ShotPower"], "Kick")
        self.assertEqual(data["player_aliases"]["Name"][0], "名前")

    def test_fallback_extraction_ignores_nonconstant_and_unrelated_calls(self):
        source = """
other(raw, 'Ignored')
obj.player_stat(raw, 'Ignored')
player_stat(raw)
player_stat(raw, variable)
player_stat(raw, 123)
player_stat(raw, 'DashSpeed', legacy_key='Speed')
player_stat(raw, 'ShotPower', legacy_key=variable)
"""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "scripts/match").mkdir(parents=True)
            (root / "scripts/match/player.py").write_text(source, encoding="utf-8")
            with patch.object(contract, "PROJECT_ROOT", root):
                result = contract.stat_fallbacks()
        self.assertNotIn("Ignored", result)
        self.assertEqual(result["DashSpeed"], "Speed")
        self.assertEqual(result["ShotPower"], "Kick")

    def test_contract_cli_detects_drift_and_explicitly_regenerates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data/contract.json"
            self.assertFalse(contract.check_contract(path))
            with patch.object(contract, "CONTRACT_PATH", path):
                self.assertEqual(contract.main(["--write"]), 0)
            self.assertTrue(contract.check_contract(path))
            with patch.object(contract, "check_contract", return_value=True):
                self.assertEqual(contract.main([]), 0)
            path.write_text("{}", encoding="utf-8")
            self.assertFalse(contract.check_contract(path))
            with patch.object(contract, "check_contract", return_value=False):
                self.assertEqual(contract.main([]), 1)

    def test_public_oracle_excludes_private_and_untracked_teams(self):
        listing = "teams/z.json\0teams/カルチョビット/private.json\0teams/a.json\0teams/readme.md\0"
        with patch.object(oracle.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, listing, "")) as run:
            paths = oracle.public_team_paths()
        self.assertEqual(paths, [oracle.PROJECT_ROOT / "teams/a.json", oracle.PROJECT_ROOT / "teams/z.json"])
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "-z", "--", "teams"])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_reference_case_keeps_payload_and_normalizes_parameters(self):
        payload = team_payload()
        payload["チームID"] = "team:test"
        payload["チームID別名"] = ["json:case.json"]
        payload["選手一覧"][0].update({"Intelligence": 5500, "名前": "日本語", "Name": "ignored", "スキル": ["バナナシュート", "unknown"]})
        original = deepcopy(payload)
        result = oracle.reference_case(payload, "case.json")
        self.assertTrue(result["valid"])
        self.assertEqual(result["choice"]["id"], "team:test")
        self.assertEqual(result["choice"]["legacy_ids"], ["json:case.json"])
        self.assertEqual(result["choice"]["starters"][0]["name"], "日本語")
        self.assertEqual(result["parameters"][0]["stats"]["Intelligence"], normalize_player_stat(5500, 0))
        self.assertEqual(result["parameters"][0]["skills"], [contract.LEGACY_SKILL_ALIASES["バナナシュート"]])
        self.assertEqual(result["parameters"][0]["tactical_discipline"], 0.3)
        self.assertEqual(payload, original)
        for invalid in (None, [], {"選手一覧": []}):
            with self.subTest(invalid=invalid):
                self.assertFalse(oracle.reference_case(invalid, "bad.json")["valid"])

    def test_synthetic_cases_cover_legacy_new_formation_and_invalid_inputs(self):
        cases = oracle.synthetic_cases(team_payload())
        self.assertGreater(len(cases), 100)
        self.assertTrue(any(not row["valid"] for row in cases))
        self.assertTrue(next(row for row in cases if row["source"].endswith("formation-7-7.json"))["valid"])
        self.assertFalse(next(row for row in cases if row["source"].endswith("formation-6-1.json"))["valid"])
        self.assertTrue(any("能力値スケール" not in row["payload"] for row in cases if isinstance(row["payload"], dict)))
        long_case = next(row for row in cases if "japanese-precedence" in row["source"])
        self.assertGreater(len(long_case["choice"]["description"]), 10000)
        json.dumps(cases, allow_nan=False)

    def test_fingerprints_detect_any_source_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "team.json"
            source.write_text("{}", encoding="utf-8")
            before = oracle.file_fingerprints([source])
            oracle.assert_sources_unchanged(before)
            source.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "modified"):
                oracle.assert_sources_unchanged(before)

    def test_oracle_writes_only_ignored_fixtures_and_keeps_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "teams/nested/team.json"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps(team_payload(), ensure_ascii=False), encoding="utf-8-sig")
            with patch.object(oracle, "PROJECT_ROOT", root), patch.object(oracle, "USER_LOG_DIR", root / "logs"), patch.object(oracle, "public_team_paths", return_value=[source]):
                path, before = oracle.write_oracle()
            oracle.assert_sources_unchanged(before)
            fixture = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(fixture["files"][0]["source"], "nested/team.json")
            self.assertTrue(fixture["cases"][0]["valid"])
            self.assertTrue((Path(fixture["catalog_root"]) / "nested/good.json").read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(set(before), {str(source)})

    def test_oracle_fails_closed_without_valid_reference_or_fresh_contract(self):
        with patch.object(oracle, "check_contract", return_value=False), self.assertRaisesRegex(ValueError, "stale"):
            oracle.write_oracle()
        with patch.object(oracle, "public_team_paths", return_value=[]), self.assertRaisesRegex(ValueError, "No tracked"):
            oracle.write_oracle()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "teams/bad.json"
            source.parent.mkdir()
            source.write_text("{}", encoding="utf-8")
            with patch.object(oracle, "PROJECT_ROOT", root), patch.object(oracle, "public_team_paths", return_value=[source]), self.assertRaisesRegex(ValueError, "No valid"):
                oracle.write_oracle()


if __name__ == "__main__":
    unittest.main()
