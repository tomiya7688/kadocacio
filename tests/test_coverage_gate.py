import json

from scripts.tools import coverage_gate


def write_report(path, files):
    path.write_text(json.dumps({"files": files}), encoding="utf-8")


def test_load_report_separates_game_and_tools(tmp_path):
    report = tmp_path / "coverage.json"
    write_report(
        report,
        {
            "scripts/match/example.py": {
                "summary": {"covered_branches": 6, "num_branches": 10}
            },
            "scripts/tools/example.py": {
                "summary": {"covered_branches": 3, "num_branches": 4}
            },
            "tests/test_example.py": {
                "summary": {"covered_branches": 99, "num_branches": 100}
            },
        },
    )

    game, tools = coverage_gate.load_report(report)

    assert game.covered == 6
    assert game.total == 10
    assert game.percent == 60.0
    assert tools.covered == 3
    assert tools.total == 4
    assert tools.percent == 75.0


def test_windows_paths_are_grouped_correctly(tmp_path):
    report = tmp_path / "coverage.json"
    write_report(
        report,
        {
            "scripts\\team\\editor.py": {
                "summary": {"covered_branches": 2, "num_branches": 5}
            },
            "scripts\\tools\\helper.py": {
                "summary": {"covered_branches": 4, "num_branches": 5}
            },
        },
    )

    game, tools = coverage_gate.load_report(report)

    assert (game.covered, game.total) == (2, 5)
    assert (tools.covered, tools.total) == (4, 5)


def test_run_fails_when_a_group_drops_below_minimum(tmp_path):
    report = tmp_path / "coverage.json"
    write_report(
        report,
        {
            "scripts/core/example.py": {
                "summary": {"covered_branches": 4, "num_branches": 10}
            },
            "scripts/tools/example.py": {
                "summary": {"covered_branches": 8, "num_branches": 10}
            },
        },
    )

    assert coverage_gate.run(report, min_game=50.0, min_tools=70.0) == 1
    assert coverage_gate.run(report, min_game=40.0, min_tools=80.0) == 0


def test_zero_branch_group_is_treated_as_fully_covered(tmp_path):
    report = tmp_path / "coverage.json"
    write_report(report, {})

    game, tools = coverage_gate.load_report(report)

    assert game.percent == 100.0
    assert tools.percent == 100.0
