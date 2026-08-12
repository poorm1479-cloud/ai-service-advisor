"""Plugin Framework factory — runtime wiring for Workflow Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.plugins.framework.capability import (
    CapabilityRegistry,
    get_capability_registry,
    reset_capability_registry,
)
from app.plugins.framework.context import PluginContext
from app.plugins.framework.lifecycle import LifecycleState
from app.plugins.framework.loader import PluginLoader
from app.plugins.framework.metadata import PluginMetadata
from app.plugins.framework.registry import (
    PluginRegistry,
    get_plugin_registry,
    reset_plugin_registry,
)


@dataclass
class PluginRuntime:
    plugins: PluginRegistry
    capabilities: CapabilityRegistry
    loader: PluginLoader


_runtime: PluginRuntime | None = None
_defaults_loaded = False


def get_plugin_runtime() -> PluginRuntime:
    global _runtime
    if _runtime is None:
        plugins = get_plugin_registry()
        capabilities = get_capability_registry()
        _runtime = PluginRuntime(
            plugins=plugins,
            capabilities=capabilities,
            loader=PluginLoader(plugins),
        )
    return _runtime


def reset_plugin_runtime() -> None:
    global _runtime, _defaults_loaded
    reset_plugin_registry()
    reset_capability_registry()
    _runtime = None
    _defaults_loaded = False
    try:
        from app.dashboard.factory import reset_dashboard_plugin
        from app.integrations.factory import reset_integration_plugin, reset_integration_runtime
        from app.plugins.advisor.factory import reset_advisor_plugin
        from app.plugins.conversation.factory import reset_conversation_plugin
        from app.plugins.crm.factory import reset_crm_plugin
        from app.plugins.inspection.factory import reset_inspection_plugin
        from app.plugins.inventory.factory import reset_inventory_plugin
        from app.learning.factory import reset_learning_runtime
        from app.plugins.learning.factory import reset_learning_plugin
        from app.plugins.memory.factory import reset_memory_plugin
        from app.plugins.revenue.factory import reset_revenue_plugin
        from app.plugins.scheduling.factory import reset_scheduling_plugin
        from app.plugins.voice.factory import reset_voice_plugin

        reset_crm_plugin()
        reset_scheduling_plugin()
        reset_conversation_plugin()
        reset_revenue_plugin()
        reset_advisor_plugin()
        reset_inspection_plugin()
        reset_inventory_plugin()
        reset_voice_plugin()
        reset_dashboard_plugin()
        reset_integration_plugin()
        reset_integration_runtime()
        reset_memory_plugin()
        reset_learning_plugin()
        reset_learning_runtime()
    except Exception:  # noqa: BLE001
        pass


def _enable_sync(plugin: Any, plugin_id: str) -> None:
    import asyncio

    runtime = get_plugin_runtime()
    life = runtime.plugins.get_lifecycle(plugin_id)

    try:
        asyncio.get_running_loop()
        life.state = LifecycleState.ENABLED
        if hasattr(plugin, "_initialized"):
            plugin._initialized = True
        return
    except RuntimeError:
        pass

    async def _boot() -> None:
        await life.initialize()
        await life.enable()

    asyncio.run(_boot())


def _register_plugin(plugin: Any, *, aliases: dict[str, str] | None = None) -> None:
    runtime = get_plugin_runtime()
    meta = PluginMetadata(
        plugin_id=plugin.plugin_id(),
        name=plugin.plugin_name(),
        version=plugin.plugin_version(),
        description=plugin.plugin_description(),
        capabilities=list(plugin.supported_capabilities()),
        aliases=aliases or {},
    )
    runtime.plugins.register(plugin, metadata=meta, replace_capabilities=True)
    _enable_sync(plugin, plugin.plugin_id())


def ensure_default_plugins() -> PluginRuntime:
    """Install reference plugins including AI Service Advisor — idempotent."""
    global _defaults_loaded
    runtime = get_plugin_runtime()
    if _defaults_loaded:
        try:
            runtime.plugins.lookup("crm")
            runtime.plugins.lookup("scheduling")
            runtime.plugins.lookup("conversation")
            runtime.plugins.lookup("revenue")
            runtime.plugins.lookup("advisor")
            runtime.plugins.lookup("inspection")
            runtime.plugins.lookup("inventory")
            runtime.plugins.lookup("voice")
            runtime.plugins.lookup("dashboard")
            runtime.plugins.lookup("integrations")
            runtime.plugins.lookup("memory")
            runtime.plugins.lookup("learning")
            return runtime
        except LookupError:
            _defaults_loaded = False

    from app.dashboard.factory import build_dashboard_plugin
    from app.integrations.factory import build_integration_plugin
    from app.plugins.advisor.factory import build_advisor_plugin
    from app.plugins.conversation.factory import build_conversation_plugin
    from app.plugins.crm.factory import build_crm_plugin
    from app.plugins.inspection.factory import build_inspection_plugin
    from app.plugins.inventory.factory import build_inventory_plugin
    from app.plugins.learning.factory import build_learning_plugin
    from app.plugins.memory.factory import build_memory_plugin
    from app.plugins.revenue.factory import build_revenue_plugin
    from app.plugins.scheduling.factory import build_scheduling_plugin
    from app.plugins.voice.factory import build_voice_plugin

    crm = build_crm_plugin(register=False)
    _register_plugin(
        crm,
        aliases={
            "crm.find_customer": "FindCustomer",
            "crm.create_customer": "CreateCustomer",
            "crm.timeline": "CustomerTimeline",
        },
    )

    scheduling = build_scheduling_plugin(register=False)
    _register_plugin(
        scheduling,
        aliases={
            "scheduling.find_slot": "FindAvailableSlot",
            "scheduling.book": "BookAppointment",
            "scheduling.cancel": "CancelAppointment",
            "scheduling.reschedule": "RescheduleAppointment",
        },
    )

    conversation = build_conversation_plugin(register=False)
    _register_plugin(
        conversation,
        aliases={
            "conversation.create": "CreateConversation",
            "conversation.find": "FindConversation",
            "conversation.update": "UpdateConversation",
            "conversation.close": "CloseConversation",
            "conversation.summary": "ConversationSummary",
        },
    )

    revenue = build_revenue_plugin(register=False)
    _register_plugin(
        revenue,
        aliases={
            "revenue.detect": "DetectRevenueOpportunity",
            "revenue.maintenance": "PredictMaintenance",
            "revenue.upsell": "GenerateUpsellRecommendations",
            "revenue.clv": "CalculateCustomerLifetimeValue",
            "revenue.customer_value": "AnalyzeCustomerValue",
            "revenue.risk": "PredictCustomerRisk",
            "revenue.recommend_service": "RecommendService",
            "revenue.contact_timing": "RecommendContactTiming",
            "revenue.retention_plan": "CreateRetentionPlan",
            "revenue.lost": "AnalyzeLostRevenue",
            "revenue.campaign": "GenerateCampaignSuggestion",
        },
    )

    advisor = build_advisor_plugin(register=False)
    _register_plugin(
        advisor,
        aliases={
            "advisor.analyze": "AnalyzeConversation",
            "advisor.repair": "GenerateRepairRecommendation",
            "advisor.estimate": "GenerateEstimateSummary",
            "advisor.followup": "GenerateFollowUp",
        },
    )

    inspection = build_inspection_plugin(register=False)
    _register_plugin(
        inspection,
        aliases={
            "inspection.analyze": "AnalyzeInspection",
            "inspection.safety": "DetectSafetyIssue",
            "inspection.repair": "GenerateInspectionRepairRecommendation",
            "inspection.explain": "GenerateInspectionCustomerExplanation",
            "inspection.estimate": "GenerateEstimateSuggestion",
            "inspection.approval": "CreateApprovalRequest",
            "inspection.prioritize": "PrioritizeRepair",
            "inspection.followup": "CreateFollowUp",
        },
    )

    inventory = build_inventory_plugin(register=False)
    _register_plugin(
        inventory,
        aliases={
            "inventory.find": "FindPart",
            "inventory.check": "CheckInventory",
            "inventory.predict": "PredictRequiredParts",
            "inventory.reserve": "ReservePart",
            "inventory.release": "ReleasePart",
            "inventory.supplier": "FindSupplier",
            "inventory.purchase": "CreatePurchaseRecommendation",
            "inventory.cost": "EstimatePartCost",
            "inventory.readiness": "CheckRepairReadiness",
        },
    )

    voice = build_voice_plugin(register=False)
    _register_plugin(
        voice,
        aliases={
            "voice.receive": "ReceiveCall",
            "voice.session": "CreateVoiceSession",
            "voice.stt": "SpeechToText",
            "voice.tts": "TextToSpeech",
            "voice.transfer": "TransferToHuman",
            "voice.end": "EndCall",
            "voice.record": "RecordConversation",
        },
    )

    dashboard = build_dashboard_plugin(register=False)
    _register_plugin(
        dashboard,
        aliases={
            "dashboard.summary": "GetDailySummary",
            "dashboard.activity": "GetAIActivity",
            "dashboard.pending": "GetPendingActions",
            "dashboard.revenue": "GetRevenueOpportunities",
            "dashboard.risk": "GetCustomerRisk",
            "dashboard.appointments": "GetAppointmentOverview",
            "dashboard.workflows": "GetWorkflowStatus",
            "dashboard.performance": "GetPerformanceMetrics",
        },
    )

    integrations = build_integration_plugin(register=False)
    _register_plugin(
        integrations,
        aliases={
            "integrations.import_customer": "ImportCustomerData",
            "integrations.import_vehicle": "ImportVehicleData",
            "integrations.import_repair": "ImportRepairHistory",
            "integrations.sync_appointment": "SyncAppointment",
            "integrations.sync_invoice": "SyncInvoice",
            "integrations.sync_payment": "SyncPayment",
            "integrations.send_message": "SendCustomerMessage",
            "integrations.receive_message": "ReceiveCustomerMessage",
        },
    )

    memory = build_memory_plugin(register=False)
    _register_plugin(
        memory,
        aliases={
            "memory.save": "SaveMemory",
            "memory.search": "SearchMemory",
            "memory.customer_history": "GetCustomerHistory",
            "memory.vehicle_history": "GetVehicleHistory",
            "memory.shop_preference": "GetShopPreference",
            "memory.knowledge": "RetrieveKnowledge",
            "memory.update_customer": "UpdateCustomerProfile",
            "memory.update_vehicle_health": "UpdateVehicleHealth",
        },
    )

    learning = build_learning_plugin(register=False)
    _register_plugin(
        learning,
        aliases={
            "learning.collect": "CollectDecisionResult",
            "learning.evaluate": "EvaluateDecision",
            "learning.customer_response": "LearnCustomerResponse",
            "learning.patterns": "AnalyzeSuccessPattern",
            "learning.optimize": "OptimizeRecommendation",
            "learning.insight": "GenerateLearningInsight",
        },
    )

    _defaults_loaded = True
    return runtime


def _bind_scoped(plugin: Any, *, fallback_id: str, fallback_name: str) -> None:
    runtime = get_plugin_runtime()
    meta = PluginMetadata(
        plugin_id=plugin.plugin_id()
        if callable(getattr(plugin, "plugin_id", None))
        else getattr(plugin, "plugin_id", fallback_id),
        name=plugin.plugin_name()
        if callable(getattr(plugin, "plugin_name", None))
        else fallback_name,
        version=plugin.plugin_version()
        if callable(getattr(plugin, "plugin_version", None))
        else "1.0.0",
        description=plugin.plugin_description()
        if callable(getattr(plugin, "plugin_description", None))
        else "",
        capabilities=list(
            plugin.supported_capabilities()
            if callable(getattr(plugin, "supported_capabilities", None))
            else plugin.capabilities()
        ),
    )
    runtime.plugins.register(plugin, metadata=meta, replace_capabilities=True)


def ensure_workflow_plugins(ports: Any | None = None) -> PluginRuntime:
    """Bind scoped plugins from DecisionPorts, else load defaults.

    Workflow must only use Plugin/Capability registries — never import CRM/Scheduling
    modules directly.
    """
    runtime = ensure_default_plugins()
    if ports is None:
        return runtime

    crm = getattr(ports, "crm_plugin", None)
    if crm is not None:
        _bind_scoped(crm, fallback_id="crm", fallback_name="CRM Plugin")

    scheduling = getattr(ports, "scheduling_plugin", None)
    if scheduling is None and getattr(ports, "scheduling_store", None) is not None:
        from app.plugins.scheduling.factory import scheduling_plugin_from_ports

        scheduling = scheduling_plugin_from_ports(
            scheduling_store=ports.scheduling_store
        )
        ports.scheduling_plugin = scheduling  # type: ignore[attr-defined]
    if scheduling is not None:
        _bind_scoped(scheduling, fallback_id="scheduling", fallback_name="Scheduling Plugin")

    conversation = getattr(ports, "conversation_plugin", None)
    if conversation is not None:
        _bind_scoped(
            conversation, fallback_id="conversation", fallback_name="Conversation Plugin"
        )

    revenue = getattr(ports, "revenue_plugin", None)
    if revenue is not None:
        _bind_scoped(revenue, fallback_id="revenue", fallback_name="Revenue Intelligence Plugin")

    advisor = getattr(ports, "advisor_plugin", None)
    if advisor is not None:
        _bind_scoped(advisor, fallback_id="advisor", fallback_name="RatchetHub")

    inspection = getattr(ports, "inspection_plugin", None)
    if inspection is not None:
        _bind_scoped(
            inspection, fallback_id="inspection", fallback_name="Inspection Intelligence"
        )

    inventory = getattr(ports, "inventory_plugin", None)
    if inventory is not None:
        _bind_scoped(
            inventory,
            fallback_id="inventory",
            fallback_name="Parts & Inventory Intelligence",
        )

    voice = getattr(ports, "voice_plugin", None)
    if voice is not None:
        _bind_scoped(voice, fallback_id="voice", fallback_name="Production Voice AI")

    return runtime


async def invoke_capability(
    capability: str,
    *,
    context: PluginContext | None = None,
    ports: Any | None = None,
    **kwargs: Any,
) -> Any:
    """Workflow-facing helper: ensure plugins, then invoke via Capability Registry."""
    ensure_workflow_plugins(ports)
    return await get_capability_registry().invoke(capability, context=context, **kwargs)
