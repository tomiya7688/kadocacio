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
        self.assertEqual(context_pack.section(body, ("missing",)), "")

    def test_compact_marks_missing_and_truncates(self):
        self.assertIn("not explicitly stated", context_pack.compact(""))
        self.assertIn("truncated", context_pack.compact("x" * 2000, limit=10))
        self.assertEqual(context_pack.compact(" short "), "short")

    def test_instruction_field_stays_on_one_line(self):
        self.assertEqual(context_pack.instruction_field("first\n- second"), "first - second")
        self.assertEqual(context_pack.instruction_field(""), "(原Issueを確認)")
        self.assertIn("続きはtask.md", context_pack.instruction_field("x" * 400))

    def test_infer_routes_uses_issue_text(self):
        issue = {"title": "リーグ保存を修正", "body": "", "labels": []}
        source, tests = context_pack.infer_routes(issue)
        self.assertIn("scripts/league/", source)
        self.assertIn("tests/test_league_manager.py", tests)

    def test_infer_routes_falls_back_for_unknown_issue(self):
        source, tests = context_pack.infer_routes(
            {"title": "unclassified work", "body": "", "labels": []}
        )

        self.assertEqual(
            source,
            ["Use AGENTS.md code map and rg to locate the smallest working set."],
        )
        self.assertEqual(
            tests,
            ["Run matching targeted tests first; run broader checks before PR when required."],
        )

    def test_main_branch_does_not_route_to_match_from_embedded_ai(self):
        for title in ("main branch maintenance", "maintain branch", "OpenAI tooling"):
            with self.subTest(title=title):
                source, _ = context_pack.infer_routes({"title": title, "body": "", "labels": []})
                self.assertNotIn("scripts/match/", source)

        source, _ = context_pack.infer_routes({
            "title": "static analysis", "body": "maintain main branch", "labels": [],
        })
        self.assertIn("scripts/tools/", source)
        self.assertNotIn("scripts/match/", source)

    def test_ai_words_and_underscore_tokens_route_to_match(self):
        for title in ("AI decision", "ai evaluator", "ai_evaluator"):
            with self.subTest(title=title):
                source, _ = context_pack.infer_routes({"title": title, "body": "", "labels": []})
                self.assertIn("scripts/match/", source)

    def test_japanese_match_keyword_keeps_substring_matching(self):
        source, _ = context_pack.infer_routes({"title": "試合結果を修正", "body": "", "labels": []})
        self.assertIn("scripts/match/", source)

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

    def test_select_next_issue_rejects_empty_list(self):
        with self.assertRaisesRegex(RuntimeError, "No open Issues"):
            context_pack.select_next_issue([])

    def test_list_open_issues_rejects_unexpected_payload(self):
        with patch.object(context_pack, "run_command", return_value={"unexpected": True}):
            with self.assertRaisesRegex(ValueError, "unexpected payload"):
                context_pack.list_open_issues()

    def test_godot_routes_include_target_and_migration_map(self):
        source, tests = context_pack.infer_routes({"title": "Godot起動基盤", "body": "", "labels": []})
        self.assertIn("godot/", source)
        self.assertIn("doc/Godot移行.md", source)
        self.assertIn("godot/tests/", tests)

    def test_missing_task_policy_preserves_old_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = context_pack.load_task_policy(Path(tmp) / "missing.json")
        self.assertEqual({"preferred_labels": [], "excluded_labels": [], "urgent_labels": []}, policy)
        issues = [{"number": 1, "title": "[P2] old", "labels": []},
                  {"number": 2, "title": "[P0] new", "labels": [{"name": "godot-migration"}]}]
        self.assertEqual(2, context_pack.select_next_issue(issues, policy=policy)["number"])

    def test_task_policy_loads_optional_fields_and_normalizes_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text('{"preferred_labels": ["  Godot-Migration  "]}', encoding="utf-8-sig")
            policy = context_pack.load_task_policy(path)
        self.assertEqual({"preferred_labels": ["godot-migration"], "excluded_labels": [], "urgent_labels": []}, policy)

    def test_task_policy_rejects_invalid_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            for text in ('[]', '{"preferred_labels": "label"}', '{"excluded_labels": [""]}',
                         '{"urgent_labels": [1]}', '{"preferred_labels": [null]}'):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "task_selection.json"):
                        context_pack.load_task_policy(path)

    def test_migration_preferred_over_ordinary_backlog_but_p0_bugs_win(self):
        policy = {"preferred_labels": ["godot-migration"], "excluded_labels": ["tracking", "blocked", "in-review"],
                  "urgent_labels": ["bug"]}
        migration = {"number": 120, "title": "[P1] new", "labels": [{"name": "GODOT-MIGRATION"}]}
        refactor = {"number": 107, "title": "[P0] old refactor", "labels": []}
        bug = {"number": 121, "title": "[P0] save corruption", "labels": [{"name": "bug"}]}
        self.assertEqual(120, context_pack.select_next_issue([refactor, migration], policy=policy)["number"])
        self.assertEqual(121, context_pack.select_next_issue([refactor, migration, bug], policy=policy)["number"])
        bug["title"] = "[P1] small bug"
        self.assertEqual(120, context_pack.select_next_issue([refactor, migration, bug], policy=policy)["number"])

    def test_excluded_issues_never_selected_even_with_p0_and_preferred_labels(self):
        policy = {"preferred_labels": ["godot-migration"], "excluded_labels": ["tracking", "blocked", "in-review"],
                  "urgent_labels": ["bug"]}
        excluded = [{"number": index, "title": "[P0] urgent",
                     "labels": [{"name": label}, {"name": "bug"}, {"name": "godot-migration"}]}
                    for index, label in enumerate(("TRACKING", "blocked", "in-review"), 1)]
        ready = {"number": 120, "title": "[P1] ready", "labels": [{"name": "godot-migration"}]}
        self.assertEqual(120, context_pack.select_next_issue([*excluded, ready], policy=policy)["number"])
        with self.assertRaisesRegex(RuntimeError, "No runnable Issues"):
            context_pack.select_next_issue(excluded, policy=policy)

    def test_preferred_issues_still_sort_by_priority_then_number_without_mutation(self):
        policy = {"preferred_labels": ["godot-migration"], "excluded_labels": [], "urgent_labels": []}
        issues = [{"number": number, "title": priority, "labels": [{"name": "godot-migration"}]}
                  for number, priority in ((10, "[P2] old"), (30, "[P1] new"), (20, "[P1] first"))]
        original = repr(issues)
        self.assertEqual(20, context_pack.select_next_issue(issues, policy=policy)["number"])
        self.assertEqual(original, repr(issues))

    def test_resolve_issue_number_keeps_explicit_choice(self):
        with patch.object(context_pack, "list_open_issues") as issue_list:
            self.assertEqual(56, context_pack.resolve_issue_number(56))
        issue_list.assert_not_called()

    def test_resolve_issue_number_selects_implicit_choice(self):
        issues = [
            {"number": 30, "title": "[P2] later", "labels": []},
            {"number": 12, "title": "[P0] first", "labels": []},
        ]
        with patch.object(context_pack, "list_open_issues", return_value=issues):
            self.assertEqual(12, context_pack.resolve_issue_number(None))

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
            request = (output / "request.md").read_text(encoding="utf-8")
            for heading in ("対象:", "目的:", "制約:", "読むべきファイル:", "完了条件:"):
                self.assertIn(heading, request)
            self.assertIn("#999 Context test", request)
            self.assertIn("Small goal", request)
            self.assertIn("Pass tests", request)
            self.assertIn("CONTEXT.md", request)
            self.assertEqual(sum(line.startswith("- ") for line in request.splitlines()), 5)
            validation = (output / "validation.md").read_text(encoding="utf-8")
            self.assertIn("UNVERIFIED", validation)


if __name__ == "__main__":
    unittest.main()
