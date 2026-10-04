"""Versioned transport wrapping the existing lossless reproduction input."""

import json

from scripts.core.match_operation import MatchOperation
from scripts.core.match_protocol import INPUT_FORMAT, VERSION, is_json_integer
from scripts.tools.match_repro_input import create_input_record, restore_input_record


def create_contract_input(home: dict, away: dict, operations: list[dict], **settings) -> dict:
    repro = create_input_record(home, away, **settings)
    repro["settings"]["seed"] = str(repro["settings"]["seed"])
    payload = {"format": INPUT_FORMAT, "version": VERSION, "repro_input": repro, "operations": operations}
    restore_contract_input(payload)
    return json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))


def restore_contract_input(payload: object) -> tuple[dict, dict, dict, list[dict]]:
    if not isinstance(payload, dict) or payload.get("format") != INPUT_FORMAT or not is_json_integer(payload.get("version")) or payload["version"] != VERSION:
        raise ValueError("unsupported match contract input")
    copied = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    repro = copied.get("repro_input")
    if not isinstance(repro, dict) or not isinstance(repro.get("settings"), dict):
        raise ValueError("missing reproduction settings")
    seed = repro["settings"].get("seed")
    if not isinstance(seed, str) or not seed or seed.strip() != seed or len(seed.lstrip("-")) > 4096:
        raise ValueError("seed must be canonical decimal text")
    try:
        number = int(seed)
    except ValueError as error:
        raise ValueError("seed must be canonical decimal text") from error
    if str(number) != seed:
        raise ValueError("seed must be canonical decimal text")
    repro["settings"]["seed"] = number
    for key, container in (("version", repro), ("max_steps", repro["settings"])):
        if is_json_integer(container.get(key)):
            container[key] = int(container[key])
    teams = repro.get("teams")
    if isinstance(teams, dict):
        for team in teams.values():
            if isinstance(team, dict):
                for key in ("primary", "secondary"):
                    if isinstance(team.get(key), list):
                        team[key] = [int(channel) if is_json_integer(channel) else channel for channel in team[key]]
    home, away, settings = restore_input_record(repro)
    operations = copied.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations must start with START")
    kinds = [MatchOperation.from_payload(operation).kind for operation in operations]
    if kinds[0] != "START" or kinds.count("START") != 1:
        raise ValueError("operations require exactly one leading START")
    if kinds.count("STEP") > settings["max_steps"]:
        raise ValueError("operations exceed physics step budget")
    return home, away, settings, operations
