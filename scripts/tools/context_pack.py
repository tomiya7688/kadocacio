from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ROUTES = [
    (("match", "試合", "pass", "shoot", "goal", "ai"), ["scripts/match/"], ["tests/"]),
    (("league", "リーグ", "tournament"), ["scripts/league/"], ["tests/test_league_manager.py"]),
    (("team", "チーム", "uniform", "ユニフォーム"), ["scripts/team/", "teams/"], ["tests/test_uniforms.py", "tests/test_team_file_organization.py"]),
    (("render", "描画", "ui", "画面"), ["scripts/app/"], ["tests/test_rendering_smoke.py"]),
    (("static", "解析", "context", "コンテキスト", "codex"), ["scripts/tools/static_analysis/", "scripts/tools/"], ["tests/"]),
]


def run_gh(issue_number: int) -> dict:
    command = [
        "gh", "issue", "view", str(issue_number),
        "--json", "number,title,url,body,labels,state",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(completed.stdout)


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


def infer_routes(issue: dict) -> tuple[list[str], list[str]]:
    labels = " ".join(label.get("name", "") for label in issue.get("labels", []))
    haystack = f"{issue.get('title', '')} {labels} {issue.get('body', '')}".lower()
    source: list[str] = []
    tests: list[str] = []
    for keywords, source_items, test_items in ROUTES:
        if any(keyword.lower() in haystack for keyword in keywords):
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a compact context pack from a GitHub Issue")
    parser.add_argument("issue", type=int)
    args = parser.parse_args()
    output = write_pack(run_gh(args.issue))
    print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
