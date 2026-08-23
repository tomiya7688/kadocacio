from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.core.performance_settings import (
    PerformanceSettings,
    league_simulation_profile,
    limited_worker_count,
    load_performance_settings,
    next_cpu_limit,
    normalize_cpu_limit,
    save_performance_settings,
    simulation_wall_time_budget,
    worker_duty_cycle,
    normalize_league_simulation_mode,
)


class PerformanceSettingsTests(unittest.TestCase):
    def test_limits_are_clamped_and_worker_budget_never_reaches_zero(self):
        self.assertEqual(normalize_cpu_limit(-20), 10)
        self.assertEqual(normalize_cpu_limit(140), 100)
        self.assertEqual(limited_worker_count(8, 25), 2)
        self.assertEqual(limited_worker_count(3, 10), 1)
        self.assertAlmostEqual(worker_duty_cycle(3, 50, 2), 0.75)
        self.assertAlmostEqual(worker_duty_cycle(3, 10, 1), 0.30)

    def test_main_thread_budget_scales_with_cpu_limit(self):
        self.assertAlmostEqual(simulation_wall_time_budget(100), 0.008)
        self.assertAlmostEqual(simulation_wall_time_budget(50), 0.004)
        self.assertAlmostEqual(simulation_wall_time_budget(10), 0.0008)

    def test_ui_cycle_wraps_through_presets(self):
        self.assertEqual(next_cpu_limit(10), 25)
        self.assertEqual(next_cpu_limit(63), 75)
        self.assertEqual(next_cpu_limit(100), 10)

    def test_league_quality_profiles_order_rethink_frequency(self):
        ultra = float(league_simulation_profile("ULTRA_PRECISE")["ai_rethink_multiplier"])
        precise = float(league_simulation_profile("PRECISE")["ai_rethink_multiplier"])
        normal = float(league_simulation_profile("NORMAL")["ai_rethink_multiplier"])
        light = float(league_simulation_profile("LIGHT")["ai_rethink_multiplier"])
        self.assertLess(ultra, precise)
        self.assertLess(precise, normal)
        self.assertLess(normal, light)
        self.assertEqual(normalize_league_simulation_mode("unknown"), "PRECISE")

    def test_japanese_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "performance_settings.json"
            save_performance_settings(
                PerformanceSettings(
                    cpu_limit_percent=50,
                    gpu_rendering=False,
                    league_simulation_mode="LIGHT",
                ),
                path,
            )
            loaded = load_performance_settings(path)
            self.assertEqual(loaded.cpu_limit_percent, 50)
            self.assertFalse(loaded.gpu_rendering)
            self.assertEqual(loaded.league_simulation_mode, "LIGHT")
            text = path.read_text(encoding="utf-8")
            self.assertIn('"CPU使用率上限": 50', text)
            self.assertIn('"GPU描画": false', text)
            self.assertIn('"リーグ裏試合モード": "LIGHT"', text)


if __name__ == "__main__":
    unittest.main()
