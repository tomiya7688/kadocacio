"""Keep the reproduction CLI's save order, diagnostics and result contract stable."""

import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.tools.match_repro_check import main
from scripts.tools.match_repro_input import create_input_record


# {
#   責務: [MatchReproCliTests: 再現CLIのファイル保護・実行順・終了診断を外部境界から検査する]
#   フィールド: [record: 現行チーム探索に依存しない試験用の再現入力]
# }
class MatchReproCliTests(unittest.TestCase):
    # {
    #   責務: [setUp: CLI配線試験だけに使う最小の保存入力を準備する]
    #   処理: [1: 復元契約を満たす両チームと明示seedから記録を作る]
    #   引数: []
    #   戻り値: [None: recordを設定する。試合核の能力・物理検証には使わない]
    # }
    def setUp(self):
        # 比較本体は模擬するため、実チームファイルや利用者の保存値を読まない。
        self.record = create_input_record(
            {"id": "home", "name": "試験ホーム", "short": "試験H", "starters": [{}], "primary": [1, 2, 3]},
            {"id": "away", "name": "試験アウェー", "short": "試験A", "starters": [{}], "primary": [4, 5, 6]},
            seed=0, max_steps=3, venue_mode="NEUTRAL", ai_rethink_multiplier=0.5,
        )

    # {
    #   責務: [test_saves_input_before_comparison_and_retains_it_on_failure: 比較失敗時も開始条件を先に保存して残すことを確認する]
    #   処理: [1: 一時入力と保存先を用意する; 2: 比較開始時の保存済み入力を検査して例外を返す; 3: 入力エラーとレポート未作成を確認する]
    #   引数: []
    #   戻り値: [None: 保存順・診断・終了コードの相違は試験失敗]
    # }
    def test_saves_input_before_comparison_and_retains_it_on_failure(self):
        # 失敗後にも再実行条件を読めるよう、比較より前の保存順を固定する。
        with TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            saved_input = Path(folder) / "保存入力.json"
            saved_report = Path(folder) / "report.json"
            source.write_text(json.dumps(self.record), encoding="utf-8")

            # {
            #   責務: [fail_after_reading_input: 模擬比較の開始時に入力保存済みを検査して失敗させる]
            #   処理: [1: 保存値を原入力と照合する; 2: 比較処理のValueErrorを模擬する]
            #   引数: [home・away: 復元されたチーム; settings: 比較呼出しの設定]
            #   戻り値: [戻らずValueError: 診断経路の試験専用]
            # }
            def fail_after_reading_input(home, away, **settings):
                # 内部メソッド順ではなく、比較境界で見えるファイルを調べる。
                self.assertEqual(json.loads(saved_input.read_text(encoding="utf-8")), self.record)
                raise ValueError("comparison failed")

            diagnostic = StringIO()
            with patch("scripts.tools.match_repro_check.compare_matches", side_effect=fail_after_reading_input):
                with redirect_stderr(diagnostic), self.assertRaises(SystemExit) as raised:
                    main(["--load-input", str(source), "--save-input", str(saved_input),
                          "--save-report", str(saved_report)])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("comparison failed", diagnostic.getvalue())
            self.assertTrue(saved_input.is_file())
            self.assertFalse(saved_report.exists())

    # {
    #   責務: [test_saves_mismatch_report_before_returning_failure: 不一致でも全ログ付きレポートを保存し標準出力は要約にすることを確認する]
    #   処理: [1: 不一致の模擬結果を用意する; 2: 一時入力をCLIから読み比較レポートを保存する; 3: 保存形式・本文・要約・失敗コードを確認する]
    #   引数: []
    #   戻り値: [None: ログ欠落・保存値の変更・成功の誤認は試験失敗]
    # }
    def test_saves_mismatch_report_before_returning_failure(self):
        # 不一致を調査する出力を、失敗コードの判定より前に残す契約を守る。
        report = {"same_state": False, "fulltime": True,
                  "event_history": {"headless": [{"text": "得点"}], "rendered": []}}
        with TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            destination = Path(folder) / "report.json"
            source.write_text(json.dumps(self.record), encoding="utf-8")
            output = StringIO()
            with patch("scripts.tools.match_repro_check.compare_matches", return_value=report) as compare:
                with redirect_stdout(output):
                    result = main(["--load-input", str(source), "--save-report", str(destination), "--allow-partial"])
            self.assertEqual(result, 1)
            self.assertTrue(compare.call_args.kwargs["include_events"])
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {
                "format": "kadocalcio.match-repro-report", "version": 1,
                "input": self.record, "comparison": report,
            })
            self.assertEqual(json.loads(output.getvalue()), {"same_state": False, "fulltime": True})
            self.assertIn("得点", destination.read_text(encoding="utf-8"))
            self.assertEqual(report["event_history"]["headless"], [{"text": "得点"}])

    # {
    #   責務: [test_preserves_existing_outputs_and_reports_save_errors: 既存出力と存在しない親フォルダを保護して入力エラーを返すことを確認する]
    #   処理: [1: 試験専用の既存ファイルを準備する; 2: 入力・レポート保存先の衝突と親不存在を指定する; 3: 終了コード・比較開始有無・元バイトを照合する]
    #   引数: []
    #   戻り値: [None: 原本上書き・比較順の変更・例外漏れは試験失敗]
    # }
    def test_preserves_existing_outputs_and_reports_save_errors(self):
        # 調査ログの上書き拒否を、入力保存と結果保存の両経路で確かめる。
        with TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            existing = Path(folder) / "existing.json"
            source.write_text(json.dumps(self.record), encoding="utf-8")
            original = b"existing result\r\n"
            existing.write_bytes(original)
            cases = (("--save-input", existing, 0), ("--save-report", existing, 1),
                     ("--save-input", Path(folder) / "missing" / "input.json", 0))
            for flag, destination, comparisons in cases:
                with self.subTest(flag=flag, destination=destination):
                    with patch("scripts.tools.match_repro_check.compare_matches",
                               return_value={"same_state": True, "fulltime": True}) as compare:
                        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
                            main(["--load-input", str(source), flag, str(destination)])
                    self.assertEqual(raised.exception.code, 2)
                    self.assertEqual(compare.call_count, comparisons)
                    self.assertEqual(existing.read_bytes(), original)

    # {
    #   責務: [test_rejects_all_saved_input_overrides_before_loading: 保存入力の条件を各CLI指定で上書きできないことを確認する]
    #   処理: [1: 全ての競合オプションを個別に指定する; 2: 不存在入力でも読込前に競合エラーとなることを確認する]
    #   引数: []
    #   戻り値: [None: 条件の黙示上書きやファイル読込優先への退行は試験失敗]
    # }
    def test_rejects_all_saved_input_overrides_before_loading(self):
        # 競合の診断は実ファイルの状態に左右されないよう、読込より先に行う。
        cases = (("--home", "home"), ("--away", "away"), ("--seed", "0"),
                 ("--max-steps", "3"), ("--venue", "HOME"), ("--ai-rethink-multiplier", "1"))
        with TemporaryDirectory() as folder:
            missing = Path(folder) / "missing.json"
            for flag, value in cases:
                diagnostic = StringIO()
                with self.subTest(flag=flag), redirect_stderr(diagnostic):
                    with self.assertRaises(SystemExit) as raised:
                        main(["--load-input", str(missing), flag, value])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("cannot be combined", diagnostic.getvalue())

    # {
    #   責務: [test_loads_bom_input_and_forwards_recorded_settings: BOM付き日本語入力を復元し明示値を比較へ丸めず渡すことを確認する]
    #   処理: [1: 試験入力をUTF-8 BOM付きで保存する; 2: 描画間隔だけ変更して実行する; 3: チーム色・seed・試合条件・省略時の全ログ設定を確認する]
    #   引数: []
    #   戻り値: [None: 復元・引数伝達・成功判定が契約と異なると試験失敗]
    # }
    def test_loads_bom_input_and_forwards_recorded_settings(self):
        # BOM許可と色のtuple復元は、CLI分割後も保存入力の互換条件とする。
        with TemporaryDirectory() as folder:
            source = Path(folder) / "入力.json"
            source.write_text(json.dumps(self.record, ensure_ascii=False), encoding="utf-8-sig")
            with patch("scripts.tools.match_repro_check.compare_matches",
                       return_value={"same_state": True, "fulltime": True}) as compare:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["--load-input", str(source), "--render-every", "7"]), 0)
            self.assertEqual(compare.call_args.args[0]["primary"], (1, 2, 3))
            self.assertEqual(compare.call_args.args[1]["name"], "試験アウェー")
            self.assertEqual(compare.call_args.kwargs, {
                "seed": 0, "max_steps": 3, "venue_mode": "NEUTRAL", "ai_rethink_multiplier": 0.5,
                "render_every": 7, "include_events": False,
            })


if __name__ == "__main__":
    unittest.main()
