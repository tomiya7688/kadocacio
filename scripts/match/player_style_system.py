from __future__ import annotations


PLAYER_TYPES = (
    "バックアップ",
    "スイーパー",
    "ストッパー",
    "マンマーカー",
    "リベロ",
    "オールラウンド",
    "ダイナモ",
    "レジスタ",
    "アタッカー",
    "チャンスメーカー",
    "ストライカー",
)

STYLE_FIELDS = {
    "zone_marking": "ZoneMarking",
    "man_marking": "ManMarking",
    "pressing": "Pressing",
    "shot_blocking": "ShotBlocking",
    "interception": "Interception",
    "support": "Support",
    "triangle": "Triangle",
    "lose_mark": "LoseMark",
    "overlap": "Overlap",
    "diagonal_run": "DiagonalRun",
    "run_into_space": "RunIntoSpace",
    "goal_poaching": "GoalPoaching",
}


def _style(**values: float) -> dict[str, float]:
    base = {key: 0.50 for key in STYLE_FIELDS}
    base.update(values)
    return base


TYPE_PREFERENCES = {
    "バックアップ": _style(zone_marking=0.94, shot_blocking=0.98, pressing=0.32, man_marking=0.42),
    "スイーパー": _style(zone_marking=0.92, pressing=0.78, shot_blocking=0.72, interception=0.68),
    "ストッパー": _style(man_marking=0.94, pressing=0.90, interception=0.58, zone_marking=0.38),
    "マンマーカー": _style(man_marking=0.97, interception=0.88, pressing=0.62, zone_marking=0.35),
    "リベロ": _style(zone_marking=0.86, shot_blocking=0.72, overlap=0.72, run_into_space=0.76, goal_poaching=0.64),
    "オールラウンド": _style(man_marking=0.76, support=0.90, triangle=0.72, pressing=0.65),
    "ダイナモ": _style(overlap=0.97, lose_mark=0.86, run_into_space=0.95, pressing=0.68, support=0.65),
    "レジスタ": _style(support=0.98, triangle=0.98, interception=0.62, overlap=0.36),
    "アタッカー": _style(overlap=0.88, run_into_space=0.94, goal_poaching=0.90, lose_mark=0.70),
    "チャンスメーカー": _style(lose_mark=0.96, diagonal_run=0.96, goal_poaching=0.76, support=0.68, triangle=0.64),
    "ストライカー": _style(lose_mark=0.90, goal_poaching=0.99, run_into_space=0.92, support=0.38, pressing=0.38),
}

LEGACY_TYPE_MAP = {
    "セカンドトップ": "チャンスメーカー",
    "ウイング": "アタッカー",
    "プレイメーカー": "レジスタ",
    "サイドバック": "ダイナモ",
    "ゴールキーパー": "バックアップ",
    "ドリブラー": "チャンスメーカー",
}


def normalize_player_type(value: object, role: str) -> str:
    label = str(value or "").strip()
    label = LEGACY_TYPE_MAP.get(label, label)
    if label in TYPE_PREFERENCES:
        return label
    return {"GK": "バックアップ", "DF": "スイーパー", "MF": "オールラウンド", "FW": "ストライカー"}.get(
        role,
        "オールラウンド",
    )


def type_preference(player_type: str, behavior: str) -> float:
    return TYPE_PREFERENCES.get(player_type, TYPE_PREFERENCES["オールラウンド"]).get(behavior, 0.50)


def combined_preference(player_type: str, behavior: str, parameter: float) -> float:
    """The explicit stat leads; player type remains a strong behavioral prior."""
    parameter = max(0.0, min(1.0, parameter))
    return max(0.0, min(1.0, parameter * 0.62 + type_preference(player_type, behavior) * 0.38))

