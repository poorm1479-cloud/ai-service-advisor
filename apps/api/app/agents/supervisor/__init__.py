"""Supervisor Agent — validate outputs, detect conflicts, escalate, summarize."""

from app.agents.supervisor.interfaces import SupervisorAgentPort
from app.agents.supervisor.service import SupervisorAgent

__all__ = ["SupervisorAgent", "SupervisorAgentPort"]
