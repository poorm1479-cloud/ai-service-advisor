"""Scenario registry."""

from __future__ import annotations

from app.simulation.models import ScenarioKind
from app.simulation.scenarios.base import BaseScenario
from app.simulation.scenarios.declined_estimate import DeclinedEstimateScenario
from app.simulation.scenarios.inspection_completed import InspectionCompletedScenario
from app.simulation.scenarios.maintenance_reminder import MaintenanceReminderScenario
from app.simulation.scenarios.new_customer_phone import NewCustomerPhoneScenario
from app.simulation.scenarios.repair_completed import RepairCompletedScenario
from app.simulation.scenarios.walk_in_customer import WalkInCustomerScenario

SCENARIO_REGISTRY: dict[ScenarioKind, type[BaseScenario]] = {
    ScenarioKind.NEW_CUSTOMER_PHONE: NewCustomerPhoneScenario,
    ScenarioKind.MAINTENANCE_REMINDER: MaintenanceReminderScenario,
    ScenarioKind.INSPECTION_COMPLETED: InspectionCompletedScenario,
    ScenarioKind.DECLINED_ESTIMATE: DeclinedEstimateScenario,
    ScenarioKind.WALK_IN: WalkInCustomerScenario,
    ScenarioKind.REPAIR_COMPLETED: RepairCompletedScenario,
}


def all_scenarios() -> list[BaseScenario]:
    return [cls() for cls in SCENARIO_REGISTRY.values()]


__all__ = ["SCENARIO_REGISTRY", "all_scenarios", "BaseScenario"]
