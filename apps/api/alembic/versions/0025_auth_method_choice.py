"""Allow phone-or-email primary auth with email OTP verification.

Revision ID: 0025_auth_method_choice
Revises: 0024_phone_primary_auth
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_auth_method_choice"
down_revision: Union[str, None] = "0024_phone_primary_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "primary_auth_method",
            sa.String(length=16),
            nullable=False,
            server_default="phone",
        ),
    )
    # Phone may be null for email-primary accounts (PostgreSQL unique allows multiple NULLs)
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)
    op.execute(
        sa.text(
            """
            UPDATE users
            SET primary_auth_method = CASE
              WHEN phone IS NOT NULL AND phone_verified THEN 'phone'
              WHEN email IS NOT NULL THEN 'email'
              ELSE 'phone'
            END,
            email_verified = CASE
              WHEN email IS NOT NULL AND phone IS NULL THEN true
              ELSE false
            END
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE users
            SET phone = COALESCE(
              phone,
              '+1' || lpad(right(replace(id::text, '-', ''), 10), 10, '0')
            )
            WHERE phone IS NULL
            """
        )
    )
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.drop_column("users", "primary_auth_method")
    op.drop_column("users", "email_verified")
