"""Twilio communications adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class TwilioAdapter(BaseAdapter):
    provider = IntegrationProvider.TWILIO
    display_name = "Twilio"
    description = "SMS and voice telephony for shop communications."
    category = IntegrationCategory.COMMUNICATIONS
    auth_method = AuthMethod.BASIC
    api_version = "v1"
    capabilities = ["sms.send", "voice.call", "webhooks"]
    required_scopes = ["messaging", "voice"]
    credential_fields = ["account_sid", "auth_token"]
    docs_url = "https://www.twilio.com/docs"
    tool_defs = [
        (
            "twilio.send_sms",
            "Send an SMS message",
            {
                "type": "object",
                "properties": {"to": {"type": "string"}, "body": {"type": "string"}, "from": {"type": "string"}},
                "required": ["to", "body"],
            },
            ["sms", "write"],
        ),
        (
            "twilio.list_messages",
            "List recent messages",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            ["sms", "read"],
        ),
    ]
