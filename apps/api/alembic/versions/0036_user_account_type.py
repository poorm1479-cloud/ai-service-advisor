"""Add users.account_type; allow null refresh_tokens.shop_id for platform admins.

Revision ID: 0036_user_account_type
Revises: 0035_user_username
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_user_account_type"
down_revision: Union[str, None] = "0035_user_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "account_type",
            sa.String(length=32),
            nullable=False,
            server_default="shop",
        ),
    )
    op.alter_column(
        "refresh_tokens",
        "shop_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM refresh_tokens WHERE shop_id IS NULL")
    op.alter_column(
        "refresh_tokens",
        "shop_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("users", "account_type")
