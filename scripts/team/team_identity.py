from __future__ import annotations

import re
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, uuid4, uuid5


TEAM_ID_KEY = "チームID"
TEAM_ID_ALIASES_KEY = "チームID別名"
TEAM_ID_PREFIX = "team:"
_TEAM_ID_PATTERN = re.compile(r"^team:[A-Za-z0-9._:-]+$")


def new_team_id() -> str:
    """Return a new path-independent team identifier."""
    return f"{TEAM_ID_PREFIX}{uuid4()}"


def legacy_team_id(relative_path: str | PurePosixPath) -> str:
    """Return the historical path-based identifier for migration purposes."""
    normalized = PurePosixPath(str(relative_path).replace("\\", "/")).as_posix()
    return f"json:{normalized}"


def deterministic_team_id(legacy_id: str) -> str:
    """Create a reproducible permanent ID while migrating repository data."""
    return f"{TEAM_ID_PREFIX}{uuid5(NAMESPACE_URL, f'kadocacio:{legacy_id}')}"


def normalize_team_id(value: object) -> str:
    team_id = str(value or "").strip()
    if not team_id:
        return ""
    if not _TEAM_ID_PATTERN.fullmatch(team_id):
        raise ValueError("チームIDは team: で始まる英数字IDにしてください")
    return team_id


def team_id_aliases(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    aliases = payload.get(TEAM_ID_ALIASES_KEY, [])
    if not isinstance(aliases, list):
        return []
    result: list[str] = []
    for alias in aliases:
        value = str(alias or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def ensure_team_identity(
    payload: dict,
    *,
    legacy_id: str = "",
    deterministic: bool = False,
) -> str:
    """Ensure a payload owns a permanent ID and remembers legacy path aliases."""
    team_id = normalize_team_id(payload.get(TEAM_ID_KEY, ""))
    if not team_id:
        team_id = deterministic_team_id(legacy_id) if deterministic and legacy_id else new_team_id()
        payload[TEAM_ID_KEY] = team_id

    aliases = team_id_aliases(payload)
    legacy_id = str(legacy_id or "").strip()
    if legacy_id and legacy_id != team_id and legacy_id not in aliases:
        aliases.append(legacy_id)
    if aliases:
        payload[TEAM_ID_ALIASES_KEY] = aliases
    return team_id


__all__ = (
    "TEAM_ID_ALIASES_KEY",
    "TEAM_ID_KEY",
    "TEAM_ID_PREFIX",
    "deterministic_team_id",
    "ensure_team_identity",
    "legacy_team_id",
    "new_team_id",
    "normalize_team_id",
    "team_id_aliases",
)
