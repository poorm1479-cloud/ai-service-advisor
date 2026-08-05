"""Built-in workflow actions + compensation (rollback) handlers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable
from uuid import UUID, uuid4

from app.workflows.enums import ActionType, DomainEventType
from app.workflows.models import DomainEvent, WorkflowAction

ActionResult = dict[str, Any]
EmitFn = Callable[[DomainEvent], Awaitable[None]]


class ActionExecutor:
    """Executes actions and records compensation data for rollback."""

    def __init__(self, *, emit: EmitFn | None = None) -> None:
        self._emit = emit
        self._side_effects: dict[str, list[dict[str, Any]]] = {
            "reminders": [],
            "crm": [],
            "revenue": [],
            "dashboard": [],
            "notifications": [],
        }

    @property
    def side_effects(self) -> dict[str, list[dict[str, Any]]]:
        return self._side_effects

    async def execute(
        self,
        action: WorkflowAction,
        *,
        shop_id: UUID,
        payload: dict[str, Any],
        context: dict[str, Any],
        correlation_id: str,
    ) -> ActionResult:
        handlers = {
            ActionType.SCHEDULE_REMINDER: self._schedule_reminder,
            ActionType.UPDATE_CRM: self._update_crm,
            ActionType.UPDATE_REVENUE: self._update_revenue,
            ActionType.UPDATE_DASHBOARD: self._update_dashboard,
            ActionType.EMIT_EVENT: self._emit_event,
            ActionType.LOG: self._log,
            ActionType.NOTIFY: self._notify,
            ActionType.DELAY: self._delay,
            ActionType.SET_CONTEXT: self._set_context,
        }
        handler = handlers.get(action.type)
        if handler is None:
            raise ValueError(f"Unknown action type: {action.type}")
        return await handler(
            action,
            shop_id=shop_id,
            payload=payload,
            context=context,
            correlation_id=correlation_id,
        )

    async def compensate(
        self,
        action: WorkflowAction,
        step_output: dict[str, Any],
        *,
        shop_id: UUID,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Best-effort undo for a succeeded step."""
        compensate_type = action.compensate.get("type") or f"undo_{action.type.value}"
        record_id = step_output.get("record_id")
        result = {"compensated": True, "type": compensate_type, "record_id": record_id}

        if action.type == ActionType.SCHEDULE_REMINDER and record_id:
            self._side_effects["reminders"] = [
                r for r in self._side_effects["reminders"] if r.get("id") != record_id
            ]
            result["message"] = "Reminder cancelled"
        elif action.type == ActionType.UPDATE_CRM and record_id:
            self._side_effects["crm"] = [r for r in self._side_effects["crm"] if r.get("id") != record_id]
            result["message"] = "CRM update reversed"
        elif action.type == ActionType.UPDATE_REVENUE and record_id:
            self._side_effects["revenue"] = [
                r for r in self._side_effects["revenue"] if r.get("id") != record_id
            ]
            result["message"] = "Revenue update reversed"
        elif action.type == ActionType.UPDATE_DASHBOARD and record_id:
            self._side_effects["dashboard"] = [
                r for r in self._side_effects["dashboard"] if r.get("id") != record_id
            ]
            result["message"] = "Dashboard update reversed"
        elif action.type == ActionType.NOTIFY and record_id:
            self._side_effects["notifications"] = [
                r for r in self._side_effects["notifications"] if r.get("id") != record_id
            ]
            result["message"] = "Notification retracted"
        else:
            result["message"] = "No-op compensation"

        if self._emit and action.compensate.get("emit"):
            await self._emit(
                DomainEvent(
                    event_type=DomainEventType(action.compensate["emit"]),
                    shop_id=shop_id,
                    payload={"compensation": result, "action": action.type.value},
                    correlation_id=correlation_id,
                    source="workflow.rollback",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return result

    async def _schedule_reminder(self, action, *, shop_id, payload, context, correlation_id):
        hours = int(action.config.get("hours_before", 24))
        record = {
            "id": str(uuid4()),
            "shop_id": str(shop_id),
            "appointment_id": payload.get("appointment_id"),
            "customer_id": payload.get("customer_id"),
            "channel": action.config.get("channel", "sms"),
            "scheduled_for": (
                datetime.now(timezone.utc) + timedelta(hours=max(hours, 0) * -1)
                if hours < 0
                else datetime.now(timezone.utc) + timedelta(hours=hours)
            ).isoformat(),
            "template": action.config.get("template", "appointment_reminder"),
        }
        self._side_effects["reminders"].append(record)
        context.setdefault("reminders", []).append(record["id"])
        if self._emit:
            await self._emit(
                DomainEvent(
                    event_type=DomainEventType.REMINDER_SCHEDULED,
                    shop_id=shop_id,
                    payload=record,
                    correlation_id=correlation_id,
                    source="workflow.action",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return {"record_id": record["id"], "reminder": record}

    async def _update_crm(self, action, *, shop_id, payload, context, correlation_id):
        record = {
            "id": str(uuid4()),
            "shop_id": str(shop_id),
            "customer_id": payload.get("customer_id"),
            "note": action.config.get("note", "Workflow CRM update"),
            "fields": action.config.get("fields", {}),
            "trigger": payload,
        }
        self._side_effects["crm"].append(record)
        context["crm_updated"] = True

        # Route CRM mutation through Capability Registry (no direct plugin refs)
        customer_id = payload.get("customer_id")
        if customer_id:
            try:
                from uuid import UUID as _UUID

                from app.plugins.framework.capability import Capability
                from app.plugins.framework.context import PluginContext
                from app.plugins.framework.factory import invoke_capability

                cid = customer_id if isinstance(customer_id, _UUID) else _UUID(str(customer_id))
                await invoke_capability(
                    Capability.ADD_TIMELINE.value,
                    context=PluginContext.for_shop(shop_id, customer_id=cid),
                    shop_id=shop_id,
                    customer_id=cid,
                    kind="workflow",
                    summary=record["note"],
                )
            except Exception:  # noqa: BLE001 — keep workflow cascade resilient
                pass

        if self._emit:
            await self._emit(
                DomainEvent(
                    event_type=DomainEventType.CRM_UPDATED,
                    shop_id=shop_id,
                    payload=record,
                    correlation_id=correlation_id,
                    source="workflow.action",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return {"record_id": record["id"], "crm": record}

    async def _update_revenue(self, action, *, shop_id, payload, context, correlation_id):
        amount = payload.get("estimated_revenue") or action.config.get("amount") or 0
        record = {
            "id": str(uuid4()),
            "shop_id": str(shop_id),
            "amount": str(amount),
            "category": action.config.get("category", "appointment"),
            "reference_id": payload.get("appointment_id") or payload.get("invoice_id"),
        }
        self._side_effects["revenue"].append(record)
        context["revenue_updated"] = True

        # Refresh opportunities via Capability Registry (no direct revenue_intel)
        try:
            from app.plugins.framework.capability import Capability
            from app.plugins.framework.context import PluginContext
            from app.plugins.framework.factory import invoke_capability

            await invoke_capability(
                Capability.DETECT_REVENUE_OPPORTUNITY.value,
                context=PluginContext.for_shop(shop_id),
                shop_id=shop_id,
                run_analysis=True,
                emit_workflow_events=True,
                limit=25,
            )
        except Exception:  # noqa: BLE001 — keep cascade resilient
            pass

        if self._emit:
            await self._emit(
                DomainEvent(
                    event_type=DomainEventType.REVENUE_UPDATED,
                    shop_id=shop_id,
                    payload=record,
                    correlation_id=correlation_id,
                    source="workflow.action",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return {"record_id": record["id"], "revenue": record}

    async def _update_dashboard(self, action, *, shop_id, payload, context, correlation_id):
        record = {
            "id": str(uuid4()),
            "shop_id": str(shop_id),
            "widget": action.config.get("widget", "overview"),
            "invalidate": action.config.get("invalidate", ["appointments", "revenue"]),
        }
        self._side_effects["dashboard"].append(record)
        context["dashboard_updated"] = True
        if self._emit:
            await self._emit(
                DomainEvent(
                    event_type=DomainEventType.DASHBOARD_UPDATED,
                    shop_id=shop_id,
                    payload=record,
                    correlation_id=correlation_id,
                    source="workflow.action",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return {"record_id": record["id"], "dashboard": record}

    async def _emit_event(self, action, *, shop_id, payload, context, correlation_id):
        event_type = DomainEventType(action.config["event_type"])
        body = {**payload, **(action.config.get("payload") or {})}
        if self._emit:
            await self._emit(
                DomainEvent(
                    event_type=event_type,
                    shop_id=shop_id,
                    payload=body,
                    correlation_id=correlation_id,
                    source="workflow.action",
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        return {"emitted": event_type.value}

    async def _log(self, action, *, shop_id, payload, context, correlation_id):
        message = action.config.get("message") or action.name or "workflow log"
        return {"logged": True, "message": message}

    async def _notify(self, action, *, shop_id, payload, context, correlation_id):
        record = {
            "id": str(uuid4()),
            "channel": action.config.get("channel", "in_app"),
            "message": action.config.get("message", "Workflow notification"),
            "to": action.config.get("to") or payload.get("customer_id"),
        }
        self._side_effects["notifications"].append(record)
        return {"record_id": record["id"], "notification": record}

    async def _delay(self, action, *, shop_id, payload, context, correlation_id):
        # Non-blocking marker — real delay is handled by retry queue scheduling.
        return {"delayed_ms": int(action.config.get("ms", 0))}

    async def _set_context(self, action, *, shop_id, payload, context, correlation_id):
        for k, v in (action.config.get("values") or {}).items():
            context[k] = v
        return {"context_keys": list((action.config.get("values") or {}).keys())}
