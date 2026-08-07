"""AI chooser — best time, channel, message, frequency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.marketing.enums import CampaignType, Channel
from app.marketing.models import AiPlan, AudienceMember, Campaign
from app.marketing.templates import EMAIL_SUBJECTS, render_template

# Preferred local send hours by channel (naive heuristic)
_CHANNEL_HOURS: dict[Channel, tuple[int, int]] = {
    Channel.SMS: (10, 19),
    Channel.EMAIL: (8, 17),
    Channel.VOICE: (11, 17),
}

# Re-recommendation cooldown after a successful SMS/email send (days).
_FREQUENCY_DAYS: dict[CampaignType, int] = {
    CampaignType.MAINTENANCE_REMINDER: 90,
    CampaignType.DECLINED_ESTIMATE: 14,
    CampaignType.THANK_YOU: 365,
    CampaignType.REVIEW_REQUEST: 180,
    CampaignType.SEASONAL_PROMOTION: 30,
    CampaignType.RECALL_NOTICE: 7,
    CampaignType.BIRTHDAY: 365,
    CampaignType.INACTIVE_CUSTOMER: 60,
}


def recommendation_cooldown_days(campaign_type: CampaignType | str) -> int:
    """Days before a customer may appear again in AI Recommendations after SMS/email."""
    ctype = (
        campaign_type
        if isinstance(campaign_type, CampaignType)
        else CampaignType(campaign_type)
    )
    return _FREQUENCY_DAYS[ctype]


def _prefs(campaign_type: CampaignType) -> list[Channel]:
    return {
        CampaignType.MAINTENANCE_REMINDER: [Channel.SMS, Channel.EMAIL, Channel.VOICE],
        CampaignType.DECLINED_ESTIMATE: [Channel.SMS, Channel.EMAIL, Channel.VOICE],
        CampaignType.THANK_YOU: [Channel.SMS, Channel.EMAIL],
        CampaignType.REVIEW_REQUEST: [Channel.SMS, Channel.EMAIL],
        CampaignType.SEASONAL_PROMOTION: [Channel.EMAIL, Channel.SMS],
        CampaignType.RECALL_NOTICE: [Channel.VOICE, Channel.SMS, Channel.EMAIL],
        CampaignType.BIRTHDAY: [Channel.EMAIL, Channel.SMS],
        CampaignType.INACTIVE_CUSTOMER: [Channel.SMS, Channel.VOICE, Channel.EMAIL],
    }[campaign_type]


class MarketingAiChooser:
    """Heuristic AI planner (swap for LLM later without changing callers)."""

    def choose_channel(
        self,
        member: AudienceMember,
        campaign: Campaign,
    ) -> Channel:
        allowed = set(campaign.channels_allowed) or {Channel.SMS, Channel.EMAIL}
        if member.preferred_channel and member.preferred_channel in allowed:
            return member.preferred_channel

        for ch in _prefs(campaign.campaign_type):
            if ch not in allowed:
                continue
            if ch == Channel.SMS and member.phone:
                return Channel.SMS
            if ch == Channel.EMAIL and member.email:
                return Channel.EMAIL
            if ch == Channel.VOICE and member.phone:
                return Channel.VOICE

        if member.phone and Channel.SMS in allowed:
            return Channel.SMS
        if member.email and Channel.EMAIL in allowed:
            return Channel.EMAIL
        if member.phone and Channel.VOICE in allowed:
            return Channel.VOICE
        # Fall back to first allowed
        return next(iter(allowed))

    def choose_send_time(
        self,
        *,
        channel: Channel,
        now: datetime | None = None,
        preferred_start: datetime | None = None,
    ) -> datetime:
        now = now or datetime.now(timezone.utc)
        base = preferred_start or now
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        start_h, end_h = _CHANNEL_HOURS[channel]
        candidate = base
        # If outside window, push to next window start
        local_hour = candidate.hour  # treating UTC as shop-local for tests/local
        if local_hour < start_h:
            candidate = candidate.replace(hour=start_h, minute=0, second=0, microsecond=0)
        elif local_hour >= end_h:
            candidate = (candidate + timedelta(days=1)).replace(
                hour=start_h, minute=0, second=0, microsecond=0
            )
        # Avoid weekends for voice
        if channel == Channel.VOICE and candidate.weekday() >= 5:
            days = 7 - candidate.weekday()
            candidate = (candidate + timedelta(days=days)).replace(hour=start_h, minute=0, second=0)
        return candidate

    def choose_frequency(self, campaign_type: CampaignType, campaign: Campaign) -> int:
        return min(campaign.max_sends_per_customer_days, _FREQUENCY_DAYS[campaign_type])

    def choose_message(
        self,
        *,
        campaign: Campaign,
        member: AudienceMember,
        channel: Channel,
    ) -> tuple[str, str | None]:
        meta = member.metadata or {}
        body = render_template(
            campaign.campaign_type,
            channel,
            name=member.name.split()[0] if member.name else "there",
            vehicle=str(meta.get("vehicle") or "vehicle"),
            service=str(meta.get("service") or "service"),
            shop=str(meta.get("shop") or campaign.metadata.get("shop_name") or "our shop"),
            offer=str(meta.get("offer") or campaign.metadata.get("offer") or "a special offer"),
            custom=campaign.custom_message,
        )
        subject = None
        if channel == Channel.EMAIL:
            subject = EMAIL_SUBJECTS.get(campaign.campaign_type, campaign.name)
        return body, subject

    def plan_for_member(
        self,
        campaign: Campaign,
        member: AudienceMember,
        *,
        now: datetime | None = None,
    ) -> AiPlan:
        now = now or datetime.now(timezone.utc)
        channel = self.choose_channel(member, campaign)
        send_at = self.choose_send_time(
            channel=channel,
            now=now,
            preferred_start=campaign.scheduled_start,
        )
        body, subject = self.choose_message(campaign=campaign, member=member, channel=channel)
        freq = self.choose_frequency(campaign.campaign_type, campaign)
        conf = 0.85 if (member.phone or member.email) else 0.55
        return AiPlan(
            channel=channel,
            send_at=send_at,
            message=body,
            subject=subject,
            frequency_days=freq,
            confidence=conf,
            reasons=[],
        )

    def plan_campaign_defaults(
        self, campaign: Campaign, *, now: datetime | None = None
    ) -> AiPlan:
        now = now or datetime.now(timezone.utc)
        # Synthetic member from first audience or empty
        if campaign.audience:
            return self.plan_for_member(campaign, campaign.audience[0], now=now)
        member = AudienceMember(
            customer_id=campaign.id,
            name="Customer",
            phone="+15550001111",
            email="customer@example.com",
        )
        return self.plan_for_member(campaign, member, now=now)
