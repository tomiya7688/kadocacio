"""Compare headless and Pygame-rendered runs of the same seeded match."""

from __future__ import annotations

import hashlib
import json
import os
from itertools import zip_longest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from scripts.core.simulation_limits import SimulationLimits
from scripts.core.simulation_runtime import (
    FIXED_PHYSICS_DT,
    advance_match_fixed,
    run_headless_match,
)
from scripts.match.match_engine import Match


# {
#   責務: [match_state_payload: 再現性の比較に使う試合状態と乱数状態の指紋を観測する]
#   処理: [1: 両チームの公開値と保持者の所属・背番号を取り出す; 2: 時計・ボール・ログ・集計をコピーする; 3: 乱数内部状態のSHA-256を添える]
#   引数: [match: 比較対象の試合。観測用の全イベント記録が必要なら構築時に有効化する]
#   戻り値: [dict: 比較用の独立値。時計・乱数列・試合状態は進めない]
# }
def match_state_payload(match: Match) -> dict:
    """Capture result-relevant state without exposing mutable game objects."""

    # {
    #   責務: [team_payload: チーム集計と出場選手の位置・体力・行動を比較用の値へ写す]
    #   処理: [1: 集計と戦術を取り出す; 2: 出場順に各選手の比較対象値を配列化する]
    #   引数: [team: 試合内の一チーム]
    #   戻り値: [dict: 集計と選手値。TeamやPlayerの可変オブジェクトを返さない]
    # }
    def team_payload(team) -> dict:
        # 同じ背番号が別チームにいても、チーム別の観測として区別する。
        return {
            "score": team.score,
            "shots": team.shots,
            "possession": team.possession,
            "tactic": team.tactic,
            "players": [
                [
                    player.number,
                    player.pos.x,
                    player.pos.y,
                    player.z,
                    player.stamina,
                    player.action_command.value,
                    player.sent_off,
                ]
                for player in team.players
            ],
        }

    # 保持者はオブジェクト参照でなく、所属と背番号の組へ写す。
    owner = match.ball.owner
    owner_id = None if owner is None else ["home" if owner.team is match.home else "away", owner.number]
    return {
        "state": match.state,
        "game_time": match.game_time,
        "simulation_elapsed": match.simulation_elapsed,
        "home": team_payload(match.home),
        "away": team_payload(match.away),
        "ball": [
            match.ball.pos.x,
            match.ball.pos.y,
            match.ball.vel.x,
            match.ball.vel.y,
            match.ball.z,
            match.ball.vertical_speed,
            owner_id,
        ],
        "events": list(match.events),
        "event_history": [event.to_payload() for event in match.event_history()],
        "goal_scorers": list(match.goal_scorers),
        "foul_count": match.foul_count,
        "card_count": match.card_count,
        "restart_counts": dict(match.restart_counts),
        "rng_state": hashlib.sha256(repr(match.rng.getstate()).encode("ascii")).hexdigest(),
    }


# {
#   責務: [run_headless: 構築時にseedを指定した同一試合核を描画せず固定更新する]
#   処理: [1: 全イベント記録付きのMatchをseedと条件から構築する; 2: 開始して更新上限まで共通ランタイムで実行する; 3: 比較状態と更新回数を返す]
#   引数: [
#     home_choice・away_choice: 両チーム入力
#     seed: 構築前から適用する整数seed
#     max_steps: 更新上限
#     venue_mode: 会場
#     ai_rethink_multiplier: 判断更新倍率
#   ]
#   戻り値: [tuple: 観測辞書・実行ステップ数。上限到達は完走を意味しない]
# }
def run_headless(
    home_choice: dict,
    away_choice: dict,
    seed: int,
    max_steps: int,
    *,
    venue_mode: str = "HOME",
    ai_rethink_multiplier: float = 1.0,
) -> tuple[dict, int]:
    # 初期選手の抽選も再現対象なので、構築後にseedを設定し直さない。
    match = Match(
        home_choice,
        away_choice,
        venue_mode,
        seed=seed,
        ai_rethink_multiplier=ai_rethink_multiplier,
        record_events=True,
    )
    match.start_new()
    result = run_headless_match(match, SimulationLimits(max_steps=max_steps))
    return match_state_payload(match), result.steps


# {
#   責務: [run_rendered: 通常のPygame描画を挟みつつ同じ固定更新の試合を実行する]
#   処理: [1: ダミーSDLを既定としGPUを無効化してGameを準備する; 2: seed指定の試合を表示側へ接続する; 3: 固定更新と指定間隔の描画を繰り返す; 4: 末尾の未描画分を描き例外時も終了処理する]
#   引数: [
#     home_choice・away_choice: 両チーム入力
#     seed: 整数seed
#     max_steps: 更新上限
#     render_every: 正の描画間隔。呼出し元が検証する
#     venue_mode: 会場
#     ai_rethink_multiplier: 判断更新倍率
#   ]
#   戻り値: [tuple: 観測辞書・実行ステップ数・描画フレーム数。実ウィンドウ操作E2Eの証明ではない]
# }
def run_rendered(
    home_choice: dict,
    away_choice: dict,
    seed: int,
    max_steps: int,
    render_every: int,
    *,
    venue_mode: str = "HOME",
    ai_rethink_multiplier: float = 1.0,
) -> tuple[dict, int, int]:
    # 指定済みのSDL設定は尊重し、比較時のGPU表示は明示的に止める。
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["KADOKA_DISABLE_GPU"] = "1"
    import pygame

    from scripts.app.game_app import Game

    game = Game(team_choices=[home_choice, away_choice])
    try:
        match = Match(
            home_choice,
            away_choice,
            venue_mode,
            seed=seed,
            ai_rethink_multiplier=ai_rethink_multiplier,
            record_events=True,
        )
        match.start_new()
        game.match = match
        game.visible_simulation.reset(match)
        game.reset_camera()
        # 描画頻度に合わせて物理dtを変えず、毎回共通の固定更新を使う。
        steps = 0
        frames = 0
        game.draw()
        frames += 1
        while match.state != "FULLTIME" and steps < max_steps:
            advance_match_fixed(match)
            steps += 1
            if steps % render_every == 0 or match.state == "FULLTIME":
                game.update_camera(FIXED_PHYSICS_DT * render_every)
                game.draw()
                frames += 1
        # 間隔で割り切れない部分実行でも、最後の状態を一度描画する。
        if steps % render_every and match.state != "FULLTIME":
            game.draw()
            frames += 1
        return match_state_payload(match), steps, frames
    finally:
        # 比較中の例外でも描画リソースとPygameを解放する。
        if game.gpu_presenter is not None:
            game.gpu_presenter.destroy()
        pygame.quit()


