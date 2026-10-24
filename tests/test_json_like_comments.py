"""Declaration-only, language-aware checks; prose quality remains a review task."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.tools.static_analysis import json_like_comments as comments

CLASS_COMMENT = "# {\n#   責務: [Sample: 状態を保持]\n#   フィールド: [value: 状態]\n# }\n"
FUNCTION_COMMENT = "# {\n#   責務: [run: 状態を読み取る]\n#   処理: [1: 状態を返す]\n#   引数: []\n#   戻り値: [int: 状態値]\n# }\n"


# {
#   責務: [JsonLikeCommentsTests: PythonとGDScriptの宣言抽出・隣接コメント・差分検査・CLIを検査する]
#   フィールド: []
# }
class JsonLikeCommentsTests(unittest.TestCase):
    # {
    #   責務: [test_python_decorators_nested_declarations_and_changed_scope: 宣言の所属とデコレータ前の説明を維持して変更だけ検査する]
    #   処理: [1: クラスと入れ子関数の修飾名を確認; 2: デコレータ前の正常説明を確認; 3: 不変宣言を差分対象から除外]
    #   引数: []
    #   戻り値: [None: 宣言抽出と差分件数を照合]
    # }
    def test_python_decorators_nested_declarations_and_changed_scope(self):
        source = CLASS_COMMENT + "@decorator\nclass Sample:\n" + "\n".join("    " + line for line in FUNCTION_COMMENT.splitlines()) + "\n    @staticmethod\n    def run():\n        return 1\n"
        self.assertEqual(comments.audit_source("sample.py", source)["violations"], [])
        self.assertEqual(comments.audit_source("sample.py", source, source)["checked"], 0)
        changed = source.replace("return 1", "return 2")
        self.assertEqual(comments.audit_source("sample.py", changed, source)["checked"], 2)
        nested = "async def outer():\n    def inner():\n        pass\n    return inner\n"
        self.assertEqual(set(comments.python_declarations(nested)), {"outer", "outer.inner"})

    # {
    #   責務: [test_gdscript_script_class_function_ranges_and_hash_in_strings: GDScriptの関数境界と文字列内のハッシュを正しく扱う]
    #   処理: [1: 明示クラスとstatic関数の正常説明を検査; 2: extendsスクリプトクラスを検査; 3: コメントと実処理の変更を区別]
    #   引数: []
    #   戻り値: [None: 宣言範囲とコード比較を照合]
    # }
    def test_gdscript_script_class_function_ranges_and_hash_in_strings(self):
        source = CLASS_COMMENT + "class_name Sample\nextends RefCounted\n" + FUNCTION_COMMENT + 'static func run() -> String:\n\treturn "#not a comment" # trailing\n\nvar value: int = 1\n'
        self.assertEqual(comments.audit_source("sample.gd", source)["violations"], [])
        changed_comment = source.replace("# trailing", "# explanation")
        self.assertEqual(comments.audit_source("sample.gd", changed_comment, source)["checked"], 0)
        changed_field = source.replace("var value: int = 1", "var value: int = 2")
        self.assertEqual(comments.audit_source("sample.gd", changed_field, source)["checked"], 1)
        script = CLASS_COMMENT + "extends SceneTree\n" + FUNCTION_COMMENT + "func run():\n\tpass\n"
        self.assertEqual(comments.audit_source("script.gd", script)["violations"], [])
        self.assertEqual(comments.gdscript_declarations("# no declarations\n"), {})

    # {
    #   責務: [test_missing_structure_empty_explanations_and_unrelated_comments: 空テンプレートや離れたコメントを正常説明として受理しない]
    #   処理: [1: 非構造コメントと空責務を拒否; 2: 許される空引数・空フィールドを確認; 3: 宣言と離れたブロックを拒否]
    #   引数: []
    #   戻り値: [None: 最低構造の拒否と受理を照合]
    # }
    def test_missing_structure_empty_explanations_and_unrelated_comments(self):
        self.assertIn("構造ブロック", comments.missing_sections("docstring only", "function"))
        empty = FUNCTION_COMMENT.replace("run: 状態を読み取る", "")
        self.assertIn("責務", comments.audit_source("empty.py", empty + "def run():\n    pass\n")["violations"][0]["missing"])
        empty_fields = CLASS_COMMENT.replace("value: 状態", "") + "class Sample:\n    pass\n"
        self.assertEqual(comments.audit_source("empty.py", empty_fields)["violations"], [])
        source = FUNCTION_COMMENT + "value = 1\ndef run():\n    return value\n"
        self.assertIn("構造ブロック", comments.audit_source("separated.py", source)["violations"][0]["missing"])

    # {
    #   責務: [test_revision_audit_reads_only_changed_sources_and_handles_added_files: PR差分検査が依存の不変宣言や非ソースを除外する]
    #   処理: [1: 模擬Gitの変更一覧とソースを与える; 2: 追加ファイルの基準不在を処理; 3: 集約数と欠落位置を照合]
    #   引数: []
    #   戻り値: [None: 差分対象と読取失敗の処理を検証]
    # }
    def test_revision_audit_reads_only_changed_sources_and_handles_added_files(self):
        valid = FUNCTION_COMMENT + "def run():\n    return 1\n"
        with patch.object(comments, "git_text", side_effect=["added.py\0notes.md\0", valid, subprocess.CalledProcessError(128, "git")]):
            self.assertEqual(comments.audit_revisions("base", "head")["checked"], 1)
        with patch.object(comments, "git_text", side_effect=["changed.py\0", "def run():\n    return 2\n", valid]):
            report = comments.audit_revisions("base", "head")
            self.assertEqual(report["violations"][0]["declaration"], "run")
        with patch.object(comments.subprocess, "check_output", return_value=b"result") as read:
            self.assertEqual(comments.git_text("status", "--short"), "result")
            self.assertEqual(read.call_args.args[0], ["git", "status", "--short"])

    # {
    #   責務: [test_cli_success_failure_json_output_and_invalid_targets: CLIの構造検査結果と入力・読込失敗を区別する]
    #   処理: [1: 一時ソースの正常と欠落を検査; 2: 任意JSON保存を確認; 3: 排他的引数・構文・入出力の失敗を確認]
    #   引数: []
    #   戻り値: [None: 各経路の終了コードを照合]
    # }
    def test_cli_success_failure_json_output_and_invalid_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.py"
            source.write_text(FUNCTION_COMMENT + "def run():\n    return 1\n", encoding="utf-8")
            report = Path(directory) / "logs/audit.json"
            self.assertEqual(comments.main([str(source), "--output", str(report)]), 0)
            self.assertTrue(report.is_file())
            source.write_text("def run():\n    pass\n", encoding="utf-8")
            self.assertEqual(comments.main([str(source)]), 1)
            source.write_text("invalid (", encoding="utf-8")
            self.assertEqual(comments.main([str(source)]), 2)
            self.assertEqual(comments.main([str(source.with_suffix('.txt'))]), 2)
            self.assertEqual(comments.main([str(source.with_name('absent.py'))]), 2)
            for args in ([], [str(source), "--base", "main"]):
                with self.assertRaises(SystemExit):
                    comments.main(args)
        with patch.object(comments, "audit_revisions", return_value={"checked": 0, "violations": []}):
            self.assertEqual(comments.main(["--base", "base", "--head", "head"]), 0)
        with patch.object(comments, "audit_revisions", side_effect=subprocess.CalledProcessError(128, "git")):
            self.assertEqual(comments.main(["--base", "missing"]), 2)


if __name__ == "__main__":
    unittest.main()
