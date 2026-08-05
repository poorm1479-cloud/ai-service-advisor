"""Simulation data models — Phase 12 Auto Repair Simulation Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ScenarioKind(StrEnum):
    NEW_CUSTOMER_PHONE = "new_customer_phone_request"
    MAINTENANCE_REMINDER = "maintenance_reminder"
    INSPECTION_COMPLETED = "inspection_completed"
    DECLINED_ESTIMATE = "declined_estimate_recovery"
    WALK_IN = "walk_in_customer"
    REPAIR_COMPLETED = "repair_completed"


@dataclass(slots=True)
class SyntheticCustomer:
    id: UUID
    name: str
    phone: str
    email: str
    retention_score: float  # 0..1


@dataclass(slots=True)
class SyntheticVehicle:
    id: UUID
    customer_id: UUID | None
    vin: str
    year: int
    make: str
    model: str
    mileage: int
    health_score: float  # 0..100


@dataclass(slots=True)
class SyntheticConversation:
    id: UUID
    customer_id: UUID | None
    channel: str
    body: str
    intent: str


@dataclass(slots=True)
class SyntheticRepairRequest:
    id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    complaint: str
    recommended_service: str
    estimated_cost: float


@dataclass(slots=True)
class SyntheticAppointment:
    id: UUID
    customer_id: UUID | None
    vehicle_id: UUID | None
    repair_type: str
    booked: bool


@dataclass(slots=True)
class SyntheticInspection:
    id: UUID
    vehicle_id: UUID | None
    findings: list[str]
    phase: str = "inspection"


@dataclass(slots=True)
class SyntheticEstimate:
    id: UUID
    customer_id: UUID | None
    amount: float
    status: str  # sent | approved | declined


@dataclass(slots=True)
class SyntheticPayment:
    id: UUID
    invoice_id: UUID
    amount: float
    paid: bool


@dataclass(slots=True)
class AiDecisionRecord:
    decision_type: str
    confidence: float
    accurate: bool
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CapabilityCallRecord:
    capability: str
    success: bool
    error: str | None = None
    result_summary: str | None = None


@dataclass(slots=True)
class PluginCallRecord:
    plugin: str
    capability: str
    success: bool
    error: str | None = None


@dataclass(slots=True)
class EventRecord:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowStepRecord:
    name: str
    status: str
    error: str | None = None


@dataclass(slots=True)
class SimulationRunResult:
    run_id: UUID
    scenario: ScenarioKind
    shop_id: UUID
    success: bool
    started_at: datetime
    finished_at: datetime
    customer: SyntheticCustomer | None = None
    vehicle: SyntheticVehicle | None = None
    conversation: SyntheticConversation | None = None
    repair: SyntheticRepairRequest | None = None
    appointment: SyntheticAppointment | None = None
    inspection: SyntheticInspection | None = None
    estimate: SyntheticEstimate | None = None
    payment: SyntheticPayment | None = None
    decisions: list[AiDecisionRecord] = field(default_factory=list)
    capabilities: list[CapabilityCallRecord] = field(default_factory=list)
    plugins: list[PluginCallRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    workflow_steps: list[WorkflowStepRecord] = field(default_factory=list)
    workflow_names: list[str] = field(default_factory=list)
    escalated: bool = False
    revenue_opportunity_detected: bool = False
    appointment_converted: bool = False
    retention_prediction: float | None = None
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SimulationMetrics:
    total_runs: int = 0
    successful_runs: int = 0
    workflow_success_rate: float = 0.0
    ai_decision_accuracy: float = 0.0
    decision_confidence_avg: float = 0.0
    plugin_failure_rate: float = 0.0
    appointment_conversion_rate: float = 0.0
    revenue_opportunity_detection_rate: float = 0.0
    customer_retention_prediction_avg: float = 0.0
    human_escalation_rate: float = 0.0
    by_scenario: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class SimulationReport:
    report_id: UUID = field(default_factory=uuid4)
    generated_at: datetime | None = None
    run_count: int = 0
    metrics: SimulationMetrics = field(default_factory=SimulationMetrics)
    summary: str = ""
    workflow_performance: list[dict[str, Any]] = field(default_factory=list)
    revenue_impact: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    failed_steps: list[dict[str, Any]] = field(default_factory=list)
    ai_decisions: list[dict[str, Any]] = field(default_factory=list)
    runs: list[SimulationRunResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "run_count": self.run_count,
            "summary": self.summary,
            "metrics": {
                "total_runs": self.metrics.total_runs,
                "successful_runs": self.metrics.successful_runs,
                "workflow_success_rate": self.metrics.workflow_success_rate,
                "ai_decision_accuracy": self.metrics.ai_decision_accuracy,
                "decision_confidence_avg": self.metrics.decision_confidence_avg,
                "plugin_failure_rate": self.metrics.plugin_failure_rate,
                "appointment_conversion_rate": self.metrics.appointment_conversion_rate,
                "revenue_opportunity_detection_rate": self.metrics.revenue_opportunity_detection_rate,
                "customer_retention_prediction_avg": self.metrics.customer_retention_prediction_avg,
                "human_escalation_rate": self.metrics.human_escalation_rate,
                "by_scenario": self.metrics.by_scenario,
            },
            "workflow_performance": self.workflow_performance,
            "revenue_impact": self.revenue_impact,
            "errors": self.errors,
            "failed_steps": self.failed_steps,
            "ai_decisions": self.ai_decisions[:100],
        }
