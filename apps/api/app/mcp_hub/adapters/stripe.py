"""Stripe payments adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class StripeAdapter(BaseAdapter):
    provider = IntegrationProvider.STRIPE
    display_name = "Stripe"
    description = "Payments, invoices, and customer billing."
    category = IntegrationCategory.PAYMENTS
    auth_method = AuthMethod.BEARER
    api_version = "2024-06-20"
    capabilities = ["payments.create", "invoices.read", "customers.read"]
    required_scopes = ["payments"]
    credential_fields = ["secret_key"]
    docs_url = "https://stripe.com/docs/api"
    tool_defs = [
        (
            "stripe.create_payment_intent",
            "Create a payment intent",
            {
                "type": "object",
                "properties": {"amount": {"type": "integer"}, "currency": {"type": "string"}, "customer": {"type": "string"}},
                "required": ["amount"],
            },
            ["payments", "write"],
        ),
        (
            "stripe.list_invoices",
            "List invoices",
            {"type": "object", "properties": {"customer": {"type": "string"}, "limit": {"type": "integer"}}},
            ["payments", "read"],
        ),
    ]
