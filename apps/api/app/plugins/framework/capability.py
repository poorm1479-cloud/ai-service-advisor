"""Capability Registry — map capabilities to plugins (with aliases + duplicate checks)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Awaitable, Callable

from app.plugins.framework.context import PluginContext
from app.plugins.framework.plugin import IPlugin


class Capability(StrEnum):
    """Named capabilities Workflow may request from plugins."""

    FIND_CUSTOMER = "FindCustomer"
    CREATE_CUSTOMER = "CreateCustomer"
    UPDATE_CUSTOMER = "UpdateCustomer"
    MERGE_CUSTOMER = "MergeCustomer"
    SEARCH_CUSTOMER = "SearchCustomer"
    CUSTOMER_SUMMARY = "CustomerSummary"

    FIND_VEHICLE = "FindVehicle"
    CREATE_VEHICLE = "CreateVehicle"
    UPDATE_VEHICLE = "UpdateVehicle"
    SEARCH_VEHICLE = "SearchVehicle"

    REPAIR_HISTORY = "RepairHistory"
    ADD_REPAIR = "AddRepair"

    COMMUNICATION_HISTORY = "CommunicationHistory"
    ADD_COMMUNICATION = "AddCommunication"
    CUSTOMER_TIMELINE = "CustomerTimeline"
    ADD_TIMELINE = "AddTimeline"

    # Scheduling Plugin
    FIND_AVAILABLE_SLOT = "FindAvailableSlot"
    BOOK_APPOINTMENT = "BookAppointment"
    RESCHEDULE_APPOINTMENT = "RescheduleAppointment"
    CANCEL_APPOINTMENT = "CancelAppointment"
    ASSIGN_MECHANIC = "AssignMechanic"
    ASSIGN_BAY = "AssignBay"
    ESTIMATE_DURATION = "EstimateDuration"
    WALK_IN_CHECK_IN = "WalkInCheckIn"
    CHECK_AVAILABILITY = "CheckAvailability"
    APPOINTMENT_HISTORY = "AppointmentHistory"
    VALIDATE_APPOINTMENT = "ValidateAppointment"
    DETECT_CONFLICT = "DetectConflict"

    # Conversation Plugin
    CREATE_CONVERSATION = "CreateConversation"
    FIND_CONVERSATION = "FindConversation"
    UPDATE_CONVERSATION = "UpdateConversation"
    CLOSE_CONVERSATION = "CloseConversation"
    MERGE_CONVERSATION = "MergeConversation"
    SEARCH_CONVERSATION = "SearchConversation"
    CONVERSATION_HISTORY = "ConversationHistory"
    CONVERSATION_SUMMARY = "ConversationSummary"

    # Revenue Intelligence Plugin
    DETECT_REVENUE_OPPORTUNITY = "DetectRevenueOpportunity"
    PREDICT_MAINTENANCE = "PredictMaintenance"
    PREDICT_CUSTOMER_RETURN = "PredictCustomerReturn"
    FIND_DECLINED_ESTIMATES = "FindDeclinedEstimates"
    GENERATE_UPSELL_RECOMMENDATIONS = "GenerateUpsellRecommendations"
    GENERATE_CROSS_SELL_RECOMMENDATIONS = "GenerateCrossSellRecommendations"
    CALCULATE_VEHICLE_HEALTH = "CalculateVehicleHealth"
    CALCULATE_CUSTOMER_HEALTH = "CalculateCustomerHealth"
    CALCULATE_CUSTOMER_LIFETIME_VALUE = "CalculateCustomerLifetimeValue"
    PREDICT_SHOP_CAPACITY = "PredictShopCapacity"
    OPTIMIZE_TECHNICIAN_UTILIZATION = "OptimizeTechnicianUtilization"

    # AI Service Advisor Plugin (decide-only)
    ANALYZE_CONVERSATION = "AnalyzeConversation"
    ANALYZE_CUSTOMER = "AnalyzeCustomer"
    ANALYZE_VEHICLE = "AnalyzeVehicle"
    GENERATE_REPAIR_RECOMMENDATION = "GenerateRepairRecommendation"
    GENERATE_ESTIMATE_SUMMARY = "GenerateEstimateSummary"
    GENERATE_CUSTOMER_EXPLANATION = "GenerateCustomerExplanation"
    GENERATE_APPROVAL_REQUEST = "GenerateApprovalRequest"
    GENERATE_REPAIR_UPDATE = "GenerateRepairUpdate"
    GENERATE_FOLLOW_UP = "GenerateFollowUp"
    GENERATE_MAINTENANCE_REMINDER = "GenerateMaintenanceReminder"
    GENERATE_REVIEW_REQUEST = "GenerateReviewRequest"
    GENERATE_RETENTION_PLAN = "GenerateRetentionPlan"

    # Inspection Intelligence Plugin (decide-only)
    ANALYZE_INSPECTION = "AnalyzeInspection"
    DETECT_SAFETY_ISSUE = "DetectSafetyIssue"
    GENERATE_ESTIMATE_SUGGESTION = "GenerateEstimateSuggestion"
    CREATE_APPROVAL_REQUEST = "CreateApprovalRequest"
    PRIORITIZE_REPAIR = "PrioritizeRepair"
    CREATE_FOLLOW_UP = "CreateFollowUp"
    # Inspection-scoped equivalents (Advisor keeps GenerateRepairRecommendation /
    # GenerateCustomerExplanation for backward compatibility)
    GENERATE_INSPECTION_REPAIR_RECOMMENDATION = "GenerateInspectionRepairRecommendation"
    GENERATE_INSPECTION_CUSTOMER_EXPLANATION = "GenerateInspectionCustomerExplanation"

    # Parts & Inventory Intelligence Plugin
    FIND_PART = "FindPart"
    CHECK_INVENTORY = "CheckInventory"
    PREDICT_REQUIRED_PARTS = "PredictRequiredParts"
    RESERVE_PART = "ReservePart"
    RELEASE_PART = "ReleasePart"
    FIND_SUPPLIER = "FindSupplier"
    CREATE_PURCHASE_RECOMMENDATION = "CreatePurchaseRecommendation"
    ESTIMATE_PART_COST = "EstimatePartCost"
    CHECK_REPAIR_READINESS = "CheckRepairReadiness"

    # Production Voice AI Plugin (communication adapter only)
    RECEIVE_CALL = "ReceiveCall"
    CREATE_VOICE_SESSION = "CreateVoiceSession"
    SPEECH_TO_TEXT = "SpeechToText"
    TEXT_TO_SPEECH = "TextToSpeech"
    TRANSFER_TO_HUMAN = "TransferToHuman"
    END_CALL = "EndCall"
    RECORD_CONVERSATION = "RecordConversation"

    # Owner Dashboard & AI Operations Center (read-only)
    GET_DAILY_SUMMARY = "GetDailySummary"
    GET_AI_ACTIVITY = "GetAIActivity"
    GET_PENDING_ACTIONS = "GetPendingActions"
    GET_REVENUE_OPPORTUNITIES = "GetRevenueOpportunities"
    GET_CUSTOMER_RISK = "GetCustomerRisk"
    GET_APPOINTMENT_OVERVIEW = "GetAppointmentOverview"
    GET_WORKFLOW_STATUS = "GetWorkflowStatus"
    GET_PERFORMANCE_METRICS = "GetPerformanceMetrics"

    # External Integration Layer (adapters only — does not replace CRM)
    IMPORT_CUSTOMER_DATA = "ImportCustomerData"
    IMPORT_VEHICLE_DATA = "ImportVehicleData"
    IMPORT_REPAIR_HISTORY = "ImportRepairHistory"
    SYNC_APPOINTMENT = "SyncAppointment"
    SYNC_INVOICE = "SyncInvoice"
    SYNC_PAYMENT = "SyncPayment"
    SEND_CUSTOMER_MESSAGE = "SendCustomerMessage"
    RECEIVE_CUSTOMER_MESSAGE = "ReceiveCustomerMessage"

    # AI Knowledge Base & Shop Memory (Phase 19)
    # Writes are Workflow-only via Decision Objects; AI may read.
    SAVE_MEMORY = "SaveMemory"
    SEARCH_MEMORY = "SearchMemory"
    GET_CUSTOMER_HISTORY = "GetCustomerHistory"
    GET_VEHICLE_HISTORY = "GetVehicleHistory"
    GET_SHOP_PREFERENCE = "GetShopPreference"
    RETRIEVE_KNOWLEDGE = "RetrieveKnowledge"
    UPDATE_CUSTOMER_PROFILE = "UpdateCustomerProfile"
    UPDATE_VEHICLE_HEALTH = "UpdateVehicleHealth"

    # Phase 20 — Revenue Intelligence & Customer Retention
    ANALYZE_CUSTOMER_VALUE = "AnalyzeCustomerValue"
    PREDICT_CUSTOMER_RISK = "PredictCustomerRisk"
    RECOMMEND_SERVICE = "RecommendService"
    RECOMMEND_CONTACT_TIMING = "RecommendContactTiming"
    CREATE_RETENTION_PLAN = "CreateRetentionPlan"
    ANALYZE_LOST_REVENUE = "AnalyzeLostRevenue"
    GENERATE_CAMPAIGN_SUGGESTION = "GenerateCampaignSuggestion"

    # Phase 21 — AI Learning Loop (analyze/propose only; never mutates rules)
    COLLECT_DECISION_RESULT = "CollectDecisionResult"
    EVALUATE_DECISION = "EvaluateDecision"
    LEARN_CUSTOMER_RESPONSE = "LearnCustomerResponse"
    ANALYZE_SUCCESS_PATTERN = "AnalyzeSuccessPattern"
    OPTIMIZE_RECOMMENDATION = "OptimizeRecommendation"
    GENERATE_LEARNING_INSIGHT = "GenerateLearningInsight"


CapabilityHandler = Callable[..., Awaitable[Any]]


@dataclass
class CapabilityBinding:
    capability: str
    plugin_id: str
    plugin_version: str
    handler: CapabilityHandler
    description: str = ""


class CapabilityRegistry:
    """Resolves capability name → plugin handler.

    Supports aliases and rejects duplicate registrations for the same
    (capability, plugin_id, version) unless replace=True.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, CapabilityBinding] = {}
        self._aliases: dict[str, str] = {}
        self._plugins: dict[str, IPlugin] = {}

    def register_alias(self, alias: str, capability: str | Capability) -> None:
        target = capability.value if isinstance(capability, Capability) else str(capability)
        existing = self._aliases.get(alias)
        if existing and existing != target:
            raise ValueError(f"Alias {alias!r} already maps to {existing!r}")
        self._aliases[alias] = target

    def canonicalize(self, capability: str | Capability) -> str:
        key = capability.value if isinstance(capability, Capability) else str(capability)
        return self._aliases.get(key, key)

    def register_plugin(
        self,
        plugin: IPlugin,
        *,
        replace: bool = False,
        aliases: dict[str, str] | None = None,
    ) -> None:
        plugin_id = plugin.plugin_id()
        version = plugin.plugin_version()
        self._plugins[f"{plugin_id}@{version}"] = plugin
        self._plugins[plugin_id] = plugin  # latest pointer

        caps_fn = getattr(plugin, "supported_capabilities", None) or getattr(
            plugin, "capabilities", None
        )
        cap_names: list[str] = list(caps_fn()) if callable(caps_fn) else []

        for name in cap_names:
            self.register(
                name,
                plugin_id=plugin_id,
                plugin_version=version,
                handler=_make_invoke_handler(plugin, name),
                description=f"{plugin_id}@{version}:{name}",
                replace=replace,
            )

        for alias, target in (aliases or {}).items():
            self.register_alias(alias, target)

    def register(
        self,
        capability: str | Capability,
        *,
        plugin_id: str,
        handler: CapabilityHandler,
        plugin_version: str = "1.0.0",
        description: str = "",
        replace: bool = False,
    ) -> None:
        key = self.canonicalize(capability)
        existing = self._bindings.get(key)
        if existing is not None and not replace:
            if (
                existing.plugin_id == plugin_id
                and existing.plugin_version == plugin_version
            ):
                # Idempotent re-register of same binding
                self._bindings[key] = CapabilityBinding(
                    capability=key,
                    plugin_id=plugin_id,
                    plugin_version=plugin_version,
                    handler=handler,
                    description=description,
                )
                return
            raise ValueError(
                f"Duplicate capability registration: {key} "
                f"(owned by {existing.plugin_id}@{existing.plugin_version}, "
                f"attempted by {plugin_id}@{plugin_version})"
            )
        self._bindings[key] = CapabilityBinding(
            capability=key,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            handler=handler,
            description=description,
        )

    def resolve(self, capability: str | Capability) -> CapabilityBinding:
        key = self.canonicalize(capability)
        binding = self._bindings.get(key)
        if binding is None:
            raise LookupError(f"No plugin registered for capability: {key}")
        return binding

    def resolve_plugin(self, capability: str | Capability) -> IPlugin:
        binding = self.resolve(capability)
        plugin = self._plugins.get(binding.plugin_id)
        if plugin is None:
            raise LookupError(f"Plugin not loaded for capability: {binding.capability}")
        return plugin

    def get_plugin(self, plugin_id: str, version: str | None = None) -> IPlugin:
        key = f"{plugin_id}@{version}" if version else plugin_id
        plugin = self._plugins.get(key)
        if plugin is None:
            raise LookupError(f"Plugin not registered: {key}")
        return plugin

    async def invoke(
        self,
        capability: str | Capability,
        *,
        context: PluginContext | None = None,
        **kwargs: Any,
    ) -> Any:
        binding = self.resolve(capability)
        if context is not None:
            merged = {**context.to_kwargs(), **kwargs}
            return await binding.handler(context=context, **merged)
        return await binding.handler(**kwargs)

    def list_capabilities(self) -> list[dict[str, str]]:
        return [
            {
                "capability": b.capability,
                "plugin_id": b.plugin_id,
                "plugin_version": b.plugin_version,
                "description": b.description,
            }
            for b in sorted(self._bindings.values(), key=lambda x: x.capability)
        ]

    def list_aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def clear(self) -> None:
        self._bindings.clear()
        self._aliases.clear()
        self._plugins.clear()

    def unbind_plugin(self, plugin_id: str) -> None:
        """Remove capability bindings for a plugin (all versions)."""
        self._bindings = {
            k: v for k, v in self._bindings.items() if v.plugin_id != plugin_id
        }
        to_del = [k for k in self._plugins if k == plugin_id or k.startswith(f"{plugin_id}@")]
        for k in to_del:
            del self._plugins[k]


def _make_invoke_handler(plugin: IPlugin, capability: str) -> CapabilityHandler:
    async def _handler(context: PluginContext | None = None, **kwargs: Any) -> Any:
        # Strip internal context key if present
        kwargs.pop("_plugin_context", None)
        return await plugin.invoke(capability, context=context, **kwargs)

    return _handler


_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


def reset_capability_registry() -> None:
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
