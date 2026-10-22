"""Optional Python primitive-draw audit, with the default Random sequence intact."""

from copy import deepcopy
import random


# {
#   責務: [MatchRandomAudit: Python参照試合の基本抽選と消費語数を乱数列を変えずに記録する]
#   フィールド: [word_count: 消費した32bit語の累計; purpose: 抽選用途; step: 物理更新番号; _events: 抽選履歴。乱数状態と正規乱数キャッシュは親が保持]
# }
class MatchRandomAudit(random.Random):
    # {
    #   責務: [__init__: 整数seedの乱数状態と空の監査履歴を準備する]
    #   処理: [1: 親のRandomをseedで初期化する; 2: 消費語数・用途・更新番号と履歴を初期化する]
    #   引数: [seed: 参照試合で利用する整数seed]
    #   戻り値: [None: 観測を開始できる乱数状態を構築する]
    # }
    def __init__(self, seed: int):
        # 乱数列はPython標準実装へ委ね、監査状態だけを追加する。
        super().__init__(seed)
        self.word_count = 0
        self.purpose = "construct"
        self.step = 0
        self._events = []

    # {
    #   責務: [random: 親と同じ一様乱数を返し二語の消費を記録する]
    #   処理: [1: 消費前の語数を保存する; 2: 親のrandomを呼ぶ; 3: 二語を加算して履歴へ記録する]
    #   引数: []
    #   戻り値: [float: 親と同じ0以上1未満の値。監査で追加抽選しない]
    # }
    def random(self) -> float:
        # CPythonの53bit実数生成は32bit語を二つ消費する。
        before = self.word_count
        value = super().random()
        self.word_count += 2
        self._record("random", [], value, before)
        return value

    # {
    #   責務: [getrandbits: 親の整数乱数と必要語数を記録する]
    #   処理: [1: 消費前の語数を保存する; 2: 親のgetrandbitsを呼ぶ; 3: bit数から消費語数を加算し履歴へ記録する]
    #   引数: [bits: 必要なbit数。妥当性と生成範囲はPython標準実装に従う]
    #   戻り値: [int: 親と同じ非負整数。不正入力の例外は親から伝播する]
    # }
    def getrandbits(self, bits: int) -> int:
        # 32bit未満の端数にも一語必要だが、0bitでは語を消費しない。
        before = self.word_count
        value = super().getrandbits(bits)
        self.word_count += (bits + 31) // 32
        self._record("getrandbits", [bits], value, before)
        return value

    # {
    #   責務: [_record: 抽選一件の用途・結果・消費語区間を履歴へ追加する]
    #   処理: [1: 連番と更新番号を付けて記録する; 2: bit抽選には整数比較用の値も付ける]
    #   引数: [method: 基本抽選名; arguments: 基本抽選の引数; value: 抽選結果; before: 抽選前の累計語数]
    #   戻り値: [None: _eventsを一件増やす。乱数状態は変更しない]
    # }
    def _record(self, method: str, arguments: list, value, before: int) -> None:
        # 呼出し元が設定した用途と物理更新番号を抽選時点で保存する。
        self._events.append({"sequence": len(self._events) + 1, "step": self.step,
                             "purpose": self.purpose, "method": method, "arguments": arguments,
                             "value": value, "word_before": before, "word_after": self.word_count})
        if method == "getrandbits":
            self._events[-1]["bit_value"] = value

    # {
    #   責務: [history: 記録済み抽選履歴を深いコピーとして返す]
    #   処理: [1: 配列・辞書・引数配列を再帰的に複製する]
    #   引数: []
    #   戻り値: [list[dict]: 独立した履歴。呼出し元の編集は元履歴へ影響しない]
    # }
    def history(self) -> list[dict]:
        # 差分レポート側で整形しても元の観測証拠を保つ。
        return deepcopy(self._events)

    # {
    #   責務: [state_payload: Godotと比較する乱数語・位置・正規乱数キャッシュを返す]
    #   処理: [1: 親から状態を読み取る; 2: 624語と次語位置とキャッシュを境界形式へ写す]
    #   引数: []
    #   戻り値: [dict: words・index・gauss_next。観測で乱数を消費しない]
    # }
    def state_payload(self) -> dict:
        # Python固有のバージョン番号は比較形式に含めない。
        _, state, cached = self.getstate()
        return {"words": list(state[:-1]), "index": state[-1], "gauss_next": cached}
