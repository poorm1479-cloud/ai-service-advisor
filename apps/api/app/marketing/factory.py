"""DI factory for Marketing Automation."""

from __future__ import annotations

from dataclasses import dataclass

from app.marketing.ai_chooser import MarketingAiChooser
from app.marketing.channels import ChannelRouter, bridge_sms_to_conversations, build_default_channels
from app.marketing.monitoring import MarketingMonitor
from app.marketing.queue import MessageQueue
from app.marketing.scheduler import CampaignScheduler
from app.marketing.service import MarketingAutomationService
from app.marketing.store import InMemoryMarketingStore, MarketingStorePort


@dataclass(slots=True)
class MarketingRuntime:
    service: MarketingAutomationService
    store: MarketingStorePort
    scheduler: CampaignScheduler
    queue: MessageQueue
    chooser: MarketingAiChooser
    channels: ChannelRouter
    monitor: MarketingMonitor


_runtime: MarketingRuntime | None = None


def build_marketing_runtime(
    *,
    store: MarketingStorePort | None = None,
    channels: ChannelRouter | None = None,
    sms_service: object | None = None,
    bridge_conversations: bool = True,
) -> MarketingRuntime:
    resource_store = store or InMemoryMarketingStore()
    channel_router = channels or build_default_channels()
    if bridge_conversations and sms_service is not None:
        channel_router = bridge_sms_to_conversations(channel_router, sms_service=sms_service)
    chooser = MarketingAiChooser()
    queue = MessageQueue(resource_store)
    scheduler = CampaignScheduler(
        store=resource_store,
        queue=queue,
        channels=channel_router,
        chooser=chooser,
    )
    service = MarketingAutomationService(
        store=resource_store,
        scheduler=scheduler,
        queue=queue,
        chooser=chooser,
        channels=channel_router,
    )
    return MarketingRuntime(
        service=service,
        store=resource_store,
        scheduler=scheduler,
        queue=queue,
        chooser=chooser,
        channels=channel_router,
        monitor=MarketingMonitor(),
    )


def get_marketing_runtime() -> MarketingRuntime:
    global _runtime
    if _runtime is None:
        sms_service = None
        try:
            from app.sms.runtime import get_sms_runtime

            sms_service = get_sms_runtime().service
        except Exception:  # noqa: BLE001
            sms_service = None
        _runtime = build_marketing_runtime(sms_service=sms_service)
    return _runtime


def reset_marketing_runtime() -> None:
    global _runtime
    _runtime = None
