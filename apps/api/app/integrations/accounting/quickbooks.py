"""QuickBooks accounting adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class QuickBooksAdapter(BaseAdapter):
    provider = IntegrationProvider.QUICKBOOKS
    category = IntegrationCategory.ACCOUNTING
    display_name = "QuickBooks"
    description = "Accounting sync — invoices and payments."
    auth_method = AuthMethod.OAUTH2
    docs_url = "https://developer.intuit.com"
    credential_fields = ["client_id", "client_secret", "realm_id"]
    capabilities = [
        IntegrationCapability.IMPORT_CUSTOMER_DATA,
        IntegrationCapability.SYNC_INVOICE,
        IntegrationCapability.SYNC_PAYMENT,
    ]
