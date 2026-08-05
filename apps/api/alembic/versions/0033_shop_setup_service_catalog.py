"""Shop setup profiles + per-shop service catalog.

Revision ID: 0033_shop_setup_service_catalog
Revises: 0032_admin_notifications
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_shop_setup_service_catalog"
down_revision: Union[str, None] = "0032_admin_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_setup_profiles",
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("country", sa.String(64), nullable=False, server_default="US"),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "shop_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False, server_default="other"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("skill", sa.String(64), nullable=False, server_default="general"),
        sa.Column("bay", sa.String(64), nullable=False, server_default="general"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_shop_services_shop_id", "shop_services", ["shop_id"])

    # Deduplicate any existing hours rows before unique constraint.
    op.execute(
        """
        DELETE FROM shop_business_hours a
        USING shop_business_hours b
        WHERE a.ctid < b.ctid
          AND a.shop_id = b.shop_id
          AND a.weekday = b.weekday
        """
    )
    op.create_unique_constraint(
        "uq_shop_business_hours_shop_weekday",
        "shop_business_hours",
        ["shop_id", "weekday"],
    )

    for table in ("shop_setup_profiles", "shop_services"):
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
    for table in ("shop_services", "shop_setup_profiles"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
    op.drop_index("ix_shop_services_shop_id", table_name="shop_services")
    op.drop_table("shop_services")
    op.drop_table("shop_setup_profiles")
    op.drop_constraint("uq_shop_business_hours_shop_weekday", "shop_business_hours", type_="unique")
