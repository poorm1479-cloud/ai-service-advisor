"""Long-term memory enums."""

from __future__ import annotations

from enum import StrEnum


class MemoryType(StrEnum):
    SEMANTIC = "semantic"
    CONVERSATION = "conversation"
    CUSTOMER = "customer"
    BUSINESS = "business"
    SHOP = "shop"
    VEHICLE = "vehicle"
    KNOWLEDGE = "knowledge"


class MemoryCategory(StrEnum):
    CUSTOMER_PREFERENCES = "customer_preferences"
    COMMUNICATION_STYLE = "communication_style"
    VEHICLE_HISTORY = "vehicle_history"
    PREVIOUS_CONVERSATIONS = "previous_conversations"
    REPAIR_DECISIONS = "repair_decisions"
    DECLINED_ESTIMATES = "declined_estimates"
    APPOINTMENT_BEHAVIOR = "appointment_behavior"
    GENERAL = "general"
    # Phase 19 — Knowledge Base / Shop Memory
    SHOP_PROFILE = "shop_profile"
    SHOP_PREFERENCES = "shop_preferences"
    CUSTOMER_HISTORY = "customer_history"
    VEHICLE_HEALTH = "vehicle_health"
    BUSINESS_KNOWLEDGE = "business_knowledge"


class MemorySource(StrEnum):
    AGENT_PIPELINE = "agent_pipeline"
    SMS = "sms"
    VOICE = "voice"
    MANUAL = "manual"
    IMPORT = "import"
    SYSTEM = "system"
    WORKFLOW = "workflow"
    KNOWLEDGE_BASE = "knowledge_base"