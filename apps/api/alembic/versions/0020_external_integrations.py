"""External Integration Layer — sync cursors and audit (adapters only).

Revision ID: 0020_external_integrations
Revises: 0019_capability_permissions
Create Date: 2026-07-29

Does not alter CRM / Workflow / Plugin / MCP Hub tables. Adds tenant-scoped
sync state for the External Integration Layer only.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_external_integrations"
down_revision: Union[str, None] = "0019_capability_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_sync_cursors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("cursor_token", sa.String(512), nullable=True),
        sa.Column("last_external_id", sa.String(255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "shop_id",
            "tenant_id",
            "provider",
            "capability",
            name="uq_integration_sync_cursor",
        ),
    )
    op.create_index(
        "ix_integration_sync_cursors_shop",
        "integration_sync_cursors",
        ["shop_id"],
    )
    op.create_index(
        "ix_integration_sync_cursors_tenant",
        "integration_sync_cursors",
        ["tenant_id"],
    )

    op.create_table(
        "integration_sync_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("payload_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_integration_sync_audit_shop",
        "integration_sync_audit",
        ["shop_id"],
    )
    op.create_index(
        "ix_integration_sync_audit_tenant",
        "integration_sync_audit",
        ["tenant_id"],
    )

    # RLS — shop isolation (same pattern as mcp_hub / CRM)
    op.execute(
        sa.text(
            """
            ALTER TABLE integration_sync_cursors ENABLE ROW LEVEL SECURITY;
            ALTER TABLE integration_sync_cursors FORCE ROW LEVEL SECURITY;
            CREATE POLICY integration_sync_cursors_shop_isolation
              ON integration_sync_cursors
              USING (shop_id::text = current_setting('app.shop_id', true));

            ALTER TABLE integration_sync_audit ENABLE ROW LEVEL SECURITY;
            ALTER TABLE integration_sync_audit FORCE ROW LEVEL SECURITY;
            CREATE POLICY integration_sync_audit_shop_isolation
              ON integration_sync_audit
              USING (shop_id::text = current_setting('app.shop_id', true));
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS integration_sync_audit_shop_isolation ON integration_sync_audit;
            DROP POLICY IF EXISTS integration_sync_cursors_shop_isolation ON integration_sync_cursors;
            """
        )
    )
    op.drop_table("integration_sync_audit")
    op.drop_table("integration_sync_cursors")
