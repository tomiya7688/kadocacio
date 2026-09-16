"""Run the upstream UPD Commander checker with Kadocalcio's staged policy."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "static_analysis" / "upd_commander.json"
VALID_SEVERITIES = frozenset({"error", "warning", "attention"})


@dataclass(frozen=True)
class Profile:
    upstream_repository: str
    upstream_commit: str
    target: Path
    enabled_rules: tuple[str, ...]
    ignore: tuple[str, ...]
    blocking_severities: frozenset[str]
    report: Path
    max_console_findings: int


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_profile(path: Path = DEFAULT_CONFIG, *, root: Path = ROOT) -> Profile:
    """Load and validate the local adoption policy."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("UPD Commander config must be a JSON object")

    repository = str(payload.get("upstream_repository", "")).strip()
    commit = str(payload.get("upstream_commit", "")).strip()
    target = str(payload.get("target", "scripts")).strip()
    report = str(payload.get("report", "static_analysis/reports/upd_commander.json")).strip()
    if not repository or not commit or not target or not report:
        raise ValueError("UPD Commander config is missing repository, commit, target, or report")

    enabled = payload.get("enabled_rules", [])
    ignore = payload.get("ignore", [])
    blocking = payload.get("blocking_severities", ["error"])
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ValueError("enabled_rules must be a list of strings")
    if not isinstance(ignore, list) or not all(isinstance(item, str) for item in ignore):
        raise ValueError("ignore must be a list of strings")
    if not isinstance(blocking, list) or not all(isinstance(item, str) for item in blocking):
        raise ValueError("blocking_severities must be a list of strings")

    blocking_set = frozenset(item.strip().lower() for item in blocking)
    if not blocking_set or not blocking_set <= VALID_SEVERITIES:
        raise ValueError("blocking_severities contains an unsupported severity")

    max_console = payload.get("max_console_findings", 20)
    if not isinstance(max_console, int) or max_console < 0:
        raise ValueError("max_console_findings must be a non-negative integer")

    return Profile(
        upstream_repository=repository,
        upstream_commit=commit,
        target=_resolve(root, target).resolve(),
        enabled_rules=tuple(dict.fromkeys(item.strip().upper() for item in enabled if item.strip())),
        ignore=tuple(item for item in ignore if item.strip()),
        blocking_severities=blocking_set,
        report=_resolve(root, report).resolve(),
        max_console_findings=max_console,
    )


def _load_upstream() -> tuple[Callable, Callable]:
    try:
        from upd_commander_checker.rule_selection import filter_enabled_findings
        from upd_commander_checker.scanner import scan_path
    except ImportError as exc:  # pragma: no cover - exercised by environment setup
        raise RuntimeError(
            "UPD Commander checker is not installed; install requirements-dev.txt"
        ) from exc
    return scan_path, filter_enabled_findings


def collect_findings(
    profile: Profile,
    *,
    scan_path_func: Callable | None = None,
    filter_func: Callable | None = None,
) -> list:
    """Collect upstream findings without importing checker code at game runtime."""
    if scan_path_func is None or filter_func is None:
        upstream_scan, upstream_filter = _load_upstream()
        scan_path_func = scan_path_func or upstream_scan
        filter_func = filter_func or upstream_filter
    findings = scan_path_func(profile.target, profile.ignore)
    return list(filter_func(findings, profile.enabled_rules))


def _display_path(path: Path, target: Path) -> str:
    path = Path(path)
    if path.is_absolute():
        try:
            return path.relative_to(target).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def _counts(findings: Iterable) -> dict[str, int]:
    counts = {severity: 0 for severity in ("error", "warning", "attention")}
    for finding in findings:
        severity = str(getattr(finding, "severity", "error")).lower()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _record(finding, target: Path) -> dict:
    return {
        "code": str(finding.code),
        "severity": str(getattr(finding, "severity", "error")).lower(),
        "path": _display_path(Path(finding.path), target),
        "line": int(finding.line),
        "message": str(finding.message),
    }


def write_report(profile: Profile, findings: Sequence, *, status: str) -> None:
    profile.report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "upstream": {
            "repository": profile.upstream_repository,
            "commit": profile.upstream_commit,
        },
        "target": profile.target.relative_to(ROOT).as_posix()
        if profile.target.is_relative_to(ROOT)
        else profile.target.as_posix(),
        "enabled_rules": list(profile.enabled_rules),
        "blocking_severities": sorted(profile.blocking_severities),
        "counts": _counts(findings),
        "findings": [_record(finding, profile.target) for finding in findings],
    }
    profile.report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(profile: Profile) -> int:
    if not profile.target.exists():
        print(f"UPD COMMANDER: ERROR target does not exist: {profile.target}")
        return 2
    try:
        findings = collect_findings(profile)
    except RuntimeError as exc:
        print(f"UPD COMMANDER: ERROR {exc}")
        return 2

    blocked = [
        finding for finding in findings
        if str(getattr(finding, "severity", "error")).lower() in profile.blocking_severities
    ]
    status = "FAIL" if blocked else "PASS"
    write_report(profile, findings, status=status)

    counts = _counts(findings)
    print(
        f"UPD COMMANDER: {status} "
        f"(e={counts.get('error', 0)}, w={counts.get('warning', 0)}, "
        f"a={counts.get('attention', 0)})"
    )
    level = {"error": "E", "warning": "W", "attention": "A"}
    for finding in findings[: profile.max_console_findings]:
        severity = str(getattr(finding, "severity", "error")).lower()
        print(
            f"- {level.get(severity, '?')} {finding.code} "
            f"{_display_path(Path(finding.path), profile.target)}:{finding.line} "
            f"{finding.message}"
        )
    hidden = len(findings) - profile.max_console_findings
    if hidden > 0:
        print(f"- ... {hidden} more findings; full report: {profile.report}")
    return 1 if blocked else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        profile = load_profile(args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"UPD COMMANDER: ERROR invalid config: {exc}")
        return 2
    return run(profile)


if __name__ == "__main__":
    raise SystemExit(main())
