"""Channel adapters for Conversation Plugin."""

from app.plugins.conversation.channels.base import BaseChannelAdapter, ChannelAdapter, ChannelInbound
from app.plugins.conversation.channels.email import EmailChannelAdapter
from app.plugins.conversation.channels.facebook import FacebookChannelAdapter
from app.plugins.conversation.channels.google_business import GoogleBusinessChannelAdapter
from app.plugins.conversation.channels.instagram import InstagramChannelAdapter
from app.plugins.conversation.channels.phone import PhoneChannelAdapter, VoiceChannelAdapter
from app.plugins.conversation.channels.sms import SmsChannelAdapter
from app.plugins.conversation.channels.walk_in import WalkInChannelAdapter
from app.plugins.conversation.channels.website_chat import WebsiteChatChannelAdapter
from app.plugins.conversation.channels.whatsapp import WhatsAppChannelAdapter


def default_channel_adapters() -> dict[str, BaseChannelAdapter]:
    adapters: list[BaseChannelAdapter] = [
        SmsChannelAdapter(),
        PhoneChannelAdapter(),
        EmailChannelAdapter(),
        FacebookChannelAdapter(),
        WebsiteChatChannelAdapter(),
        WalkInChannelAdapter(),
        WhatsAppChannelAdapter(),
        InstagramChannelAdapter(),
        GoogleBusinessChannelAdapter(),
    ]
    return {a.channel: a for a in adapters}


__all__ = [
    "BaseChannelAdapter",
    "ChannelAdapter",
    "ChannelInbound",
    "EmailChannelAdapter",
    "FacebookChannelAdapter",
    "GoogleBusinessChannelAdapter",
    "InstagramChannelAdapter",
    "PhoneChannelAdapter",
    "SmsChannelAdapter",
    "VoiceChannelAdapter",
    "WalkInChannelAdapter",
    "WebsiteChatChannelAdapter",
    "WhatsAppChannelAdapter",
    "default_channel_adapters",
]
