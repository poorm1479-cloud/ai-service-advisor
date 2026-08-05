"""Twilio communication adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class TwilioAdapter(BaseAdapter):
    provider = IntegrationProvider.TWILIO
    category = IntegrationCategory.COMMUNICATION
    display_name = "Twilio"
    description = "SMS / voice messaging for customer communication."
    auth_method = AuthMethod.API_KEY
    docs_url = "https://www.twilio.com/docs"
    credential_fields = ["account_sid", "auth_token", "from_number"]
    capabilities = [
        IntegrationCapability.SEND_CUSTOMER_MESSAGE,
        IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE,
    ]
