"""Email communication adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class EmailAdapter(BaseAdapter):
    provider = IntegrationProvider.EMAIL
    category = IntegrationCategory.COMMUNICATION
    display_name = "Email"
    description = "Transactional email send/receive for customer messages."
    auth_method = AuthMethod.API_KEY
    docs_url = None
    credential_fields = ["smtp_host", "smtp_user", "smtp_password", "from_email"]
    capabilities = [
        IntegrationCapability.SEND_CUSTOMER_MESSAGE,
        IntegrationCapability.RECEIVE_CUSTOMER_MESSAGE,
    ]
