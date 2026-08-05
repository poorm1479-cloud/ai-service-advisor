"""Conversation Plugin — unified Conversation domain for Workflow Engine."""

from app.plugins.conversation.factory import (
    build_conversation_plugin,
    conversation_plugin_from_ports,
    get_conversation_plugin,
    reset_conversation_plugin,
)
from app.plugins.conversation.interfaces import IConversationPlugin
from app.plugins.conversation.models import (
    Conversation,
    ConversationAiInsights,
    ConversationChannel,
    ConversationMessage,
    ConversationStatus,
    Participant,
    ParticipantRole,
)
from app.plugins.conversation.plugin import ConversationPlugin

__all__ = [
    "Conversation",
    "ConversationAiInsights",
    "ConversationChannel",
    "ConversationMessage",
    "ConversationPlugin",
    "ConversationStatus",
    "IConversationPlugin",
    "Participant",
    "ParticipantRole",
    "build_conversation_plugin",
    "conversation_plugin_from_ports",
    "get_conversation_plugin",
    "reset_conversation_plugin",
]
