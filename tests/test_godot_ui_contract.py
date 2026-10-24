from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.core.performance_settings import LEAGUE_SIMULATION_MODES, normalize_cpu_limit
from scripts.core.settings import WINDOW_SIZE_OPTIONS
from scripts.tools import godot_ui_contract as contract


class GodotUiContractTests(unittest.TestCase):
    def test_generated_choices_match_reference_and_committed_contract(self):
        values = json.loads(contract.contract_text())
        self.assertEqual(values["modes"], LEAGUE_SIMULATION_MODES)
        self.assertEqual(values["cpu_min"], normalize_cpu_limit(-1))
        self.assertEqual(values["cpu_max"], normalize_cpu_limit(1000))
        self.assertEqual(values["window_sizes"], [list(size) for size in WINDOW_SIZE_OPTIONS])
        self.assertTrue(contract.check_contract())

    def test_check_missing_stale_and_current_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            self.assertFalse(contract.check_contract(path))
            path.write_text("{}", encoding="utf-8")
            self.assertFalse(contract.check_contract(path))
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")
            path.write_text(contract.contract_text(), encoding="utf-8")
            self.assertTrue(contract.check_contract(path))

    def test_cli_checks_or_explicitly_generates(self):
        for valid in (False, True):
            with patch.object(contract, "check_contract", return_value=valid):
                self.assertEqual(contract.main([]), 0 if valid else 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "choices.json"
            with patch.object(contract, "CONTRACT_PATH", path):
                self.assertEqual(contract.main(["--write"]), 0)
            self.assertTrue(contract.check_contract(path))


if __name__ == "__main__":
    unittest.main()
