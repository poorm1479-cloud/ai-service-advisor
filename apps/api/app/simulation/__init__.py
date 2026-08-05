"""Phase 12 — Auto Repair Simulation Engine package.

Simulation-only environment. Does not modify production business logic,
workflows, or plugins.
"""

from app.simulation.engine import SimulationEngine, run_simulations
from app.simulation.models import ScenarioKind, SimulationMetrics, SimulationReport, SimulationRunResult

__all__ = [
    "ScenarioKind",
    "SimulationEngine",
    "SimulationMetrics",
    "SimulationReport",
    "SimulationRunResult",
    "run_simulations",
]
