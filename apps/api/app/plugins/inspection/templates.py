"""Customer communication templates for inspection outcomes."""

from __future__ import annotations

from typing import Any


TEMPLATES: dict[str, str] = {
    "safety_warning": (
        "Safety alert for your {vehicle}: we found {issue}. "
        "This should be addressed before driving extensively. "
        "Reply YES to approve the recommended repair (~${amount})."
    ),
    "recommended_repair": (
        "After inspecting your {vehicle}, we recommend: {issue}. "
        "Estimated investment ~${amount}. Reply YES to approve or ASK for details."
    ),
    "optional_repair": (
        "Optional improvement for your {vehicle}: {issue}. "
        "Not urgent — estimated ~${amount}. Happy to schedule when convenient."
    ),
    "maintenance_reminder": (
        "Maintenance note for your {vehicle}: {issue}. "
        "Staying ahead helps avoid larger repairs. Estimated ~${amount}."
    ),
    "approval_request": (
        "Please approve inspection-based repairs for your {vehicle}: {services}. "
        "Total estimate ~${amount}. Reply YES to approve, NO to decline, or CALL to speak with us."
    ),
    "follow_up": (
        "Following up on your {vehicle} inspection — {issue} is still outstanding. "
        "We can help whenever you're ready. Estimated ~${amount}."
    ),
}


def render_template(name: str, **kwargs: Any) -> str:
    template = TEMPLATES.get(name) or TEMPLATES["recommended_repair"]
    defaults = {
        "vehicle": "vehicle",
        "issue": "an item needing attention",
        "amount": "0.00",
        "services": "recommended services",
    }
    defaults.update({k: (str(v) if v is not None else defaults.get(k, "")) for k, v in kwargs.items()})
    try:
        return template.format(**defaults)
    except KeyError:
        return template
