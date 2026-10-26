"""A match seed must cover initialization as well as fixed-step play."""

import hashlib
import random
import unittest
from queue import SimpleQueue
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from scripts.app.game_app import Game
from scripts.core.match_seed import league_fixture_seed
from scripts.core.simulation_runtime import advance_match_fixed
from scripts.league.league_simulation_workers import _match_output, _run_headless_league_match, _run_synchronized_match_batch
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import match_state_payload


# {
#   責務: [MatchSeedContractTests: seedが初期化・固定更新・リーグの両実行経路へ一貫して適用されることを確認する]
#   フィールド: [home_choice・away_choice: 各試合へ渡す共有の開始チーム入力]
# }
class MatchSeedContractTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: seed契約試験の両チームを準備する]
    #   処理: [1: 有効チーム候補から先頭二件を保持する]
    #   引数: []
    #   戻り値: [None: クラスの開始入力を設定する。保存ファイルを変更しない]
    # }
    @classmethod
    def setUpClass(cls):
        # seed以外の入力を揃え、初期化や固定更新の差を比較する。
        cls.home_choice, cls.away_choice = discover_team_choices()[:2]

    # {
    #   責務: [new_match: 固定した両チームと会場に指定seedを構築時から適用する]
    #   処理: [1: 共通入力とseedを渡して新しいMatchを作る]
    #   引数: [seed: 構築前から適用する整数seed]
    #   戻り値: [Match: 未開始の独立した試合。初期選手の抽選も指定seedに従う]
    # }
    def new_match(self, seed: int) -> Match:
        # 構築後のrng.seedでは再現できない初期抽選まで対象にする。
        return Match(self.home_choice, self.away_choice, "HOME", seed=seed)

    # {
    #   責務: [test_seeded_matches_reproduce_initial_state_and_fixed_steps: 同seedの初期選手値と80固定更新後の主要状態が一致することを確認する]
    #   処理: [1: 二試合を構築しグローバル乱数不変と初期抽選一致を照合する; 2: 同じ固定更新を80回行う; 3: 乱数・時計・得点・イベント・座標・体力を比較する]
    #   引数: []
    #   戻り値: [None: 初期抽選または固定更新の再現性が失われると試験失敗。90分完走の試験ではない]
    # }
    def test_seeded_matches_reproduce_initial_state_and_fixed_steps(self):
        # 試合専用seedの指定が、プロセス全体の乱数状態を変更しないか確認する。
        global_state = random.getstate()
        first = self.new_match(7103)
        second = self.new_match(7103)
        self.assertEqual(random.getstate(), global_state)
        self.assertEqual(first.seed, 7103)
        self.assertEqual(first.rng.getstate(), second.rng.getstate())
        self.assertEqual(
            [(player.skill, player.roam_timer) for team in first.teams for player in team.players],
            [(player.skill, player.roam_timer) for team in second.teams for player in team.players],
        )

        # 時計だけを飛ばさず、両経路へ同じ物理ステップを与える。
        first.start_new()
        second.start_new()
        for _ in range(80):
            advance_match_fixed(first)
            advance_match_fixed(second)

        self.assertEqual(first.rng.getstate(), second.rng.getstate())
        self.assertEqual(
            (first.game_time, first.home.score, first.away.score), (second.game_time, second.home.score, second.away.score)
        )
        self.assertEqual(tuple(first.events), tuple(second.events))
        self.assertEqual(
            (first.ball.pos.x, first.ball.pos.y, first.ball.z), (second.ball.pos.x, second.ball.pos.y, second.ball.z)
        )
        self.assertEqual(
            [(player.pos.x, player.pos.y, player.stamina) for team in first.teams for player in team.players],
            [(player.pos.x, player.pos.y, player.stamina) for team in second.teams for player in team.players],
        )

    # {
    #   責務: [test_distinct_seeds_change_pre_kickoff_player_state: 異なるseedが開始前の個体抽選へ作用することを確認する]
    #   処理: [1: 同じチームで異なるseedの二試合を構築する; 2: 初期個体補正の差を確認する]
    #   引数: []
    #   戻り値: [None: seedが初期抽選へ接続されていないと試験失敗]
    # }
    def test_distinct_seeds_change_pre_kickoff_player_state(self):
        # 試合開始後の違いだけでは、構築時のseed適用を証明できない。
        first = self.new_match(1)
        second = self.new_match(2)
        self.assertNotEqual(first.home.players[0].skill, second.home.players[0].skill)

    # {
    #   責務: [test_league_fixture_seed_keeps_existing_background_formula: 共通seed計算が旧リーグ式と再現性を維持することを確認する]
    #   処理: [1: 既知の入力から旧式の期待seedを計算する; 2: 同じ入力の一致と試合ID変更時の差を確認する]
    #   引数: []
    #   戻り値: [None: 文字列化・ハッシュの取出し・バイト順が変わると試験失敗]
    # }
    def test_league_fixture_seed_keeps_existing_background_formula(self):
        # ライブラリのhash()や別のID方式へ変更されないよう旧式を独立して照合する。
        expected = int.from_bytes(hashlib.sha256(b"round-1:Home:Away").digest()[:8], "big")
        self.assertEqual(league_fixture_seed("round-1", "Home", "Away"), expected)
        self.assertEqual(league_fixture_seed("round-1", "Home", "Away"), expected)
        self.assertNotEqual(league_fixture_seed("round-2", "Home", "Away"), expected)

    # {
    #   責務: [test_watched_league_fixture_uses_shared_seed: 観戦入口とヘッドレスの同じ対戦が同seedと短区間の結果を共有することを確認する]
    #   処理: [1: 画面初期化を省いた観戦入口へ対戦を渡す; 2: 共通式のseedを確認する; 3: 観戦側80更新と同上限のヘッドレス出力を比較する]
    #   引数: []
    #   戻り値: [None: seedや演算出力が異なると試験失敗。実ウィンドウ操作の検証ではない]
    # }
    def test_watched_league_fixture_uses_shared_seed(self):
        # 観戦入口のseed配線に絞り、無関係な画面・他会場起動を模擬する。
        fixture = {
            "id": "round-1",
            "home_id": self.home_choice["id"],
            "away_id": self.away_choice["id"],
        }
        game = Game.__new__(Game)
        game.league_manager = SimpleNamespace(
            day=1,
            choices_by_id={fixture["home_id"]: self.home_choice, fixture["away_id"]: self.away_choice},
            fixtures_on_day=lambda _day, *, unplayed_only: [fixture],
        )
        game.start_league_simulations = lambda _fixtures, *, live_updates: None
        game.visible_simulation = SimpleNamespace(reset=lambda _match: None)
        game.roll_stadium_guests = lambda: None
        game.reset_camera = lambda: None

        Game.start_league_fixture(game, fixture)

        self.assertEqual(
            game.match.seed,
            league_fixture_seed(fixture["id"], self.home_choice["name"], self.away_choice["name"]),
        )
        # 観戦側とヘッドレス側で同じ固定更新数を消費させる。
        for _ in range(80):
            advance_match_fixed(game.match)
        headless = _run_headless_league_match(
            {
                "fixture": fixture,
                "home_choice": self.home_choice,
                "away_choice": self.away_choice,
                "max_match_steps": 80,
            }
        )
        self.assertEqual(headless["engine_steps"], 80)
        self.assertEqual(
            {key: headless[key] for key in _match_output(game.match)},
            _match_output(game.match),
        )

    # {
    #   責務: [test_real_headless_and_batch_workers_share_seed_and_state: 同一対戦の単独処理と同期バッチが短区間の実Match状態を共有することを確認する]
    #   処理: [1: 実Matchを保持する構築窓口を用意する; 2: 同じ対戦を両ワーカー入口で83固定更新する; 3: 構築seed・乱数指紋を含む状態・共通結果項目を照合する]
    #   引数: []
    #   戻り値: [None: 初期化または固定更新の差は試験失敗。実子プロセス・90分・描画速度の検証ではない]
    # }
    def test_real_headless_and_batch_workers_share_seed_and_state(self):
        # 実試合核を使い、移動や乱数を模擬して経路間の差を隠さない。
        matches = []

        # {
        #   責務: [construct_observed_match: ワーカーの構築引数から実Matchを作り比較用参照を保持する]
        #   処理: [1: 引数を変更せず実Matchへ渡す; 2: 構築済み試合を保持して返す]
        #   引数: [args・kwargs: ワーカーが渡したMatch構築引数]
        #   戻り値: [Match: 通常の演算状態。観測参照の保持で乱数や時計は進めない]
        # }
        def construct_observed_match(*args, **kwargs):
            # 参照を記録するだけで、開始・更新・seed設定を肩代わりしない。
            match = Match(*args, **kwargs)
            matches.append(match)
            return match

        job = {
            "fixture": {"id": "worker-seed-contract"},
            "home_choice": self.home_choice,
            "away_choice": self.away_choice,
            "max_match_steps": 83,
            "ai_rethink_multiplier": 0.75,
        }
        with patch("scripts.league.league_simulation_workers.Match", side_effect=construct_observed_match):
            headless = _run_headless_league_match(job)
            batch = _run_synchronized_match_batch([job], SimpleNamespace(value=-1.0), SimpleQueue(), Event())
        self.assertEqual(len(matches), 2)
        expected_seed = league_fixture_seed(job["fixture"]["id"], self.home_choice["name"], self.away_choice["name"])
        self.assertEqual([match.seed for match in matches], [expected_seed, expected_seed])
        self.assertEqual(match_state_payload(matches[0]), match_state_payload(matches[1]))
        self.assertEqual(len(batch), 1)
        self.assertEqual({key: headless[key] for key in batch[0]}, batch[0])
        self.assertEqual((headless["engine_steps"], batch[0]["engine_steps"]), (83, 83))
        self.assertFalse(headless["fulltime"])


if __name__ == "__main__":
    unittest.main()
