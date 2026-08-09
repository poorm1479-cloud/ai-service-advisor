"""DI factory for SMS AI runtime."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.agents.factory import AgentRuntime, build_agent_runtime
from app.infrastructure.config import settings
from app.sms.memory import ConversationMemoryPort, InMemoryConversationMemory
from app.sms.monitoring import SmsMonitor
from app.sms.queue import InMemoryMessageQueue, MessageQueuePort, RedisMessageQueue
from app.sms.reply import ContextualReplyGenerator
from app.sms.service import SmsAiService
from app.sms.store import InMemorySmsStore, SmsStorePort
from app.sms.twilio.provider import (
    FakeSmsProvider,
    SmsProviderPort,
    TwilioSettings,
    TwilioSmsProvider,
)


@dataclass(slots=True)
class SmsRuntime:
    service: SmsAiService
    agents: AgentRuntime
    store: SmsStorePort
    memory: ConversationMemoryPort
    provider: SmsProviderPort
    queue: MessageQueuePort
    monitor: SmsMonitor


def _parse_shop_map(raw: str) -> dict[str, UUID]:
    """Format: +15551111:uuid,+15552222:uuid"""
    mapping: dict[str, UUID] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        phone, shop = part.split(":", 1)
        mapping[phone.strip()] = UUID(shop.strip())
    return mapping


def build_sms_provider() -> SmsProviderPort:
    if settings.twilio_provider == "fake" or not settings.twilio_account_sid:
        return FakeSmsProvider()
    return TwilioSmsProvider(
        TwilioSettings(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            from_number=settings.twilio_from_number,
            status_callback_url=settings.twilio_status_callback_url or None,
            validate_signature=settings.twilio_validate_signature,
        )
    )


def build_sms_queue() -> MessageQueuePort:
    if settings.sms_queue_backend == "redis":
        return RedisMessageQueue(settings.redis_url, max_attempts=settings.sms_queue_max_attempts)
    return InMemoryMessageQueue(max_attempts=settings.sms_queue_max_attempts)


def build_sms_runtime(
    *,
    agents: AgentRuntime | None = None,
    store: SmsStorePort | None = None,
    memory: ConversationMemoryPort | None = None,
    provider: SmsProviderPort | None = None,
    queue: MessageQueuePort | None = None,
    monitor: SmsMonitor | None = None,
    uow_factory=None,
) -> SmsRuntime:
    # Share Phase 8 scheduling intelligence with the agent pipeline
    if agents is None:
        from app.workflows.factory import get_workflow_runtime

        agents = build_agent_runtime(
            scheduling_store=get_workflow_runtime().coordinator.resolve_scheduling_agent_store()
        )
    agent_runtime = agents
    if store is not None:
        sms_store = store
    elif (settings.sms_store_backend or "db").lower() == "memory":
        sms_store = InMemorySmsStore()
    else:
        from app.sms.sql_store import SqlAlchemySmsStore

        sms_store = SqlAlchemySmsStore()
    # Seed shop map into in-memory store when applicable
    shop_map = _parse_shop_map(settings.twilio_shop_map)
    if isinstance(sms_store, InMemorySmsStore):
        for phone, shop_id in shop_map.items():
            sms_store.register_shop_number(shop_id, phone)

    sms_memory = memory or InMemoryConversationMemory()
    sms_provider = provider or build_sms_provider()
    sms_queue = queue or build_sms_queue()
    sms_monitor = monitor or SmsMonitor()

    service = SmsAiService(
        agents=agent_runtime,
        store=sms_store,
        memory=sms_memory,
        provider=sms_provider,
        queue=sms_queue,
        monitor=sms_monitor,
        reply_generator=ContextualReplyGenerator(),
        default_from_number=settings.twilio_from_number,
        shop_number_map=shop_map,
        uow_factory=uow_factory,
    )
    return SmsRuntime(
        service=service,
        agents=agent_runtime,
        store=sms_store,
        memory=sms_memory,
        provider=sms_provider,
        queue=sms_queue,
        monitor=sms_monitor,
    )
