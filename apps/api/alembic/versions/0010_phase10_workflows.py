"""phase 10 workflow engine

Revision ID: 0010_phase10_workflows
Revises: 0009_phase9_import
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase10_workflows"
down_revision: Union[str, None] = "0009_phase9_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column("conditions_json", sa.Text(), nullable=True),
        sa.Column("actions_json", sa.Text(), nullable=False),
        sa.Column("retry_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_workflow_definitions_shop", "workflow_definitions", ["shop_id"])
    op.create_index("ix_workflow_definitions_trigger", "workflow_definitions", ["trigger"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trigger_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_event_type", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("logs_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_runs_shop", "workflow_runs", ["shop_id"])
    op.create_index("ix_workflow_runs_workflow", "workflow_runs", ["workflow_id"])

    op.create_table(
        "workflow_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="system"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_workflow_events_shop", "workflow_events", ["shop_id"])
    op.create_index("ix_workflow_events_type", "workflow_events", ["shop_id", "event_type"])

    op.create_table(
        "workflow_retries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_workflow_retries_due", "workflow_retries", ["state", "next_attempt_at"])

    for table in ("workflow_definitions", "workflow_runs", "workflow_events", "workflow_retries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_shop_isolation ON {table}
            FOR ALL
            USING (
              shop_id IS NULL
              OR shop_id::text = current_setting('app.shop_id', true)
            )
            WITH CHECK (
              shop_id IS NULL
              OR shop_id::text = current_setting('app.shop_id', true)
            )
            """
        )


def downgrade() -> None:
    for table in ("workflow_retries", "workflow_events", "workflow_runs", "workflow_definitions"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
