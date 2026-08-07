"""Update Free plan quotas: 50 AI / 50 SMS / 2 seats.

Revision ID: 0038_free_plan_quotas
Revises: 0037_platform_settings
Create Date: 2026-08-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_free_plan_quotas"
down_revision: Union[str, None] = "0037_platform_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 50,
                sms_monthly = 50,
                seats = 2
            WHERE id = 'free'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 100,
                sms_monthly = 100,
                seats = 2
            WHERE id = 'free'
            """
        )
    )
