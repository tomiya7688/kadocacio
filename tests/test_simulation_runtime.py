import unittest

from simulation_runtime import MatchTelemetry, SimulationLimits, advance_match_fixed, run_headless_match


class _Position:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def distance_to(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


class _Command:
    value = "ウォーク"


class _Player:
    def __init__(self, team, x):
        self.team = team
        self.pos = _Position(x, 0.0)
        self.action_command = _Command()


class _Team:
    def __init__(self, offset):
        self.players = [_Player(self, offset), _Player(self, offset + 20.0)]


class _Ball:
    def __init__(self, owner):
        self.owner = owner
        self.pos = _Position(10.0, 0.0)


class _Match:
    def __init__(self):
        self.home = _Team(0.0)
        self.away = _Team(100.0)
        self.teams = (self.home, self.away)
        self.ball = _Ball(self.home.players[0])
        self.state = "PLAYING"
        self.game_time = 0.0
        self.received_steps = []

    def update_step(self, dt):
        self.received_steps.append(dt)
        self.game_time += dt * 10.0
        if self.game_time >= 2.0:
            self.state = "FULLTIME"


class SimulationRuntimeTests(unittest.TestCase):
    def test_headless_runner_advances_ai_and_clock_with_identical_fixed_steps(self):
        match = _Match()
        result = run_headless_match(match, SimulationLimits(sample_every_steps=1))
        self.assertTrue(result.fulltime)
        self.assertEqual(result.steps, 4)
        self.assertEqual(match.received_steps, [0.05, 0.05, 0.05, 0.05])

    def test_fixed_step_rejects_clock_skipping_size(self):
        with self.assertRaises(ValueError):
            advance_match_fixed(_Match(), 0.10)

    def test_telemetry_observes_commands_spacing_and_control_changes(self):
        match = _Match()
        telemetry = MatchTelemetry(match, crowd_radius=30.0)
        telemetry.observe_control()
        telemetry.sample()
        match.ball.owner = match.away.players[0]
        telemetry.observe_control()
        home = telemetry.team_metrics(match.home)
        away = telemetry.team_metrics(match.away)
        self.assertEqual(home["command_counts"]["ウォーク"], 2)
        self.assertEqual(home["crowded_player_ratio"], 1.0)
        self.assertEqual(home["turnovers"], 1)
        self.assertEqual(away["takeaways"], 1)


if __name__ == "__main__":
    unittest.main()
