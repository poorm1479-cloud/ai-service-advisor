"""MFA backup codes and public status incidents.

Revision ID: 0030_mfa_backup_incidents
Revises: 0029_sms_idempotency
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_mfa_backup_incidents"
down_revision: Union[str, None] = "0029_sms_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_backup_codes_json", sa.Text(), nullable=True))

    op.create_table(
        "status_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="minor"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="investigating"),
        sa.Column("affected_components", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_status_incidents_started", "status_incidents", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_status_incidents_started", table_name="status_incidents")
    op.drop_table("status_incidents")
    op.drop_column("users", "mfa_backup_codes_json")
