from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.tools import context_pack


class ContextPackTests(unittest.TestCase):
    def test_section_extracts_matching_heading(self):
        body = "# A\ntext\n## 目的\nGoal text\n## 完了条件\nDone"
        self.assertEqual(context_pack.section(body, ("目的",)), "Goal text")
        self.assertEqual(context_pack.section(body, ("完了条件",)), "Done")

    def test_compact_marks_missing_and_truncates(self):
        self.assertIn("not explicitly stated", context_pack.compact(""))
        self.assertIn("truncated", context_pack.compact("x" * 2000, limit=10))

    def test_infer_routes_uses_issue_text(self):
        issue = {"title": "リーグ保存を修正", "body": "", "labels": []}
        source, tests = context_pack.infer_routes(issue)
        self.assertIn("scripts/league/", source)
        self.assertIn("tests/test_league_manager.py", tests)

    def test_write_pack_creates_compact_files(self):
        issue = {
            "number": 999,
            "title": "Context test",
            "url": "https://example.invalid/issues/999",
            "state": "OPEN",
            "labels": [{"name": "context"}],
            "body": "## 目的\nSmall goal\n## 完了条件\nPass tests",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(context_pack, "ROOT", root):
                output = context_pack.write_pack(issue)
            self.assertTrue((output / "task.md").exists())
            self.assertTrue((output / "files.txt").exists())
            validation = (output / "validation.md").read_text(encoding="utf-8")
            self.assertIn("UNVERIFIED", validation)


if __name__ == "__main__":
    unittest.main()
