import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.tools.static_analysis import upd_commander


def make_profile(tmp_path: Path, *, blocking=frozenset({"error"}), max_console=20):
    target = tmp_path / "scripts"
    target.mkdir(parents=True, exist_ok=True)
    return upd_commander.Profile(
        upstream_repository="owner/upd",
        upstream_commit="abc123",
        target=target,
        enabled_rules=("UPD101", "UPD401"),
        ignore=("generated/**",),
        blocking_severities=blocking,
        report=tmp_path / "reports" / "upd.json",
        max_console_findings=max_console,
    )


def finding(path: Path, severity="warning", code="UPD401", line=1, message="finding"):
    return SimpleNamespace(
        path=path,
        severity=severity,
        code=code,
        line=line,
        message=message,
    )


def test_resolve_handles_relative_and_absolute_paths(tmp_path):
    absolute = (tmp_path / "absolute").resolve()

    assert upd_commander._resolve(tmp_path, "relative") == tmp_path / "relative"
    assert upd_commander._resolve(tmp_path, str(absolute)) == absolute


def test_load_profile_resolves_policy_and_validates_fields(tmp_path):
    config = tmp_path / "profile.json"
    config.write_text(
        json.dumps(
            {
                "upstream_repository": "owner/upd",
                "upstream_commit": "abc123",
                "target": "scripts",
                "enabled_rules": ["upd101", "UPD401", "UPD101", ""],
                "ignore": ["tests/**", ""],
                "blocking_severities": ["ERROR"],
                "report": "reports/upd.json",
                "max_console_findings": 7,
            }
        ),
        encoding="utf-8",
    )

    profile = upd_commander.load_profile(config, root=tmp_path)

    assert profile.target == (tmp_path / "scripts").resolve()
    assert profile.enabled_rules == ("UPD101", "UPD401")
    assert profile.ignore == ("tests/**",)
    assert profile.blocking_severities == frozenset({"error"})
    assert profile.report == (tmp_path / "reports/upd.json").resolve()
    assert profile.max_console_findings == 7


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "JSON object"),
        ({}, "missing repository"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "enabled_rules": "UPD101"}, "enabled_rules"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "ignore": "tests"}, "ignore"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "blocking_severities": "error"}, "blocking_severities"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "blocking_severities": []}, "blocking_severities"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "blocking_severities": ["fatal"]}, "blocking_severities"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "max_console_findings": -1}, "max_console_findings"),
        ({"upstream_repository": "x", "upstream_commit": "y", "target": "scripts", "report": "r", "max_console_findings": "20"}, "max_console_findings"),
    ],
)
def test_load_profile_rejects_invalid_policy(tmp_path, payload, message):
    config = tmp_path / "profile.json"
    config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        upd_commander.load_profile(config, root=tmp_path)


def test_collect_findings_uses_profile_rules_and_supports_lazy_loader(monkeypatch, tmp_path):
    profile = make_profile(tmp_path)
    seen = {}
    raw = [finding(profile.target / "x.py")]

    def scan(target, ignore):
        seen["scan"] = (target, ignore)
        return raw

    def filter_rules(items, enabled):
        seen["filter"] = (items, enabled)
        return items

    assert upd_commander.collect_findings(
        profile,
        scan_path_func=scan,
        filter_func=filter_rules,
    ) == raw
    assert seen["scan"] == (profile.target, profile.ignore)
    assert seen["filter"] == (raw, profile.enabled_rules)

    monkeypatch.setattr(upd_commander, "_load_upstream", lambda: (scan, filter_rules))
    assert upd_commander.collect_findings(profile) == raw
    assert upd_commander.collect_findings(profile, scan_path_func=scan) == raw
    assert upd_commander.collect_findings(profile, filter_func=filter_rules) == raw


def test_display_path_handles_relative_inside_and_outside_paths(tmp_path):
    target = tmp_path / "scripts"
    inside = target / "match" / "engine.py"
    outside = tmp_path / "other.py"

    assert upd_commander._display_path(Path("relative.py"), target) == "relative.py"
    assert upd_commander._display_path(inside, target) == "match/engine.py"
    assert upd_commander._display_path(outside, target) == outside.as_posix()


