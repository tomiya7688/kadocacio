import unittest
from copy import deepcopy

from scripts.league.league_live_view import (
    clamp_other_match_scroll,
    other_match_max_scroll,
    visible_other_matches,
    merged_live_results,
)


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

    def test_missing_fixture_ids_never_match_unrelated_results(self) -> None:
        statuses = [{"state": "PLAYING"}, {"fixture_id": None}, {"fixture_id": ""}]
        results = [{"home_score": 9}, {"fixture_id": None, "home_score": 8},
                   {"fixture_id": "", "home_score": 7}]
        self.assertEqual(merged_live_results(statuses, results), statuses)

    def test_numeric_fixture_id_zero_remains_a_valid_identity(self) -> None:
        merged = merged_live_results([{"fixture_id": 0}, {"fixture_id": "other"}],
                                     [{"fixture_id": "0", "home_score": 3, "away_score": 2}])
        self.assertEqual(merged[0]["home_score"], 3)
        self.assertEqual(merged[1], {"fixture_id": "other"})


if __name__ == "__main__":
    unittest.main()
