"""Retrieve relevant long-term memories for AI context."""

from __future__ import annotations

from datetime import datetime, timezone

from app.memory.embeddings import cosine, embed, lexical_overlap
from app.memory.enums import MemoryCategory, MemoryType
from app.memory.models import MemoryBundle, MemoryHit, MemoryQuery
from app.memory.monitoring import MemoryMonitor
from app.memory.store import MemoryStorePort


class MemoryRetriever:
    def __init__(self, store: MemoryStorePort, monitor: MemoryMonitor | None = None) -> None:
        self._store = store
        self._monitor = monitor or MemoryMonitor()

    def retrieve(self, query: MemoryQuery) -> list[MemoryHit]:
        candidates = self._store.all_for_shop(query.shop_id)
        filtered: list = []
        for rec in candidates:
            if query.customer_id and rec.customer_id and rec.customer_id != query.customer_id:
                # Keep business-scoped and unmatched-customer semantic facts
                if rec.memory_type != MemoryType.BUSINESS and rec.customer_id != query.customer_id:
                    continue
            if query.customer_id and rec.customer_id is None and rec.memory_type == MemoryType.CUSTOMER:
                continue
            if query.vehicle_id and rec.vehicle_id and rec.vehicle_id != query.vehicle_id:
                continue
            if query.memory_types and rec.memory_type not in query.memory_types:
                continue
            if query.categories and rec.category not in query.categories:
                continue
            filtered.append(rec)

        q_vec = embed(query.text or "") if query.text else None
        hits: list[MemoryHit] = []
        for rec in filtered:
            score = rec.importance * 0.35
            if query.customer_id and rec.customer_id == query.customer_id:
                score += 0.25
            if query.vehicle_id and rec.vehicle_id == query.vehicle_id:
                score += 0.15
            if q_vec and rec.embedding:
                score += cosine(q_vec, rec.embedding) * 0.5
            if query.text:
                score += lexical_overlap(query.text, rec.content) * 0.35
                if rec.summary:
                    score += lexical_overlap(query.text, rec.summary) * 0.15
            # Recency boost
            if rec.updated_at:
                age_hours = max(
                    0.0,
                    (datetime.now(timezone.utc) - rec.updated_at).total_seconds() / 3600.0,
                )
                score += max(0.0, 0.1 - age_hours / 2400.0)
            if score < query.min_score:
                continue
            hits.append(MemoryHit(record=rec, score=score, reason="semantic+filters"))

        hits.sort(key=lambda h: h.score, reverse=True)
        top = hits[: query.limit]
        for h in top:
            self._store.touch(query.shop_id, h.record.id)
        self._monitor.record_retrieve(len(top))
        return top

    def build_bundle(self, query: MemoryQuery) -> MemoryBundle:
        hits = self.retrieve(query)
        by_category: dict[str, list[str]] = {}
        preferences: dict = {}
        style: dict = {}
        for h in hits:
            cat = h.record.category.value
            by_category.setdefault(cat, []).append(h.record.content)
            if h.record.category == MemoryCategory.CUSTOMER_PREFERENCES:
                preferences.update(h.record.metadata.get("prefs", {}))
                preferences.setdefault("notes", []).append(h.record.content)
            if h.record.category == MemoryCategory.COMMUNICATION_STYLE:
                style.update(h.record.metadata.get("style", {}))
                style.setdefault("notes", []).append(h.record.content)

        prompt = self._as_prompt(hits, preferences=preferences, style=style)
        return MemoryBundle(
            shop_id=query.shop_id,
            customer_id=query.customer_id,
            vehicle_id=query.vehicle_id,
            hits=hits,
            by_category=by_category,
            preferences=preferences,
            communication_style=style,
            prompt=prompt,
        )

    def _as_prompt(
        self,
        hits: list[MemoryHit],
        *,
        preferences: dict,
        style: dict,
    ) -> str:
        if not hits and not preferences and not style:
            return ""
        lines = ["## Long-term customer memory (use automatically)"]
        if style:
            tone = style.get("tone") or style.get("formality") or "neutral"
            lines.append(f"- Communication style: {tone}")
            for note in (style.get("notes") or [])[:3]:
                lines.append(f"  · {note}")
        if preferences:
            for note in (preferences.get("notes") or [])[:5]:
                lines.append(f"- Preference: {note}")
        grouped: dict[str, list[MemoryHit]] = {}
        for h in hits:
            grouped.setdefault(h.record.category.value, []).append(h)
        for cat, items in grouped.items():
            if cat in (
                MemoryCategory.CUSTOMER_PREFERENCES.value,
                MemoryCategory.COMMUNICATION_STYLE.value,
            ):
                continue
            lines.append(f"- {cat.replace('_', ' ').title()}:")
            for h in items[:4]:
                lines.append(f"  · {h.record.content}")
        return "\n".join(lines)
