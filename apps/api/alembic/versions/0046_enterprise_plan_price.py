"""Update Enterprise plan price to $400.

Revision ID: 0046_enterprise_plan_price
Revises: 0045_pro_plan_ai_price
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046_enterprise_plan_price"
down_revision: Union[str, None] = "0045_pro_plan_ai_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET price_cents_monthly = 40000
            WHERE id = 'enterprise'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET price_cents_monthly = 29900
            WHERE id = 'enterprise'
            """
        )
    )
