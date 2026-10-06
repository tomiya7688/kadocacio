"""Capture operation-by-operation observations through the reference boundary."""

from scripts.core.match_protocol import TRACE_FORMAT, VERSION
from scripts.match.match_session import MatchSession
from scripts.tools.match_contract_input import restore_contract_input


# {
#   責務: [capture_trace: 操作ごとの参照Match観測を出自付きの列として捕捉する]
#   処理: [1: 契約入力からセッションを作成; 2: 操作後に未読イベントと状態を記録; 3: seedと実行範囲を添付]
#   引数: [payload: 検証対象の操作付き試合入力]
#   戻り値: [dict: 実参照試合による観測列。全試合互換を認定するものではない]
# }
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
