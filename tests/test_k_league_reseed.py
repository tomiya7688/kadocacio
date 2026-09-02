import json
import tempfile
import unittest
from pathlib import Path

from scripts.tools.reseed_k_league_teams import (
    apply_reseed_plan,
    build_reseed_plan,
    checkpoint_competition_template,
    validate_reseed_files,
)


def _league(name: str, upper: str, teams: list[str]) -> dict:
    return {
        "リーグ名": name,
        "表示色": "#123456",
        "開幕日": 14,
        "最終節日": 330,
        "上位リーグ": upper,
        "所属チーム": teams,
    }


class KLeagueReseedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.teams_root = self.root / "teams"
        self.template_path = self.root / "league_templates" / "K1-K2.json"
        self.original_ids = [
            "json:KadokaOriginalK1/Alpha.json",
            "json:KadokaOriginalK1/Beta.json",
            "json:KadokaOriginalK2/Gamma.json",
            "json:KadokaOriginalK2/Delta.json",
        ]
        for team_id in self.original_ids:
            relative = Path(team_id.removeprefix("json:"))
            path = self.teams_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"name": path.stem}), encoding="utf-8")
        self.template = {
            "リーグ一覧": [
                _league("K1リーグ", "", self.original_ids[:2]),
                _league("K2リーグ", "K1リーグ", self.original_ids[2:]),
            ],
            "トーナメント一覧": [],
        }
        self.template_path.parent.mkdir(parents=True, exist_ok=True)
        self.template_path.write_text(
            json.dumps(self.template, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def checkpoint(self, k1: list[str], k2: list[str], *, seasons: int = 2) -> dict:
        return {
            "seasons_completed": seasons,
            "manager_state": {
                "competition_template": {
                    "リーグ一覧": [
                        _league("K1リーグ", "", k1),
                        _league("K2リーグ", "K1リーグ", k2),
                    ]
                }
            },
        }

    def test_plan_uses_simulated_membership_after_promotion(self) -> None:
        checkpoint = self.checkpoint(
            [self.original_ids[0], self.original_ids[2]],
            [self.original_ids[1], self.original_ids[3]],
        )

        plan = build_reseed_plan(checkpoint, self.template, teams_root=self.teams_root)
        moves = [entry for entry in plan if entry["move_required"]]

        self.assertEqual(len(moves), 2)
        self.assertEqual(
            {(entry["team_name"], entry["league_name"]) for entry in moves},
            {("Gamma", "K1リーグ"), ("Beta", "K2リーグ")},
        )

    def test_apply_moves_files_updates_template_and_keeps_backup(self) -> None:
        checkpoint = self.checkpoint(
            [self.original_ids[0], self.original_ids[2]],
            [self.original_ids[1], self.original_ids[3]],
        )
        plan = build_reseed_plan(checkpoint, self.template, teams_root=self.teams_root)

        backup = apply_reseed_plan(
            plan,
            self.template,
            template_path=self.template_path,
            teams_root=self.teams_root,
            backup_root=self.root / "backups",
        )

        self.assertTrue((self.teams_root / "KadokaOriginalK1" / "Gamma.json").exists())
        self.assertTrue((self.teams_root / "KadokaOriginalK2" / "Beta.json").exists())
        self.assertFalse((self.teams_root / "KadokaOriginalK2" / "Gamma.json").exists())
        self.assertFalse((self.teams_root / "KadokaOriginalK1" / "Beta.json").exists())
        updated = json.loads(self.template_path.read_text(encoding="utf-8"))
        self.assertIn(
            "json:KadokaOriginalK1/Gamma.json",
            updated["リーグ一覧"][0]["所属チーム"],
        )
        self.assertTrue((backup / "manifest.json").exists())
        self.assertTrue((backup / "league_template.json").exists())
        self.assertTrue((backup / "teams" / "KadokaOriginalK2" / "Gamma.json").exists())

    def test_checkpoint_requires_a_completed_season(self) -> None:
        checkpoint = self.checkpoint(self.original_ids[:2], self.original_ids[2:], seasons=0)

        with self.assertRaisesRegex(ValueError, "1年度"):
            checkpoint_competition_template(checkpoint)

    def test_team_set_mismatch_is_rejected_before_file_operations(self) -> None:
        checkpoint = self.checkpoint(
            [self.original_ids[0], "json:KadokaOriginalK2/Unknown.json"],
            [self.original_ids[1], self.original_ids[3]],
        )

        with self.assertRaisesRegex(ValueError, "チーム集合"):
            build_reseed_plan(checkpoint, self.template, teams_root=self.teams_root)

    def test_existing_destination_collision_is_rejected(self) -> None:
        checkpoint = self.checkpoint(
            [self.original_ids[0], self.original_ids[2]],
            [self.original_ids[1], self.original_ids[3]],
        )
        collision = self.teams_root / "KadokaOriginalK1" / "Gamma.json"
        collision.write_text("collision", encoding="utf-8")
        plan = build_reseed_plan(checkpoint, self.template, teams_root=self.teams_root)

        with self.assertRaisesRegex(FileExistsError, "別ファイル"):
            validate_reseed_files(plan)


if __name__ == "__main__":
    unittest.main()
