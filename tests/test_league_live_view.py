import unittest
from copy import deepcopy

from scripts.league.league_live_view import (
    clamp_other_match_scroll,
    other_match_max_scroll,
    visible_other_matches,
    merged_live_results,
)


# {
#   責務: [LeagueLiveViewTests: 全会場への到達と独立した確定結果反映を検査する]
#   フィールド: []
# }
class LeagueLiveViewTests(unittest.TestCase):
    def test_ninety_matches_are_all_reachable(self) -> None:
        statuses = list(range(90))
        maximum = other_match_max_scroll(len(statuses))
        seen = set()
        for scroll_row in range(maximum + 1):
            visible, _, _ = visible_other_matches(statuses, scroll_row)
            seen.update(visible)
        self.assertEqual(seen, set(statuses))

    def test_grid_shows_up_to_twenty_seven_matches(self) -> None:
        visible, first, last = visible_other_matches(list(range(90)), 0)
        self.assertEqual((first, last), (0, 27))
        self.assertEqual(len(visible), 27)

    def test_scroll_is_clamped_after_status_count_changes(self) -> None:
        self.assertEqual(clamp_other_match_scroll(999, 90), other_match_max_scroll(90))
        self.assertEqual(clamp_other_match_scroll(10, 3), 0)

    # {
    #   責務: [test_final_scores_are_detached_from_cached_and_worker_statuses: 確定得点の表示用合成が元速報を変更しないことを確認する]
    #   処理: [1: 一致・不一致IDの速報を合成; 2: 終了時計と得点を確認; 3: 独立コピーと元値保持を確認]
    #   引数: []
    #   戻り値: [None: 元データの変更は試験失敗]
    # }
    def test_final_scores_are_detached_from_cached_and_worker_statuses(self) -> None:
        statuses = [{"fixture_id": "one", "game_time": 123, "state": "PLAYING", "home_score": 0},
                    {"fixture_id": "two", "game_time": 100, "state": "PLAYING", "home_score": 1}]
        results = [{"fixture_id": "one", "home_score": 2, "away_score": 1}]
        original_statuses, original_results = deepcopy(statuses), deepcopy(results)
        merged = merged_live_results(statuses, results)
        self.assertEqual((merged[0]["state"], merged[0]["game_time"], merged[0]["minute"]),
                         ("FULLTIME", 5400, 90))
        self.assertEqual((merged[0]["home_score"], merged[0]["away_score"]), (2, 1))
        self.assertEqual(merged[1], statuses[1])
        self.assertIsNot(merged[1], statuses[1])
        self.assertEqual(statuses, original_statuses)
        self.assertEqual(results, original_results)
        self.assertEqual(merged_live_results(statuses, []), original_statuses)

    # {
    #   責務: [test_missing_fixture_ids_never_match_unrelated_results: ID不明の速報へ無関係な終了結果を誤適用しないことを確認する]
    #   処理: [1: 欠落・null・空IDの速報と結果を合成; 2: 元速報と一致するか確認]
    #   引数: []
    #   戻り値: [None: 誤った確定結果反映は試験失敗]
    # }
    def test_missing_fixture_ids_never_match_unrelated_results(self) -> None:
        statuses = [{"state": "PLAYING"}, {"fixture_id": None}, {"fixture_id": ""}]
        results = [{"home_score": 9}, {"fixture_id": None, "home_score": 8},
                   {"fixture_id": "", "home_score": 7}]
        self.assertEqual(merged_live_results(statuses, results), statuses)

    # {
    #   責務: [test_numeric_fixture_id_zero_remains_a_valid_identity: 数値0のIDを未指定と誤認せず結果反映することを確認する]
    #   処理: [1: 数値と文字列0のIDを合成; 2: 対応得点と不一致IDの不変を確認]
    #   引数: []
    #   戻り値: [None: ID互換の欠落は試験失敗]
    # }
    def test_numeric_fixture_id_zero_remains_a_valid_identity(self) -> None:
        merged = merged_live_results([{"fixture_id": 0}, {"fixture_id": "other"}],
                                     [{"fixture_id": "0", "home_score": 3, "away_score": 2}])
        self.assertEqual(merged[0]["home_score"], 3)
        self.assertEqual(merged[1], {"fixture_id": "other"})


if __name__ == "__main__":
    unittest.main()
