"""Immutable observation of one message emitted by the match engine."""

from __future__ import annotations

from dataclasses import dataclass


# {
#   責務: [MatchLogEvent: 試合が表示文を出した瞬間の順序・二つの時計・文面を変更不可の値として保持する]
#   フィールド: [
#     sequence: 記録を有効にした試合内の1始まり通番。同時刻・同文面でも別の記録になる
#     game_time: 発生時の試合内秒数。セットプレー準備中は進まない
#     simulation_elapsed: 発生時の演算経過秒数。準備中の固定更新も含む
#     text: 発生時の表示文。物理イベント種別や選手IDを表す公開契約ではない
#   ]
# }
@dataclass(frozen=True, slots=True)
class MatchLogEvent:
    sequence: int
    game_time: float
    simulation_elapsed: float
    text: str

    # {
    #   責務: [to_payload: 一件の観測値を記録・比較用の独立した辞書へ写す]
    #   処理: [1: 通番・試合内秒数・演算経過秒数・表示文を同じ値で取り出す]
    #   引数: []
    #   戻り値: [dict: 呼出しごとに新しいJSON対応辞書。時計や通番を進めず、履歴列の並べ替えもしない]
    # }
    def to_payload(self) -> dict:
        """Return detached JSON values in chronological sequence order."""
        # 保持する値は数値・文字列なので、返す辞書を書き換えても記録へ反映しない。
        return {
            "sequence": self.sequence,
            "game_time": self.game_time,
            "simulation_elapsed": self.simulation_elapsed,
            "text": self.text,
        }
