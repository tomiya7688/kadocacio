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


def test_run_command_forwards_capture_and_repository_root(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        return completed(command)

    monkeypatch.setattr(git_workflow.subprocess, "run", fake_run)

    result = git_workflow.run_command(("git", "status"), capture=True)

    assert result.returncode == 0
    assert seen["command"] == ["git", "status"]
    assert seen["cwd"] == git_workflow.ROOT
    assert seen["capture_output"] is True


def test_require_success_reports_command_failure_details(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, 2, stdout="fallback"),
    )
    with pytest.raises(RuntimeError, match="fallback"):
        git_workflow.require_success(("git", "bad"), capture=True)

    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, 3),
    )
    with pytest.raises(RuntimeError, match=r"command failed \(3\)"):
        git_workflow.require_success(("git", "worse"))


def test_git_output_and_current_branch_handle_normal_and_detached(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: completed(command, stdout=" feat/test \n"),
    )
    assert git_workflow.git_output("branch", "--show-current") == "feat/test"

    monkeypatch.setattr(git_workflow, "git_output", lambda *args: "")
    with pytest.raises(RuntimeError, match="detached HEAD"):
        git_workflow.current_branch()


def test_print_change_summary_handles_clean_and_dirty_states(monkeypatch, capsys):
    values = iter(("", "", ""))
    monkeypatch.setattr(git_workflow, "git_output", lambda *args: next(values))
    git_workflow.print_change_summary()
    assert "working tree clean" in capsys.readouterr().out

    values = iter((" M file.py", " file.py | 2 +-", " staged.py | 1 +"))
    monkeypatch.setattr(git_workflow, "git_output", lambda *args: next(values))
    git_workflow.print_change_summary()
    output = capsys.readouterr().out
    assert "unstaged diff" in output
    assert "staged diff" in output


def test_repository_checks_propagate_failure(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=5),
    )
    with pytest.raises(RuntimeError, match="exit code 5"):
        git_workflow.run_repository_checks()

    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=0),
    )
    git_workflow.run_repository_checks()


def test_commit_message_resolution_covers_message_issue_and_missing():
    assert git_workflow.resolve_commit_message("  custom message  ", None) == "custom message"
    assert git_workflow.resolve_commit_message(None, 37) == "Complete issue #37"
    with pytest.raises(RuntimeError, match="--message"):
        git_workflow.resolve_commit_message("   ", None)


def test_same_requested_feature_branch_is_allowed():
    assert (
        git_workflow.resolve_work_branch(
            "feat/current",
            requested="feat/current",
            issue=None,
        )
        == "feat/current"
    )


def test_requested_feature_branch_is_created_from_main(monkeypatch):
    calls = []
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: calls.append(tuple(command)) or completed(command),
    )

    assert (
        git_workflow.resolve_work_branch(
            "main",
            requested="feat/custom",
            issue=None,
        )
        == "feat/custom"
    )
    assert calls == [("git", "switch", "-c", "feat/custom")]


def test_stage_changes_reports_git_diff_errors(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: completed(command),
    )
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=2),
    )
    with pytest.raises(RuntimeError, match="git diff exit 2"):
        git_workflow.stage_changes()


def test_create_pull_request_returns_url_and_fallback(monkeypatch):
    calls = []
    outputs = iter(
        [
            completed(("gh", "--version")),
            completed(("git", "push")),
            completed(("gh", "pr", "create"), stdout="notice\nhttps://example/pr/2\n"),
        ]
    )

    def fake_require(command, **kwargs):
        calls.append((tuple(command), kwargs.get("capture", False)))
        return next(outputs)

    monkeypatch.setattr(git_workflow, "require_success", fake_require)
    assert (
        git_workflow.create_pull_request(
            branch="feat/x",
            base="main",
            title="Title",
            body="Body",
            remote="origin",
        )
        == "https://example/pr/2"
    )
    assert calls[0] == (("gh", "--version"), True)

    outputs = iter(
        [
            completed(("gh", "--version")),
            completed(("git", "push")),
            completed(("gh", "pr", "create"), stdout="\n"),
        ]
    )
    assert (
        git_workflow.create_pull_request(
            branch="feat/x",
            base="main",
            title="Title",
            body="Body",
            remote="origin",
        )
        == "(PR created; URL not returned)"
    )


def test_commit_mode_skips_push_and_pr(monkeypatch):
    events = []
    monkeypatch.setattr(git_workflow, "print_change_summary", lambda: events.append("summary"))
    monkeypatch.setattr(git_workflow, "current_branch", lambda: "feat/current")
    monkeypatch.setattr(git_workflow, "run_repository_checks", lambda: events.append("checks"))
    monkeypatch.setattr(git_workflow, "stage_changes", lambda: events.append("stage"))
    monkeypatch.setattr(
        git_workflow,
        "require_success",
        lambda command, **kwargs: events.append(tuple(command)) or completed(command),
    )
    monkeypatch.setattr(git_workflow, "git_output", lambda *args: "commit123")
    monkeypatch.setattr(
        git_workflow,
        "create_pull_request",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("PR must not run")),
    )

    args = argparse.Namespace(
        mode="commit",
        issue=37,
        branch=None,
        message=None,
        title=None,
        body=None,
        base="main",
        remote="origin",
    )
    assert git_workflow.finalize(args) == 0
    assert ("git", "commit", "-m", "Complete issue #37") in events


def test_main_returns_finalize_success(monkeypatch):
    monkeypatch.setattr(git_workflow, "finalize", lambda args: 0)
    assert git_workflow.main(["check"]) == 0


def test_require_success_and_current_branch_normal_paths(monkeypatch):
    monkeypatch.setattr(
        git_workflow,
        "run_command",
        lambda command, **kwargs: completed(command, returncode=0, stdout="ok"),
    )
    assert git_workflow.require_success(("git", "status")).stdout == "ok"

    monkeypatch.setattr(git_workflow, "git_output", lambda *args: "feat/normal")
    assert git_workflow.current_branch() == "feat/normal"
