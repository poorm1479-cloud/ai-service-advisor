"""CRM Agent — communication/repair history and customer summaries."""

from app.agents.crm.interfaces import CrmAgentPort, CrmStorePort
from app.agents.crm.service import CrmAgent, InMemoryCrmStore

__all__ = ["CrmAgent", "CrmAgentPort", "CrmStorePort", "InMemoryCrmStore"]
