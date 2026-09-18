from __future__ import annotations

import argparse
import subprocess

import pytest

from scripts.tools import git_workflow


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_parse_args_defaults_to_non_destructive_check():
    args = git_workflow.parse_args([])
    assert args.mode == "check"
    assert args.base == "main"
    assert args.remote == "origin"


def test_resolve_work_branch_keeps_existing_feature_branch(monkeypatch):
    calls = []
    monkeypatch.setattr(git_workflow, "require_success", lambda command, **kwargs: calls.append(tuple(command)))

    branch = git_workflow.resolve_work_branch(
        "feat/current",
        requested=None,
        issue=37,
    )

    assert branch == "feat/current"
    assert calls == []


def test_resolve_work_branch_creates_issue_branch_from_main(monkeypatch):
    calls = []
    monkeypatch.setattr(git_workflow, "require_success", lambda command, **kwargs: calls.append(tuple(command)))

    branch = git_workflow.resolve_work_branch(
        "main",
        requested=None,
        issue=37,
    )

    assert branch == "issue-37-work"
    assert calls == [("git", "switch", "-c", "issue-37-work")]


@pytest.mark.parametrize(
    ("current", "requested", "issue"),
    [
        ("main", None, None),
        ("master", "main", 37),
        ("feat/current", "feat/other", 37),
    ],
)
def test_resolve_work_branch_refuses_unsafe_switches(current, requested, issue):
    with pytest.raises(RuntimeError):
        git_workflow.resolve_work_branch(
            current,
            requested=requested,
            issue=issue,
        )


def test_stage_changes_refuses_empty_commit(monkeypatch):
    calls = []

    def fake_require(command, **kwargs):
        calls.append(tuple(command))
        return completed(command)

    monkeypatch.setattr(git_workflow, "require_success", fake_require)
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=0),
    )

    with pytest.raises(RuntimeError, match="no changes"):
        git_workflow.stage_changes()

    assert calls == [("git", "add", "--all")]


def test_stage_changes_accepts_staged_diff(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: completed(command),
    )
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=1),
    )

    git_workflow.stage_changes()


def test_pr_body_closes_issue_when_available():
    body = git_workflow.build_pr_body(37)
    assert "Verification" in body
    assert "Closes #37" in body
    assert "Closes" not in git_workflow.build_pr_body(None)


def test_check_mode_runs_checks_without_git_writes(monkeypatch):
    events = []
    monkeypatch.setattr(git_workflow, "print_change_summary", lambda: events.append("summary"))
    monkeypatch.setattr(git_workflow, "current_branch", lambda: "main")
    monkeypatch.setattr(git_workflow, "run_repository_checks", lambda: events.append("checks"))

    args = argparse.Namespace(
        mode="check",
        issue=None,
        branch=None,
        message=None,
        title=None,
        body=None,
        base="main",
        remote="origin",
    )

    assert git_workflow.finalize(args) == 0
    assert events == ["summary", "checks"]


def test_pr_mode_checks_commits_pushes_and_creates_pr(monkeypatch):
    events = []
    monkeypatch.setattr(git_workflow, "print_change_summary", lambda: events.append("summary"))
    monkeypatch.setattr(git_workflow, "current_branch", lambda: "feat/issue-37")
    monkeypatch.setattr(git_workflow, "run_repository_checks", lambda: events.append("checks"))
    monkeypatch.setattr(git_workflow, "stage_changes", lambda: events.append("stage"))
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: events.append(tuple(command)) or completed(command),
    )
    monkeypatch.setattr(git_workflow, "git_output", lambda *args: "abc123")
    monkeypatch.setattr(
        git_workflow,
        "create_pull_request",
        lambda **kwargs: events.append(("pr", kwargs["branch"])) or "https://example/pr/1",
    )

    args = argparse.Namespace(
        mode="pr",
        issue=37,
        branch=None,
        message="Add developer finalize workflow",
        title=None,
        body=None,
        base="main",
        remote="origin",
    )

    assert git_workflow.finalize(args) == 0
    assert events[:3] == ["summary", "checks", "stage"]
    assert ("git", "commit", "-m", "Add developer finalize workflow") in events
    assert ("pr", "feat/issue-37") in events


def test_main_turns_runtime_error_into_nonzero(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "finalize",
        lambda args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert git_workflow.main(["check"]) == 1
