"""Detached, immutable observation of the reference Match, never live objects."""

from dataclasses import asdict, dataclass
import json


# {
#   責務: [_team_state: チームと選手の生オブジェクトを観測可能な値へ変換する]
#   処理: [1: チーム成績を抽出; 2: 安定ID・位置・目標・スタミナ・コマンドを選手ごとに抽出]
#   引数: [team: 参照試合のチーム; identities: オブジェクトIDから観測IDへの対応]
#   戻り値: [dict: JSON化可能なチーム観測]
# }
def _team_state(team, identities: dict[int, str]) -> dict:
    return {"score": team.score, "shots": team.shots, "possession": team.possession,
            "tactic": team.tactic, "direction": team.direction,
            "players": [{"id": identities[id(player)], "number": player.number,
                         "name": player.name, "role": player.role,
                         "position": [player.pos.x, player.pos.y, player.z],
                         "target": [player.target.x, player.target.y],
                         "stamina": player.stamina, "command": player.action_command.name,
                         "sent_off": player.sent_off} for player in team.players]}


# {
#   責務: [MatchObservation: 試合内部から独立した不変の状態・イベント・結果を保持する]
#   フィールド: [_json: 有限JSON値に変換済みの観測文字列]
# }
@dataclass(frozen=True, slots=True)
class MatchObservation:
    _json: str

    # {
    #   責務: [capture: 時計を進めずに参照試合の一時点を取得する]
    #   処理: [1: チーム・選手IDを構成; 2: 状態とカーソル以降のイベントを抽出; 3: 終了時だけ結果を添えJSON化]
    #   引数: [match: 参照試合; step: 実更新数; paused: ホスト停止状態; after_sequence: 既読イベント番号]
    #   戻り値: [MatchObservation: 試合への可変参照を持たない観測]
    # }
    @classmethod
    def capture(cls, match, step: int, paused: bool, after_sequence: int = 0) -> "MatchObservation":
        identities = {id(player): f"{side}:{index}" for side, team in (("HOME", match.home), ("AWAY", match.away)) for index, player in enumerate(team.players)}
        side = lambda team: None if team is None else "HOME" if team is match.home else "AWAY"
        player_id = lambda player: None if player is None else identities.get(id(player))
        pending = match.pending_kick
        snapshot = {
            "step": step, "paused": paused, "status": asdict(match.status_snapshot()),
            "simulation_elapsed": match.simulation_elapsed,
            "home": _team_state(match.home, identities), "away": _team_state(match.away, identities),
            "ball": {"position": [match.ball.pos.x, match.ball.pos.y, match.ball.z],
                     "velocity": [match.ball.vel.x, match.ball.vel.y, match.ball.vertical_speed],
                     "owner": player_id(match.ball.owner)},
            "restart": None if not match.restart_type else {"kind": match.restart_type, "side": side(match.restart_team), "spot": [match.restart_spot.x, match.restart_spot.y], "taker": player_id(match.restart_taker), "elapsed": match.restart_elapsed},
            "throw_in": None if match.throw_in_team is None else {"side": side(match.throw_in_team), "spot": [match.throw_in_spot.x, match.throw_in_spot.y], "taker": player_id(match.thrower)},
            "pending_kick": None if pending is None else {"player": player_id(pending.player), "command": pending.command.name, "target_player": player_id(pending.target_player), "target_point": None if pending.target_point is None else [pending.target_point.x, pending.target_point.y]},
            "foul_count": match.foul_count, "card_count": match.card_count,
            "restart_counts": dict(match.restart_counts),
        }
        payload = {"snapshot": snapshot, "events": [event.to_payload() for event in match.event_history() if event.sequence > after_sequence],
                   "result": match.final_result().to_payload() if match.state == "FULLTIME" else None}
        return cls(json.dumps(payload, ensure_ascii=False, allow_nan=False))

    # {
    #   責務: [to_payload: 消費側が変更できる独立した観測値を返す]
    #   処理: [1: 保存JSONを新しい辞書へ復元する]
    #   引数: []
    #   戻り値: [dict: 呼出しごとに独立した観測]
    # }
    def to_payload(self) -> dict:
        return json.loads(self._json)
