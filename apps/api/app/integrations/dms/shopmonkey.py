"""Shopmonkey DMS adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class ShopmonkeyAdapter(BaseAdapter):
    provider = IntegrationProvider.SHOPMONKEY
    category = IntegrationCategory.DMS
    display_name = "Shopmonkey"
    description = "Modern shop OS — customers, vehicles, jobs, and appointments."
    auth_method = AuthMethod.API_KEY
    docs_url = "https://www.shopmonkey.io"
    credential_fields = ["api_key"]
    capabilities = [
        IntegrationCapability.IMPORT_CUSTOMER_DATA,
        IntegrationCapability.IMPORT_VEHICLE_DATA,
        IntegrationCapability.IMPORT_REPAIR_HISTORY,
        IntegrationCapability.SYNC_APPOINTMENT,
        IntegrationCapability.SYNC_INVOICE,
    ]
