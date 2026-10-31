"""Saved reproduction inputs must survive later changes to team source files."""

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("KADOKA_DISABLE_GPU", "1")

from scripts.core.settings import AWAY_BLUE
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import main, run_headless
from scripts.tools.match_repro_input import create_input_record, restore_input_record


# {
#   責務: [MatchReproInputTests: 再現入力の独立性・互換検証・CLI保存と失敗時の原本保持を確認する]
#   フィールド: [home・away: 試験の開始入力として使う読込済み両チーム。編集する試験は複製する]
# }
class MatchReproInputTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: 再現入力試験で共有する二チームを読み込む]
    #   処理: [1: 有効なチーム候補の先頭二件を保持する]
    #   引数: []
    #   戻り値: [None: クラスの開始入力を準備し、チームファイルは変更しない]
    # }
    @classmethod
    def setUpClass(cls):
        # 個々の試験で変更する値は、この共有入力から分離して使う。
        cls.home, cls.away = discover_team_choices()[:2]

    # {
    #   責務: [record: 異常値試験の基準となる新しい再現入力を作る]
    #   処理: [1: seed・更新上限・会場・判断倍率を固定して記録を作成する]
    #   引数: []
    #   戻り値: [dict: 各試験が変更できる独立した基準入力]
    # }
    def record(self):
        # 共有チームを直接変更せず、毎回新しい記録を返す。
        return create_input_record(
            self.home,
            self.away,
            seed=29,
            max_steps=45,
            venue_mode="AWAY",
            ai_rethink_multiplier=0.75,
        )

    # {
    #   責務: [test_roundtrip_preserves_exact_team_values_and_match_state: 保存復元が小数・色・試合状態を保持し元記録と独立していることを確認する]
    #   処理: [1: 複製チームへ小数能力と色を設定し参照試合を実行する; 2: 記録後に元入力を変えて復元値と試合状態を比較する; 3: 復元値の変更が記録へ戻らないことを確認する]
    #   引数: []
    #   戻り値: [None: 丸め・tuple復元・参照分離の退行は試験失敗]
    # }
    def test_roundtrip_preserves_exact_team_values_and_match_state(self):
        # 整数化や色のlist化が試合へ影響しないか、実際の短い試合で比較する。
        home, away = deepcopy(self.home), deepcopy(self.away)
        home["manager_intelligence"] = 0.123456789123
        home["starters"][0]["raw"]["ShotPower"] = 3210.123456789
        home["primary"] = away["primary"] = AWAY_BLUE
        home["secondary"] = (80, 95, 110)
        settings = {"seed": 3, "max_steps": 80, "venue_mode": "NEUTRAL", "ai_rethink_multiplier": 2.5}
        original = run_headless(home, away, **settings)
        record = create_input_record(home, away, **settings)
        saved = json.dumps(record, ensure_ascii=False)
        # 保存元を後から編集しても、開始時の記録が保持されることを検査する。
        home["starters"][0]["raw"]["ShotPower"] = 0
        restored_home, restored_away, restored_settings = restore_input_record(json.loads(saved))
        self.assertEqual(restored_home["manager_intelligence"], 0.123456789123)
        self.assertEqual(restored_home["primary"], AWAY_BLUE)
        self.assertEqual(run_headless(restored_home, restored_away, **restored_settings), original)
        restored_home["starters"][0]["raw"]["ShotPower"] = 1
        self.assertEqual(json.dumps(record, ensure_ascii=False), saved)

    # {
    #   責務: [test_cli_saves_and_reloads_without_discovering_teams: 保存入力の再実行が現行チーム探索に依存せずseed=0と原本を保持することを確認する]
    #   処理: [1: 一時ファイルへCLIで入力を新規保存する; 2: 両方のチーム探索入口を失敗させ保存入力から再実行する; 3: 結果一致と既存入力の上書き拒否を確認する]
    #   引数: []
    #   戻り値: [None: 再探索・seed置換・原本破壊は試験失敗。一時ファイルは試験専用]
    # }
    def test_cli_saves_and_reloads_without_discovering_teams(self):
        # 日本語ファイル名も含め、実CLI入口から保存と再読込を通す。
        with TemporaryDirectory() as folder:
            path = Path(folder) / "試合条件.json"
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            "--save-input",
                            str(path),
                            "--max-steps",
                            "25",
                            "--seed",
                            "0",
                            "--venue",
                            "AWAY",
                            "--ai-rethink-multiplier",
                            "0.75",
                            "--allow-partial",
                        ]
                    ),
                    0,
                )
            first_report = json.loads(output.getvalue())
            output = StringIO()
            # 読込時に現在のteamsへ戻る退行を、探索呼出しそのもので検出する。
            with patch("scripts.tools.match_repro_cli.discover_team_choices", side_effect=AssertionError("discovery")):
                with patch("scripts.app.game_app.discover_team_choices", side_effect=AssertionError("discovery")):
                    with redirect_stdout(output):
                        self.assertEqual(main(["--load-input", str(path), "--allow-partial"]), 0)
            self.assertEqual(json.loads(output.getvalue()), first_report)
            self.assertEqual(first_report["seed"], 0)
            # 保存先が既存入力と同じでも、内容を一バイトも上書きしない。
            previous = path.read_bytes()
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--load-input", str(path), "--save-input", str(path)])
            self.assertEqual(path.read_bytes(), previous)

    # {
    #   責務: [test_cli_rejects_overrides_missing_files_and_malformed_json: 入力上書き指定・不存在・不正JSONがCLIエラーになることを確認する]
    #   処理: [1: loadとseedの競合および不存在ファイルを拒否させる; 2: 不正JSONを一時保存し拒否を確認する]
    #   引数: []
    #   戻り値: [None: 不正入力の受入やSystemExit以外の例外漏れは試験失敗]
    # }
    def test_cli_rejects_overrides_missing_files_and_malformed_json(self):
        # 利用者のファイルではなく、一時領域の不存在・壊れた入力だけを使う。
        with TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            for args in (["--load-input", str(path), "--seed", "1"], ["--load-input", str(path)]):
                with self.subTest(args=args), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    main(args)
            path.write_text("{", encoding="utf-8")
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--load-input", str(path)])

    # {
    #   責務: [test_cli_exports_inputs_and_full_events_without_overwriting: 調査レポートが再現入力と全ログを含み既存ファイルを保護することを確認する]
    #   処理: [1: 一時ファイルへ比較レポートを出力する; 2: 形式・復元可能な入力・両経路の全ログを照合する; 3: 標準出力の要約と再保存時の原本保持を確認する]
    #   引数: []
    #   戻り値: [None: ログ欠落・要約への全ログ混入・上書きは試験失敗]
    # }
    def test_cli_exports_inputs_and_full_events_without_overwriting(self):
        # 保存ファイルには全ログ、標準出力には要約という境界を実CLIで確認する。
        with TemporaryDirectory() as folder:
            path = Path(folder) / "全イベント.json"
            output = StringIO()
            args = ["--save-report", str(path), "--max-steps", "25", "--allow-partial"]
            with redirect_stdout(output):
                self.assertEqual(main(args), 0)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(report["format"], "kadocalcio.match-repro-report")
            self.assertEqual(report["version"], 1)
            restore_input_record(report["input"])
            comparison = report["comparison"]
            self.assertTrue(comparison["same_state"])
            self.assertIsNone(comparison["first_event_difference"])
            self.assertEqual(comparison["event_history"]["headless"], comparison["event_history"]["rendered"])
            self.assertEqual(comparison["event_history"]["headless"][0]["text"], "キックオフ！")
            self.assertNotIn("event_history", json.loads(output.getvalue()))
            # 調査レポートも排他的作成で、既存の証拠を壊さない。
            previous = path.read_bytes()
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(args)
            self.assertEqual(path.read_bytes(), previous)

    # {
    #   責務: [test_rejects_incompatible_envelope: 未対応形式・版・外部コマンド等を黙って復元しないことを確認する]
    #   処理: [1: 外枠の型・版・コマンド・teams・settingsを壊した例を列挙する; 2: 全例でValueErrorを要求する]
    #   引数: []
    #   戻り値: [None: 未対応入力の受入や不適切な例外は試験失敗]
    # }
    def test_rejects_incompatible_envelope(self):
        # boolの版番号や将来の操作列を、既知のv1として読み飛ばさせない。
        for record in (
            None,
            {},
            {**self.record(), "version": 2},
            {**self.record(), "version": True},
            {**self.record(), "commands": [{"step": 0, "command": "unknown"}]},
            {**self.record(), "teams": []},
            {**self.record(), "settings": []},
        ):
            with self.subTest(record=record), self.assertRaises(ValueError):
                restore_input_record(record)

    # {
    #   責務: [test_rejects_invalid_settings: 不正な型・範囲・非有限・巨大整数の設定を入力エラーとして拒否することを確認する]
    #   処理: [1: 設定項目ごとの不正値を列挙する; 2: 基準入力の一項目だけを置き換えValueErrorを要求する]
    #   引数: []
    #   戻り値: [None: 不正設定の受入やOverflowError等の例外漏れは試験失敗]
    # }
    def test_rejects_invalid_settings(self):
        # 巨大整数も通常の不正入力であり、float変換の内部例外へ漏らさない。
        invalid = (
            ("seed", True),
            ("seed", "1"),
            ("max_steps", 0),
            ("max_steps", 1.5),
            ("fixed_physics_dt", 0.1),
            ("venue_mode", "unknown"),
            ("ai_rethink_multiplier", None),
            ("ai_rethink_multiplier", True),
            ("ai_rethink_multiplier", float("nan")),
            ("ai_rethink_multiplier", 0.4),
            ("ai_rethink_multiplier", 3.1),
            ("ai_rethink_multiplier", 10**400),
            ("ai_rethink_multiplier", -(10**400)),
            ("ai_rethink_multiplier", float("inf")),
            ("ai_rethink_multiplier", -float("inf")),
        )
        for key, value in invalid:
            record = self.record()
            record["settings"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                restore_input_record(record)

    # {
    #   責務: [test_rejects_malformed_team_snapshots: チーム識別子・先発・RGBの必須形式を検査する]
    #   処理: [1: 両側のチーム非オブジェクトを拒否させる; 2: 必須文字列・先発配列・色の型と範囲を壊して拒否を確認する]
    #   引数: []
    #   戻り値: [None: 読込が不正スナップショットを受け入れると試験失敗]
    # }
    def test_rejects_malformed_team_snapshots(self):
        # 元データを変更せず、記録の一箇所だけを壊して原因を切り分ける。
        for side in ("home", "away"):
            record = self.record()
            record["teams"][side] = None
            with self.subTest(side=side), self.assertRaises(ValueError):
                restore_input_record(record)
        for key, value in (
            ("id", ""),
            ("name", 1),
            ("short", None),
            ("starters", []),
            ("primary", [1, 2]),
            ("secondary", "blue"),
            ("primary", [0, -1, 256]),
        ):
            record = self.record()
            record["teams"]["home"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                restore_input_record(record)

    # {
    #   責務: [test_cli_rejects_huge_multiplier_as_input_error: 保存入力の巨大倍率が内部例外でなくCLIの入力エラーになることを確認する]
    #   処理: [1: 正負の巨大倍率を持つ入力を一時保存する; 2: load入口で実行する; 3: 終了コード2と対象設定名の診断を確認する]
    #   引数: []
    #   戻り値: [None: OverflowError漏れ・誤った終了・診断欠落は試験失敗]
    # }
    def test_cli_rejects_huge_multiplier_as_input_error(self):
        # 新しい試験専用ファイルだけを使い、利用者の保存入力へ書き込まない。
        with TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            for multiplier in (10**400, -(10**400)):
                record = self.record()
                record["settings"]["ai_rethink_multiplier"] = multiplier
                path.write_text(json.dumps(record), encoding="utf-8")
                diagnostic = StringIO()
                with self.subTest(multiplier=multiplier), redirect_stderr(diagnostic):
                    with self.assertRaises(SystemExit) as raised:
                        main(["--load-input", str(path), "--allow-partial"])
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn("ai_rethink_multiplier", diagnostic.getvalue())

    # {
    #   責務: [test_accepts_multiplier_boundaries_without_coercion: 許可する倍率の両端と整数型を丸めず復元することを確認する]
    #   処理: [1: 下端・上端と整数の有効倍率を記録へ設定する; 2: 復元後の値と型を確認する]
    #   引数: []
    #   戻り値: [None: 有効入力の拒否や不要な型変換は試験失敗]
    # }
    def test_accepts_multiplier_boundaries_without_coercion(self):
        # 巨大値の拒否を直しても、有効値の比較や保存形式を変えない。
        for multiplier in (0.5, 3.0, 1, 3):
            record = self.record()
            record["settings"]["ai_rethink_multiplier"] = multiplier
            with self.subTest(multiplier=multiplier):
                _, _, settings = restore_input_record(record)
                self.assertEqual(settings["ai_rethink_multiplier"], multiplier)
                self.assertIs(type(settings["ai_rethink_multiplier"]), type(multiplier))


if __name__ == "__main__":
    unittest.main()
