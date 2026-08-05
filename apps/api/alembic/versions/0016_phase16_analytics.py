"""phase 16 analytics engine

Revision ID: 0016_phase16_analytics
Revises: 0015_phase15_memory
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_phase16_analytics"
down_revision: Union[str, None] = "0015_phase15_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("repair_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customers_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customers_returning", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("appointments_offered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("appointments_booked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marketing_spend", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("marketing_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("mechanic_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("billed_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ai_conversations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clv_cohort_avg", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("shop_id", "day", name="uq_analytics_facts_shop_day"),
    )
    op.create_index("ix_analytics_facts_shop_day", "analytics_facts", ["shop_id", "day"])

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_analytics_snapshots_shop", "analytics_snapshots", ["shop_id"])

    op.create_table(
        "analytics_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_analytics_reports_shop", "analytics_reports", ["shop_id"])

    op.create_table(
        "analytics_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_analytics_exports_shop", "analytics_exports", ["shop_id"])

    for table in ("analytics_facts", "analytics_snapshots", "analytics_reports", "analytics_exports"):
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
    for table in ("analytics_exports", "analytics_reports", "analytics_snapshots", "analytics_facts"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
