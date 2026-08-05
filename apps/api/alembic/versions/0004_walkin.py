"""walk-in visits nullable vehicle customer

Revision ID: 0004_walkin
Revises: 0003_phase2
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_walkin"
down_revision: Union[str, None] = "0003_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("vehicles", "customer_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.drop_constraint("vehicles_customer_id_fkey", "vehicles", type_="foreignkey")
    op.create_foreign_key(
        "vehicles_customer_id_fkey",
        "vehicles",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "repair_histories", "customer_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True
    )
    op.drop_constraint("repair_histories_customer_id_fkey", "repair_histories", type_="foreignkey")
    op.create_foreign_key(
        "repair_histories_customer_id_fkey",
        "repair_histories",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "walk_in_visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vehicles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("complaint", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_walk_in_visits_shop_id", "walk_in_visits", ["shop_id"])
    op.create_index("ix_walk_in_visits_vehicle_id", "walk_in_visits", ["vehicle_id"])
    op.create_index("ix_walk_in_visits_customer_id", "walk_in_visits", ["customer_id"])

    op.execute("ALTER TABLE walk_in_visits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE walk_in_visits FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY walk_in_visits_shop_isolation ON walk_in_visits
        FOR ALL
        USING (shop_id::text = current_setting('app.shop_id', true))
        WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS walk_in_visits_shop_isolation ON walk_in_visits")
    op.drop_table("walk_in_visits")

    op.drop_constraint("repair_histories_customer_id_fkey", "repair_histories", type_="foreignkey")
    op.create_foreign_key(
        "repair_histories_customer_id_fkey",
        "repair_histories",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute("UPDATE repair_histories SET customer_id = customer_id WHERE customer_id IS NOT NULL")
    # Cannot safely force non-null if nulls exist; leave nullable on downgrade skip
    op.alter_column(
        "repair_histories", "customer_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True
    )

    op.drop_constraint("vehicles_customer_id_fkey", "vehicles", type_="foreignkey")
    op.create_foreign_key(
        "vehicles_customer_id_fkey",
        "vehicles",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("vehicles", "customer_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
