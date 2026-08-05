"""phase 14 mcp integration hub

Revision ID: 0014_phase14_mcp_hub
Revises: 0013_phase13_executive
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_phase14_mcp_hub"
down_revision: Union[str, None] = "0013_phase13_executive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_hub_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="disconnected"),
        sa.Column("api_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("credentials_json", sa.Text(), nullable=True),
        sa.Column("permissions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mcp_hub_connections_shop", "mcp_hub_connections", ["shop_id"])
    op.create_index("ix_mcp_hub_connections_shop_provider", "mcp_hub_connections", ["shop_id", "provider"])

    op.create_table(
        "mcp_hub_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("actions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mcp_hub_permissions_shop", "mcp_hub_permissions", ["shop_id"])
    op.create_index(
        "ix_mcp_hub_permissions_lookup",
        "mcp_hub_permissions",
        ["shop_id", "principal", "provider"],
    )

    op.create_table(
        "mcp_hub_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("event", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mcp_hub_logs_shop", "mcp_hub_logs", ["shop_id"])
    op.create_index("ix_mcp_hub_logs_shop_created", "mcp_hub_logs", ["shop_id", "created_at"])

    op.create_table(
        "mcp_hub_invokes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("api_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mcp_hub_invokes_shop", "mcp_hub_invokes", ["shop_id"])

    for table in ("mcp_hub_connections", "mcp_hub_permissions", "mcp_hub_logs", "mcp_hub_invokes"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_shop_isolation ON {table}
            FOR ALL
            USING (shop_id::text = current_setting('app.shop_id', true))
            WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
            """
        )


def downgrade() -> None:
    for table in ("mcp_hub_invokes", "mcp_hub_logs", "mcp_hub_permissions", "mcp_hub_connections"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
