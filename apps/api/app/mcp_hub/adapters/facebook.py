"""Facebook / Meta social adapter."""

from __future__ import annotations

from app.mcp_hub.adapters.base import BaseAdapter
from app.mcp_hub.enums import AuthMethod, IntegrationCategory, IntegrationProvider


class FacebookAdapter(BaseAdapter):
    provider = IntegrationProvider.FACEBOOK
    display_name = "Facebook"
    description = "Page messaging and posts for shop marketing."
    category = IntegrationCategory.SOCIAL
    auth_method = AuthMethod.OAUTH2
    api_version = "v19.0"
    capabilities = ["pages.read", "posts.write", "messages.read"]
    required_scopes = ["pages_manage_posts", "pages_messaging"]
    credential_fields = ["page_id", "access_token"]
    docs_url = "https://developers.facebook.com"
    tool_defs = [
        (
            "facebook.create_post",
            "Publish a page post",
            {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
            ["social", "write"],
        ),
        (
            "facebook.list_messages",
            "List page inbox messages",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            ["social", "read"],
        ),
    ]
