"""Stripe payment adapter."""

from __future__ import annotations

from app.integrations.core.adapter import BaseAdapter
from app.integrations.enums import (
    AuthMethod,
    IntegrationCapability,
    IntegrationCategory,
    IntegrationProvider,
)


class StripeAdapter(BaseAdapter):
    provider = IntegrationProvider.STRIPE
    category = IntegrationCategory.PAYMENT
    display_name = "Stripe"
    description = "Payment processing and payment sync."
    auth_method = AuthMethod.API_KEY
    docs_url = "https://stripe.com/docs"
    credential_fields = ["secret_key"]
    capabilities = [
        IntegrationCapability.SYNC_PAYMENT,
        IntegrationCapability.SYNC_INVOICE,
    ]
