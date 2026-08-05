"""Tekmetric DMS adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class TekmetricAdapter(BaseAdapter):
    provider = IntegrationProvider.TEKMETRIC
    category = IntegrationCategory.DMS
    display_name = "Tekmetric"
    description = "Shop management — repair orders, customers, and vehicles."
    auth_method = AuthMethod.OAUTH2
    docs_url = "https://www.tekmetric.com"
    credential_fields = ["client_id", "client_secret", "shop_id"]
    capabilities = [
        IntegrationCapability.IMPORT_CUSTOMER_DATA,
        IntegrationCapability.IMPORT_VEHICLE_DATA,
        IntegrationCapability.IMPORT_REPAIR_HISTORY,
        IntegrationCapability.SYNC_APPOINTMENT,
        IntegrationCapability.SYNC_INVOICE,
    ]
