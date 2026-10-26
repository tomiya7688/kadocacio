"""Pickle-safe worker functions for complete league matches."""

from __future__ import annotations

import time
from statistics import mean

from scripts.core.cpu_usage_limiter import CpuUsageLimiter
from scripts.core.match_seed import league_fixture_seed
from scripts.core.match_telemetry import MatchTelemetry
from scripts.core.simulation_runtime import MAX_FULL_MATCH_STEPS, advance_match_fixed
from scripts.match.match_engine import Match


SYNCED_LIVE_STEP_BUDGET = 20
SYNCED_FAST_FINISH_STEP_BUDGET = 240
SYNCED_LIVE_REPORT_INTERVAL = 5.0
SYNCED_FAST_FINISH_REPORT_INTERVAL = 60.0


def _match_output(match: Match) -> dict:
    """Use the public final result; keep incomplete step-limit diagnostics."""
    if match.state == "FULLTIME":
        return match.final_result().to_payload()
    return {
        "home_score": match.home.score,
        "away_score": match.away.score,
        "home_shots": match.home.shots,
        "away_shots": match.away.shots,
        "home_possession": match.home.possession,
        "away_possession": match.away.possession,
        "goal_scorers": list(match.goal_scorers),
        "game_time": match.game_time,
    }


# {
#   責務: [_run_headless_league_match: 一対戦を描画せず共通の固定更新で実行し結果と完走状態を返す]
#   処理: [
#     1: 対戦ID・両チーム名から共通seedを作りMatch構築時から適用する
#     2: 要求された観測・CPU枠・更新上限を準備する
#     3: 固定更新を繰り返し要求時だけ統計採取と途中経過送信を行う
#     4: 終了状態を送信し完走または更新上限の結果を返す
#   ]
#   引数: [
#     job: fixture・home_choice・away_choiceが必要な対戦入力
#     jobの任意項目: 判断倍率・更新上限・CPU稼働率・進捗キュー・統計採取設定
#   ]
#   戻り値: [dict: 対戦ID・得点等・固定更新回数・終了理由・演算経過秒数。未完走はstep_limitとし、演算や送信の例外は隠さない]
# }
def _run_headless_league_match(job: dict) -> dict:
    """Play a complete real Match in a worker process without rendering."""
    # 初期選手値の抽選も対象なので、構築後のrng.seed()ではなくseed引数を使う。
    fixture = job["fixture"]
    seed = league_fixture_seed(
        fixture.get("id"),
        job["home_choice"].get("name"),
        job["away_choice"].get("name"),
    )
    match = Match(
        job["home_choice"],
        job["away_choice"],
        "HOME",
        ai_rethink_multiplier=float(job.get("ai_rethink_multiplier", 1.0)),
        seed=seed,
    )
    match.start_new()
    # 観測は明示要求時だけ保持し、CPU待機と更新上限を試合の物理幅から分離する。
    collect_telemetry = bool(job.get("collect_telemetry", False))
    telemetry = MatchTelemetry(match) if collect_telemetry else None
    sample_every_steps = max(1, int(job.get("sample_every_steps", 18)))
    started_at = time.perf_counter()
    steps = 0
    progress_queue = job.get("progress_queue")
    cpu_limiter = CpuUsageLimiter(job.get("cpu_duty_cycle", 1.0))
    next_report = 0.0
    maximum_steps = max(1, int(job.get("max_match_steps", MAX_FULL_MATCH_STEPS)))
    # CPU待機や進捗通知で時計を直接進めず、共通の固定更新だけを消費する。
    while match.state != "FULLTIME" and steps < maximum_steps:
        advance_match_fixed(match)
        steps += 1
        if telemetry is not None:
            telemetry.observe_control()
            if steps % sample_every_steps == 0:
                telemetry.sample()
        cpu_limiter.throttle()
        if progress_queue is not None and match.game_time >= next_report:
            progress_queue.put(
                {
                    "fixture_id": fixture["id"],
                    "minute": min(90, int(match.game_time // 60)),
                    "home_score": match.home.score,
                    "away_score": match.away.score,
                    "state": match.state,
                }
            )
            next_report += 60.0
    # 上限終了の調査にも使えるよう、最終通知と結果へ実際の状態を残す。
    if progress_queue is not None:
        progress_queue.put(
            {
                "fixture_id": fixture["id"],
                "game_time": min(5400.0, match.game_time),
                "minute": min(90, int(match.game_time // 60)),
                "home_score": match.home.score,
                "away_score": match.away.score,
                "state": match.state,
            }
        )
    result = {
        "fixture_id": fixture["id"],
        **_match_output(match),
        "engine_steps": steps,
        "simulation_mode": str(job.get("simulation_mode", "PRECISE")),
        "fulltime": match.state == "FULLTIME",
        "finish_reason": "fulltime" if match.state == "FULLTIME" else "step_limit",
        "simulation_elapsed": match.simulation_elapsed,
        "restart_type": match.restart_type,
        "restart_elapsed": match.restart_elapsed,
        "restart_counts": dict(match.restart_counts),
        "wall_seconds": time.perf_counter() - started_at,
    }
    if telemetry is not None:
        # 追加の選手集計は評価用途だけへ返し、通常ジョブへ不要な走査を増やさない。
        result["home_telemetry"] = telemetry.team_metrics(match.home)
        result["away_telemetry"] = telemetry.team_metrics(match.away)
        result["home_remaining_stamina"] = mean(player.stamina_ratio for player in match.home.players)
        result["away_remaining_stamina"] = mean(player.stamina_ratio for player in match.away.players)
    return result


# {
#   責務: [_run_synchronized_match_batch: 一ワーカー内の複数試合を観戦側の演算ペースへ合わせて固定更新する]
#   処理: [
#     1: 各対戦の共通seedをMatch構築時から適用し個別の更新上限を保持する
#     2: 共有の目標演算秒数まで各試合を進めて途中経過を送信する
#     3: 目標が負なら待機ペースを解除し同じ物理幅のまま残りを計算する
#     4: 中断なら空配列、それ以外は完走または上限到達の結果を対戦順で返す
#   ]
#   引数: [
#     jobs: 対戦入力の配列。CPU稼働率は先頭ジョブからバッチ全体へ適用する
#     sync_clock: valueが目標演算秒数の共有値。負値はペース制限を解除する
#     progress_queue: 途中経過と各試合の末尾状態を送るキュー
#     cancel_event: is_set()でバッチ中断を指示する共有イベント
#   ]
#   戻り値: [list: 対戦ごとの結果辞書。中断時と空の入力は空配列。時計だけの早送りはせず、例外は呼出し元へ伝える]
# }
def _run_synchronized_match_batch(jobs: list[dict], sync_clock, progress_queue, cancel_event) -> list[dict]:
    """Advance games at the watched simulation pace, with independent clocks."""
    # 状態・seed・更新回数は対戦ごとに持ち、バッチ順を変えても乱数器を共有しない。
    contexts: list[dict] = []
    cpu_limiter = CpuUsageLimiter(jobs[0].get("cpu_duty_cycle", 1.0) if jobs else 1.0)
    for job in jobs:
        fixture = job["fixture"]
        seed = league_fixture_seed(
            fixture.get("id"),
            job["home_choice"].get("name"),
            job["away_choice"].get("name"),
        )
        match = Match(
            job["home_choice"],
            job["away_choice"],
            "HOME",
            ai_rethink_multiplier=float(job.get("ai_rethink_multiplier", 1.0)),
            seed=seed,
        )
        match.start_new()
        contexts.append(
            {
                "fixture": fixture,
                "match": match,
                "steps": 0,
                "maximum_steps": max(1, int(job.get("max_match_steps", MAX_FULL_MATCH_STEPS))),
                "next_report": 0.0,
                "simulation_mode": str(job.get("simulation_mode", "PRECISE")),
            }
        )

    # 比較するのは試合時計でなく演算経過で、再開準備による時計停止を各試合へ閉じる。
    while not cancel_event.is_set() and any(
        context["match"].state != "FULLTIME" and context["steps"] < context["maximum_steps"] for context in contexts
    ):
        requested_elapsed = float(sync_clock.value)
        finish_without_pacing = requested_elapsed < 0.0
        target_elapsed = float("inf") if finish_without_pacing else max(0.0, requested_elapsed)
        progressed = False
        for context in contexts:
            match = context["match"]
            if match.state == "FULLTIME" or context["steps"] >= context["maximum_steps"]:
                continue
            # Every match receives the same amount of physics time. Its playing
            # clock may legitimately differ because restarts pause independently.
            # Once the watched game is over there is no frame clock to follow.
            # Larger chunks improve cache locality and avoid repeatedly reading
            # the manager-backed clock for every twenty fixed physics steps.
            # The Match engine still receives the exact same 0.05 second steps.
            step_budget = SYNCED_FAST_FINISH_STEP_BUDGET if finish_without_pacing else SYNCED_LIVE_STEP_BUDGET
            while (
                match.simulation_elapsed + 0.001 < target_elapsed
                and step_budget > 0
                and match.state != "FULLTIME"
                and context["steps"] < context["maximum_steps"]
            ):
                advance_match_fixed(match)
                context["steps"] += 1
                step_budget -= 1
                progressed = True
                cpu_limiter.throttle()
            if match.game_time >= context["next_report"] or match.state == "FULLTIME":
                progress_queue.put(
                    {
                        "fixture_id": context["fixture"]["id"],
                        "game_time": min(5400.0, match.game_time),
                        "minute": min(90, int(match.game_time // 60)),
                        "home_score": match.home.score,
                        "away_score": match.away.score,
                        "state": match.state,
                    }
                )
                # Sending two Manager queue messages per real-time second is
                # useful during a watched game, but it can flood the IPC queue
                # when dozens of lagging games are released to full speed.
                report_interval = SYNCED_FAST_FINISH_REPORT_INTERVAL if finish_without_pacing else SYNCED_LIVE_REPORT_INTERVAL
                context["next_report"] = match.game_time + report_interval
        if not progressed:
            # 共有目標に追いついた時だけ短く待ち、進められない状態でCPUを占有しない。
            time.sleep(0.002)

    # 中断を完走結果へ見せかけず、通常終了だけ末尾通知と対戦順の結果を作る。
    if cancel_event.is_set():
        return []
    results = []
    for context in contexts:
        fixture = context["fixture"]
        match = context["match"]
        progress_queue.put(
            {
                "fixture_id": fixture["id"],
                "game_time": min(5400.0, match.game_time),
                "minute": min(90, int(match.game_time // 60)),
                "home_score": match.home.score,
                "away_score": match.away.score,
                "state": match.state,
            }
        )
        results.append(
            {
                "fixture_id": fixture["id"],
                **_match_output(match),
                "engine_steps": context["steps"],
                "simulation_mode": str(context.get("simulation_mode", "PRECISE")),
                "fulltime": match.state == "FULLTIME",
                "finish_reason": "fulltime" if match.state == "FULLTIME" else "step_limit",
                "simulation_elapsed": match.simulation_elapsed,
                "restart_type": str(getattr(match, "restart_type", "")),
                "restart_elapsed": float(getattr(match, "restart_elapsed", 0.0)),
            }
        )
    return results


__all__ = ("_run_headless_league_match", "_run_synchronized_match_batch")
