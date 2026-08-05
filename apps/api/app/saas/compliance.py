"""GDPR-oriented shop data export and deletion."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select, text

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import (
    CustomerModel,
    ShopMembershipModel,
    ShopModel,
    UserModel,
    VehicleModel,
    WalkInVisitModel,
)

logger = logging.getLogger("asa.compliance")


class ComplianceService:
    async def export_shop(self, shop_id: UUID) -> dict:
        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            shop = await session.get(ShopModel, shop_id)
            if shop is None:
                return {}
            memberships = (
                await session.scalars(
                    select(ShopMembershipModel).where(ShopMembershipModel.shop_id == shop_id)
                )
            ).all()
            users = []
            for m in memberships:
                u = await session.get(UserModel, m.user_id)
                if u:
                    users.append(
                        {
                            "user_id": str(u.id),
                            "full_name": u.full_name,
                            "email": u.email,
                            "phone": u.phone,
                            "role": m.role,
                        }
                    )
            customers = (
                await session.scalars(select(CustomerModel).where(CustomerModel.shop_id == shop_id))
            ).all()
            vehicles = (
                await session.scalars(select(VehicleModel).where(VehicleModel.shop_id == shop_id))
            ).all()
            walkins = (
                await session.scalars(select(WalkInVisitModel).where(WalkInVisitModel.shop_id == shop_id))
            ).all()
            return {
                "shop": {"id": str(shop.id), "name": shop.name, "slug": shop.slug},
                "members": users,
                "customers": [
                    {
                        "id": str(c.id),
                        "full_name": c.name,
                        "email": c.email,
                        "phone": c.phone,
                    }
                    for c in customers
                ],
                "vehicles": [
                    {"id": str(v.id), "vin": getattr(v, "vin", None), "customer_id": str(v.customer_id)}
                    for v in vehicles
                ],
                "walk_ins": [{"id": str(w.id), "status": w.status} for w in walkins],
            }

    async def delete_shop(self, shop_id: UUID) -> None:
        delete_payload: dict = {
            "shop_slug": "",
            "shop_name": "",
            "owner_email": None,
            "owner_phone": None,
            "owner_name": None,
            "deleted_user_count": 0,
            "member_count": 0,
        }
        async with SessionLocal() as session:
            await session.execute(
                text("SELECT set_config('app.shop_id', :sid, true)"),
                {"sid": str(shop_id)},
            )
            shop = await session.get(ShopModel, shop_id)
            if shop is None:
                return
            delete_payload["shop_slug"] = shop.slug
            delete_payload["shop_name"] = shop.name

            # Cascade from shops should remove most children; memberships/users may remain shared.
            memberships = (
                await session.scalars(
                    select(ShopMembershipModel).where(ShopMembershipModel.shop_id == shop_id)
                )
            ).all()
            delete_payload["member_count"] = len(memberships)
            user_ids = [m.user_id for m in memberships]

            # Capture owner contact before rows are removed.
            for m in memberships:
                if m.role != "owner":
                    continue
                owner = await session.get(UserModel, m.user_id)
                if owner:
                    delete_payload["owner_email"] = owner.email
                    delete_payload["owner_phone"] = owner.phone
                    delete_payload["owner_name"] = owner.full_name
                break

            await session.execute(delete(ShopModel).where(ShopModel.id == shop_id))
            deleted_users = 0
            for uid in user_ids:
                other = await session.scalar(
                    select(ShopMembershipModel.id).where(ShopMembershipModel.user_id == uid).limit(1)
                )
                if other is None:
                    await session.execute(delete(UserModel).where(UserModel.id == uid))
                    deleted_users += 1
            delete_payload["deleted_user_count"] = deleted_users
            await session.commit()

        await self._notify_shop_deleted(shop_id, delete_payload)

    async def _notify_shop_deleted(self, shop_id: UUID, payload: dict) -> None:
        """Mirror signup: emit domain event + durable admin notification fallback."""
        slug = payload.get("shop_slug") or str(shop_id)
        owner = payload.get("owner_email") or payload.get("owner_phone") or ""
        message = (
            f"shop={slug} owner={owner} deleted_users={payload.get('deleted_user_count', 0)}"
        ).strip()
        try:
            from app.workflows.emitter import emit_domain_event
            from app.workflows.enums import DomainEventType

            await emit_domain_event(
                shop_id=shop_id,
                event_type=DomainEventType.SAAS_SHOP_DELETED,
                payload=payload,
                source="compliance",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("saas.shop_deleted.emit_failed shop=%s err=%s", slug, exc)
        try:
            from app.admin.notifications import AdminNotificationService
            from app.workflows.enums import DomainEventType

            await AdminNotificationService().create(
                event_type=DomainEventType.SAAS_SHOP_DELETED.value,
                title="Shop deleted",
                message=message,
                severity="major",
                source="compliance",
                shop_id=shop_id,
                payload={
                    **payload,
                    "kind": "shop_deleted",
                    "domain_event_type": "saas.shop_deleted",
                },
                dedupe_key=f"saas.shop_deleted:{shop_id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("saas.shop_deleted.notify_failed shop=%s err=%s", slug, exc)
