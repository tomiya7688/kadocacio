import random
import unittest

from scripts.team.team_editor import TeamEditor
from scripts.team.team_editor_config import load_editor_options
from scripts.team.team_editor_data import STAT_FIELDS, create_team_template
from scripts.team.team_template_profile import target_for_rank


class TeamTemplateProfileTests(unittest.TestCase):
    def test_rank_targets_use_the_middle_of_each_display_band(self) -> None:
        self.assertEqual(target_for_rank("S"), 5250)
        self.assertEqual(target_for_rank("A+"), 4750)
        self.assertEqual(target_for_rank("E-"), 250)

    def test_physical_profile_redistributes_stats_without_changing_mean(self) -> None:
        options = load_editor_options()
        target = 2750
        payload = create_team_template(
            "target", target=target, spread="小", rng=random.Random(29),
            options=options, profile_id="physical",
        )
        players = payload["選手一覧"]
        all_values = [int(player[field]) for player in players for field in STAT_FIELDS]
        categories = {
            str(entry["id"]): tuple(entry["fields"])
            for entry in options["generation_categories"]
        }

        def category_mean(category_id: str) -> float:
            values = [int(player[field]) for player in players for field in categories[category_id]]
            return sum(values) / len(values)

        self.assertAlmostEqual(sum(all_values) / len(all_values), target, delta=1.0)
        self.assertGreater(category_mean("physical"), category_mean("technique") + 800)

    def test_editor_can_switch_rank_input_and_cycle_profile_without_generating(self) -> None:
        editor = TeamEditor.__new__(TeamEditor)
        editor.target_mean = "2750"
        editor.target_input_mode = "number"
        editor.target_rank = "C+"
        editor.target_profile_id = "balanced"
        editor.editor_options = load_editor_options()
        editor.active_input = ({}, "target", "editor_target")

        editor._perform("target_mode", None)
        self.assertEqual(editor.target_input_mode, "rank")
        self.assertEqual(editor.target_rank, "C+")
        self.assertEqual(editor.target_mean, "2750")
        self.assertIsNone(editor.active_input)

        editor._perform("target_rank_step", -1)
        self.assertEqual(editor.target_rank, "B-")
        self.assertEqual(editor.target_mean, "3250")

        editor._perform("generation_profile", None)
        self.assertEqual(editor.target_profile_id, "physical")


if __name__ == "__main__":
    unittest.main()
