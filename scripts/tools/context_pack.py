from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ROUTES = [
    (("godot", "gdscript"), ["godot/", "doc/Godot移行.md"], ["godot/tests/"]),
    (("match", "試合", "pass", "shoot", "goal", "ai"), ["scripts/match/"], ["tests/"]),
    (("league", "リーグ", "tournament"), ["scripts/league/"], ["tests/test_league_manager.py"]),
    (("team", "チーム", "uniform", "ユニフォーム"), ["scripts/team/", "teams/"], ["tests/test_uniforms.py", "tests/test_team_file_organization.py"]),
    (("render", "描画", "ui", "画面"), ["scripts/app/"], ["tests/test_rendering_smoke.py"]),
    (("static", "解析", "context", "コンテキスト", "codex"), ["scripts/tools/static_analysis/", "scripts/tools/"], ["tests/"]),
]

PRIORITY_ORDER = ("P0", "P1", "P2", "P3")


def run_command(command: list[str]) -> object:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def run_gh(issue_number: int) -> dict:
    return run_command([
        "gh", "issue", "view", str(issue_number),
        "--json", "number,title,url,body,labels,state",
    ])


def list_open_issues() -> list[dict]:
    payload = run_command([
        "gh", "issue", "list",
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,url,labels",
    ])
    if not isinstance(payload, list):
        raise ValueError("gh issue list returned an unexpected payload")
    return payload


def issue_priority(issue: dict) -> int:
    title = str(issue.get("title", ""))
    labels = [str(label.get("name", "")) for label in issue.get("labels", [])]
    searchable = " ".join([title, *labels]).upper()
    for rank, priority in enumerate(PRIORITY_ORDER):
        if re.search(rf"(?:^|[^A-Z0-9]){priority}(?:[^A-Z0-9]|$)", searchable):
            return rank
    return len(PRIORITY_ORDER)


def load_task_policy(path: Path | None = None) -> dict[str, list[str]]:
    """Read the editable task policy; an absent file retains priority-only selection."""
    path = path or ROOT / "task_selection.json"
    fields = ("preferred_labels", "excluded_labels", "urgent_labels")
    if not path.exists():
        return {field: [] for field in fields}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("task_selection.json must contain an object")
    policy = {}
    for field in fields:
        values = payload.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"task_selection.json {field} must contain nonempty label strings")
        policy[field] = [value.strip().casefold() for value in values]
    return policy


def issue_labels(issue: dict) -> set[str]:
    return {str(label.get("name", "")).casefold() for label in issue.get("labels", [])}


def selection_key(issue: dict, policy: dict[str, list[str]]) -> tuple[int, int, int]:
    """P0 bugs first, preferred work next, then the existing priority/number order."""
    labels = issue_labels(issue)
    priority = issue_priority(issue)
    group = (0 if priority == 0 and labels.intersection(policy["urgent_labels"])
             else 1 if labels.intersection(policy["preferred_labels"]) else 2)
    return group, priority, int(issue.get("number", 1_000_000_000))


def select_next_issue(issues: list[dict], *, policy: dict[str, list[str]] | None = None) -> dict:
    if not issues:
        raise RuntimeError("No open Issues were found.")
    policy = load_task_policy() if policy is None else policy
    candidates = [issue for issue in issues if not issue_labels(issue).intersection(policy["excluded_labels"])]
    if not candidates:
        raise RuntimeError("No runnable Issues: remaining work is tracking, blocked or in review.")
    return min(candidates, key=lambda issue: selection_key(issue, policy))


def section(body: str, names: tuple[str, ...]) -> str:
    lines = body.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match and any(name.lower() in match.group(1).lower() for name in names):
            start = index + 1
            break
    if start is None:
        return ""
    result: list[str] = []
    for line in lines[start:]:
        if re.match(r"^#{1,6}\s+", line):
            break
        result.append(line)
    return "\n".join(result).strip()


def compact(text: str, limit: int = 1800) -> str:
    text = text.strip()
    if not text:
        return "(not explicitly stated; read the source Issue if needed)"
    return text if len(text) <= limit else text[:limit].rstrip() + "\n… (truncated; see source Issue)"


def instruction_field(text: str, limit: int = 360) -> str:
    """Keep one work-request field on one line even for Markdown lists."""
    value = " ".join(text.split())
    if not value:
        return "(原Issueを確認)"
    return value if len(value) <= limit else value[:limit].rstrip() + "… (続きはtask.md)"


