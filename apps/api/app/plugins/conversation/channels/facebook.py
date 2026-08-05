"""Facebook Messenger channel adapter — wraps MCP FacebookAdapter when available."""

from __future__ import annotations

from app.plugins.conversation.channels.base import BaseChannelAdapter


class FacebookChannelAdapter(BaseChannelAdapter):
    channel = "facebook"

    def __init__(self, facebook_adapter: object | None = None) -> None:
        self._facebook = facebook_adapter
