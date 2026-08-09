"""Add shops.ai_paused for dashboard AI pause.

Revision ID: 0042_shop_ai_paused
Revises: 0041_voice_sid_lookup_rls
Create Date: 2026-08-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042_shop_ai_paused"
down_revision: Union[str, None] = "0041_voice_sid_lookup_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shops",
        sa.Column(
            "ai_paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("shops", "ai_paused")
