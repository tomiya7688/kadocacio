import json

from scripts.tools.static_analysis import run_all
from scripts.tools.static_analysis.reporting import CheckResult, write_reports


def result(name, code=0):
    return CheckResult(
        name=name,
        command=("python", "-m", name),
        returncode=code,
        duration_seconds=0.1,
        stdout="failure detail" if code else "ok",
    )


def test_default_checks_match_ci_entry_points():
    checks = run_all.default_checks("python")

    assert [check.name for check in checks] == ["flake8", "compileall", "pytest"]
    assert checks[0].command[:3] == ("python", "-m", "flake8")
    assert checks[1].command == (
        "python",
        "-m",
        "compileall",
        "-q",
        "main.py",
        "scripts",
    )
    assert checks[2].command[:4] == ("python", "-m", "pytest", "-q")
    assert checks[2].command[4].startswith("--junitxml=")


def test_run_all_stops_after_first_failure(monkeypatch, tmp_path):
    seen = []

    def fake_run(check):
        seen.append(check.name)
        return result(check.name, 2 if check.name == "compileall" else 0)

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(run_all.default_checks("python"), report_dir=tmp_path)

    assert code == 1
    assert seen == ["flake8", "compileall"]
    assert (tmp_path / "check_summary.json").exists()
    assert (tmp_path / "check_summary.md").exists()


def test_run_all_can_keep_going(monkeypatch, tmp_path):
    seen = []

    def fake_run(check):
        seen.append(check.name)
        code = 1 if check.name in {"flake8", "pytest"} else 0
        return result(check.name, code)

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(
        run_all.default_checks("python"),
        keep_going=True,
        report_dir=tmp_path,
    )

    assert code == 1
    assert seen == ["flake8", "compileall", "pytest"]


def test_write_reports_contains_status_and_failure_excerpt(tmp_path):
    json_path, md_path = write_reports(
        [result("flake8"), result("pytest", 1)],
        tmp_path,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert payload["checks"][0]["status"] == "PASS"
    assert payload["checks"][1]["status"] == "FAIL"

    markdown = md_path.read_text(encoding="utf-8")
    assert "STATUS: FAIL" in markdown
    assert "pytest: FAIL" in markdown
    assert "failure detail" in markdown
