"""Check configured architecture import boundaries using the Python AST."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "static_analysis" / "architecture_rules.json"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    source: str
    forbidden_imports: tuple[str, ...]
    severity: str
    message: str


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: str
    path: str
    line: int
    imported: str
    message: str


def load_rules(path: Path = DEFAULT_CONFIG) -> tuple[Rule, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rules = []
    for item in payload.get("rules", []):
        severity = str(item.get("severity", "error")).lower()
        if severity not in {"error", "warning"}:
            raise ValueError(f"invalid severity for {item.get('id')}: {severity}")
        rules.append(
            Rule(
                rule_id=str(item["id"]),
                source=str(item["source"]),
                forbidden_imports=tuple(str(value) for value in item["forbidden_imports"]),
                severity=severity,
                message=str(item.get("message", "architecture boundary violation")),
            )
        )
    return tuple(rules)


def imported_modules(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.lineno


def matches_forbidden(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(forbidden + ".")


def scan_file(path: Path, rule: Rule, *, root: Path = ROOT) -> list[Violation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        line = getattr(exc, "lineno", None) or 1
        return [
            Violation(
                rule_id="parser-error",
                severity="error",
                path=str(path.relative_to(root)),
                line=line,
                imported="",
                message=str(exc),
            )
        ]

    violations = []
    for module, line in imported_modules(tree):
        for forbidden in rule.forbidden_imports:
            if matches_forbidden(module, forbidden):
                violations.append(
                    Violation(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        path=str(path.relative_to(root)),
                        line=line,
                        imported=module,
                        message=rule.message,
                    )
                )
    return violations


def check_boundaries(rules: Sequence[Rule], *, root: Path = ROOT) -> list[Violation]:
    violations = []
    for rule in rules:
        source = root / rule.source
        if not source.exists():
            violations.append(
                Violation(
                    rule_id=rule.rule_id,
                    severity="error",
                    path=rule.source,
                    line=1,
                    imported="",
                    message="configured source path does not exist",
                )
            )
            continue
        for path in sorted(source.rglob("*.py")):
            violations.extend(scan_file(path, rule, root=root))
    return violations


def write_report(violations: Sequence[Violation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "FAIL" if any(v.severity == "error" for v in violations) else "PASS",
        "errors": sum(v.severity == "error" for v in violations),
        "warnings": sum(v.severity == "warning" for v in violations),
        "violations": [v.__dict__ for v in violations],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "static_analysis" / "reports" / "architecture_boundary.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    violations = check_boundaries(load_rules(args.config))
    write_report(violations, args.report)

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    status = "FAIL" if errors else "PASS"
    print(f"ARCHITECTURE BOUNDARY: {status} ({len(errors)} errors, {len(warnings)} warnings)")
    for violation in violations:
        print(
            f"- {violation.severity.upper()} {violation.path}:{violation.line} "
            f"[{violation.rule_id}] {violation.imported or violation.message}"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
