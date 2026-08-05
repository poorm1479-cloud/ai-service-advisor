"""phase 13 executive dashboard

Revision ID: 0013_phase13_executive
Revises: 0012_phase12_marketing
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_phase13_executive"
down_revision: Union[str, None] = "0012_phase12_marketing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "executive_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_executive_snapshots_shop", "executive_snapshots", ["shop_id"])
    op.create_index("ix_executive_snapshots_shop_gen", "executive_snapshots", ["shop_id", "generated_at"])

    op.create_table(
        "executive_live_state",
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    for table in ("executive_snapshots", "executive_live_state"):
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
    for table in ("executive_live_state", "executive_snapshots"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
