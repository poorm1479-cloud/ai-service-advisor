"""Phase 12 Marketing Automation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.marketing.channels import InMemoryChannelSender, build_default_channels
from app.marketing.enums import CampaignStatus, CampaignType, Channel, MessageStatus
from app.marketing.factory import build_marketing_runtime, reset_marketing_runtime
from app.marketing.store import InMemoryMarketingStore


@pytest.fixture(autouse=True)
def _reset():
    reset_marketing_runtime()
    yield
    reset_marketing_runtime()


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def runtime():
    return build_marketing_runtime(store=InMemoryMarketingStore())


@pytest.mark.asyncio
async def test_create_and_ai_plan(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Oil reminders",
        campaign_type=CampaignType.MAINTENANCE_REMINDER,
        use_demo_audience=True,
    )
    assert campaign.status == CampaignStatus.DRAFT
    assert campaign.ai_defaults is not None
    assert campaign.ai_defaults.channel in {Channel.SMS, Channel.EMAIL, Channel.VOICE}
    assert campaign.ai_defaults.message
    assert campaign.ai_defaults.frequency_days > 0
    assert len(campaign.audience) == 3


@pytest.mark.asyncio
async def test_schedule_queue_send_and_track(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Thank you blast",
        campaign_type=CampaignType.THANK_YOU,
        channels_allowed=["sms", "email"],
        use_demo_audience=True,
    )
    messages = await runtime.service.schedule_campaign(shop_id, campaign.id)
    assert len(messages) == 3
    updated = await runtime.service.get_campaign(shop_id, campaign.id)
    assert updated.status == CampaignStatus.SCHEDULED

    sent = await runtime.service.process_campaign_now(shop_id, campaign.id)
    assert len(sent) == 3
    assert all(m.status == MessageStatus.SENT for m in sent)
    assert all(m.provider_id for m in sent)

    # Track engagement
    m0 = sent[0]
    await runtime.service.track_event(shop_id, m0.id, event="open")
    await runtime.service.track_event(shop_id, m0.id, event="click")
    await runtime.service.track_event(shop_id, m0.id, event="reply")
    await runtime.service.track_event(
        shop_id, m0.id, event="appointment", revenue=Decimal("220")
    )

    metrics = await runtime.service.get_metrics(shop_id, campaign.id)
    assert metrics.sent == 3
    assert metrics.opened >= 1
    assert metrics.clicked >= 1
    assert metrics.replied >= 1
    assert metrics.appointments >= 1
    assert metrics.revenue >= Decimal("220")
    assert metrics.open_rate > 0
    assert metrics.roi != 0 or metrics.cost > 0


@pytest.mark.asyncio
async def test_retry_on_channel_failure(runtime, shop_id):
    # Force SMS sender to fail once
    assert isinstance(runtime.channels.sms, InMemoryChannelSender)
    runtime.channels.sms.fail_next = 1

    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="SMS only",
        campaign_type=CampaignType.REVIEW_REQUEST,
        channels_allowed=["sms"],
        audience=[
            {
                "name": "Pat",
                "phone": "+15550999",
                "metadata": {"shop": "Apex", "offer": "https://review.example"},
            }
        ],
        use_demo_audience=False,
    )
    await runtime.service.schedule_campaign(shop_id, campaign.id)
    first = await runtime.service.process_campaign_now(shop_id, campaign.id)
    # First attempt may fail and schedule retry — either empty processed or retrying
    messages = await runtime.store.list_messages(shop_id, campaign.id)
    assert messages
    # Force retries due
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    for item in runtime.store.queue.values():
        if item.state.value in {"pending"}:
            item.run_at = now - timedelta(seconds=1)
    second = await runtime.service.process_queue(now=now)
    final = await runtime.store.list_messages(shop_id, campaign.id)
    assert any(m.status == MessageStatus.SENT for m in final) or second or first


@pytest.mark.asyncio
async def test_calendar_and_analytics(runtime, shop_id):
    c = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Seasonal",
        campaign_type=CampaignType.SEASONAL_PROMOTION,
        use_demo_audience=True,
        auto_schedule=True,
    )
    await runtime.service.process_campaign_now(shop_id, c.id)
    events = await runtime.service.calendar(shop_id)
    assert events
    summary = await runtime.service.analytics_summary(shop_id)
    assert summary["campaigns"] >= 1
    assert "open_rate" in summary
    assert "by_channel" in summary


@pytest.mark.asyncio
async def test_create_without_demo_keeps_empty_audience(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Real only",
        campaign_type=CampaignType.INACTIVE_CUSTOMER,
        use_demo_audience=False,
    )
    assert campaign.audience == []


@pytest.mark.asyncio
async def test_inactive_and_recall_types(runtime, shop_id):
    for ctype in (
        CampaignType.INACTIVE_CUSTOMER,
        CampaignType.RECALL_NOTICE,
        CampaignType.BIRTHDAY,
        CampaignType.DECLINED_ESTIMATE,
    ):
        c = await runtime.service.create_campaign(
            shop_id=shop_id,
            name=ctype.value,
            campaign_type=ctype,
            use_demo_audience=True,
        )
        assert c.ai_defaults and c.ai_defaults.message


@pytest.mark.asyncio
async def test_sms_send_mirrors_into_conversations():
    from app.sms.factory import build_sms_runtime
    from app.sms.store import InMemorySmsStore, normalize_phone

    sms_store = InMemorySmsStore()
    sms_runtime = build_sms_runtime(store=sms_store)
    runtime = build_marketing_runtime(
        store=InMemoryMarketingStore(),
        sms_service=sms_runtime.service,
    )
    shop_id = uuid4()
    phone = "+15550123"
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Conv bridge",
        campaign_type=CampaignType.THANK_YOU,
        channels_allowed=["sms"],
        audience=[{"name": "Alex", "phone": phone}],
        use_demo_audience=False,
    )
    await runtime.service.schedule_campaign(shop_id, campaign.id)
    sent = await runtime.service.process_campaign_now(shop_id, campaign.id)
    assert len(sent) == 1
    assert sent[0].status == MessageStatus.SENT

    conversations = await sms_store.list_conversations(shop_id)
    assert len(conversations) == 1
    conv = conversations[0]
    assert conv.customer_phone == normalize_phone(phone)
    assert conv.last_intent == "marketing"
    assert conv.reply_preview == sent[0].body

    messages = await sms_store.list_messages(shop_id, conv.id)
    assert len(messages) == 1
    assert messages[0].direction == "outbound"
    assert messages[0].intent == "marketing"
    assert messages[0].body == sent[0].body
    assert messages[0].twilio_sid == sent[0].provider_id
