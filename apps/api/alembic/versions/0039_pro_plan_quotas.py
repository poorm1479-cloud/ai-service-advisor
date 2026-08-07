"""Update Pro plan quotas: 200 AI / 200 SMS / 4 seats.

Revision ID: 0039_pro_plan_quotas
Revises: 0038_free_plan_quotas
Create Date: 2026-08-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_pro_plan_quotas"
down_revision: Union[str, None] = "0038_free_plan_quotas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 200,
                sms_monthly = 200,
                seats = 4
            WHERE id = 'pro'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 2000,
                sms_monthly = 1000,
                seats = 10
            WHERE id = 'pro'
            """
        )
    )
