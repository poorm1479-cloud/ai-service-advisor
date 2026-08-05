"""Campaign message templates by type."""

from __future__ import annotations

from app.marketing.enums import CampaignType, Channel

# {name}, {vehicle}, {service}, {shop}, {offer}
TEMPLATES: dict[CampaignType, dict[Channel, str]] = {
    CampaignType.MAINTENANCE_REMINDER: {
        Channel.SMS: "Hi {name}, your {vehicle} is due for {service}. Reply YES to book at {shop}.",
        Channel.EMAIL: (
            "Hi {name},\n\nYour {vehicle} is due for {service}. "
            "Schedule online or reply to this email.\n\n— {shop}"
        ),
        Channel.VOICE: (
            "Hello {name}, this is {shop}. Your {vehicle} is due for {service}. "
            "Press 1 to speak with an advisor."
        ),
    },
    CampaignType.DECLINED_ESTIMATE: {
        Channel.SMS: "Hi {name}, we can still honor options for {service} on your {vehicle}. Reply YES.",
        Channel.EMAIL: (
            "Hi {name},\n\nFollowing up on the {service} estimate for your {vehicle}. "
            "We have flexible options — reply to revisit.\n\n— {shop}"
        ),
        Channel.VOICE: (
            "Hello {name}, {shop} calling about your previous {service} estimate. "
            "Press 1 if you'd like to discuss options."
        ),
    },
    CampaignType.THANK_YOU: {
        Channel.SMS: "Thanks {name}! We appreciate your visit to {shop}. Drive safe.",
        Channel.EMAIL: "Hi {name},\n\nThank you for choosing {shop}. We're glad we could help.\n\n— The team",
        Channel.VOICE: "Hello {name}, thank you for visiting {shop}. Have a great day.",
    },
    CampaignType.REVIEW_REQUEST: {
        Channel.SMS: "Hi {name}, how was your visit to {shop}? Leave a quick review: {offer}",
        Channel.EMAIL: (
            "Hi {name},\n\nWe'd love your feedback on your recent visit. "
            "Share a review here: {offer}\n\n— {shop}"
        ),
        Channel.VOICE: "Hello {name}, {shop} would appreciate a quick review of your recent visit.",
    },
    CampaignType.SEASONAL_PROMOTION: {
        Channel.SMS: "Hi {name}, seasonal special at {shop}: {offer}. Book this week!",
        Channel.EMAIL: "Hi {name},\n\n{offer}\n\nBook your appointment with {shop} this season.",
        Channel.VOICE: "Hello {name}, {shop} has a seasonal offer: {offer}. Press 1 to book.",
    },
    CampaignType.RECALL_NOTICE: {
        Channel.SMS: "Important: possible recall related to your {vehicle}. Contact {shop} to schedule a check.",
        Channel.EMAIL: (
            "Hi {name},\n\nA recall may affect your {vehicle}. "
            "Please schedule an inspection with {shop}.\n\nSafety first."
        ),
        Channel.VOICE: (
            "Hello {name}, this is an important safety notice from {shop} "
            "regarding your {vehicle}. Press 1 to schedule an inspection."
        ),
    },
    CampaignType.BIRTHDAY: {
        Channel.SMS: "Happy birthday {name}! Enjoy {offer} from {shop} this month.",
        Channel.EMAIL: "Happy birthday {name}!\n\nCelebrate with {offer} from all of us at {shop}.",
        Channel.VOICE: "Happy birthday {name}! {shop} wishes you a wonderful day. {offer}",
    },
    CampaignType.INACTIVE_CUSTOMER: {
        Channel.SMS: "Hi {name}, we miss you at {shop}. Complimentary inspection this week — reply YES.",
        Channel.EMAIL: (
            "Hi {name},\n\nIt's been a while. Come back to {shop} for a complimentary "
            "multi-point inspection: {offer}\n\nWe'd love to see you."
        ),
        Channel.VOICE: (
            "Hello {name}, it's {shop}. We miss you! Press 1 to schedule a complimentary inspection."
        ),
    },
}

EMAIL_SUBJECTS: dict[CampaignType, str] = {
    CampaignType.MAINTENANCE_REMINDER: "Maintenance due for your vehicle",
    CampaignType.DECLINED_ESTIMATE: "Still here to help with your estimate",
    CampaignType.THANK_YOU: "Thank you for visiting",
    CampaignType.REVIEW_REQUEST: "How did we do?",
    CampaignType.SEASONAL_PROMOTION: "Seasonal offer inside",
    CampaignType.RECALL_NOTICE: "Important safety notice",
    CampaignType.BIRTHDAY: "Happy birthday from us",
    CampaignType.INACTIVE_CUSTOMER: "We miss you — special invite",
}


def render_template(
    campaign_type: CampaignType,
    channel: Channel,
    *,
    name: str = "there",
    vehicle: str = "vehicle",
    service: str = "service",
    shop: str = "our shop",
    offer: str = "a special offer",
    custom: str | None = None,
) -> str:
    if custom:
        return custom.format(
            name=name, vehicle=vehicle, service=service, shop=shop, offer=offer
        )
    tmpl = TEMPLATES[campaign_type][channel]
    return tmpl.format(name=name, vehicle=vehicle, service=service, shop=shop, offer=offer)
