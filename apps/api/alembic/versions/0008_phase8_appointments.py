"""phase 8 appointment intelligence

Revision ID: 0008_phase8_appointments
Revises: 0007_phase7_voice
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_phase8_appointments"
down_revision: Union[str, None] = "0007_phase7_voice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mechanics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("skills_json", sa.Text(), nullable=True),
        sa.Column("work_start", sa.String(8), nullable=False, server_default="08:00"),
        sa.Column("work_end", sa.String(8), nullable=False, server_default="17:00"),
        sa.Column("workdays_json", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False, server_default="75"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mechanics_shop_id", "mechanics", ["shop_id"])

    op.create_table(
        "bays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("bay_type", sa.String(32), nullable=False, server_default="general"),
        sa.Column("supports_json", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_bays_shop_id", "bays", ["shop_id"])

    op.create_table(
        "shop_business_hours",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.String(8), nullable=False),
        sa.Column("close_time", sa.String(8), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_shop_business_hours_shop_id", "shop_business_hours", ["shop_id"])

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mechanics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bay_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bays.id", ondelete="SET NULL"), nullable=True),
        sa.Column("walk_in_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("walk_in_visits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="booked"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("repair_type", sa.String(32), nullable=False, server_default="general"),
        sa.Column("vehicle_type", sa.String(32), nullable=False, server_default="sedan"),
        sa.Column("estimated_duration_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("source", sa.String(32), nullable=False, server_default="dashboard"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("estimated_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("estimated_completion", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wait_time_min", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_appointments_shop_id", "appointments", ["shop_id"])
    op.create_index("ix_appointments_start_at", "appointments", ["start_at"])
    op.create_index("ix_appointments_mechanic_id", "appointments", ["mechanic_id"])
    op.create_index("ix_appointments_bay_id", "appointments", ["bay_id"])

    for table in ("mechanics", "bays", "shop_business_hours", "appointments"):
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
    for table in ("appointments", "shop_business_hours", "bays", "mechanics"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.drop_table(table)
