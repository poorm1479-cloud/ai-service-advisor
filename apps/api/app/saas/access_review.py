"""Quarterly access-review export for SOC2 evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import ShopMembershipModel, ShopModel, UserModel


class AccessReviewService:
    async def export(self) -> dict:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ShopModel, ShopMembershipModel, UserModel)
                    .join(ShopMembershipModel, ShopMembershipModel.shop_id == ShopModel.id)
                    .join(UserModel, UserModel.id == ShopMembershipModel.user_id)
                    .order_by(ShopModel.slug, ShopMembershipModel.role, UserModel.full_name)
                )
            ).all()
            entries = []
            for shop, membership, user in rows:
                entries.append(
                    {
                        "shop_id": str(shop.id),
                        "shop_slug": shop.slug,
                        "shop_name": shop.name,
                        "user_id": str(user.id),
                        "full_name": user.full_name,
                        "email": user.email,
                        "phone": user.phone,
                        "role": membership.role,
                        "mfa_enabled": bool(getattr(user, "mfa_enabled", False)),
                        "is_active": bool(user.is_active),
                        "review_decision": "",  # filled by reviewer
                        "reviewer_notes": "",
                    }
                )
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "purpose": "quarterly_access_review",
                "entry_count": len(entries),
                "entries": entries,
                "instructions": [
                    "Review each row and set review_decision to keep|revoke|change_role",
                    "Attach this JSON (or CSV export) to the SOC2 evidence folder",
                    "Record reviewer name and date in change management notes",
                ],
            }
