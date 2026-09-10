from scripts.tools.static_analysis import run_all


def test_default_checks_match_ci_entry_points():
    checks = run_all.default_checks("python")

    assert [check.name for check in checks] == [
        "flake8",
        "compileall",
        "architecture-boundary",
        "pytest",
    ]
    assert checks[0].command[:3] == ("python", "-m", "flake8")
    assert checks[1].command == (
        "python",
        "-m",
        "compileall",
        "-q",
        "main.py",
        "scripts",
    )
    assert checks[2].command == (
        "python",
        "-m",
        "scripts.tools.static_analysis.architecture_boundary",
    )
    assert checks[3].command == ("python", "-m", "pytest", "-q")


def test_run_all_stops_after_first_failure(monkeypatch):
    seen = []

    def fake_run(check):
        seen.append(check.name)
        return 2 if check.name == "compileall" else 0

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(run_all.default_checks("python"))

    assert code == 1
    assert seen == ["flake8", "compileall"]


def test_run_all_can_keep_going(monkeypatch):
    seen = []

    def fake_run(check):
        seen.append(check.name)
        return 1 if check.name in {"flake8", "pytest"} else 0

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(run_all.default_checks("python"), keep_going=True)

    assert code == 1
    assert seen == ["flake8", "compileall", "architecture-boundary", "pytest"]
