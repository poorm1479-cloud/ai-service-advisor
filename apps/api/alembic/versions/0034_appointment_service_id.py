"""Link appointments to service catalog (service_id).

Revision ID: 0034_appointment_service_id
Revises: 0033_shop_setup_service_catalog
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_appointment_service_id"
down_revision: Union[str, None] = "0033_shop_setup_service_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shop_services.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_appointments_service_id", "appointments", ["service_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_service_id", table_name="appointments")
    op.drop_column("appointments", "service_id")
