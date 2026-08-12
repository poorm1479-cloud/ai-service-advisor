"""DI factory for Voice AI runtime."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.agents.factory import AgentRuntime, build_agent_runtime
from app.infrastructure.ai.factory import build_ai_services
from app.infrastructure.config import settings
from app.sms.queue import InMemoryMessageQueue, MessageQueuePort, RedisMessageQueue
from app.voice.memory import CallMemoryPort, InMemoryCallMemory
from app.voice.monitoring import VoiceMonitor
from app.voice.reply import VoiceReplyGenerator
from app.voice.service import VoiceAiService
from app.voice.speech import SpeechPipeline
from app.voice.store import InMemoryVoiceStore, VoiceStorePort
from app.voice.twilio.provider import (
    FakeVoiceProvider,
    TwilioVoiceProvider,
    VoiceProviderPort,
    VoiceTwilioSettings,
)
from app.voice.twilio.streams import MediaStreamHub


@dataclass(slots=True)
class VoiceRuntime:
    service: VoiceAiService
    agents: AgentRuntime
    store: VoiceStorePort
    memory: CallMemoryPort
    provider: VoiceProviderPort
    speech: SpeechPipeline
    queue: MessageQueuePort
    monitor: VoiceMonitor
    streams: MediaStreamHub


def _parse_shop_map(raw: str) -> dict[str, UUID]:
    mapping: dict[str, UUID] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        phone, shop = part.split(":", 1)
        mapping[phone.strip()] = UUID(shop.strip())
    return mapping


def build_voice_provider() -> VoiceProviderPort:
    twilio_settings = VoiceTwilioSettings(
        account_sid=settings.twilio_account_sid or "ACdev",
        auth_token=(settings.twilio_auth_token or "dev").strip(),
        from_number=settings.twilio_from_number or "+15550001111",
        validate_signature=settings.twilio_validate_signature,
        say_voice=settings.voice_tts_voice,
        barge_in=settings.voice_barge_in,
        gather_timeout=settings.voice_gather_timeout_sec,
        speech_timeout=settings.voice_gather_speech_timeout,
    )
    if settings.voice_provider == "fake" or not settings.twilio_account_sid:
        return FakeVoiceProvider(twilio_settings)
    return TwilioVoiceProvider(twilio_settings)


def build_voice_queue() -> MessageQueuePort:
    if settings.voice_queue_backend == "redis":
        return RedisMessageQueue(
            settings.redis_url,
            key="asa:voice:jobs",
            max_attempts=settings.voice_queue_max_attempts,
        )
    return InMemoryMessageQueue(max_attempts=settings.voice_queue_max_attempts)


def build_voice_runtime(
    *,
    agents: AgentRuntime | None = None,
    store: VoiceStorePort | None = None,
    memory: CallMemoryPort | None = None,
    provider: VoiceProviderPort | None = None,
    speech: SpeechPipeline | None = None,
    queue: MessageQueuePort | None = None,
    monitor: VoiceMonitor | None = None,
    streams: MediaStreamHub | None = None,
    uow_factory=None,
) -> VoiceRuntime:
    if agents is None:
        from app.workflows.factory import get_workflow_runtime

        agents = build_agent_runtime(
            scheduling_store=get_workflow_runtime().coordinator.resolve_scheduling_agent_store()
        )
    agent_runtime = agents
    if store is not None:
        voice_store = store
    elif (settings.voice_store_backend or "db").lower() == "memory":
        voice_store = InMemoryVoiceStore()
    else:
        from app.voice.sql_store import SqlAlchemyVoiceStore

        voice_store = SqlAlchemyVoiceStore()
    shop_map = _parse_shop_map(settings.twilio_voice_shop_map or settings.twilio_shop_map)
    if isinstance(voice_store, InMemoryVoiceStore):
        for phone, shop_id in shop_map.items():
            voice_store.register_shop_number(shop_id, phone)

    voice_monitor = monitor or VoiceMonitor()
    ai = build_ai_services()
    speech_pipeline = speech or SpeechPipeline(
        stt=ai.stt,
        tts=ai.tts,
        extractor=ai.extractor,
        default_voice=settings.voice_tts_voice,
        barge_in=settings.voice_barge_in,
    )
    voice_provider = provider or build_voice_provider()
    voice_queue = queue or build_voice_queue()
    voice_memory = memory or InMemoryCallMemory()
    stream_hub = streams or MediaStreamHub(voice_monitor)

    service = VoiceAiService(
        agents=agent_runtime,
        store=voice_store,
        memory=voice_memory,
        provider=voice_provider,
        speech=speech_pipeline,
        queue=voice_queue,
        monitor=voice_monitor,
        streams=stream_hub,
        reply_generator=VoiceReplyGenerator(),
        shop_number_map=shop_map,
        public_base_url=settings.twilio_public_base_url,
        stream_enabled=settings.voice_stream_enabled,
        empty_gather_hangup_after=settings.voice_empty_gather_hangup_after,
        uow_factory=uow_factory,
    )
    return VoiceRuntime(
        service=service,
        agents=agent_runtime,
        store=voice_store,
        memory=voice_memory,
        provider=voice_provider,
        speech=speech_pipeline,
        queue=voice_queue,
        monitor=voice_monitor,
        streams=stream_hub,
    )
