from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.tools import context_pack


# {
#   責務: [ContextPackTests: Issueの作業選択・対象ファイル推定・小さな作業資料の生成契約を検査する]
#   フィールド: []
# }
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
        self.assertEqual(2, context_pack.issue_priority({"title": "normal", "labels": []}))
        self.assertEqual(4, context_pack.issue_priority({"title": "[p4] future", "labels": []}))

    def test_priority_label_overrides_stale_title_and_ignores_token_fragments(self):
        self.assertEqual(2, context_pack.issue_priority({"title": "[P0] stale", "labels": [{"name": "p2"}]}))
        self.assertEqual(1, context_pack.issue_priority({"title": "[P3] stale", "labels": [{"name": "P4"}, {"name": "P1"}]}))
        for title in ("P40 proposal", "AP0 embedded", "P1X embedded", "unclassified"):
            with self.subTest(title=title):
                self.assertEqual(2, context_pack.issue_priority({"title": title, "labels": []}))

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

    # {
    #   責務: [test_godot_routes_include_target_and_migration_map: Godot作業が移行先と移行計画・検証入口へ案内されることを確認する]
    #   処理: [1: Godot起動基盤を示すIssueを作る; 2: 対象推定を実行; 3: ソースと検証入口の三つの必須経路を照合]
    #   引数: []
    #   戻り値: [None: 案内経路の欠落はassertion失敗。GitHubや実ファイルへ書き込まない]
    # }
    def test_godot_routes_include_target_and_migration_map(self):
        source, tests = context_pack.infer_routes({"title": "Godot起動基盤", "body": "", "labels": []})
        self.assertIn("godot/", source)
        self.assertIn("doc/Godot移行.md", source)
        self.assertIn("godot/tests/", tests)

    # {
    #   責務: [test_missing_task_policy_preserves_old_priority_order: 設定なしの環境でも従来の優先度順で作業を選べることを確認する]
    #   処理: [1: 一時フォルダ内の不存在パスを指定; 2: 全設定が空配列に戻ることを確認; 3: カテゴリより既存の優先度が選択を決めることを照合]
    #   引数: []
    #   戻り値: [None: 不在設定の互換動作が変わるとassertion失敗。一時フォルダは終了時に片付ける]
    # }
    def test_missing_task_policy_preserves_old_priority_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = context_pack.load_task_policy(Path(tmp) / "missing.json")
        self.assertEqual({"preferred_labels": [], "excluded_labels": [], "urgent_labels": []}, policy)
        issues = [{"number": 1, "title": "[P2] old", "labels": []},
                  {"number": 2, "title": "[P0] new", "labels": [{"name": "godot-migration"}]}]
        self.assertEqual(2, context_pack.select_next_issue(issues, policy=policy)["number"])

    # {
    #   責務: [test_task_policy_loads_optional_fields_and_normalizes_labels: 任意項目の省略・BOM付きJSON・ラベルの表記ゆれを同時に検査する]
    #   処理: [1: 一時JSONへ空白・大小文字を含む優先ラベルだけを保存; 2: 読込結果を取得; 3: 正規化済み値と未指定項目の空配列を照合]
    #   引数: []
    #   戻り値: [None: 正規化または省略項目の既定値が異なるとassertion失敗。実際の設定ファイルは使わない]
    # }
    def test_task_policy_loads_optional_fields_and_normalizes_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text('{"preferred_labels": ["  Godot-Migration  "]}', encoding="utf-8-sig")
            policy = context_pack.load_task_policy(path)
        self.assertEqual({"preferred_labels": ["godot-migration"], "excluded_labels": [], "urgent_labels": []}, policy)

    # {
    #   責務: [test_task_policy_rejects_invalid_structures: 不正な設定を作業選択へ黙って受け入れないことを確認する]
    #   処理: [1: 一時JSONへ非オブジェクト・非配列・空ラベル・数値・nullの各例を保存; 2: 各例の読込で設定名を含むValueErrorを要求]
    #   引数: []
    #   戻り値: [None: 不正設定の受入または説明不足はassertion失敗。一時データだけを更新する]
    # }
    def test_task_policy_rejects_invalid_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            for text in ('[]', '{"preferred_labels": "label"}', '{"excluded_labels": [""]}',
                         '{"urgent_labels": [1]}', '{"preferred_labels": [null]}'):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "task_selection.json"):
                        context_pack.load_task_policy(path)

    # {
    #   責務: [test_p0_is_urgent_regardless_of_bug_label_and_migration_breaks_p1_ties: P0の無条件優先とP1同順位内の移行優先を確認する]
    #   処理: [1: 移行・通常作業・緊急候補を作る; 2: 同じP1では移行が先と照合; 3: P0 bugを優先しP1に戻すと移行が先になることを確認; 4: bugラベルの無いP0も最優先と照合]
    #   引数: []
    #   戻り値: [None: P0の条件付き優先や同順位内の逆転はassertion失敗。候補の変更は試験内だけ]
    # }
    def test_p0_is_urgent_regardless_of_bug_label_and_migration_breaks_p1_ties(self):
        policy = {"preferred_labels": ["godot-migration"], "excluded_labels": ["tracking", "blocked", "in-review"],
                  "urgent_labels": ["bug"]}
        migration = {"number": 120, "title": "[P1] new", "labels": [{"name": "GODOT-MIGRATION"}]}
        refactor = {"number": 107, "title": "[P1] refactor", "labels": []}
        bug = {"number": 121, "title": "[P0] save corruption", "labels": [{"name": "bug"}]}
        self.assertEqual(120, context_pack.select_next_issue([refactor, migration], policy=policy)["number"])
        self.assertEqual(121, context_pack.select_next_issue([refactor, migration, bug], policy=policy)["number"])
        bug["title"] = "[P1] small bug"
        self.assertEqual(120, context_pack.select_next_issue([refactor, migration, bug], policy=policy)["number"])
        emergency = {"number": 200, "title": "[P0] urgent recovery", "labels": []}
        self.assertEqual(200, context_pack.select_next_issue([refactor, migration, bug, emergency], policy=policy)["number"])

    def test_low_priority_migration_cannot_leapfrog_higher_priority_work(self):
        policy = {"preferred_labels": ["godot-migration"], "excluded_labels": []}
        migration = {"number": 1, "title": "[P4] future migration", "labels": [{"name": "godot-migration"}]}
        ordinary = {"number": 2, "title": "[P1] priority", "labels": []}
        self.assertEqual(2, context_pack.select_next_issue([migration, ordinary], policy=policy)["number"])
        ordinary["title"] = "unclassified"
        self.assertEqual(2, context_pack.select_next_issue([migration, ordinary], policy=policy)["number"])
        ordinary["title"] = "[P3] deferred"
        self.assertEqual(2, context_pack.select_next_issue([migration, ordinary], policy=policy)["number"])

    # {
    #   責務: [test_excluded_issues_never_selected_even_with_p0_and_preferred_labels: 緊急・優先ラベルが除外状態を無視しないことを確認する]
    #   処理: [1: tracking・blocked・in-reviewの各候補にP0と優先ラベルを重ねる; 2: 着手可能な候補だけが選ばれることを照合; 3: 全候補が除外ならRuntimeErrorを要求]
    #   引数: []
    #   戻り値: [None: 除外候補の選択または無候補の見逃しはassertion失敗。外部Issueのラベルは変更しない]
    # }
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

    # {
    #   責務: [test_preferred_issues_still_sort_by_priority_then_number_without_mutation: 同じ優先カテゴリ内の優先度・番号順と入力不変性を検査する]
    #   処理: [1: 異なる優先度と番号を持つ移行候補を作って入力表現を保存; 2: P1の最小番号が選ばれることを照合; 3: 一覧や候補の内容が変わらないことを確認]
    #   引数: []
    #   戻り値: [None: 選択順の逆転または入力の書換はassertion失敗]
    # }
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
