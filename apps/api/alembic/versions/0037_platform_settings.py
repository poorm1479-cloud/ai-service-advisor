"""Platform admin runtime settings key-value store.

Revision ID: 0037_platform_settings
Revises: 0036_user_account_type
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_platform_settings"
down_revision: Union[str, None] = "0036_user_account_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="null"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
