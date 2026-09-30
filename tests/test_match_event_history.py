"""Optional full event history must not alter simulation or the bounded UI log."""

import unittest
from dataclasses import FrozenInstanceError

from scripts.core.simulation_runtime import advance_match_fixed
from scripts.match.match_engine import Match
from scripts.team.team_data import discover_team_choices
from scripts.tools.match_repro_check import match_state_payload


class MatchEventHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home, cls.away = discover_team_choices()[:2]

    def test_default_keeps_only_the_bounded_display_log(self):
        match = Match(self.home, self.away, seed=9)
        match.start_new()
        for index in range(12):
            match.add_event(f"event {index}")
        self.assertEqual(len(match.events), 8)
        self.assertEqual(match.events[0], (0, "event 11"))
        self.assertEqual(match.event_history(), ())

    def test_full_history_retains_order_and_both_clocks(self):
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

    def test_history_is_immutable_and_a_new_match_resets_it(self):
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

    def test_recording_does_not_change_rng_or_match_state(self):
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


if __name__ == "__main__":
    unittest.main()
