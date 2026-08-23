import unittest

from scripts.league.league_live_view import (
    clamp_other_match_scroll,
    other_match_max_scroll,
    visible_other_matches,
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


if __name__ == "__main__":
    unittest.main()
