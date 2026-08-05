"""Automatic memory load / capture for the agent pipeline."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.memory.enums import MemoryCategory, MemorySource, MemoryType
from app.memory.indexer import MemoryIndexer
from app.memory.models import MemoryBundle, MemoryQuery, RememberRequest
from app.memory.monitoring import MemoryMonitor
from app.memory.retriever import MemoryRetriever


class MemoryAutoPilot:
    """AI uses memory automatically — load before pipeline, write after stages."""

    def __init__(
        self,
        retriever: MemoryRetriever,
        indexer: MemoryIndexer,
        monitor: MemoryMonitor | None = None,
    ) -> None:
        self._retriever = retriever
        self._indexer = indexer
        self._monitor = monitor or MemoryMonitor()

    def load(
        self,
        shop_id: UUID,
        *,
        text: str | None = None,
        customer_id: UUID | None = None,
        vehicle_id: UUID | None = None,
        limit: int = 12,
    ) -> MemoryBundle:
        bundle = self._retriever.build_bundle(
            MemoryQuery(
                shop_id=shop_id,
                text=text,
                customer_id=customer_id,
                vehicle_id=vehicle_id,
                limit=limit,
            )
        )
        self._monitor.record_auto_load()
        return bundle

    def capture_from_pipeline(
        self,
        *,
        shop_id: UUID,
        customer_id: UUID | None,
        vehicle_id: UUID | None,
        channel: str | None,
        message_text: str | None,
        stages: dict[str, Any],
        escalate: bool = False,
    ) -> list:
        written = []
        source = (
            MemorySource.SMS
            if channel == "sms"
            else MemorySource.VOICE
            if channel == "voice"
            else MemorySource.AGENT_PIPELINE
        )

        # Previous conversation turn
        if message_text:
            written.append(
                self._indexer.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=f"Customer said: {message_text[:500]}",
                        memory_type=MemoryType.CONVERSATION,
                        category=MemoryCategory.PREVIOUS_CONVERSATIONS,
                        customer_id=customer_id,
                        vehicle_id=vehicle_id,
                        importance=0.45,
                        source=source,
                        tags=["conversation", channel or "unknown"],
                        metadata={"channel": channel},
                    )
                )
            )

        intent_stage = stages.get("intent")
        intent_data = intent_stage.data if intent_stage and getattr(intent_stage, "data", None) else None
        if intent_data is not None:
            intent_val = getattr(intent_data, "intent", None)
            intent_name = intent_val.value if hasattr(intent_val, "value") else str(intent_val)
            # Appointment behavior
            if intent_name in {"book_appointment", "reschedule", "cancel_appointment"}:
                written.append(
                    self._indexer.remember(
                        RememberRequest(
                            shop_id=shop_id,
                            content=f"Appointment behavior: customer intent={intent_name}",
                            memory_type=MemoryType.CUSTOMER,
                            category=MemoryCategory.APPOINTMENT_BEHAVIOR,
                            customer_id=customer_id,
                            importance=0.7,
                            source=source,
                            tags=["appointment", intent_name],
                            metadata={"intent": intent_name},
                        )
                    )
                )

        # Vehicle history
        vehicle_stage = stages.get("vehicle")
        vehicle_data = vehicle_stage.data if vehicle_stage and getattr(vehicle_stage, "data", None) else None
        if vehicle_data is not None and getattr(vehicle_data, "vehicle", None):
            v = vehicle_data.vehicle
            label = " ".join(
                str(x)
                for x in (
                    getattr(v, "year", None),
                    getattr(v, "make", None),
                    getattr(v, "model", None),
                )
                if x
            ).strip()
            if label:
                written.append(
                    self._indexer.remember(
                        RememberRequest(
                            shop_id=shop_id,
                            content=f"Vehicle on file: {label}",
                            memory_type=MemoryType.CUSTOMER,
                            category=MemoryCategory.VEHICLE_HISTORY,
                            customer_id=customer_id,
                            vehicle_id=vehicle_id or getattr(v, "id", None),
                            importance=0.75,
                            source=source,
                            tags=["vehicle"],
                            metadata={"vehicle_label": label},
                        )
                    )
                )

        # Declined estimates + repair decision context from revenue stage
        revenue_stage = stages.get("revenue")
        revenue_data = revenue_stage.data if revenue_stage and getattr(revenue_stage, "data", None) else None
        if revenue_data is not None:
            for item in (getattr(revenue_data, "declined_estimates", None) or [])[:5]:
                if isinstance(item, dict):
                    title = item.get("service") or item.get("title") or str(item)
                else:
                    title = str(item)
                written.append(
                    self._indexer.remember(
                        RememberRequest(
                            shop_id=shop_id,
                            content=f"Declined estimate: {title}",
                            memory_type=MemoryType.CUSTOMER,
                            category=MemoryCategory.DECLINED_ESTIMATES,
                            customer_id=customer_id,
                            vehicle_id=vehicle_id,
                            importance=0.85,
                            source=source,
                            tags=["declined", "estimate"],
                        )
                    )
                )
            for item in (getattr(revenue_data, "upsell_opportunities", None) or [])[:3]:
                title = getattr(item, "service", None) or getattr(item, "title", None) or str(item)
                written.append(
                    self._indexer.remember(
                        RememberRequest(
                            shop_id=shop_id,
                            content=f"Repair decision context: {title}",
                            memory_type=MemoryType.SEMANTIC,
                            category=MemoryCategory.REPAIR_DECISIONS,
                            customer_id=customer_id,
                            vehicle_id=vehicle_id,
                            importance=0.55,
                            source=source,
                            tags=["repair"],
                        )
                    )
                )

        # Scheduling outcome → appointment behavior
        sched_stage = stages.get("scheduling")
        sched_data = sched_stage.data if sched_stage and getattr(sched_stage, "data", None) else None
        if sched_data is not None and getattr(sched_data, "success", False):
            action = getattr(sched_data, "action", None)
            action_name = action.value if hasattr(action, "value") else str(action or "scheduled")
            written.append(
                self._indexer.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=f"Completed scheduling action: {action_name}",
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.APPOINTMENT_BEHAVIOR,
                        customer_id=customer_id,
                        importance=0.8,
                        source=source,
                        tags=["appointment", "success"],
                        metadata={"action": action_name},
                    )
                )
            )

        if escalate:
            written.append(
                self._indexer.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content="Conversation required human escalation",
                        memory_type=MemoryType.CONVERSATION,
                        category=MemoryCategory.PREVIOUS_CONVERSATIONS,
                        customer_id=customer_id,
                        importance=0.9,
                        source=source,
                        tags=["escalation"],
                    )
                )
            )

        # Infer communication style from short/long messages
        if message_text:
            style = "concise" if len(message_text) < 40 else "detailed"
            written.append(
                self._indexer.remember(
                    RememberRequest(
                        shop_id=shop_id,
                        content=f"Prefers {style} replies based on message length",
                        memory_type=MemoryType.CUSTOMER,
                        category=MemoryCategory.COMMUNICATION_STYLE,
                        customer_id=customer_id,
                        importance=0.4,
                        source=source,
                        tags=["style", style],
                        metadata={"style": {"tone": style, "formality": "casual"}},
                    )
                )
            )

        self._monitor.record_auto_write(len(written))
        return written
