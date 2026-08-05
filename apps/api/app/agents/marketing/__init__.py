"""Marketing Agent — campaigns, review requests, thank-you, reminders."""

from app.agents.marketing.interfaces import MarketingAgentPort, MarketingDispatcherPort
from app.agents.marketing.service import MarketingAgent, LoggingMarketingDispatcher

__all__ = [
    "LoggingMarketingDispatcher",
    "MarketingAgent",
    "MarketingAgentPort",
    "MarketingDispatcherPort",
]
