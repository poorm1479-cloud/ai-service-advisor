"""Read-only source aggregation for Owner Dashboard / AI Operations Center.

Does not modify Workflow Engine or plugin business logic — only reads
existing registries, stores, and capability outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.dashboard.metrics import safe_int


class DashboardAggregator:
    """Collect live read-only snapshots from registered AutoRepair OS modules."""

    async def collect(self, shop_id: UUID, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        sources: dict[str, Any] = {"collected_at": now.isoformat()}

        sources["plugins"] = await self._plugin_health()
        sources["voice"] = await self._voice_analytics()
        sources["workflow"] = await self._workflow_status(shop_id)
        sources["revenue"] = await self._revenue(shop_id)
        sources["scheduling"] = await self._scheduling(shop_id)
        sources["conversation"] = await self._conversation(shop_id)
        sources["inspection"] = await self._inspection(shop_id)
        sources["inventory"] = await self._inventory(shop_id)
        sources["executive"] = await self._executive(shop_id)
        return sources

    async def _plugin_health(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        try:
            from app.plugins.framework.factory import ensure_default_plugins

            runtime = ensure_default_plugins()
            for plugin_id in (
                "crm",
                "scheduling",
                "conversation",
                "revenue",
                "advisor",
                "inspection",
                "inventory",
                "voice",
                "dashboard",
            ):
                try:
                    plugin = runtime.plugins.lookup(plugin_id)
                    if hasattr(plugin, "health_check"):
                        out[plugin_id] = await plugin.health_check()
                    else:
                        out[plugin_id] = {"status": "healthy", "ok": True}
                except LookupError:
                    continue
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
        return out

    async def _voice_analytics(self) -> dict[str, Any]:
        try:
            from app.plugins.framework.factory import ensure_default_plugins

            plugin = ensure_default_plugins().plugins.lookup("voice")
            if hasattr(plugin, "metrics"):
                return dict(plugin.metrics.snapshot())
            health = await plugin.health_check()
            return dict(health.get("metrics") or health)
        except Exception as exc:  # noqa: BLE001
            # Fall back to legacy voice runtime monitor (read-only)
            try:
                from app.voice.runtime import get_voice_runtime

                return get_voice_runtime().monitor.snapshot()
            except Exception:  # noqa: BLE001
                return {"error": str(exc)}

    async def _workflow_status(self, shop_id: UUID) -> dict[str, Any]:
        """Read workflow history only — no engine mutation."""
        try:
            from app.workflows.enums import RunStatus
            from app.workflows.factory import ensure_seeded, get_workflow_runtime

            rt = get_workflow_runtime()
            await ensure_seeded(rt)
            runs = await rt.store.list_runs(shop_id, limit=50)
            events = await rt.store.list_events(shop_id, limit=50)
            succeeded = sum(1 for r in runs if r.status == RunStatus.COMPLETED)
            failed = sum(1 for r in runs if r.status == RunStatus.FAILED)
            pending = sum(
                1
                for r in runs
                if r.status not in {RunStatus.COMPLETED, RunStatus.FAILED}
            )
            recent = [
                {
                    "id": str(r.id),
                    "name": r.workflow_name,
                    "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                }
                for r in runs[:12]
            ]
            return {
                "engine_status": "healthy",
                "run_count": len(runs),
                "succeeded": succeeded,
                "failed": failed,
                "pending": pending,
                "event_count": len(events),
                "recent_runs": recent,
                "recent_events": [
                    {
                        "type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                        "id": str(getattr(e, "id", "")),
                    }
                    for e in events[:12]
                ],
            }
        except Exception as exc:  # noqa: BLE001
            return {"engine_status": "unknown", "error": str(exc), "run_count": 0}

    async def _revenue(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.framework.capability import Capability
            from app.plugins.framework.context import PluginContext
            from app.plugins.framework.factory import invoke_capability

            result = await invoke_capability(
                Capability.DETECT_REVENUE_OPPORTUNITY.value,
                context=PluginContext.for_shop(shop_id),
                shop_id=shop_id,
                run_analysis=False,
                emit_workflow_events=False,
                limit=20,
            )
            out: dict[str, Any] = {
                "open_opportunities": 0,
                "opportunity_count": 0,
                "items": [],
            }
            if isinstance(result, dict):
                out = {
                    "open_opportunities": safe_int(result.get("count")),
                    "opportunity_count": safe_int(result.get("count")),
                    "items": list(result.get("opportunities") or result.get("items") or [])[:10],
                    "raw_keys": list(result.keys()),
                }
            # Phase 20 retention / campaign metrics (additive)
            try:
                from app.revenue.factory import get_revenue_intelligence_runtime

                metrics = await get_revenue_intelligence_runtime().engine.dashboard_metrics(
                    shop_id
                )
                out.update(metrics)
            except Exception as exc:  # noqa: BLE001
                out["phase20_error"] = str(exc)
            # Phase 21 learning metrics (additive)
            try:
                from app.learning.factory import get_learning_runtime

                learning_metrics = await get_learning_runtime().engine.dashboard_metrics(
                    shop_id
                )
                out["learning"] = learning_metrics
                out.update(
                    {
                        "decision_accuracy": learning_metrics.get("decision_accuracy"),
                        "appointment_conversion_improvement": learning_metrics.get(
                            "appointment_conversion_improvement"
                        ),
                        "repair_approval_rate": learning_metrics.get("repair_approval_rate"),
                        "customer_retention_improvement": learning_metrics.get(
                            "customer_retention_improvement"
                        ),
                        "revenue_impact": learning_metrics.get("revenue_impact"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                out["phase21_error"] = str(exc)
            return out
        except Exception as exc:  # noqa: BLE001
            return {"open_opportunities": 0, "error": str(exc), "items": []}

    async def _scheduling(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.framework.factory import ensure_default_plugins

            plugin = ensure_default_plugins().plugins.lookup("scheduling")
            # Prefer non-mutating health / live snapshot if present
            if hasattr(plugin, "live_snapshot"):
                snap = await plugin.live_snapshot(shop_id)
                if isinstance(snap, dict):
                    return snap
            health = await plugin.health_check()
            return {
                "appointments_today": safe_int(health.get("appointments_today")),
                "status": health.get("status"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"appointments_today": 0, "error": str(exc)}

    async def _conversation(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.framework.factory import ensure_default_plugins

            plugin = ensure_default_plugins().plugins.lookup("conversation")
            health = await plugin.health_check()
            store = getattr(plugin, "store", None) or getattr(plugin, "_store", None)
            open_count = 0
            items: list[dict[str, Any]] = []
            if store is not None and hasattr(store, "search"):
                convos = await store.search(shop_id, limit=20)
                open_count = len(convos) if isinstance(convos, list) else 0
                for c in (convos or [])[:8]:
                    items.append(
                        {
                            "id": str(getattr(c, "id", "")),
                            "channel": getattr(c, "channel", None),
                            "status": getattr(c, "status", None),
                        }
                    )
            return {
                "open_conversations": open_count or safe_int(health.get("conversations")),
                "items": items,
                "status": health.get("status"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"open_conversations": 0, "items": [], "error": str(exc)}

    async def _inspection(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.framework.factory import ensure_default_plugins

            plugin = ensure_default_plugins().plugins.lookup("inspection")
            store = getattr(plugin, "store", None) or getattr(plugin, "_store", None)
            records = store.list_for_shop(shop_id, limit=20) if store else []
            pending_approvals = []
            for rec in records:
                findings = getattr(rec, "findings", None) or []
                if findings:
                    pending_approvals.append(
                        {
                            "id": str(rec.id),
                            "finding_count": len(findings),
                            "status": getattr(rec, "status", None),
                        }
                    )
            return {
                "inspection_count": len(records),
                "pending_approvals": pending_approvals[:10],
            }
        except Exception as exc:  # noqa: BLE001
            return {"inspection_count": 0, "pending_approvals": [], "error": str(exc)}

    async def _inventory(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.plugins.framework.capability import Capability
            from app.plugins.framework.context import PluginContext
            from app.plugins.framework.factory import invoke_capability

            # Readiness check is decide-only analysis — safe for dashboard preview
            out = await invoke_capability(
                Capability.CHECK_REPAIR_READINESS.value,
                context=PluginContext.for_shop(shop_id),
                shop_id=shop_id,
                service_type="oil_change",
            )
            dash = (out or {}).get("dashboard") if isinstance(out, dict) else {}
            return {
                "ready": bool((out or {}).get("ready")) if isinstance(out, dict) else False,
                "missing_count": safe_int((dash or {}).get("missing_count")),
                "estimated_parts_cost": (dash or {}).get("estimated_total")
                or (out or {}).get("estimated_parts_cost"),
            }
        except Exception as exc:  # noqa: BLE001
            try:
                from app.plugins.framework.factory import ensure_default_plugins

                plugin = ensure_default_plugins().plugins.lookup("inventory")
                health = await plugin.health_check()
                return {"catalog_size": health.get("catalog_size"), "status": health.get("status")}
            except Exception:  # noqa: BLE001
                return {"error": str(exc)}

    async def _executive(self, shop_id: UUID) -> dict[str, Any]:
        try:
            from app.executive.factory import get_executive_runtime

            rt = get_executive_runtime()
            snap = await rt.service.get_dashboard(shop_id, force=False)
            return {
                "version": snap.version,
                "live": dict(snap.live or {}),
                "card_count": len(snap.cards),
                "widget_count": len(snap.widgets),
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
