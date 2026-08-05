"""AutoLeap DMS adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class AutoLeapAdapter(BaseAdapter):
    provider = IntegrationProvider.AUTOLEAP
    category = IntegrationCategory.DMS
    display_name = "AutoLeap"
    description = "Automotive shop software — CRM, RO history, scheduling."
    auth_method = AuthMethod.API_KEY
    docs_url = "https://www.autoleap.com"
    credential_fields = ["api_key"]
    capabilities = [
        IntegrationCapability.IMPORT_CUSTOMER_DATA,
        IntegrationCapability.IMPORT_VEHICLE_DATA,
        IntegrationCapability.IMPORT_REPAIR_HISTORY,
        IntegrationCapability.SYNC_APPOINTMENT,
        IntegrationCapability.SYNC_INVOICE,
    ]
