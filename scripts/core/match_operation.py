"""One validated, immutable host operation, independent of match internals."""

from dataclasses import dataclass
import math

from scripts.core.match_protocol import OPERATION_KINDS, FIXED_PHYSICS_DT, SPEED_OPTIONS, is_json_integer


@dataclass(frozen=True, slots=True)
class MatchOperation:
    kind: str
    value: float | int | None = None

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

    def to_payload(self) -> dict:
        return {"kind": self.kind, **({"dt": self.value} if self.kind == "STEP" else {"value": self.value} if self.kind == "SET_SPEED" else {})}
