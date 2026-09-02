from __future__ import annotations

import random
import time
import math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from multiprocessing import get_context
import os

from scripts.match.match_engine import Match
from scripts.match.player_style_system import STYLE_FIELDS, TYPE_PREFERENCES
from scripts.core.settings import FIELD, MATCH_SECONDS, clamp
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.core.cpu_usage_limiter import CpuUsageLimiter
from scripts.core.performance_settings import (
    limited_worker_count,
    normalize_cpu_limit,
    worker_duty_cycle,
)
from scripts.core.stat_scale import (
    LEGACY_PLAYER_STAT_MAX,
    LEGACY_PLAYER_STAT_MIN,
    PLAYER_STAT_DEFAULT,
    PLAYER_STAT_MAX,
    PLAYER_STAT_MEAN_TOLERANCE,
    PLAYER_STAT_MIN,
    current_to_legacy_player_stat,
    legacy_player_stat,
    legacy_player_stat_delta,
)
from scripts.team.team_data import team_choice_from_payload
from scripts.team.team_rating import category_average, rank_for_average


HIDDEN_BEHAVIOR_BY_FIELD = {field: behavior for behavior, field in STYLE_FIELDS.items()}


def automatic_opponent_priority(metrics: dict[str, float]) -> tuple[float, str, float]:
    """Return (raw weight, readable class, competitive signal).

    A slightly stronger but reachable opponent receives the highest priority.
    Matches already won by a large margin and opponents currently far beyond
    reach remain in the sample, but do not dominate the optimizer.
    """
    goal_difference = float(metrics.get("得点", 0.0)) - float(metrics.get("失点", 0.0))
    shot_difference = float(metrics.get("シュート", 0.0)) - float(metrics.get("被シュート", 0.0))
    possession_edge = (float(metrics.get("支配率", 50.0)) - 50.0) / 18.0
    signal = goal_difference + shot_difference * 0.14 + possession_edge * 0.35
    closeness = math.exp(-abs(signal) / 1.8)
    reachable_loss_bonus = 0.0
    if signal < -0.10:
        reachable_loss_bonus = 0.58 * math.exp(-((signal + 0.75) / 1.05) ** 2)
    close_win_bonus = 0.0
    if signal >= -0.10:
        close_win_bonus = 0.24 * math.exp(-((signal - 0.65) / 1.05) ** 2)
    weight = clamp(0.55 + closeness * 1.10 + reachable_loss_bonus + close_win_bonus, 0.45, 2.25)
    if signal < -2.50:
        label = "格上（差が大きい）"
    elif signal < -0.10:
        label = "勝てそうな格上"
    elif signal <= 0.15:
        label = "互角"
    elif signal <= 1.60:
        label = "僅差で勝っている"
    elif signal <= 3.00:
        label = "優勢"
    else:
        label = "大幅優勢"
    return weight, label, signal

ROLE_FIELD_BOOSTS = {
    "GK": {
        "ゴールストップ力": 1.28, "トラップの上手さ": 1.12, "ジャンプの正確さ": 1.12,
        "ジャンプの判断力": 1.14, "ゴールキック": 1.16, "パス力": 1.08,
        "シュート力": 0.72, "シュートの上手さ": 0.70, "ドリブル時のスピード": 0.78,
        "ゴール前待機": 0.62, "オーバーラップ": 0.64,
    },
    "DF": {
        "パスカットの上手さ": 1.12, "スティールの上手さ": 1.12,
        "ジャンプの高さ": 1.08, "ヘディングの判断力": 1.09,
        "ゾーンマーキング": 1.12, "マンツーマン": 1.10, "シュートカット": 1.14,
        "インターセプト": 1.12, "シュート力": 0.84, "ゴール前待機": 0.78,
    },
    "MF": {
        "パス精度": 1.10, "パス力": 1.06, "パスの上手さ": 1.12,
        "スタミナ最大値": 1.08, "スタミナ管理": 1.07,
        "サポート": 1.10, "トライアングル": 1.12, "インテリジェンス": 1.06,
    },
    "FW": {
        "シュート力": 1.12, "シュート精度": 1.12, "シュートの上手さ": 1.14,
        "ダッシュ時のスピード": 1.08, "ドリブル時のスピード": 1.08,
        "ドリブルの上手さ": 1.08, "ゴール前待機": 1.15,
        "マークを外す": 1.10, "スペースに走り込む": 1.12,
        "ゴールストップ力": 0.58, "ゾーンマーキング": 0.82,
    },
}

TYPE_GENERAL_BOOSTS = {
    "バックアップ": {"シュートカット": 1.12, "ゾーンマーキング": 1.10},
    "スイーパー": {"プレッシング": 1.08, "インターセプト": 1.08},
    "ストッパー": {"マンツーマン": 1.13, "プレッシング": 1.12},
    "マンマーカー": {"マンツーマン": 1.14, "インターセプト": 1.11},
    "リベロ": {"ゾーンマーキング": 1.08, "オーバーラップ": 1.08},
    "オールラウンド": {"サポート": 1.08, "スタミナ最大値": 1.06},
    "ダイナモ": {"ダッシュ時のスピード": 1.10, "スタミナ最大値": 1.10, "オーバーラップ": 1.12},
    "レジスタ": {"パス精度": 1.12, "パスの上手さ": 1.14, "トライアングル": 1.12},
    "アタッカー": {"ドリブル時のスピード": 1.08, "スペースに走り込む": 1.12},
    "チャンスメーカー": {"ドリブルの上手さ": 1.10, "パスの上手さ": 1.10, "ダイアゴナルラン": 1.12},
    "ストライカー": {"シュート力": 1.12, "シュート精度": 1.12, "シュートの上手さ": 1.14, "ゴール前待機": 1.14},
}


