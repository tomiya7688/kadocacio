"""Architecture boundary violation result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule_id: str
    severity: str
    path: str
    line: int
    imported: str
    message: str
