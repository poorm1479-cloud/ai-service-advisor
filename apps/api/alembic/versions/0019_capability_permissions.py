"""Capability-based shop permissions (Owner / Staff / AI Agent).

Revision ID: 0019_capability_permissions
Revises: 0018_phase18_enterprise
Create Date: 2026-07-29

Phase 17 permission architecture refactor:
- Replace job-title roles with Owner / Staff / AI Agent
- Add shop_memberships.capabilities_json
- Backfill legacy manager/service_advisor/mechanic → staff + capabilities
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_capability_permissions"
down_revision: Union[str, None] = "0018_phase18_enterprise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALL_CAPS = (
    '["customer_management","vehicle_management","appointment_management",'
    '"inspection_input","estimate_creation","repair_status_update",'
    '"customer_communication","payment_handling"]'
)


def upgrade() -> None:
    op.add_column(
        "shop_memberships",
        sa.Column("capabilities_json", sa.Text(), nullable=True),
    )

    # Normalize legacy job-title roles → staff/owner/ai_agent
    op.execute(
        sa.text(
            """
            UPDATE shop_memberships
            SET role = 'staff'
            WHERE lower(role) IN (
                'manager', 'service_advisor', 'mechanic',
                'receptionist', 'technician', 'serviceadvisor'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE shop_memberships
            SET role = 'ai_agent'
            WHERE lower(role) IN ('ai_agent', 'ai-agent', 'agent')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE shop_memberships
            SET role = 'owner'
            WHERE lower(role) = 'owner'
            """
        )
    )

    # Full capability set for all members (small-shop multi-function default)
    op.execute(
        sa.text(
            f"""
            UPDATE shop_memberships
            SET capabilities_json = '{_ALL_CAPS}'
            WHERE capabilities_json IS NULL
            """
        )
    )


def downgrade() -> None:
    # Keep roles as owner/staff/ai_agent (cannot safely restore job titles)
    op.drop_column("shop_memberships", "capabilities_json")
