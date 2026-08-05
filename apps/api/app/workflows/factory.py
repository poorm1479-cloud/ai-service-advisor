"""DI factory for Workflow Engine."""

from __future__ import annotations

from dataclasses import dataclass

from app.workflows.actions import ActionExecutor
from app.workflows.bus import WorkflowEventBus
from app.workflows.coordinator import WorkflowCoordinator
from app.workflows.decision_executor import DecisionExecutor
from app.workflows.monitoring import WorkflowMonitor
from app.workflows.retry_queue import RetryQueue
from app.workflows.runner import WorkflowRunner
from app.workflows.seeds import default_workflows
from app.workflows.service import WorkflowEngineService
from app.workflows.store import InMemoryWorkflowStore, WorkflowStorePort


@dataclass(slots=True)
class WorkflowRuntime:
    service: WorkflowEngineService
    store: WorkflowStorePort
    bus: WorkflowEventBus
    runner: WorkflowRunner
    retry_queue: RetryQueue
    monitor: WorkflowMonitor
    executor: ActionExecutor
    coordinator: WorkflowCoordinator
    decision_executor: DecisionExecutor


_runtime: WorkflowRuntime | None = None


async def _seed_if_empty(store: WorkflowStorePort) -> None:
    existing = [w for w in await store.list_workflows(__import__("uuid").uuid4()) if w.shop_id is None]
    if existing:
        return
    for wf in default_workflows():
        await store.save_workflow(wf)


def build_workflow_runtime(
    *,
    store: WorkflowStorePort | None = None,
    seed: bool = True,
) -> WorkflowRuntime:
    resource_store = store or InMemoryWorkflowStore()
    bus = WorkflowEventBus(store=resource_store)
    retry_queue = RetryQueue(resource_store)
    executor = ActionExecutor(emit=bus.publish)
    runner = WorkflowRunner(
        store=resource_store,
        bus=bus,
        retry_queue=retry_queue,
        executor=executor,
    )
    service = WorkflowEngineService(
        store=resource_store,
        bus=bus,
        runner=runner,
        retry_queue=retry_queue,
    )

    # Event-driven fan-out for callers that publish on the bus directly.
    # emit_and_run invokes the runner directly (does not re-publish) to avoid duplicates.
    async def _on_event(event):  # type: ignore[no-untyped-def]
        await runner.handle_event(event)

    bus.subscribe("*", _on_event)

    # Admin Notification Center — observers get emit_and_run + bus.publish events.
    try:
        from app.admin.event_bridge import wire_admin_notification_bridge

        wire_admin_notification_bridge(bus)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("asa.admin.notifications").warning(
            "admin_notification.bridge_wire_failed err=%s", exc
        )

    monitor = WorkflowMonitor()
    decision_executor = DecisionExecutor(monitor=monitor)
    coordinator = WorkflowCoordinator(
        service=service,
        runner=runner,
        monitor=monitor,
        decision_executor=decision_executor,
    )
    # Wire emit/escalate after coordinator exists
    decision_executor._emit = coordinator._emit_for_executor  # noqa: SLF001
    decision_executor._escalate = coordinator._escalate_for_executor  # noqa: SLF001

    # Ensure Plugin Framework reference plugins (CRM) are registered
    from app.plugins.framework.factory import ensure_default_plugins

    ensure_default_plugins()

    rt = WorkflowRuntime(
        service=service,
        store=resource_store,
        bus=bus,
        runner=runner,
        retry_queue=retry_queue,
        monitor=monitor,
        executor=executor,
        coordinator=coordinator,
        decision_executor=decision_executor,
    )

    if seed:
        import asyncio

        try:
            asyncio.get_running_loop()
            # Defer; caller/tests should await ensure_seeded()
            rt.monitor.by_event.setdefault("_seed_pending", 1)
        except RuntimeError:
            asyncio.run(_seed_if_empty(resource_store))

    return rt


async def ensure_seeded(rt: WorkflowRuntime | None = None) -> None:
    runtime = rt or get_workflow_runtime()
    await _seed_if_empty(runtime.store)
    runtime.monitor.by_event.pop("_seed_pending", None)


def get_workflow_runtime() -> WorkflowRuntime:
    global _runtime
    if _runtime is None:
        _runtime = build_workflow_runtime()
    return _runtime


def reset_workflow_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.bus.clear()
    _runtime = None
    try:
        from app.plugins.framework.factory import reset_plugin_runtime

        reset_plugin_runtime()
    except Exception:  # noqa: BLE001
        pass
