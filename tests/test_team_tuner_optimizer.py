import random
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.core.settings import MATCH_SECONDS
from scripts.team.team_tuner import (
    TeamTunerSession,
    _simulate_tuner_job,
    automatic_opponent_priority,
    category_mean_values,
    mutate_payload_distribution,
)


# {
#   責務: [TeamTunerOptimizerTests: 相手優先度・能力予算・ジョブ実行と部分終了の採否契約を検査する]
#   フィールド: []
# }
class TeamTunerOptimizerTests(unittest.TestCase):
    # {
    #   責務: [_match_fixture: 実更新入口へ渡せる独立した模擬試合を作る]
    #   処理: [1: 集計用の両チームと時計を生成する; 2: 固定入力を記録する試験内更新関数を接続する]
    #   引数: [step_seconds: 1更新で模擬時計を進める量; fulltime: 更新時にFULLTIMEへ移すか]
    #   戻り値: [SimpleNamespace: メモリ上の試合。物理精度や実チームの性能を模擬するものではない]
    # }
    def _match_fixture(self, step_seconds, fulltime):
        # 型を増やさず、試験が必要とする状態だけを独立したデータとして作る。
        teams = [
            SimpleNamespace(
                players=[SimpleNamespace(stamina_ratio=0.8, action_command="ウォーク")], score=0, shots=1, possession=1.0
            )
            for _ in range(2)
        ]
        match = SimpleNamespace(home=teams[0], away=teams[1], rng=random.Random(), state="READY", game_time=0.0, steps=[])

        # {
        #   責務: [update_step: 模擬試合の固定更新入力を記録して指定の終了条件へ進める]
        #   処理: [1: dtを記録し模擬時計を進める; 2: 指定時だけ完走状態へ移す]
        #   引数: [dt: 共通固定更新入口が渡した演算秒数]
        #   戻り値: [None: このfixtureの時計・steps・stateだけを変更する]
        # }
        def update_step(dt):
            # 模擬時計の進み方は試験用であり、実エンジンの早送りではない。
            match.steps.append(dt)
            match.game_time += step_seconds
            if fulltime:
                match.state = "FULLTIME"

        match.update_step = update_step
        return match

    # {
    #   責務: [test_reachable_stronger_opponent_gets_more_priority_than_easy_win: 勝てそうな格上を大差勝ちより重視することを確認する]
    #   処理: [1: 僅差負けと大差勝ちの指標を採点する; 2: 優先度と分類を比較する]
    #   引数: []
    #   戻り値: [None: 容易な相手が優先されると試験失敗]
    # }
    def test_reachable_stronger_opponent_gets_more_priority_than_easy_win(self):
        # 勝敗だけでなく内容の近さを含む指標を使う。
        reachable, reachable_label, _ = automatic_opponent_priority(
            {
                "得点": 1,
                "失点": 2,
                "シュート": 8,
                "被シュート": 9,
                "支配率": 48,
            }
        )
        easy, easy_label, _ = automatic_opponent_priority(
            {
                "得点": 5,
                "失点": 0,
                "シュート": 15,
                "被シュート": 2,
                "支配率": 68,
            }
        )
        self.assertEqual(reachable_label, "勝てそうな格上")
        self.assertEqual(easy_label, "大幅優勢")
        self.assertGreater(reachable, easy)

    # {
    #   責務: [test_close_win_has_own_class_and_remains_high_priority: 僅差勝ちを独立分類し練習相手として残すことを確認する]
    #   処理: [1: 僅差勝ちと大差勝ちを採点する; 2: 分類と優先度を照合する]
    #   引数: []
    #   戻り値: [None: 僅差勝ちの分類欠落や優先度低下は試験失敗]
    # }
    def test_close_win_has_own_class_and_remains_high_priority(self):
        # 僅差の勝利も、内容改善に使う高優先度の相手とする。
        close_win, label, _ = automatic_opponent_priority(
            {
                "得点": 2,
                "失点": 1,
                "シュート": 9,
                "被シュート": 8,
                "支配率": 52,
            }
        )
        easy, _, _ = automatic_opponent_priority(
            {
                "得点": 5,
                "失点": 0,
                "シュート": 15,
                "被シュート": 2,
                "支配率": 68,
            }
        )
        self.assertEqual(label, "僅差で勝っている")
        self.assertGreater(close_win, easy)

    # {
    #   責務: [test_scouting_normalizes_weights_and_locks_readable_classes: 偵察結果の重み正規化と分類の表示を確認する]
    #   処理: [1: 最小セッションと相手ごとの指標を作る; 2: 重みを校正して分類・合計・優先順を照合する]
    #   引数: []
    #   戻り値: [None: 重みや分類が契約と異なると試験失敗]
    # }
    def test_scouting_normalizes_weights_and_locks_readable_classes(self):
        # 試合の実行とは分けて、結果からの重み付けだけを検査する。
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": "close"}, {"id": "easy"}]
        session.opponent_names = {"close": "接戦相手", "easy": "大勝相手"}
        session.opponent_weights = {"close": 1.0, "easy": 1.0}
        session.opponent_classes = {"close": "偵察前", "easy": "偵察前"}
        session.opponent_signals = {"close": 0.0, "easy": 0.0}
        session.opponent_weights_ready = False
        close = {"得点": 1, "失点": 2, "シュート": 8, "被シュート": 9, "支配率": 48}
        easy = {"得点": 5, "失点": 0, "シュート": 15, "被シュート": 2, "支配率": 68}
        session._calibrate_opponent_weights(
            [
                {"opponent_key": "close", "metrics": close},
                {"opponent_key": "close", "metrics": close},
                {"opponent_key": "easy", "metrics": easy},
                {"opponent_key": "easy", "metrics": easy},
            ]
        )
        self.assertTrue(session.opponent_weights_ready)
        self.assertAlmostEqual(sum(session.opponent_weights.values()), 2.0, places=6)
        self.assertGreater(session.opponent_weights["close"], session.opponent_weights["easy"])
        self.assertEqual(session.opponent_classes["close"], "勝てそうな格上")

    # {
    #   責務: [test_scouting_keeps_only_highest_priority_opponents_for_later_trials: 速度優先の偵察後に上位の相手を選ぶことを確認する]
    #   処理: [1: 7相手の両会場分の結果を作る; 2: 校正後の3相手を照合する]
    #   引数: []
    #   戻り値: [None: 速度優先で低優先度の相手が残ると試験失敗]
    # }
    def test_scouting_keeps_only_highest_priority_opponents_for_later_trials(self):
        # speedだけが偵察後の相手数を絞る条件を作る。
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": f"team-{index}"} for index in range(7)]
        session.opponent_names = {f"team-{index}": f"相手{index}" for index in range(7)}
        session.opponent_weights = {key: 1.0 for key in session.opponent_names}
        session.opponent_classes = {key: "偵察前" for key in session.opponent_names}
        session.opponent_signals = {key: 0.0 for key in session.opponent_names}
        session.opponent_weights_ready = False
        session.adaptive_opponent_limit = 3
        session.evaluation_mode = "speed"
        results = []
        for index in range(7):
            metrics = {
                "得点": 1,
                "失点": 2 if index < 3 else 0,
                "シュート": 8,
                "被シュート": 9 if index < 3 else 3,
                "支配率": 48 if index < 3 else 65,
            }
            results.extend(
                [
                    {"opponent_key": f"team-{index}", "metrics": metrics},
                    {"opponent_key": f"team-{index}", "metrics": metrics},
                ]
            )
        session._calibrate_opponent_weights(results)
        self.assertEqual(len(session.active_opponent_keys), 3)
        self.assertEqual(session.active_opponent_keys, {"team-0", "team-1", "team-2"})

    # {
    #   責務: [test_accuracy_mode_keeps_every_scouted_opponent: 精度優先では偵察した全相手を残すことを確認する]
    #   処理: [1: 7相手の結果を精度優先で校正する; 2: 全IDが残ることを照合する]
    #   引数: []
    #   戻り値: [None: 精度優先で相手が削られると試験失敗]
    # }
    def test_accuracy_mode_keeps_every_scouted_opponent(self):
        # 速度優先と同じ上限設定でも、accuracyは全件を評価する。
        session = TeamTunerSession.__new__(TeamTunerSession)
        session.opponents = [{"id": f"team-{index}"} for index in range(7)]
        session.opponent_names = {f"team-{index}": f"相手{index}" for index in range(7)}
        session.opponent_weights = {key: 1.0 for key in session.opponent_names}
        session.opponent_classes = {key: "偵察前" for key in session.opponent_names}
        session.opponent_signals = {key: 0.0 for key in session.opponent_names}
        session.opponent_weights_ready = False
        session.adaptive_opponent_limit = 3
        session.evaluation_mode = "accuracy"
        results = []
        for index in range(7):
            metrics = {"得点": index % 3, "失点": 1, "シュート": 7, "被シュート": 8, "支配率": 49}
            results.extend(
                [
                    {"opponent_key": f"team-{index}", "metrics": metrics},
                    {"opponent_key": f"team-{index}", "metrics": metrics},
                ]
            )
        session._calibrate_opponent_weights(results)
        self.assertEqual(session.active_opponent_keys, set(session.opponent_names))

    # {
    #   責務: [test_local_mutation_redistributes_fields_without_changing_category_mean: 個別値を動かしながら系統平均を保つことを確認する]
    #   処理: [1: 不均等なキック系配分を作る; 2: 固定乱数で変異させる; 3: 配分変更と平均/合計の不変を照合する]
    #   引数: []
    #   戻り値: [None: 個別値固定や系統予算の変化は試験失敗]
    # }
    def test_local_mutation_redistributes_fields_without_changing_category_mean(self):
        # 平均だけが制約であり、1100/700等の偏りは探索できる。
        category = {
            "id": "kick",
            "fields": ["シュート力", "シュート精度", "パス精度", "パス力"],
        }
        payload = {
            "選手一覧": [
                {
                    "名前": "配分テスト",
                    "ポジション": "FW",
                    "プレイヤータイプ": "ストライカー",
                    "シュート力": "1100",
                    "シュート精度": "700",
                    "パス精度": "900",
                    "パス力": "900",
                }
            ]
        }
        before = category_mean_values(payload, [category])["kick"]
        original = tuple(payload["選手一覧"][0][field] for field in category["fields"])

        mutate_payload_distribution(
            payload,
            [category],
            include_hidden=True,
            rng=random.Random(17),
            strength=0.12,
        )

        after = category_mean_values(payload, [category])["kick"]
        changed = tuple(payload["選手一覧"][0][field] for field in category["fields"])
        self.assertEqual(after, before)
        self.assertNotEqual(changed, original)
        self.assertEqual(sum(map(int, changed)), 3600)

    # {
    #   責務: [test_repeated_mutation_can_discover_uneven_allocations: 繰返し探索で均等値以外へ到達できることを確認する]
    #   処理: [1: 均等な4能力を固定乱数で30回変異する; 2: 予算の保持と能力間の差を照合する]
    #   引数: []
    #   戻り値: [None: 予算増減や探索幅の欠落は試験失敗]
    # }
    def test_repeated_mutation_can_discover_uneven_allocations(self):
        # 処理時間やチームの強さではなく、配分探索の可動性を検査する。
        category = {"id": "kick", "fields": ["シュート力", "シュート精度", "パス精度", "パス力"]}
        payload = {
            "選手一覧": [
                {
                    "ポジション": "FW",
                    "プレイヤータイプ": "ストライカー",
                    **{field: "900" for field in category["fields"]},
                }
            ]
        }
        rng = random.Random(23)
        for _ in range(30):
            mutate_payload_distribution(payload, [category], include_hidden=True, rng=rng, strength=0.10)
        values = [int(payload["選手一覧"][0][field]) for field in category["fields"]]
        self.assertEqual(sum(values), 3600)
        self.assertGreater(max(values) - min(values), 100)

    # {
    #   責務: [test_candidate_job_evaluates_every_opponent_home_and_away: 全相手の両会場へ指定seedで試合を構築することを確認する]
    #   処理: [1: 即時完走する独立4試合を用意する; 2: 実ワーカーを実行する; 3: 件数・両側・構築seedを照合する]
    #   引数: []
    #   戻り値: [None: 対戦漏れ・会場片寄り・seed欠落は試験失敗。実物理の完走を証明しない]
    # }
    def test_candidate_job_evaluates_every_opponent_home_and_away(self):
        # Matchの構築だけをモック化し、既存ワーカーの更新・集計は実行する。
        matches = [self._match_fixture(MATCH_SECONDS, True) for _ in range(4)]
        job = {
            "candidate": {"チーム名": "候補", "略称": "候"},
            "opponents": [{"id": "A", "name": "A"}, {"id": "B", "name": "B"}],
            "fixture_seeds": [1, 2, 3, 4],
            "clock_acceleration": 10.0,
            "wall_time_limit": 1.0,
        }
        memory_choice = {"id": "memory:tuner-worker", "name": "候補", "short": "候"}
        with (
            patch("scripts.team.team_tuner.team_choice_from_payload", return_value=memory_choice),
            patch(
                "scripts.team.team_tuner.Match",
                side_effect=matches,
            ) as constructor,
        ):
            result = _simulate_tuner_job(job)

        calls = [(call.args[0].get("id"), call.args[1].get("id")) for call in constructor.call_args_list]
        self.assertEqual(result["fixture_count"], 4)
        self.assertEqual(result["completed_matches"], 4)
        self.assertEqual(len(calls), 4)
        self.assertTrue(any(home == "memory:tuner-worker" for home, _ in calls))
        self.assertTrue(any(away == "memory:tuner-worker" for _, away in calls))
        self.assertEqual([call.kwargs["seed"] for call in constructor.call_args_list], [1, 2, 3, 4])

    # {
    #   責務: [test_speed_job_completes_at_short_evaluation_target_without_clock_skip: 短い評価区間でも共通固定更新を通すことを確認する]
    #   処理: [1: 1更新60秒の模擬試合を用意する; 2: 600秒目標でワーカーを実行する; 3: 目標・進行率・演算dtを照合する]
    #   引数: []
    #   戻り値: [None: 目標到達前の完了報告や固定ステップ上限超過は試験失敗。模擬時計を物理精度と混同しない]
    # }
    def test_speed_job_completes_at_short_evaluation_target_without_clock_skip(self):
        # 模擬時計は区間到達だけを作り、渡されるdtは共通入口の値を記録する。
        match = self._match_fixture(60.0, False)
        job = {
            "candidate": {"チーム名": "候補", "略称": "候"},
            "opponents": [{"id": "A", "name": "A"}],
            "venues": [True],
            "fixture_seeds": [1],
            "clock_acceleration": 1.0,
            "wall_time_limit": 1.0,
            "target_game_time": 600.0,
        }
        memory_choice = {"id": "memory:tuner-worker", "name": "候補", "short": "候"}
        with (
            patch("scripts.team.team_tuner.team_choice_from_payload", return_value=memory_choice),
            patch(
                "scripts.team.team_tuner.Match",
                return_value=match,
            ),
        ):
            result = _simulate_tuner_job(job)

        self.assertEqual(result["completed_matches"], 1)
        self.assertEqual(result["evaluation_target"], 600.0)
        self.assertEqual(result["metrics"]["進行率"], 600.0 / MATCH_SECONDS * 100.0)
        self.assertEqual(len(match.steps), 10)
        self.assertTrue(all(0 < dt <= 0.05 for dt in match.steps))

    # {
    #   責務: [test_partial_matches_cannot_be_accepted_or_report_convergence: 部分試合の高得点を採用や収束へ使わないことを確認する]
    #   処理: [1: 完走ゼロの高得点futureと期限切れセッションを作る; 2: 回収入口を実行する; 3: 不採用・終了理由を照合する]
    #   引数: []
    #   戻り値: [None: 未完走候補の採用・完走数加算・誤った収束報告は試験失敗]
    # }
    def test_partial_matches_cannot_be_accepted_or_report_convergence(self):
        # 可変状態のためだけのクラスを増やさず、非同期APIの返答だけを固定する。
        session = TeamTunerSession.__new__(TeamTunerSession)
        future = Mock()
        future.done.return_value = True
        future.result.return_value = {"score": 999.0, "completed_matches": 0, "metrics": {"進行率": 80.0}}
        session.pending_trials = {future: 0}
        session.active_parallel_candidate = {"選手一覧": []}
        session.active_parallel_results = []
        session.active_parallel_expected = 1
        session.parallel_failures = 0
        session.parallel_worker_count = 1
        session.completed_matches = 0
        session.last_score = 0.0
        session.last_metrics = {}
        session.best_score = float("-inf")
        session.best_payload = {"元": True}
        session.accepted_trials = 0
        session.stagnant_trials = 99
        session.stagnant_limit = 1
        session.trials = 3
        session.opponents = [{"name": "相手"}]
        session.deadline = time.perf_counter() - 0.1
        session.executor = Mock()
        session.finished = False
        session.finish_reason = ""
        session.parallel_enabled = True

        session._step_parallel()

        self.assertEqual(session.accepted_trials, 0)
        self.assertEqual(session.best_payload, {"元": True})
        self.assertEqual(session.completed_matches, 0)
        self.assertEqual(session.finish_reason, "時間上限に到達（完走試合なし）")


if __name__ == "__main__":
    unittest.main()
