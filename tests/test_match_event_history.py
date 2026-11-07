"""Optional full event history must not alter simulation or the bounded UI log."""

import unittest
from dataclasses import FrozenInstanceError

from scripts.core.settings import FIELD
from scripts.core.simulation_geometry import Vec2
from scripts.core.simulation_runtime import FIXED_PHYSICS_DT, advance_match_fixed
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import match_state_payload


# {
#   責務: [MatchEventHistoryTests: 任意の全件記録が表示ログ・時計・乱数・履歴の独立性を壊さないことを検査する]
#   フィールド: [home・away: 同条件の比較へ渡す読込済み二チーム。試験は元ファイルを変更しない]
# }
class MatchEventHistoryTests(unittest.TestCase):
    # {
    #   責務: [setUpClass: イベント観測の試験に共通の開始チームを用意する]
    #   処理: [1: 有効なチーム候補の先頭二件を読み込む]
    #   引数: []
    #   戻り値: [None: クラスへ両チームを保持する]
    # }
    @classmethod
    def setUpClass(cls):
        # 各試験は新しいMatchを作り、可変の試合内状態を共有しない。
        cls.home, cls.away = discover_team_choices()[:2]

    # {
    #   責務: [test_default_keeps_only_the_bounded_display_log: 通常設定は表示用の最新8件だけを残すことを確認する]
    #   処理: [1: 記録オフの試合へ12件追加する; 2: 表示件数と最新値・空の全履歴を確認する]
    #   引数: []
    #   戻り値: [None: 通常時の不要な全件保持や表示順の退行は試験失敗]
    # }
    def test_default_keeps_only_the_bounded_display_log(self):
        # 描画用の逆時系列ログと、任意の全件記録を混同しない。
        match = Match(self.home, self.away, seed=9)
        match.start_new()
        for index in range(12):
            match.add_event(f"event {index}")
        self.assertEqual(len(match.events), 8)
        self.assertEqual(match.events[0], (0, "event 11"))
        self.assertEqual(match.event_history(), ())

    # {
    #   責務: [test_full_history_retains_order_and_both_clocks: 全履歴が開始ログからの順序・二つの時計を保持することを確認する]
    #   処理: [1: 記録オンの試合へ時計を指定して12件追加する; 2: キックオフと通番・末尾時計・表示上限を確認する]
    #   引数: []
    #   戻り値: [None: 全履歴の切捨て・順序や時計の取り違えは試験失敗]
    # }
    def test_full_history_retains_order_and_both_clocks(self):
        # ここでは時計の採取値を検査し、試合の時間進行自体は模擬しない。
        match = Match(self.home, self.away, seed=9, record_events=True)
        match.start_new()
        match.game_time = 65.5
        for index in range(12):
            match.simulation_elapsed = 8.0 + index * 0.05
            match.add_event(f"event {index}")
        history = match.event_history()
        self.assertEqual(len(history), 13)
        self.assertEqual(history[0].text, "キックオフ！")
        self.assertEqual([event.sequence for event in history], list(range(1, 14)))
        self.assertEqual(history[-1].game_time, 65.5)
        self.assertEqual(history[-1].simulation_elapsed, 8.55)
        self.assertEqual(len(match.events), 8)

    # {
    #   責務: [test_history_is_immutable_and_a_new_match_resets_it: 値の変更を拒否し再開始時に内部履歴だけを初期化することを確認する]
    #   処理: [1: 追加ログの取得値と辞書を得る; 2: 辞書の変更と凍結フィールドへの代入を試す; 3: 再開始後の通番と取得済み値を確認する]
    #   引数: []
    #   戻り値: [None: 外部変更の伝播・再開始時の通番残留は試験失敗。再開始の乱数再現を保証する試験ではない]
    # }
    def test_history_is_immutable_and_a_new_match_resets_it(self):
        # start_newは同じ乱数器を使うが、記録列と通番は新しい試合として初期化する。
        match = Match(self.home, self.away, seed=9, record_events=True)
        match.start_new()
        match.add_event("保存済みイベント")
        history = match.event_history()
        payload = history[-1].to_payload()
        payload["text"] = "changed"
        with self.assertRaises(FrozenInstanceError):
            history[-1].text = "changed"
        match.start_new()
        self.assertEqual(len(match.event_history()), 1)
        self.assertEqual(match.event_history()[0].sequence, 1)
        self.assertEqual(history[-1].text, "保存済みイベント")

    # {
    #   責務: [test_recording_does_not_change_rng_or_match_state: 全件記録の有無で乱数消費や固定更新後の状態が変わらないことを確認する]
    #   処理: [1: 同seedの記録なし・あり試合を作る; 2: 両者を120固定更新する; 3: 記録列以外の全比較項目を照合する]
    #   引数: []
    #   戻り値: [None: 乱数指紋・状態・集計等の相違は試験失敗。90分完走や全物理状態の網羅比較ではない]
    # }
    def test_recording_does_not_change_rng_or_match_state(self):
        # 観測用の全履歴だけを除き、同じ比較ペイロードをそのまま突き合わせる。
        plain = Match(self.home, self.away, seed=811)
        recorded = Match(self.home, self.away, seed=811, record_events=True)
        for match in (plain, recorded):
            match.start_new()
            for _ in range(120):
                advance_match_fixed(match)
        left = match_state_payload(plain)
        right = match_state_payload(recorded)
        self.assertTrue(right.pop("event_history"))
        self.assertEqual(left.pop("event_history"), [])
        self.assertEqual(left, right)

    # {
    #   責務: [test_identical_messages_at_the_same_time_remain_distinct: 同文面・同時刻でも各発生を別の通番で残すことを確認する]
    #   処理: [1: 同じ時計のまま同文面を二度追加する; 2: 二件の辞書と連続する通番・同じ時計を照合する]
    #   引数: []
    #   戻り値: [None: 文面や時刻での重複排除・通番欠落・保存キーの変更は試験失敗]
    # }
    def test_identical_messages_at_the_same_time_remain_distinct(self):
        # 文字列や時計を識別子に使うと、別々の発生が失われるため通番で区別する。
        match = Match(self.home, self.away, seed=9, record_events=True)
        match.start_new()
        match.game_time = 125.25
        match.simulation_elapsed = 12.5
        match.add_event("同じ表示文")
        match.add_event("同じ表示文")
        self.assertEqual(
            [event.to_payload() for event in match.event_history()[-2:]],
            [
                {"sequence": 2, "game_time": 125.25, "simulation_elapsed": 12.5, "text": "同じ表示文"},
                {"sequence": 3, "game_time": 125.25, "simulation_elapsed": 12.5, "text": "同じ表示文"},
            ],
        )

    # {
    #   責務: [test_obtained_history_does_not_grow_after_later_events: 取得済みの履歴と辞書が後続の追加から独立していることを確認する]
    #   処理: [1: キックオフ直後の履歴と辞書を取得する; 2: 後続ログを追加する; 3: 旧履歴の型・件数と新履歴の追加値を照合する]
    #   引数: []
    #   戻り値: [None: 内部可変リストの流出や取得済み値の変更は試験失敗]
    # }
    def test_obtained_history_does_not_grow_after_later_events(self):
        # 比較途中の観測を保持しても、その後の記録で参照先が増えない契約を確かめる。
        match = Match(self.home, self.away, seed=9, record_events=True)
        match.start_new()
        earlier = match.event_history()
        saved_payload = earlier[0].to_payload()
        match.add_event("後続イベント")
        self.assertIsInstance(earlier, tuple)
        self.assertEqual(len(earlier), 1)
        self.assertEqual(earlier[0].to_payload(), saved_payload)
        self.assertEqual(len(match.event_history()), 2)
        self.assertEqual(match.event_history()[-1].text, "後続イベント")

    # {
    #   責務: [test_recorded_clocks_diverge_during_restart_preparation: 再開準備中の記録は停止した試合時計と進んだ演算時計を区別することを確認する]
    #   処理: [1: フリーキック・スローインの準備を個別に開始する; 2: 準備前後へ観測文を追加して4固定更新する; 3: まだ準備中であることと両時計を照合する]
    #   引数: []
    #   戻り値: [None: 時計の混同や準備中の更新欠落は試験失敗。再開後の全プレーを検証する試験ではない]
    # }
    def test_recorded_clocks_diverge_during_restart_preparation(self):
        # 実際の再開準備と共通固定更新を使い、時計の値を手動で進めて成功させない。
        for kind in ("FREE_KICK", "THROW_IN"):
            with self.subTest(kind=kind):
                match = Match(self.home, self.away, seed=9, record_events=True)
                match.start_new()
                match.banner_timer = 0.0
                match.game_time = 125.25
                if kind == "FREE_KICK":
                    match.start_set_piece(kind, match.home, Vec2(FIELD.center))
                else:
                    match.ball.last_touch = match.away.players[0]
                    match.ball.pos.update(FIELD.centerx, FIELD.top - 2)
                    match.start_throw_in()
                match.add_event("準備開始の観測")
                before = match.event_history()[-1]
                for _ in range(4):
                    advance_match_fixed(match)
                match.add_event("準備中の観測")
                after = match.event_history()[-1]
                self.assertTrue(match.throw_in_team is not None or match.restart_type)
                self.assertEqual((before.game_time, after.game_time), (125.25, 125.25))
                self.assertAlmostEqual(after.simulation_elapsed - before.simulation_elapsed, 4 * FIXED_PHYSICS_DT)


if __name__ == "__main__":
    unittest.main()
