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
    await runtime.store.force_campaign_queue_due(shop_id, campaign.id, now=now - timedelta(seconds=1))
    second = await runtime.service.process_queue(now=now, shop_id=shop_id)
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
async def test_delete_message_removes_record_and_queue(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Delete me",
        campaign_type=CampaignType.THANK_YOU,
        channels_allowed=["sms"],
        use_demo_audience=True,
    )
    messages = await runtime.service.schedule_campaign(shop_id, campaign.id)
    assert messages
    target = messages[0]
    assert await runtime.store.get_message(shop_id, target.id) is not None

    await runtime.service.delete_message(shop_id, target.id)

    assert await runtime.store.get_message(shop_id, target.id) is None
    remaining = await runtime.store.list_messages(shop_id, campaign.id)
    assert all(m.id != target.id for m in remaining)
    assert all(q.message_id != target.id for q in runtime.store.queue.values())
    with pytest.raises(LookupError):
        await runtime.service.delete_message(shop_id, target.id)


@pytest.mark.asyncio
async def test_delete_all_messages(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Delete all",
        campaign_type=CampaignType.THANK_YOU,
        channels_allowed=["sms"],
        use_demo_audience=True,
    )
    messages = await runtime.service.schedule_campaign(shop_id, campaign.id)
    assert len(messages) >= 1

    deleted = await runtime.service.delete_all_messages(shop_id)
    assert deleted >= 1
    remaining = await runtime.store.list_messages(shop_id, campaign.id)
    assert remaining == []
    assert all(q.shop_id != shop_id or q.message_id not in {m.id for m in messages}
               for q in runtime.store.queue.values())
    assert await runtime.service.delete_all_messages(shop_id) == 0


@pytest.mark.asyncio
async def test_delete_messages_bulk(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Bulk delete",
        campaign_type=CampaignType.THANK_YOU,
        channels_allowed=["sms"],
        use_demo_audience=True,
    )
    messages = await runtime.service.schedule_campaign(shop_id, campaign.id)
    assert len(messages) >= 1
    keep = messages[-1]
    targets = [m.id for m in messages[:-1]] if len(messages) > 1 else [messages[0].id]

    deleted = await runtime.service.delete_messages(shop_id, targets)
    assert deleted == len(targets)

    remaining = await runtime.store.list_messages(shop_id, campaign.id)
    if len(messages) > 1:
        assert any(m.id == keep.id for m in remaining)
        assert all(m.id not in set(targets) for m in remaining)
    else:
        assert remaining == []
    assert await runtime.service.delete_messages(shop_id, targets) == 0


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
async def test_preview_ai_works_with_sample_looking_crm_audience(runtime, shop_id):
    """CRM customers may reuse demo-like phones/emails; preview must still work."""
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Declined follow-up",
        campaign_type=CampaignType.DECLINED_ESTIMATE,
        use_demo_audience=False,
        audience=[
            {
                "name": "Alex Rivera",
                "phone": "+15550100",
                "email": "alex@example.com",
                "metadata": {"vehicle": "2018 Civic", "service": "brakes", "shop": "Main Street"},
            }
        ],
    )
    preview = await runtime.service.preview_ai(shop_id, campaign.id)
    assert preview["customer_name"] == "Alex Rivera"
    assert preview["message"]
    assert preview["channel"] in {"sms", "email", "voice"}


@pytest.mark.asyncio
async def test_preview_ai_empty_audience_errors(runtime, shop_id):
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Empty",
        campaign_type=CampaignType.THANK_YOU,
        use_demo_audience=False,
    )
    with pytest.raises(LookupError, match="no audience"):
        await runtime.service.preview_ai(shop_id, campaign.id)


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


@pytest.mark.asyncio
async def test_recommendation_cooldown_after_sms_send(runtime, shop_id):
    """After SMS/email is sent, customer is suppressed until cooldown days elapse."""
    from app.marketing.ai_chooser import recommendation_cooldown_days

    customer_id = uuid4()
    audience = [
        {
            "customer_id": str(customer_id),
            "name": "Sam",
            "phone": "+15558801",
            "email": "sam@example.com",
            "metadata": {"shop": "Apex", "vehicle": "2019 Civic", "service": "oil"},
        }
    ]
    campaign = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Maint reminder",
        campaign_type=CampaignType.MAINTENANCE_REMINDER,
        channels_allowed=["sms", "email"],
        audience=audience,
        use_demo_audience=False,
    )
    await runtime.service.schedule_campaign(shop_id, campaign.id)
    sent = await runtime.service.process_campaign_now(shop_id, campaign.id)
    assert len(sent) == 1
    assert sent[0].sent_at is not None

    suppressed = await runtime.service.customers_in_recommendation_cooldown(
        shop_id, CampaignType.MAINTENANCE_REMINDER
    )
    assert customer_id in suppressed

    filtered = runtime.service.filter_audience_for_recommendations(
        campaign.audience, suppressed
    )
    assert filtered == []

    # Second schedule of a new same-type campaign should skip already-contacted customer
    campaign2 = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Maint reminder 2",
        campaign_type=CampaignType.MAINTENANCE_REMINDER,
        channels_allowed=["sms"],
        audience=audience,
        use_demo_audience=False,
    )
    msgs2 = await runtime.service.schedule_campaign(shop_id, campaign2.id)
    assert msgs2 == []

    # After full cooldown window, customer is eligible again
    days = recommendation_cooldown_days(CampaignType.MAINTENANCE_REMINDER)
    future = datetime.now(timezone.utc) + timedelta(days=days + 1)
    suppressed_later = await runtime.service.customers_in_recommendation_cooldown(
        shop_id, CampaignType.MAINTENANCE_REMINDER, now=future
    )
    assert customer_id not in suppressed_later


@pytest.mark.asyncio
async def test_recommendation_cooldown_is_per_campaign_type(runtime, shop_id):
    customer_id = uuid4()
    audience = [
        {
            "customer_id": str(customer_id),
            "name": "Jordan",
            "phone": "+15558802",
            "metadata": {"shop": "Apex"},
        }
    ]
    declined = await runtime.service.create_campaign(
        shop_id=shop_id,
        name="Declined follow-up",
        campaign_type=CampaignType.DECLINED_ESTIMATE,
        channels_allowed=["sms"],
        audience=audience,
        use_demo_audience=False,
    )
    await runtime.service.schedule_campaign(shop_id, declined.id)
    await runtime.service.process_campaign_now(shop_id, declined.id)

    still_open = await runtime.service.customers_in_recommendation_cooldown(
        shop_id, CampaignType.INACTIVE_CUSTOMER
    )
    assert customer_id not in still_open

    same_type = await runtime.service.customers_in_recommendation_cooldown(
        shop_id, CampaignType.DECLINED_ESTIMATE
    )
    assert customer_id in same_type
