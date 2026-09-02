"""Frontend-independent scheduling for a rendered match simulation.

The match engine owns football state and fixed physics.  A frontend only feeds
real elapsed time into this driver and renders the latest completed state.  The
small wall-time budget prevents fast-forward from monopolising the UI thread;
no physics step is skipped inside the retained backlog.
"""

from scripts.core.realtime_simulation_driver import RealtimeSimulationDriver
from scripts.core.step_match import StepMatch


__all__ = ("RealtimeSimulationDriver", "StepMatch")
