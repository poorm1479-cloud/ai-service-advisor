"""AI catalog match → AppointmentDecision → Workflow books (no AI DB writes)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.agents.base.agent import AgentContext
from app.agents.decisions.bridge import ports_from_agents
from app.agents.intent.service import IntentAgent
from app.agents.scheduling.catalog_port import CatalogServiceView, InMemoryServiceCatalog
from app.agents.scheduling.models import SchedulingAction, SchedulingRequest
from app.agents.scheduling.service import SchedulingAgent
from app.agents.communication.models import NormalizedMessage
from app.agents.scheduling.catalog_match import match_catalog_service
from app.workflows.factory import build_workflow_runtime, reset_workflow_runtime
from app.workflows.store import InMemoryWorkflowStore


@pytest.fixture(autouse=True)
def _reset():
    reset_workflow_runtime()
    yield
    reset_workflow_runtime()


def test_match_catalog_service_by_name_and_duration():
    oil_id = uuid4()
    brake_id = uuid4()
    services = [
        CatalogServiceView(
            id=oil_id,
            name="Oil Change",
            category="maintenance",
            duration_minutes=30,
            skill="oil_change",
            bay="quick_service",
        ),
        CatalogServiceView(
            id=brake_id,
            name="Brake Repair",
            category="brakes",
            duration_minutes=120,
            skill="brakes",
            bay="general",
        ),
    ]
    oil = match_catalog_service("need an oil change appointment", services)
    assert oil is not None
    assert oil.service_id == oil_id
    assert oil.duration_minutes == 30

    brake = match_catalog_service("brakes", services)
    assert brake is not None
    assert brake.service_id == brake_id
    assert brake.duration_minutes == 120


def test_reschedule_phrasing_does_not_match_oil_change():
    """'change … appointment' must not fuzzy-match the Oil Change catalog row."""
    services = [
        CatalogServiceView(
            id=uuid4(),
            name="Oil Change",
            category="maintenance",
            duration_minutes=30,
            skill="oil_change",
            bay="quick_service",
        ),
        CatalogServiceView(
            id=uuid4(),
            name="Brake Inspection",
            category="brakes",
            duration_minutes=45,
            skill="brakes",
            bay="general",
        ),
    ]
    for phrase in (
        "Can I change my appointment time?",
        "I want to change my appointment",
        "change the appointment to Tuesday",
        "different time please",
    ):
        assert match_catalog_service(phrase, services) is None, phrase

    # Explicit service mention on a reschedule still matches.
    oil = match_catalog_service("reschedule my oil change", services)
    assert oil is not None
    assert oil.name == "Oil Change"


def test_switch_target_prefers_destination_service():
    from app.agents.scheduling.catalog_match import (
        extract_service_switch_target,
        find_catalog_service_candidates,
        match_catalog_service,
    )

    oil_id = uuid4()
    brake_id = uuid4()
    services = [
        CatalogServiceView(
            id=oil_id,
            name="Oil Change",
            category="maintenance",
            duration_minutes=30,
            skill="oil_change",
            bay="quick_service",
        ),
        CatalogServiceView(
            id=brake_id,
            name="Brake Repair",
            category="brakes",
            duration_minutes=120,
            skill="brakes",
            bay="general",
        ),
    ]
    phrase = "I want to change my oil change to a brake repair"
    assert extract_service_switch_target(phrase)
    cands = find_catalog_service_candidates(phrase, services)
    assert len(cands) == 1
    assert cands[0].name == "Brake Repair"
    # Stale appointment service_id must not pin Oil when name says Brake.
    matched = match_catalog_service("Brake Repair", services, service_id=oil_id)
    assert matched is not None
    assert matched.service_id == brake_id

    # Spoken "change the service type to X" must extract destination (space before to).
    assert (
        extract_service_switch_target("Please change the service type to brake repair")
        == "brake repair"
    )
    assert extract_service_switch_target("change service to tire rotation") == "tire rotation"
    type_cands = find_catalog_service_candidates(
        "Please change the service type to brake repair", services
    )
    assert len(type_cands) == 1
    assert type_cands[0].name == "Brake Repair"


@pytest.mark.asyncio
async def test_intent_extracts_requested_service():
    agent = IntentAgent()
    ctx = AgentContext(shop_id=uuid4())
    result = await agent.detect(
        NormalizedMessage(
            channel="sms",
            direction="incoming",
            body="I'd like to book an appointment for an oil change",
            sender="5551112222",
            recipient=None,
            subject=None,
            received_at=None,
            language="en",
            metadata={},
        ),
        ctx,
    )
    assert result.data is not None
    assert result.data.entities.get("requested_service") == "Oil Change"


@pytest.mark.asyncio
async def test_scheduling_agent_proposes_catalog_appointment_decision():
    shop_id = uuid4()
    oil_id = uuid4()
    catalog = InMemoryServiceCatalog()
    catalog.seed_shop(
        shop_id,
        [
            CatalogServiceView(
                id=oil_id,
                name="Oil Change",
                category="maintenance",
                duration_minutes=30,
                skill="oil_change",
                bay="quick_service",
            )
        ],
    )
    agent = SchedulingAgent(catalog=catalog)
    ctx = AgentContext(shop_id=shop_id, customer_id=uuid4())
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        ctx,
    )
    start = openings.data.available_slots[0].start
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            requested_service="Oil Change",
            customer_id=ctx.customer_id,
            preferred_start=start,
            time_precision="clock",
        ),
        ctx,
    )
    assert result.success
    decision = result.data.decision
    assert decision is not None
    assert decision.action == "book"
    assert decision.service_id == oil_id
    assert decision.service_name == "Oil Change"
    assert decision.duration_minutes == 30
    assert decision.recommended_slot_start is not None
    assert decision.recommended_slot_end == decision.recommended_slot_start + timedelta(
        minutes=30
    )
    # AI must not have written an appointment
    assert result.data.appointment is None


@pytest.mark.asyncio
async def test_workflow_validates_and_books_from_catalog_decision():
    shop_id = uuid4()
    oil_id = uuid4()
    catalog = InMemoryServiceCatalog()
    catalog.seed_shop(
        shop_id,
        [
            CatalogServiceView(
                id=oil_id,
                name="Oil Change",
                category="maintenance",
                duration_minutes=30,
                skill="oil_change",
                bay="quick_service",
            )
        ],
    )
    scheduling = SchedulingAgent(catalog=catalog)
    ports = ports_from_agents(scheduling=scheduling)
    rt = build_workflow_runtime(store=InMemoryWorkflowStore(), seed=False)
    import app.workflows.factory as wf_factory

    wf_factory._runtime = rt

    ctx = AgentContext(shop_id=shop_id, customer_id=uuid4())
    openings = await scheduling.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        ctx,
    )
    start = openings.data.available_slots[0].start
    decided = await scheduling.process(
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            requested_service="oil change",
            customer_id=ctx.customer_id,
            preferred_start=start,
            time_precision="clock",
        ),
        ctx,
    )
    decision = decided.data.decision
    assert decision is not None
    assert decision.service_id == oil_id
    assert decision.action == "book"

    applied = await rt.coordinator.apply_decisions(
        shop_id=shop_id,
        decisions=[decision],
        ports=ports,
        context=ctx,
    )
    assert applied.scheduling_result is not None
    assert applied.scheduling_result.success
    appt = applied.scheduling_result.appointment
    assert appt is not None
    assert appt.service_id == oil_id
    assert appt.service_name == "Oil Change"
    assert int((appt.end - appt.start).total_seconds() / 60) == 30


@pytest.mark.asyncio
async def test_empty_catalog_loses_oil_change_duration():
    """Regression: without a catalog match, slots default to 60m (not Oil Change 30m)."""
    agent = SchedulingAgent()  # empty InMemoryServiceCatalog
    ctx = AgentContext(shop_id=uuid4(), customer_id=uuid4())
    openings = await agent.process(
        SchedulingRequest(action=SchedulingAction.LIST_SLOTS, days_ahead=14),
        ctx,
    )
    start = openings.data.available_slots[0].start
    result = await agent.process(
        SchedulingRequest(
            action=SchedulingAction.BOOK,
            requested_service="Oil Change",
            customer_id=ctx.customer_id,
            preferred_start=start,
            time_precision="clock",
        ),
        ctx,
    )
    assert result.success
    decision = result.data.decision
    assert decision is not None
    assert decision.duration_minutes is None
    assert decision.recommended_slot_start is not None
    assert decision.recommended_slot_end is not None
    # InMemorySchedulingStore slot grid defaults to 60 minutes
    assert int(
        (decision.recommended_slot_end - decision.recommended_slot_start).total_seconds() / 60
    ) == 60


def test_default_service_catalog_uses_session_outside_test(monkeypatch):
    """SMS/voice/agent runtimes must read shop setup durations from Postgres."""
    from app.agents.factory import _default_service_catalog
    from app.agents.scheduling.catalog_port import InMemoryServiceCatalog, SessionServiceCatalog
    from app.infrastructure.config import settings

    monkeypatch.setattr(settings, "environment", "development")
    catalog = _default_service_catalog()
    assert isinstance(catalog, SessionServiceCatalog)

    monkeypatch.setattr(settings, "environment", "test")
    assert isinstance(_default_service_catalog(), InMemoryServiceCatalog)


@pytest.mark.asyncio
async def test_session_service_catalog_binds_rls_shop_id(monkeypatch):
    """Without app.shop_id bind, FORCE RLS returns [] and AI falls back to 60m."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from app.agents.scheduling.catalog_port import SessionServiceCatalog
    from app.shop_setup import service as setup_mod
    from app.shop_setup.schemas import ServiceOut

    shop_id = uuid4()
    oil_id = uuid4()
    now = datetime.now(timezone.utc)
    session = AsyncMock()
    session.execute = AsyncMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=session_cm)

    class _FakeSetup:
        def __init__(self, sess):  # noqa: ANN001
            self._session = sess

        async def list_services(self, shop, *, active_only=False):  # noqa: ARG002
            return [
                ServiceOut(
                    id=oil_id,
                    shop_id=shop_id,
                    name="Oil Change",
                    category="maintenance",
                    duration_minutes=30,
                    price=Decimal("49.99"),
                    skill="oil_change",
                    bay="quick_service",
                    active=True,
                    sort_order=0,
                    created_at=now,
                    updated_at=now,
                )
            ]

    monkeypatch.setattr(setup_mod, "ShopSetupService", _FakeSetup)
    rows = await SessionServiceCatalog(factory).list_bookable_services(shop_id)

    assert len(rows) == 1
    assert rows[0].duration_minutes == 30
    session.execute.assert_awaited()
    bind_call = session.execute.await_args
    assert "app.shop_id" in str(bind_call.args[0])
    assert bind_call.args[1]["sid"] == str(shop_id)
