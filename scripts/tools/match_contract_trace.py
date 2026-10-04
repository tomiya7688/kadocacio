"""Capture operation-by-operation observations through the reference boundary."""

from scripts.core.match_protocol import TRACE_FORMAT, VERSION
from scripts.match.match_session import MatchSession
from scripts.tools.match_contract_input import restore_contract_input


def capture_trace(payload: dict) -> dict:
    home, away, settings, operations = restore_contract_input(payload)
    session = MatchSession(home, away, **settings)
    entries = []
    cursor = 0
    for index, operation in enumerate(operations):
        session.apply(operation)
        observation = session.observe(cursor).to_payload()
        if observation["events"]:
            cursor = observation["events"][-1]["sequence"]
        entries.append({"operation_index": index, **observation})
    return {"format": TRACE_FORMAT, "version": VERSION,
            "source": {"implementation": "python-reference", "execution": "simulation", "rng": "python.random.Random/MT19937", "seed_text": str(settings["seed"])},
            "entries": entries}
