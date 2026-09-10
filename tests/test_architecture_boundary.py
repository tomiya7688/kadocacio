import json
from pathlib import Path

from scripts.tools.static_analysis.architecture_boundary import (
    Rule,
    check_boundaries,
    load_rules,
    matches_forbidden,
    write_report,
)


def test_matches_forbidden_matches_package_and_children():
    assert matches_forbidden("scripts.app", "scripts.app")
    assert matches_forbidden("scripts.app.rendering", "scripts.app")
    assert not matches_forbidden("scripts.application", "scripts.app")


def test_checker_reports_error_and_warning(tmp_path: Path):
    (tmp_path / "scripts" / "match").mkdir(parents=True)
    (tmp_path / "scripts" / "core").mkdir(parents=True)
    (tmp_path / "scripts" / "match" / "bad.py").write_text(
        "from scripts.app.game_app import Game\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "core" / "legacy.py").write_text(
        "import pygame\n", encoding="utf-8"
    )
    rules = (
        Rule("match-no-app", "scripts/match", ("scripts.app",), "error", "no app"),
        Rule("core-pygame", "scripts/core", ("pygame",), "warning", "portable core"),
    )

    violations = check_boundaries(rules, root=tmp_path)

    assert [(item.rule_id, item.severity) for item in violations] == [
        ("match-no-app", "error"),
        ("core-pygame", "warning"),
    ]


def test_write_report_marks_warning_only_as_pass(tmp_path: Path):
    source = tmp_path / "scripts" / "core"
    source.mkdir(parents=True)
    (source / "legacy.py").write_text("import pygame\n", encoding="utf-8")
    rules = (Rule("core-pygame", "scripts/core", ("pygame",), "warning", "legacy"),)
    violations = check_boundaries(rules, root=tmp_path)
    report = tmp_path / "report.json"

    write_report(violations, report)
    payload = json.loads(report.read_text(encoding="utf-8"))

    assert payload["status"] == "PASS"
    assert payload["errors"] == 0
    assert payload["warnings"] == 1


def test_load_rules_rejects_unknown_severity(tmp_path: Path):
    config = tmp_path / "rules.json"
    config.write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "id": "bad",
                        "source": "scripts/core",
                        "forbidden_imports": ["pygame"],
                        "severity": "fatal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        load_rules(config)
    except ValueError as exc:
        assert "invalid severity" in str(exc)
    else:
        raise AssertionError("load_rules should reject invalid severity")