def test_counts_accepts_known_default_and_extra_severities(tmp_path):
    target = tmp_path / "scripts"
    findings = [
        finding(target / "a.py", "error"),
        finding(target / "b.py", "warning"),
        finding(target / "c.py", "attention"),
        SimpleNamespace(path=target / "d.py", code="UPD999", line=1, message="x"),
        finding(target / "e.py", "custom"),
    ]

    counts = upd_commander._counts(findings)

    assert counts == {"error": 2, "warning": 1, "attention": 1, "custom": 1}


def test_write_report_records_upstream_counts_and_paths(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(upd_commander, "ROOT", root)
    profile = make_profile(root)
    items = [finding(profile.target / "game.py", "warning", line=12)]

    upd_commander.write_report(profile, items, status="PASS")
    payload = json.loads(profile.report.read_text(encoding="utf-8"))

    assert payload["status"] == "PASS"
    assert payload["upstream"] == {"repository": "owner/upd", "commit": "abc123"}
    assert payload["target"] == "scripts"
    assert payload["counts"]["warning"] == 1
    assert payload["findings"][0]["path"] == "game.py"

    outside = make_profile(tmp_path / "outside")
    upd_commander.write_report(outside, [], status="PASS")
    outside_payload = json.loads(outside.report.read_text(encoding="utf-8"))
    assert outside_payload["target"] == outside.target.as_posix()


def test_run_warns_without_blocking_and_caps_console(monkeypatch, tmp_path, capsys):
    profile = make_profile(tmp_path, max_console=1)
    items = [
        finding(profile.target / "large.py", "warning", "UPD401", 10, "large"),
        finding(profile.target / "data.py", "attention", "UPD403", 20, "data"),
    ]
    monkeypatch.setattr(upd_commander, "collect_findings", lambda _profile: items)

    assert upd_commander.run(profile) == 0
    output = capsys.readouterr().out
    assert "UPD COMMANDER: PASS (e=0, w=1, a=1)" in output
    assert "1 more findings" in output
    assert json.loads(profile.report.read_text(encoding="utf-8"))["status"] == "PASS"


def test_run_blocks_errors_and_handles_unknown_console_severity(monkeypatch, tmp_path, capsys):
    profile = make_profile(tmp_path, blocking=frozenset({"error", "attention"}))
    items = [
        finding(profile.target / "bad.py", "error", "UPD101", 3, "bad dependency"),
        finding(profile.target / "attention.py", "attention", "UPD403", 4, "split type"),
        finding(profile.target / "odd.py", "custom", "UPD999", 5, "custom"),
    ]
    monkeypatch.setattr(upd_commander, "collect_findings", lambda _profile: items)

    assert upd_commander.run(profile) == 1
    output = capsys.readouterr().out
    assert "UPD COMMANDER: FAIL" in output
    assert "? UPD999" in output


def test_run_reports_missing_target_and_missing_checker(monkeypatch, tmp_path, capsys):
    missing_profile = upd_commander.Profile(
        "owner/upd",
        "abc",
        tmp_path / "missing",
        (),
        (),
        frozenset({"error"}),
        tmp_path / "report.json",
        20,
    )
    assert upd_commander.run(missing_profile) == 2
    assert "target does not exist" in capsys.readouterr().out

    profile = make_profile(tmp_path)
    monkeypatch.setattr(
        upd_commander,
        "collect_findings",
        lambda _profile: (_ for _ in ()).throw(RuntimeError("checker missing")),
    )
    assert upd_commander.run(profile) == 2
    assert "checker missing" in capsys.readouterr().out


def test_main_handles_invalid_config_and_success(monkeypatch, tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")
    assert upd_commander.main(["--config", str(invalid)]) == 2
    assert "invalid config" in capsys.readouterr().out

    profile = make_profile(tmp_path)
    monkeypatch.setattr(upd_commander, "load_profile", lambda _path: profile)
    monkeypatch.setattr(upd_commander, "run", lambda _profile: 0)
    assert upd_commander.main(["--config", str(invalid)]) == 0


def test_upstream_pin_is_dev_only_and_matches_policy():
    profile = upd_commander.load_profile()
    dev_requirements = (upd_commander.ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    runtime_requirements = (upd_commander.ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert profile.upstream_repository in dev_requirements
    assert profile.upstream_commit in dev_requirements
    assert "upd-commander-checker" in dev_requirements
    assert "upd-commander" not in runtime_requirements.lower()