# {
#   責務: [_event_digest: キー順の違いに影響されない全イベント列の指紋を作る]
#   処理: [1: 非有限値を拒否してキー順を揃えたJSONへ変換する; 2: UTF-8のSHA-256を返す]
#   引数: [events: 比較対象のイベント辞書列。イベント順は維持する]
#   戻り値: [str: 16進指紋。イベント列は変更しない]
# }
def _event_digest(events: list[dict]) -> str:
    # イベントの時系列は並べ替えず、辞書内のキー順だけを安定化する。
    encoded = json.dumps(events, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# {
#   責務: [_first_event_difference: 内容または件数が最初に異なるイベントを探す]
#   処理: [1: 長い方の末尾まで同じindexで比較する; 2: 最初の差を両経路の値付きで返す]
#   引数: [headless: 描画なしの全イベント; rendered: 描画ありの全イベント]
#   戻り値: [dictまたはNone: 0始まりのindexと両値。一方の欠落はNone、一致時はNone]
# }
def _first_event_difference(headless: list[dict], rendered: list[dict]) -> dict | None:
    # zipで短い方へ切り詰めると、末尾イベントの欠落を見落とす。
    for index, (left, right) in enumerate(zip_longest(headless, rendered)):
        if left != right:
            return {"index": index, "headless": left, "rendered": right}
    return None


# {
#   責務: [compare_matches: 同一入力の描画有無を比較し部分実行と完走を区別して報告する]
#   処理: [1: 正の更新上限と描画間隔を確認する; 2: 同じ設定で両経路を実行する; 3: 状態と更新回数の差を集める; 4: 全イベントの件数・指紋・最初の差を報告する]
#   引数: [
#     home_choice・away_choice: 両チーム入力
#     seed: 整数seed
#     max_steps: 更新上限
#     render_every: 描画間隔
#     venue_mode: 会場
#     ai_rethink_multiplier: 判断更新倍率
#     include_events: 全イベント本文も報告するか
#   ]
#   戻り値: [dict: 一致・完走・差分の比較結果。途中一致を完走成功に置き換えない。不正な正数条件はValueError]
# }
def compare_matches(
    home_choice: dict,
    away_choice: dict,
    *,
    seed: int,
    max_steps: int,
    render_every: int,
    venue_mode: str = "HOME",
    ai_rethink_multiplier: float = 1.0,
    include_events: bool = False,
) -> dict:
    if max_steps < 1 or render_every < 1:
        raise ValueError("max_steps and render_every must be positive")
    # 実行条件を共通化し、描画頻度以外を比較経路間で変えない。
    match_settings = {"venue_mode": venue_mode, "ai_rethink_multiplier": ai_rethink_multiplier}
    headless, headless_steps = run_headless(home_choice, away_choice, seed, max_steps, **match_settings)
    rendered, rendered_steps, frames = run_rendered(
        home_choice,
        away_choice,
        seed,
        max_steps,
        render_every,
        **match_settings,
    )
    # 同じ状態でも消費した物理ステップが違えば不一致として報告する。
    different_fields = [key for key in headless if headless[key] != rendered[key]]
    if headless_steps != rendered_steps:
        different_fields.insert(0, "steps")
    report = {
        "home_id": home_choice.get("id"),
        "away_id": away_choice.get("id"),
        "seed": seed,
        **match_settings,
        "headless_steps": headless_steps,
        "rendered_steps": rendered_steps,
        "rendered_frames": frames,
        "game_time": rendered["game_time"],
        "fulltime": headless["state"] == rendered["state"] == "FULLTIME",
        "same_state": not different_fields,
        "different_fields": different_fields,
        "headless_event_count": len(headless["event_history"]),
        "rendered_event_count": len(rendered["event_history"]),
        "headless_event_digest": _event_digest(headless["event_history"]),
        "rendered_event_digest": _event_digest(rendered["event_history"]),
        "first_event_difference": _first_event_difference(headless["event_history"], rendered["event_history"]),
    }
    # 通常の標準出力を大きくしないよう、全ログ本文は明示要求時だけ付ける。
    if include_events:
        report["event_history"] = {"headless": headless["event_history"], "rendered": rendered["event_history"]}
    return report


# {
#   責務: [main: 従来のCLI入口を専用のコマンド指揮へ接続する]
#   処理: [1: CLI担当を遅延読込する; 2: 比較関数を接続して実行を委譲する]
#   引数: [argv: CLI引数列。Noneはプロセス引数]
#   戻り値: [int: CLI担当の終了コード。入力エラー等のSystemExitも変更せず返す]
# }
def main(argv: list[str] | None = None) -> int:
    # 比較APIだけを使う呼出し元へCLIの探索・保存依存を持ち込まない。
    from scripts.tools.match_repro_cli import MatchReproductionCli

    return MatchReproductionCli(compare_matches).run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
