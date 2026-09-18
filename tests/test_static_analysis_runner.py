import json
from pathlib import Path

from scripts.tools.static_analysis import run_all
from scripts.tools.static_analysis.reporting import (
    summarize_flake8,
    summarize_pytest,
    write_reports,
)


def fake_result(name, code=0, stdout=""):
    return {
        "name": name,
        "command": ["python", "-m", name],
        "returncode": code,
        "duration_seconds": 0.1,
        "stdout_log": f"static_analysis/reports/{name}.stdout.log",
        "stderr_log": f"static_analysis/reports/{name}.stderr.log",
        "_stdout": stdout,
        "_stderr": "",
    }


def test_default_checks_match_ci_entry_points(tmp_path):
    checks = run_all.default_checks("python", report_dir=tmp_path)

    assert [check["name"] for check in checks] == [
        "flake8",
        "compileall",
        "architecture-boundary",
        "upd-commander",
        "pytest",
    ]
    assert checks[0]["command"][:3] == ("python", "-m", "flake8")
    assert checks[1]["command"] == (
        "python",
        "-m",
        "compileall",
        "-q",
        "main.py",
        "scripts",
    )
    assert checks[2]["command"] == (
        "python",
        "-m",
        "scripts.tools.static_analysis.architecture_boundary",
    )
    assert checks[3]["command"] == (
        "python",
        "-m",
        "scripts.tools.static_analysis.upd_checker",
    )
    assert checks[4]["command"][:4] == ("python", "-m", "pytest", "-q")
    assert checks[4]["command"][4] == f"--junitxml={tmp_path / 'pytest_junit.xml'}"


def test_default_checks_can_disable_junit_output():
    checks = run_all.default_checks("python", report_dir=None)
    assert checks[-1]["command"] == ("python", "-m", "pytest", "-q")


def test_run_all_stops_after_first_failure(monkeypatch, tmp_path):
    seen = []

    def fake_run(check, report_dir):
        seen.append(check["name"])
        return fake_result(
            check["name"],
            2 if check["name"] == "compileall" else 0,
        )

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(
        run_all.default_checks("python", report_dir=tmp_path),
        report_dir=tmp_path,
    )

    assert code == 1
    assert seen == ["flake8", "compileall"]
    payload = json.loads((tmp_path / "precommit_summary.json").read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"


def test_run_all_can_keep_going(monkeypatch, tmp_path):
    seen = []

    def fake_run(check, report_dir):
        seen.append(check["name"])
        code = 1 if check["name"] in {"flake8", "pytest"} else 0
        return fake_result(check["name"], code, "2 failed, 3 passed" if check["name"] == "pytest" else "")

    monkeypatch.setattr(run_all, "run_check", fake_run)
    code = run_all.run_all(
        run_all.default_checks("python", report_dir=tmp_path),
        keep_going=True,
        report_dir=tmp_path,
    )

    assert code == 1
    assert seen == [
        "flake8",
        "compileall",
        "architecture-boundary",
        "upd-commander",
        "pytest",
    ]


def test_run_all_without_reports_does_not_write_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        run_all,
        "run_check",
        lambda check, report_dir: fake_result(check["name"]),
    )
    assert run_all.run_all(run_all.default_checks("python"), report_dir=None) == 0
    assert list(tmp_path.iterdir()) == []


def test_summarize_pytest_reads_terminal_counts_and_failures(tmp_path):
    junit = tmp_path / "pytest_junit.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite tests="4" failures="1" errors="0" skipped="1" time="1.25">
    <testcase classname="tests.test_sample" name="test_ok" file="tests/test_sample.py" />
    <testcase classname="tests.test_sample" name="test_fail" file="tests/test_sample.py">
      <failure type="AssertionError" message="nope">trace</failure>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    summary = summarize_pytest(
        junit,
        "1 failed, 2 passed, 1 skipped, 1 xfailed, 1 xpassed",
    )

    assert summary["failed"] == 1
    assert summary["passed"] == 2
    assert summary["skipped"] == 1
    assert summary["xfailed"] == 1
    assert summary["xpassed"] == 1
    assert summary["duration_seconds"] == 1.25
    assert summary["failures"][0]["test"] == "tests.test_sample::test_fail"
    assert summary["failures"][0]["type"] == "AssertionError"


def test_summarize_pytest_falls_back_to_junit_counts(tmp_path):
    junit = tmp_path / "pytest_junit.xml"
    junit.write_text(
        '<testsuite tests="3" failures="1" errors="1" skipped="0" time="0.5"></testsuite>',
        encoding="utf-8",
    )
    summary = summarize_pytest(junit, "")
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 1


def test_summarize_flake8_prefers_count_line_and_can_count_messages():
    assert summarize_flake8("a.py:1:1: F821 bad\n1\n")["violations"] == 1
    assert summarize_flake8("a.py:1:1: F821 bad\nb.py:2:1: E999 bad\n")["violations"] == 2
    assert summarize_flake8("")["violations"] == 0


def test_write_reports_contains_compact_failure_information(tmp_path):
    pytest_summary = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "duration_seconds": 0.2,
        "failures": [
            {
                "test": "tests.test_x::test_bad",
                "file": "tests/test_x.py",
                "kind": "failure",
                "type": "AssertionError",
                "message": "bad",
            }
        ],
    }
    json_path, md_path = write_reports(
        [
            {key: value for key, value in fake_result("flake8").items() if not key.startswith("_")},
            {key: value for key, value in fake_result("pytest", 1).items() if not key.startswith("_")},
        ],
        tmp_path,
        pytest_summary=pytest_summary,
        flake8_summary={"violations": 0},
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "FAIL"
    assert payload["pytest"]["failures"][0]["test"] == "tests.test_x::test_bad"

    markdown = md_path.read_text(encoding="utf-8")
    assert "STATUS: FAIL" in markdown
    assert "tests.test_x::test_bad [AssertionError]" in markdown
    assert "pytest.stdout.log" in markdown


def test_parse_args_supports_report_controls(tmp_path):
    args = run_all.parse_args(["--keep-going", "--report-dir", str(tmp_path)])
    assert args.keep_going is True
    assert args.report_dir == Path(tmp_path)
    assert args.no_reports is False

    args = run_all.parse_args(["--no-reports"])
    assert args.no_reports is True
