"""Admin console aggregations — reuses billing, quotas, incidents, monitors, enterprise."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update

from app.enterprise.factory import get_enterprise_runtime
from app.infrastructure.config import settings
from app.infrastructure.database import SessionLocal
from app.domain.enums import UserRole
from app.infrastructure.models import (
    RefreshTokenModel,
    ShopMembershipModel,
    SmsConversationModel,
    SmsMessageModel,
    UserModel,
    VoiceCallModel,
)
from app.ops.healthchecks import readiness
from app.saas.access_review import AccessReviewService
from app.saas.billing import BillingService, BillingServicePort, SaasPlanModel, ShopSubscriptionModel
from app.saas.incidents import StatusIncidentService
from app.saas.quotas import ShopUsageCounterModel, _period_ym
from app.sms.enums import SmsConversationStatus, SmsMessageDirection
from app.sms.runtime import get_sms_runtime
from app.voice.enums import VoiceCallStatus
from app.voice.runtime import get_voice_runtime


class AdminConsoleService:
    def __init__(self, billing: BillingServicePort | None = None) -> None:
        self._billing: BillingServicePort = billing or BillingService()
        self._incidents = StatusIncidentService()
        self._access = AccessReviewService()

    async def dashboard(self) -> dict:
        ready = await readiness()
        shops = await self._billing.list_shops_summary()
        plans = await self._billing.list_plans()
        usage = await self._usage_rollup()
        users = await self._user_counts()
        payments = await self._payments_summary()
        incidents = await self._incidents.list_public(limit=20)
        open_incidents = [i for i in incidents if i.status != "resolved"]
        sms = await self._sms_snapshot()
        voice = await self._voice_snapshot()
        by_status: dict[str, int] = {}
        for s in shops:
            key = str(s.get("status") or "none")
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": ready.get("environment"),
            "system": ready,
            "shops": {
                "total": len(shops),
                "by_status": by_status,
                "suspended": by_status.get("suspended", 0),
                "items": shops[:25],
            },
            "users": users,
            "plans": {
                "total": len(plans),
                "items": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "price_cents_monthly": p.price_cents_monthly,
                        "ai_calls_monthly": p.ai_calls_monthly,
                        "sms_monthly": p.sms_monthly,
                        "seats": p.seats,
                    }
                    for p in plans
                ],
            },
            "payments": payments,
            "tokens": usage,
            "sms": sms,
            "voice": voice,
            "incidents": {"open": len(open_incidents), "total": len(incidents)},
        }

    async def organizations(self) -> dict:
        shops = await self._billing.list_shops_summary()
        usage_by_shop = await self._usage_by_shop()
        user_by_shop = await self._users_by_shop()
        owners = await self._owners_by_shop()
        active_logins = await self._active_logins_by_shop()
        last_activity = await self._last_activity_by_shop()
        enterprise = get_enterprise_runtime().service.list_orgs()
        org_rows = []
        for s in shops:
            sid = s["shop_id"]
            u = usage_by_shop.get(sid, {})
            owner = owners.get(sid) or {}
            sessions = active_logins.get(sid) or []
            joined = bool(sessions)
            # Joined by = users with a recent live session (login/refresh within access TTL).
            names = [row["full_name"] for row in sessions if row.get("full_name")]
            roles = list(
                dict.fromkeys(row["role"] for row in sessions if row.get("role"))
            )
            activity = last_activity.get(sid) or s.get("created_at")
            org_rows.append(
                {
                    **s,
                    "owner_name": owner.get("full_name"),
                    "owner_email": owner.get("email"),
                    "owner_phone": owner.get("phone"),
                    "joined": joined,
                    "joined_by": ", ".join(names) if names else None,
                    "joined_by_role": ", ".join(roles) if roles else None,
                    "joined_at": sessions[0].get("joined_at") if sessions else None,
                    "last_activity_at": activity,
                    "users": user_by_shop.get(sid, 0),
                    "ai_calls": u.get("ai_calls", 0),
                    "sms_usage": u.get("sms", 0),
                }
            )
        # Online tenants first for ops visibility.
        org_rows.sort(
            key=lambda r: (
                not bool(r.get("joined")),
                (r.get("shop_name") or "").lower(),
            )
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "shops": org_rows,
            "enterprise_orgs": [
                {
                    "id": str(o.id),
                    "name": o.name,
                    "slug": o.slug,
                    "franchise": o.franchise,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in enterprise
            ],
        }

    async def organization_detail(self, shop_id: str) -> dict | None:
        shops = await self.organizations()
        for row in shops.get("shops", []):
            if row.get("shop_id") == shop_id:
                members = await self._members_for_shop(shop_id)
                usage = await self.organization_usage(shop_id)
                plans = await self._billing.list_plans()
                return {
                    "generated_at": shops.get("generated_at"),
                    "shop": row,
                    "members": members,
                    "usage": usage,
                    "plans": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "price_cents_monthly": p.price_cents_monthly,
                            "ai_calls_monthly": p.ai_calls_monthly,
                            "sms_monthly": p.sms_monthly,
                            "seats": p.seats,
                        }
                        for p in plans
                    ],
                }
        return None

    async def organization_usage(self, shop_id: str) -> dict:
        from app.saas.usage_tracking import UsageTrackingService

        try:
            shop_uuid = UUID(shop_id)
        except ValueError as exc:
            from app.domain.exceptions import NotFoundError

            raise NotFoundError("Shop not found") from exc

        period = _period_ym()
        by_shop = await self._usage_by_shop()
        quota = by_shop.get(shop_id, {})
        monitored = await UsageTrackingService().get_usage(shop_uuid, period=period)
        return {
            "period": period,
            "shop_id": shop_id,
            "ai_calls": int(quota.get("ai_calls", 0)),
            "sms": int(quota.get("sms", 0)),
            "ai_requests": monitored["ai_requests"],
            "input_tokens": monitored["input_tokens"],
            "output_tokens": monitored["output_tokens"],
            "sms_count": monitored["sms_count"],
            "voice_seconds": monitored["voice_seconds"],
            "voice_minutes": monitored["voice_minutes"],
            "estimated_cost_usd": monitored["estimated_cost_usd"],
        }

    async def change_organization_plan(self, shop_id: str, plan_id: str) -> dict:
        from app.domain.exceptions import NotFoundError, ValidationError

        plan_id = (plan_id or "").strip()
        if not plan_id:
            raise ValidationError("plan_id is required")
        detail = await self.organization_detail(shop_id)
        if detail is None:
            raise NotFoundError("Shop not found")
        try:
            shop_uuid = UUID(shop_id)
        except ValueError as exc:
            raise NotFoundError("Shop not found") from exc
        return await self._billing.admin_set_plan(shop_uuid, plan_id)

    async def set_member_active(self, shop_id: str, user_id: str, *, is_active: bool) -> dict:
        from app.domain.exceptions import NotFoundError, ValidationError

        try:
            shop_uuid = UUID(shop_id)
            user_uuid = UUID(user_id)
        except ValueError as exc:
            raise NotFoundError("Member not found") from exc

        async with SessionLocal() as session:
            membership = await session.scalar(
                select(ShopMembershipModel).where(
                    ShopMembershipModel.shop_id == shop_uuid,
                    ShopMembershipModel.user_id == user_uuid,
                )
            )
            if membership is None:
                raise NotFoundError("Member not found")
            user = await session.get(UserModel, user_uuid)
            if user is None:
                raise NotFoundError("Member not found")
            if (user.account_type or "").strip().lower() == "platform_admin":
                raise ValidationError("Cannot change platform admin account status here")
            user.is_active = bool(is_active)
            await session.commit()
            return {
                "ok": True,
                "shop_id": shop_id,
                "user_id": user_id,
                "is_active": bool(user.is_active),
            }

    async def request_member_password_reset(self, shop_id: str, user_id: str) -> dict:
        from app.domain.exceptions import NotFoundError, ValidationError
        from app.saas.password_reset import PasswordResetService

        try:
            shop_uuid = UUID(shop_id)
            user_uuid = UUID(user_id)
        except ValueError as exc:
            raise NotFoundError("Member not found") from exc

        async with SessionLocal() as session:
            membership = await session.scalar(
                select(ShopMembershipModel).where(
                    ShopMembershipModel.shop_id == shop_uuid,
                    ShopMembershipModel.user_id == user_uuid,
                )
            )
            if membership is None:
                raise NotFoundError("Member not found")
            user = await session.get(UserModel, user_uuid)
            if user is None or not user.is_active:
                raise NotFoundError("Member not found")
            email = user.email
            phone = user.phone

        if not email and not phone:
            raise ValidationError("Member has no email or phone for password reset")

        result = await PasswordResetService().request_reset(email=email, phone=None if email else phone)
        return {
            "ok": True,
            "shop_id": shop_id,
            "user_id": user_id,
            "channel": "email" if email else "phone",
            "dev_token": result.get("dev_token"),
        }

    async def initialize_member_password(
        self,
        shop_id: str,
        user_id: str,
        *,
        new_password: str | None = None,
    ) -> dict:
        """Set a temporary password for a shop member. Returns plaintext once."""
        import secrets
        import string

        from app.domain.exceptions import NotFoundError, ValidationError
        from app.infrastructure.security import hash_password

        try:
            shop_uuid = UUID(shop_id)
            user_uuid = UUID(user_id)
        except ValueError as exc:
            raise NotFoundError("Member not found") from exc

        password = (new_password or "").strip()
        if password:
            if len(password) < 8:
                raise ValidationError("Password must be at least 8 characters")
            if len(password) > 128:
                raise ValidationError("Password must be at most 128 characters")
        else:
            alphabet = string.ascii_letters + string.digits
            password = "".join(secrets.choice(alphabet) for _ in range(12))

        async with SessionLocal() as session:
            membership = await session.scalar(
                select(ShopMembershipModel).where(
                    ShopMembershipModel.shop_id == shop_uuid,
                    ShopMembershipModel.user_id == user_uuid,
                )
            )
            if membership is None:
                raise NotFoundError("Member not found")
            user = await session.get(UserModel, user_uuid)
            if user is None:
                raise NotFoundError("Member not found")
            if (user.account_type or "").strip().lower() == "platform_admin":
                raise ValidationError("Cannot initialize platform admin password here")
            if not user.is_active:
                raise ValidationError("Cannot initialize password for inactive member")

            user.password_hash = hash_password(password)
            now = datetime.now(timezone.utc)
            await session.execute(
                update(RefreshTokenModel)
                .where(
                    RefreshTokenModel.user_id == user_uuid,
                    RefreshTokenModel.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await session.commit()

        return {
            "ok": True,
            "shop_id": shop_id,
            "user_id": user_id,
            "temporary_password": password,
        }

    async def billing_monitor(self) -> dict:
        return await self._billing.admin_monitor()

    async def token_usage(self) -> dict:
        from app.saas.usage_tracking import UsageTrackingService

        period = _period_ym()
        shops = await self._billing.list_shops_summary()
        by_shop = await self._usage_by_shop()
        tracker = UsageTrackingService()
        items = []
        totals = {
            "ai_calls": 0,
            "sms": 0,
            "ai_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "sms_count": 0,
            "voice_seconds": 0,
            "estimated_cost_micros": 0,
        }
        for s in shops:
            sid = s["shop_id"]
            u = by_shop.get(sid, {})
            ai = int(u.get("ai_calls", 0))
            sms = int(u.get("sms", 0))
            monitored = await tracker.get_usage(UUID(sid), period=period)
            totals["ai_calls"] += ai
            totals["sms"] += sms
            totals["ai_requests"] += monitored["ai_requests"]
            totals["input_tokens"] += monitored["input_tokens"]
            totals["output_tokens"] += monitored["output_tokens"]
            totals["sms_count"] += monitored["sms_count"]
            totals["voice_seconds"] += monitored["voice_seconds"]
            totals["estimated_cost_micros"] += monitored["estimated_cost_micros"]
            items.append(
                {
                    "shop_id": sid,
                    "shop_name": s["shop_name"],
                    "shop_slug": s["shop_slug"],
                    "plan_id": s["plan_id"],
                    "plan_name": s["plan_name"],
                    "status": s["status"],
                    "ai_calls": ai,
                    "sms": sms,
                    "ai_requests": monitored["ai_requests"],
                    "input_tokens": monitored["input_tokens"],
                    "output_tokens": monitored["output_tokens"],
                    "sms_count": monitored["sms_count"],
                    "voice_minutes": monitored["voice_minutes"],
                    "estimated_cost_usd": monitored["estimated_cost_usd"],
                }
            )
        items.sort(key=lambda r: r["ai_requests"] or r["ai_calls"], reverse=True)
        sms_monitor = await self._sms_snapshot()
        voice_monitor = await self._voice_snapshot()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": period,
            "totals": {
                **totals,
                "voice_minutes": round(totals["voice_seconds"] / 60.0, 2),
                "estimated_cost_usd": round(totals["estimated_cost_micros"] / 1_000_000.0, 6),
            },
            "shops": items,
            "sms_runtime": sms_monitor,
            "voice_runtime": voice_monitor,
        }

    async def users(self) -> dict:
        review = await self._access.export()
        active_logins = await self._active_logins_by_shop()
        online_keys: set[tuple[str, str]] = set()
        for sid, sessions in active_logins.items():
            for row in sessions:
                uid = row.get("user_id")
                if uid:
                    online_keys.add((sid, str(uid)))

        entries: list[dict] = []
        for entry in review.get("entries", []) or []:
            sid = str(entry.get("shop_id") or "")
            uid = str(entry.get("user_id") or "")
            entries.append({**entry, "online": (sid, uid) in online_keys})

        # Online members first for ops visibility.
        entries.sort(
            key=lambda e: (
                not bool(e.get("online")),
                (e.get("shop_name") or "").lower(),
                (e.get("full_name") or "").lower(),
            )
        )
        return {
            "generated_at": review.get("generated_at"),
            "total": review.get("entry_count", 0),
            "users": entries,
        }

    async def system_status(self) -> dict:
        ready = await readiness()
        incidents = await self._incidents.list_public(limit=30)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "readiness": ready,
            "sms": await self._sms_snapshot(),
            "voice": await self._voice_snapshot(),
            "incidents": [
                {
                    "id": str(i.id),
                    "title": i.title,
                    "summary": i.summary,
                    "severity": i.severity,
                    "status": i.status,
                    "affected_components": i.affected_components,
                    "started_at": i.started_at.isoformat() if i.started_at else None,
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                }
                for i in incidents
            ],
        }

    async def notification_feed(
        self,
        *,
        limit: int = 200,
        event_type: str | None = None,
        unread_only: bool = False,
    ) -> dict:
        """Admin Notification Center — durable store first, plus live SMS/voice context."""
        from app.admin.notifications import AdminNotificationService

        store = AdminNotificationService()
        stored: list[dict] = []
        counts: dict = {"total": 0, "unread": 0, "by_event_type": {}}
        try:
            rows = await store.list(
                limit=limit,
                event_type=event_type,
                unread_only=unread_only,
            )
            stored = [r.to_feed_item() for r in rows]
            counts = await store.counts()
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger("asa.admin.notifications").warning(
                "admin_notification.feed_read_failed err=%s", exc
            )
            stored = []

        sms = await self._sms_snapshot()
        voice = await self._voice_snapshot()

        # When filtering the durable center, skip legacy aggregate noise.
        items = list(stored)
        if not event_type and not unread_only:
            if sms.get("last_event_at"):
                items.append(
                    {
                        "id": f"sms:{sms['last_event_at']}",
                        "event_type": "runtime.sms",
                        "source": "sms",
                        "severity": "info",
                        "title": "SMS activity",
                        "message": (
                            f"inbound={sms.get('inbound_received', 0)} "
                            f"outbound={sms.get('outbound_sent', 0)} "
                            f"escalations={sms.get('escalations', 0)}"
                        ),
                        "shop_id": None,
                        "shop_slug": None,
                        "payload": {},
                        "status": "active",
                        "occurred_at": sms["last_event_at"],
                        "read_at": None,
                    }
                )
            if voice.get("last_event_at"):
                items.append(
                    {
                        "id": f"voice:{voice['last_event_at']}",
                        "event_type": "runtime.voice",
                        "source": "voice",
                        "severity": "info",
                        "title": "Voice activity",
                        "message": (
                            f"started={voice.get('calls_started', 0)} "
                            f"completed={voice.get('calls_completed', 0)} "
                            f"live={voice.get('live_calls', 0)}"
                        ),
                        "shop_id": None,
                        "shop_slug": None,
                        "payload": {},
                        "status": "active",
                        "occurred_at": voice["last_event_at"],
                        "read_at": None,
                    }
                )

        items.sort(key=lambda x: x.get("occurred_at") or "", reverse=True)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notifications": items[:limit],
            "counts": counts,
            "event_types": [
                "saas.signup",
                "saas.member_joined",
                "saas.shop_deleted",
                "billing.payment_succeeded",
                "billing.payment_failed",
                "billing.quota_warning",
                "system.error",
            ],
            "sms": sms,
            "voice": voice,
        }

    async def mark_notification_read(self, notification_id: UUID) -> dict | None:
        from app.admin.notifications import AdminNotificationService

        row = await AdminNotificationService().mark_read(notification_id)
        return row.to_feed_item() if row else None

    async def delete_notification(self, notification_id: UUID) -> bool:
        from app.admin.notifications import AdminNotificationService

        return await AdminNotificationService().delete(notification_id)

    async def delete_notifications(self, notification_ids: list[UUID]) -> dict:
        from app.admin.notifications import AdminNotificationService

        deleted = await AdminNotificationService().delete_many(notification_ids)
        return {"deleted": deleted}

    async def mark_all_notifications_read(self) -> dict:
        from app.admin.notifications import AdminNotificationService

        updated = await AdminNotificationService().mark_all_read()
        return {"updated": updated}

    def notification_fingerprint(self, feed: dict) -> str:
        ids = [n.get("id", "") for n in feed.get("notifications", [])[:200]]
        counts = feed.get("counts") or {}
        sms = feed.get("sms") or {}
        voice = feed.get("voice") or {}
        return "|".join(
            [
                *ids,
                str(counts.get("total", 0)),
                str(counts.get("unread", 0)),
                str(sms.get("inbound_received", 0)),
                str(sms.get("outbound_sent", 0)),
                str(voice.get("calls_started", 0)),
                str(voice.get("live_calls", 0)),
            ]
        )

    def dashboard_fingerprint(self, data: dict) -> str:
        """Stable KPI fingerprint — ignore generated_at and shop item churn noise."""
        shops = data.get("shops") or {}
        users = data.get("users") or {}
        payments = data.get("payments") or {}
        tokens = data.get("tokens") or {}
        sms = data.get("sms") or {}
        voice = data.get("voice") or {}
        incidents = data.get("incidents") or {}
        system = data.get("system") or {}
        by_status = shops.get("by_status") or {}
        status_part = ",".join(f"{k}:{by_status[k]}" for k in sorted(by_status))
        return "|".join(
            [
                str(data.get("environment") or ""),
                str(system.get("status") or ""),
                str(shops.get("total", 0)),
                str(shops.get("suspended", 0)),
                status_part,
                str(users.get("total", 0)),
                str(users.get("active", 0)),
                str(users.get("memberships", 0)),
                str(payments.get("mrr_cents", 0)),
                str(payments.get("with_stripe", 0)),
                str(tokens.get("ai_calls", 0)),
                str(tokens.get("period") or ""),
                str(sms.get("inbound_received", 0)),
                str(sms.get("outbound_sent", 0)),
                str(voice.get("calls_started", 0)),
                str(voice.get("live_calls", 0)),
                str(incidents.get("open", 0)),
                str(incidents.get("total", 0)),
                str((data.get("plans") or {}).get("total", 0)),
            ]
        )

    def resource_fingerprint(self, data: dict) -> str:
        """Stable hash for SSE — ignore generated_at clock noise."""
        cleaned = {k: v for k, v in data.items() if k != "generated_at"}
        raw = json.dumps(cleaned, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _sms_snapshot(self) -> dict:
        """Durable SMS counts from PostgreSQL; keep process-local ops counters from monitor."""
        monitor = get_sms_runtime().monitor.snapshot()
        async with SessionLocal() as session:
            inbound = await session.scalar(
                select(func.count())
                .select_from(SmsMessageModel)
                .where(SmsMessageModel.direction == SmsMessageDirection.INBOUND.value)
            )
            outbound = await session.scalar(
                select(func.count())
                .select_from(SmsMessageModel)
                .where(SmsMessageModel.direction == SmsMessageDirection.OUTBOUND.value)
            )
            escalations = await session.scalar(
                select(func.count())
                .select_from(SmsConversationModel)
                .where(SmsConversationModel.escalate.is_(True))
            )
            active = await session.scalar(
                select(func.count())
                .select_from(SmsConversationModel)
                .where(SmsConversationModel.status == SmsConversationStatus.ACTIVE.value)
            )
            last_at = await session.scalar(select(func.max(SmsMessageModel.created_at)))
        return {
            **monitor,
            "inbound_received": int(inbound or 0),
            "outbound_sent": int(outbound or 0),
            "escalations": int(escalations or 0),
            "conversations_active": int(active or 0),
            "last_event_at": last_at.isoformat() if last_at else monitor.get("last_event_at"),
            "source": "database",
        }

    async def _voice_snapshot(self) -> dict:
        """Durable voice counts from PostgreSQL; keep process-local ops counters from monitor."""
        monitor = get_voice_runtime().monitor.snapshot()
        live_statuses = (
            VoiceCallStatus.RINGING.value,
            VoiceCallStatus.IN_PROGRESS.value,
            VoiceCallStatus.ESCALATED.value,
        )
        async with SessionLocal() as session:
            started = await session.scalar(select(func.count()).select_from(VoiceCallModel))
            completed = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(VoiceCallModel.status == VoiceCallStatus.COMPLETED.value)
            )
            escalations = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(VoiceCallModel.escalate.is_(True))
            )
            live = await session.scalar(
                select(func.count())
                .select_from(VoiceCallModel)
                .where(VoiceCallModel.status.in_(live_statuses))
            )
            last_at = await session.scalar(select(func.max(VoiceCallModel.created_at)))
        return {
            **monitor,
            "calls_started": int(started or 0),
            "calls_completed": int(completed or 0),
            "escalations": int(escalations or 0),
            "live_calls": int(live or 0),
            "last_event_at": last_at.isoformat() if last_at else monitor.get("last_event_at"),
            "source": "database",
        }

    async def _usage_rollup(self) -> dict:
        period = _period_ym()
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopUsageCounterModel.metric, func.coalesce(func.sum(ShopUsageCounterModel.count), 0))
                    .where(ShopUsageCounterModel.period_ym == period)
                    .group_by(ShopUsageCounterModel.metric)
                )
            ).all()
            totals = {metric: int(total) for metric, total in rows}
        return {
            "period": period,
            "ai_calls": totals.get("ai_calls", 0),
            "sms": totals.get("sms", 0),
        }

    async def _usage_by_shop(self) -> dict[str, dict[str, int]]:
        period = _period_ym()
        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(ShopUsageCounterModel).where(ShopUsageCounterModel.period_ym == period)
                )
            ).all()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            key = str(r.shop_id)
            bucket = out.setdefault(key, {"ai_calls": 0, "sms": 0})
            if r.metric in bucket:
                bucket[r.metric] = int(r.count)
        return out

    async def _user_counts(self) -> dict:
        async with SessionLocal() as session:
            total_users = await session.scalar(select(func.count()).select_from(UserModel))
            active_users = await session.scalar(
                select(func.count()).select_from(UserModel).where(UserModel.is_active.is_(True))
            )
            memberships = await session.scalar(select(func.count()).select_from(ShopMembershipModel))
            by_role_rows = (
                await session.execute(
                    select(ShopMembershipModel.role, func.count())
                    .group_by(ShopMembershipModel.role)
                )
            ).all()
        return {
            "total": int(total_users or 0),
            "active": int(active_users or 0),
            "memberships": int(memberships or 0),
            "by_role": {str(role): int(count) for role, count in by_role_rows},
        }

    async def _users_by_shop(self) -> dict[str, int]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopMembershipModel.shop_id, func.count()).group_by(ShopMembershipModel.shop_id)
                )
            ).all()
        return {str(shop_id): int(count) for shop_id, count in rows}

    async def _owners_by_shop(self) -> dict[str, dict]:
        """Map shop_id → first membership with role=owner (full_name/email/phone)."""
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopMembershipModel, UserModel)
                    .join(UserModel, UserModel.id == ShopMembershipModel.user_id)
                    .where(func.lower(ShopMembershipModel.role) == UserRole.OWNER.value)
                    .order_by(ShopMembershipModel.created_at.asc())
                )
            ).all()
        out: dict[str, dict] = {}
        for membership, user in rows:
            key = str(membership.shop_id)
            if key in out:
                continue
            out[key] = {
                "user_id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "role": membership.role,
                "joined_at": membership.created_at.isoformat() if membership.created_at else None,
            }
        return out

    async def _active_logins_by_shop(self) -> dict[str, list[dict]]:
        """Map shop_id → users with a recent live session.

        Refresh tokens remain valid for days after tab close, so "online" requires a
        recently issued/rotated token (login or refresh within the access-token window).
        """
        now = datetime.now(timezone.utc)
        # Slight grace so a session mid-refresh is not dropped as offline.
        presence_minutes = max(settings.access_token_expire_minutes, 1) + 5
        since = now - timedelta(minutes=presence_minutes)
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(RefreshTokenModel, UserModel, ShopMembershipModel)
                    .join(UserModel, UserModel.id == RefreshTokenModel.user_id)
                    .outerjoin(
                        ShopMembershipModel,
                        (ShopMembershipModel.user_id == RefreshTokenModel.user_id)
                        & (ShopMembershipModel.shop_id == RefreshTokenModel.shop_id),
                    )
                    .where(
                        RefreshTokenModel.revoked_at.is_(None),
                        RefreshTokenModel.expires_at > now,
                        RefreshTokenModel.created_at >= since,
                    )
                    .order_by(RefreshTokenModel.created_at.desc())
                )
            ).all()
        out: dict[str, list[dict]] = {}
        seen: dict[str, set[str]] = {}
        for token, user, membership in rows:
            sid = str(token.shop_id)
            uid = str(user.id)
            shop_seen = seen.setdefault(sid, set())
            if uid in shop_seen:
                continue
            shop_seen.add(uid)
            out.setdefault(sid, []).append(
                {
                    "user_id": uid,
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone": user.phone,
                    "role": membership.role if membership is not None else None,
                    "joined_at": token.created_at.isoformat() if token.created_at else None,
                }
            )
        return out

    async def _last_activity_by_shop(self) -> dict[str, str | None]:
        """Best-effort last activity from refresh tokens, SMS, and voice (no schema change)."""
        activity: dict[str, datetime] = {}

        def _bump(shop_id: object, ts: datetime | None) -> None:
            if ts is None:
                return
            key = str(shop_id)
            prev = activity.get(key)
            if prev is None or ts > prev:
                activity[key] = ts

        async with SessionLocal() as session:
            token_rows = (
                await session.execute(
                    select(RefreshTokenModel.shop_id, func.max(RefreshTokenModel.created_at)).group_by(
                        RefreshTokenModel.shop_id
                    )
                )
            ).all()
            for shop_id, ts in token_rows:
                _bump(shop_id, ts)

            sms_rows = (
                await session.execute(
                    select(SmsConversationModel.shop_id, func.max(SmsConversationModel.last_message_at)).group_by(
                        SmsConversationModel.shop_id
                    )
                )
            ).all()
            for shop_id, ts in sms_rows:
                _bump(shop_id, ts)

            voice_rows = (
                await session.execute(
                    select(VoiceCallModel.shop_id, func.max(VoiceCallModel.created_at)).group_by(
                        VoiceCallModel.shop_id
                    )
                )
            ).all()
            for shop_id, ts in voice_rows:
                _bump(shop_id, ts)

        return {sid: ts.isoformat() if ts else None for sid, ts in activity.items()}

    async def _members_for_shop(self, shop_id: str) -> list[dict]:
        from uuid import UUID

        try:
            shop_uuid = UUID(shop_id)
        except ValueError:
            return []
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopMembershipModel, UserModel)
                    .join(UserModel, UserModel.id == ShopMembershipModel.user_id)
                    .where(ShopMembershipModel.shop_id == shop_uuid)
                    .order_by(ShopMembershipModel.role.asc(), UserModel.full_name.asc())
                )
            ).all()
        return [
            {
                "user_id": str(user.id),
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone,
                "role": membership.role,
                "is_active": bool(user.is_active),
                "joined_at": membership.created_at.isoformat() if membership.created_at else None,
            }
            for membership, user in rows
        ]

    async def _payments_summary(self) -> dict:
        async with SessionLocal() as session:
            rows = (await session.scalars(select(ShopSubscriptionModel))).all()
            plans = {
                p.id: p
                for p in (await session.scalars(select(SaasPlanModel))).all()
            }
        mrr = 0
        with_stripe = 0
        by_status: dict[str, int] = {}
        for sub in rows:
            by_status[sub.status] = by_status.get(sub.status, 0) + 1
            if sub.stripe_customer_id or sub.stripe_subscription_id:
                with_stripe += 1
            plan = plans.get(sub.plan_id)
            if sub.status == "active" and plan and plan.price_cents_monthly > 0:
                mrr += plan.price_cents_monthly
        return {
            "subscriptions": len(rows),
            "with_stripe": with_stripe,
            "mrr_cents": mrr,
            "by_status": by_status,
        }
