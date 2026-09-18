"""Safely finish a local development task from checks through pull request creation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
PROTECTED_BRANCHES = {"main", "master"}


def run_command(command: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=ROOT,
        check=False,
        text=True,
        encoding="utf-8",
        capture_output=capture,
    )


def require_success(command: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    completed = run_command(command, capture=capture)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}{suffix}")
    return completed


def git_output(*args: str) -> str:
    return require_success(("git", *args), capture=True).stdout.strip()


def current_branch() -> str:
    branch = git_output("branch", "--show-current")
    if not branch:
        raise RuntimeError("detached HEAD is not supported by the finalize workflow")
    return branch


def print_change_summary() -> None:
    status = git_output("status", "--short")
    diff = git_output("diff", "--stat")
    staged = git_output("diff", "--cached", "--stat")
    print("== repository state ==")
    print(status or "(working tree clean)")
    if diff:
        print("\nunstaged diff:")
        print(diff)
    if staged:
        print("\nstaged diff:")
        print(staged)


def run_repository_checks() -> None:
    print("\n== repository checks ==")
    completed = run_command(
        (sys.executable, "-m", "scripts.tools.static_analysis.run_all")
    )
    if completed.returncode:
        raise RuntimeError(f"repository checks failed with exit code {completed.returncode}")


def resolve_commit_message(message: str | None, issue: int | None) -> str:
    if message and message.strip():
        return message.strip()
    if issue is not None:
        return f"Complete issue #{issue}"
    raise RuntimeError("--message is required when --issue is not supplied")


def resolve_work_branch(
    current: str,
    *,
    requested: str | None,
    issue: int | None,
) -> str:
    if current not in PROTECTED_BRANCHES:
        if requested and requested != current:
            raise RuntimeError(
                f"already on {current}; refusing to switch automatically to {requested}"
            )
        return current

    target = (requested or (f"issue-{issue}-work" if issue is not None else "")).strip()
    if not target:
        raise RuntimeError(
            "commit/pr mode cannot run on main/master; supply --branch or --issue"
        )
    if target in PROTECTED_BRANCHES:
        raise RuntimeError(f"refusing to use protected branch: {target}")
    require_success(("git", "switch", "-c", target))
    return target


def stage_changes() -> None:
    require_success(("git", "add", "--all"))
    staged = run_command(("git", "diff", "--cached", "--quiet"))
    if staged.returncode == 0:
        raise RuntimeError("no changes are staged after git add --all")
    if staged.returncode != 1:
        raise RuntimeError(
            f"unable to inspect staged changes (git diff exit {staged.returncode})"
        )


def build_pr_body(issue: int | None) -> str:
    body = (
        "## Verification\n"
        "- `run_dev_finalize.bat check`: pass\n"
    )
    if issue is not None:
        body += f"\nCloses #{issue}\n"
    return body


def create_pull_request(
    *,
    branch: str,
    base: str,
    title: str,
    body: str,
    remote: str,
) -> str:
    require_success(("gh", "--version"), capture=True)
    require_success(("git", "push", "-u", remote, branch))
    completed = require_success(
        (
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ),
        capture=True,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else "(PR created; URL not returned)"


def finalize(args: argparse.Namespace) -> int:
    print_change_summary()
    starting_branch = current_branch()
    run_repository_checks()

    if args.mode == "check":
        print("\nDEV FINALIZE: PASS")
        print(f"Mode: check\nBranch: {starting_branch}")
        return 0

    branch = resolve_work_branch(
        starting_branch,
        requested=args.branch,
        issue=args.issue,
    )
    message = resolve_commit_message(args.message, args.issue)
    stage_changes()
    require_success(("git", "commit", "-m", message))
    commit_sha = git_output("rev-parse", "HEAD")

    pr_url = ""
    if args.mode == "pr":
        title = (args.title or message).strip()
        body = args.body if args.body is not None else build_pr_body(args.issue)
        pr_url = create_pull_request(
            branch=branch,
            base=args.base,
            title=title,
            body=body,
            remote=args.remote,
        )

    print("\nDEV FINALIZE: PASS")
    print(f"Mode: {args.mode}")
    print(f"Branch: {branch}")
    print(f"Commit: {commit_sha}")
    if pr_url:
        print(f"PR: {pr_url}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("check", "commit", "pr"),
        default="check",
        help="check only, commit locally, or commit/push/create a PR",
    )
    parser.add_argument("--issue", type=int, help="related GitHub Issue number")
    parser.add_argument("--branch", help="branch to create when currently on main/master")
    parser.add_argument("--message", help="commit message; defaults to 'Complete issue #N'")
    parser.add_argument("--title", help="PR title; defaults to commit message")
    parser.add_argument("--body", help="PR body; defaults to verification + Closes #N")
    parser.add_argument("--base", default="main", help="PR base branch")
    parser.add_argument("--remote", default="origin", help="git remote used for push")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return finalize(parse_args(argv))
    except (RuntimeError, OSError) as exc:
        print(f"DEV FINALIZE: FAIL\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
