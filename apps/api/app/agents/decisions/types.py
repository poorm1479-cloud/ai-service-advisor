"""AI Decision Layer — strongly typed decision objects.

AI modules propose these; Workflow Engine executes them.
AI must never mutate CRM, scheduling, marketing, or external systems.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID


class DecisionKind(StrEnum):
    INTENT = "intent"
    APPOINTMENT = "appointment"
    CUSTOMER = "customer"
    VEHICLE = "vehicle"
    CRM = "crm"
    MARKETING = "marketing"
    REVENUE = "revenue"
    PRIORITY = "priority"
    SUMMARY = "summary"
    ESCALATION = "escalation"
    MEMORY = "memory"
    # AI Service Advisor
    REPAIR_RECOMMENDATION = "repair_recommendation"
    ESTIMATE_EXPLANATION = "estimate_explanation"
    APPROVAL_REQUEST = "approval_request"
    REPAIR_STATUS = "repair_status"
    MAINTENANCE_REMINDER = "maintenance_reminder"
    REVIEW_REQUEST = "review_request"
    RETENTION = "retention"
    CUSTOMER_COMMUNICATION = "customer_communication"
    # Inspection Intelligence
    INSPECTION_ANALYSIS = "inspection_analysis"
    SAFETY_ALERT = "safety_alert"
    CUSTOMER_EXPLANATION = "customer_explanation"
    FOLLOW_UP = "follow_up"
    # Parts & Inventory Intelligence
    PARTS_AVAILABILITY = "parts_availability"
    INVENTORY_RISK = "inventory_risk"
    PURCHASE_RECOMMENDATION = "purchase_recommendation"
    REPAIR_READINESS = "repair_readiness"
    PART_COST = "part_cost"
    # Phase 19 — Knowledge Base / Shop Memory (AI proposes; Workflow applies)
    CUSTOMER_MEMORY = "customer_memory"
    VEHICLE_MEMORY = "vehicle_memory"
    SHOP_PREFERENCE = "shop_preference"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    # Phase 20 — Revenue Intelligence & Retention
    CUSTOMER_RETENTION = "customer_retention"
    REVENUE_OPPORTUNITY = "revenue_opportunity"
    SERVICE_RECOMMENDATION = "service_recommendation"
    CONTACT_TIMING = "contact_timing"
    CAMPAIGN_RECOMMENDATION = "campaign_recommendation"
    CUSTOMER_VALUE = "customer_value"
    # Phase 21 — AI Learning Loop (review-only; never auto-mutates rules)
    LEARNING_FEEDBACK = "learning_feedback"
    OPTIMIZATION = "optimization"
    PATTERN_DISCOVERY = "pattern_discovery"


@dataclass(slots=True)
class IntentDecision:
    """Classification of customer intent — decide only."""

    kind: DecisionKind = field(default=DecisionKind.INTENT, init=False)
    intent: str = "unknown"
    confidence: float = 0.0
    entities: dict[str, Any] = field(default_factory=dict)
    secondary_intents: list[str] = field(default_factory=list)
    is_emergency: bool = False
    is_complaint: bool = False
    rationale: str = ""


@dataclass(slots=True)
class AppointmentDecision:
    """Recommend book / reschedule / cancel — Workflow performs the mutation.

    Catalog fields (service_id, duration_minutes, …) are set by AI after
    matching the requested service; Workflow validates availability and books.
    """

    kind: DecisionKind = field(default=DecisionKind.APPOINTMENT, init=False)
    action: Literal["book", "reschedule", "cancel", "list_slots", "noop"] = "noop"
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    appointment_id: UUID | None = None
    preferred_start: datetime | None = None
    preferred_end: datetime | None = None
    recommended_slot_start: datetime | None = None
    recommended_slot_end: datetime | None = None
    # Service Catalog linkage (AI match → Decision; WF persists)
    requested_service: str | None = None
    service_id: UUID | None = None
    service_name: str | None = None
    duration_minutes: int | None = None
    required_skill: str | None = None
    required_bay: str | None = None
    reason: str | None = None
    days_ahead: int = 7
    confidence: float = 1.0
    rationale: str = ""
    # list_slots policy for counselor: offer openings, ask for a time, or
    # report that the requested clock time is taken.
    offer_policy: Literal["offer", "ask_time", "unavailable"] = "offer"
    # SMS/voice pending_action for confirmation / ask-time holds.
    # Explicit so Workflow does not infer reschedule from a leftover appointment_id.
    hold_action: Literal["book", "reschedule"] | None = None


@dataclass(slots=True)
class CustomerDecision:
    """Recommend create / merge customer — Workflow persists."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER, init=False)
    action: Literal["create", "merge", "update", "none"] = "none"
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    primary_id: UUID | None = None
    duplicate_ids: list[UUID] = field(default_factory=list)
    profile_patch: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class VehicleDecision:
    """Recommend create vehicle or update mileage — Workflow persists."""

    kind: DecisionKind = field(default=DecisionKind.VEHICLE, init=False)
    action: Literal["create", "update_mileage", "none"] = "none"
    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CrmUpdateDecision:
    """Recommend CRM timeline writes — Workflow persists."""

    kind: DecisionKind = field(default=DecisionKind.CRM, init=False)
    customer_id: UUID | None = None
    channel: str | None = None
    message: str | None = None
    intent: str | None = None
    vehicle_id: UUID | None = None
    repair_note: str | None = None
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class MarketingDecision:
    """Recommend outbound marketing content — Workflow dispatches."""

    kind: DecisionKind = field(default=DecisionKind.MARKETING, init=False)
    action_type: str = "thank_you"
    channel: str = "sms"
    customer_id: UUID | None = None
    template: str = ""
    body: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    scheduled_at: datetime | None = None
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class RevenueDecision:
    """Revenue opportunity scoring / prediction — decide only (+ optional marketing)."""

    kind: DecisionKind = field(default=DecisionKind.REVENUE, init=False)
    upsell_opportunities: list[dict[str, Any]] = field(default_factory=list)
    declined_estimates: list[dict[str, Any]] = field(default_factory=list)
    maintenance_reminders: list[dict[str, Any]] = field(default_factory=list)
    lost_customer_risk: float = 0.0
    predicted_revenue: Decimal = Decimal("0.00")
    notes: list[str] = field(default_factory=list)
    marketing_actions: list[MarketingDecision] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class PriorityDecision:
    """Priority scoring for work / escalation."""

    kind: DecisionKind = field(default=DecisionKind.PRIORITY, init=False)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    score: float = 0.0
    factors: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(slots=True)
