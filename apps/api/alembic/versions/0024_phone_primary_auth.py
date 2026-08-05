"""Phone-primary auth — users.phone unique, email secondary/optional.

Revision ID: 0024_phone_primary_auth
Revises: 0023_phase21_learning_loop
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_phone_primary_auth"
down_revision: Union[str, None] = "0023_phase21_learning_loop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Backfill unique phones for legacy email-only rows
    op.execute(
        sa.text(
            """
            UPDATE users
            SET phone = '+1' || lpad(
              right(replace(id::text, '-', ''), 10),
              10,
              '0'
            )
            WHERE phone IS NULL
            """
        )
    )

    op.alter_column("users", "phone", nullable=False)
    op.create_index("ix_users_phone", "users", ["phone"], unique=False)
    op.create_unique_constraint("uq_users_phone", "users", ["phone"])

    # Email becomes optional secondary identifier
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_email"))
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_not_null
            ON users (lower(email))
            WHERE email IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_users_email_not_null"))
    # Ensure emails exist before restoring NOT NULL
    op.execute(
        sa.text(
            """
            UPDATE users
            SET email = 'legacy-' || replace(id::text, '-', '') || '@example.invalid'
            WHERE email IS NULL
            """
        )
    )
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.create_unique_constraint("users_email_key", "users", ["email"])

    op.drop_constraint("uq_users_phone", "users", type_="unique")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "phone")
