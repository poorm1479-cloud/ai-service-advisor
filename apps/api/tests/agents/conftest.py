"""Shared fixtures for agent unit tests (no Postgres required)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.factory import AgentRuntime, build_agent_runtime


@pytest.fixture
def shop_id():
    return uuid4()


@pytest.fixture
def context(shop_id):
    return AgentContext(shop_id=shop_id)


@pytest.fixture
def runtime() -> AgentRuntime:
    return build_agent_runtime()
