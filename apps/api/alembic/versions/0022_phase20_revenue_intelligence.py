"""Phase 20 — Revenue Intelligence retention/campaign insight tables.

Revision ID: 0022_phase20_revenue_intelligence
Revises: 0021_phase19_knowledge_memory
Create Date: 2026-07-29

Additive only. Does not alter Workflow Engine or existing revenue_intel tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_phase20_revenue_intelligence"
down_revision: Union[str, None] = "0021_phase19_knowledge_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Default alembic_version.version_num is VARCHAR(32); this revision id is 33 chars.
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
    )
    op.create_table(
        "revenue_retention_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_revenue_retention_insights_shop",
        "revenue_retention_insights",
        ["shop_id"],
    )
    op.create_index(
        "ix_revenue_retention_insights_kind",
        "revenue_retention_insights",
        ["shop_id", "kind"],
    )

    op.execute(
        sa.text(
            """
            ALTER TABLE revenue_retention_insights ENABLE ROW LEVEL SECURITY;
            ALTER TABLE revenue_retention_insights FORCE ROW LEVEL SECURITY;
            CREATE POLICY revenue_retention_insights_shop_isolation
              ON revenue_retention_insights
              USING (shop_id::text = current_setting('app.shop_id', true));
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS revenue_retention_insights_shop_isolation "
            "ON revenue_retention_insights;"
        )
    )
    op.drop_table("revenue_retention_insights")
