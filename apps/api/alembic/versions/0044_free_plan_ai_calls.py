"""Update Free plan AI calls: 10 / mo.

Revision ID: 0044_free_plan_ai_calls
Revises: 0043_voice_call_soft_delete
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_free_plan_ai_calls"
down_revision: Union[str, None] = "0043_voice_call_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 10
            WHERE id = 'free'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE saas_plans
            SET ai_calls_monthly = 50
            WHERE id = 'free'
            """
        )
    )