class SummaryDecision:
    """Conversation / owner summary."""

    kind: DecisionKind = field(default=DecisionKind.SUMMARY, init=False)
    summary: str = ""
    highlights: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(slots=True)
class EscalationDecision:
    """Recommend human escalation — Workflow performs escalation."""

    kind: DecisionKind = field(default=DecisionKind.ESCALATION, init=False)
    escalate: bool = False
    reason: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    details: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(slots=True)
class MemoryDecision:
    """Recommend memory writes — Workflow persists facts."""

    kind: DecisionKind = field(default=DecisionKind.MEMORY, init=False)
    facts: list[dict[str, Any]] = field(default_factory=list)
    escalate: bool = False
    channel: str | None = None
    message_text: str | None = None
    rationale: str = ""


@dataclass(slots=True)
class RepairRecommendationDecision:
    """Recommend repair/service — Workflow records timeline only (not completed history)."""

    kind: DecisionKind = field(default=DecisionKind.REPAIR_RECOMMENDATION, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    service_type: str = "general"
    title: str = ""
    description: str = ""
    estimated_cost: Decimal = Decimal("0.00")
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    plain_language: str = ""
    advisor_notes: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class EstimateExplanationDecision:
    """Explain an estimate in plain language — Workflow communicates / timelines."""

    kind: DecisionKind = field(default=DecisionKind.ESTIMATE_EXPLANATION, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    estimate_id: UUID | None = None
    amount: Decimal = Decimal("0.00")
    line_items: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    plain_language: str = ""
    channel: str = "sms"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class ApprovalRequestDecision:
    """Request customer approval for estimate/repair — Workflow sends request."""

    kind: DecisionKind = field(default=DecisionKind.APPROVAL_REQUEST, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    estimate_id: UUID | None = None
    amount: Decimal = Decimal("0.00")
    services: list[str] = field(default_factory=list)
    message_body: str = ""
    channel: str = "sms"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class RepairStatusDecision:
    """Repair status update for customer — Workflow notifies / timelines."""

    kind: DecisionKind = field(default=DecisionKind.REPAIR_STATUS, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    status: Literal["received", "diagnosing", "awaiting_parts", "in_progress", "ready", "completed"] = (
        "in_progress"
    )
    message_body: str = ""
    channel: str = "sms"
    advisor_notes: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class MaintenanceReminderDecision:
    """Maintenance due reminder — Workflow schedules reminder / marketing."""

    kind: DecisionKind = field(default=DecisionKind.MAINTENANCE_REMINDER, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    service: str = "service"
    due_mileage: str | None = None
    due_date: datetime | None = None
    message_body: str = ""
    channel: str = "sms"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class ReviewRequestDecision:
    """Ask for customer review — Workflow dispatches review request."""

    kind: DecisionKind = field(default=DecisionKind.REVIEW_REQUEST, init=False)
    customer_id: UUID | None = None
    channel: str = "sms"
    message_body: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class RetentionDecision:
    """Customer retention plan — Workflow may update conversation / revenue / CRM."""

    kind: DecisionKind = field(default=DecisionKind.RETENTION, init=False)
    customer_id: UUID | None = None
    risk_score: float = 0.0
    plan: str = ""
    actions: list[str] = field(default_factory=list)
    suggested_offer: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CustomerCommunicationDecision:
    """Customer-facing reply plan — Workflow sends / records communication."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER_COMMUNICATION, init=False)
    customer_id: UUID | None = None
    conversation_id: UUID | None = None
    channel: str = "sms"
    body: str = ""
    intent: str | None = None
    tone: str = "helpful"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class InspectionAnalysisDecision:
    """Structured inspection analysis — Workflow may timeline / escalate."""

    kind: DecisionKind = field(default=DecisionKind.INSPECTION_ANALYSIS, init=False)
    inspection_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    condition_summary: str = ""
    finding_count: int = 0
    safety_count: int = 0
    recommended_count: int = 0
    optional_count: int = 0
    systems: list[str] = field(default_factory=list)
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    findings_snapshot: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class SafetyAlertDecision:
    """Safety finding alert — Workflow communicates / escalates (AI never sends)."""

    kind: DecisionKind = field(default=DecisionKind.SAFETY_ALERT, init=False)
    inspection_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    finding_id: UUID | None = None
    title: str = ""
    issue: str = ""
    severity: str = "safety"
    system: str = "general"
    urgent: bool = False
    plain_language: str = ""
    channel: str = "sms"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CustomerExplanationDecision:
    """Plain-language inspection explanation — Workflow communicates."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER_EXPLANATION, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    inspection_id: UUID | None = None
    template: str = "recommended_repair"
    category: str = "recommended"
    title: str = ""
    plain_language: str = ""
    channel: str = "sms"
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class FollowUpDecision:
    """Follow-up after inspection / estimate — Workflow schedules communication."""

    kind: DecisionKind = field(default=DecisionKind.FOLLOW_UP, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    inspection_id: UUID | None = None
    reason: str = "inspection_follow_up"
    message_body: str = ""
    channel: str = "sms"
    scheduled_at: datetime | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class PartsAvailabilityDecision:
    """Parts availability for a repair — Workflow may reserve / communicate."""

    kind: DecisionKind = field(default=DecisionKind.PARTS_AVAILABILITY, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    sku: str = ""
    part_name: str = ""
    quantity_needed: int = 1
    quantity_available: int = 0
    status: str = "out_of_stock"
    sufficient: bool = False
    reserve_recommended: bool = False
    lead_time_days: int = 0
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class InventoryRiskDecision:
    """Inventory delay / shortage risk — Workflow may escalate or reschedule."""

    kind: DecisionKind = field(default=DecisionKind.INVENTORY_RISK, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    risk_level: Literal["low", "medium", "high", "urgent"] = "medium"
    delay_days: int = 0
    missing_skus: list[str] = field(default_factory=list)
    message: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class PurchaseRecommendationDecision:
    """Recommend purchasing parts — Workflow may order (AI never purchases)."""

    kind: DecisionKind = field(default=DecisionKind.PURCHASE_RECOMMENDATION, init=False)
    shop_hint: str | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    sku: str = ""
    part_name: str = ""
    quantity: int = 1
    supplier_id: UUID | None = None
    supplier_name: str | None = None
    lead_time_days: int = 0
    estimated_cost: Decimal = Decimal("0.00")
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    reason: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class RepairReadinessDecision:
    """Whether repair can proceed given parts — Workflow may update schedule / notify."""

    kind: DecisionKind = field(default=DecisionKind.REPAIR_READINESS, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    ready: bool = False
    delay_days: int = 0
    blocking_parts: list[str] = field(default_factory=list)
    parts_cost_total: Decimal = Decimal("0.00")
    schedule_adjustment: Literal["proceed", "delay", "noop"] = "noop"
    customer_message: str = ""
    channel: str = "sms"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class PartCostDecision:
    """Parts cost estimate impact — Workflow may timeline / estimate."""

    kind: DecisionKind = field(default=DecisionKind.PART_COST, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    repair_id: UUID | None = None
    sku: str = ""
    part_name: str = ""
    quantity: int = 1
    unit_cost: Decimal = Decimal("0.00")
    line_cost: Decimal = Decimal("0.00")
    list_price_hint: Decimal | None = None
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CustomerMemoryDecision:
    """Propose customer memory / profile update — Workflow persists via Memory Plugin."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER_MEMORY, init=False)
    customer_id: UUID | None = None
    action: Literal["save", "update_profile", "noop"] = "save"
    content: str = ""
    category: str = "customer_preferences"
    patch: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.7
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class VehicleMemoryDecision:
    """Propose vehicle history / health update — Workflow persists via Memory Plugin."""

    kind: DecisionKind = field(default=DecisionKind.VEHICLE_MEMORY, init=False)
    vehicle_id: UUID | None = None
    customer_id: UUID | None = None
    action: Literal["save_history", "update_health", "noop"] = "update_health"
    content: str = ""
    health: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.75
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class ShopPreferenceDecision:
    """Propose shop preference / profile changes — Workflow persists via Memory Plugin."""

    kind: DecisionKind = field(default=DecisionKind.SHOP_PREFERENCE, init=False)
    preferences: dict[str, Any] = field(default_factory=dict)
    profile_patch: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class KnowledgeRetrievalDecision:
    """Request knowledge retrieval for advisor context — read-only (no memory write)."""

    kind: DecisionKind = field(default=DecisionKind.KNOWLEDGE_RETRIEVAL, init=False)
    query: str = ""
    limit: int = 12
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CustomerRetentionDecision:
    """Retention plan proposal — Workflow records; AI never contacts customer."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER_RETENTION, init=False)
    customer_id: UUID | None = None
    risk_score: float = 0.0
    plan: str = ""
    actions: list[str] = field(default_factory=list)
    suggested_offer: str | None = None
    lifetime_value: float = 0.0
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class RevenueOpportunityDecision:
    """Detected revenue opportunity — Workflow timelines / dashboard; no auto-pricing."""

    kind: DecisionKind = field(default=DecisionKind.REVENUE_OPPORTUNITY, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    opportunity_kind: str = "general"
    title: str = ""
    expected_revenue: float = 0.0
    probability: float = 0.5
    opportunity_score: float = 0.0
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class ServiceRecommendationDecision:
    """Recommended service — Workflow may timeline; AI never books or prices."""

    kind: DecisionKind = field(default=DecisionKind.SERVICE_RECOMMENDATION, init=False)
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    service: str = ""
    reason: str = ""
    expected_revenue: float = 0.0
    urgency: Literal["low", "normal", "high", "urgent"] = "normal"
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class ContactTimingDecision:
    """Best contact window suggestion — AI never sends messages."""

    kind: DecisionKind = field(default=DecisionKind.CONTACT_TIMING, init=False)
    customer_id: UUID | None = None
    channel: str = "sms"
    preferred_window: str = "weekday_morning"
    reason: str = ""
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CampaignRecommendationDecision:
    """Campaign suggestion — auto_send must stay False; Workflow stores suggestion only."""

    kind: DecisionKind = field(default=DecisionKind.CAMPAIGN_RECOMMENDATION, init=False)
    customer_id: UUID | None = None
    campaign_type: str = "retention"
    channel: str = "sms"
    message_draft: str = ""
    audience_size: int = 1
    auto_send: bool = False
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class CustomerValueDecision:
    """Customer value / CLV insight — read/record only."""

    kind: DecisionKind = field(default=DecisionKind.CUSTOMER_VALUE, init=False)
    customer_id: UUID | None = None
    lifetime_value: float = 0.0
    health_score: float | None = None
    churn_risk: float | None = None
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class LearningFeedbackDecision:
    """Learning insight / feedback for staff review — never auto-applies rule changes."""

    kind: DecisionKind = field(default=DecisionKind.LEARNING_FEEDBACK, init=False)
    source: str = "system"  # customer | staff | workflow | system
    summary: str = ""
    rating: float | None = None
    insights: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    requires_review: bool = True
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class OptimizationDecision:
    """Recommend improvement to recommendations/prompts — never mutates workflows/prices."""

    kind: DecisionKind = field(default=DecisionKind.OPTIMIZATION, init=False)
    target: str = "recommendations"
    suggestions: list[str] = field(default_factory=list)
    expected_impact: str = ""
    requires_review: bool = True
    auto_apply: bool = False  # always treated as False by executor
    confidence: float = 1.0
    rationale: str = ""


@dataclass(slots=True)
class PatternDiscoveryDecision:
    """Discovered success pattern — recorded for review; AI cannot change business rules."""

    kind: DecisionKind = field(default=DecisionKind.PATTERN_DISCOVERY, init=False)
    pattern_key: str = ""
    description: str = ""
    support_count: int = 0
    success_rate: float = 0.0
    confidence: float = 0.0
    rationale: str = ""


Decision = (
    IntentDecision
    | AppointmentDecision
    | CustomerDecision
    | VehicleDecision
    | CrmUpdateDecision
    | MarketingDecision
    | RevenueDecision
    | PriorityDecision
    | SummaryDecision
    | EscalationDecision
    | MemoryDecision
    | RepairRecommendationDecision
    | EstimateExplanationDecision
    | ApprovalRequestDecision
    | RepairStatusDecision
    | MaintenanceReminderDecision
    | ReviewRequestDecision
    | RetentionDecision
    | CustomerCommunicationDecision
    | InspectionAnalysisDecision
    | SafetyAlertDecision
    | CustomerExplanationDecision
    | FollowUpDecision
    | PartsAvailabilityDecision
    | InventoryRiskDecision
    | PurchaseRecommendationDecision
    | RepairReadinessDecision
    | PartCostDecision
    | CustomerMemoryDecision
    | VehicleMemoryDecision
    | ShopPreferenceDecision
    | KnowledgeRetrievalDecision
    | CustomerRetentionDecision
    | RevenueOpportunityDecision
    | ServiceRecommendationDecision
    | ContactTimingDecision
    | CampaignRecommendationDecision
    | CustomerValueDecision
    | LearningFeedbackDecision
    | OptimizationDecision
    | PatternDiscoveryDecision
)
