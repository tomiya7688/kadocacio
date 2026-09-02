"""Rank targets and editable category biases for generated team templates."""

from __future__ import annotations

from collections.abc import Iterable

from scripts.core.stat_scale import (
    PLAYER_GRADE_THRESHOLDS,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MIN,
    clamp_player_stat,
)


def rank_labels(thresholds: Iterable[dict] = PLAYER_GRADE_THRESHOLDS) -> tuple[str, ...]:
    return tuple(str(entry.get("rank", "E-")) for entry in thresholds)


def target_for_rank(rank: str, thresholds: Iterable[dict] = PLAYER_GRADE_THRESHOLDS) -> int:
    entries = tuple(thresholds)
    for index, entry in enumerate(entries):
        if str(entry.get("rank")) != str(rank):
            continue
        lower = float(entry.get("minimum", PLAYER_STAT_MIN))
        upper = PLAYER_STAT_MAX if index == 0 else float(entries[index - 1].get("minimum", PLAYER_STAT_MAX))
        return round(clamp_player_stat((lower + upper) / 2.0))
    return round((PLAYER_STAT_MIN + PLAYER_STAT_MAX) / 2.0)


def generation_profiles(options: dict) -> tuple[dict, ...]:
    profiles = tuple(
        entry for entry in options.get("generation_profiles", ())
        if isinstance(entry, dict) and str(entry.get("id", "")).strip()
    )
    return profiles or ({"id": "balanced", "label": "バランス", "modifiers": {}},)


def profile_label(options: dict, profile_id: str) -> str:
    profile = next(
        (entry for entry in generation_profiles(options) if str(entry.get("id")) == str(profile_id)),
        generation_profiles(options)[0],
    )
    return str(profile.get("label", profile.get("id", "バランス")))


def generation_field_targets(
    base_target: int | float,
    profile_id: str,
    options: dict,
    stat_fields: Iterable[str],
) -> dict[str, int]:
    """Redistribute category strength while retaining the requested overall mean."""
    fields = tuple(str(field) for field in stat_fields)
    profiles = generation_profiles(options)
    profile = next(
        (entry for entry in profiles if str(entry.get("id")) == str(profile_id)),
        profiles[0],
    )
    modifiers = profile.get("modifiers", {})
    modifiers = modifiers if isinstance(modifiers, dict) else {}
    category_fields = {
        str(entry.get("id")): tuple(str(field) for field in entry.get("fields", ()))
        for entry in options.get("generation_categories", ())
        if isinstance(entry, dict)
    }
    raw_bias = {field: 0.0 for field in fields}
    for category_id, raw_modifier in modifiers.items():
        try:
            modifier = float(raw_modifier)
        except (TypeError, ValueError):
            continue
        for field in category_fields.get(str(category_id), ()):
            if field in raw_bias:
                raw_bias[field] += modifier
    center = sum(raw_bias.values()) / len(fields) if fields else 0.0
    return {
        field: round(clamp_player_stat(float(base_target) + raw_bias[field] - center))
        for field in fields
    }


__all__ = (
    "generation_field_targets",
    "generation_profiles",
    "profile_label",
    "rank_labels",
    "target_for_rank",
)
