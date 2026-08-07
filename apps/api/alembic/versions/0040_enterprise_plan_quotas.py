"""Update Enterprise plan quotas: 500 AI / 500 SMS / 10 seats.

Revision ID: 0040_enterprise_plan_quotas
Revises: 0039_pro_plan_quotas
Create Date: 2026-08-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040_enterprise_plan_quotas"
down_revision: Union[str, None] = "0039_pro_plan_quotas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 500,
                sms_monthly = 500,
                seats = 10
            WHERE id = 'enterprise'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 20000,
                sms_monthly = 10000,
                seats = 100
            WHERE id = 'enterprise'
            """
        )
    )
