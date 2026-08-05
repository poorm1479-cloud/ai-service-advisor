"""Transactional email adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class EmailAdapter(BaseAdapter):
    provider = IntegrationProvider.EMAIL
    display_name = "Email"
    description = "SMTP / provider-backed transactional email."
    category = IntegrationCategory.MESSAGING
    auth_method = AuthMethod.API_KEY
    api_version = "v1"
    capabilities = ["email.send", "email.templates"]
    required_scopes = ["email.send"]
    credential_fields = ["api_key", "from_address"]
    docs_url = None
    tool_defs = [
        (
            "email.send",
            "Send an email",
            {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            ["email", "write"],
        ),
        (
            "email.send_template",
            "Send a templated email",
            {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "template_id": {"type": "string"},
                    "variables": {"type": "object"},
                },
                "required": ["to", "template_id"],
            },
            ["email", "write"],
        ),
    ]
