"""Architecture boundary rule definition."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    source: str
    forbidden_imports: tuple[str, ...]
    severity: str
    message: str
