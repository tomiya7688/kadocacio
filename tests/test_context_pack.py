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

    def test_priority_accepts_title_prefix_and_label(self):
        self.assertEqual(0, context_pack.issue_priority({"title": "[P0] urgent", "labels": []}))
        self.assertEqual(1, context_pack.issue_priority({"title": "normal", "labels": [{"name": "P1"}]}))
        self.assertEqual(4, context_pack.issue_priority({"title": "normal", "labels": []}))

    def test_select_next_issue_prefers_priority_then_issue_number(self):
        issues = [
            {"number": 20, "title": "[P2] later", "labels": []},
            {"number": 11, "title": "[P1] older", "labels": []},
            {"number": 12, "title": "[P1] newer", "labels": []},
            {"number": 1, "title": "unprioritized", "labels": []},
        ]
        self.assertEqual(11, context_pack.select_next_issue(issues)["number"])

    def test_resolve_issue_number_keeps_explicit_choice(self):
        with patch.object(context_pack, "list_open_issues") as issue_list:
            self.assertEqual(56, context_pack.resolve_issue_number(56))
        issue_list.assert_not_called()

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
