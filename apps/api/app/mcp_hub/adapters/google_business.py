"""Google Business Profile adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class GoogleBusinessAdapter(BaseAdapter):
    provider = IntegrationProvider.GOOGLE_BUSINESS
    display_name = "Google Business"
    description = "Manage Google Business Profile reviews and posts."
    category = IntegrationCategory.BUSINESS
    auth_method = AuthMethod.OAUTH2
    api_version = "v1"
    capabilities = ["reviews.read", "reviews.reply", "posts.write"]
    required_scopes = ["business.manage"]
    credential_fields = ["client_id", "client_secret", "refresh_token"]
    docs_url = "https://developers.google.com/my-business"
    tool_defs = [
        (
            "google_business.list_reviews",
            "List business reviews",
            {"type": "object", "properties": {"location_id": {"type": "string"}}},
            ["business", "read"],
        ),
        (
            "google_business.reply_review",
            "Reply to a review",
            {
                "type": "object",
                "properties": {"review_id": {"type": "string"}, "comment": {"type": "string"}},
                "required": ["review_id", "comment"],
            },
            ["business", "write"],
        ),
    ]
