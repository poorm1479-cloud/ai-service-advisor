"""Update Pro plan: 150 AI calls / $150.

Revision ID: 0045_pro_plan_ai_price
Revises: 0044_free_plan_ai_calls
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_pro_plan_ai_price"
down_revision: Union[str, None] = "0044_free_plan_ai_calls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 150,
                price_cents_monthly = 15000
            WHERE id = 'pro'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 200,
                price_cents_monthly = 9900
            WHERE id = 'pro'
            """
        )
    )