def keyword_matches(haystack: str, keyword: str) -> bool:
    """Match English route words as tokens and Japanese route words in text."""
    if keyword.isascii():
        pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])"
        return re.search(pattern, haystack, flags=re.IGNORECASE) is not None
    return keyword in haystack


def infer_routes(issue: dict) -> tuple[list[str], list[str]]:
    labels = " ".join(label.get("name", "") for label in issue.get("labels", []))
    haystack = f"{issue.get('title', '')} {labels} {issue.get('body', '')}".lower()
    source: list[str] = []
    tests: list[str] = []
    for keywords, source_items, test_items in ROUTES:
        if any(keyword_matches(haystack, keyword) for keyword in keywords):
            source.extend(source_items)
            tests.extend(test_items)
    if not source:
        source = ["Use AGENTS.md code map and rg to locate the smallest working set."]
    if not tests:
        tests = ["Run matching targeted tests first; run broader checks before PR when required."]
    return list(dict.fromkeys(source)), list(dict.fromkeys(tests))


def write_pack(issue: dict) -> Path:
    issue_number = issue["number"]
    output = ROOT / "context" / str(issue_number)
    output.mkdir(parents=True, exist_ok=True)

    body = issue.get("body") or ""
    goal = section(body, ("目的", "goal", "summary"))
    required = section(body, ("方針", "制約", "required", "requirements"))
    acceptance = section(body, ("完了条件", "acceptance", "done"))
    deferred = section(body, ("対象外", "deferred", "out of scope"))
    source, tests = infer_routes(issue)

    labels = ", ".join(label.get("name", "") for label in issue.get("labels", [])) or "(none)"
    task = f"""# Task Capsule: #{issue_number} {issue['title']}

Source: {issue['url']}
State: {issue.get('state', 'unknown')}
Labels: {labels}

## Goal
{compact(goal)}

## Required
{compact(required)}

## Acceptance
{compact(acceptance)}

## Deferred / Out of Scope
{compact(deferred)}

## Working Set
See `files.txt`. Read source/tests before broad docs. Expand only when a concrete unknown requires it.

## Exploration Stop
Stop broad exploration when Goal / Required / Acceptance / Working set are sufficient. Reopen exploration only for a concrete missing constraint, contradiction, failure cause, or required validation.

## Source of Truth
This capsule is an index, not the specification. Return to the source Issue, implementation, tests, AGENTS.md, README/SPEC as needed.
"""
    (output / "task.md").write_text(task, encoding="utf-8")
    (output / "files.txt").write_text("[source candidates]\n" + "\n".join(source) + "\n\n[test candidates]\n" + "\n".join(tests) + "\n", encoding="utf-8")
    request = f"""# Codex Work Request: #{issue_number}

- 対象: #{issue_number} {issue['title']} ({issue['url']})
- 目的: {instruction_field(goal)}
- 制約: {instruction_field(required)}
- 読むべきファイル: `files.txt` の候補と該当フォルダの `CONTEXT.md`。不足時だけ原Issueと実装を確認。
- 完了条件: {instruction_field(acceptance)}

詳細は `task.md`、最新の作業状態はIssueとGitで確認する。候補ファイルは推定であり、正本ではない。
"""
    (output / "request.md").write_text(request, encoding="utf-8")
    (output / "validation.md").write_text(
        "# Validation\n\n"
        "- VERIFIED: add checks actually run\n"
        "- UNVERIFIED: checks not required for current Acceptance\n"
        "- BLOCKED: required checks that could not run\n"
        "- NOT_APPLICABLE: irrelevant checks\n\n"
        "Do not expand validation only to make UNVERIFIED empty.\n",
        encoding="utf-8",
    )
    return output


def resolve_issue_number(explicit_issue: int | None) -> int:
    if explicit_issue is not None:
        return explicit_issue
    selected = select_next_issue(list_open_issues())
    number = int(selected["number"])
    print(f"Selected #{number}: {selected['title']}")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a compact context pack from a GitHub Issue")
    parser.add_argument("issue", type=int, nargs="?", help="Issue number; omit to select the highest-priority open Issue")
    args = parser.parse_args()
    issue_number = resolve_issue_number(args.issue)
    issue = run_gh(issue_number)
    print(f"Task #{issue['number']}: {issue['title']}")
    print(issue["url"])
    output = write_pack(issue)
    print(f"Context pack: {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
