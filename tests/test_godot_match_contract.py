"""Real Match adapter, shared input, exact/tolerant reports, safe fixture tooling."""

import json
import math
import tempfile
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from scripts.core.match_operation import MatchOperation
from scripts.core.match_protocol import is_json_integer
from scripts.core.match_trace_comparison import compare_traces, first_difference, validate_trace
from scripts.core.settings import FIELD, MATCH_SECONDS
from scripts.core.simulation_geometry import Vec2
from scripts.match.match_session import MatchSession
from scripts.match.pending_kick import PendingKick
from scripts.match.player_command import PlayerCommand
from scripts.tools import godot_match_contract as contract, godot_match_fixture as fixture
from scripts.tools.godot_team_oracle import public_team_paths, reference_case
from scripts.tools.match_contract_cases import comparison_cases, input_cases, trace_cases
from scripts.tools.match_contract_input import create_contract_input, restore_contract_input
from scripts.tools.match_contract_trace import capture_trace


# {
#   責務: [GodotMatchContractTests: 実Match境界の再現性・検証・独立観測・CLI安全性を検査する]
#   フィールド: [choices: 公開2チームの選択値; operations: 参照操作列; input: 共通試合入力; trace: 実参照観測列]
# }
class GodotMatchContractTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: 実参照エンジンで共通の試験入力と観測を準備する]
    #   処理: [1: 公開チームを復元; 2: 停止と倍率を含む操作列を作成; 3: 固定seedの観測を捕捉]
    #   引数: []
    #   戻り値: [None: クラスの共有fixtureを設定する]
    # }
    @classmethod
    def setUpClass(cls):
        cls.choices = [reference_case(json.loads(path.read_text(encoding="utf-8-sig")), path.relative_to(fixture.PROJECT_ROOT / "teams").as_posix())["choice"] for path in public_team_paths()[:2]]
        cls.operations = [{"kind": "START"}, {"kind": "STEP", "dt": 0.05}, {"kind": "SET_SPEED", "value": 100}, {"kind": "PAUSE"}, {"kind": "STEP", "dt": 0.05}, {"kind": "RESUME"}, {"kind": "STEP", "dt": 0.025}]
        cls.input = create_contract_input(*cls.choices, cls.operations, seed=2**63 + 12345, max_steps=20, venue_mode="NEUTRAL", ai_rethink_multiplier=1.0)
        cls.trace = capture_trace(cls.input)

    # {
    #   責務: [session: 共通入力から試験ごとに独立した未開始セッションを作る]
    #   処理: [1: 契約入力を復元; 2: 同じ再現設定でセッションを生成]
    #   引数: []
    #   戻り値: [MatchSession: 別試験の状態変更に影響されないセッション]
    # }
    def session(self):
        home, away, settings, _ = restore_contract_input(self.input)
        return MatchSession(home, away, **settings)

    # {
    #   責務: [test_operation_and_input_detach_validation_and_whole_json_numbers: 操作制約と整数JSON表現・コピー独立性を検査する]
    #   処理: [1: 操作の正常・不正値を確認; 2: 不正seedと入力を確認; 3: 整数float正規化と元入力保持を確認]
    #   引数: []
    #   戻り値: [None: 期待との差はunittest失敗]
    # }
    def test_operation_and_input_detach_validation_and_whole_json_numbers(self):
        for value, valid in ((0, True), (1.0, True), (1.5, False), (True, False), (None, False), (float("nan"), False), (10**500, False)):
            self.assertEqual(is_json_integer(value), valid)
        for payload in self.operations:
            operation = MatchOperation.from_payload(payload)
            self.assertEqual(operation.to_payload(), payload)
            with self.assertRaises(FrozenInstanceError):
                operation.kind = "other"
        for payload in (None, {}, {"kind": "unknown"}, {"kind": "START", "extra": 1}, {"kind": "STEP"}, {"kind": "STEP", "dt": True}, {"kind": "STEP", "dt": math.nan}, {"kind": "STEP", "dt": -1}, {"kind": "STEP", "dt": 0.1}, {"kind": "SET_SPEED", "value": True}, {"kind": "SET_SPEED", "value": 4}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                MatchOperation.from_payload(payload)
        self.assertEqual(MatchOperation.from_payload({"kind": "SET_SPEED", "value": 10.0}).value, 10)
        for row in input_cases(self.input):
            self.assertFalse(row["valid"], row["name"])
        for seed in ("", " 0", "bad", "01", "-0", "0" * 4097):
            actual = deepcopy(self.input)
            actual["repro_input"]["settings"]["seed"] = seed
            with self.subTest(seed=seed[:15]), self.assertRaises(ValueError):
                restore_contract_input(actual)
        for actual in (None, {"format": "bad"}, {**self.input, "version": 99}, {**self.input, "operations": {}}, {**self.input, "operations": [{"kind": "START"}] + [{"kind": "STEP", "dt": 0.05}] * 21}):
            with self.assertRaises(ValueError):
                restore_contract_input(actual)
        actual = deepcopy(self.input)
        actual["version"] = 1.0
        actual["repro_input"]["settings"]["max_steps"] = 20.0
        actual["repro_input"]["teams"]["home"]["primary"] = [1.0, 2.0, 3.0]
        home, _, settings, operations = restore_contract_input(actual)
        self.assertEqual(home["primary"], (1, 2, 3))
        self.assertEqual(settings["seed"], 2**63 + 12345)
        operations.clear()
        self.assertTrue(actual["operations"])
        for team in (None, {"name": "no id", "primary": {}}):
            actual = deepcopy(self.input)
            actual["repro_input"]["teams"]["home"] = team
            with self.assertRaises(ValueError):
                restore_contract_input(actual)

    # {
    #   責務: [test_real_adapter_replay_fixed_step_pause_and_immutable_observation: 再現操作が時計・停止・イベントカーソルを守るか検査する]
    #   処理: [1: 再実行と更新数を比較; 2: 開始順・カーソル・予算の拒否を確認; 3: 不変観測と深いコピーを確認]
    #   引数: []
    #   戻り値: [None: 境界違反を試験失敗にする]
    # }
    def test_real_adapter_replay_fixed_step_pause_and_immutable_observation(self):
        self.assertEqual(self.trace, capture_trace(self.input))
        entries = self.trace["entries"]
        self.assertEqual(entries[4]["snapshot"]["simulation_elapsed"], 0.05)
        self.assertEqual(entries[-1]["snapshot"]["simulation_elapsed"], 0.07500000000000001)
        self.assertEqual(entries[-1]["snapshot"]["step"], 2)
        self.assertEqual(entries[-1]["snapshot"]["status"]["speed_multiplier"], 100)
        session = self.session()
        with self.assertRaises(ValueError):
            session.observe()
        with self.assertRaises(ValueError):
            session.apply({"kind": "PAUSE"})
        session.apply({"kind": "START"})
        with self.assertRaises(ValueError):
            session.apply({"kind": "START"})
        for cursor in (-1, False):
            with self.assertRaises(ValueError):
                session.observe(cursor)
        observation = session.observe()
        payload = observation.to_payload()
        payload["snapshot"]["ball"]["position"][0] = -100
        self.assertNotEqual(payload, observation.to_payload())
        with self.assertRaises(FrozenInstanceError):
            observation._json = "{}"
        self.assertEqual(len(session.observe().to_payload()["events"]), 1)
        self.assertEqual(session.observe(1).to_payload()["events"], [])
        session._max_steps = 0
        with self.assertRaises(ValueError):
            session.apply({"kind": "STEP", "dt": 0.05})

    # {
    #   責務: [test_restart_pending_kick_owner_and_fulltime_use_existing_rules: 再開とキック待ち・終了結果が既存Match由来であることを検査する]
    #   処理: [1: 再開中の時計と担当者を観測; 2: 実Matchを終了させて結果を照合; 3: 終了後の停止と結果差分を確認]
    #   引数: []
    #   戻り値: [None: 偽の結果や進行は試験失敗]
    # }
    def test_restart_pending_kick_owner_and_fulltime_use_existing_rules(self):
        session = self.session()
        session.apply({"kind": "START"})
        match = session._match  # Test setup only; not an API exposed to UI.
        match.start_set_piece("FREE_KICK", match.away, Vec2(FIELD.center))
        snapshot = session.observe().to_payload()["snapshot"]
        self.assertEqual(snapshot["restart"]["side"], "AWAY")
        session.apply({"kind": "STEP", "dt": 0.05})
        self.assertEqual(session.observe().to_payload()["snapshot"]["status"]["game_time"], 0)
        match.restart_type = ""
        match.throw_in_team = match.home
        match.thrower = match.home.players[0]
        match.pending_kick = PendingKick(match.home.players[0], PlayerCommand.PASS, target_player=match.home.players[1], target_point=Vec2(FIELD.center))
        snapshot = session.observe().to_payload()["snapshot"]
        self.assertEqual(snapshot["throw_in"]["taker"], "HOME:0")
        self.assertEqual(snapshot["pending_kick"]["command"], "PASS")
        match.pending_kick.target_point = None
        self.assertIsNone(session.observe().to_payload()["snapshot"]["pending_kick"]["target_point"])
        match.throw_in_team = None
        match.pending_kick = None
        match.ball.owner = None
        match.banner_timer = 0
        match.halftime_done = True
        match.game_time = MATCH_SECONDS - 0.5
        session.apply({"kind": "STEP", "dt": 0.05})
        observation = session.observe().to_payload()
        self.assertEqual(observation["snapshot"]["status"]["state"], "FULLTIME")
        self.assertEqual(observation["result"], json.loads(json.dumps(match.final_result().to_payload())))
        elapsed = observation["snapshot"]["simulation_elapsed"]
        session.apply({"kind": "STEP", "dt": 0.05})
        self.assertEqual(session.observe().to_payload()["snapshot"]["simulation_elapsed"], elapsed)
        trace = {**deepcopy(self.trace), "entries": [{"operation_index": 0, **observation}]}
        actual = deepcopy(trace)
        actual["entries"][0]["result"]["home_score"] += 1
        self.assertIsNotNone(compare_traces(trace, actual)["first_result_difference"])

    # {
    #   責務: [test_reports_first_state_event_result_and_exact_vs_tolerant_values: 差分報告の順序・カテゴリと数値許容差を検査する]
    #   処理: [1: 共通期待報告を照合; 2: seed・長さ・型の差を確認; 3: 位置の許容差と得点の厳密性を確認]
    #   引数: []
    #   戻り値: [None: 報告が誤ると試験失敗]
    # }
    def test_reports_first_state_event_result_and_exact_vs_tolerant_values(self):
        for row in comparison_cases(self.trace):
            self.assertEqual(row["report"], compare_traces(row["expected"], row["actual"]))
        actual = deepcopy(self.trace)
        actual["entries"][1]["snapshot"]["status"]["game_time"] += 1
        actual["entries"][0]["events"][0]["text"] += "!"
        report = compare_traces(self.trace, actual)
        self.assertEqual(report["first_difference"]["step"], 0)
        self.assertEqual(report["first_state_difference"]["step"], 1)
        self.assertEqual(report["first_event_difference"]["category"], "event")
        self.assertEqual(report["kernel_parity"], "not_evaluated")
        actual = deepcopy(self.trace)
        actual["source"]["execution"] = "contract_roundtrip"
        self.assertEqual(compare_traces(self.trace, actual)["scope"], "contract_roundtrip")
        actual["source"]["seed_text"] = "1"
        self.assertEqual(compare_traces(self.trace, actual)["first_difference"]["category"], "input")
        shorter = {**self.trace, "entries": self.trace["entries"][:-1]}
        self.assertEqual(compare_traces(self.trace, shorter)["first_difference"]["reason"], "missing_entry")
        self.assertEqual(compare_traces(shorter, self.trace)["first_difference"]["reason"], "missing_entry")
        for left, right in (({}, {"key": None}), ([1], [1, 2]), ([1], [2]), (False, 0), ({"score": 1}, {"score": 1.00000001})):
            self.assertIsNotNone(first_difference(left, right))
        self.assertIsNone(first_difference({"position": [2000.0]}, {"position": [2000.0002]}))
        self.assertIsNone(first_difference(None, None))

    # {
    #   責務: [test_malformed_traces_do_not_pass_as_equal: 不正観測を自己比較の一致で見逃さないことを検査する]
    #   処理: [1: 共通破損ケースを自己比較; 2: 必須項目とイベント・JSON型の破損を列挙; 3: 全件の拒否を確認]
    #   引数: []
    #   戻り値: [None: 不正値の受理は試験失敗]
    # }
    def test_malformed_traces_do_not_pass_as_equal(self):
        for row in trace_cases(self.trace):
            self.assertFalse(row["valid"], row["name"])
            with self.assertRaises(ValueError):
                compare_traces(row["trace"], row["trace"])
        invalids = [None, {}, {**self.trace, "version": True}, {**self.trace, "source": {}}, {**self.trace, "entries": []}]
        for path, value in (("operation_index", -1), ("snapshot", None), ("events", None), ("result", [])):
            actual = deepcopy(self.trace)
            actual["entries"][0][path] = value
            invalids.append(actual)
        for key, value in (("step", False), ("status", {}), ("ball", {}), ("home", {}), ("away", None), ("extra", math.nan), ("object", object())):
            actual = deepcopy(self.trace)
            actual["entries"][0]["snapshot"][key] = value
            invalids.append(actual)
        for event in ({}, {"sequence": True}, {"sequence": 0}, None):
            actual = deepcopy(self.trace)
            actual["entries"][0]["events"] = [event]
            invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["source"].pop("rng")
        invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["entries"][0]["snapshot"]["home"]["players"] = [None]
        invalids.append(actual)
        actual = deepcopy(self.trace)
        actual["extra"] = {1: "invalid JSON key"}
        invalids.append(actual)
        for actual in invalids:
            with self.assertRaises(ValueError):
                validate_trace(actual)

    # {
    #   責務: [test_portable_numbers_and_result_phase: 巨大数による比較の例外漏れと終了結果の位相不整合を防ぐ]
    #   処理: [1: 整数範囲の境界・小数・巨大値を入力と観測で検査; 2: 途中結果と終了結果欠落を拒否; 3: 実終了結果の受理を確認]
    #   引数: []
    #   戻り値: [None: 全不正値がValueErrorになることを確認]
    # }
    def test_portable_numbers_and_result_phase(self):
        for value in (9_000_000_000_000_000, 9e15, -9_000_000_000_000_000, 10**500, True, 1.5):
            invalid_input = deepcopy(self.input)
            invalid_input["repro_input"]["settings"]["max_steps"] = value
            with self.subTest(budget=value), self.assertRaises(ValueError):
                restore_contract_input(invalid_input)
        for value in (9_000_000_000_000_000, 9e15, -9_000_000_000_000_000, 10**500, -10**500):
            invalid = deepcopy(self.trace)
            invalid["extra"] = {"nested": [value]}
            with self.subTest(observation=value), self.assertRaises(ValueError):
                compare_traces(invalid, invalid)
        session = self.session()
        session.apply({"kind": "START"})
        session._match.state = "FULLTIME"
        final = {**deepcopy(self.trace), "entries": [{"operation_index": 0, **session.observe().to_payload()}]}
        validate_trace(final)
        missing = deepcopy(final)
        missing["entries"][0]["result"] = None
        with self.assertRaisesRegex(ValueError, "exactly at FULLTIME"):
            validate_trace(missing)
        premature = deepcopy(final)
        premature["entries"][0]["snapshot"]["status"]["state"] = "PLAYING"
        with self.assertRaisesRegex(ValueError, "exactly at FULLTIME"):
            validate_trace(premature)
        maximum = deepcopy(self.input)
        maximum["repro_input"]["settings"]["max_steps"] = 8_999_999_999_999_999
        self.assertEqual(restore_contract_input(maximum)[2]["max_steps"], 8_999_999_999_999_999)
        portable = deepcopy(self.trace)
        portable["extra"] = {"nested": [8_999_999_999_999_999, -8_999_999_999_999_999, 0.5, False]}
        self.assertTrue(compare_traces(portable, portable)["same_observations"])

    # {
    #   責務: [test_contract_export_and_safe_public_fixture_cli: 定義の導出・公開fixture保存・比較CLIの失敗経路を検査する]
    #   処理: [1: 古い定義と不正予算を検査; 2: 一時出力へのfixture保存を確認; 3: 外部観測の一致・不一致・引数失敗を確認]
    #   引数: []
    #   戻り値: [None: 元データを変更せず期待終了コードを確認]
    # }
    def test_contract_export_and_safe_public_fixture_cli(self):
        with self.assertRaises(ValueError):
            MatchSession(*self.choices, seed=None, venue_mode="NEUTRAL", ai_rethink_multiplier=1.0, max_steps=1)
        self.assertTrue(contract.check_contract())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertFalse(contract.check_contract(output / "missing.json"))
            path = output / "contract.json"
            with patch.object(contract, "CONTRACT_PATH", path):
                self.assertEqual(contract.main(["--write"]), 0)
            self.assertTrue(contract.check_contract(path))
            path.write_text("{}", encoding="utf-8")
            self.assertFalse(contract.check_contract(path))
            for valid in (False, True):
                with patch.object(contract, "check_contract", return_value=valid):
                    self.assertEqual(contract.main([]), 0 if valid else 1)
            path, fingerprints = fixture.write_fixture(output, 2)
            self.assertTrue(path.is_file())
            self.assertEqual(len(fingerprints), 2)
            for steps in (0, 501, True):
                with self.assertRaises(ValueError):
                    fixture.write_fixture(output, steps)
            with patch.object(fixture, "check_contract", return_value=False), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            with patch.object(fixture, "public_team_paths", return_value=[]), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            with patch.object(fixture, "reference_case", return_value={"valid": False}), self.assertRaises(ValueError):
                fixture.write_fixture(output)
            native = output / "native.json"
            native.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8"))["reference"]), encoding="utf-8")
            self.assertEqual(fixture.main(["--fixture", str(path), "--actual", str(native), "--output", str(output)]), 0)
            actual = json.loads(native.read_text(encoding="utf-8"))
            actual["entries"][0]["snapshot"]["status"]["home_score"] += 1
            native.write_text(json.dumps(actual), encoding="utf-8")
            self.assertEqual(fixture.main(["--fixture", str(path), "--actual", str(native), "--output", str(output)]), 1)
            for args in (["--actual", str(native)], ["--fixture", str(path)], ["--actual", "missing", "--fixture", str(path)]):
                self.assertEqual(fixture.main(args), 2)
            with patch.object(fixture, "write_fixture", return_value=(path, {})):
                self.assertEqual(fixture.main([]), 0)
