"""Platform-admin runtime settings (non-secret operational knobs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.config import settings
from app.infrastructure.database import Base, SessionLocal


class PlatformSettingModel(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


DEFAULTS: dict[str, Any] = {
    "dashboard_poll_seconds": 3,
    "notification_retention_days": 90,
    "toast_enabled": True,
    "maintenance_mode": False,
}

EDITABLE_KEYS = frozenset(DEFAULTS.keys())


class EditableSettingsPatch(BaseModel):
    dashboard_poll_seconds: int | None = Field(default=None, ge=3, le=60)
    notification_retention_days: int | None = Field(default=None, ge=1, le=365)
    toast_enabled: bool | None = None
    maintenance_mode: bool | None = None

    @field_validator("dashboard_poll_seconds")
    @classmethod
    def _poll_bounds(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return max(3, min(60, int(v)))

    @field_validator("notification_retention_days")
    @classmethod
    def _retention_bounds(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return max(1, min(365, int(v)))


def _env_snapshot() -> dict[str, Any]:
    allowlist = sorted(settings.platform_admin_username_set)
    return {
        "environment": settings.environment,
        "ai_provider": settings.ai_provider,
        "sms_enabled": settings.sms_enabled,
        "voice_enabled": settings.voice_enabled,
        "agents_enabled": settings.agents_enabled,
        "metrics_enabled": settings.metrics_enabled,
        "billing_trial_days": settings.billing_trial_days,
        "platform_admin_usernames": allowlist,
        "web_app_url": settings.web_app_url,
    }


class PlatformSettingsService:
    async def get(self) -> dict[str, Any]:
        editable, latest = await self._load_editable()
        return {
            "editable": editable,
            "env_snapshot": _env_snapshot(),
            "updated_at": latest.isoformat() if latest else None,
        }

    async def patch(self, body: EditableSettingsPatch, updated_by: str | None = None) -> dict[str, Any]:
        changes = body.model_dump(exclude_none=True)
        if not changes:
            return await self.get()
        now = datetime.now(timezone.utc)
        async with SessionLocal() as session:
            for key, value in changes.items():
                if key not in EDITABLE_KEYS:
                    continue
                row = await session.get(PlatformSettingModel, key)
                payload = json.dumps(value)
                if row is None:
                    session.add(
                        PlatformSettingModel(
                            key=key,
                            value_json=payload,
                            updated_at=now,
                            updated_by=updated_by,
                        )
                    )
                else:
                    row.value_json = payload
                    row.updated_at = now
                    row.updated_by = updated_by
            await session.commit()
        return await self.get()

    async def dashboard_poll_seconds(self) -> int:
        editable, _ = await self._load_editable()
        raw = editable.get("dashboard_poll_seconds", DEFAULTS["dashboard_poll_seconds"])
        try:
            return max(3, min(60, int(raw)))
        except (TypeError, ValueError):
            return int(DEFAULTS["dashboard_poll_seconds"])

    async def notification_retention_days(self) -> int:
        editable, _ = await self._load_editable()
        raw = editable.get("notification_retention_days", DEFAULTS["notification_retention_days"])
        try:
            return max(1, min(365, int(raw)))
        except (TypeError, ValueError):
            return int(DEFAULTS["notification_retention_days"])

    async def toast_enabled(self) -> bool:
        editable, _ = await self._load_editable()
        return bool(editable.get("toast_enabled", DEFAULTS["toast_enabled"]))

    async def maintenance_mode(self) -> bool:
        editable, _ = await self._load_editable()
        return bool(editable.get("maintenance_mode", DEFAULTS["maintenance_mode"]))

    async def _load_editable(self) -> tuple[dict[str, Any], datetime | None]:
        merged = dict(DEFAULTS)
        latest: datetime | None = None
        async with SessionLocal() as session:
            rows = (await session.scalars(select(PlatformSettingModel))).all()
            for row in rows:
                if row.key not in EDITABLE_KEYS:
                    continue
                try:
                    merged[row.key] = json.loads(row.value_json)
                except json.JSONDecodeError:
                    continue
                if latest is None or row.updated_at > latest:
                    latest = row.updated_at
        return merged, latest