def _number(value: object, default: float = PLAYER_STAT_DEFAULT) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _player_role(player: dict) -> str:
    role = str(player.get("ポジション", ""))
    if role in ("GK", "DF", "MF", "FW"):
        return role
    try:
        position_y = int(player.get("ポジションY", 0))
    except (TypeError, ValueError):
        return "MF"
    if position_y == 11:
        return "GK"
    if position_y <= 3:
        return "FW"
    if position_y <= 7:
        return "MF"
    return "DF"


def _field_factor(player: dict, field: str) -> float:
    role = _player_role(player)
    player_type = str(player.get("プレイヤータイプ", "オールラウンド"))
    factor = ROLE_FIELD_BOOSTS.get(role, {}).get(field, 1.0)
    factor *= TYPE_GENERAL_BOOSTS.get(player_type, {}).get(field, 1.0)
    behavior = HIDDEN_BEHAVIOR_BY_FIELD.get(field)
    if behavior is not None:
        preference = TYPE_PREFERENCES.get(player_type, TYPE_PREFERENCES["オールラウンド"]).get(behavior, 0.5)
        factor *= 0.80 + preference * 0.40
    return clamp(factor, 0.58, 1.38)


def _normalize_cells(cells: list[tuple[dict, str]], target: float) -> None:
    if not cells:
        return
    values = [clamp(_number(player.get(field), target), PLAYER_STAT_MIN, PLAYER_STAT_MAX) for player, field in cells]
    for _ in range(40):
        difference = target - sum(values) / len(values)
        if abs(difference) < 0.35:
            break
        values = [clamp(value + difference, PLAYER_STAT_MIN, PLAYER_STAT_MAX) for value in values]
    integers = [round(value) for value in values]
    remaining = round(target * len(integers)) - sum(integers)
    direction = 1 if remaining > 0 else -1
    cursor = 0
    while remaining != 0 and cursor < len(integers) * 4:
        index = cursor % len(integers)
        candidate = integers[index] + direction
        if PLAYER_STAT_MIN <= candidate <= PLAYER_STAT_MAX:
            integers[index] = candidate
            remaining -= direction
        cursor += 1
    for (player, field), value in zip(cells, integers):
        player[field] = str(value)


def auto_adjust_payload(
    payload: dict,
    targets: dict[str, int],
    categories: tuple[dict, ...] | list[dict],
    *,
    player_indices: list[int] | None = None,
    include_hidden: bool = True,
    rng: random.Random | None = None,
    mutation: float = 0.0,
) -> int:
    """Role/type-aware adjustment while preserving each requested group mean."""
    rng = rng or random.Random()
    players = payload.get("選手一覧", [])
    if not isinstance(players, list):
        return 0
    selected = [
        player for index, player in enumerate(players)
        if isinstance(player, dict) and (player_indices is None or index in player_indices)
    ]
    changes = 0
    for category in categories:
        if category.get("hidden") and not include_hidden:
            continue
        category_id = str(category.get("id"))
        target = clamp(float(targets.get(category_id, PLAYER_STAT_DEFAULT)), PLAYER_STAT_MIN, PLAYER_STAT_MAX)
        legacy_target = current_to_legacy_player_stat(target)
        cells: list[tuple[dict, str]] = []
        for player in selected:
            for field in category.get("fields", ()):
                factor = _field_factor(player, str(field))
                # Keep the old role/type distribution exactly equivalent by
                # generating in the legacy domain, then mapping to the active
                # editable scale.
                jitter = rng.gauss(0.0, legacy_target * (0.018 + mutation))
                legacy_value = clamp(
                    legacy_target * factor + jitter,
                    LEGACY_PLAYER_STAT_MIN,
                    LEGACY_PLAYER_STAT_MAX,
                )
                value = legacy_player_stat(legacy_value)
                if str(player.get(field, "")) != str(round(value)):
                    changes += 1
                player[str(field)] = str(round(value))
                cells.append((player, str(field)))
        _normalize_cells(cells, target)
    return changes


def payload_category_summary(payload: dict, categories: tuple[dict, ...] | list[dict]) -> dict[str, tuple[float, str]]:
    players = [player for player in payload.get("選手一覧", []) if isinstance(player, dict)]
    result: dict[str, tuple[float, str]] = {}
    for category in categories:
        values = [category_average(player, category) for player in players]
        average = sum(values) / len(values) if values else 0.0
        result[str(category.get("id"))] = (average, rank_for_average(average))
    return result


