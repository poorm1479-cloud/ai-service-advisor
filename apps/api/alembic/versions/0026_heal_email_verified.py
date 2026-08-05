"""Heal email_verified for email-primary accounts.

Revision ID: 0026_heal_email_verified
Revises: 0025_auth_method_choice
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_heal_email_verified"
down_revision: Union[str, None] = "0025_auth_method_choice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET email_verified = true
            WHERE primary_auth_method = 'email'
              AND email IS NOT NULL
              AND email_verified = false
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE users
            SET primary_auth_method = 'phone'
            WHERE phone IS NOT NULL
              AND phone_verified = true
              AND primary_auth_method = 'email'
            """
        )
    )


def downgrade() -> None:
    pass
