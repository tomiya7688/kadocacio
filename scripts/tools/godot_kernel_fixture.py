"""Public kickoff/clock and integer-seeded RNG oracle, not a synthetic match."""

import argparse
import json
from pathlib import Path

from scripts.core.match_protocol import TRACE_FORMAT, VERSION
from scripts.core.match_trace_comparison import compare_traces
from scripts.core.paths import USER_LOG_DIR
from scripts.match.match_session import MatchSession
from scripts.match.match_engine import Match
from scripts.core.simulation_geometry import Vec2
from scripts.core.settings import FIELD
from scripts.tools.godot_match_fixture import write_fixture
from scripts.tools.godot_team_oracle import assert_sources_unchanged
from scripts.tools.match_contract_input import restore_contract_input
from scripts.tools.match_random_audit import MatchRandomAudit

DEFAULT_OUTPUT = USER_LOG_DIR / "godot/match_kernel"


def rng_observation(rng: MatchRandomAudit, cursor: int) -> dict:
    state = rng.state_payload()
    return {"rng_words": state["words"], "rng_index": state["index"],
            "gauss_next": state["gauss_next"], "rng_word_count": rng.word_count,
            "rng_draws": rng.history()[cursor:]}


def capture_kickoff(payload: dict) -> dict:
    home, away, settings, operations = restore_contract_input(payload)
    rng = MatchRandomAudit(settings["seed"])
    session = MatchSession(home, away, **settings, rng_factory=lambda seed: rng)
    cursor = 0
    event_cursor = 0
    entries = []
    for index, operation in enumerate(operations):
        rng.purpose = "start" if operation["kind"] == "START" else "step"
        if operation["kind"] == "STEP":
            rng.step = session._steps + 1
        session.apply(operation)
        observation = session.observe(event_cursor).to_payload()
        observation["snapshot"]["rng"] = rng_observation(rng, cursor)
        cursor = len(rng.history())
        if observation["events"]:
            event_cursor = observation["events"][-1]["sequence"]
        entries.append({"operation_index": index, **observation})
    return {"format": TRACE_FORMAT, "version": VERSION, "source": {
        "implementation": "python-kickoff-reference", "execution": "simulation",
        "rng": "python.random.Random/MT19937", "seed_text": str(settings["seed"])}, "entries": entries}


def rng_cases() -> list[dict]:
    cases = []
    for seed in (0, 1, -1, 42, 2**32, 2**63 + 12345, -(2**130 + 19), 10**4095 + 321):
        rng = MatchRandomAudit(seed)
        outputs = []
        for index in range(720):
            rng.purpose, rng.step = "draw.sequence", index
            outputs.append({"kind": "random", "value": rng.random()})
        for bits in (0, 1, 5, 31, 32, 33, 53):
            rng.purpose = "draw.bits"
            outputs.append({"kind": "getrandbits", "arguments": [bits], "value": rng.getrandbits(bits)})
        for minimum, maximum in ((-3.5, 8.4), (1.2, -4.0), (8.0, 8.0)):
            rng.purpose = "draw.uniform"
            outputs.append({"kind": "uniform", "arguments": [minimum, maximum], "value": rng.uniform(minimum, maximum)})
        for minimum, maximum in ((0, 0), (-20, 20), (0, 16), (2, 2**42)):
            rng.purpose = "draw.randint"
            outputs.append({"kind": "randint", "arguments": [minimum, maximum], "value": rng.randint(minimum, maximum)})
        for _ in range(3):
            rng.purpose = "draw.choice"
            outputs.append({"kind": "choice", "arguments": [["a", "b", "c"]], "value": rng.choice(["a", "b", "c"])})
        for mean, deviation in ((0.0, 1.0), (10.0, 0.7), (2.0, 3.0)):
            rng.purpose = "draw.gauss"
            outputs.append({"kind": "gauss", "arguments": [mean, deviation], "value": rng.gauss(mean, deviation)})
        cases.append({"seed_text": str(seed), "outputs": outputs, "audit": rng.history(), "state": rng.state_payload()})
    return cases


def clock_cases(home: dict, away: dict) -> list[dict]:
    cases = [
        {"name": "live", "game_time": 100.0, "banner": "", "timer": 0.0, "waiting": False, "dt": 0.05, "after": 100.5, "transition": ""},
        {"name": "restart", "game_time": 100.0, "banner": "", "timer": 0.0, "waiting": True, "dt": 0.05, "after": 100.0, "transition": ""},
        {"name": "kickoff", "game_time": 0.0, "banner": "KICK OFF", "timer": 0.01, "waiting": False, "dt": 0.05, "after": 0.0, "transition": ""},
        {"name": "halftime", "game_time": 2699.9, "banner": "", "timer": 0.0, "waiting": False, "dt": 0.05, "after": 2700.0, "transition": "HALFTIME"},
        {"name": "halftime_banner", "game_time": 2700.0, "banner": "HALF TIME", "timer": 2.4, "waiting": False, "dt": 0.05, "after": 2700.5, "transition": ""},
        {"name": "fulltime", "game_time": 5399.9, "banner": "", "timer": 0.0, "waiting": False, "dt": 0.05, "after": 5400.0, "transition": "FULLTIME"},
    ]
    for row in cases:
        match = Match(home, away, "NEUTRAL", seed=41)
        match.start_new()
        match.game_time = row["game_time"]
        match.halftime_done = match.game_time >= 2700.0
        match.banner, match.banner_timer = row["banner"], row["timer"]
        if row["waiting"]:
            match.start_set_piece("FREE_KICK", match.home, Vec2(FIELD.center))
        match.update_step(row["dt"])
        expected_transition = "FULLTIME" if match.state == "FULLTIME" else "HALFTIME" if not (row["game_time"] >= 2700) and match.halftime_done else ""
        if match.game_time != row["after"] or expected_transition != row["transition"]:
            raise ValueError("clock expectation is stale: " + row["name"])
        row["after"] = match.game_time
    return cases


def write_kernel_fixture(output: Path = DEFAULT_OUTPUT) -> tuple[Path, dict[str, str]]:
    path, fingerprints = write_fixture(output, 50)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["reference"] = capture_kickoff(document["input"])
        document["rng_cases"] = rng_cases()
        home, away, _, _ = restore_contract_input(document["input"])
        document["clock_cases"] = clock_cases(home, away)
        path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return path, fingerprints
    finally:
        assert_sources_unchanged(fingerprints)


def compare_native(fixture: Path, native: Path) -> dict:
    document = json.loads(fixture.read_text(encoding="utf-8"))
    return compare_traces(document["reference"], json.loads(native.read_text(encoding="utf-8")))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    path, _ = write_kernel_fixture(args.output)
    print(f"GODOT KERNEL FIXTURE: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
