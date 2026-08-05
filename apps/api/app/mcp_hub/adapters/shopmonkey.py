"""Shopmonkey PMS adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class ShopmonkeyAdapter(BaseAdapter):
    provider = IntegrationProvider.SHOPMONKEY
    display_name = "Shopmonkey"
    description = "Modern shop OS — jobs, inventory, and customer CRM."
    category = IntegrationCategory.PMS
    auth_method = AuthMethod.API_KEY
    api_version = "v1"
    capabilities = ["jobs.read", "jobs.write", "inventory.read", "customers.read"]
    required_scopes = ["shop.read", "shop.write"]
    credential_fields = ["api_key"]
    docs_url = "https://www.shopmonkey.io"
    tool_defs = [
        (
            "shopmonkey.list_jobs",
            "List open jobs",
            {"type": "object", "properties": {"status": {"type": "string"}}},
            ["pms", "read"],
        ),
        (
            "shopmonkey.update_job",
            "Update job status or notes",
            {
                "type": "object",
                "properties": {"job_id": {"type": "string"}, "status": {"type": "string"}, "notes": {"type": "string"}},
                "required": ["job_id"],
            },
            ["pms", "write"],
        ),
    ]