def category_mean_values(payload: dict, categories: tuple[dict, ...] | list[dict]) -> dict[str, float]:
    return {
        category_id: float(summary[0])
        for category_id, summary in payload_category_summary(payload, categories).items()
    }


def enforce_category_mean_limits(
    payload: dict,
    baseline_means: dict[str, float],
    categories: tuple[dict, ...] | list[dict],
    *,
    include_hidden: bool,
    tolerance: float = PLAYER_STAT_MEAN_TOLERANCE,
) -> None:
    """Keep optimizer candidates within ±tolerance of their starting means."""
    players = [player for player in payload.get("選手一覧", []) if isinstance(player, dict)]
    current_means = category_mean_values(payload, categories)
    for category in categories:
        if category.get("hidden") and not include_hidden:
            continue
        category_id = str(category.get("id"))
        baseline = float(baseline_means.get(category_id, current_means.get(category_id, PLAYER_STAT_DEFAULT)))
        current = float(current_means.get(category_id, baseline))
        if baseline - tolerance <= current <= baseline + tolerance:
            continue
        cells = [
            (player, str(field))
            for player in players
            for field in category.get("fields", ())
        ]
        _normalize_cells(cells, baseline)


def mutate_payload_distribution(
    payload: dict,
    categories: tuple[dict, ...] | list[dict],
    *,
    include_hidden: bool,
    rng: random.Random,
    strength: float = 0.07,
) -> int:
    """Move ability points inside each category without changing its total budget.

    The tuner is allowed to discover uneven allocations inside a category.
    Only the category-wide mean is a constraint; player
    averages and individual fields are deliberately free to move.
    """
    players = [player for player in payload.get("選手一覧", []) if isinstance(player, dict)]
    changes = 0
    strength = clamp(float(strength), 0.01, 0.22)
    for category in categories:
        if category.get("hidden") and not include_hidden:
            continue
        cells = [
            (player, str(field))
            for player in players
            for field in category.get("fields", ())
        ]
        if len(cells) < 2:
            continue
        category_mean = sum(_number(player.get(field)) for player, field in cells) / len(cells)
        transfer_count = max(1, round(len(cells) * (0.035 + strength * 0.42)))
        for _ in range(transfer_count):
            first_index, second_index = rng.sample(range(len(cells)), 2)
            first, second = cells[first_index], cells[second_index]
            first_factor = _field_factor(*first)
            second_factor = _field_factor(*second)
            # Usually move points toward the role/type-favoured cell, while
            # retaining exploration so the match engine can overturn heuristics.
            if rng.random() < 0.68:
                receiver, donor = (first, second) if first_factor >= second_factor else (second, first)
            else:
                receiver, donor = (first, second) if rng.random() < 0.5 else (second, first)
            receiver_value = round(_number(receiver[0].get(receiver[1]), category_mean))
            donor_value = round(_number(donor[0].get(donor[1]), category_mean))
            transferable = min(PLAYER_STAT_MAX - receiver_value, donor_value - PLAYER_STAT_MIN)
            if transferable <= 0:
                continue
            legacy_mean = current_to_legacy_player_stat(category_mean)
            typical = max(
                legacy_player_stat_delta(4.0),
                legacy_player_stat_delta(legacy_mean * strength * 0.55),
            )
            amount = min(transferable, max(1, round(abs(rng.gauss(typical, typical * 0.42)))))
            receiver[0][receiver[1]] = str(receiver_value + amount)
            donor[0][donor[1]] = str(donor_value - amount)
            changes += 2
    return changes


def _score_match_sample(match: Match, target, command_counts: Counter[str], active_samples: int, total_samples: int) -> tuple[float, dict[str, float]]:
    opponent = match.away if target is match.home else match.home
    fraction = clamp(match.game_time / MATCH_SECONDS, 0.08, 1.0)
    goal_difference = (target.score - opponent.score) / fraction
    shot_difference = (target.shots - opponent.shots) / fraction
    possession_total = target.possession + opponent.possession
    possession_share = target.possession / possession_total if possession_total else 0.5
    stamina_ratio = sum(player.stamina_ratio for player in target.players) / max(1, len(target.players))
    active_ratio = active_samples / max(1, total_samples)
    action_diversity = len(command_counts)
    score = (
        goal_difference * 4.8
        + shot_difference * 0.16
        + (possession_share - 0.5) * 4.0
        + stamina_ratio * 0.35
        + min(action_diversity, 12) * 0.018
        - abs(active_ratio - 0.68) * 0.25
    )
    if match.state == "FULLTIME":
        score += 1.1 if target.score > opponent.score else -0.8 if target.score < opponent.score else 0.15
    return score, {
        "得点": float(target.score), "失点": float(opponent.score),
        "シュート": float(target.shots), "被シュート": float(opponent.shots),
        "支配率": possession_share * 100.0, "残スタミナ": stamina_ratio * 100.0,
        "行動種類": float(action_diversity), "活動率": active_ratio * 100.0,
        "進行率": fraction * 100.0,
    }


