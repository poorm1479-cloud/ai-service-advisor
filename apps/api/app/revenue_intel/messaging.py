"""Recommended channel + message templates."""

from __future__ import annotations

from app.revenue_intel.enums import ContactChannel, OpportunityKind
from app.revenue_intel.models import CustomerSnapshot


def recommend_channel(customer: CustomerSnapshot, kind: OpportunityKind) -> ContactChannel:
    has_sms = bool(customer.phone)
    has_email = bool(customer.email)
    recent_sms = any(c.channel == "sms" for c in customer.communications[-5:])

    if kind == OpportunityKind.LOST_CUSTOMER:
        return ContactChannel.PHONE if has_sms else ContactChannel.EMAIL
    if kind in {OpportunityKind.BRAKES, OpportunityKind.BATTERY} and has_sms:
        return ContactChannel.SMS
    if recent_sms and has_sms:
        return ContactChannel.SMS
    if has_sms:
        return ContactChannel.SMS
    if has_email:
        return ContactChannel.EMAIL
    return ContactChannel.IN_APP


_TEMPLATES: dict[OpportunityKind, str] = {
    OpportunityKind.LOST_CUSTOMER: (
        "Hi {name}, we miss you at the shop. Book a complimentary multi-point inspection "
        "this week — we're holding a slot for your {vehicle}."
    ),
    OpportunityKind.LIKELY_RETURN: (
        "Hi {name}, based on your visit pattern you're due for a check-in. "
        "Want us to reserve a convenient time for your {vehicle}?"
    ),
    OpportunityKind.LIKELY_ACCEPT: (
        "Hi {name}, we can still honor your previous estimate for {service} on your {vehicle}. "
        "Reply YES to schedule."
    ),
    OpportunityKind.MAINTENANCE_OVERDUE: (
        "Hi {name}, maintenance on your {vehicle} is overdue ({service}). "
        "Scheduling now helps avoid larger repairs."
    ),
    OpportunityKind.BATTERY: (
        "Hi {name}, winter/seasonal conditions make battery failures more likely. "
        "We recommend testing/replacing the battery on your {vehicle}."
    ),
    OpportunityKind.BRAKES: (
        "Hi {name}, your {vehicle} is due for brake service based on mileage/history. "
        "Safety first — can we schedule an inspection?"
    ),
    OpportunityKind.OIL_CHANGE: (
        "Hi {name}, your {vehicle} is due for an oil change. "
        "We have openings this week — reply to book."
    ),
    OpportunityKind.TIRES: (
        "Hi {name}, tire wear/mileage suggests it's time to evaluate tires on your {vehicle}. "
        "Ask about current packages."
    ),
    OpportunityKind.ALIGNMENT: (
        "Hi {name}, an alignment on your {vehicle} can improve tire life and handling. "
        "Book a quick alignment slot."
    ),
    OpportunityKind.FLUIDS: (
        "Hi {name}, fluid service is due on your {vehicle}. "
        "Keeping fluids fresh protects major components."
    ),
    OpportunityKind.DECLINED_ESTIMATE: (
        "Hi {name}, following up on the {service} estimate for your {vehicle}. "
        "We can revisit options that fit your budget."
    ),
}


def recommend_message(
    *,
    kind: OpportunityKind,
    customer: CustomerSnapshot,
    vehicle_label: str | None,
    service: str | None = None,
) -> str:
    tmpl = _TEMPLATES.get(kind, "Hi {name}, we have a recommended service for your {vehicle}.")
    return tmpl.format(
        name=customer.name.split()[0] if customer.name else "there",
        vehicle=vehicle_label or "vehicle",
        service=service or "service",
    )
