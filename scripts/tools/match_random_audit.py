"""Optional Python primitive-draw audit, with the default Random sequence intact."""

from copy import deepcopy
import random


class MatchRandomAudit(random.Random):
    def __init__(self, seed: int):
        super().__init__(seed)
        self.word_count = 0
        self.purpose = "construct"
        self.step = 0
        self._events = []

    def random(self) -> float:
        before = self.word_count
        value = super().random()
        self.word_count += 2
        self._record("random", [], value, before)
        return value

    def getrandbits(self, bits: int) -> int:
        before = self.word_count
        value = super().getrandbits(bits)
        self.word_count += (bits + 31) // 32
        self._record("getrandbits", [bits], value, before)
        return value

    def _record(self, method: str, arguments: list, value, before: int) -> None:
        self._events.append({"sequence": len(self._events) + 1, "step": self.step,
                             "purpose": self.purpose, "method": method, "arguments": arguments,
                             "value": value, "word_before": before, "word_after": self.word_count})
        if method == "getrandbits":
            self._events[-1]["bit_value"] = value

    def history(self) -> list[dict]:
        return deepcopy(self._events)

    def state_payload(self) -> dict:
        _, state, cached = self.getstate()
        return {"words": list(state[:-1]), "index": state[-1], "gauss_next": cached}
