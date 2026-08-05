"""Customer Agent — find, create, merge, and profile customers."""

from app.agents.customer.interfaces import CustomerAgentPort, CustomerDirectoryPort
from app.agents.customer.service import CustomerAgent, InMemoryCustomerDirectory

__all__ = [
    "CustomerAgent",
    "CustomerAgentPort",
    "CustomerDirectoryPort",
    "InMemoryCustomerDirectory",
]