def _simulate_tuner_job(job: dict) -> dict:
    """Evaluate one candidate across every opponent, home and away.

    All candidates use the same fixture seeds. Matches are advanced round-robin,
    so even a time-limited result compares candidates at similar match progress.
    """
    candidate = job["candidate"]
    cpu_limiter = CpuUsageLimiter(job.get("cpu_duty_cycle", 1.0))
    choice = team_choice_from_payload(candidate, "<team-tuner-worker>")
    choice.update({"id": "memory:tuner-worker", "kind": "MEMORY", "short": choice.get("short") or "TUNE"})
    fixtures = []
    seeds = list(job.get("fixture_seeds", ()))
    seed_index = 0
    venues = tuple(job.get("venues", (True, False)))
    for opponent_choice in job["opponents"]:
        for is_home in venues:
            if is_home:
                match = Match(choice, opponent_choice, "HOME")
                target = match.home
            else:
                match = Match(opponent_choice, choice, "HOME")
                target = match.away
            seed = seeds[seed_index] if seed_index < len(seeds) else seed_index
            seed_index += 1
            match.rng.seed(int(seed))
            match.state = "PLAYING"
            fixtures.append({
                "match": match, "target": target, "counts": Counter(),
                "active": 0, "samples": 0, "counter": 0,
            })
    worker_deadline = time.perf_counter() + max(1.0, float(job["wall_time_limit"]))
    evaluation_target = clamp(float(job.get("target_game_time", MATCH_SECONDS)), 60.0, MATCH_SECONDS)
    while time.perf_counter() < worker_deadline and any(
        item["match"].state != "FULLTIME" and item["match"].game_time < evaluation_target
        for item in fixtures
    ):
        for item in fixtures:
            match = item["match"]
            if match.state == "FULLTIME" or match.game_time >= evaluation_target:
                continue
            # Headless does not mean clock-only acceleration.  Use the exact
            # same fixed physics/AI step as a visible match so every simulated
            # minute contains the normal number of decisions and contacts.
            advance_match_fixed(match)
            cpu_limiter.throttle()
            item["counter"] += 1
            if item["counter"] % 18 == 0:
                for player in item["target"].players:
                    command = getattr(player.action_command, "value", str(player.action_command))
                    item["counts"][str(command)] += 1
                    item["samples"] += 1
                    if command not in ("待機", "ポジションへ戻る", "ポジションを保つ"):
                        item["active"] += 1
            if time.perf_counter() >= worker_deadline:
                break
    scores = []
    metric_rows = []
    for item in fixtures:
        score, metrics = _score_match_sample(
            item["match"], item["target"], item["counts"], item["active"], item["samples"],
        )
        scores.append(score)
        metric_rows.append(metrics)
    metric_names = metric_rows[0].keys() if metric_rows else ()
    aggregate_metrics = {
        name: sum(row[name] for row in metric_rows) / len(metric_rows)
        for name in metric_names
    }
    completed_matches = sum(
        item["match"].state == "FULLTIME" or item["match"].game_time >= evaluation_target
        for item in fixtures
    )
    return {
        "opponent_key": str(job.get("opponent_key", "")),
        "score": sum(scores) / max(1, len(scores)),
        "completed_matches": completed_matches,
        "fixture_count": len(fixtures),
        "evaluation_target": evaluation_target,
        "metrics": aggregate_metrics,
    }


