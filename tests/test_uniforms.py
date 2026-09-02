import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pygame

from scripts.app.uniform_rendering import draw_uniform_polygon
from scripts.team.team_data import (
    team_choice_from_payload,
    team_choice_from_snapshot,
    team_snapshot_from_choice,
)
from scripts.team.team_editor_data import create_team_template, validate_payload
from scripts.team.uniform_data import (
    UNIFORM_PART_SIZES,
    default_uniform,
    export_uniform,
    load_uniform,
    normalize_uniform,
    runtime_uniform,
    validate_uniform,
)


class UniformDataTests(unittest.TestCase):
    def test_default_uniform_has_all_five_fixed_size_parts(self) -> None:
        uniform = default_uniform()
        self.assertEqual(validate_uniform(uniform), [])
        for part, (width, height) in UNIFORM_PART_SIZES.items():
            rows = uniform["パーツ"][part]
            self.assertEqual(len(rows), height)
            self.assertTrue(all(len(row) == width for row in rows))

    def test_normalize_repairs_bad_cells_and_runtime_resolves_tokens(self) -> None:
        source = {"パーツ": {"胸": [["#12abef", "invalid"], ["S"]]}}
        normalized = normalize_uniform(source)
        self.assertEqual(normalized["パーツ"]["胸"][0][:2], ["#12ABEF", "P"])
        runtime = runtime_uniform(normalized, (10, 20, 30), (40, 50, 60))
        self.assertEqual(runtime["胸"][0][:2], ((18, 171, 239), (10, 20, 30)))
        self.assertEqual(runtime["胸"][1][0], (40, 50, 60))

    def test_export_and_import_round_trip(self) -> None:
        uniform = default_uniform()
        uniform["パーツ"]["胸"][2][3] = "#ABCDEF"
        with tempfile.TemporaryDirectory() as temporary:
            with patch("scripts.team.uniform_data.UNIFORMS_DIR", Path(temporary)):
                path = export_uniform(uniform, "テスト / ユニフォーム")
                self.assertTrue(path.exists())
                self.assertEqual(load_uniform(path), normalize_uniform(uniform))

    def test_league_snapshot_preserves_uniform(self) -> None:
        payload = create_team_template("initial")
        payload["チーム情報"]["ユニフォーム"]["パーツ"]["右腕"][1][1] = "#102030"
        choice = team_choice_from_payload(payload, "folder/team.json")
        choice["id"] = "folder/team.json"
        restored = team_choice_from_snapshot(team_snapshot_from_choice(choice))
        self.assertIsNotNone(restored)
        self.assertEqual(restored["uniform_data"]["パーツ"]["右腕"][1][1], "#102030")
        self.assertEqual(validate_payload(payload), [])

    def test_pattern_renderer_keeps_distinct_pixel_cells(self) -> None:
        surface = pygame.Surface((24, 24))
        grid = (((255, 0, 0), (0, 255, 0)), ((0, 0, 255), (255, 255, 255)))
        points = [pygame.Vector2(2, 22), pygame.Vector2(22, 22), pygame.Vector2(22, 2), pygame.Vector2(2, 2)]
        draw_uniform_polygon(surface, points, grid, (0, 0, 0))
        self.assertEqual(surface.get_at((7, 7))[:3], (255, 0, 0))
        self.assertEqual(surface.get_at((17, 7))[:3], (0, 255, 0))
        self.assertEqual(surface.get_at((7, 17))[:3], (0, 0, 255))
        self.assertEqual(surface.get_at((17, 17))[:3], (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
