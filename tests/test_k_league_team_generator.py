import json
import tempfile
import unittest
from pathlib import Path

from scripts.core.paths import TEAMS_DIR, TEMPLATE_DIR
from scripts.team.team_editor_data import validate_payload
from scripts.tools.generate_k_league_teams import (
    build_generation_plan,
    league_template_payload,
    load_generation_config,
    make_generated_payload,
    team_mean,
    write_generation,
)


class KLeagueTeamGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generation_config()
        cls.editor_options = json.loads(
            (TEMPLATE_DIR / "editor_options.json").read_text(encoding="utf-8")
        )

    def test_default_plan_has_nine_leagues_and_180_unique_teams(self) -> None:
        plan = build_generation_plan(self.config)

        self.assertEqual(len(plan), 180)
        self.assertEqual(len({entry["league_name"] for entry in plan}), 9)
        self.assertEqual(len({entry["team_name"] for entry in plan}), 180)
        self.assertTrue(all(
            len([entry for entry in plan if entry["league_number"] == league_number]) == 20
            for league_number in range(1, 10)
        ))

    def test_k1_and_k2_reuse_existing_clubs_without_editing_sources(self) -> None:
        plan = build_generation_plan(self.config)
        source_entries = [entry for entry in plan if entry["league_number"] in (1, 2)]

        self.assertEqual(len(source_entries), 40)
        self.assertTrue(all(isinstance(entry["source_path"], Path) for entry in source_entries))
        self.assertTrue(all(entry["source_path"].is_relative_to(TEAMS_DIR) for entry in source_entries))

    def test_generated_lower_league_payload_is_valid_and_weaker(self) -> None:
        plan = build_generation_plan(self.config)
        k3_entry = next(entry for entry in plan if entry["league_number"] == 3)
        k9_entry = next(entry for entry in plan if entry["league_number"] == 9)

        k3 = make_generated_payload(k3_entry, self.editor_options, seed=1234)
        k9 = make_generated_payload(k9_entry, self.editor_options, seed=1234)

        self.assertEqual(validate_payload(k3), [])
        self.assertEqual(validate_payload(k9), [])
        self.assertGreater(team_mean(k3), team_mean(k9) + 700)

    def test_small_write_creates_valid_template_and_preserves_source_bytes(self) -> None:
        plan = build_generation_plan(self.config, league_count=3, teams_per_league=2)
        source = next(entry["source_path"] for entry in plan if entry["source_path"] is not None)
        before = source.read_bytes()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root = root / "teams"
            template_path = root / "league_templates" / "K1-K3.json"
            write_generation(
                plan,
                output_root=output_root,
                template_path=template_path,
                editor_options=self.editor_options,
                seed=1234,
                overwrite=False,
            )

            generated_paths = sorted(output_root.rglob("*.json"))
            template = json.loads(template_path.read_text(encoding="utf-8"))
            generated_payload = json.loads(
                next(path for path in generated_paths if "KadokaOriginalK3" in path.parts).read_text(encoding="utf-8")
            )

            self.assertEqual(len(generated_paths), 6)
            self.assertEqual(len(template["リーグ一覧"]), 3)
            self.assertEqual(validate_payload(generated_payload), [])
            self.assertEqual(source.read_bytes(), before)

    def test_template_links_every_planned_team_and_orders_divisions(self) -> None:
        plan = build_generation_plan(self.config, league_count=4, teams_per_league=3)
        payload = league_template_payload(plan)

        self.assertEqual([league["リーグ名"] for league in payload["リーグ一覧"]], [
            "K1リーグ", "K2リーグ", "K3リーグ", "K4リーグ",
        ])
        self.assertEqual(payload["リーグ一覧"][1]["上位リーグ"], "K1リーグ")
        self.assertEqual(sum(len(league["所属チーム"]) for league in payload["リーグ一覧"]), 12)


if __name__ == "__main__":
    unittest.main()
