"""Automotive Repair Business Workflows — Phase 11 catalog."""

from __future__ import annotations

from app.workflows.automotive.declined_estimate_recovery import (
    SPEC as DECLINED_ESTIMATE_SPEC,
)
from app.workflows.automotive.declined_estimate_recovery import build as build_declined_estimate
from app.workflows.automotive.inspection_completed import (
    SPEC as INSPECTION_COMPLETED_SPEC,
)
from app.workflows.automotive.inspection_completed import build as build_inspection_completed
from app.workflows.automotive.maintenance_reminder import (
    SPEC as MAINTENANCE_REMINDER_SPEC,
)
from app.workflows.automotive.maintenance_reminder import build as build_maintenance_reminder
from app.workflows.automotive.new_customer_phone_request import (
    SPEC as NEW_CUSTOMER_PHONE_SPEC,
)
from app.workflows.automotive.new_customer_phone_request import build as build_new_customer_phone
from app.workflows.automotive.repair_completed import SPEC as REPAIR_COMPLETED_SPEC
from app.workflows.automotive.repair_completed import build as build_repair_completed
from app.workflows.automotive.walk_in_customer import SPEC as WALK_IN_CUSTOMER_SPEC
from app.workflows.automotive.walk_in_customer import build as build_walk_in_customer
from app.workflows.models import WorkflowDefinition

AUTOMOTIVE_SPECS = [
    NEW_CUSTOMER_PHONE_SPEC,
    MAINTENANCE_REMINDER_SPEC,
    INSPECTION_COMPLETED_SPEC,
    DECLINED_ESTIMATE_SPEC,
    WALK_IN_CUSTOMER_SPEC,
    REPAIR_COMPLETED_SPEC,
]


def automotive_workflows() -> list[WorkflowDefinition]:
    return [
        build_new_customer_phone(),
        build_maintenance_reminder(),
        build_inspection_completed(),
        build_declined_estimate(),
        build_walk_in_customer(),
        build_repair_completed(),
    ]


__all__ = [
    "AUTOMOTIVE_SPECS",
    "automotive_workflows",
]