class TeamTunerSession:
    """Incremental, UI-friendly optimizer that runs the real Match engine headlessly."""

    def __init__(
        self,
        payload: dict,
        opponents: list[dict],
        targets: dict[str, int],
        categories: tuple[dict, ...] | list[dict],
        *,
        time_limit: float | None,
        include_hidden: bool,
        stagnant_limit: int = 6,
        clock_acceleration: float = 10.0,
        worker_count: int = 0,
        max_workers: int = 4,
        cpu_limit_percent: int = 100,
        worker_match_time_limit: float = 8.0,
        adaptive_opponent_limit: int = 5,
        evaluation_mode: str = "accuracy",
        speed_evaluation_minutes: float = 10.0,
        minimum_score_improvement: float = 0.10,
        speed_max_trials: int = 16,
        rng: random.Random | None = None,
    ) -> None:
        if not opponents:
            raise ValueError("対戦相手を1チーム以上選択してください")
        self.rng = rng or random.Random()
        self.categories = tuple(categories)
        self.configured_targets = dict(targets)
        self.opponents = list(opponents)
        self.opponent_names = {
            str(choice.get("id") or choice.get("name") or index): str(choice.get("name", "対戦相手"))
            for index, choice in enumerate(self.opponents)
        }
        self.opponent_weights = {key: 1.0 for key in self.opponent_names}
        self.opponent_classes = {key: "偵察前" for key in self.opponent_names}
        self.opponent_signals = {key: 0.0 for key in self.opponent_names}
        self.opponent_weights_ready = False
        self.adaptive_opponent_limit = max(2, int(adaptive_opponent_limit))
        self.evaluation_mode = "speed" if str(evaluation_mode).lower() == "speed" else "accuracy"
        self.speed_evaluation_game_time = clamp(float(speed_evaluation_minutes) * 60.0, 60.0, MATCH_SECONDS)
        self.minimum_score_improvement = max(0.01, float(minimum_score_improvement))
        self.speed_max_trials = max(4, int(speed_max_trials))
        self.active_opponent_keys = set(self.opponent_names)
        self.include_hidden = include_hidden
        self.convergence_only = time_limit is None
        self.time_limit = None if self.convergence_only else max(0.1, float(time_limit))
        # One candidate already contains every selected fixture (accuracy) or
        # every active priority fixture (speed).  Scaling the number of
        # consecutive rejected candidates by opponent count made convergence
        # explode from minutes to hours without adding statistical confidence.
        self.stagnant_limit = max(3, int(stagnant_limit))
        # Kept as an input for compatibility with existing template files.
        # It no longer skips the match clock; doing so invalidated AI results.
        self.clock_acceleration = clamp(float(clock_acceleration), 1.0, 30.0)
        self.started_at = time.perf_counter()
        self.deadline = float("inf") if self.convergence_only else self.started_at + self.time_limit
        self.best_payload = deepcopy(payload)
        # Match optimization redistributes ability between players but must not
        # inflate (or deflate) the team's category budgets.  The explicit
        # "基準値へ調整" buttons remain the only operation that changes them.
        self.locked_category_means = category_mean_values(payload, self.categories)
        self.targets = dict(self.locked_category_means)
        self.mean_tolerance = PLAYER_STAT_MEAN_TOLERANCE
        self.best_scores: dict[str, float] = {}
        self.best_score = float("-inf")
        # Every candidate is tested with the same seeds, eliminating most of the
        # random-match advantage that previously caused weak candidates to win.
        self.fixture_seeds = tuple(
            self.rng.randrange(0, 2**31) for _ in range(len(self.opponents) * 2)
        )
        self.trials = 0
        self.completed_matches = 0
        self.stagnant_trials = 0
        self.accepted_trials = 0
        self.finished = False
        self.cancelled = False
        self.finish_reason = ""
        self.current_match: Match | None = None
        self.current_target_team = None
        self.current_candidate: dict | None = None
        self.current_opponent: dict | None = None
        self.current_opponent_name = ""
        self.current_is_home = True
        self.sample_counter = 0
        self.command_counts: Counter[str] = Counter()
        self.active_samples = 0
        self.total_player_samples = 0
        self.last_metrics: dict[str, float] = {}
        self.last_score = 0.0
        self.cpu_limit_percent = normalize_cpu_limit(cpu_limit_percent)
        requested_workers = int(worker_count)
        cpu_workers = max(1, (os.cpu_count() or 2) - 1)
        if requested_workers <= 0:
            requested_workers = cpu_workers
        full_worker_budget = max(1, min(requested_workers, int(max_workers), cpu_workers))
        self.parallel_worker_count = limited_worker_count(full_worker_budget, self.cpu_limit_percent)
        self.worker_duty_cycle = worker_duty_cycle(
            full_worker_budget, self.cpu_limit_percent, self.parallel_worker_count,
        )
        self.worker_match_time_limit = max(
            1.0,
            float(worker_match_time_limit) if self.convergence_only else min(float(worker_match_time_limit), self.time_limit),
        )
        self.parallel_enabled = self.parallel_worker_count > 1
        self.executor: ProcessPoolExecutor | None = None
        self.pending_trials: dict = {}
        self.active_parallel_candidate: dict | None = None
        self.active_parallel_results: list[dict] = []
        self.active_parallel_expected = 0
        self.parallel_failures = 0
        if self.parallel_enabled:
            try:
                self.executor = ProcessPoolExecutor(
                    max_workers=self.parallel_worker_count,
                    mp_context=get_context("spawn"),
                )
                self._submit_parallel_trials()
            except (OSError, RuntimeError):
                self.parallel_enabled = False
                self.executor = None
                self._begin_trial()
        else:
            self._begin_trial()

    @property
    def elapsed(self) -> float:
        return max(0.0, time.perf_counter() - self.started_at)

    @property
    def progress(self) -> float:
        if self.parallel_enabled and self.active_parallel_expected > 0 and self.pending_trials:
            finished = max(0, self.active_parallel_expected - len(self.pending_trials))
            return clamp(finished / self.active_parallel_expected, 0.0, 1.0)
        if self.convergence_only:
            return clamp(self.stagnant_trials / max(1, self.stagnant_limit), 0.0, 1.0)
        return clamp(self.elapsed / self.time_limit, 0.0, 1.0)

    def _begin_trial(self) -> None:
        fixture_index = self.trials % (len(self.opponents) * 2)
        opponent_index = fixture_index // 2
        self.current_opponent = self.opponents[opponent_index]
        self.current_opponent_name = str(self.current_opponent.get("name", "対戦相手"))
        self.current_is_home = fixture_index % 2 == 0
        candidate = deepcopy(self.best_payload)
        if self.trials > 0:
            strength = max(0.025, 0.085 * (0.94 ** min(self.accepted_trials, 20)))
            mutate_payload_distribution(
                candidate, self.categories,
                include_hidden=self.include_hidden, rng=self.rng, strength=strength,
            )
            enforce_category_mean_limits(
                candidate, self.locked_category_means, self.categories,
                include_hidden=self.include_hidden, tolerance=self.mean_tolerance,
            )
        choice = team_choice_from_payload(candidate, "<team-tuner>")
        choice.update({"id": "memory:tuner", "kind": "MEMORY", "short": choice.get("short") or "TUNE"})
        if self.current_is_home:
            match = Match(choice, self.current_opponent, "HOME")
            target_team = match.home
        else:
            match = Match(self.current_opponent, choice, "HOME")
            target_team = match.away
        match.rng.seed(self.fixture_seeds[fixture_index])
        match.state = "PLAYING"
        self.current_candidate = candidate
        self.current_match = match
        self.current_target_team = target_team
        self.sample_counter = 0
        self.command_counts.clear()
        self.active_samples = 0
        self.total_player_samples = 0

    def _make_parallel_candidate(self, trial_index: int) -> dict:
        candidate = deepcopy(self.best_payload)
        if trial_index > 0:
            strength = max(0.025, 0.085 * (0.94 ** min(self.accepted_trials, 20)))
            if self.stagnant_trials >= max(2, self.stagnant_limit // 2):
                strength = min(0.14, strength * 1.45)
            mutate_payload_distribution(
                candidate, self.categories,
                include_hidden=self.include_hidden, rng=self.rng, strength=strength,
            )
            enforce_category_mean_limits(
                candidate, self.locked_category_means, self.categories,
                include_hidden=self.include_hidden, tolerance=self.mean_tolerance,
            )
        return candidate

    def _calibrate_opponent_weights(self, results: list[dict]) -> None:
        """Lock automatic weights from the unmodified team's first fixture set."""
        grouped: dict[str, list[dict[str, float]]] = {}
        for result in results:
            key = str(result.get("opponent_key", ""))
            if key:
                grouped.setdefault(key, []).append(result.get("metrics", {}))
        if len(grouped) != len(self.opponents):
            return
        raw_weights: dict[str, float] = {}
        for key, rows in grouped.items():
            metric_names = set().union(*(row.keys() for row in rows))
            averaged = {
                name: sum(float(row.get(name, 0.0)) for row in rows) / len(rows)
                for name in metric_names
            }
            raw_weight, label, signal = automatic_opponent_priority(averaged)
            raw_weights[key] = raw_weight
            self.opponent_classes[key] = label
            self.opponent_signals[key] = signal
        normalizer = len(raw_weights) / max(0.001, sum(raw_weights.values()))
        self.opponent_weights = {
            key: clamp(weight * normalizer, 0.35, 2.40)
            for key, weight in raw_weights.items()
        }
        ranked_keys = sorted(
            self.opponent_weights,
            key=lambda key: (self.opponent_weights[key], -abs(self.opponent_signals.get(key, 0.0))),
            reverse=True,
        )
        opponent_limit = max(2, int(getattr(self, "adaptive_opponent_limit", 5)))
        if getattr(self, "evaluation_mode", "accuracy") == "accuracy":
            self.active_opponent_keys = set(ranked_keys)
        else:
            self.active_opponent_keys = set(ranked_keys[:min(opponent_limit, len(ranked_keys))])
        self.opponent_weights_ready = True

    def opponent_weight_info(self, choice: dict) -> tuple[float, str]:
        key = str(choice.get("id") or choice.get("name") or "")
        weights = getattr(self, "opponent_weights", {})
        classes = getattr(self, "opponent_classes", {})
        return weights.get(key, 1.0), classes.get(key, "偵察前")

    def opponent_is_active(self, choice: dict) -> bool:
        key = str(choice.get("id") or choice.get("name") or "")
        return key in getattr(self, "active_opponent_keys", set())

    def _result_weight(self, result: dict) -> float:
        weights = getattr(self, "opponent_weights", {})
        return weights.get(str(result.get("opponent_key", "")), 1.0)

    def _submit_parallel_trials(self) -> None:
        if self.executor is None or self.finished or self.active_parallel_candidate is not None:
            return
        if time.perf_counter() >= self.deadline:
            return
        candidate = self._make_parallel_candidate(self.trials)
        self.active_parallel_candidate = candidate
        self.active_parallel_results = []
        if self.opponent_weights_ready:
            opponent_indexes = [
                index for index, opponent in enumerate(self.opponents)
                if str(opponent.get("id") or opponent.get("name") or index) in self.active_opponent_keys
            ]
        else:
            opponent_indexes = list(range(len(self.opponents)))
        self.active_parallel_expected = len(opponent_indexes) * 2
        for opponent_index in opponent_indexes:
            opponent = self.opponents[opponent_index]
            for venue_index, is_home in enumerate((True, False)):
                fixture_index = opponent_index * 2 + venue_index
                job = {
                    "candidate": candidate,
                    "opponents": [opponent],
                    "venues": [is_home],
                    "fixture_seeds": [self.fixture_seeds[fixture_index]],
                    "opponent_key": str(opponent.get("id") or opponent.get("name") or opponent_index),
                    "clock_acceleration": self.clock_acceleration,
                    "wall_time_limit": self.worker_match_time_limit,
                    "target_game_time": self.speed_evaluation_game_time if self.evaluation_mode == "speed" else MATCH_SECONDS,
                    "cpu_duty_cycle": self.worker_duty_cycle,
                }
                future = self.executor.submit(_simulate_tuner_job, job)
                self.pending_trials[future] = fixture_index

    def _stop_parallel_workers(self) -> None:
        for future in tuple(self.pending_trials):
            future.cancel()
        self.pending_trials.clear()
        self.active_parallel_candidate = None
        self.active_parallel_results = []
        self.active_parallel_expected = 0
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None

    def _step_parallel(self) -> None:
        completed = [future for future in self.pending_trials if future.done()]
        for future in completed:
            self.pending_trials.pop(future)
            try:
                result = future.result()
            except Exception:
                self.parallel_failures += 1
                continue
            self.active_parallel_results.append(result)
        if self.active_parallel_candidate is not None and not self.pending_trials:
            results = self.active_parallel_results
            expected = self.active_parallel_expected
            completed_matches = sum(int(result.get("completed_matches", 0)) for result in results)
            self.completed_matches += completed_matches
            if len(results) == expected and results:
                if completed_matches == expected and not self.opponent_weights_ready:
                    self._calibrate_opponent_weights(results)
                result_weights = [self._result_weight(result) for result in results]
                weight_total = max(0.001, sum(result_weights))
                score = sum(
                    float(result.get("score", -999.0)) * weight
                    for result, weight in zip(results, result_weights)
                ) / weight_total
                metric_names = set().union(*(result.get("metrics", {}).keys() for result in results))
                self.last_score = score
                self.last_metrics = {
                    name: sum(
                        float(result.get("metrics", {}).get(name, 0.0)) * weight
                        for result, weight in zip(results, result_weights)
                    ) / weight_total
                    for name in metric_names
                }
                # A partial match may be shown as progress, but it must never
                # decide an optimizer candidate or trigger convergence.
                if completed_matches == expected:
                    previous = self.best_score
                    improved = score > previous + (self.minimum_score_improvement if previous != float("-inf") else 0.0)
                    if improved:
                        self.best_score = score
                        self.best_payload = deepcopy(self.active_parallel_candidate)
                        self.accepted_trials += 1
                        self.stagnant_trials = 0
                    else:
                        self.stagnant_trials += 1
                else:
                    self.stagnant_trials = 0
            else:
                self.stagnant_trials += 1
            self.trials += 1
            self.active_parallel_candidate = None
            self.active_parallel_results = []
            self.active_parallel_expected = 0
        if self.parallel_failures >= self.parallel_worker_count and self.completed_matches == 0:
            self._stop_parallel_workers()
            self.parallel_enabled = False
            self._begin_trial()
            return
        if time.perf_counter() >= self.deadline:
            self.finished = True
            self.finish_reason = "時間上限に到達" if self.completed_matches else "時間上限に到達（完走試合なし）"
            self._stop_parallel_workers()
            return
        if (
            self.evaluation_mode == "speed"
            and self.trials >= self.speed_max_trials
            and self.completed_matches > 0
        ):
            self.finished = True
            self.finish_reason = "速度重視の探索候補上限に到達"
            self._stop_parallel_workers()
            return
        required_completed = max(1, len(self.active_opponent_keys)) * 2
        if self.stagnant_trials >= self.stagnant_limit and self.completed_matches >= required_completed:
            self.finished = True
            self.finish_reason = "結果がほぼ収束"
            self._stop_parallel_workers()
            return
        self._submit_parallel_trials()

    def _sample_movement(self) -> None:
        if self.current_target_team is None:
            return
        for player in self.current_target_team.players:
            command = getattr(player.action_command, "value", str(player.action_command))
            self.command_counts[str(command)] += 1
            self.total_player_samples += 1
            if command not in ("待機", "ポジションへ戻る", "ポジションを保つ"):
                self.active_samples += 1

    def _score_current(self, partial: bool = False) -> tuple[float, dict[str, float]]:
        match = self.current_match
        target = self.current_target_team
        if match is None or target is None:
            return -999.0, {}
        opponent = match.away if target is match.home else match.home
        fraction = clamp(match.game_time / MATCH_SECONDS, 0.08, 1.0)
        goal_difference = (target.score - opponent.score) / fraction
        shot_difference = (target.shots - opponent.shots) / fraction
        possession_total = target.possession + opponent.possession
        possession_share = target.possession / possession_total if possession_total else 0.5
        stamina_ratio = sum(player.stamina_ratio for player in target.players) / max(1, len(target.players))
        active_ratio = self.active_samples / max(1, self.total_player_samples)
        action_diversity = len(self.command_counts)
        score = (
            goal_difference * 4.8
            + shot_difference * 0.16
            + (possession_share - 0.5) * 4.0
            + stamina_ratio * 0.35
            + min(action_diversity, 12) * 0.018
            - abs(active_ratio - 0.68) * 0.25
        )
        if not partial:
            score += 1.1 if target.score > opponent.score else -0.8 if target.score < opponent.score else 0.15
        metrics = {
            "得点": float(target.score), "失点": float(opponent.score),
            "シュート": float(target.shots), "被シュート": float(opponent.shots),
            "支配率": possession_share * 100.0, "残スタミナ": stamina_ratio * 100.0,
            "行動種類": float(action_diversity), "活動率": active_ratio * 100.0,
            "進行率": fraction * 100.0,
        }
        return score, metrics

    def _complete_trial(self, partial: bool = False) -> None:
        score, metrics = self._score_current(partial)
        self.last_score = score
        self.last_metrics = metrics
        key = f"{self.current_opponent_name}:{'HOME' if self.current_is_home else 'AWAY'}"
        previous = self.best_scores.get(key, float("-inf"))
        improved = score > previous + (self.minimum_score_improvement if previous != float("-inf") else 0.0)
        if improved and self.current_candidate is not None:
            self.best_scores[key] = score
            self.best_payload = deepcopy(self.current_candidate)
            self.accepted_trials += 1
            self.stagnant_trials = 0
        else:
            self.stagnant_trials += 1
        self.trials += 1
        evaluation_finished = (
            self.current_match is not None
            and (
                self.current_match.state == "FULLTIME"
                or (
                    self.evaluation_mode == "speed"
                    and self.current_match.game_time >= self.speed_evaluation_game_time
                )
            )
        )
        if evaluation_finished:
            self.completed_matches += 1

    def step(self, budget_ms: float = 8.0) -> None:
        if self.finished:
            return
        if self.parallel_enabled:
            self._step_parallel()
            return
        frame_deadline = time.perf_counter() + max(1.0, budget_ms) / 1000.0
        while time.perf_counter() < frame_deadline and not self.finished:
            if self.current_match is None:
                self.finished = True
                self.finish_reason = "試合を作成できませんでした"
                break
            evaluation_finished = (
                self.current_match.state == "FULLTIME"
                or (
                    self.evaluation_mode == "speed"
                    and self.current_match.game_time >= self.speed_evaluation_game_time
                )
            )
            if evaluation_finished:
                self._complete_trial(partial=self.current_match.state != "FULLTIME")
                if time.perf_counter() >= self.deadline:
                    self.finished = True
                    self.finish_reason = "時間上限に到達"
                    break
                if self.stagnant_trials >= self.stagnant_limit and self.completed_matches >= len(self.opponents) * 2:
                    self.finished = True
                    self.finish_reason = "結果がほぼ収束"
                    break
                if self.evaluation_mode == "speed" and self.trials >= self.speed_max_trials:
                    self.finished = True
                    self.finish_reason = "速度重視の探索候補上限に到達"
                    break
                self._begin_trial()
                continue
            if time.perf_counter() >= self.deadline:
                self.finished = True
                self.finish_reason = "時間上限に到達" if self.completed_matches else "時間上限に到達（完走試合なし）"
                break
            advance_match_fixed(self.current_match)
            self.sample_counter += 1
            if self.sample_counter % 18 == 0:
                self._sample_movement()

    def cancel(self) -> None:
        if self.finished:
            return
        self.cancelled = True
        self.finished = True
        self.finish_reason = "ユーザーが中止"
        if self.parallel_enabled:
            self._stop_parallel_workers()

    def status_text(self) -> str:
        metrics = self.last_metrics
        tolerance_label = f"分野平均±{self.mean_tolerance:g}固定　"
        end_label = "収束まで　" if self.convergence_only else ""
        if not metrics:
            if self.parallel_enabled:
                fixtures = len(self.opponents) * 2
                finished = max(0, fixtures - len(self.pending_trials))
                return f"{tolerance_label}{end_label}{self.parallel_worker_count}コアで候補1件を評価中（{finished}/{fixtures}試合終了）"
            return f"{tolerance_label}{end_label}{self.current_opponent_name} 戦を計算中"
        mode_label = (
            "精度重視"
            if self.evaluation_mode == "accuracy"
            else f"速度重視({self.speed_evaluation_game_time / 60.0:g}分×{len(self.active_opponent_keys)}相手)"
        )
        prefix = f"{mode_label}・{self.parallel_worker_count}コア並列　" if self.parallel_enabled else f"{mode_label}　"
        priority = ""
        if self.opponent_weights_ready and self.opponent_weights:
            key = max(self.opponent_weights, key=self.opponent_weights.get)
            priority = (
                f"重点:{self.opponent_names.get(key, key)}×{self.opponent_weights[key]:.2f}"
                f"({self.opponent_classes.get(key, '')})　"
            )
        fixture_progress = ""
        if self.parallel_enabled and self.active_parallel_expected > 0 and self.pending_trials:
            finished = max(0, self.active_parallel_expected - len(self.pending_trials))
            fixture_progress = f"現在の候補 {finished}/{self.active_parallel_expected}評価完了　"
        completion_label = "評価区間完了" if self.evaluation_mode == "speed" else "完走試合"
        return tolerance_label + end_label + prefix + (
            fixture_progress + priority + f"候補{self.trials}件 / {completion_label}{self.completed_matches}回 / 採用{self.accepted_trials}回　"
            f"直近 {metrics.get('得点', 0):.0f}-{metrics.get('失点', 0):.0f}　"
            f"支配率{metrics.get('支配率', 0):.0f}%　残スタミナ{metrics.get('残スタミナ', 0):.0f}%"
        )
