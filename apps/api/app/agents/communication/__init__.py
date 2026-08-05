"""Communication Agent — normalize inbound multi-channel messages."""

from app.agents.communication.interfaces import CommunicationAgentPort
from app.agents.communication.service import CommunicationAgent

__all__ = ["CommunicationAgent", "CommunicationAgentPort"]
