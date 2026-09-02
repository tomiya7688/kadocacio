from __future__ import annotations

import json
from copy import deepcopy

from scripts.core.paths import TEMPLATE_DIR
from scripts.core.stat_scale import PLAYER_GRADE_THRESHOLDS, PLAYER_STAT_DEFAULT, PLAYER_STAT_INITIAL

FALLBACK_EDITOR_OPTIONS = {
    "team_defaults": {
        "チーム名": "新規チーム", "チームの略称": "NEW", "監督名": "",
        "チームカラー": "#D84442", "戦術": "バランス", "ゾーン手前": "3",
        "ゾーン奥": "7", "戦術への忠実さ": "50",
        "ホームコート": "新規チームホーム",
    },
    "tabs": [
        {"id": "TEAM", "label": "チーム情報"}, {"id": "INTRO", "label": "チーム紹介"},
        {"id": "UNIFORM", "label": "ユニフォーム"}, {"id": "PLAYER", "label": "選手能力"},
        {"id": "SKILLS", "label": "スキル一覧"}, {"id": "FORMATION", "label": "フォーメーション"},
        {"id": "TUNER", "label": "チューナー"}, {"id": "ERRORS", "label": "エラー"},
    ],
    "team_templates": [
        {"id": "initial", "label": "初期値テンプレート", "description": f"選手1〜11・全能力{PLAYER_STAT_INITIAL}"},
        {"id": "random", "label": "ランダムテンプレート", "description": "能力値を0〜5500で生成"},
    ],
    "spread_options": ["小", "中", "大"],
    "uniform_palette": [
        "#FFFFFF", "#111827", "#D84442", "#2463A7", "#F1C232", "#2E8B57",
        "#8E44AD", "#F28C28", "#74C0FC", "#F4A6C1", "#7F8C8D", "#7A4B2A",
        "#00A6A6", "#EDE6D6", "#B8E986", "#F5F5F5",
    ],
    "generation_categories": [],
    "generation_profiles": [
        {"id": "balanced", "label": "バランス", "description": "全分野を均等に生成", "modifiers": {}},
    ],
}

FALLBACK_TUNER_OPTIONS = {
    "default_target": round(PLAYER_STAT_DEFAULT),
    "default_time_limit_seconds": 600,
    "minimum_time_limit_seconds": 1,
    "maximum_time_limit_seconds": 3600,
    "simulation_budget_ms_per_frame": 9,
    "headless_clock_acceleration": 1.0,
    "worker_match_time_limit_seconds": 300.0,
    "accuracy_minimum_time_limit_seconds": 600,
    "adaptive_opponent_limit": 3,
    "default_evaluation_mode": "精度重視",
    "speed_evaluation_minutes": 5.0,
    "hidden_parameters_default": True,
    "convergence_stagnant_trials": 4,
    "minimum_score_improvement": 0.10,
    "speed_max_trials": 16,
    "rank_thresholds": list(PLAYER_GRADE_THRESHOLDS),
    "categories": [],
}


def _load_json(name: str, fallback: dict) -> dict:
    path = TEMPLATE_DIR / name
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            value = json.load(file)
        if isinstance(value, dict):
            merged = deepcopy(fallback)
            merged.update(value)
            return merged
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return deepcopy(fallback)


def load_editor_options() -> dict:
    """Reload editable choices whenever the team editor is opened."""
    return _load_json("editor_options.json", FALLBACK_EDITOR_OPTIONS)


def load_tuner_options() -> dict:
    return _load_json("tuner_defaults.json", FALLBACK_TUNER_OPTIONS)
