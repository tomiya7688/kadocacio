from __future__ import annotations

import unittest

from scripts.core.simulation_driver import RealtimeSimulationDriver


class FakeClock:
    def __init__(self, increment: float = 0.0) -> None:
        self.value = 0.0
        self.increment = increment

    def __call__(self) -> float:
        value = self.value
        self.value += self.increment
        return value


class FakeMatch:
    def __init__(self, speed: int = 1) -> None:
        self.state = "PLAYING"
        self.speed_multiplier = speed
        self.steps: list[float] = []

    def update_step(self, dt: float) -> None:
        self.steps.append(dt)


class RealtimeSimulationDriverTests(unittest.TestCase):
    def test_normal_speed_advances_the_available_fraction(self):
        match = FakeMatch(speed=1)
        driver = RealtimeSimulationDriver(clock=FakeClock())
        count = driver.advance(match, 1.0 / 60.0)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(match.steps[0], 1.0 / 60.0)
        self.assertAlmostEqual(driver.pending_time, 0.0)

    def test_fast_forward_yields_after_wall_time_budget(self):
        match = FakeMatch(speed=100)
        driver = RealtimeSimulationDriver(
            wall_time_budget=0.006,
            max_backlog=2.0,
            clock=FakeClock(increment=0.004),
        )
        count = driver.advance(match, 1.0 / 60.0)
        self.assertEqual(count, 2)
        self.assertGreater(driver.pending_time, 1.5)
        self.assertTrue(all(step <= 0.05 for step in match.steps))

    def test_backlog_is_bounded_without_skipping_executed_physics(self):
        match = FakeMatch(speed=100)
        driver = RealtimeSimulationDriver(
            wall_time_budget=0.0,
            max_backlog=0.20,
            clock=FakeClock(),
        )
        driver.advance(match, 1.0)
        self.assertGreater(driver.dropped_time, 99.0)
        self.assertLessEqual(driver.pending_time, 0.20)
        self.assertAlmostEqual(match.steps[0], 0.05)

    def test_new_match_does_not_inherit_old_backlog(self):
        driver = RealtimeSimulationDriver(wall_time_budget=0.0, clock=FakeClock())
        first = FakeMatch(speed=100)
        driver.advance(first, 0.02)
        self.assertGreater(driver.pending_time, 0.0)
        second = FakeMatch(speed=1)
        driver.advance(second, 0.01)
        self.assertAlmostEqual(sum(second.steps), 0.01)


if __name__ == "__main__":
    unittest.main()
