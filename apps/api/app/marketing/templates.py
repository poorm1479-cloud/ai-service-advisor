"""Campaign message templates by type."""

from __future__ import annotations

from app.marketing.enums import CampaignType, Channel

# {name}, {vehicle}, {service}, {shop}, {offer}
TEMPLATES: dict[CampaignType, dict[Channel, str]] = {
    CampaignType.MAINTENANCE_REMINDER: {
        Channel.SMS: (
            "Hi {name}, just a friendly heads-up — your {vehicle} looks ready for "
            "{service}. Want us to save you a spot at {shop}? Reply YES and we'll "
            "take care of it."
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "Hope you're doing well. Your {vehicle} is about due for {service}, "
            "and we wanted to check in before it becomes a bigger worry.\n"
            "Whenever it works for you, we're happy to get you on the schedule — "
            "just reply and we'll take care of it.\n"
            "Take care,\n{shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, this is {shop}. Just checking in — your {vehicle} is due "
            "for {service}. Press 1 if you'd like to talk with an advisor and "
            "find a time that works."
        ),
    },
    CampaignType.DECLINED_ESTIMATE: {
        Channel.SMS: (
            "Hi {name}, no pressure at all — we're still happy to help with the "
            "{service} on your {vehicle} whenever you're ready. Reply YES if you'd "
            "like us to walk through the options again."
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "We know deciding on {service} for your {vehicle} isn't always easy. "
            "Whenever you're ready, we're still here with flexible options — "
            "and happy to answer any questions, no strings attached.\n"
            "Just reply if you'd like to revisit the estimate.\n"
            "Warmly,\n{shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, it's {shop}. We wanted to gently follow up about the "
            "{service} estimate for your {vehicle}. Press 1 if you'd like to "
            "talk through options at your own pace."
        ),
    },
    CampaignType.THANK_YOU: {
        Channel.SMS: (
            "Hey {name}, thanks again for stopping by {shop}. It meant a lot "
            "having you in — drive safe out there!"
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "Thank you for trusting {shop} with your vehicle. We're really glad "
            "we could help, and we hope everything feels good on the road.\n"
            "If you ever need us, we're just a message away.\n"
            "— The team at {shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, this is {shop}. Thank you so much for visiting us — "
            "we truly appreciate you. Have a wonderful day."
        ),
    },
    CampaignType.REVIEW_REQUEST: {
        Channel.SMS: (
            "Hi {name}, hope everything's going smoothly since your visit! "
            "If you have a moment, we'd love to hear how we did at {shop}: {offer}"
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "We hope your visit left you feeling taken care of. Your feedback "
            "helps us keep improving for customers like you.\n"
            "If you have a minute, we'd be grateful for a quick review: {offer}\n"
            "Thank you,\n{shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, it's {shop}. We hope your recent visit went well — "
            "if you have a moment, we'd really appreciate a quick review."
        ),
    },
    CampaignType.SEASONAL_PROMOTION: {
        Channel.SMS: (
            "Hi {name}, a little something for the season from {shop}: {offer}. "
            "Happy to help you book whenever it works for you — just reply YES."
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "As the season changes, we thought of you. Here's a special from "
            "{shop}:\n{offer}\n"
            "No rush — when you're ready, we'd love to get you on the calendar.\n"
            "See you soon,\n{shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, it's {shop} with a seasonal offer we thought you'd "
            "appreciate: {offer}. Press 1 if you'd like us to help you book."
        ),
    },
    CampaignType.RECALL_NOTICE: {
        Channel.SMS: (
            "Hi {name}, we wanted to reach out about a possible recall on your "
            "{vehicle}. Your safety matters to us — {shop} can help you get it "
            "checked. Reply YES to schedule."
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "We're reaching out because a recall may affect your {vehicle}. "
            "We know that can feel unsettling — we're here to make the check "
            "simple and stress-free.\n"
            "Please schedule an inspection with {shop} when you can. Your "
            "safety comes first.\n"
            "— {shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, this is an important safety note from {shop} about "
            "your {vehicle}. We care about keeping you safe — press 1 to "
            "schedule a quick inspection."
        ),
    },
    CampaignType.BIRTHDAY: {
        Channel.SMS: (
            "Happy birthday, {name}! Hope your day is wonderful — here's a "
            "little gift from all of us at {shop}: {offer}"
        ),
        Channel.EMAIL: (
            "Happy birthday, {name}!\n"
            "We hope today brings you something special. From everyone at "
            "{shop}, please enjoy this birthday treat: {offer}\n"
            "Cheers to you!"
        ),
        Channel.VOICE: (
            "Happy birthday, {name}! Everyone at {shop} is wishing you a "
            "wonderful day. {offer}"
        ),
    },
    CampaignType.INACTIVE_CUSTOMER: {
        Channel.SMS: (
            "Hi {name}, it's been a while and we've been thinking of you at "
            "{shop}. Whenever you're ready, we'd love to see you — complimentary "
            "inspection on us this week. Reply YES to book."
        ),
        Channel.EMAIL: (
            "Hi {name},\n"
            "It's been a little while, and we miss seeing you around {shop}. "
            "No guilt trip — life gets busy. When you're ready, we'd love to "
            "welcome you back with a complimentary multi-point inspection: "
            "{offer}\n"
            "Hope to see you soon.\n{shop}"
        ),
        Channel.VOICE: (
            "Hi {name}, it's {shop}. We've missed you! Whenever you're ready, "
            "press 1 to schedule a complimentary inspection — we'd love to "
            "help again."
        ),
    },
}

EMAIL_SUBJECTS: dict[CampaignType, str] = {
    CampaignType.MAINTENANCE_REMINDER: "A friendly reminder about your vehicle",
    CampaignType.DECLINED_ESTIMATE: "Still here whenever you're ready",
    CampaignType.THANK_YOU: "Thanks for trusting us",
    CampaignType.REVIEW_REQUEST: "How did we do? We'd love to hear",
    CampaignType.SEASONAL_PROMOTION: "A little something for the season",
    CampaignType.RECALL_NOTICE: "A safety note about your vehicle",
    CampaignType.BIRTHDAY: "Happy birthday from our team",
    CampaignType.INACTIVE_CUSTOMER: "We've missed you — come back anytime",
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
