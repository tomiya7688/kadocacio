"""Operation/observation adapter over the existing engine; no new match rules."""

from copy import deepcopy

from scripts.core.match_operation import MatchOperation
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.match.match_engine import Match
from scripts.match.match_observation import MatchObservation


# {
#   責務: [MatchSession: 外部操作と参照Matchの固定更新・独立観測を仲介する]
#   フィールド: [_match: 所有する参照試合; _started: 開始済み; _paused: 停止状態; _steps: 実更新数; _max_steps: 更新予算]
# }
class MatchSession:
    # {
    #   責務: [__init__: 再現条件を明示した独立試合セッションを準備する]
    #   処理: [1: seedと更新予算を検証; 2: チームを複製してMatchと操作状態を初期化]
    #   引数: [home: ホーム選択; away: アウェー選択; seed: 整数seed; venue_mode: 会場; ai_rethink_multiplier: 判断頻度; max_steps: 更新予算]
    #   戻り値: [None: 試合開始はSTART操作まで行わない]
    # }
    def __init__(self, home: dict, away: dict, *, seed: int, venue_mode: str, ai_rethink_multiplier: float, max_steps: int):
        if type(seed) is not int or type(max_steps) is not int or max_steps < 1:
            raise ValueError("explicit integer seed and positive step budget are required")
        self._match = Match(deepcopy(home), deepcopy(away), venue_mode, seed=seed,
                            ai_rethink_multiplier=ai_rethink_multiplier, record_events=True)
        self._started = False
        self._paused = False
        self._steps = 0
        self._max_steps = max_steps

    # {
    #   責務: [apply: 検証した操作を開始順・停止状態・固定更新予算に従って適用する]
    #   処理: [1: 操作と開始状態を検査; 2: 開始・倍率・停止を適用; 3: 許可されたSTEPだけ既存演算を進める]
    #   引数: [payload: ホスト操作の辞書]
    #   戻り値: [None: 不正操作や予算超過はValueError]
    # }
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

    # {
    #   責務: [observe: 開始済み試合から指定カーソル以降の独立観測を取得する]
    #   処理: [1: 開始済みと非負整数カーソルを検証; 2: 現状態を不変観測へ変換]
    #   引数: [after_sequence: 既読イベント番号。0で全履歴]
    #   戻り値: [MatchObservation: 演算や乱数を進めない状態値]
    # }
    def observe(self, after_sequence: int = 0) -> MatchObservation:
        if not self._started:
            raise ValueError("START is required before observing")
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("event cursor must be a nonnegative integer")
        return MatchObservation.capture(self._match, self._steps, self._paused, after_sequence)
