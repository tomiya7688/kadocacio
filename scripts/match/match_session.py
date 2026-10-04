"""Operation/observation adapter over the existing engine; no new match rules."""

from copy import deepcopy

from scripts.core.match_operation import MatchOperation
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.match.match_engine import Match
from scripts.match.match_observation import MatchObservation


class MatchSession:
    def __init__(self, home: dict, away: dict, *, seed: int, venue_mode: str, ai_rethink_multiplier: float, max_steps: int, rng_factory=None):
        if type(seed) is not int or type(max_steps) is not int or max_steps < 1:
            raise ValueError("explicit integer seed and positive step budget are required")
        self._match = Match(deepcopy(home), deepcopy(away), venue_mode, seed=seed,
                            ai_rethink_multiplier=ai_rethink_multiplier, record_events=True, rng_factory=rng_factory)
        self._started = False
        self._paused = False
        self._steps = 0
        self._max_steps = max_steps

    def apply(self, payload: dict) -> None:
        operation = MatchOperation.from_payload(payload)
        if operation.kind == "START":
            if self._started:
                raise ValueError("START may only occur once")
            self._match.start_new()
            self._started = True
            return
        if not self._started:
            raise ValueError("START is required before operations")
        if operation.kind == "SET_SPEED":
            self._match.speed_multiplier = operation.value
        elif operation.kind in ("PAUSE", "RESUME"):
            self._paused = operation.kind == "PAUSE"
        elif not self._paused and self._match.state != "FULLTIME":
            if self._steps >= self._max_steps:
                raise ValueError("physics step budget exhausted")
            advance_match_fixed(self._match, operation.value)
            self._steps += 1

    def observe(self, after_sequence: int = 0) -> MatchObservation:
        if not self._started:
            raise ValueError("START is required before observing")
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("event cursor must be a nonnegative integer")
        return MatchObservation.capture(self._match, self._steps, self._paused, after_sequence)
