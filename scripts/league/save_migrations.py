from __future__ import annotations

from copy import deepcopy


CURRENT_FORMAT_VERSION = 1
LEGACY_FORMAT_VERSION = 0


class SaveFormatError(ValueError):
    """Raised when a league save cannot be migrated safely."""


def detect_format_version(payload: dict) -> int:
    value = payload.get("format_version", LEGACY_FORMAT_VERSION)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SaveFormatError("format_versionが不正です")
    return value


def validate_current_save_payload(payload: dict) -> None:
    if detect_format_version(payload) != CURRENT_FORMAT_VERSION:
        raise SaveFormatError("現行format_versionではありません")
    for key in ("fixtures", "last_results", "history"):
        if key in payload and not isinstance(payload[key], list):
            raise SaveFormatError(f"{key}が配列ではありません")
    for key in (
        "league_memberships",
        "league_participations",
        "team_signature",
        "チームスナップショット",
    ):
        if key in payload and not isinstance(payload[key], dict):
            raise SaveFormatError(f"{key}がオブジェクトではありません")


def migrate_save_payload(payload: dict) -> tuple[dict, int]:
    if not isinstance(payload, dict):
        raise SaveFormatError("JSONの一番外側がオブジェクトではありません")
    source_version = detect_format_version(payload)
    if source_version > CURRENT_FORMAT_VERSION:
        raise SaveFormatError(
            f"未対応の未来format_versionです: {source_version} > {CURRENT_FORMAT_VERSION}"
        )
    migrated = deepcopy(payload)
    if source_version == LEGACY_FORMAT_VERSION:
        migrated["format_version"] = CURRENT_FORMAT_VERSION
    validate_current_save_payload(migrated)
    return migrated, source_version


__all__ = (
    "CURRENT_FORMAT_VERSION",
    "LEGACY_FORMAT_VERSION",
    "SaveFormatError",
    "detect_format_version",
    "migrate_save_payload",
    "validate_current_save_payload",
)
