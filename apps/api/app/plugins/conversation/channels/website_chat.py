"""Website chat channel adapter — stub transport for agent inbound."""

from __future__ import annotations

from app.plugins.conversation.channels.base import BaseChannelAdapter


class WebsiteChatChannelAdapter(BaseChannelAdapter):
    channel = "website_chat"
