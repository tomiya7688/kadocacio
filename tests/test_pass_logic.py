import random
import unittest

import pygame

from scripts.match.match_engine import (
    Match,
    PASS_CLEAN,
    PASS_DANGEROUS_LANE,
    PASS_OVERHIT,
    PASS_UNDERHIT,
    PASS_WRONG_DIRECTION,
    offside_position_active,
    score_pass_candidate,
)
from scripts.match.player_commands import PlayerCommand


class DummyTeam:
    def __init__(self, direction: int = 1):
        self.direction = direction


class DummyPlayer:
    def __init__(self, pos, intelligence: float, trap: float = 0.5, action=None):
        self.pos = pygame.Vector2(pos)
        self.team = DummyTeam()
        self.effective_intelligence = intelligence
        self.action_command = action if action is None else getattr(PlayerCommand, action)
        self._trap = trap
        self.sent_off = False
        self.is_keeper = False
        self.technique_success_factor = 1.0
        self.mistake_error_factor = 1.0

    def effective_stat(self, stat_name):
        if stat_name == "trap_technique":
            return self._trap
        return 0.5


class PassCandidateScoringTests(unittest.TestCase):
    def test_offside_line_uses_second_last_defender(self):
        match = Match.__new__(Match)
        match.home = type("Home", (), {})()
        match.away = type("Away", (), {})()
        match.home.players = [DummyPlayer((100, 0), intelligence=0.5)]
        match.away.players = [
            DummyPlayer((150, 0), intelligence=0.5),
            DummyPlayer((200, 0), intelligence=0.5),
            DummyPlayer((250, 0), intelligence=0.5),
        ]
        match.home.direction = 1

        self.assertEqual(match.offside_line(match.home), 200.0)

    def test_offside_position_is_symmetric_for_attack_direction(self):
        right_attack = offside_position_active(
            team_direction=1,
            attacker_x=500.0,
            passer_x=300.0,
            offside_line=450.0,
            in_opponent_half=True,
        )
        left_attack = offside_position_active(
            team_direction=-1,
            attacker_x=500.0,
            passer_x=700.0,
            offside_line=550.0,
            in_opponent_half=True,
        )

        self.assertTrue(right_attack)
        self.assertTrue(left_attack)
        self.assertEqual(right_attack, left_attack)

    def test_offside_position_is_inactive_on_the_line_for_both_directions(self):
        self.assertFalse(
            offside_position_active(
                team_direction=1,
                attacker_x=450.0,
                passer_x=300.0,
                offside_line=450.0,
                in_opponent_half=True,
            )
        )
        self.assertFalse(
            offside_position_active(
                team_direction=-1,
                attacker_x=550.0,
                passer_x=700.0,
                offside_line=550.0,
                in_opponent_half=True,
            )
        )

    def test_offside_position_requires_forward_progress(self):
        for direction in (1, -1):
            self.assertFalse(
                offside_position_active(
                    team_direction=direction,
                    attacker_x=500.0,
                    passer_x=500.0,
                    offside_line=450.0 if direction == 1 else 550.0,
                    in_opponent_half=True,
                )
            )

    def test_offside_position_is_inactive_in_own_half(self):
        for direction, attacker_x, passer_x, line in (
            (1, 500.0, 300.0, 450.0),
            (-1, 500.0, 700.0, 550.0),
        ):
            self.assertFalse(
                offside_position_active(
                    team_direction=direction,
                    attacker_x=attacker_x,
                    passer_x=passer_x,
                    offside_line=line,
                    in_opponent_half=False,
                )
            )

    def test_higher_intelligence_receivers_are_preferred(self):
        owner = DummyPlayer((0, 0), intelligence=0.4)
        smart = DummyPlayer((120, 0), intelligence=0.9, action="RECEIVE_PASS")
        dull = DummyPlayer((120, 0), intelligence=0.3, action="IDLE")
        rng = random.Random(0)

        smart_score = score_pass_candidate(
            owner,
            smart,
            lane_clearance=120.0,
            nearest_opponent_distance=80.0,
            forward_weight=1.0,
            pass_power=0.7,
            passing=0.8,
            intelligence=0.5,
            decision=0.8,
            rng=rng,
        )
        dull_score = score_pass_candidate(
            owner,
            dull,
            lane_clearance=120.0,
            nearest_opponent_distance=80.0,
            forward_weight=1.0,
            pass_power=0.7,
            passing=0.8,
            intelligence=0.5,
            decision=0.8,
            rng=rng,
        )

        self.assertGreater(smart_score, dull_score)

    def test_near_sideline_candidates_are_penalized(self):
        owner = DummyPlayer((0, 0), intelligence=0.5)
        target = DummyPlayer((140, 20), intelligence=0.7, action="SUPPORT")
        rng = random.Random(0)

        score = score_pass_candidate(
            owner,
            target,
            lane_clearance=140.0,
            nearest_opponent_distance=90.0,
            forward_weight=1.0,
            pass_power=0.7,
            passing=0.8,
            intelligence=0.6,
            decision=0.8,
            rng=rng,
        )

        self.assertLess(score, 300.0)

    def test_pass_accuracy_controls_explicit_mistake_outcomes(self):
        match = Match.__new__(Match)
        match.rng = random.Random(19)
        owner = DummyPlayer((0, 0), intelligence=0.5)
        low_accuracy = [match.choose_pass_outcome(owner, 0.08) for _ in range(1200)]
        high_accuracy = [match.choose_pass_outcome(owner, 0.98) for _ in range(1200)]

        self.assertGreater(low_accuracy.count(PASS_CLEAN), 0)
        self.assertGreater(low_accuracy.count(PASS_WRONG_DIRECTION), 0)
        self.assertGreater(low_accuracy.count(PASS_DANGEROUS_LANE), 0)
        self.assertGreater(low_accuracy.count(PASS_OVERHIT), 0)
        self.assertGreater(low_accuracy.count(PASS_UNDERHIT), 0)
        self.assertGreater(high_accuracy.count(PASS_CLEAN), low_accuracy.count(PASS_CLEAN))


if __name__ == "__main__":
    unittest.main()
