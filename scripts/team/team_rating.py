from __future__ import annotations

from typing import Iterable

from scripts.team.team_data import PLAYER_KEY_ALIASES
from scripts.team.team_editor_config import load_tuner_options


TUNER_OPTIONS = load_tuner_options()
TUNER_CATEGORIES = tuple(TUNER_OPTIONS.get("categories", ()))
RANK_THRESHOLDS = tuple(TUNER_OPTIONS.get("rank_thresholds", ()))

JAPANESE_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in PLAYER_KEY_ALIASES.items()
    for alias in aliases
}


def reload_rating_options() -> None:
    global TUNER_OPTIONS, TUNER_CATEGORIES, RANK_THRESHOLDS
    TUNER_OPTIONS = load_tuner_options()
    TUNER_CATEGORIES = tuple(TUNER_OPTIONS.get("categories", ()))
    RANK_THRESHOLDS = tuple(TUNER_OPTIONS.get("rank_thresholds", ()))


def numeric_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rank_for_average(value: float, thresholds: Iterable[dict] | None = None) -> str:
    ordered = thresholds or RANK_THRESHOLDS
    for entry in ordered:
        if value >= numeric_value(entry.get("minimum"), 0.0):
            return str(entry.get("rank", "E-"))
    return "E-"


def category_average(record: dict, category: dict) -> float:
    fields = tuple(category.get("fields", ()))
    values = [numeric_value(record.get(field), 0.0) for field in fields]
    return sum(values) / len(values) if values else 0.0


def category_grades(record: dict, categories: Iterable[dict] | None = None) -> dict[str, str]:
    return {
        str(category.get("id")): rank_for_average(category_average(record, category))
        for category in (categories or TUNER_CATEGORIES)
    }


def entity_category_grades(player: object, categories: Iterable[dict] | None = None) -> dict[str, str]:
    data = getattr(player, "data", {})
    raw = data.get("raw", {}) if isinstance(data, dict) else {}
    japanese_record: dict[str, object] = {}
    if isinstance(raw, dict):
        for category in (categories or TUNER_CATEGORIES):
            for field in category.get("fields", ()):
                canonical = JAPANESE_TO_CANONICAL.get(str(field), str(field))
                japanese_record[str(field)] = raw.get(canonical, raw.get(field, 0))
    return category_grades(japanese_record, categories)


def compact_entity_grade_text(player: object, categories: Iterable[dict] | None = None) -> str:
    selected = tuple(categories or TUNER_CATEGORIES)
    grades = entity_category_grades(player, selected)
    return "  ".join(
        f"{category.get('short', category.get('label', '?'))}{grades.get(str(category.get('id')), 'E-')}"
        for category in selected
    )
