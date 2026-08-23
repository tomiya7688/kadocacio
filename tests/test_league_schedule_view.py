import unittest

from scripts.league.league_schedule_view import (
    clamp_schedule_scroll,
    schedule_max_scroll,
    visible_schedule_fixtures,
)


class LeagueScheduleViewTests(unittest.TestCase):
    def test_all_ninety_fixtures_can_be_reached_for_watch_booking(self) -> None:
        fixtures = list(range(90))
        seen = set()
        for scroll_row in range(schedule_max_scroll(len(fixtures)) + 1):
            visible, _, _ = visible_schedule_fixtures(fixtures, scroll_row)
            seen.update(visible)
        self.assertEqual(seen, set(fixtures))

    def test_first_view_displays_sixteen_reservable_fixtures(self) -> None:
        visible, first, last = visible_schedule_fixtures(list(range(90)), 0)
        self.assertEqual((first, last), (0, 16))
        self.assertEqual(len(visible), 16)

    def test_schedule_scroll_clamps_when_match_count_changes(self) -> None:
        self.assertEqual(clamp_schedule_scroll(999, 90), schedule_max_scroll(90))
        self.assertEqual(clamp_schedule_scroll(10, 2), 0)


if __name__ == "__main__":
    unittest.main()
