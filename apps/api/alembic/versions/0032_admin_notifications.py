"""Admin notification center storage.

Revision ID: 0032_admin_notifications
Revises: 0031_user_notification_prefs
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_admin_notifications"
down_revision: Union[str, None] = "0031_user_notification_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unread"),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("dedupe_key", name="uq_admin_notifications_dedupe_key"),
    )
    op.create_index("ix_admin_notifications_event_type", "admin_notifications", ["event_type"])
    op.create_index("ix_admin_notifications_shop_id", "admin_notifications", ["shop_id"])
    op.create_index("ix_admin_notifications_status", "admin_notifications", ["status"])
    op.create_index("ix_admin_notifications_occurred", "admin_notifications", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_notifications_occurred", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_status", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_shop_id", table_name="admin_notifications")
    op.drop_index("ix_admin_notifications_event_type", table_name="admin_notifications")
    op.drop_table("admin_notifications")
