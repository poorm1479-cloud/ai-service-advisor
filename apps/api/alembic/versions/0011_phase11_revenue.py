"""phase 11 revenue intelligence

Revision ID: 0011_phase11_revenue
Revises: 0010_phase10_workflows
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_phase11_revenue"
down_revision: Union[str, None] = "0010_phase10_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revenue_analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("customers_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opportunities_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_revenue_analysis_jobs_shop", "revenue_analysis_jobs", ["shop_id"])

    op.create_table(
        "revenue_opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("revenue_analysis_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expected_revenue", sa.Numeric(12, 2), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("expected_roi", sa.Float(), nullable=False),
        sa.Column("recommended_contact_date", sa.Date(), nullable=False),
        sa.Column("recommended_channel", sa.String(16), nullable=False),
        sa.Column("recommended_message", sa.Text(), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("vehicle_label", sa.String(255), nullable=True),
        sa.Column("customer_health", sa.Float(), nullable=True),
        sa.Column("vehicle_health", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("seasonality_boost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_revenue_opportunities_shop", "revenue_opportunities", ["shop_id"])
    op.create_index("ix_revenue_opportunities_horizon", "revenue_opportunities", ["shop_id", "horizon"])
    op.create_index("ix_revenue_opportunities_status", "revenue_opportunities", ["shop_id", "status"])

    op.create_table(
        "revenue_health_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("band", sa.String(16), nullable=False),
        sa.Column("factors_json", sa.Text(), nullable=True),
        sa.Column("notes_json", sa.Text(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_revenue_health_scores_shop", "revenue_health_scores", ["shop_id", "entity_type"])

    for table in ("revenue_analysis_jobs", "revenue_opportunities", "revenue_health_scores"):
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
    for table in ("revenue_health_scores", "revenue_opportunities", "revenue_analysis_jobs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
