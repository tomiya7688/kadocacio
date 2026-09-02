"""Precomputed quality metrics for one candidate pass."""

from dataclasses import dataclass

from scripts.core.simulation_geometry import Vec2


@dataclass
class PassRoute:
    """Carry a pass destination and interception margins between decisions."""

    destination: Vec2
    flight_time: float
    interception_risk: float
    receiver_margin: float
    touchline_margin: float
    lane_clearance: float
    opponent_clearance: float


__all__ = ("PassRoute",)
