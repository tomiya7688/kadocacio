"""Compare headless and Pygame-rendered runs of the same seeded match."""

from __future__ import annotations

import argparse
import hashlib
import json
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from scripts.core.simulation_limits import SimulationLimits
from scripts.core.simulation_runtime import (
    FIXED_PHYSICS_DT,
    MAX_FULL_MATCH_STEPS,
    advance_match_fixed,
    run_headless_match,
)
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices


def match_state_payload(match: Match) -> dict:
    """Capture result-relevant state without exposing mutable game objects."""
    def team_payload(team) -> dict:
        return {
            "score": team.score,
            "shots": team.shots,
            "possession": team.possession,
            "tactic": team.tactic,
            "players": [
                [
                    player.number, player.pos.x, player.pos.y, player.z,
                    player.stamina, player.action_command.value, player.sent_off,
                ]
                for player in team.players
            ],
        }

    owner = match.ball.owner
    owner_id = None if owner is None else ["home" if owner.team is match.home else "away", owner.number]
    return {
        "state": match.state,
        "game_time": match.game_time,
        "simulation_elapsed": match.simulation_elapsed,
        "home": team_payload(match.home),
        "away": team_payload(match.away),
        "ball": [
            match.ball.pos.x, match.ball.pos.y, match.ball.vel.x, match.ball.vel.y,
            match.ball.z, match.ball.vertical_speed, owner_id,
        ],
        "events": list(match.events),
        "goal_scorers": list(match.goal_scorers),
        "foul_count": match.foul_count,
        "card_count": match.card_count,
        "restart_counts": dict(match.restart_counts),
        "rng_state": hashlib.sha256(repr(match.rng.getstate()).encode("ascii")).hexdigest(),
    }


def run_headless(home_choice: dict, away_choice: dict, seed: int, max_steps: int) -> tuple[dict, int]:
    match = Match(home_choice, away_choice, "HOME", seed=seed)
    match.start_new()
    result = run_headless_match(match, SimulationLimits(max_steps=max_steps))
    return match_state_payload(match), result.steps


def run_rendered(
    home_choice: dict, away_choice: dict, seed: int, max_steps: int, render_every: int,
) -> tuple[dict, int, int]:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ["KADOKA_DISABLE_GPU"] = "1"
    import pygame

    from scripts.app.game_app import Game

    game = Game()
    try:
        match = Match(home_choice, away_choice, "HOME", seed=seed)
        match.start_new()
        game.match = match
        game.visible_simulation.reset(match)
        game.reset_camera()
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
        if steps % render_every and match.state != "FULLTIME":
            game.draw()
            frames += 1
        return match_state_payload(match), steps, frames
    finally:
        if game.gpu_presenter is not None:
            game.gpu_presenter.destroy()
        pygame.quit()


def compare_matches(
    home_choice: dict, away_choice: dict, *, seed: int, max_steps: int, render_every: int,
) -> dict:
    if max_steps < 1 or render_every < 1:
        raise ValueError("max_steps and render_every must be positive")
    headless, headless_steps = run_headless(home_choice, away_choice, seed, max_steps)
    rendered, rendered_steps, frames = run_rendered(
        home_choice, away_choice, seed, max_steps, render_every,
    )
    different_fields = [key for key in headless if headless[key] != rendered[key]]
    if headless_steps != rendered_steps:
        different_fields.insert(0, "steps")
    return {
        "home_id": home_choice.get("id"),
        "away_id": away_choice.get("id"),
        "seed": seed,
        "headless_steps": headless_steps,
        "rendered_steps": rendered_steps,
        "rendered_frames": frames,
        "game_time": rendered["game_time"],
        "fulltime": headless["state"] == rendered["state"] == "FULLTIME",
        "same_state": not different_fields,
        "different_fields": different_fields,
    }


def _choose_team(choices: list[dict], query: str | None, fallback_index: int) -> dict:
    if query is None:
        return choices[fallback_index]
    for choice in choices:
        if query in (str(choice.get("id")), choice.get("name")):
            return choice
    raise ValueError(f"team not found: {query}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare seeded headless and Pygame-rendered match state")
    parser.add_argument("--home", help="home team ID or exact name; defaults to the first team")
    parser.add_argument("--away", help="away team ID or exact name; defaults to the second team")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--max-steps", type=int, default=MAX_FULL_MATCH_STEPS)
    parser.add_argument("--render-every", type=int, default=60)
    parser.add_argument("--allow-partial", action="store_true", help="accept a matching run before full time")
    args = parser.parse_args(argv)
    choices = discover_team_choices()
    if len(choices) < 2:
        parser.error("at least two valid teams are required")
    try:
        home = _choose_team(choices, args.home, 0)
        away = _choose_team(choices, args.away, 1)
        report = compare_matches(
            home, away, seed=args.seed, max_steps=args.max_steps, render_every=args.render_every,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["same_state"] and (report["fulltime"] or args.allow_partial) else 1


if __name__ == "__main__":
    raise SystemExit(main())
