"""Phase 21 — AI Learning Loop tables.

Revision ID: 0023_phase21_learning_loop
Revises: 0022_phase20_revenue_intelligence
Create Date: 2026-07-29

Additive only. Does not alter Workflow Engine or business rule tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_phase21_learning_loop"
down_revision: Union[str, None] = "0022_phase20_revenue_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_decision_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_kind", sa.String(128), nullable=False),
        sa.Column("outcome_kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_learning_decision_results_shop",
        "learning_decision_results",
        ["shop_id"],
    )
    op.create_index(
        "ix_learning_decision_results_kind",
        "learning_decision_results",
        ["shop_id", "decision_kind"],
    )

    op.create_table(
        "learning_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("staff_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_kind", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_learning_feedback_shop", "learning_feedback", ["shop_id"])
    op.create_index(
        "ix_learning_feedback_source",
        "learning_feedback",
        ["shop_id", "source"],
    )

    op.create_table(
        "learning_success_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern_key", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("decision_kinds_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("signals_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_learning_success_patterns_shop",
        "learning_success_patterns",
        ["shop_id"],
    )
    op.create_index(
        "ix_learning_success_patterns_key",
        "learning_success_patterns",
        ["shop_id", "pattern_key"],
        unique=True,
    )

    op.execute(
        sa.text(
            """
            ALTER TABLE learning_decision_results ENABLE ROW LEVEL SECURITY;
            ALTER TABLE learning_decision_results FORCE ROW LEVEL SECURITY;
            CREATE POLICY learning_decision_results_shop_isolation
              ON learning_decision_results
              USING (shop_id::text = current_setting('app.shop_id', true));

            ALTER TABLE learning_feedback ENABLE ROW LEVEL SECURITY;
            ALTER TABLE learning_feedback FORCE ROW LEVEL SECURITY;
            CREATE POLICY learning_feedback_shop_isolation
              ON learning_feedback
              USING (shop_id::text = current_setting('app.shop_id', true));

            ALTER TABLE learning_success_patterns ENABLE ROW LEVEL SECURITY;
            ALTER TABLE learning_success_patterns FORCE ROW LEVEL SECURITY;
            CREATE POLICY learning_success_patterns_shop_isolation
              ON learning_success_patterns
              USING (shop_id::text = current_setting('app.shop_id', true));
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS learning_success_patterns_shop_isolation
              ON learning_success_patterns;
            DROP POLICY IF EXISTS learning_feedback_shop_isolation
              ON learning_feedback;
            DROP POLICY IF EXISTS learning_decision_results_shop_isolation
              ON learning_decision_results;
            """
        )
    )
    op.drop_table("learning_success_patterns")
    op.drop_table("learning_feedback")
    op.drop_table("learning_decision_results")
