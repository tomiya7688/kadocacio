"""One validated, immutable host operation, independent of match internals."""

from dataclasses import dataclass
import math

from scripts.core.match_protocol import OPERATION_KINDS, FIXED_PHYSICS_DT, SPEED_OPTIONS, is_json_integer


# {
#   責務: [MatchOperation: ホスト操作を検証済みの不変値として保持する]
#   フィールド: [kind: 操作種別; value: STEPのdtまたはSET_SPEEDの倍率]
# }
@dataclass(frozen=True, slots=True)
class MatchOperation:
    kind: str
    value: float | int | None = None

    # {
    #   責務: [from_payload: 操作の種別と種別固有の値を検証して生成する]
    #   処理: [1: 必須項目と余分な項目を検査; 2: 固定dtまたは倍率を検証・正規化]
    #   引数: [payload: 外部操作のJSON値]
    #   戻り値: [MatchOperation: 正常な操作。不正値はValueError]
    # }
    @classmethod
    def from_payload(cls, payload: object) -> "MatchOperation":
        if not isinstance(payload, dict) or payload.get("kind") not in OPERATION_KINDS:
            raise ValueError("unknown match operation")
        kind = payload["kind"]
        field = "dt" if kind == "STEP" else "value" if kind == "SET_SPEED" else None
        if set(payload) != ({"kind", field} if field else {"kind"}):
            raise ValueError("unexpected/missing operation fields")
        value = payload.get(field)
        if kind == "STEP" and (type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= FIXED_PHYSICS_DT):
            raise ValueError("STEP dt must be finite and in (0, 0.05]")
        if kind == "SET_SPEED" and (not is_json_integer(value) or value not in SPEED_OPTIONS):
            raise ValueError("unsupported speed")
        if kind == "SET_SPEED":
            value = int(value)
        return cls(kind, value)

    # {
    #   責務: [to_payload: 操作種別に合う項目だけをJSON値へ出す]
    #   処理: [1: kindと必要なdtまたはvalueで辞書を構成する]
    #   引数: []
    #   戻り値: [dict: 元の不変値を参照しない操作辞書]
    # }
    def to_payload(self) -> dict:
        return {"kind": self.kind, **({"dt": self.value} if self.kind == "STEP" else {"value": self.value} if self.kind == "SET_SPEED" else {})}
